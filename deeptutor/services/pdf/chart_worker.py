#!/usr/bin/env python3
"""报告图表/ODE 检查的**可信 worker**（P1-33 / R4 / R7）。

这是仓库里的一个可执行脚本，P33 只把它**单独只读挂载**进报告沙箱，绝不复制到
模型可写的目录后再信任执行。它只用标准库，因此不依赖仓库源码可见性。

调用（argv 全部由服务端生成，模型不能提供任何一项）::

    python -I -B <trusted>/chart_worker.py --chart '<spec json>'
    python -I -B <trusted>/chart_worker.py --ode   '<spec json>'
    python -I -B <trusted>/chart_worker.py --ode-samples '<inner spec json>'   # 内部自用

``spec`` 是服务端生成的 JSON：``script`` / ``expected_png`` / ``expression`` /
``points`` / ``cpu_seconds`` / ``memory_mb`` / ``max_file_bytes`` / ``wall_clock_s``。

三条硬性质：

1. **worker 自己的输出有界。** 模型脚本的 stdout/stderr 用非阻塞 select 边读边丢，
   只保留固定大小的尾部；不会先 ``communicate()`` 整段再截断（那会在 64MiB 地址空间
   上限下把自己 OOM 掉）。控制 envelope 只放很短的服务端诊断尾巴。
2. **控制协议与诊断分离。** stdout 上恰好一个 JSON 对象；模型脚本的输出永远走管道，
   不进入 worker 的 stdout。
3. **ODE 结论由可信父进程算。** 模型脚本在**独立不可信子进程**里运行，只能回报五点
   ``(x, y, f(x,y))`` 采样值；父 worker 在同一个 OS 隔离环境里用服务端已验证表达式
   自己算参考值、有限性与误差。模型在 stdout 上伪造 ``ok/finite/max_abs_error``
   没有任何作用。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import resource
import selectors
import subprocess
import sys
import time

#: 回传诊断尾巴的上限（服务端只把原始输出用于私有排查）。
MAX_TAIL_CHARS = 600
#: 单次读取的分块大小：读取期间就丢弃超额部分，内存只保留尾部。
READ_CHUNK = 65536
#: ODE 检查点数量上限（服务端固定用 5 个）。
MAX_ODE_POINTS = 32

_MODES = ("--chart", "--ode", "--ode-samples")

_SAFE_NAMES = {
    "sin": math.sin,
    "cos": math.cos,
    "exp": math.exp,
    "log": math.log,
    "sqrt": math.sqrt,
    "abs": abs,
}


class WorkerError(Exception):
    """worker 自身无法完成任务（不是模型脚本失败）。"""


# ---------------------------------------------------------------------------
# 有界输出
# ---------------------------------------------------------------------------
class _TailBuffer:
    """只保留最后 ``limit`` 字节；更早的字节在读取期间就丢弃。"""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._buffer = bytearray()
        self.dropped = 0

    def feed(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)
        if len(self._buffer) > self.limit:
            excess = len(self._buffer) - self.limit
            self.dropped += excess
            del self._buffer[:excess]

    def text(self) -> str:
        return bytes(self._buffer).decode("utf-8", errors="replace")


class _BoundedSink(io.TextIOBase):
    """``redirect_stdout`` 用：写入被接受但只留尾部，内存有界。"""

    def __init__(self, limit: int = 4096) -> None:
        super().__init__()
        self._tail = _TailBuffer(limit)

    def write(self, text: str) -> int:  # type: ignore[override]
        self._tail.feed(text.encode("utf-8", errors="replace"))
        return len(text)

    def flush(self) -> None:  # pragma: no cover - 无需动作
        return None


def _reject_constant(name: str) -> float:
    raise WorkerError(f"非标准数字常量 {name}")


def _emit(payload: dict) -> None:
    """把**唯一**结果对象写到 stdout（worker 的 stdout 只用于这一件事）。"""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _load_object(raw: object) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise WorkerError("spec 为空")
    try:
        value = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise WorkerError("spec 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise WorkerError("spec 顶层不是对象")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise WorkerError("控制对象包含重复字段")
        value[key] = item
    return value


def _require_int(spec: dict, key: str, *, minimum: int, maximum: int) -> int:
    value = spec.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerError(f"{key} 必须是整数")
    if not minimum <= value <= maximum:
        raise WorkerError(f"{key} 超出允许范围")
    return value


def _safe_basename(value: object, what: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WorkerError(f"{what} 必须是裸文件名")
    if "/" in value or "\\" in value or "\0" in value or value in (".", ".."):
        raise WorkerError(f"{what} 不能包含路径分隔符")
    return value


def _tail(text: str | None) -> str:
    if not text:
        return ""
    return text[-MAX_TAIL_CHARS:]


# ---------------------------------------------------------------------------
# 资源上限（必须在运行模型脚本之前设置）
# ---------------------------------------------------------------------------
def _set_hard_limits(spec: dict) -> dict:
    cpu_seconds = _require_int(spec, "cpu_seconds", minimum=1, maximum=600)
    memory_mb = _require_int(spec, "memory_mb", minimum=64, maximum=65536)
    max_file_bytes = _require_int(spec, "max_file_bytes", minimum=1024, maximum=1 << 32)
    address_space = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError) as exc:  # pragma: no cover - 依赖宿主已有 hard limit
        raise WorkerError(f"无法设置资源上限：{type(exc).__name__}") from exc
    return {
        "cpu_seconds": cpu_seconds,
        "memory_mb": memory_mb,
        "max_file_bytes": max_file_bytes,
    }


# ---------------------------------------------------------------------------
# 产物
# ---------------------------------------------------------------------------
def _artifact(workdir: str, expected_png: str) -> dict | None:
    """工作目录里当前存在的期望产物；符号链接/目录/缺失一律不算。"""
    path = os.path.join(workdir, expected_png)
    if os.path.islink(path):
        return None
    try:
        info = os.stat(path)
    except OSError:
        return None
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"name": expected_png, "size": info.st_size, "sha256": digest.hexdigest()}


# ---------------------------------------------------------------------------
# 运行子进程：读取期间即有界
# ---------------------------------------------------------------------------
def _run_bounded_child(
    argv: list[str],
    workdir: str,
    *,
    timeout_s: int,
    tail_chars: int = MAX_TAIL_CHARS,
) -> dict:
    """运行 *argv*，只保留 stdout/stderr 的尾部，绝不整段物化。"""
    try:
        process = subprocess.Popen(
            argv,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
    except OSError as exc:
        raise WorkerError(f"无法启动子进程：{type(exc).__name__}") from exc

    selector = selectors.DefaultSelector()
    buffers = {"stdout": _TailBuffer(tail_chars), "stderr": _TailBuffer(tail_chars)}
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    for name, stream in streams.items():
        if stream is None:  # pragma: no cover - 防御
            continue
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)

    timed_out = False
    deadline = time.monotonic() + max(1, timeout_s)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _events in selector.select(timeout=min(remaining, 0.25)):
                stream = key.fileobj
                try:
                    chunk = stream.read(READ_CHUNK)  # type: ignore[union-attr]
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError:  # pragma: no cover - 管道异常
                    chunk = b""
                if chunk:
                    buffers[key.data].feed(chunk)
                else:
                    with contextlib.suppress(KeyError, ValueError):
                        selector.unregister(stream)
    finally:
        with contextlib.suppress(Exception):
            selector.close()
        if timed_out or process.poll() is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - 需要内核级异常
            with contextlib.suppress(ProcessLookupError, OSError):
                process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)
        for stream in streams.values():
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()

    exit_code = 124 if timed_out else int(process.returncode or 0)
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_tail": _tail(buffers["stdout"].text()),
        "stderr_tail": _tail(buffers["stderr"].text()),
        "stdout_truncated": buffers["stdout"].dropped > 0,
    }


# ---------------------------------------------------------------------------
# chart 模式
# ---------------------------------------------------------------------------
def _chart_mode(spec: dict, workdir: str) -> int:
    script = _safe_basename(spec.get("script"), "script")
    expected_png = _safe_basename(spec.get("expected_png"), "expected_png")
    wall_clock_s = _require_int(spec, "wall_clock_s", minimum=1, maximum=600)
    _set_hard_limits(spec)
    outcome = _run_bounded_child(
        [sys.executable, "-I", "-B", os.path.join(workdir, script)],
        workdir,
        timeout_s=max(1, wall_clock_s - 2),
    )
    artifact = None if outcome["timed_out"] else _artifact(workdir, expected_png)
    if outcome["timed_out"]:
        status = "timed_out"
    elif outcome["exit_code"] != 0:
        status = "script_failed"
    elif artifact is None:
        status = "no_artifact"
    else:
        status = "ok"
    _emit(
        {
            "schema": 1,
            "mode": "chart",
            "status": status,
            "exit_code": outcome["exit_code"],
            "timed_out": outcome["timed_out"],
            "expected_png": expected_png,
            "artifact": artifact,
            "stdout_tail": outcome["stdout_tail"],
            "stderr_tail": outcome["stderr_tail"],
        }
    )
    return 0


# ---------------------------------------------------------------------------
# ode 模式：可信父进程算参考值，模型子进程只提供采样
# ---------------------------------------------------------------------------
def _validate_points(points: object) -> list[list[float]]:
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_ODE_POINTS:
        raise WorkerError("points 必须是 1..%d 个点" % MAX_ODE_POINTS)
    checked: list[list[float]] = []
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in point)
        ):
            raise WorkerError("points 里必须是 [x, y] 数值对")
        checked.append([float(point[0]), float(point[1])])
    return checked


def _parse_samples(stdout: str, expected: list[list[float]]) -> list[float]:
    """严格解析不可信子进程的采样输出：只接受固定结构的五点 ``f`` 值。"""
    try:
        payload = json.loads(
            stdout.strip(), parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
    except (json.JSONDecodeError, WorkerError) as exc:
        raise WorkerError("采样输出不是合法 JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"samples"}:
        raise WorkerError("采样输出结构不符")
    samples = payload["samples"]
    if not isinstance(samples, list) or len(samples) != len(expected):
        raise WorkerError("采样点数量不符")
    values: list[float] = []
    for index, sample in enumerate(samples):
        if (
            not isinstance(sample, list)
            or len(sample) != 3
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in sample)
        ):
            raise WorkerError("采样结构不符")
        x_value, y_value, value = (float(item) for item in sample)
        if x_value != expected[index][0] or y_value != expected[index][1]:
            raise WorkerError("采样点与服务端固定点不一致")
        values.append(value)
    return values


def _reference_error(expression: str, points: list[list[float]], values: list[float]) -> float:
    """可信父进程自己算参考值与最大绝对误差（只用服务端已验证表达式）。"""
    try:
        code = compile(expression, "<ode_expression>", "eval")
    except (SyntaxError, ValueError) as exc:  # pragma: no cover - 已在服务端校验
        raise WorkerError("expression 无法编译") from exc
    errors: list[float] = []
    for index, (x_value, y_value) in enumerate(points):
        if index >= len(values):
            raise WorkerError("采样不足")
        got = values[index]
        if not math.isfinite(got):
            raise WorkerError("采样值非有限")
        expected = float(
            eval(  # noqa: S307 - AST 白名单 + 隔离环境 + 空 builtins
                code, {"__builtins__": {}}, {**_SAFE_NAMES, "x": x_value, "y": y_value}
            )
        )
        if not math.isfinite(expected):
            raise WorkerError("参考值非有限")
        difference = abs(got - expected)
        if not math.isfinite(difference):
            raise WorkerError("误差非有限")
        errors.append(difference)
    if not errors:  # pragma: no cover - points 非空
        raise WorkerError("没有可比较的点")
    return max(errors)


def _ode_samples_mode(spec: dict, workdir: str) -> int:
    """**不可信**子进程：只 import 模型脚本、只回报五点采样值。"""
    script = _safe_basename(spec.get("script"), "script")
    points = _validate_points(spec.get("points"))
    _set_hard_limits(spec)
    path = os.path.join(workdir, script)
    if os.path.islink(path) or not os.path.isfile(path):
        _emit({"samples": []})
        return 0

    samples: list[list[float]] = []
    try:
        loader = importlib.util.spec_from_file_location("_chart_model", path)
        if loader is None or loader.loader is None:  # pragma: no cover - 防御
            _emit({"samples": []})
            return 0
        module = importlib.util.module_from_spec(loader)
        with contextlib.redirect_stdout(_BoundedSink()), contextlib.redirect_stderr(_BoundedSink()):
            loader.loader.exec_module(module)
            func = getattr(module, "f", None)
            if callable(func):
                for x_value, y_value in points:
                    value = func(x_value, y_value)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        samples = []
                        break
                    samples.append([x_value, y_value, float(value)])
    except BaseException:  # noqa: BLE001 - 模型脚本的任何异常都只表示"没有采样"
        samples = []
    _emit({"samples": samples})
    return 0


def _ode_mode(spec: dict, workdir: str) -> int:
    """**可信**父 worker：起不可信子进程取采样，自己算参考值/误差/有限性。"""
    script = _safe_basename(spec.get("script"), "script")
    expression = spec.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise WorkerError("expression 不能为空")
    points = _validate_points(spec.get("points"))
    wall_clock_s = _require_int(spec, "wall_clock_s", minimum=1, maximum=600)
    limits = _set_hard_limits(spec)
    inner = {"script": script, "points": points, **limits}
    outcome = _run_bounded_child(
        [
            sys.executable,
            "-I",
            "-B",
            os.path.abspath(__file__),
            "--ode-samples",
            json.dumps(inner, ensure_ascii=False),
        ],
        workdir,
        timeout_s=max(1, wall_clock_s - 2),
    )
    checks: dict | None
    if outcome["timed_out"]:
        checks, status = None, "timed_out"
    elif outcome["exit_code"] != 0:
        checks, status = None, "ode_failed"
    else:
        try:
            if outcome["stdout_truncated"]:
                raise WorkerError("采样控制输出超过上限")
            values = _parse_samples(outcome["stdout_tail"], points)
            error_value = _reference_error(expression, points, values)
        except WorkerError as exc:
            checks = {"ok": False, "reason": str(exc)[:120], "finite": False, "max_abs_error": None}
            status = "ode_failed"
        else:
            checks = {
                "ok": True,
                "reason": "",
                "finite": True,
                "max_abs_error": error_value,
                "points": len(points),
            }
            status = "ok"
    _emit(
        {
            "schema": 1,
            "mode": "ode",
            "status": status,
            "exit_code": 124 if outcome["timed_out"] else 0,
            "timed_out": outcome["timed_out"],
            "checks": checks,
            "stdout_tail": outcome["stdout_tail"],
            "stderr_tail": outcome["stderr_tail"],
        }
    )
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    started = time.time()
    if len(argv) != 2 or argv[0] not in _MODES:
        _emit(
            {
                "schema": 1,
                "mode": "worker",
                "status": "worker_error",
                "error": "worker_invocation",
                "detail": "用法：chart_worker.py --chart|--ode|--ode-samples <spec json>",
            }
        )
        return 2
    mode, raw = argv
    workdir = os.getcwd()
    try:
        spec = _load_object(raw)
        if mode == "--chart":
            return _chart_mode(spec, workdir)
        if mode == "--ode":
            return _ode_mode(spec, workdir)
        return _ode_samples_mode(spec, workdir)
    except WorkerError as exc:
        _emit(
            {
                "schema": 1,
                "mode": mode.lstrip("-"),
                "status": "worker_error",
                "error": "worker_error",
                "detail": str(exc)[:200],
                "elapsed_s": round(time.time() - started, 3),
            }
        )
        return 3
    except BaseException as exc:  # noqa: BLE001 - 兜底：也要给出结构化失败
        _emit(
            {
                "schema": 1,
                "mode": mode.lstrip("-"),
                "status": "worker_error",
                "error": "worker_crashed",
                "detail": type(exc).__name__,
            }
        )
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

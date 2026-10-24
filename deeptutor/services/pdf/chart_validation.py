"""当前任务 PNG 与 ODE 数值产物验证（P1-34）。

存在文件不等于有效图。这个模块回答两个问题：

1. **``expected_png`` 是不是"本次 attempt 新产生的、有效的当前任务图"？**
   判定顺序刻意从"归属"到"字节"，每一步都不能靠 ``exists`` 或 mtime 蒙过去：

   * 必须有**服务端写的** attempt 记录（``cleared``/``finished`` 都为真），且它属于
     本次 run 与本次 basename —— 上一次成功留下的图、别的 run 的图都不算本次；
   * 路径必须限定在本 run 的 workdir 内（父目录/叶子都不许是符号链接）；
   * 必须是常规文件、非空、不超过 10MiB；
   * Pillow 必须认出它就是 PNG，像素数不超过 20 百万，``verify()`` 与真实
     ``load()`` 都要通过；**解码期间的任何警告/炸弹提示都按失败处理**；
   * 读取有界：先看头部尺寸再决定是否解码。

2. **声明了 ODE 时，模型脚本的 ``f`` 是否在给定 5 点上与声明表达式数值吻合？**
   这必须走 P33 的同一个 trusted worker / 受限执行器（``execute_ode_check``），
   绝不在宿主 import 或执行模型 ``_chart.py``。通过只说明"给定 5 点的数值检查
   通过"，**不代表**解析解正确、也不代表整篇数学已证明。

不编排整篇报告（P35 的事），只提供可复用的纯验证与一个 ODE 入口。
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import stat as stat_module
from typing import Any, Mapping
import warnings

from PIL import Image

from deeptutor.services.pdf import chart_executor, report_store
from deeptutor.services.pdf.chart_executor import (
    DEFAULT_POLICY,
    ReportExecutionPolicy,
    chart_failure_error,
    chart_target_name,
    chart_target_path,
    read_chart_attempt,
)
from deeptutor.services.pdf.report_inputs import validate_ode_expression
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    SubjectStorageError,
    subject_error,
)

#: 单图字节上限（C11：单图 10MiB）。
MAX_CHART_BYTES = 10 * 1024 * 1024
#: 单图像素上限（C11：20 百万像素）。
MAX_CHART_PIXELS = 20_000_000
#: ODE 数值检查的固定 5 点。
ODE_CHECK_POINTS: tuple[tuple[float, float], ...] = (
    (-2.5, 1.0),
    (0.0, 0.5),
    (1.7, -2.0),
    (2.2, 2.5),
    (-0.8, -3.0),
)
#: 通过阈值：最大绝对误差必须**严格小于** 1e-6。
ODE_MAX_ABS_ERROR = 1e-6

_HASH_CHUNK = 1 << 20


def _chart_failed(cause: BaseException | None = None) -> SubjectOperationError:
    """把产物/数值问题统一映射成 C02 ``chart_failed``（502/retryable）。"""
    return subject_error(ErrorCode.CHART_FAILED, cause=cause)


def _sha256_file(path: Path, *, limit: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            total += len(chunk)
            if total > limit:
                raise _chart_failed()
            digest.update(chunk)
    return total, digest.hexdigest()


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _attempt_is_current(
    record: Mapping[str, Any] | None, run: report_store.ReportRun, name: str
) -> bool:
    """attempt 记录必须是**本次成功**的 attempt。

    ``finished`` 只说明收尾了，不说明成功：非 0 退出、超时、worker 错误、缺产物都必须
    拒绝。记录还必须绑定本次 run/basename/代次与产物 size+sha256。
    """
    if not isinstance(record, Mapping):
        return False
    if record.get("cleared") is not True or record.get("finished") is not True:
        return False
    if record.get("succeeded") is not True:
        return False
    if record.get("basename") != name or record.get("run_id") != run.report_id:
        return False
    if record.get("staging_dir") != str(run.staging_dir):
        return False
    if _strict_int(record.get("generation")) is None:
        return False
    if record.get("status") != "ok":
        return False
    if record.get("exit_code") != 0 or record.get("timed_out") is not False:
        return False
    if record.get("error") not in ("", None):
        return False
    if not isinstance(record.get("attempt_id"), str) or not record["attempt_id"]:
        return False
    artifact = record.get("artifact")
    if not isinstance(artifact, Mapping):
        return False
    if artifact.get("name") != name:
        return False
    if _strict_int(artifact.get("size")) is None or artifact.get("size") <= 0:
        return False
    digest = artifact.get("sha256")
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest)
    )


def _decode_png_strict(path: Path, *, max_pixels: int) -> tuple[int, int, str]:
    """Pillow 严格解码：verify + 真实 load；任何警告/炸弹/格式不符都算失败。

    返回 ``(width, height, mode)``。读取有界：先看头部尺寸，超限直接拒绝，不做解码。
    警告处理是**局部**的（``catch_warnings`` + ``error``），不改变进程级过滤状态：
    解码期间的任何警告都说明这张图"有问题"，不能当作合法成功。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise _chart_failed()
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise _chart_failed()
                if width * height > max_pixels:
                    raise _chart_failed()
                # 多帧（APNG）不是报告图的形态，也避免按帧放大解码量。
                if getattr(image, "n_frames", 1) != 1:
                    raise _chart_failed()
                image.verify()
            with Image.open(path) as image:
                image.load()
                mode = str(image.mode)
        except SubjectOperationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 损坏/截断/非法结构/解码警告
            raise _chart_failed(exc) from exc
    return width, height, mode


def validate_chart_output(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """验证本次 attempt 的 ``expected_png``，返回 ``ReportFile`` 形状的字典。

    成功：``{"path": "chart_N.png", "size": int, "sha256": str, "role": "chart"}``。
    失败：抛 C02 固定错误（``chart_failed``；名字非法是 ``invalid_input``）。
    """
    report_store.require_report_run(run)
    name = chart_target_name(expected_png, policy=policy)
    max_bytes = min(policy.max_artifact_bytes, MAX_CHART_BYTES)
    max_pixels = min(policy.max_pixels, MAX_CHART_PIXELS)

    try:
        record = read_chart_attempt(run, name)
    except SubjectStorageError as exc:
        # 读不到/读坏了本次 attempt 证据：这张图无法归属本次，按图表失败处理
        # （cause 只留在服务端诊断里）。
        raise _chart_failed(exc) from exc
    if not _attempt_is_current(record, run, name):
        # 没有本次 attempt 的记录：旧图、别的 run 的图、被伪造/损坏的记录都不算本次。
        raise _chart_failed()

    try:
        target = chart_target_path(run, name, policy=policy)
    except SubjectStorageError as exc:  # 父目录/叶子是符号链接等
        raise _chart_failed(exc) from exc

    try:
        info = target.lstat()
    except OSError as exc:
        raise _chart_failed(exc) from exc
    if stat_module.S_ISLNK(info.st_mode) or not stat_module.S_ISREG(info.st_mode):
        raise _chart_failed()
    if info.st_size <= 0:
        raise _chart_failed()
    if info.st_size > max_bytes:
        raise _chart_failed()

    _decode_png_strict(target, max_pixels=max_pixels)

    try:
        size, digest = _sha256_file(target, limit=max_bytes)
    except OSError as exc:
        raise _chart_failed(exc) from exc
    if size != info.st_size or size <= 0:
        raise _chart_failed()
    # R6：执行成功之后被替换/改写过的 PNG 不是 worker 的产物。
    assert isinstance(record, Mapping)  # noqa: S101 - 上面已确认
    binding = record["artifact"]
    if size != binding.get("size") or digest != binding.get("sha256"):
        raise _chart_failed()
    return {
        "path": name,
        "size": size,
        "sha256": digest,
        "role": report_store.ROLE_CHART,
    }


async def check_ode_numeric(
    run: report_store.ReportRun,
    ode_rhs: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """在隔离环境里用固定 5 点检查 ``f`` 与声明表达式的数值一致性。

    返回 ``{"status": "passed", "max_abs_error": float, "points": int}``；缺 ``f``、
    数值不符、NaN/Inf、坏输出、超时都抛 ``chart_failed``。表达式本身先过 P31 的
    AST 白名单（非法表达式是 ``invalid_input``，不会进入执行器）。

    结论范围仅限"给定 5 点的数值检查通过"，不是解析解证明。
    """
    report_store.require_report_run(run)
    expression = validate_ode_expression(ode_rhs)
    if not expression:
        raise json_store.invalid_input("没有 ODE 表达式就没有数值检查")
    result = await chart_executor.execute_ode_check(
        run, expression, points=ODE_CHECK_POINTS, policy=policy
    )
    failure = chart_failure_error(result)
    if failure is not None:
        raise failure
    checks = result.checks
    if not isinstance(checks, Mapping) or checks.get("ok") is not True:
        raise _chart_failed()
    if checks.get("finite") is not True:
        raise _chart_failed()
    error_value = checks.get("max_abs_error")
    if isinstance(error_value, bool) or not isinstance(error_value, (int, float)):
        raise _chart_failed()
    error_value = float(error_value)
    # 最大绝对误差天然 ≥ 0：负值只可能来自不可信的伪造结果。
    if not math.isfinite(error_value) or error_value < 0 or error_value >= ODE_MAX_ABS_ERROR:
        raise _chart_failed()
    points = checks.get("points")
    if not isinstance(points, int) or isinstance(points, bool) or points != len(ODE_CHECK_POINTS):
        raise _chart_failed()
    return {
        "status": report_store.VERIFICATION_PASSED,
        "max_abs_error": error_value,
        "points": points,
    }


def verification_status(ode_rhs: object, *, passed: bool) -> str:
    """报告级 ``verification_status``：没有 ODE 就是 ``not_requested``。"""
    expression = validate_ode_expression(ode_rhs)
    if not expression:
        return report_store.VERIFICATION_NOT_REQUESTED
    return report_store.VERIFICATION_PASSED if passed else report_store.VERIFICATION_FAILED


__all__ = [
    "MAX_CHART_BYTES",
    "MAX_CHART_PIXELS",
    "ODE_CHECK_POINTS",
    "ODE_MAX_ABS_ERROR",
    "check_ode_numeric",
    "validate_chart_output",
    "verification_status",
]

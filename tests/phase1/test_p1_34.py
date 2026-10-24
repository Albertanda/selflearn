"""P1-34 行为测试：当前任务 PNG 与 ODE 数值产物验证。

目标：退出成功不等于有正确新图；旧图、别的 run 的图、软链接、空文件、超大/超像素
与解码有警告的图都不得通过。ODE 通过只称"给定 5 点的数值检查通过"。

必证场景（对应卡片清单与 START_S08 第二节 P1-34 的"证据"）：

* 有效当前 PNG 正例 → 空/损坏/别 run/链接/超 byte/超像素/解码警告反例；
* code 以 0 退出但没有图仍然失败；
* 两次 attempt 不复用旧图；
* ODE 五点合法 / 不符 / 非有限 / 超时，fake 落在 **executor 边界**、由真实
  validation 判定（不是"断言 helper 曾被调用"）。
"""

from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import time

from PIL import Image
import pytest

from deeptutor.services.pdf import chart_executor as ce
from deeptutor.services.pdf import chart_validation as cv
from deeptutor.services.pdf import report_store as rs
from deeptutor.subjects import json_store
from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, SubjectStorageError
from tests.phase1 import helpers

ODE_POINTS = cv.ODE_CHECK_POINTS


@pytest.fixture
def p1_subject(p1_runtime: Path):
    rs._reset_active_runs_for_tests()
    try:
        yield helpers.make_subject(p1_runtime, "报告科目")
    finally:
        rs._reset_active_runs_for_tests()


@pytest.fixture
def p1_run(p1_subject) -> rs.ReportRun:
    return rs.create_report_run(p1_subject.subject_id)


def _run(coro):
    return asyncio.run(coro)


class _HostBackend:
    """受控进程边界：真实 worker + 真实执行器，只把沙箱换成宿主进程。"""

    name = "controlled-host-boundary"

    def isolation_proof(self) -> ce.ReportIsolationProof:
        return ce.ReportIsolationProof(
            per_task_namespaces=True,
            per_task_mounts=True,
            network_disabled=True,
            env_cleared=True,
            process_group_cleanup=True,
        )

    async def health(self) -> tuple[bool, str]:
        return True, "controlled boundary"

    def build_spawn(self, request: ce.ChartSandboxRequest) -> ce.SpawnCommand:
        return ce.SpawnCommand(argv=tuple(request.argv), cwd=request.workdir, env=dict(request.env))


def _png_bytes(*, size: tuple[int, int] = (8, 8), mode: str = "RGB", color: object = None) -> bytes:
    buffer = BytesIO()
    fill = color if color is not None else (None if mode == "RGB" else 0)
    Image.new(mode, size, fill).save(buffer, format="PNG")
    return buffer.getvalue()


def _execute(p1_run: rs.ReportRun, code: str, name: str = "chart_1.png", **kwargs: object):
    return _run(
        ce.execute_chart_code(
            code,
            run=p1_run,
            expected_png=name,
            policy=ce.ReportExecutionPolicy(backend=_HostBackend(), **kwargs),  # type: ignore[arg-type]
        )
    )


def _test_worker_artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {"name": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _write_artifact(
    p1_run: rs.ReportRun, data: bytes, name: str = "chart_1.png", *, script: str | None = None
) -> None:
    """受控地产生"本次 attempt"的产物：记录走真实 begin/finish，字节由测试给出。

    这不是绕过验证：attempt 记录与文件归属仍由服务端流程写下，验证逻辑完全真实。
    """
    if script is not None:
        (p1_run.workdir / ce.CHART_SCRIPT_NAME).write_text(script, encoding="utf-8")
    attempt = ce.begin_chart_attempt(p1_run, name)
    (p1_run.workdir / name).write_bytes(data)
    ce.finish_chart_attempt(
        attempt,
        ce.ChartExecutionResult(
            exit_code=0,
            timed_out=False,
            error="",
            status="ok",
            artifact=_test_worker_artifact(p1_run.workdir / name),
        ),
    )


def _chart_code(*, expression: str | None = None) -> str:
    lines = ["def f(x, y):", f"    return {expression or 'x**2 - y'}", ""]
    lines.append("open('chart_1.png', 'wb').write(%r)" % _png_bytes())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 正例与基本属性
# ---------------------------------------------------------------------------
def test_valid_current_png_passes(p1_run: rs.ReportRun) -> None:
    result = _execute(p1_run, _chart_code())
    assert result.ok is True

    entry = cv.validate_chart_output(p1_run, "chart_1.png")

    target = p1_run.workdir / "chart_1.png"
    assert entry == {
        "path": "chart_1.png",
        "size": target.stat().st_size,
        "sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest(),
        "role": rs.ROLE_CHART,
    }
    # 返回的形状可以直接进 publish 清单（跨单元断言见文件末尾的发布用例）。
    assert set(entry) == {"path", "size", "sha256", "role"}


def test_validation_requires_the_attempt_record(p1_run: rs.ReportRun) -> None:
    """没有本次 attempt 记录（例如进程崩溃留下的旧图）不能当成本次产物。"""
    _write_artifact(p1_run, _png_bytes())
    assert cv.validate_chart_output(p1_run, "chart_1.png")["role"] == rs.ROLE_CHART

    record = ce.attempt_record_path(p1_run, "chart_1.png")
    payload = json.loads(record.read_text("utf-8"))
    for broken in (
        {**payload, "cleared": False},
        {**payload, "finished": False},
        {**payload, "run_id": "0" * 32},
        {**payload, "basename": "chart_2.png"},
        {**payload, "staging_dir": "/tmp/other-run"},
        {**payload, "attempt_id": ""},
    ):
        record.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(SubjectOperationError) as info:
            cv.validate_chart_output(p1_run, "chart_1.png")
        assert info.value.code is ErrorCode.CHART_FAILED
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert cv.validate_chart_output(p1_run, "chart_1.png")["size"] > 0


def test_another_runs_image_is_not_this_runs_output(p1_subject) -> None:
    first = rs.create_report_run(p1_subject.subject_id)
    second = rs.create_report_run(p1_subject.subject_id)
    _write_artifact(first, _png_bytes())

    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(second, "chart_1.png")

    assert info.value.code is ErrorCode.CHART_FAILED
    assert not (second.workdir / "chart_1.png").exists()
    # 复制别人的图到自己的目录也没用：没有本次 attempt 记录。
    shutil.copyfile(first.workdir / "chart_1.png", second.workdir / "chart_1.png")
    with pytest.raises(SubjectOperationError):
        cv.validate_chart_output(second, "chart_1.png")


def test_expected_png_name_and_run_type_are_validated(p1_run: rs.ReportRun) -> None:
    for bad in (
        "../chart_1.png",
        "/tmp/chart_1.png",
        "chart_9.png",
        "chart_0.png",
        "chart_x.png",
        3,
    ):
        with pytest.raises(json_store.InvalidInputError):
            cv.validate_chart_output(p1_run, bad)
    for bad_run in (Path("/tmp"), "run", None):
        with pytest.raises(json_store.InvalidInputError):
            cv.validate_chart_output(bad_run, "chart_1.png")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 反例：空/损坏/换格式/链接/超限/警告
# ---------------------------------------------------------------------------
def test_empty_and_truncated_and_wrong_format_images_fail(p1_run: rs.ReportRun) -> None:
    cases = {
        "empty": b"",
        "garbage": b"not a png at all",
        "truncated": _png_bytes()[:20],
        "wrong_format": _jpeg_bytes(),
    }
    for label, data in cases.items():
        run = rs.create_report_run(p1_run.subject_id)
        _write_artifact(run, data)
        with pytest.raises(SubjectOperationError) as info:
            cv.validate_chart_output(run, "chart_1.png")
        assert info.value.code is ErrorCode.CHART_FAILED, label
        assert str(info.value) == "图表生成失败。"


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (5, 6, 7)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_oversize_bytes_and_oversize_pixels_are_rejected(p1_run: rs.ReportRun) -> None:
    # 超字节：文件头是合法 PNG，但整体超过 10MiB。
    big = rs.create_report_run(p1_run.subject_id)
    huge = _png_bytes() + b"\x00" * (cv.MAX_CHART_BYTES + 1)
    _write_artifact(big, huge)
    assert (big.workdir / "chart_1.png").stat().st_size > cv.MAX_CHART_BYTES
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(big, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED

    # 超像素：24 百万像素（6000x4000），文件本身很小。
    wide = rs.create_report_run(p1_run.subject_id)
    buffer = BytesIO()
    Image.new("1", (6000, 4000)).save(buffer, format="PNG")
    payload = buffer.getvalue()
    assert len(payload) < cv.MAX_CHART_BYTES
    _write_artifact(wide, payload)
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(wide, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED

    # 20 百万像素以内仍然通过（边界之内不误伤）。
    ok_run = rs.create_report_run(p1_run.subject_id)
    buffer = BytesIO()
    Image.new("1", (5000, 4000)).save(buffer, format="PNG")
    _write_artifact(ok_run, buffer.getvalue())
    assert cv.validate_chart_output(ok_run, "chart_1.png")["size"] > 0


def test_decoder_warning_is_never_treated_as_success(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实 Pillow 解码告警（解压炸弹 warning）必须被拒绝。"""
    _write_artifact(p1_run, _png_bytes(size=(64, 64)))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 3000)  # 4096 像素 ∈ (1x, 2x) → warning

    with pytest.warns(Image.DecompressionBombWarning):
        with Image.open(p1_run.workdir / "chart_1.png") as probe:
            probe.load()

    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED

    # 炸弹 error（>2x 阈值）同样拒绝。
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)  # >2x → Pillow 直接报 error
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED


def test_symlinked_leaf_and_parent_are_rejected(p1_run: rs.ReportRun) -> None:
    _write_artifact(p1_run, _png_bytes())
    target = p1_run.workdir / "chart_1.png"
    elsewhere = p1_run.workdir / "real.png"
    target.rename(elsewhere)
    target.symlink_to(elsewhere)

    with pytest.raises((SubjectOperationError, SubjectStorageError)) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert isinstance(info.value, (SubjectOperationError, SubjectStorageError))
    if isinstance(info.value, SubjectOperationError):
        assert info.value.code is ErrorCode.CHART_FAILED

    # 父目录被换成链接：同样拒绝，且不跟随。
    target.unlink()
    real_workdir = p1_run.workdir
    backup = p1_run.staging_dir / "work-real"
    real_workdir.rename(backup)
    real_workdir.symlink_to(backup)
    try:
        with pytest.raises((SubjectOperationError, SubjectStorageError)):
            cv.validate_chart_output(p1_run, "chart_1.png")
    finally:
        real_workdir.unlink()
        backup.rename(real_workdir)


def test_exit_zero_without_an_image_still_fails(p1_run: rs.ReportRun) -> None:
    result = _execute(p1_run, "print('exit 0, no chart')\n")

    assert result.exit_code == 0
    assert result.artifact is None
    assert ce.chart_failure_error(result) is not None
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED


def test_second_attempt_does_not_reuse_the_previous_image(p1_run: rs.ReportRun) -> None:
    _write_artifact(p1_run, _png_bytes())
    first = cv.validate_chart_output(p1_run, "chart_1.png")

    second = _execute(p1_run, "print('this attempt produced nothing')\n")

    assert second.artifact is None
    assert not (p1_run.workdir / "chart_1.png").exists()
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED
    assert first["sha256"]
    time.sleep(0.01)


def test_validation_is_independent_of_mtime(p1_run: rs.ReportRun) -> None:
    """改 mtime 不能让"上一次的图"变成本次产物；删除记录也一样失败。"""
    _write_artifact(p1_run, _png_bytes())
    target = p1_run.workdir / "chart_1.png"
    os.utime(target, (time.time() - 86400, time.time() - 86400))

    assert cv.validate_chart_output(p1_run, "chart_1.png")["size"] > 0

    ce.attempt_record_path(p1_run, "chart_1.png").unlink()
    with pytest.raises(SubjectOperationError):
        cv.validate_chart_output(p1_run, "chart_1.png")


# ---------------------------------------------------------------------------
# ODE：走 P33 的执行器 + 真实 validation
# ---------------------------------------------------------------------------
def test_ode_five_points_pass_and_status_is_numeric_only(p1_run: rs.ReportRun) -> None:
    _execute(p1_run, _chart_code(expression="x**2 - y"))

    outcome = _run(cv.check_ode_numeric(p1_run, "x**2 - y"))

    assert outcome["status"] == rs.VERIFICATION_PASSED
    assert outcome["points"] == 5
    assert outcome["max_abs_error"] < cv.ODE_MAX_ABS_ERROR
    assert cv.verification_status("x**2 - y", passed=True) == rs.VERIFICATION_PASSED


def test_ode_mismatch_nonfinite_and_missing_f_fail(p1_run: rs.ReportRun) -> None:
    _execute(p1_run, _chart_code(expression="x**2 - y"))

    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "x**2 - y + 1"))
    assert info.value.code is ErrorCode.CHART_FAILED

    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "1e308 * x"))
    assert info.value.code is ErrorCode.CHART_FAILED

    # 没有 f 的脚本：缺 f 必须失败。
    _write_artifact(p1_run, _png_bytes(), script="print('no f in this script')\n")
    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "x**2 - y"))
    assert info.value.code is ErrorCode.CHART_FAILED


def test_ode_rejects_unusable_expression_before_the_executor(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    async def spy(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))
        raise AssertionError("不应该调用执行器")

    monkeypatch.setattr(ce, "execute_ode_check", spy)
    for bad in ("__import__('os')", "x.real", "", "   ", None, 7):
        with pytest.raises(json_store.InvalidInputError):
            _run(cv.check_ode_numeric(p1_run, bad))
    assert calls == []


def test_ode_timeout_fails_through_the_same_executor(p1_run: rs.ReportRun) -> None:
    # 作为脚本运行时很快结束；被 ODE 检查 import 时才挂住 → 只有执行器超时路径被触发。
    script = (
        "import time\n"
        "if __name__ != '__main__':\n"
        "    time.sleep(30)\n"
        f"open('chart_1.png', 'wb').write({_png_bytes()!r})\n"
    )
    assert _execute(p1_run, script).ok is True

    policy = ce.ReportExecutionPolicy(backend=_HostBackend(), ode_wall_clock_s=1)

    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "x**2 - y", policy=policy))
    assert info.value.code is ErrorCode.CHART_FAILED


def test_ode_validation_judges_a_faked_executor_result(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fake 只落在 executor 边界；判定逻辑必须是真实 validation。

    这里伪造执行器返回值，逐一验证 validation 自己会拒绝不完整/伪造结构，而不是
    "相信执行器说 ok"。
    """
    _execute(p1_run, _chart_code(expression="x**2 - y"))
    seen: list[object] = []
    replies: list[ce.ChartExecutionResult] = []

    async def fake_execute(run, expression, *, points, policy=ce.DEFAULT_POLICY):  # type: ignore[no-untyped-def]
        seen.append((run, expression, tuple(map(tuple, points))))
        return replies.pop(0)

    monkeypatch.setattr(cv.chart_executor, "execute_ode_check", fake_execute)

    replies.append(
        ce.ChartExecutionResult(
            exit_code=0,
            timed_out=False,
            error="",
            checks={"ok": True, "finite": True, "max_abs_error": 5e-7, "points": 5},
            mode="ode",
        )
    )
    outcome = _run(cv.check_ode_numeric(p1_run, "x**2 - y"))
    assert outcome == {"status": rs.VERIFICATION_PASSED, "max_abs_error": 5e-7, "points": 5}
    assert seen and seen[0][1] == "x**2 - y"
    assert seen[0][2] == tuple(ODE_POINTS)  # 固定 5 点由服务端给出

    forged = [
        ce.ChartExecutionResult(0, False, "", checks=None, mode="ode"),
        ce.ChartExecutionResult(0, False, "", checks={"ok": False}, mode="ode"),
        ce.ChartExecutionResult(0, False, "", checks={"ok": True, "finite": False}, mode="ode"),
        ce.ChartExecutionResult(0, False, "", checks={"ok": True, "finite": True}, mode="ode"),
        ce.ChartExecutionResult(
            0,
            False,
            "",
            checks={"ok": True, "finite": True, "max_abs_error": "0", "points": 5},
            mode="ode",
        ),
        ce.ChartExecutionResult(
            0,
            False,
            "",
            checks={"ok": True, "finite": True, "max_abs_error": float("nan"), "points": 5},
            mode="ode",
        ),
        ce.ChartExecutionResult(
            0,
            False,
            "",
            checks={"ok": True, "finite": True, "max_abs_error": 1.0, "points": 5},
            mode="ode",
        ),
        ce.ChartExecutionResult(
            0,
            False,
            "",
            checks={"ok": True, "finite": True, "max_abs_error": 0.0, "points": 4},
            mode="ode",
        ),
        ce.ChartExecutionResult(0, True, "", checks=None, mode="ode"),
        ce.ChartExecutionResult(3, False, "", checks=None, mode="ode"),
    ]
    for reply in forged:
        replies.append(reply)
        with pytest.raises(SubjectOperationError) as info:
            _run(cv.check_ode_numeric(p1_run, "x**2 - y"))
        assert info.value.code is ErrorCode.CHART_FAILED, reply


def test_chart_validation_judges_a_faked_executor_result(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """图表路径同理：伪造执行器"成功"，真实 validation 仍要按字节判定。"""
    real_execute = ce.execute_chart_code

    async def fake_execute(code, *, run, expected_png, policy=ce.DEFAULT_POLICY):  # type: ignore[no-untyped-def]
        # 落盘由 fake 完成（模拟 worker），但 attempt 记录仍走真实流程。
        attempt = ce.begin_chart_attempt(run, expected_png, policy=policy)
        (run.workdir / expected_png).write_bytes(_png_bytes())
        result = ce.ChartExecutionResult(
            exit_code=0,
            timed_out=False,
            error="",
            status="ok",
            mode="chart",
            artifact=_test_worker_artifact(run.workdir / expected_png),
        )
        ce.finish_chart_attempt(attempt, result)
        return result

    monkeypatch.setattr(cv.chart_executor, "execute_chart_code", fake_execute)
    assert _run(
        cv.chart_executor.execute_chart_code("code", run=p1_run, expected_png="chart_1.png")
    ).ok

    entry = cv.validate_chart_output(p1_run, "chart_1.png")
    assert entry["size"] == (p1_run.workdir / "chart_1.png").stat().st_size

    # 同一 fake 产出损坏字节 → 真实 validation 拒绝。
    async def fake_broken(code, *, run, expected_png, policy=ce.DEFAULT_POLICY):  # type: ignore[no-untyped-def]
        attempt = ce.begin_chart_attempt(run, expected_png, policy=policy)
        (run.workdir / expected_png).write_bytes(b"broken")
        result = ce.ChartExecutionResult(
            0,
            False,
            "",
            status="ok",
            mode="chart",
            artifact=_test_worker_artifact(run.workdir / expected_png),
        )
        ce.finish_chart_attempt(attempt, result)
        return result

    monkeypatch.setattr(cv.chart_executor, "execute_chart_code", fake_broken)
    _run(cv.chart_executor.execute_chart_code("code", run=p1_run, expected_png="chart_1.png"))
    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED
    assert callable(real_execute)


def test_verification_status_mapping() -> None:
    assert cv.verification_status("", passed=False) == rs.VERIFICATION_NOT_REQUESTED
    assert cv.verification_status("   ", passed=False) == rs.VERIFICATION_NOT_REQUESTED
    assert cv.verification_status("x - y", passed=True) == rs.VERIFICATION_PASSED
    assert cv.verification_status("x - y", passed=False) == rs.VERIFICATION_FAILED
    with pytest.raises(json_store.InvalidInputError):
        cv.verification_status("__import__('os')", passed=True)


def test_validated_entry_publishes_and_invalid_one_is_refused(p1_run: rs.ReportRun) -> None:
    """P34 的返回值就是 P32 发布清单的服务端来源。"""
    _write_artifact(p1_run, _png_bytes())
    (p1_run.workdir / "report.md").write_text("# 报告\n", encoding="utf-8")
    (p1_run.workdir / "report.pdf").write_bytes(b"%PDF-1.4\n")

    chart_entry = cv.validate_chart_output(p1_run, "chart_1.png")
    files = [
        _entry(p1_run.workdir / "report.md", rs.ROLE_MARKDOWN),
        _entry(p1_run.workdir / "report.pdf", rs.ROLE_PDF),
        chart_entry,
    ]
    manifest = rs.publish_report_run(
        p1_run, files=files, verification_status=rs.VERIFICATION_NOT_REQUESTED
    )
    assert manifest.status == rs.STATUS_COMPLETED
    assert [entry.role for entry in manifest.files] == ["markdown", "pdf", "chart"]
    assert (p1_run.public_dir / "chart_1.png").read_bytes() == (
        p1_run.workdir / "chart_1.png"
    ).read_bytes()

    # 第二次 attempt 没有图 → 无法验证 → 也不能发布（旧 completed 不受影响）。
    second = rs.create_report_run(p1_run.subject_id)
    (second.workdir / "report.md").write_text("# 报告\n", encoding="utf-8")
    (second.workdir / "report.pdf").write_bytes(b"%PDF-1.4\n")
    _execute(second, "print('no chart')\n")
    with pytest.raises(SubjectOperationError):
        cv.validate_chart_output(second, "chart_1.png")
    assert not second.public_dir.exists()


def _entry(path: Path, role: str) -> dict:
    import hashlib

    return {
        "path": path.name,
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "role": role,
    }


# ---------------------------------------------------------------------------
# R6：只有"完整成功"的 attempt 才能通过验证；产物 hash 必须与记录一致
# ---------------------------------------------------------------------------
FAILED_ATTEMPT_RESULTS = [
    pytest.param(
        ce.ChartExecutionResult(7, False, "", mode="chart", status="script_failed"), id="nonzero"
    ),
    pytest.param(
        ce.ChartExecutionResult(0, True, "", mode="chart", status="timed_out"), id="timeout"
    ),
    pytest.param(
        ce.ChartExecutionResult(0, False, "worker_failed", mode="chart", status=""), id="error"
    ),
    pytest.param(
        ce.ChartExecutionResult(0, False, "", mode="chart", status="no_artifact"), id="no-artifact"
    ),
]


@pytest.mark.parametrize("result", FAILED_ATTEMPT_RESULTS)
def test_finished_failed_attempt_cannot_validate_png(
    p1_run: rs.ReportRun, result: ce.ChartExecutionResult
) -> None:
    """``finished`` 不代表成功：非 0/超时/错误/无产物的 attempt 即便落了合法 PNG 也拒绝。"""
    attempt = ce.begin_chart_attempt(p1_run, "chart_1.png")
    (p1_run.workdir / "chart_1.png").write_bytes(_png_bytes())
    ce.finish_chart_attempt(attempt, result)

    record = ce.read_chart_attempt(p1_run, "chart_1.png")
    assert record["finished"] is True and record["succeeded"] is False

    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED


def test_post_execution_replacement_is_not_same_verified_artifact(p1_run: rs.ReportRun) -> None:
    """执行完成后把 PNG 换成另一张：记录里的 size/hash 对不上 → 拒绝。"""
    _write_artifact(p1_run, _png_bytes(color=(255, 0, 0)))
    assert cv.validate_chart_output(p1_run, "chart_1.png")["size"] > 0

    (p1_run.workdir / "chart_1.png").write_bytes(_png_bytes(color=(0, 0, 255)))

    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(p1_run, "chart_1.png")
    assert info.value.code is ErrorCode.CHART_FAILED


def test_record_without_artifact_binding_is_rejected(p1_run: rs.ReportRun) -> None:
    """记录缺 artifact/size/hash 绑定（伪造或旧格式）不能通过验证。"""
    _write_artifact(p1_run, _png_bytes())
    record_path = ce.attempt_record_path(p1_run, "chart_1.png")
    payload = json.loads(record_path.read_text("utf-8"))
    assert payload["artifact"]["sha256"]

    variants = [
        {**payload, "artifact": None},
        {**payload, "artifact": {**payload["artifact"], "sha256": "0" * 64}},
        {**payload, "artifact": {**payload["artifact"], "size": payload["artifact"]["size"] + 1}},
        {**payload, "succeeded": False},
        {**payload, "generation": None},
        {**payload, "status": "script_failed"},
    ]
    for variant in variants:
        record_path.write_text(json.dumps(variant), encoding="utf-8")
        with pytest.raises(SubjectOperationError):
            cv.validate_chart_output(p1_run, "chart_1.png")


def test_published_bytes_match_the_validated_manifest(p1_run: rs.ReportRun) -> None:
    """最终发布字节与验证清单逐项一致（替换尝试不会污染已发布内容）。"""
    _execute(p1_run, _chart_code())
    (p1_run.workdir / "report.md").write_text("# 报告\n", encoding="utf-8")
    (p1_run.workdir / "report.pdf").write_bytes(b"%PDF-1.4\n")
    chart_entry = cv.validate_chart_output(p1_run, "chart_1.png")

    files = [
        _entry(p1_run.workdir / "report.md", rs.ROLE_MARKDOWN),
        _entry(p1_run.workdir / "report.pdf", rs.ROLE_PDF),
        chart_entry,
    ]
    manifest = rs.publish_report_run(
        p1_run, files=files, verification_status=rs.VERIFICATION_NOT_REQUESTED
    )

    import hashlib

    for entry in manifest.files:
        payload = (p1_run.public_dir / entry.path).read_bytes()
        assert len(payload) == entry.size
        assert hashlib.sha256(payload).hexdigest() == entry.sha256
    assert manifest.file_for_role(rs.ROLE_CHART).sha256 == chart_entry["sha256"]


# ---------------------------------------------------------------------------
# R7：ODE 可信比较
# ---------------------------------------------------------------------------
def test_negative_numeric_error_is_not_a_valid_check(
    p1_run: rs.ReportRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """伪造的负最大误差（只可能来自模型自签）绝不能 passed。"""

    async def fake(*args, **kwargs):  # type: ignore[no-untyped-def]
        return ce.ChartExecutionResult(
            0,
            False,
            "",
            mode="ode",
            checks={"ok": True, "finite": True, "points": 5, "max_abs_error": -9},
        )

    monkeypatch.setattr(ce, "execute_ode_check", fake)
    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "x-y"))
    assert info.value.code is ErrorCode.CHART_FAILED


def test_ode_model_cannot_self_certify_success_via_stdout(p1_run: rs.ReportRun) -> None:
    """真实 bwrap：模型脚本往 fd 1 写伪造 checks 并自毁也不能 passed。"""
    path = p1_run.workdir / ce.CHART_SCRIPT_NAME
    path.write_text("def f(x,y): return x-y\n", encoding="utf-8")
    positive = _run(cv.check_ode_numeric(p1_run, "x-y"))
    assert positive["status"] == rs.VERIFICATION_PASSED

    payload = {"ok": True, "finite": True, "points": 5, "max_abs_error": 0.0}
    path.write_text(
        "import os\ndef f(x,y): return 123456\n"
        "if __name__ == '_chart_model':\n"
        "    os.write(1,%r)\n"
        "    os._exit(0)\n" % json.dumps(payload).encode()
    )
    with pytest.raises(SubjectOperationError) as info:
        _run(cv.check_ode_numeric(p1_run, "x-y"))
    assert info.value.code is ErrorCode.CHART_FAILED


def test_ode_samples_are_untrusted_and_recomputed(p1_run: rs.ReportRun) -> None:
    """模型只能提供采样值：伪造 ok/finite 字段或错误 f 都不能骗过可信父进程。"""
    wrong = "def f(x, y):\n    return 123456\n"
    (p1_run.workdir / ce.CHART_SCRIPT_NAME).write_text(wrong, encoding="utf-8")
    with pytest.raises(SubjectOperationError):
        _run(cv.check_ode_numeric(p1_run, "x - y"))

    right = "def f(x, y):\n    return x - y\n"
    (p1_run.workdir / ce.CHART_SCRIPT_NAME).write_text(right, encoding="utf-8")
    outcome = _run(cv.check_ode_numeric(p1_run, "x - y"))
    assert outcome["status"] == rs.VERIFICATION_PASSED
    assert outcome["points"] == len(cv.ODE_CHECK_POINTS)


# Coordinator acceptance: remaining boundary failures, 2026-10-17.


def test_attempt_success_requires_actual_worker_artifact(p1_run):
    run = p1_run
    a = ce.begin_chart_attempt(run, "chart_1.png")
    (run.workdir / "chart_1.png").write_bytes(_png_bytes())
    ce.finish_chart_attempt(a, ce.ChartExecutionResult(0, False, "", status="ok", artifact=None))
    with pytest.raises(SubjectOperationError):
        cv.validate_chart_output(run, "chart_1.png")


def test_model_sampling_garbage_prefix_cannot_be_trimmed_into_valid_control(p1_run):
    run = p1_run
    script = run.workdir / ce.CHART_SCRIPT_NAME
    script.write_text("def f(x,y): return x-y\n")
    assert asyncio.run(cv.check_ode_numeric(run, "x-y"))["status"] == "passed"
    samples = {"samples": [[x, y, x - y] for x, y in cv.ODE_CHECK_POINTS]}
    raw = b"INVALID_PREFIX" + b" " * 5000 + json.dumps(samples).encode()
    script.write_text(
        "import os\ndef f(x,y): return 1234\nif __name__=='_chart_model':\n    os.write(1,%r)\n    os._exit(0)\n"
        % raw
    )
    with pytest.raises(SubjectOperationError):
        asyncio.run(cv.check_ode_numeric(run, "x-y"))


def test_png_io_exception_has_stable_chart_error(p1_run, monkeypatch):
    run = p1_run
    _write_artifact(run, _png_bytes())

    def failure(*a, **k):
        raise OSError("PRIVATE_PATH_NOISE")

    monkeypatch.setattr(cv, "_sha256_file", failure)
    with pytest.raises(SubjectOperationError) as caught:
        cv.validate_chart_output(run, "chart_1.png")
    assert caught.value.code is ErrorCode.CHART_FAILED and "PRIVATE_PATH_NOISE" not in str(
        caught.value
    )

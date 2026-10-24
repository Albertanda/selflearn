"""P1-56 行为测试：subject 路由的统一错误出口（C02/C01）。

目标：**全部现有 subject 路由**的具名存储/领域/LLM 异常都通过 C02 固定安全出口返回；
全局路由与原生框架行为不变。

覆盖的必证场景：

* 损坏 registry → ``storage_corrupt``（不是"空科目列表"）；损坏/符号链接集合 →
  ``storage_corrupt`` / ``storage_io``，且原文件字节不变；
* profile 读与写的坏文件都是具名 500，原文件保留；
* 非法 slug → 400 ``invalid_subject_id``；合法但未注册 → 404 ``subject_not_found``，
  且两者都不回显输入；
* 真实预算耗尽 → 502 ``reasoning_budget_exhausted``（走真实 generation 路径，不是手造
  error dict）、非空截断 → 502 ``output_truncated``；
* 原生 422、401/403 及其 ``WWW-Authenticate`` headers 原样保留（不被业务包装吞掉），
  依赖里抛出的存储异常同样被覆盖；
* 32KiB 虚构输入与异常标记不出现在完整 JSON 响应里；未解析出当前用户时不回退管理员路径；
* 非 subject 的普通 router 不受影响（没有全局 handler）；
* P1-06 / P1-08 的业务失败响应满足 ErrorResponse schema。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.subject_route import SubjectRoute
from deeptutor.subjects import exam_points, json_store, store, wrong_book
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
)
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX

FAKE_MARKER = "p1-56-FAKE-MARKER-e3d91b-DO-NOT-LEAK"
HOST_PATH_MARKER = "/home/host-only/secret/path"


def _schema(name: str) -> dict:
    doc = json.loads((REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8"))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{name}",
        "$defs": doc["$defs"],
    }


def _assert_error_response(response, expected: ErrorCode, *, status: int | None = None) -> dict:
    from jsonschema import validate

    if status is not None:
        assert response.status_code == status
    assert response.status_code >= 400
    body = response.json()
    validate(instance=body, schema=_schema("ErrorResponse"))
    assert body["error"]["code"] == expected.value
    assert body["detail"] == body["error"]["message"]
    assert body["error"]["retryable"] is (expected in {
        ErrorCode.STORAGE_IO,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.PROVIDER_TIMEOUT,
        ErrorCode.EMPTY_MODEL_OUTPUT,
        ErrorCode.INVALID_MODEL_OUTPUT,
        ErrorCode.OUTPUT_TRUNCATED,
        ErrorCode.REASONING_BUDGET_EXHAUSTED,
    })
    return body


def _install_cfg(monkeypatch: pytest.MonkeyPatch):
    import deeptutor.services.llm.config as config_mod

    cfg = config_mod.LLMConfig(
        model="p1-56-fake-model",
        api_key="p1-56-fake-key",
        base_url="http://127.0.0.1:9/v1",
    )
    monkeypatch.setattr(config_mod, "_LLM_CONFIG_CACHE", cfg)
    return cfg


def _corrupt(path: Path, body: str = "[{ 坏 JSON") -> bytes:
    path.write_text(body, encoding="utf-8")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# 存储错误：具名 500，原文件保留
# ---------------------------------------------------------------------------
def test_a_corrupt_registry_is_storage_corrupt_not_an_empty_list(p1_subjects, p1_route_client):
    index = helpers.learning_root(p1_subjects["_admin_root"]) / "index.json"
    before = _corrupt(index)

    response = p1_route_client.get(ROUTE_PREFIX)

    body = _assert_error_response(response, ErrorCode.STORAGE_CORRUPT, status=500)
    assert "subjects" not in body
    assert index.read_bytes() == before


def test_a_corrupt_collection_is_a_named_500_with_the_file_intact(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]
    path = subject.root / "wrong_book.json"
    before = _corrupt(path, "not json at all")

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book")

    _assert_error_response(response, ErrorCode.STORAGE_CORRUPT, status=500)
    assert path.read_bytes() == before


def test_a_symlinked_collection_is_refused_as_storage_io(p1_subjects, p1_route_client, tmp_path):
    subject = p1_subjects["科目A"]
    target = tmp_path / "outside.json"
    target.write_text("[]", encoding="utf-8")
    path = subject.root / "exam_points.json"
    path.unlink(missing_ok=True)
    path.symlink_to(target)

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/exam-points")

    _assert_error_response(response, ErrorCode.STORAGE_IO, status=500)
    assert target.read_text(encoding="utf-8") == "[]"


def test_a_corrupt_profile_fails_on_both_get_and_update_and_keeps_the_file(
    p1_subjects, p1_route_client
):
    subject = p1_subjects["科目A"]
    path = subject.root / "profile.json"
    before = _corrupt(path, '{"facts": "不是数组"}')

    get_response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/profile")
    post_response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/profile", data={"goals": "新目标"}
    )

    _assert_error_response(get_response, ErrorCode.STORAGE_CORRUPT, status=500)
    _assert_error_response(post_response, ErrorCode.STORAGE_CORRUPT, status=500)
    assert path.read_bytes() == before


def test_an_injected_storage_io_error_is_retryable_storage_io(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目A"]
    calls: list[str] = []

    def failing_read_object(path, *, default):
        calls.append(Path(path).name)
        raise StorageIOError("注入的读取失败", path=Path(path).name)

    monkeypatch.setattr(json_store, "read_object", failing_read_object)

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/profile")

    body = _assert_error_response(response, ErrorCode.STORAGE_IO, status=500)
    assert body["error"]["retryable"] is True
    assert calls == ["profile.json"]


def test_a_storage_error_inside_a_dependency_is_also_projected(p1_runtime: Path):
    """依赖里抛出的存储异常同样走 C02（只包 endpoint 是不够的）。"""

    def exploding_dependency() -> None:
        raise StorageCorruptError("依赖里的坏文件", path="index.json")

    app = FastAPI()
    probe = APIRouter(route_class=SubjectRoute)

    @probe.get("/probe")
    async def probe_route(_: None = Depends(exploding_dependency)):
        return {"never": True}

    app.include_router(probe)
    with TestClient(app) as client:
        response = client.get("/probe")

    _assert_error_response(response, ErrorCode.STORAGE_CORRUPT, status=500)


# ---------------------------------------------------------------------------
# 非法 / 未知科目
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("subject_id", [" ", "%", "科目!", "a" * 65, "科目　"])
def test_an_invalid_subject_id_is_400_with_the_fixed_message(
    p1_subjects, p1_route_client, subject_id
):
    from deeptutor.subjects.errors import ERROR_SPECS

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject_id}/profile")

    body = _assert_error_response(response, ErrorCode.INVALID_SUBJECT_ID, status=400)
    # 固定常量消息：与输入无关，因此不可能回显输入。
    assert body["detail"] == ERROR_SPECS[ErrorCode.INVALID_SUBJECT_ID].message


def test_an_invalid_subject_id_does_not_echo_a_distinctive_marker(p1_subjects, p1_route_client):
    response = p1_route_client.get(f"{ROUTE_PREFIX}/{FAKE_MARKER}!/profile")

    body = _assert_error_response(response, ErrorCode.INVALID_SUBJECT_ID, status=400)
    assert FAKE_MARKER not in response.text
    assert FAKE_MARKER.lower() not in body["detail"]


def test_an_unknown_subject_is_404_subject_not_found(p1_subjects, p1_route_client):
    response = p1_route_client.get(f"{ROUTE_PREFIX}/不存在的科目/profile")

    body = _assert_error_response(response, ErrorCode.SUBJECT_NOT_FOUND, status=404)
    assert "不存在的科目" not in body["detail"]
    assert body["error"]["retryable"] is False


def test_an_unknown_subject_never_brings_a_tree_into_existence(p1_subjects, p1_route_client):
    subjects_root = helpers.learning_root(p1_subjects["_admin_root"])
    before = sorted(p.name for p in subjects_root.iterdir() if p.is_dir())

    response = p1_route_client.get(f"{ROUTE_PREFIX}/从未注册的科目/profile")

    assert response.status_code == 404
    assert sorted(p.name for p in subjects_root.iterdir() if p.is_dir()) == before


def test_an_unresolvable_current_user_does_not_fall_back_to_the_admin_root(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    """当前用户解析不出来时必须报错，而不是悄悄读管理员数据根。"""
    import deeptutor.multi_user.paths as paths_mod
    import deeptutor.services.path_service as path_service_mod

    monkeypatch.setattr(paths_mod, "get_current_path_service", lambda: None)

    def forbidden_fallback():  # pragma: no cover - 只有回退时才会被调用
        raise AssertionError("禁止回退到默认（管理员）PathService")

    monkeypatch.setattr(path_service_mod, "get_path_service", forbidden_fallback)

    response = p1_route_client.get(f"{ROUTE_PREFIX}/科目a/profile")

    _assert_error_response(response, ErrorCode.STORAGE_IO, status=500)


# ---------------------------------------------------------------------------
# LLM / 领域错误
# ---------------------------------------------------------------------------
def test_a_real_budget_exhaustion_is_502_reasoning_budget_exhausted(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目A"]
    _install_cfg(monkeypatch)
    p1_llm.response = ""
    p1_llm.finish_reason = "length"
    p1_llm.usage = {"completion_tokens": 16000, "prompt_tokens": 10, "total_tokens": 16010}

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "1+1=?", "student_answer": "2"},
    )

    _assert_error_response(response, ErrorCode.REASONING_BUDGET_EXHAUSTED, status=502)
    assert p1_llm.call_count == 1  # 真的走过生成路径


def test_a_non_empty_truncation_is_502_output_truncated(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目A"]
    _install_cfg(monkeypatch)
    p1_llm.response = '{"points": ['
    p1_llm.finish_reason = "max_tokens"
    p1_llm.usage = {"completion_tokens": 16000}

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/exam-points/detect",
        data={"transcript": "这个内容很重要，大家一定要重视起来。"},
    )

    _assert_error_response(response, ErrorCode.OUTPUT_TRUNCATED, status=502)


def test_a_missing_llm_configuration_is_provider_unavailable(p1_subjects, p1_route_client):
    """隔离根里没有配置模型：真实 ``get_llm_config()`` 的 LLMConfigError 走 502。"""
    subject = p1_subjects["科目A"]

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "1+1=?", "student_answer": "2"},
    )

    _assert_error_response(response, ErrorCode.PROVIDER_UNAVAILABLE, status=502)


def test_a_corrupt_exam_points_file_fails_the_detect_route_before_the_model(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目A"]
    path = subject.root / "exam_points.json"
    before = _corrupt(path, "[]]")
    _install_cfg(monkeypatch)
    # 检测本身必须成功，才会走到批量保存那一步（否则测的是模型错误）。
    p1_llm.response = json.dumps(
        {
            "points": [
                {
                    "content": "洛必达法则（整体重要性）",
                    "level": "emphasis",
                    "evidence": "这个内容很重要，大家一定要重视起来",
                    "kp": "洛必达法则",
                }
            ]
        },
        ensure_ascii=False,
    )

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/exam-points/detect",
        data={"transcript": "这个内容很重要，大家一定要重视起来。"},
    )

    _assert_error_response(response, ErrorCode.STORAGE_CORRUPT, status=500)
    assert p1_llm.call_count == 1
    assert path.read_bytes() == before  # 坏文件不会被空集合覆盖


def test_a_grading_failure_returns_a_schema_valid_error_and_writes_nothing(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目B"]
    (subject.root / "wrong_book.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = "这不是 JSON"

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "1+1=?", "student_answer": "2"},
    )

    _assert_error_response(response, ErrorCode.INVALID_MODEL_OUTPUT, status=502)
    assert not (subject.root / "wrong_book.json").exists()


def test_a_detection_failure_returns_a_schema_valid_error_and_writes_nothing(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目B"]
    (subject.root / "exam_points.json").unlink(missing_ok=True)
    _install_cfg(monkeypatch)
    p1_llm.response = '{"points": [{"content": "c", "level": "inferred", "evidence": "x", "kp": "k"}]}'

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/exam-points/detect",
        data={"transcript": "x 是原文。"},
    )

    _assert_error_response(response, ErrorCode.INVALID_MODEL_OUTPUT, status=502)
    assert not (subject.root / "exam_points.json").exists()


def test_an_internal_error_is_500_without_a_traceback(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目A"]

    def exploding(*args, **kwargs):
        raise RuntimeError(f"内部细节 {FAKE_MARKER} {HOST_PATH_MARKER}")

    from deeptutor.subjects import profile as profile_mod

    monkeypatch.setattr(profile_mod, "load", exploding)

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/profile")

    _assert_error_response(response, ErrorCode.INTERNAL_ERROR, status=500)
    assert "Traceback" not in response.text
    assert FAKE_MARKER not in response.text
    assert HOST_PATH_MARKER not in response.text


# ---------------------------------------------------------------------------
# 原生框架行为原样保留
# ---------------------------------------------------------------------------
def test_a_missing_required_form_field_keeps_the_native_422(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]

    response = p1_route_client.post(f"{ROUTE_PREFIX}/{subject.subject_id}/exam-points/detect", data={})

    assert response.status_code == 422
    body = response.json()
    assert "error" not in body
    assert isinstance(body["detail"], list)


def test_a_missing_token_is_401_with_the_original_header(p1_subjects, p1_route_client, monkeypatch):
    import deeptutor.api.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)

    response = p1_route_client.get(ROUTE_PREFIX)

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


def test_an_invalid_token_is_401_and_does_not_echo_it(p1_subjects, p1_route_client, monkeypatch):
    import deeptutor.api.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)

    response = p1_route_client.get(
        ROUTE_PREFIX, headers={"Authorization": f"Bearer {FAKE_MARKER}"}
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert FAKE_MARKER not in response.text


def test_a_403_raised_by_a_dependency_passes_through_untouched(p1_runtime: Path):
    def forbidden() -> None:
        raise HTTPException(status_code=403, detail="forbidden by policy", headers={"X-Probe": "1"})

    app = FastAPI()
    probe = APIRouter(route_class=SubjectRoute)

    @probe.get("/probe")
    async def probe_route(_: None = Depends(forbidden)):
        return {"never": True}

    app.include_router(probe)
    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 403
    assert response.headers.get("X-Probe") == "1"
    assert response.json() == {"detail": "forbidden by policy"}


def test_a_historical_http_exception_keeps_its_framework_shape(p1_subjects, p1_route_client):
    """科目路由里既有的普通 400（空白题目）不被改写成 error 形状。"""
    subject = p1_subjects["科目A"]

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "   ", "student_answer": "2"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "question and student_answer are required"}


# ---------------------------------------------------------------------------
# 错误保密 / 作用域
# ---------------------------------------------------------------------------
def test_a_32kib_fictional_input_never_comes_back(
    p1_subjects, p1_route_client, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch
):
    subject = p1_subjects["科目A"]
    _install_cfg(monkeypatch)
    marker = f"{FAKE_MARKER}-" + "x" * (32 * 1024)
    p1_llm.response = "坏输出"

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "1+1=?", "student_answer": marker},
    )

    _assert_error_response(response, ErrorCode.INVALID_MODEL_OUTPUT, status=502)
    assert FAKE_MARKER not in response.text
    assert HOST_PATH_MARKER not in response.text


def test_a_provider_message_never_comes_back(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    from deeptutor.services.llm.exceptions import LLMProviderTransportError

    subject = p1_subjects["科目A"]
    _install_cfg(monkeypatch)

    class _RaisingLLM(helpers.FakeLLMClient):
        async def complete_response(self, prompt: str = "", **kwargs):
            self._record(prompt=prompt, **kwargs)
            raise LLMProviderTransportError(f"{FAKE_MARKER} at {HOST_PATH_MARKER}")

    helpers.install_provider_stubs(monkeypatch, llm=_RaisingLLM(""))

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/wrong-book/check",
        data={"question": "1+1=?", "student_answer": "2"},
    )

    _assert_error_response(response, ErrorCode.PROVIDER_UNAVAILABLE, status=502)
    assert FAKE_MARKER not in response.text
    assert HOST_PATH_MARKER not in response.text


# ---------------------------------------------------------------------------
# 作用范围：只影响 subject router
# ---------------------------------------------------------------------------
def test_every_subject_route_uses_the_subject_route_class():
    from deeptutor.api.routers import subjects as subjects_router

    assert subjects_router.router.routes
    assert all(isinstance(route, SubjectRoute) for route in subjects_router.router.routes)


def test_other_routers_keep_the_plain_route_class(p1_runtime: Path):
    from deeptutor.api.routers import knowledge, sessions

    other_routes = list(knowledge.router.routes) + list(sessions.router.routes)
    assert other_routes
    assert not any(isinstance(route, SubjectRoute) for route in other_routes)


def test_no_global_exception_handler_was_registered(p1_runtime: Path):
    """普通 router 抛出的存储异常不被包装 —— 证明没有注册全局 handler。"""
    app = FastAPI()
    plain = APIRouter()

    @plain.get("/plain")
    async def plain_route():
        raise StorageIOError("普通路由的存储失败", path="x.json")

    app.include_router(plain)
    with TestClient(app) as client:
        with pytest.raises(StorageIOError):
            client.get("/plain")


def test_the_error_boundary_does_not_change_a_successful_response(p1_subjects, p1_route_client):
    subject = p1_subjects["科目A"]

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/profile")

    assert response.status_code == 200
    assert set(response.json()) == {"subject_id", "profile"}
    assert response.json()["subject_id"] == subject.subject_id


def test_a_route_body_that_still_uses_http_exceptions_is_not_rewritten(p1_subjects, p1_route_client):
    """历史 HTTPException（KB 不存在）保持旧框架行为，不被猜成业务码。"""
    subject = p1_subjects["科目A"]

    response = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/没有这个库/status"
    )

    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


def test_the_wrong_book_and_exam_points_domain_helpers_are_used_by_the_routes():
    """接线检查：路由确实调用 P1-06 / P1-08 的组合提交函数（不是旧逐条路径）。"""
    import inspect

    from deeptutor.api.routers import subjects as subjects_router

    check_source = inspect.getsource(subjects_router.check_answer)
    detect_source = inspect.getsource(subjects_router.detect_exam_points)
    assert "submit_graded_attempt" in check_source
    assert "upsert_detected" in detect_source
    # 旧路径已经不再被路由调用
    assert "add_point(" not in detect_source
    assert wrong_book.submit_graded_attempt.__module__ == "deeptutor.subjects.wrong_book"
    assert exam_points.upsert_detected.__module__ == "deeptutor.subjects.exam_points"


# ---------------------------------------------------------------------------
# R4（rework01）：明确业务 cause 的 HTTPException 也走 C02，且服务端保留诊断
# ---------------------------------------------------------------------------
def _wrapped_app(cause: BaseException | None, *, status: int = 502):
    """只含一条 SubjectRoute 的 app：endpoint 抛带（或不带）cause 的 HTTPException。"""
    app = FastAPI()
    probe = APIRouter(route_class=SubjectRoute)

    @probe.get("/probe")
    async def probe_route():
        if cause is None:
            raise HTTPException(
                status_code=status, detail=FAKE_MARKER, headers={"X-Probe": "preserved"}
            )
        raise HTTPException(
            status_code=status, detail=FAKE_MARKER, headers={"X-Probe": "preserved"}
        ) from cause

    app.include_router(probe)
    return app


def _cause_cases() -> list[BaseException]:
    from deeptutor.services.llm.exceptions import (
        LLMEmptyResponseError,
        LLMProviderTransportError,
        LLMTimeoutError,
    )
    from deeptutor.subjects.model_output import ModelOutputError

    return [
        ModelOutputError("probe_reason"),
        LLMEmptyResponseError(FAKE_MARKER),
        LLMProviderTransportError(FAKE_MARKER),
        LLMTimeoutError(FAKE_MARKER),
        StorageIOError(FAKE_MARKER, path="x.json"),
        StorageCorruptError(FAKE_MARKER, path="x.json"),
    ]


@pytest.mark.parametrize("cause", _cause_cases(), ids=lambda c: type(c).__name__)
def test_r4_a_wrapped_business_cause_is_projected_with_its_mapped_status(
    p1_runtime: Path, cause: BaseException
):
    from deeptutor.subjects.errors import map_subject_exception

    expected = map_subject_exception(cause)

    with TestClient(_wrapped_app(cause)) as client:
        response = client.get("/probe")

    assert response.status_code == expected.http_status
    body = response.json()
    assert body["error"]["code"] == expected.code.value
    assert body["detail"] == expected.message
    assert FAKE_MARKER not in response.text
    assert HOST_PATH_MARKER not in response.text


def test_r4_a_wrapped_timeout_is_504_not_the_outer_status(p1_runtime: Path):
    from deeptutor.services.llm.exceptions import LLMTimeoutError

    with TestClient(_wrapped_app(LLMTimeoutError(FAKE_MARKER), status=502)) as client:
        response = client.get("/probe")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"
    assert response.json()["error"]["retryable"] is True


def test_r4_a_wrapped_storage_error_is_500_not_the_outer_status(p1_runtime: Path):
    with TestClient(_wrapped_app(StorageIOError(FAKE_MARKER, path="x.json"), status=502)) as client:
        response = client.get("/probe")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "storage_io"


@pytest.mark.parametrize("status", [401, 403, 422])
def test_r4_auth_and_native_statuses_win_over_a_business_cause(p1_runtime: Path, status: int):
    from deeptutor.services.llm.exceptions import LLMEmptyResponseError

    with TestClient(
        _wrapped_app(LLMEmptyResponseError("private"), status=status)
    ) as client:
        response = client.get("/probe")

    assert response.status_code == status
    assert response.json() == {"detail": FAKE_MARKER}
    assert response.headers.get("X-Probe") == "preserved"


@pytest.mark.parametrize(
    "cause", [ValueError(FAKE_MARKER), RuntimeError(FAKE_MARKER), KeyError(FAKE_MARKER)]
)
def test_r4_an_unknown_cause_is_not_guessed_into_a_business_code(
    p1_runtime: Path, cause: BaseException
):
    """普通 ValueError/RuntimeError 不是 provider 依据：仍是框架行为。"""
    with TestClient(_wrapped_app(cause)) as client:
        response = client.get("/probe")

    assert response.status_code == 502
    assert response.json() == {"detail": FAKE_MARKER}
    assert response.headers.get("X-Probe") == "preserved"


def test_r4_an_http_exception_without_a_cause_keeps_its_framework_shape(p1_runtime: Path):
    with TestClient(_wrapped_app(None, status=409)) as client:
        response = client.get("/probe")

    assert response.status_code == 409
    assert response.json() == {"detail": FAKE_MARKER}
    assert response.headers.get("X-Probe") == "preserved"


def test_r4_the_real_review_pack_route_does_not_leak_the_wrapped_llm_detail(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    """真实 review-pack endpoint：LLMEmptyResponseError 被包成 HTTPException from exc。"""
    from jsonschema import validate

    from deeptutor.services.llm.exceptions import LLMEmptyResponseError

    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise LLMEmptyResponseError(f"{FAKE_MARKER} {HOST_PATH_MARKER}")

    monkeypatch.setattr(
        "deeptutor.services.pdf.review_guide.generate_guide_markdown", failing
    )

    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/review-pack", data={"format": "pdf"}
    )

    assert response.status_code == 502
    body = response.json()
    validate(instance=body, schema=_schema("ErrorResponse"))
    assert body["error"]["code"] == "empty_model_output"
    assert FAKE_MARKER not in response.text
    assert HOST_PATH_MARKER not in response.text


def test_r4_a_business_cause_inside_a_dependency_is_also_projected(p1_runtime: Path):
    from deeptutor.services.llm.exceptions import LLMEmptyResponseError

    def failing_dependency() -> None:
        raise HTTPException(status_code=502, detail=FAKE_MARKER) from LLMEmptyResponseError(
            FAKE_MARKER
        )

    app = FastAPI()
    probe = APIRouter(route_class=SubjectRoute)

    @probe.get("/probe")
    async def probe_route(_: None = Depends(failing_dependency)):
        return {"never": True}

    app.include_router(probe)
    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "empty_model_output"
    assert FAKE_MARKER not in response.text


def test_r4_typed_errors_keep_their_original_cause_server_side(p1_runtime: Path):
    """裸具名错误：日志里必须有真实异常对象/trace，而响应只有固定安全信息。"""
    from deeptutor.subjects.model_output import ModelOutputError

    app = FastAPI()
    probe = APIRouter(route_class=SubjectRoute)
    cause = RuntimeError(FAKE_MARKER)
    error = ModelOutputError("review_diagnostic_reason", cause=cause)

    @probe.get("/probe")
    async def probe_route():
        raise error from cause

    app.include_router(probe)
    import logging as _logging

    logger = _logging.getLogger("deeptutor.api.subject_route")
    records: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=_logging.WARNING)
    logger.addHandler(handler)
    try:
        with TestClient(app) as client:
            response = client.get("/probe")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert FAKE_MARKER not in response.text
    retained = [
        record
        for record in records
        if (record.exc_info and record.exc_info[1] in (error, cause))
        or any(value is error or value is cause for value in vars(record).values())
    ]
    assert retained, "只有类名被记录，真实 cause/诊断被丢弃"
    # 日志文本里带有受控诊断（reason/类型），不是仅类名
    assert any("review_diagnostic_reason" in record.getMessage() for record in records)


def test_r4_a_wrapped_llm_cause_is_visible_in_the_server_log(p1_runtime: Path):
    import logging as _logging

    from deeptutor.services.llm.exceptions import LLMProviderTransportError

    cause = LLMProviderTransportError(FAKE_MARKER)
    logger = _logging.getLogger("deeptutor.api.subject_route")
    records: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=_logging.WARNING)
    logger.addHandler(handler)
    try:
        with TestClient(_wrapped_app(cause)) as client:
            response = client.get("/probe")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 502
    assert FAKE_MARKER not in response.text
    assert any(
        record.exc_info and record.exc_info[1] is cause for record in records
    ), "包装的 cause 没有作为真实异常记录到服务端日志"

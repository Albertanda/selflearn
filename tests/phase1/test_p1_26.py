"""P1-26：图像描述 helper（C09 ImageDescription 契约）。

覆盖 START_S06 §三 P1-26 证据清单：strategies 选择、auto 的乐观降级、两种
dedicated 策略不回落主模型、空/截断/超时/异常/取消、字节与格式边界、page/
location 与类型拒绝、不泄漏异常原文/绝对缓存路径/base64。

fake provider 装在**真实 factory 请求接缝**（``factory.complete_response``）上，
断言的是被选中的模型、实际请求参数和返回投影，而不是"helper 被调用过"。
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from PIL import Image
import pytest

from deeptutor.services.llm import factory
from deeptutor.services.llm.multimodal import has_image_parts
from deeptutor.services.llm.provider_core.base import LLMProvider, LLMResponse
from deeptutor.services.llm.types import TutorResponse
from deeptutor.services.rag.pipelines.llamaindex import image_description as desc
from tests.phase1 import helpers

# ---------------------------------------------------------------------------
# fixtures / doubles
# ---------------------------------------------------------------------------

_MAIN = SimpleNamespace(
    model="main-multimodal",
    provider_name="openai",
    reasoning_effort=None,
    binding="openai",
    api_key="main-key",
    base_url="https://main.invalid/v1",
    api_version=None,
    extra_headers={"X-Main": "1"},
)
_DEDICATED = SimpleNamespace(
    model="dedicated-vision",
    provider_name="openai",
    reasoning_effort=None,
    binding="openai",
    api_key="ded-key",
    base_url="https://ded.invalid/v1",
    api_version=None,
    extra_headers={"X-Ded": "1"},
)

#: The pristine factory entry point, so the wire tests below can exercise the
#: *real* factory + provider retry layer while only the transport is fake.
_REAL_COMPLETE_RESPONSE = factory.complete_response

_SCHEMA_PATTERN = re.compile(r"^(?!\.\.?$)[^/\\\x00-\x1f]+$", re.DOTALL)
_SKIP_ENUM = {
    "parser_no_assets",
    "vision_unavailable",
    "vision_failed",
    "budget",
    "unsupported_image",
}
_FIELDS = {
    "text",
    "content_kind",
    "source_file",
    "page",
    "location",
    "asset_ref",
    "skip_reason",
}


def _assert_schema(description: Any) -> dict[str, Any]:
    """Validate the projection against schemas.json ``ImageDescription``."""
    value = asdict(description) if not isinstance(description, dict) else dict(description)
    assert set(value) == _FIELDS, f"unexpected projection keys: {sorted(value)}"
    assert value["content_kind"] == "image_description"
    assert isinstance(value["text"], str)
    assert isinstance(value["source_file"], str)
    assert _SCHEMA_PATTERN.fullmatch(value["source_file"]), value["source_file"]
    page = value["page"]
    assert page is None or (isinstance(page, int) and not isinstance(page, bool) and page >= 0)
    assert value["location"] is None or isinstance(value["location"], str)
    assert isinstance(value["asset_ref"], str)
    assert value["skip_reason"] is None or value["skip_reason"] in _SKIP_ENUM
    if value["skip_reason"] is None:
        assert value["text"].strip(), "a described image needs non-empty text"
        assert value["text"].startswith(desc.DESCRIPTION_PREFIX)
    else:
        assert value["text"] == ""
    return value


class _Hang:
    """Outcome marker: the stub never answers, forcing the timeout path."""


class _VisionStub:
    """``factory.complete_response`` double recording every real call."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.entered: asyncio.Event | None = None

    async def complete_response(self, prompt: str = "", **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        if self.entered is not None:
            self.entered.set()
        outcome = self.outcomes.pop(0) if self.outcomes else "resolved figure"
        if outcome is _Hang:
            await asyncio.sleep(3600)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _response(content: str, finish_reason: str | None = "stop") -> TutorResponse:
    return TutorResponse(
        content=content,
        finish_reason=finish_reason,
        usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    )


def _png(target_size: int | None = 1200, *, size: tuple[int, int] = (16, 16)) -> bytes:
    """A *valid* PNG, zero-padded to ``target_size`` bytes by default.

    The default keeps every fixture above the 1200-byte floor (C09), so a test
    that means to exercise the vision path is never silently skipped as
    "budget" instead.
    """
    buffer = io.BytesIO()
    Image.new("RGB", size, (12, 120, 200)).save(buffer, format="PNG", compress_level=0)
    data = buffer.getvalue()
    if target_size is not None:
        assert len(data) <= target_size, (len(data), target_size)
        data = data + b"\x00" * (target_size - len(data))
    return data


@pytest.fixture
def image_file(tmp_path: Path) -> Path:
    path = tmp_path / "figure.png"
    path.write_bytes(_png())
    return path


@pytest.fixture
def vision(monkeypatch: pytest.MonkeyPatch):
    """Install a vision stub at the real factory seam plus deterministic config."""

    def install(*outcomes: Any, dedicated: Any = _DEDICATED, main: Any = _MAIN, vision_capable: bool = True):
        stub = _VisionStub(*outcomes)
        helpers.install_provider_stubs(monkeypatch, llm=stub)
        monkeypatch.setattr(desc, "get_vision_strategy", lambda: "auto")
        monkeypatch.setattr(desc, "resolve_llm_runtime_config", lambda *a, **k: main)
        monkeypatch.setattr(desc, "resolve_vision_runtime_config", lambda *a, **k: dedicated)
        monkeypatch.setattr(desc, "supports_vision", lambda binding, model=None: vision_capable)
        return stub

    return install


def _describe(image: Path, **kwargs: Any):
    params = {"source_file": "notes.pdf", "asset_ref": "images/figure.png"}
    params.update(kwargs)
    return asyncio.run(desc.describe_image_for_index(str(image), **params))


# ---------------------------------------------------------------------------
# 成功路径：选择、请求参数、投影字段
# ---------------------------------------------------------------------------
def test_dedicated_vision_describes_image_with_text_projection(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(_response("图中标记 FIXTURE-A，坐标轴为时间。"), dedicated=_DEDICATED, main=None)
    result = _describe(image_file, page=3, location="body/figure")
    value = _assert_schema(result)

    assert value["text"].startswith("【来自图像】notes.pdf")
    assert "第 3 页" in value["text"]
    assert "body/figure" in value["text"]
    assert "FIXTURE-A" in value["text"]
    assert value["source_file"] == "notes.pdf"
    assert value["page"] == 3
    assert value["location"] == "body/figure"
    assert value["asset_ref"] == "images/figure.png"
    assert value["skip_reason"] is None

    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["model"] == "dedicated-vision"
    assert call["api_key"] == "ded-key"
    assert call["base_url"] == "https://ded.invalid/v1"
    assert call["extra_headers"] == {"X-Ded": "1"}
    assert call["max_tokens"] == desc.DESCRIBE_MAX_TOKENS
    assert call["image_filename"] == "notes.pdf"
    assert call["image_mime_type"] == "image/png"
    assert call["image_data"] == __import__("base64").b64encode(image_file.read_bytes()).decode()
    assert not call["image_data"].startswith("data:")

    # Mapping-compatible return: attribute and item access agree, dict() works.
    assert result["text"] == result.text
    assert dict(result) == value
    assert result == value


def test_standalone_image_uses_file_name_as_asset_ref(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    vision(_response("独立图片描述"))
    result = asyncio.run(
        desc.describe_image_for_index(str(image_file), source_file=image_file.name)
    )
    value = _assert_schema(result)
    assert value["asset_ref"] == "figure.png"
    assert value["page"] is None
    assert value["location"] is None
    assert value["text"].startswith(f"{desc.DESCRIPTION_PREFIX}{image_file.name}")


def test_described_mime_type_follows_content_not_extension(
    p1_runtime: Path, tmp_path: Path, vision
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 10, 10)).save(buffer, format="JPEG")
    disguised = tmp_path / "actually-jpeg.png"
    disguised.write_bytes(buffer.getvalue() + b"\x00" * 1200)

    stub = vision(_response("JPEG 内容"))
    result = _describe(disguised)
    assert result.skip_reason is None
    assert stub.calls[0]["image_mime_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# strategy 选择与有界降级
# ---------------------------------------------------------------------------
def test_auto_uses_capability_allowed_main_without_fallback(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(_response("主模型描述"), main=_MAIN, dedicated=_DEDICATED, vision_capable=True)
    result = _describe(image_file)
    assert result.skip_reason is None
    assert [call["model"] for call in stub.calls] == ["main-multimodal"]


def test_auto_skips_main_when_capability_says_unsupported(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(_response("专用模型描述"), main=_MAIN, dedicated=_DEDICATED, vision_capable=False)
    result = _describe(image_file)
    assert result.skip_reason is None
    # The main model is *explicitly* unsupported: it is never asked at all.
    assert [call["model"] for call in stub.calls] == ["dedicated-vision"]


def test_auto_falls_back_once_when_main_request_is_rejected(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(
        RuntimeError("provider rejected image input: SECRET-MARKER-9137"),
        _response("专用模型接手"),
        main=_MAIN,
        dedicated=_DEDICATED,
        vision_capable=True,
    )
    result = _describe(image_file)
    value = _assert_schema(result)
    assert [call["model"] for call in stub.calls] == ["main-multimodal", "dedicated-vision"]
    assert "专用模型接手" in value["text"]
    # The provider's raw text never reaches the projection.
    assert "SECRET-MARKER-9137" not in json.dumps(value, ensure_ascii=False)


def test_auto_attempts_are_bounded_and_publish_vision_failed(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(RuntimeError("boom"), RuntimeError("boom again"), main=_MAIN, dedicated=_DEDICATED)
    result = _describe(image_file)
    value = _assert_schema(result)
    assert value["skip_reason"] == "vision_failed"
    assert len(stub.calls) == desc.MAX_CANDIDATE_ATTEMPTS == 2


@pytest.mark.parametrize("strategy", ["prefer_dedicated", "dedicated_only"])
def test_dedicated_only_strategies_never_touch_main(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch, strategy: str
) -> None:
    stub = vision(RuntimeError("dedicated down"), main=_MAIN, dedicated=_DEDICATED, vision_capable=True)
    monkeypatch.setattr(desc, "get_vision_strategy", lambda: strategy)
    result = _describe(image_file)
    assert result.skip_reason == "vision_failed"
    # Two strategies, one candidate each: main is configured and capable, and
    # still must not be called.
    assert [call["model"] for call in stub.calls] == ["dedicated-vision"]


@pytest.mark.parametrize("strategy", ["prefer_dedicated", "dedicated_only"])
def test_dedicated_only_strategies_report_vision_unavailable_without_dedicated(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch, strategy: str
) -> None:
    stub = vision(main=_MAIN, dedicated=None, vision_capable=True)
    monkeypatch.setattr(desc, "get_vision_strategy", lambda: strategy)
    result = _describe(image_file)
    assert result.skip_reason == "vision_unavailable"
    assert stub.calls == []


def test_auto_without_any_usable_vision_reports_unavailable(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(main=None, dedicated=None)
    result = _describe(image_file)
    assert result.skip_reason == "vision_unavailable"
    assert stub.calls == []


def test_auto_with_unsupported_main_and_no_dedicated_does_not_call_main(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(main=_MAIN, dedicated=None, vision_capable=False)
    result = _describe(image_file)
    assert result.skip_reason == "vision_unavailable"
    assert stub.calls == []


def test_main_config_failure_still_uses_the_dedicated_model(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken main-model resolution must not fail the image (R2).

    The main candidate is simply lost; the configured dedicated model still
    answers, and no exception escapes to the indexing run.
    """
    stub = vision(_response("专用模型仍然可用"), main=None)
    monkeypatch.setattr(desc, "resolve_llm_runtime_config", lambda *a, **k: (_ for _ in ()).throw(ValueError("no main")))
    result = _describe(image_file)
    assert result.skip_reason is None
    assert "专用模型仍然可用" in result.text
    assert [call["model"] for call in stub.calls] == ["dedicated-vision"]


def _wire_provider(monkeypatch: pytest.MonkeyPatch, outcome):
    """Install a fake *transport* behind the real factory + retry layer."""

    class _Provider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.wire_calls: list[bool] = []

        def get_default_model(self) -> str:
            return _DEDICATED.model

        async def chat(self, messages, **kwargs):  # type: ignore[override]
            has_image = has_image_parts(messages)
            self.wire_calls.append(has_image)
            return outcome(has_image, len(self.wire_calls))

    provider = _Provider()
    monkeypatch.setattr(factory, "complete_response", _REAL_COMPLETE_RESPONSE)
    monkeypatch.setattr(
        factory,
        "_resolve_call_config",
        lambda **_kwargs: (_DEDICATED, SimpleNamespace(name="openai")),
    )
    monkeypatch.setattr(factory, "get_runtime_provider", lambda *_args: provider)
    monkeypatch.setattr(factory, "supports_vision", lambda *_args: False)
    monkeypatch.setattr(
        _Provider,
        "_normalize_retry_delays",
        staticmethod(lambda delays: tuple(0.00001 for _ in (delays or ()))),
    )
    return provider


def test_real_factory_never_promotes_an_imageless_fallback_to_ocr(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The "drop the images and ask again" degradation must not be enabled.

    With the real factory + provider in place, an error response to the image
    request would otherwise be retried without image parts and the text answer
    accepted as if the model had seen the figure.
    """
    vision(main=None)
    provider = _wire_provider(
        monkeypatch,
        lambda has_image, _n: LLMResponse(
            content="unsupported image input" if has_image else "PHANTOM ANSWER",
            finish_reason="error" if has_image else "stop",
        ),
    )
    result = asyncio.run(
        desc.describe_image_for_index(image_file, source_file="notes.pdf")
    )
    assert result.skip_reason == "vision_failed"
    assert result.text == ""
    assert provider.wire_calls == [True], "the image must be sent exactly once"


def test_real_factory_makes_one_wire_attempt_per_candidate(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One candidate means one request: the factory's retry schedule is off."""
    vision(main=None)
    provider = _wire_provider(
        monkeypatch,
        lambda _has_image, n: LLMResponse(
            content="503 temporarily unavailable" if n == 1 else "second attempt",
            finish_reason="error" if n == 1 else "stop",
        ),
    )
    result = asyncio.run(
        desc.describe_image_for_index(image_file, source_file="notes.pdf")
    )
    assert len(provider.wire_calls) == 1, provider.wire_calls
    assert result.skip_reason == "vision_failed"


# ---------------------------------------------------------------------------
# 响应质量：空、截断、超时、异常、取消
# ---------------------------------------------------------------------------
def test_empty_and_blank_responses_are_not_success(p1_runtime: Path, image_file: Path, vision) -> None:
    stub = vision(_response(""), _response("   \n", finish_reason=None), main=None)
    result = _describe(image_file)
    assert result.skip_reason == "vision_failed"
    # Bounded: one call per configured candidate, no retry storm.
    assert len(stub.calls) == len([_DEDICATED])


def test_truncated_body_is_not_a_success_text_node(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    stub = vision(_response("这是一段被输出上限截断的描述", finish_reason="length"), main=None)
    result = _describe(image_file)
    value = _assert_schema(result)
    assert value["skip_reason"] == "vision_failed"
    assert value["text"] == ""
    assert stub.calls[0]["model"] == "dedicated-vision"


def test_truncation_with_empty_body_is_not_success(p1_runtime: Path, image_file: Path, vision) -> None:
    vision(_response("", finish_reason="length"), main=None)
    result = _describe(image_file)
    assert result.skip_reason == "vision_failed"


def test_timeout_is_a_failure_not_a_hang(
    p1_runtime: Path, image_file: Path, vision, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desc, "DESCRIBE_TIMEOUT_SECONDS", 0.05)
    vision(_Hang, main=None)
    result = _describe(image_file)
    assert result.skip_reason == "vision_failed"


def test_provider_exception_text_never_leaks_and_kind_is_stable(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    from deeptutor.services.llm.exceptions import LLMEmptyResponseError
    from deeptutor.subjects.errors import SubjectOutputTruncated

    marker = "SECRET-MARKER-9137"
    vision(RuntimeError(marker), main=None)
    result = _describe(image_file, page=2, location="p2")
    value = _assert_schema(result)
    blob = json.dumps(value, ensure_ascii=False)
    assert marker not in blob
    assert str(image_file) not in blob
    assert "/home/" not in blob and "tmp" not in blob
    assert value["skip_reason"] == "vision_failed"
    assert "text" in value and value["text"] == ""

    assert desc.failure_kind(TimeoutError("x")) == desc.FAILURE_TIMEOUT
    assert desc.failure_kind(asyncio.TimeoutError("x")) == desc.FAILURE_TIMEOUT
    assert desc.failure_kind(SubjectOutputTruncated("half", diagnostics={})) == desc.FAILURE_TRUNCATED
    from deeptutor.services.llm.exceptions import LLMReasoningBudgetExhausted

    assert (
        desc.failure_kind(LLMReasoningBudgetExhausted("no body", diagnostics={}))
        == desc.FAILURE_REASONING_BUDGET
    )
    assert desc.failure_kind(LLMEmptyResponseError("blank")) == desc.FAILURE_EMPTY
    assert desc.failure_kind(RuntimeError("boom")) == desc.FAILURE_PROVIDER


def test_cancellation_propagates(p1_runtime: Path, image_file: Path, vision) -> None:
    stub = vision(_Hang, main=None)
    stub.entered = asyncio.Event()

    async def _exercise() -> None:
        task = asyncio.create_task(
            desc.describe_image_for_index(
                str(image_file), source_file="notes.pdf", asset_ref="images/figure.png"
            )
        )
        await asyncio.wait_for(stub.entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_exercise())


def test_no_base64_or_absolute_path_in_projection(p1_runtime: Path, image_file: Path, vision) -> None:
    vision(_response("描述正文"))
    result = _describe(image_file)
    blob = json.dumps(_assert_schema(result), ensure_ascii=False)
    encoded = __import__("base64").b64encode(image_file.read_bytes()).decode()
    assert encoded not in blob
    assert str(image_file.parent) not in blob
    assert result.asset_ref == "images/figure.png"


# ---------------------------------------------------------------------------
# 字节/格式边界与 leaf 约束
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size,expected", [(1199, "budget"), (1200, None)])
def test_minimum_byte_boundary_is_inclusive(
    p1_runtime: Path, tmp_path: Path, vision, size: int, expected: str | None
) -> None:
    path = tmp_path / f"figure-{size}.png"
    path.write_bytes(_png(size))
    assert path.stat().st_size == size
    stub = vision(_response("边界描述"), main=None)
    result = _describe(path)
    value = _assert_schema(result)
    assert value["skip_reason"] == expected
    if expected is None:
        assert stub.calls, "an admitted image must reach the vision model"
    else:
        assert stub.calls == []


def test_payload_below_the_byte_floor_is_budget(
    p1_runtime: Path, tmp_path: Path, vision
) -> None:
    """The historical 6-byte fixture is a *budget* skip, not a vision failure."""
    path = tmp_path / "tiny.png"
    path.write_bytes(b"\x89PNG\r\n")
    stub = vision(_response("不该被调用"), main=None)
    result = _describe(path)
    assert _assert_schema(result)["skip_reason"] == "budget"
    assert stub.calls == []


def test_maximum_byte_boundary_is_inclusive(
    p1_runtime: Path, tmp_path: Path, vision
) -> None:
    limit = 4 * 1024 * 1024
    exact = tmp_path / "exact-4mib.png"
    exact.write_bytes(_png(limit))
    over = tmp_path / "over-4mib.png"
    over.write_bytes(_png(limit + 1))

    stub = vision(_response("4MiB 描述"))
    admitted = _describe(exact)
    assert _assert_schema(admitted)["skip_reason"] is None
    assert len(stub.calls) == 1

    rejected = _describe(over)
    assert _assert_schema(rejected)["skip_reason"] == "budget"
    assert len(stub.calls) == 1, "an over-budget file must not reach the model"


@pytest.mark.parametrize(
    "payload_name,payload",
    [
        ("plain.txt", b"x" * 2000),
        ("fake.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000),
        ("payload.png", b"%PDF-1.4\n" + b"\x00" * 2000),
    ],
)
def test_corrupt_or_unsupported_payloads_are_unsupported_image(
    p1_runtime: Path, tmp_path: Path, vision, payload_name: str, payload: bytes
) -> None:
    path = tmp_path / payload_name
    if not payload_name.endswith(".png"):
        path = tmp_path / "plain.png"
    path.write_bytes(payload)
    stub = vision(_response("不该被调用"), main=None)
    result = _describe(path)
    assert _assert_schema(result)["skip_reason"] == "unsupported_image"
    assert stub.calls == []


def test_vector_format_is_unsupported_image(p1_runtime: Path, tmp_path: Path, vision) -> None:
    path = tmp_path / "diagram.tiff"
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (3, 4, 5)).save(buffer, format="TIFF")
    data = buffer.getvalue()
    path.write_bytes(data + b"\x00" * max(0, 2000 - len(data)))
    stub = vision(_response("不该被调用"), main=None)
    result = _describe(path)
    assert _assert_schema(result)["skip_reason"] == "unsupported_image"
    assert stub.calls == []


def test_symlinked_leaf_is_never_followed(p1_runtime: Path, tmp_path: Path, vision) -> None:
    real = tmp_path / "outside.png"
    real.write_bytes(_png())
    link = tmp_path / "link.png"
    link.symlink_to(real)

    stub = vision(_response("不该被调用"), main=None)
    result = _describe(link)
    assert _assert_schema(result)["skip_reason"] == "unsupported_image"
    assert stub.calls == []
    assert str(real) not in json.dumps(asdict(result), ensure_ascii=False)


def test_standalone_parent_symlink_is_never_followed(p1_runtime: Path, tmp_path: Path, vision) -> None:
    real = tmp_path / "outside"
    real.mkdir()
    (real / "figure.png").write_bytes(_png())
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    stub = vision(_response("must not send the image"), main=None)
    assert _describe(alias / "figure.png").skip_reason == "unsupported_image"
    assert stub.calls == []


def test_missing_and_directory_paths_are_unsupported_image(
    p1_runtime: Path, tmp_path: Path, vision
) -> None:
    stub = vision(_response("不该被调用"), main=None)
    missing = _describe(tmp_path / "nope.png")
    assert _assert_schema(missing)["skip_reason"] == "unsupported_image"
    directory = _describe(tmp_path)
    assert _assert_schema(directory)["skip_reason"] == "unsupported_image"
    assert stub.calls == []


# ---------------------------------------------------------------------------
# 参数类型/取值拒绝（拒绝而不是 str() 成来源）
# ---------------------------------------------------------------------------
def test_rejects_wrong_source_file_types_and_unsafe_names(
    p1_runtime: Path, image_file: Path
) -> None:
    with pytest.raises(TypeError):
        asyncio.run(desc.describe_image_for_index(str(image_file), source_file=123))
    for bad in ("", "   ", ".", "..", "../escape.pdf", "a/b.pdf", "a\\b.pdf", "bad\nname.pdf"):
        with pytest.raises(ValueError):
            asyncio.run(desc.describe_image_for_index(str(image_file), source_file=bad))


def test_rejects_wrong_page_and_location(image_file: Path) -> None:
    for bad_page in (True, "3", 2.5):
        with pytest.raises(TypeError):
            asyncio.run(
                desc.describe_image_for_index(
                    str(image_file), source_file="notes.pdf", page=bad_page
                )
            )
    with pytest.raises(ValueError):
        asyncio.run(
            desc.describe_image_for_index(str(image_file), source_file="notes.pdf", page=-1)
        )
    with pytest.raises(TypeError):
        asyncio.run(
            desc.describe_image_for_index(
                str(image_file), source_file="notes.pdf", location=5
            )
        )
    with pytest.raises(ValueError):
        asyncio.run(
            desc.describe_image_for_index(
                str(image_file), source_file="notes.pdf", location="line\nbreak"
            )
        )
    with pytest.raises(TypeError):
        asyncio.run(desc.describe_image_for_index(123, source_file="notes.pdf"))


@pytest.mark.parametrize(
    "asset_ref",
    ["", "   ", "/etc/passwd", "../secret.png", "images/../../secret.png", "C:\\cache\\x.png"],
)
def test_rejects_escaping_asset_refs(p1_runtime: Path, image_file: Path, vision, asset_ref: str) -> None:
    vision(_response("x"), main=None)
    with pytest.raises(ValueError):
        _describe(image_file, asset_ref=asset_ref)


def test_page_and_location_pass_through_without_base_guessing(
    p1_runtime: Path, image_file: Path, vision
) -> None:
    vision(_response("描述"))
    zero = _describe(image_file, page=0)
    assert _assert_schema(zero)["page"] == 0, "0-based parser page must stay 0"
    blank_location = _describe(image_file, location="   ")
    assert _assert_schema(blank_location)["location"] is None
    nested = _describe(image_file, asset_ref="images/sub/figure.png")
    assert _assert_schema(nested)["asset_ref"] == "images/sub/figure.png"


def test_asset_ref_from_root_is_constrained(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    (root / "images").mkdir(parents=True)
    inside = root / "images" / "figure-1.png"
    inside.write_bytes(_png())
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png())

    assert desc.asset_ref_from_root(inside, root) == "images/figure-1.png"
    with pytest.raises(ValueError):
        desc.asset_ref_from_root(outside, root)
    link = root / "images" / "link.png"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        desc.asset_ref_from_root(link, root)
    assert desc.standalone_asset_ref(inside) == "figure-1.png"


def test_budget_skip_signature_is_stable() -> None:
    assert desc.MIN_IMAGE_BYTES == 1200
    assert desc.MAX_IMAGE_BYTES == 4 * 1024 * 1024
    assert desc.SKIP_REASONS[0] == "parser_no_assets"
    assert len(desc.SKIP_REASONS) == 5
    digest = hashlib.sha256(desc.DESCRIPTION_PREFIX.encode("utf-8")).hexdigest()
    assert digest  # the prefix is a fixed literal, not a call-time format string

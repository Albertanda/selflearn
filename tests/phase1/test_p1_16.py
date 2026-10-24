"""P1-16 行为测试：安全音频保存与 ASR 流式发送（C07/C02）。

目标：恶意文件名/软链接不越界、限额分块、失败不留半批、转写不伪造成功，
ASR 以受控文件流 + 正确 MIME 发送且不把供应商原文回显给客户端。

必证场景（对应卡内清单）：

* 绝对路径 / ``..`` / 反斜杠 / 控制字符 / 不可 UTF-8 编码的名字被拒绝，且外部没有新增文件；
* 合法 ``.wav`` / ``.m4a`` / ``.flac`` 正常保存并得到转写文本；
* 恰好限额通过、限额 +1 失败（monkeypatch 小限额，不写真实大文件）；
* 读取中断 / ASR 失败 → 没有假转写成功、没有残留、旧同名文件字节不变；
* ASR multipart 传的是打开的文件流而不是整块 bytes，MIME 与扩展名对应；
* 供应商错误正文与虚构标记不出现在任何 HTTP 响应里；
* 普通文档允许集合没有被音频路径扩大。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deeptutor.services.asr import transcribe as transcribe_module
from deeptutor.subjects import json_store, material_manifest, uploads
from deeptutor.utils.document_validator import DocumentValidator
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX

FAKE_MARKER = "p1-16-FAKE-PROVIDER-MARKER-4f21c9-DO-NOT-LEAK"


def _schema(name: str) -> dict:
    doc = json.loads(
        (REPO_ROOT / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8")
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{name}",
        "$defs": doc["$defs"],
    }


def _validate(name: str, payload: dict) -> None:
    from jsonschema import validate

    validate(instance=payload, schema=_schema(name))


def _upload(client, subject_id: str, specs, *, type: str = "auto"):
    files = [
        ("files", (name, content, mime or "application/octet-stream"))
        for name, content, mime in specs
    ]
    return client.post(
        f"{ROUTE_PREFIX}/{subject_id}/knowledge/upload",
        files=files,
        data={"type": type},
    )


def _audio(name: str, size: int = 64) -> tuple[str, bytes, str]:
    return (name, b"RIFF" + bytes(size), uploads.AUDIO_MIME[Path(name).suffix.lower()])


def _tree(root: Path) -> dict:
    return helpers.tree_digest(root)


def _tree_without_locks(root: Path) -> dict:
    """目录摘要，忽略 KB 事务锁（``.deeptutor.lock`` 不是资料残留）。"""
    return {
        key: value
        for key, value in helpers.tree_digest(root).items()
        if not key.endswith(json_store.LOCK_FILE_NAME)
    }


def _material_dir(subject, kb_type: str = "lecture") -> Path:
    return Path(subject.materials) / kb_type


def _staging_slots(subject) -> list[Path]:
    root = Path(subject.root) / uploads.STAGING_DIR_NAME
    if not root.is_dir():
        return []
    return [entry for entry in root.iterdir() if entry.is_dir()]


# ---------------------------------------------------------------------------
# 合法路径：保存 + 转写
# ---------------------------------------------------------------------------
def test_legal_audio_formats_are_published_with_transcripts(
    p1_subjects, p1_route_client, p1_providers
):
    subject = p1_subjects["科目A"]
    response = _upload(
        p1_route_client,
        subject.subject_id,
        [_audio("lecture.wav"), _audio("lecture.m4a"), _audio("lecture.flac")],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    _validate("UploadTranscribe", payload)

    assert payload["operation"] == "transcribe"
    assert payload["type"] == "lecture"
    assert payload["files"] == ["lecture.wav", "lecture.m4a", "lecture.flac"]
    assert [item["file"] for item in payload["transcripts"]] == [
        "lecture.wav",
        "lecture.m4a",
        "lecture.flac",
    ]
    assert all(item["text"] == "stub-transcript" for item in payload["transcripts"])
    # 转写操作不宣传索引：没有 KB、没有 task_id
    assert "task_id" not in payload and "kb_name" not in payload

    materials = _material_dir(subject)
    for name in ("lecture.wav", "lecture.m4a", "lecture.flac"):
        assert (materials / name).is_file()
        transcript = materials / f"{name}.transcript.txt"
        assert transcript.read_text(encoding="utf-8") == "stub-transcript"
    # 转写不建立索引源
    assert not (subject.knowledge_bases / "lecture-kb").exists()
    assert _staging_slots(subject) == []
    # p1_providers 的替身确实被真实调用点使用
    assert len(p1_providers["stt"].calls) == 3


def test_empty_transcript_text_is_still_a_success(
    p1_subjects, p1_route_client, monkeypatch
):
    class _Empty:
        async def transcribe(self, audio_path, *, language="zh"):
            return {"text": "", "model": "stub-empty", "base_url": "https://x.invalid"}

    empty = _Empty()
    helpers.install_stub(
        monkeypatch, "deeptutor.services.asr.transcribe", "transcribe", empty.transcribe
    )
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("silent.wav")])
    assert response.status_code == 200, response.text
    payload = response.json()
    _validate("UploadTranscribe", payload)
    assert payload["transcripts"][0]["text"] == ""
    transcript = _material_dir(subject) / "silent.wav.transcript.txt"
    assert transcript.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# 恶意名字：拒绝且不越界
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_name",
    [
        "/etc/passwd.wav",
        "../../escape.wav",
        "..\\..\\escape.wav",
        "sub/dir/escape.wav",
        "..",
        ".",
    ],
)
def test_path_like_original_names_are_refused(
    p1_subjects, p1_route_client, p1_providers, bad_name, tmp_path
):
    subject = p1_subjects["科目A"]
    before_subject = _tree(subject.root)
    outside = tmp_path / "outside"
    outside.mkdir()
    probe = outside / "escape.wav"
    probe.write_bytes(b"untouched")

    response = _upload(p1_route_client, subject.subject_id, [(bad_name, b"RIFF", "audio/wav")])
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "invalid_input"
    assert bad_name not in response.text
    assert _tree(subject.root) == before_subject
    assert probe.read_bytes() == b"untouched"
    assert sorted(p.name for p in outside.iterdir()) == ["escape.wav"]


def test_control_characters_and_unencodable_names_are_refused():
    for bad in ("bad\x00name.wav", "bad\x07name.wav", "line\nbreak.wav", "\ud800.wav"):
        with pytest.raises(json_store.InvalidInputError) as excinfo:
            uploads.assert_safe_original_name(bad)
        assert excinfo.value.http_status == 400
    # 合法名字原样通过（不做静默改名）
    assert uploads.assert_safe_original_name("正常 录音.wav") == "正常 录音.wav"


def test_absolute_and_traversal_names_never_reach_the_filesystem(
    p1_subjects, p1_route_client, p1_providers
):
    subject = p1_subjects["科目A"]
    for bad in ("/tmp/abs.wav", "../sibling.wav", "a\\b.wav"):
        with pytest.raises(Exception):
            uploads.assert_safe_original_name(bad)
    assert not (Path(subject.root).parent / "sibling.wav").exists()


def test_symlinked_material_leaf_is_refused(p1_subjects, p1_route_client, p1_providers, tmp_path):
    subject = p1_subjects["科目A"]
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside-original")
    materials = _material_dir(subject)
    materials.mkdir(parents=True, exist_ok=True)
    link = materials / "linked.wav"
    link.symlink_to(outside)

    response = _upload(p1_route_client, subject.subject_id, [_audio("linked.wav")])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] in ("storage_io", "storage_corrupt")
    assert outside.read_bytes() == b"outside-original"
    assert link.is_symlink()


def test_symlinked_material_directory_is_refused(
    p1_subjects, p1_route_client, p1_providers, tmp_path
):
    subject = p1_subjects["科目A"]
    outside_dir = tmp_path / "elsewhere"
    outside_dir.mkdir()
    materials_root = Path(subject.materials)
    materials_root.mkdir(parents=True, exist_ok=True)
    import shutil

    existing = materials_root / "lecture"
    if existing.is_symlink() or existing.is_file():
        existing.unlink()
    elif existing.is_dir():
        shutil.rmtree(existing)
    (materials_root / "lecture").symlink_to(outside_dir)

    response = _upload(p1_route_client, subject.subject_id, [_audio("x.wav")])
    assert response.status_code == 500, response.text
    assert sorted(p.name for p in outside_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# 限额：恰好通过 / +1 失败
# ---------------------------------------------------------------------------
def test_exact_limit_passes_and_limit_plus_one_fails(
    p1_subjects, p1_route_client, p1_providers, monkeypatch
):
    monkeypatch.setattr(DocumentValidator, "MAX_FILE_SIZE", 1024)
    assert uploads.max_file_size() == 1024
    subject = p1_subjects["科目A"]

    ok = _upload(p1_route_client, subject.subject_id, [("exact.wav", b"a" * 1024, "audio/wav")])
    assert ok.status_code == 200, ok.text
    assert (_material_dir(subject) / "exact.wav").stat().st_size == 1024

    before = _tree(subject.root)
    too_big = _upload(
        p1_route_client, subject.subject_id, [("over.wav", b"a" * 1025, "audio/wav")]
    )
    assert too_big.status_code == 400, too_big.text
    assert too_big.json()["error"]["code"] == "invalid_input"
    assert not (_material_dir(subject) / "over.wav").exists()
    assert _staging_slots(subject) == []
    after = _tree(subject.root)
    assert set(after) - set(before) == set()


def test_oversized_batch_leaves_no_partial_file(
    p1_subjects, p1_route_client, p1_providers, monkeypatch
):
    monkeypatch.setattr(DocumentValidator, "MAX_FILE_SIZE", 512)
    subject = p1_subjects["科目A"]
    response = _upload(
        p1_route_client,
        subject.subject_id,
        [("small.wav", b"a" * 100, "audio/wav"), ("big.wav", b"a" * 900, "audio/wav")],
    )
    assert response.status_code == 400, response.text
    materials = _material_dir(subject)
    assert not (materials / "small.wav").exists()
    assert not (materials / "big.wav").exists()
    assert _staging_slots(subject) == []


# ---------------------------------------------------------------------------
# 失败：不发布、不残留、旧字节不变
# ---------------------------------------------------------------------------
def test_asr_failure_publishes_nothing_and_keeps_old_bytes(
    p1_subjects, p1_route_client, p1_providers
):
    subject = p1_subjects["科目A"]
    materials = _material_dir(subject)
    materials.mkdir(parents=True, exist_ok=True)
    old = materials / "lecture.wav"
    old.write_bytes(b"old-audio-bytes")
    old_transcript = materials / "lecture.wav.transcript.txt"
    old_transcript.write_text("old transcript", encoding="utf-8")

    p1_providers["stt"].error = FAKE_MARKER
    before = _tree(subject.root)
    response = _upload(
        p1_route_client,
        subject.subject_id,
        [_audio("lecture.wav", 32), _audio("second.wav", 32)],
    )
    assert response.status_code == 502, response.text
    payload = response.json()
    assert payload["error"]["code"] == "provider_unavailable"
    assert payload["detail"] == "模型服务暂时不可用，请稍后重试。"
    assert FAKE_MARKER not in response.text
    assert response.headers.get("content-type", "").startswith("application/json")

    assert old.read_bytes() == b"old-audio-bytes"
    assert old_transcript.read_text(encoding="utf-8") == "old transcript"
    assert not (materials / "second.wav").exists()
    assert not (materials / "second.wav.transcript.txt").exists()
    assert _staging_slots(subject) == []
    assert _tree(subject.root) == before


def test_asr_timeout_maps_to_provider_timeout(
    p1_subjects, p1_route_client, monkeypatch
):
    class _Timeout:
        async def transcribe(self, audio_path, *, language="zh"):
            return {
                "text": "",
                "model": "stub-stt",
                "base_url": "https://stub.invalid",
                "error": f"timeout {FAKE_MARKER}",
                "error_kind": "timeout",
            }

    stub = _Timeout()
    helpers.install_stub(
        monkeypatch, "deeptutor.services.asr.transcribe", "transcribe", stub.transcribe
    )
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("slow.wav")])
    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "provider_timeout"
    assert FAKE_MARKER not in response.text
    assert not (_material_dir(subject) / "slow.wav").exists()


def test_second_file_failure_keeps_the_whole_batch_unpublished(
    p1_subjects, p1_route_client, monkeypatch
):
    class _FailOnSecond:
        def __init__(self) -> None:
            self.calls = 0

        async def transcribe(self, audio_path, *, language="zh"):
            self.calls += 1
            if self.calls == 2:
                return {
                    "text": "",
                    "model": "stub-stt",
                    "base_url": "https://stub.invalid",
                    "error": "second failed",
                    "error_kind": "provider",
                }
            return {"text": "first ok", "model": "stub-stt", "base_url": "https://stub.invalid"}

    stub = _FailOnSecond()
    helpers.install_stub(
        monkeypatch, "deeptutor.services.asr.transcribe", "transcribe", stub.transcribe
    )
    subject = p1_subjects["科目A"]
    materials = _material_dir(subject)
    materials.mkdir(parents=True, exist_ok=True)
    (materials / "two.wav").write_bytes(b"old-two")

    response = _upload(
        p1_route_client, subject.subject_id, [_audio("one.wav"), _audio("two.wav")]
    )
    assert response.status_code == 502, response.text
    assert not (materials / "one.wav").exists()
    assert not (materials / "one.wav.transcript.txt").exists()
    assert (materials / "two.wav").read_bytes() == b"old-two"
    assert not (materials / "two.wav.transcript.txt").exists()
    assert stub.calls == 2


def test_unreadable_staging_file_becomes_a_controlled_error(
    p1_subjects, p1_route_client, p1_providers, monkeypatch
):
    subject = p1_subjects["科目A"]

    async def _open_or_report(audio_path, *, language="zh"):
        try:
            with open(audio_path, "rb") as handle:
                handle.read(1)
        except OSError as exc:
            return {
                "text": "",
                "model": "stub-stt",
                "base_url": "https://stub.invalid",
                "error": f"{type(exc).__name__}",
                "error_kind": "io",
            }
        return {"text": "unexpected", "model": "stub-stt", "base_url": "https://stub.invalid"}

    def _stage_then_remove(plan, staging_dir, **kwargs):
        raise AssertionError("stage_files must not run in this scenario")

    async def _stage_with_missing_file(plan, staging_dir, **kwargs):
        staged = await _real_stage(plan, staging_dir, **kwargs)
        staged[0].path.unlink()
        return staged

    _real_stage = uploads.stage_files
    helpers.install_stub(
        monkeypatch, "deeptutor.services.asr.transcribe", "transcribe", _open_or_report
    )
    _ = _stage_then_remove
    monkeypatch.setattr(uploads, "stage_files", _stage_with_missing_file)
    response = _upload(p1_route_client, subject.subject_id, [_audio("gone.wav")])
    # 本地音频读不到是存储问题，不是供应商问题（R6）
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_io"
    assert not (_material_dir(subject) / "gone.wav").exists()
    assert _staging_slots(subject) == []


# ---------------------------------------------------------------------------
# ASR wire：文件流 + MIME + 不整块读入内存
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "wire-transcript") -> None:
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    captured: dict = {}

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, headers=None, files=None, data=None):
        name, payload, mime = files["file"]
        handle = payload
        body = handle.read() if hasattr(handle, "read") else payload
        _FakeAsyncClient.captured = {
            "url": url,
            "headers": headers,
            "data": data,
            "name": name,
            "mime": mime,
            "is_stream": hasattr(handle, "read"),
            "closed_after": None,
            "body": body,
            "handle": handle,
            "timeout": self.init_kwargs.get("timeout"),
        }
        return _FakeResponse()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.wav", "audio/wav"),
        ("a.m4a", "audio/mp4"),
        ("a.flac", "audio/flac"),
        ("a.mp3", "audio/mpeg"),
        ("a.ogg", "audio/ogg"),
    ],
)
def test_asr_sends_a_file_stream_with_the_extension_mime(
    tmp_path, monkeypatch, filename, expected
):
    import asyncio

    monkeypatch.setattr(
        transcribe_module,
        "_stt_config",
        lambda: transcribe_module.STTConfig(base_url="https://stt.invalid/v1", api_key="sk-fake-key", model="fake-stt-model"),
    )
    monkeypatch.setattr(transcribe_module.httpx, "AsyncClient", _FakeAsyncClient)

    def _no_read_bytes(self):  # pragma: no cover - must never be called
        raise AssertionError("read_bytes() must not be used for ASR uploads")

    monkeypatch.setattr(Path, "read_bytes", _no_read_bytes)

    payload = os.urandom(4_000)
    audio = tmp_path / filename
    audio.write_bytes(b"RIFF" + payload)

    result = asyncio.run(transcribe_module.transcribe(audio, language="zh"))
    captured = _FakeAsyncClient.captured

    assert result["error"] == ""
    assert result["text"] == "wire-transcript"
    assert captured["is_stream"] is True
    assert captured["mime"] == expected
    assert captured["name"] == filename
    assert captured["body"] == b"RIFF" + payload
    assert captured["data"]["response_format"] == "text"
    assert captured["data"]["language"] == "zh"
    assert captured["data"]["model"] == "fake-stt-model"
    assert captured["headers"]["Authorization"] == "Bearer sk-fake-key"
    assert captured["timeout"] == 300
    assert captured["handle"].closed is True


def test_provider_error_body_and_marker_are_not_echoed(tmp_path, monkeypatch):
    import asyncio

    class _Failing(_FakeAsyncClient):
        async def post(self, url, headers=None, files=None, data=None):
            return _FakeResponse(status_code=500, text=f"boom {FAKE_MARKER}")

    monkeypatch.setattr(
        transcribe_module,
        "_stt_config",
        lambda: transcribe_module.STTConfig(base_url="https://stt.invalid/v1", api_key="sk-fake-key", model="fake-stt-model"),
    )
    monkeypatch.setattr(transcribe_module.httpx, "AsyncClient", _Failing)

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    result = asyncio.run(transcribe_module.transcribe(audio))

    assert result["error_kind"] == "provider"
    assert FAKE_MARKER not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", ""),
        ("  spaced  ", "spaced"),
        ('{"text": "json transcript"}', "json transcript"),
        ('{"text": ""}', ""),
        ('{"text": 12}', None),
        ('{"text": {"nested": 1}}', None),
        ('{"other": "value"}', None),
        ("{not json", None),
        ("[1, 2, 3]", None),
        ("null", None),
        ('"just a string"', None),
        ("123", "123"),
    ],
)
def test_transcript_extraction_requires_a_real_string(body, expected):
    # 纯文本按原样返回；数组/null/字符串字面量等 JSON 形态不是转写
    assert transcribe_module.extract_transcript_text(body) == expected


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        ('["not-a-transcript"]', "application/json", None),
        ("null", "application/json", None),
        ("123", "application/json", None),
        ('{"text": 12}', "application/json", None),
        ('{"other": "x"}', "application/json", None),
        ("{not json", "application/json", None),
        ('{"text": "ok"}', "application/json", "ok"),
        ("plain transcript", "text/plain", "plain transcript"),
        ("", "text/plain", ""),
        ('{"text": "json"}', "text/plain", "json"),
    ],
)
def test_json_payloads_are_only_transcripts_as_objects_with_string_text(
    body, content_type, expected
):
    assert (
        transcribe_module.extract_transcript_text(body, content_type=content_type) == expected
    )


def test_invalid_provider_payload_is_not_reported_as_a_transcript(
    p1_subjects, p1_route_client, monkeypatch, tmp_path
):
    import asyncio

    class _BadPayload(_FakeAsyncClient):
        async def post(self, url, headers=None, files=None, data=None):
            return _FakeResponse(status_code=200, text='{"text": 12}')

    monkeypatch.setattr(
        transcribe_module,
        "_stt_config",
        lambda: transcribe_module.STTConfig(base_url="https://stt.invalid/v1", api_key="sk-fake-key", model="fake-stt-model"),
    )
    monkeypatch.setattr(transcribe_module.httpx, "AsyncClient", _BadPayload)

    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("bad.wav")])
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert not (_material_dir(subject) / "bad.wav").exists()
    assert asyncio.run(
        transcribe_module.transcribe(tmp_path / "missing.wav")
    )["error_kind"] in ("io",)


# ---------------------------------------------------------------------------
# 范围：不扩大普通文档允许集合
# ---------------------------------------------------------------------------
def test_audio_path_does_not_widen_the_document_whitelist():
    before = set(DocumentValidator.ALLOWED_EXTENSIONS)
    supported = material_manifest.supported_extensions()
    assert not (before & set(uploads.AUDIO_EXTENSIONS))
    assert not (supported & set(uploads.AUDIO_EXTENSIONS))
    assert ".zip" not in supported and ".doc" not in supported and ".ppt" not in supported
    assert DocumentValidator.ALLOWED_EXTENSIONS == before


@pytest.mark.parametrize("name", ["archive.zip", "legacy.doc", "binary.exe", "clip.mp4"])
def test_unsupported_document_extensions_are_refused_before_writing(
    p1_subjects, p1_route_client, p1_providers, name
):
    subject = p1_subjects["科目A"]
    before = _tree(subject.root)
    response = _upload(p1_route_client, subject.subject_id, [(name, b"data", None)])
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    assert _tree(subject.root) == before


# ---------------------------------------------------------------------------
# R1（rework01）：可预测的临时叶软链接不能改写资料根之外
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("part", [".a.wav.p1part", ".a.wav.transcript.txt.p1part"])
def test_predictable_part_symlinks_cannot_overwrite_outside(
    p1_subjects, p1_route_client, p1_providers, tmp_path, part
):
    subject = p1_subjects["科目A"]
    lecture = _material_dir(subject)
    lecture.mkdir(parents=True, exist_ok=True)
    for existing in lecture.iterdir():
        if existing.name != json_store.LOCK_FILE_NAME:
            existing.unlink() if existing.is_file() or existing.is_symlink() else None

    outside = tmp_path / "outside-audio-part"
    outside.write_bytes(b"outside-old")
    (lecture / part).symlink_to(outside)

    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav")])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] in ("storage_io", "storage_corrupt")
    assert outside.read_bytes() == b"outside-old", "临时软链接把内容写到了资料根之外"


def test_a_leftover_part_file_is_replaced_not_followed(
    p1_subjects, p1_route_client, p1_providers, tmp_path
):
    """普通残留 part 文件属于本模块命名空间：可安全清理并重新独占创建。"""
    subject = p1_subjects["科目A"]
    lecture = _material_dir(subject)
    lecture.mkdir(parents=True, exist_ok=True)
    stale = lecture / ".a.wav.p1part"
    stale.write_bytes(b"stale-temp")

    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav")])
    assert response.status_code == 200, response.text
    assert (lecture / "a.wav").read_bytes() == b"RIFF" + bytes(64)
    assert not stale.exists()


# ---------------------------------------------------------------------------
# R6（rework01）：ASR 配置与供应商响应边界
# ---------------------------------------------------------------------------
def test_stt_configuration_failure_is_a_provider_error_without_publishing(
    p1_subjects, p1_route_client, monkeypatch
):
    def _boom():
        raise RuntimeError(FAKE_MARKER)

    monkeypatch.setattr(transcribe_module, "_stt_config", _boom)
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav")])
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert FAKE_MARKER not in response.text
    assert not (_material_dir(subject) / "a.wav").exists()
    assert _staging_slots(subject) == []


class _BodyResponseClient:
    """假 httpx client：固定返回一个原始正文 + content-type。"""

    def __init__(self, body: str, content_type: str, *, status_code: int = 200) -> None:
        self.body = body
        self.content_type = content_type
        self.status_code = status_code

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, *args, **kwargs):
        import httpx

        return httpx.Response(
            self.status_code,
            content=self.body.encode("utf-8"),
            headers={"content-type": self.content_type},
        )


def _patch_asr_transport(monkeypatch, body: str, content_type: str) -> None:
    monkeypatch.setattr(
        transcribe_module,
        "_stt_config",
        lambda: transcribe_module.STTConfig(base_url="https://stt.invalid/v1", api_key="sk-fake", model="fake-model"),
    )
    monkeypatch.setattr(
        transcribe_module.httpx, "AsyncClient", _BodyResponseClient(body, content_type)
    )


@pytest.mark.parametrize(
    "body",
    [
        '["not-a-transcript"]',
        "null",
        "123",
        '"scalar"',
        '{"other": "value"}',
        '{"text": 12}',
        "{}",
        "{not json",
    ],
)
def test_non_object_json_responses_are_not_transcripts(
    p1_subjects, p1_route_client, monkeypatch, body
):
    _patch_asr_transport(monkeypatch, body, "application/json")
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav")])
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert not (_material_dir(subject) / "a.wav").exists()


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        ('{"text": "来自 JSON 的转写"}', "application/json", "来自 JSON 的转写"),
        ('{"text": ""}', "application/json", ""),
        ("纯文本转写", "text/plain", "纯文本转写"),
        ("", "text/plain", ""),
    ],
)
def test_object_json_and_plain_text_stay_compatible(
    p1_subjects, p1_route_client, monkeypatch, body, content_type, expected
):
    _patch_asr_transport(monkeypatch, body, content_type)
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav")])
    assert response.status_code == 200, response.text
    assert response.json()["transcripts"][0]["text"] == expected
    assert (_material_dir(subject) / "a.wav.transcript.txt").read_text(
        encoding="utf-8"
    ) == expected


def test_local_audio_read_failure_is_a_storage_error_not_a_provider_one(
    p1_subjects, p1_route_client, monkeypatch
):
    async def _missing(audio_path, *, language="zh"):
        return {
            "text": "",
            "model": "stub",
            "base_url": "https://stub.invalid",
            "error": f"FileNotFoundError {FAKE_MARKER}",
            "error_kind": "io",
        }

    helpers.install_stub(
        monkeypatch, "deeptutor.services.asr.transcribe", "transcribe", _missing
    )
    subject = p1_subjects["科目A"]
    response = _upload(p1_route_client, subject.subject_id, [_audio("gone.wav")])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_io"
    assert FAKE_MARKER not in response.text


# ---------------------------------------------------------------------------
# R3（rework01）：音频与转写文本在同一个回滚边界内
# ---------------------------------------------------------------------------
def test_transcript_write_failure_rolls_back_the_audio(
    p1_subjects, p1_route_client, p1_providers, monkeypatch
):
    subject = p1_subjects["科目A"]
    lecture = _material_dir(subject)
    lecture.mkdir(parents=True, exist_ok=True)
    (lecture / "a.wav").write_bytes(b"old-audio")
    (lecture / "b.wav").write_bytes(b"old-b")
    before = _tree_without_locks(subject.root)

    real = uploads._write_text_atomic

    def _fail_second(target, text):
        if Path(target).name.startswith("b.wav"):
            raise json_store.StorageIOError("injected transcript failure", path=target.name)
        return real(target, text)

    monkeypatch.setattr(uploads, "_write_text_atomic", _fail_second)
    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav"), _audio("b.wav")])
    assert response.status_code == 500, response.text
    assert (lecture / "a.wav").read_bytes() == b"old-audio", "第一份音频没有回滚"
    assert (lecture / "b.wav").read_bytes() == b"old-b"
    assert _tree_without_locks(subject.root) == before


def test_second_audio_publication_failure_rolls_back_the_first(
    p1_subjects, p1_route_client, p1_providers, monkeypatch
):
    subject = p1_subjects["科目A"]
    lecture = _material_dir(subject)
    lecture.mkdir(parents=True, exist_ok=True)
    for name in ("a.wav", "b.wav"):
        (lecture / name).write_bytes(b"old")

    real = uploads._atomic_copy

    def _fail(src, dst):
        if Path(dst) == lecture / "b.wav":
            raise json_store.StorageIOError("injected second audio failure")
        return real(src, dst)

    monkeypatch.setattr(uploads, "_atomic_copy", _fail)
    response = _upload(p1_route_client, subject.subject_id, [_audio("a.wav"), _audio("b.wav")])
    assert response.status_code == 500, response.text
    assert (lecture / "a.wav").read_bytes() == b"old", "第一份音频没有回滚"
    assert (lecture / "b.wav").read_bytes() == b"old"


@pytest.mark.parametrize(
    'error,code,status',
    [
        (json_store.StorageIOError('fake config IO'), 'storage_io', 500),
        (json_store.StorageCorruptError('fake config corruption'), 'storage_corrupt', 500),
        (TimeoutError('fake config timeout'), 'provider_timeout', 504),
    ],
)
def test_typed_stt_configuration_errors_keep_their_classification(
    p1_subjects, p1_route_client, monkeypatch, error, code, status
):
    from deeptutor.services.asr import transcribe as asr_service

    subject = p1_subjects['科目A']
    def fail_config():
        raise error
    monkeypatch.setattr(asr_service, '_stt_config', fail_config)
    response = _upload(p1_route_client, subject.subject_id, [('a.wav', b'audio', None)])
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert not (Path(subject.materials) / 'lecture' / 'a.wav').exists()

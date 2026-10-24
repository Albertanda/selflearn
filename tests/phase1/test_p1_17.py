"""P1-17 行为测试：完整 batch 分类与操作标识（C07）。

目标：不再按第一个文件给整批分类；``index`` 与 ``transcribe`` 的含义、字段与
实际执行一致；整批失败不留前缀保存、幽灵任务或记录。

必证场景（对应卡内清单）：

* 同类 ``auto`` 批次成功，且落盘、record、排队三者一致；
* ``png+docx``、``pdf+mp3``、``lecture+txt`` 一律 400，磁盘/records/queue 零正式变化；
* 只换顺序（把原本"第一个文件"放到最后）仍然拒绝——证明没有按首文件分类；
* 显式非 lecture 的人工类别覆盖仍合法，音频不能混入文档批次；
* 空批次、同批重名、NFC 规范化重名、ZIP、引擎不支持的扩展先拒绝；
* 两种成功响应分别满足 ``UploadIndex`` / ``UploadTranscribe``，且互不混淆。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.subjects import store, uploads
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX


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


class _QueueRecorder:
    """捕获队列：证明"已排队"，但绝不让真实索引发起网络/引擎调用。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, kb_dir, task_id, run, *args) -> None:
        self.calls.append(
            {
                "kb_dir": str(kb_dir),
                "task_id": task_id,
                "runner": getattr(run, "__name__", str(run)),
                "args": args,
            }
        )


@pytest.fixture(autouse=True)
def _isolated_upload_registry():
    uploads.reset_registry_for_tests()
    yield
    uploads.reset_registry_for_tests()


@pytest.fixture
def queued(monkeypatch) -> _QueueRecorder:
    recorder = _QueueRecorder()
    monkeypatch.setattr(uploads, "run_reserved_index_task", recorder)
    return recorder


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


def _doc(name: str, body: bytes = b"content") -> tuple[str, bytes, None]:
    return (name, body, None)


def _audio(name: str) -> tuple[str, bytes, str]:
    return (name, b"RIFF-audio", "audio/wav")


def _subject_state(subject) -> dict:
    return {
        "tree": helpers.tree_digest(subject.root),
        "records": store.load_knowledge_records(subject.subject_id),
    }


def _assert_no_side_effects(subject, queued: _QueueRecorder, before: dict) -> None:
    assert helpers.tree_digest(subject.root) == before["tree"]
    assert store.load_knowledge_records(subject.subject_id) == before["records"]
    assert queued.calls == []
    assert uploads.reservation_for(subject.knowledge_bases / "assignment-kb") is None
    assert not (subject.knowledge_bases / "assignment-kb").exists()
    assert not (subject.knowledge_bases / "board-kb").exists()
    assert not (subject.knowledge_bases / "lecture-kb").exists()


# ---------------------------------------------------------------------------
# 同类 auto 成功 + index 响应契约
# ---------------------------------------------------------------------------
def test_homogeneous_auto_batch_is_indexed_as_one_operation(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    response = _upload(
        p1_route_client,
        subject.subject_id,
        [_doc("notes-a.txt", b"alpha"), _doc("notes-b.md", b"beta")],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    _validate("UploadIndex", payload)

    assert payload["operation"] == "index"
    assert payload["kb_name"] == "assignment-kb"
    assert payload["type"] == "assignment"
    assert payload["files"] == ["notes-a.txt", "notes-b.md"]
    assert payload["task_id"] and isinstance(payload["task_id"], str)
    assert payload["documents"] == 2

    materials = Path(subject.materials) / "assignment"
    raw = subject.knowledge_bases / "assignment-kb" / "raw"
    for name, body in (("notes-a.txt", b"alpha"), ("notes-b.md", b"beta")):
        assert (materials / name).read_bytes() == body
        assert (raw / name).read_bytes() == body

    records = store.load_knowledge_records(subject.subject_id)
    assert len(records) == 1
    assert records[0]["kb_name"] == "assignment-kb"
    assert records[0]["type"] == "assignment"
    assert records[0]["documents"] == 2

    assert len(queued.calls) == 1
    assert queued.calls[0]["task_id"] == payload["task_id"]
    assert queued.calls[0]["runner"] == "run_initialization_task"
    reservation = uploads.reservation_for(subject.knowledge_bases / "assignment-kb")
    assert reservation is not None and reservation["task_id"] == payload["task_id"]


def test_same_category_but_unknown_document_extension_falls_back_to_textbook(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    response = _upload(
        p1_route_client, subject.subject_id, [_doc("script.py", b"print(1)"), _doc("data.json", b"{}")]
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    _validate("UploadIndex", payload)
    assert payload["type"] == "textbook"
    assert payload["kb_name"] == "textbook-kb"
    assert (Path(subject.materials) / "textbook" / "script.py").is_file()


# ---------------------------------------------------------------------------
# 整批分类：顺序无关
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "specs",
    [
        [_doc("board.png"), _doc("homework.docx")],
        [_doc("homework.docx"), _doc("board.png")],
        [_doc("book.pdf"), _audio("lecture.mp3")],
        [_audio("lecture.mp3"), _doc("book.pdf")],
        [_doc("book.pdf"), _doc("homework.docx")],
        [_doc("notes.txt"), _doc("slides.pptx")],
    ],
)
def test_mixed_auto_batches_are_refused_regardless_of_order(
    p1_subjects, p1_route_client, queued, specs
):
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(p1_route_client, subject.subject_id, specs)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"]["code"] == "invalid_input"
    assert payload["detail"] == "请求参数无效，请检查后重试。"
    _assert_no_side_effects(subject, queued, before)


def test_a_batch_that_would_pass_on_its_first_file_alone_is_still_refused(
    p1_subjects, p1_route_client, queued
):
    """坏对照：单看第一个文件是合法 textbook，整批仍然必须拒绝。"""
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(
        p1_route_client, subject.subject_id, [_doc("book.pdf"), _doc("board.png")]
    )
    assert response.status_code == 400, response.text
    _assert_no_side_effects(subject, queued, before)
    # 单独上传同一个 pdf 是合法的，证明上面的拒绝来自"整批"而不是这个文件本身
    solo = _upload(p1_route_client, subject.subject_id, [_doc("book.pdf")])
    assert solo.status_code == 200, solo.text
    assert solo.json()["type"] == "textbook"


# ---------------------------------------------------------------------------
# 显式类型规则
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "specs",
    [
        [_doc("notes.txt")],
        [_audio("lecture.wav"), _doc("notes.txt")],
    ],
)
def test_explicit_lecture_requires_audio_only(p1_subjects, p1_route_client, queued, specs):
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(p1_route_client, subject.subject_id, specs, type="lecture")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    _assert_no_side_effects(subject, queued, before)


def test_explicit_non_lecture_keeps_the_manual_override_but_refuses_audio(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    overridden = _upload(
        p1_route_client, subject.subject_id, [_doc("notes.txt", b"manual")], type="textbook"
    )
    assert overridden.status_code == 200, overridden.text
    payload = overridden.json()
    _validate("UploadIndex", payload)
    assert payload["type"] == "textbook"
    assert payload["kb_name"] == "textbook-kb"
    assert (Path(subject.materials) / "textbook" / "notes.txt").read_bytes() == b"manual"

    before = _subject_state(subject)
    queued.calls.clear()
    mixed = _upload(
        p1_route_client, subject.subject_id, [_audio("lecture.wav")], type="assignment"
    )
    assert mixed.status_code == 400, mixed.text
    assert helpers.tree_digest(subject.root) == before["tree"]
    assert queued.calls == []
    assert uploads.reservation_for(subject.knowledge_bases / "textbook-kb") is not None


def test_unknown_explicit_type_is_refused(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(p1_route_client, subject.subject_id, [_doc("a.txt")], type="handout")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    _assert_no_side_effects(subject, queued, before)


# ---------------------------------------------------------------------------
# 先拒绝：空批次 / 重名 / ZIP / 不支持扩展
# ---------------------------------------------------------------------------
def test_empty_batch_is_refused_before_any_disk_change(p1_subjects, p1_route_client, queued):
    from deeptutor.subjects import json_store

    with pytest.raises(json_store.InvalidInputError):
        uploads.plan_batch([], type="auto")

    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = p1_route_client.post(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/upload",
        files=[],
        data={"type": "auto"},
    )
    assert response.status_code == 422, response.text
    assert helpers.tree_digest(subject.root) == before["tree"]
    assert queued.calls == []


@pytest.mark.parametrize(
    ("specs", "legal_counterpart"),
    [
        ([_doc("same.txt", b"one"), _doc("same.txt", b"two")],
         [_doc("same.txt", b"one"), _doc("same-2.txt", b"two")]),
        ([_doc("Same.TXT"), _doc("Same.txt")],
         [_doc("Same.TXT"), _doc("Other.txt")]),
        ([_doc("caf\u00e9.txt"), _doc("cafe\u0301.txt")],
         [_doc("caf\u00e9.txt"), _doc("cafe-plain.txt")]),
        ([_doc("report.pdf"), _doc("report.PDF")],
         [_doc("report.pdf"), _doc("report-2.PDF")]),
    ],
)
def test_duplicate_names_in_one_batch_are_refused(
    p1_subjects, p1_route_client, queued, specs, legal_counterpart
):
    """坏对照：同一批只把重名改成不同名就合法，证明拒绝来自重复名本身。

    C02 的对外消息是固定安全文案（不回显输入），所以这里用"只改一个字段"的
    合法对照证明原因，而不是断言错误文本里出现某个词。
    """
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(p1_route_client, subject.subject_id, specs)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    _assert_no_side_effects(subject, queued, before)

    legal = _upload(p1_route_client, subject.subject_id, legal_counterpart)
    assert legal.status_code == 200, legal.text
    assert legal.json()["operation"] == "index"


@pytest.mark.parametrize(
    "name", ["archive.zip", "nested.zip", "legacy.doc", "slides.ppt", "tool.exe"]
)
def test_zip_and_unsupported_extensions_are_refused(
    p1_subjects, p1_route_client, queued, name
):
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    for type_value in ("auto", "textbook"):
        response = _upload(p1_route_client, subject.subject_id, [_doc(name)], type=type_value)
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "invalid_input"
    _assert_no_side_effects(subject, queued, before)


def test_derived_transcript_names_never_collide_with_inputs(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    before = _subject_state(subject)
    response = _upload(
        p1_route_client,
        subject.subject_id,
        [_audio("lesson.wav"), _doc("lesson.wav.transcript.txt", b"fake")],
    )
    assert response.status_code == 400, response.text
    assert helpers.tree_digest(subject.root) == before["tree"]
    assert queued.calls == []


# ---------------------------------------------------------------------------
# 操作标识：两种响应不混淆
# ---------------------------------------------------------------------------
def test_index_and_transcribe_responses_are_distinct(
    p1_subjects, p1_route_client, queued, p1_providers
):
    subject = p1_subjects["科目A"]
    index_response = _upload(p1_route_client, subject.subject_id, [_doc("notes.txt")])
    transcribe_response = _upload(p1_route_client, subject.subject_id, [_audio("lecture.wav")])

    assert index_response.status_code == 200 and transcribe_response.status_code == 200
    index_payload = index_response.json()
    transcribe_payload = transcribe_response.json()
    _validate("UploadIndex", index_payload)
    _validate("UploadTranscribe", transcribe_payload)

    assert index_payload["operation"] == "index"
    assert "transcripts" not in index_payload
    assert "task_id" in index_payload and "kb_name" in index_payload

    assert transcribe_payload["operation"] == "transcribe"
    assert transcribe_payload["type"] == "lecture"
    assert "task_id" not in transcribe_payload
    assert "kb_name" not in transcribe_payload

    # 坏对照：转写响应不满足 index 契约，index 响应也不满足 transcribe 契约
    from jsonschema import ValidationError, validate

    with pytest.raises(ValidationError):
        validate(instance=transcribe_payload, schema=_schema("UploadIndex"))
    with pytest.raises(ValidationError):
        validate(instance=index_payload, schema=_schema("UploadTranscribe"))

    # 转写文档没有进入任何 KB，也没有留下索引源
    assert queued.calls and all(
        call["kb_dir"].endswith("assignment-kb") for call in queued.calls
    )
    assert not (subject.knowledge_bases / "lecture-kb").exists()


def test_a_second_batch_reuses_the_same_kb_without_creating_another(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload(p1_route_client, subject.subject_id, [_doc("one.txt", b"1")])
    assert first.status_code == 200, first.text
    assert len(store.load_knowledge_records(subject.subject_id)) == 1

    # 仍处于"已排队未开始"状态：同库第二批必须先被业务拒绝，而不是另建 KB
    second = _upload(p1_route_client, subject.subject_id, [_doc("two.txt", b"2")])
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "kb_busy"
    assert store.load_knowledge_records(subject.subject_id)[0]["documents"] == 1
    assert len(queued.calls) == 1

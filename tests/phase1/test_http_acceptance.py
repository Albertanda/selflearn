"""S14/P1-51: HTTP 现有业务闭环验收（真实路由 + 临时磁盘）。

覆盖 H1–H6：科目 CRUD/三态、multipart 资料与真实索引、批改/学情、
考点检测、复习包/图表报告发布、ZIP 导出与删除互斥。

边界：外部 LLM/STT/embedding 只使用确定性替身；科目路由、Form/File 解析、
领域服务、真实 LlamaIndex 文本索引、真实 bwrap/Matplotlib/Typst 报告链、
outputs 下载和 ZIP/PDF/DOCX 解析都实际运行。所有写入都在 pytest 临时根。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from deeptutor.api.routers import outputs
from deeptutor.api.routers import subjects as subjects_router
from deeptutor.services.llm.exceptions import LLMProviderTransportError
from deeptutor.services.pdf import report as report_mod
from deeptutor.services.pdf import report_store
from deeptutor.subjects import export_bundle, json_store, material_manifest, store
from deeptutor.utils.document_validator import DocumentValidator
from tests.phase1 import helpers

ROUTE = "/api/v1/subjects"
OUTPUTS = "/api/outputs"
KB_NAME = "assignment-kb"

#: 本文件所有 fake 文本/路径都带这个标记；错误响应不得回显它。
FAKE_SECRET = "s14-http-FAKE-PROVIDER-TEXT-71c2-DO-NOT-LEAK"


def _catalog() -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "s14-llm-profile",
                "active_model_id": "s14-llm-model",
                "profiles": [
                    {
                        "id": "s14-llm-profile",
                        "name": "S14 local stub",
                        "binding": "openai",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "sk-s14-fake-only",
                        "models": [
                            {"id": "s14-llm-model", "name": "s14", "model": "s14-local-stub"}
                        ],
                    }
                ],
            },
            "embedding": {
                "active_profile_id": "s14-embedding-profile",
                "active_model_id": "s14-embedding-model",
                "profiles": [
                    {
                        "id": "s14-embedding-profile",
                        "name": "S14 embedding stub",
                        "binding": "openai",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "sk-s14-fake-only",
                        "models": [
                            {
                                "id": "s14-embedding-model",
                                "name": "s14-embedding",
                                "model": "s14-text-embedding",
                                "dimension": 8,
                            }
                        ],
                    }
                ],
            },
            "search": {"active_profile_id": None, "profiles": []},
        },
    }


def _seed_catalog(admin_root: Path) -> None:
    path = admin_root / "user" / "settings" / "model_catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_catalog(), ensure_ascii=False), encoding="utf-8")


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(subjects_router.router, prefix=ROUTE)
    app.include_router(outputs.router, prefix=OUTPUTS)
    return app


@pytest.fixture
def http_client(p1_runtime: Path, p1_providers) -> TestClient:
    _seed_catalog(p1_runtime)
    with TestClient(_app()) as client:
        yield client


def _create(client: TestClient, name: str, *, description: str = "", term: str = "2026春"):
    response = client.post(
        ROUTE, data={"name": name, "description": description, "term": term}
    )
    assert response.status_code == 200, response.text
    return response.json()["subject"]


def _upload(
    client: TestClient,
    subject_id: str,
    *,
    filename: str,
    content: bytes,
    type_: str = "assignment",
):
    return client.post(
        f"{ROUTE}/{subject_id}/knowledge/upload",
        files=[("files", (filename, content, "text/plain"))],
        data={"type": type_},
    )


def _wait_ready(client: TestClient, subject_id: str, kb_name: str = KB_NAME) -> dict:
    deadline = time.monotonic() + 20
    last: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"{ROUTE}/{subject_id}/knowledge/{kb_name}/status")
        assert response.status_code == 200, response.text
        last = response.json()
        if last.get("status") == "ready":
            return last
        if last.get("status") == "error":
            raise AssertionError(last)
        time.sleep(0.05)
    raise AssertionError(f"KB did not become ready: {last}")


def _query(client: TestClient, subject_id: str, marker: str, kb_name: str = KB_NAME) -> dict:
    response = client.post(
        f"{ROUTE}/{subject_id}/knowledge/{kb_name}/query",
        data={"query": marker, "mode": "hybrid"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tree(root: Path) -> dict[str, str]:
    return helpers.tree_digest(root)


def _tree_without_locks(root: Path) -> dict[str, str]:
    return {
        path: digest
        for path, digest in helpers.tree_digest(root).items()
        if not path.endswith(json_store.LOCK_FILE_NAME)
    }


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# H1 — CRUD / PATCH 三态
# ---------------------------------------------------------------------------
def test_h1_http_crud_and_patch_three_state(http_client: TestClient) -> None:
    a = _create(http_client, "科目 A", description="原描述", term="2026春")
    b = _create(http_client, "科目 B", description="B 描述", term="2025秋")
    assert a["id"] and b["id"] and a["id"] != b["id"]
    assert a["id"].islower() and " " not in a["id"]
    assert a["name"] == "科目 A" and a["term"] == "2026春"

    listing = http_client.get(ROUTE)
    assert listing.status_code == 200
    ids = {item["id"] for item in listing.json()["subjects"]}
    assert {a["id"], b["id"]} <= ids

    # 只提交 description：term 必须保留。
    patched = http_client.patch(f"{ROUTE}/{a['id']}", data={"description": "新描述"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["subject"]["description"] == "新描述"
    assert patched.json()["subject"]["term"] == "2026春"

    # 显式空字符串：只清空 term，description 保留。
    cleared = http_client.patch(f"{ROUTE}/{a['id']}", data={"term": ""})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["subject"]["term"] == ""
    assert cleared.json()["subject"]["description"] == "新描述"

    # 空 PATCH 不写注册表（字节不变）。
    registry = store.subjects_root() / "index.json"
    before = registry.read_bytes()
    noop = http_client.patch(f"{ROUTE}/{a['id']}", data={})
    assert noop.status_code == 200, noop.text
    assert noop.json()["subject"]["description"] == "新描述"
    assert registry.read_bytes() == before

    # 不存在的科目是具名 C02，而不是半写或 500。
    missing = http_client.patch(f"{ROUTE}/not-registered", data={"description": "x"})
    assert missing.status_code == 404, missing.text
    body = missing.json()
    assert body["detail"] == body["error"]["message"]
    assert body["error"]["code"] == "subject_not_found"
    assert registry.read_bytes() == before
    assert b["id"] in {item["id"] for item in http_client.get(ROUTE).json()["subjects"]}


# ---------------------------------------------------------------------------
# H2 — multipart 文档/音频、同名替换、路径/限额/软链接负例
# ---------------------------------------------------------------------------
def test_h2_multipart_document_is_indexed_and_same_name_replacement_is_authoritative(
    http_client: TestClient, p1_providers
) -> None:
    subject = _create(http_client, "资料科目")
    sid = subject["id"]
    old_marker = "HTTP-DOC-OLD-5e1a"
    new_marker = "HTTP-DOC-NEW-9b27"

    first = _upload(
        http_client,
        sid,
        filename="notes.txt",
        content=f"# 第一版\n\n{old_marker}\n".encode(),
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["operation"] == "index"
    assert first_body["type"] == "assignment"
    assert first_body["files"] == ["notes.txt"]
    assert first_body["task_id"]
    _wait_ready(http_client, sid)

    old = _query(http_client, sid, old_marker)
    assert old_marker in old["result"]["answer"]
    assert "needs_reindex" not in old["result"]

    replacement = _upload(
        http_client,
        sid,
        filename="notes.txt",
        content=f"# 第二版\n\n{new_marker}\n".encode(),
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["operation"] == "index"
    _wait_ready(http_client, sid)

    current = _query(http_client, sid, new_marker)
    assert new_marker in current["result"]["answer"]
    assert old_marker not in json.dumps(current, ensure_ascii=False)

    # 当前权威 raw 和 manifest 确实是新字节；旧索引只是历史版本，不再被读取。
    from deeptutor.subjects.store import subject_dir

    root = subject_dir(sid)
    raw = root / "knowledge_bases" / KB_NAME / "raw" / "notes.txt"
    manifest_path = root / "knowledge_bases" / KB_NAME / material_manifest.MANIFEST_NAME
    assert raw.read_text(encoding="utf-8").endswith(new_marker + "\n")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    only = manifest["files"][0]
    assert only["path"] == "notes.txt"
    assert only["sha256"] == _hash(raw)
    assert only["size"] == raw.stat().st_size

    # 音频：实际 ASR 接线与落盘，audio 不冒充自动索引。
    audio = http_client.post(
        f"{ROUTE}/{sid}/knowledge/upload",
        files=[("files", ("lecture.wav", b"RIFF" + b"\x00" * 64, "audio/wav"))],
        data={"type": "lecture"},
    )
    assert audio.status_code == 200, audio.text
    audio_body = audio.json()
    assert audio_body["operation"] == "transcribe"
    assert "task_id" not in audio_body and "kb_name" not in audio_body
    assert audio_body["transcripts"][0]["text"] == "stub-transcript"
    assert (root / "materials" / "lecture" / "lecture.wav").is_file()
    assert (root / "materials" / "lecture" / "lecture.wav.transcript.txt").read_text(
        encoding="utf-8"
    ) == "stub-transcript"
    assert not (root / "knowledge_bases" / "lecture-kb").exists()
    assert p1_providers["stt"].call_count >= 1


def test_h2_multipart_path_names_and_limit_are_rejected_before_publication(
    http_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _create(http_client, "拒绝科目")
    sid = subject["id"]
    marker = "HTTP-KEEP-ORIGINAL-3df0"
    assert _upload(
        http_client, sid, filename="keep.txt", content=f"{marker}\n".encode()
    ).status_code == 200
    _wait_ready(http_client, sid)

    from deeptutor.subjects.store import subject_dir

    root = subject_dir(sid)
    raw = root / "knowledge_bases" / KB_NAME / "raw" / "keep.txt"
    manifest = root / "knowledge_bases" / KB_NAME / material_manifest.MANIFEST_NAME
    before_raw, before_manifest = raw.read_bytes(), manifest.read_bytes()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"s14 outside sentinel")

    for bad_name in ("../escape.txt", "/tmp/s14-absolute-escape.txt", "a\\b.txt"):
        response = _upload(http_client, sid, filename=bad_name, content=b"evil")
        assert response.status_code == 400, (bad_name, response.text)
        assert response.json()["error"]["code"] == "invalid_input"
        assert raw.read_bytes() == before_raw
        assert manifest.read_bytes() == before_manifest
        assert outside.read_bytes() == b"s14 outside sentinel"

    monkeypatch.setattr(DocumentValidator, "MAX_FILE_SIZE", 1024)
    too_big = _upload(http_client, sid, filename="big.txt", content=b"x" * 1025)
    assert too_big.status_code == 400, too_big.text
    assert too_big.json()["error"]["code"] == "invalid_input"
    assert not (root / "knowledge_bases" / KB_NAME / "raw" / "big.txt").exists()
    assert raw.read_bytes() == before_raw
    assert manifest.read_bytes() == before_manifest

    # 软链接叶：服务端在发布前拒绝，绝不跟随写入；旧字节/manifest 保留。
    material = root / "materials" / "assignment" / "linked.txt"
    material.parent.mkdir(parents=True, exist_ok=True)
    material.symlink_to(outside)
    linked = _upload(http_client, sid, filename="linked.txt", content=b"through-link")
    assert linked.status_code == 500, linked.text
    assert linked.json()["error"]["code"] in {"storage_io", "storage_corrupt"}
    assert material.is_symlink()
    assert outside.read_bytes() == b"s14 outside sentinel"
    assert raw.read_bytes() == before_raw
    assert manifest.read_bytes() == before_manifest


# ---------------------------------------------------------------------------
# H3 — 批改/学情
# ---------------------------------------------------------------------------
def _check(client: TestClient, sid: str, *, question: str, answer: str, kp: str = ""):
    return client.post(
        f"{ROUTE}/{sid}/wrong-book/check",
        data={
            "question": question,
            "student_answer": answer,
            "reference_answer": "x",
            "kp": kp,
        },
    )


def test_h3_http_grading_verdicts_attempts_and_knowledge_points(
    http_client: TestClient, p1_llm
) -> None:
    subject = _create(http_client, "批改科目")
    sid = subject["id"]
    q_correct, q_partial, q_wrong = "导数题一", "导数题二", "导数题三"

    p1_llm.response = json.dumps({"verdict": "correct", "feedback": "很好"})
    correct = _check(http_client, sid, question=q_correct, answer="1")
    assert correct.status_code == 200, correct.text
    body = correct.json()
    assert body["verdict"] == "correct" and body["correct"] is True
    assert body["saved"] is False and body["entry"] is None

    p1_llm.response = json.dumps({"verdict": "partial", "feedback": "一半对"})
    partial = _check(http_client, sid, question=q_partial, answer="1", kp="导数")
    assert partial.status_code == 200, partial.text
    partial_body = partial.json()
    assert partial_body["verdict"] == "partial"
    assert partial_body["correct"] is False and partial_body["saved"] is True
    entry = partial_body["entry"]
    assert entry["question"] == q_partial and entry["kp"] == "导数"
    assert len(entry["attempts"]) == 1
    assert entry["attempts"][0]["correct"] is False
    assert entry["mastery"] == 0 or entry["status"] == "missed"

    p1_llm.response = json.dumps({"verdict": "wrong", "feedback": "错了"})
    wrong = _check(http_client, sid, question=q_partial, answer="2", kp="导数")
    assert wrong.status_code == 200, wrong.text
    wrong_body = wrong.json()
    assert wrong_body["verdict"] == "wrong" and wrong_body["correct"] is False
    assert wrong_body["saved"] is True
    assert len(wrong_body["entry"]["attempts"]) == 2
    assert all(item["correct"] is False for item in wrong_body["entry"]["attempts"])
    assert wrong_body["entry"]["mastery"] <= entry["mastery"]

    # 真实 HTTP 考点 + 知识点构建，让 C10 的 assessed 关联有可核对来源。
    added = http_client.post(
        f"{ROUTE}/{sid}/exam-points",
        data={
            "content": "导数应用",
            "level": "explicit",
            "evidence": "必考",
            "kp": "导数",
            "term": "2026春",
            "confirmed": "true",
        },
    )
    assert added.status_code == 200, added.text
    built = http_client.post(f"{ROUTE}/{sid}/knowledge-points/build")
    assert built.status_code == 200, built.text
    points = http_client.get(f"{ROUTE}/{sid}/knowledge-points")
    assert points.status_code == 200, points.text
    point = next(item for item in points.json()["points"] if item["name"] == "导数")
    assert point["evidence_count"] == 1
    assert point["assessment_status"] == "assessed"
    assert point["mastery"] is not None

    # 新题答对仍不进入错题本。
    wrong_book = json.loads((store.subject_dir(sid) / "wrong_book.json").read_text("utf-8"))
    assert [item["question"] for item in wrong_book] == [q_partial]


@pytest.mark.parametrize(
    ("response", "finish_reason", "expected"),
    [
        ("{not json", "stop", "invalid_model_output"),
        ("", "stop", "empty_model_output"),
        ('{"verdict":"wrong","feedback":"半截', "length", "output_truncated"),
    ],
)
def test_h3_http_model_failures_are_c02_and_leave_learning_bytes_unchanged(
    http_client: TestClient,
    p1_llm,
    response: str,
    finish_reason: str,
    expected: str,
) -> None:
    subject = _create(http_client, "失败批改科目")
    sid = subject["id"]
    p1_llm.response = json.dumps({"verdict": "partial", "feedback": "先记一次"})
    p1_llm.finish_reason = "stop"
    seeded = _check(http_client, sid, question="原题", answer="1", kp="导数")
    assert seeded.status_code == 200, seeded.text

    from deeptutor.subjects.store import subject_dir

    before = _tree_without_locks(subject_dir(sid))
    p1_llm.response = response
    p1_llm.finish_reason = finish_reason
    failed = _check(http_client, sid, question="会失败的新题", answer="2", kp="导数")
    assert failed.status_code >= 400, failed.text
    assert failed.json()["error"]["code"] == expected
    assert failed.json()["detail"] == failed.json()["error"]["message"]
    assert FAKE_SECRET not in failed.text
    assert _tree_without_locks(subject_dir(sid)) == before


def test_h3_http_transport_failure_is_502_without_echo_or_learning_change(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _create(http_client, "传输失败科目")
    sid = subject["id"]
    from deeptutor.subjects.store import subject_dir

    # 合法基准（成功一次）后再只改 provider 故障点。
    baseline_llm = helpers.FakeLLMClient(json.dumps({"verdict": "wrong", "feedback": "基准"}))
    monkeypatch.setattr(
        "deeptutor.services.llm.factory.complete_response", baseline_llm.complete_response
    )
    seeded = _check(http_client, sid, question="基准题", answer="0")
    assert seeded.status_code == 200, seeded.text
    before = _tree_without_locks(subject_dir(sid))

    async def broken(*_args, **_kwargs):
        raise LLMProviderTransportError(f"upstream {FAKE_SECRET} /host/private/cache")

    monkeypatch.setattr("deeptutor.services.llm.factory.complete_response", broken)
    failed = _check(http_client, sid, question="传输失败题", answer="1")
    assert failed.status_code == 502, failed.text
    body = failed.json()
    assert body["error"]["code"] == "provider_unavailable"
    assert body["detail"] == body["error"]["message"]
    assert FAKE_SECRET not in failed.text and "/host/private/cache" not in failed.text
    assert _tree_without_locks(subject_dir(sid)) == before


# ---------------------------------------------------------------------------
# H4 — 考点检测
# ---------------------------------------------------------------------------
def _points_json(*points: dict) -> str:
    return json.dumps({"points": list(points)}, ensure_ascii=False)


def _detect(client: TestClient, sid: str, transcript: str, *, auto_confirm: bool = False):
    return client.post(
        f"{ROUTE}/{sid}/exam-points/detect",
        data={
            "transcript": transcript,
            "term": "2026春",
            "source": "lecture",
            "auto_confirm": str(auto_confirm).lower(),
        },
    )


def test_h4_exam_detection_four_keys_source_and_confirmation(
    http_client: TestClient, p1_llm
) -> None:
    subject = _create(http_client, "考点科目")
    sid = subject["id"]
    transcript = "这一段是必考内容。这个知识点很重要。"
    p1_llm.response = _points_json(
        {
            "content": "必考公式",
            "level": "explicit",
            "evidence": "这一段是必考内容",
            "kp": "公式",
        },
        {
            "content": "重要概念",
            "level": "emphasis",
            "evidence": "这个知识点很重要",
            "kp": "概念",
        },
    )
    response = _detect(http_client, sid, transcript)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"version", "detected", "stored", "raw", "warnings"}
    assert body["version"] == "v4"
    assert body["detected"] == 2
    assert len(body["stored"]) == 2
    by_content = {item["content"]: item for item in body["stored"]}
    assert by_content["必考公式"]["level"] == "explicit"
    assert by_content["必考公式"]["confirmed"] is True
    assert by_content["必考公式"]["source"] == "lecture"
    assert by_content["重要概念"]["level"] == "emphasis"
    assert by_content["重要概念"]["confirmed"] is False
    assert FAKE_SECRET not in response.text

    # 强调不是确认；人工确认后才进入 confirmed 集合。
    confirmed = http_client.get(f"{ROUTE}/{sid}/exam-points", params={"confirmed_only": "true"})
    assert confirmed.status_code == 200
    assert {item["content"] for item in confirmed.json()["points"]} == {"必考公式"}
    emphasis_id = by_content["重要概念"]["id"]
    confirm = http_client.post(f"{ROUTE}/{sid}/exam-points/{emphasis_id}/confirm")
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["point"]["confirmed"] is True
    confirmed = http_client.get(f"{ROUTE}/{sid}/exam-points", params={"confirmed_only": "true"})
    assert {item["content"] for item in confirmed.json()["points"]} == {"必考公式", "重要概念"}


@pytest.mark.parametrize(
    "raw",
    [
        "{bad json",
        _points_json(
            {
                "content": "合法候选",
                "level": "explicit",
                "evidence": "这一段是必考内容",
                "kp": "公式",
            },
            {
                "content": "伪造引用",
                "level": "explicit",
                "evidence": "原文里没有这句",
                "kp": "公式",
            },
        ),
        _points_json(
            {
                "content": "非法级别",
                "level": "must",
                "evidence": "这一段是必考内容",
                "kp": "公式",
            }
        ),
    ],
)
def test_h4_malformed_detection_is_atomic_and_keeps_old_points(
    http_client: TestClient, p1_llm, raw: str
) -> None:
    subject = _create(http_client, "失败考点科目")
    sid = subject["id"]
    transcript = "这一段是必考内容。"
    p1_llm.response = _points_json(
        {
            "content": "旧考点",
            "level": "explicit",
            "evidence": "这一段是必考内容",
            "kp": "公式",
        }
    )
    seeded = _detect(http_client, sid, transcript)
    assert seeded.status_code == 200, seeded.text
    from deeptutor.subjects.store import subject_dir

    path = subject_dir(sid) / "exam_points.json"
    before = path.read_bytes() if path.exists() else None
    p1_llm.response = raw
    failed = _detect(http_client, sid, transcript)
    assert failed.status_code == 502, failed.text
    assert failed.json()["error"]["code"] == "invalid_model_output"
    after = path.read_bytes() if path.exists() else None
    assert after == before


# ---------------------------------------------------------------------------
# H5 — 复习包 + 真实报告
# ---------------------------------------------------------------------------
def _review_pack(client: TestClient, sid: str, format_: str, p1_llm, marker: str):
    p1_llm.response = (
        "# 期末复习指南\n\n## 一、期末考点速览\n"
        f"- 必考公式（标记 {marker}）\n\n"
        "## 二、错题回顾与易错点\n- 导数题：注意符号。\n\n"
        "## 三、复习建议\n- 先复习公式。\n"
    )
    p1_llm.finish_reason = "stop"
    point = client.post(
        f"{ROUTE}/{sid}/exam-points",
        data={
            "content": f"必考公式 {marker}",
            "level": "explicit",
            "evidence": "必考",
            "kp": "公式",
            "term": "2026春",
            "confirmed": "true",
        },
    )
    assert point.status_code == 200, point.text
    response = client.post(
        f"{ROUTE}/{sid}/review-pack", data={"format": format_, "term": "2026春"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_h5_review_pack_downloads_real_pdf_and_docx(http_client: TestClient, p1_llm) -> None:
    subject = _create(http_client, "复习科目")
    sid = subject["id"]
    pdf = _review_pack(http_client, sid, "pdf", p1_llm, "S14-REVIEW-PDF-37c1")
    assert pdf["format"] == "pdf" and pdf["status"] == "completed"
    assert pdf["url"].startswith(f"{OUTPUTS}/subjects/{sid}/")
    assert pdf["markdown_tokens"] > 0
    downloaded = http_client.get(pdf["url"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.startswith(b"%PDF")
    import pymupdf

    with pymupdf.open(stream=downloaded.content, filetype="pdf") as document:
        assert document.page_count >= 1
        text = "".join(page.get_text() for page in document)
    assert "S14-REVIEW-PDF-37c1" in text

    docx = _review_pack(http_client, sid, "docx", p1_llm, "S14-REVIEW-DOCX-6af2")
    assert docx["status"] == "completed"
    downloaded_docx = http_client.get(docx["url"])
    assert downloaded_docx.status_code == 200, downloaded_docx.text
    with zipfile.ZipFile(io.BytesIO(downloaded_docx.content)) as archive:
        assert "word/document.xml" in archive.namelist()
        assert archive.testzip() is None
    from docx import Document

    document = Document(io.BytesIO(downloaded_docx.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "S14-REVIEW-DOCX-6af2" in text


def _real_report_llm(body: str, chart_code: str | None = None):
    async def fake(prompt: str, system: str) -> str:
        if "## 报告题目" in prompt:
            return body
        if chart_code is None:
            raise AssertionError("unexpected chart request")
        return json.dumps({"code": chart_code}, ensure_ascii=False)

    return fake


_CHART_CODE = '''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.figure(figsize=(4.2, 3.0))
plt.bar(["甲", "乙", "丙"], [1, 3, 2])
plt.title("S14 中文图表")
plt.tight_layout()
plt.savefig("chart_1.png", dpi=80)
'''


def _report_tree(subject_id: str, report_id: str) -> Path:
    return (
        store.current_subject_paths().get_public_outputs_root()
        / "subjects"
        / subject_id
        / "reports"
        / report_id
    )


def test_h5_report_uses_real_bwrap_matplotlib_and_typst_then_outputs_download(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = _create(http_client, "报告科目")
    sid = subject["id"]
    body = "# S14 中文报告\n\n这是一份真实 Typst 报告。\n\n{CHART:中文柱状图}\n"
    monkeypatch.setattr(report_mod, "_llm", _real_report_llm(body, _CHART_CODE))

    response = http_client.post(
        f"{ROUTE}/{sid}/report",
        data={"title": "S14 真实报告", "requirements": "包含中文图表"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert re.fullmatch(r"[a-f0-9]{32}", result["report_id"])
    assert result["status"] == "completed"
    assert result["chart_count"] == 1
    assert result["verification_status"] == "not_requested"
    assert result["url"] == (
        f"{OUTPUTS}/subjects/{sid}/reports/{result['report_id']}/report.pdf"
    )
    assert result["path"] == f"subjects/{sid}/reports/{result['report_id']}/report.pdf"

    manifest = report_store.read_published_manifest(sid, result["report_id"])
    assert manifest is not None and manifest.status == "completed"
    assert manifest.report_id == result["report_id"]
    assert manifest.subject_id == sid
    assert manifest.verification_status == result["verification_status"]
    tree = _report_tree(sid, result["report_id"])
    by_name = {entry.path: entry for entry in manifest.files}
    assert set(by_name) == {"report.md", "report.pdf", "chart_1.png"}
    for name, entry in by_name.items():
        data = (tree / name).read_bytes()
        assert len(data) == entry.size
        assert hashlib.sha256(data).hexdigest() == entry.sha256
    assert (tree / "report.md").read_text(encoding="utf-8") == body.replace(
        "{CHART:中文柱状图}", "![chart 1](chart_1.png)"
    ).strip()
    assert report_store.active_report_runs() == ()

    pdf_download = http_client.get(result["url"])
    assert pdf_download.status_code == 200, pdf_download.text
    assert pdf_download.content.startswith(b"%PDF")
    assert hashlib.sha256(pdf_download.content).hexdigest() == by_name["report.pdf"].sha256
    import pymupdf

    with pymupdf.open(stream=pdf_download.content, filetype="pdf") as document:
        assert document.page_count >= 1
        assert any(page.get_images() for page in document)

    chart_download = http_client.get(
        f"{OUTPUTS}/subjects/{sid}/reports/{result['report_id']}/chart_1.png"
    )
    assert chart_download.status_code == 200, chart_download.text
    from PIL import Image

    with Image.open(io.BytesIO(chart_download.content)) as image:
        assert image.format == "PNG"
        assert image.width >= 200 and image.height >= 150
        image.verify()
    assert b"fake" not in chart_download.content.lower()


@pytest.mark.parametrize(
    "chart_reply",
    ['{"code": [1, 2]}', json.dumps({"code": "raise RuntimeError('s14-chart-failure')"})],
    ids=["invalid-model-code", "executor-failure"],
)
def test_h5_report_failure_has_no_url_and_never_touches_completed_report(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch, chart_reply: str
) -> None:
    subject = _create(http_client, "报告失败科目")
    sid = subject["id"]
    body_ok = "# 旧报告\n\n纯正文。\n"
    monkeypatch.setattr(report_mod, "_llm", _real_report_llm(body_ok))
    first = http_client.post(
        f"{ROUTE}/{sid}/report", data={"title": "旧报告", "requirements": "正文"}
    )
    assert first.status_code == 200, first.text
    first_result = first.json()
    old_tree = _report_tree(sid, first_result["report_id"])
    before = _tree(old_tree)
    public_before = sorted(path.name for path in old_tree.parent.iterdir() if path.is_dir())

    bad_body = "# 新报告\n\n{CHART:坏图}\n"
    monkeypatch.setattr(report_mod, "_llm", _real_report_llm(bad_body, chart_reply))
    failed = http_client.post(
        f"{ROUTE}/{sid}/report", data={"title": "新报告", "requirements": "坏图"}
    )
    assert failed.status_code >= 400, failed.text
    assert failed.json()["error"]["code"] == "chart_failed"
    assert "url" not in failed.text
    assert _tree(old_tree) == before
    assert sorted(path.name for path in old_tree.parent.iterdir() if path.is_dir()) == public_before
    assert report_store.active_report_runs() == ()
    assert report_store.resolve_report_for_review(sid).report_id == first_result["report_id"]


# ---------------------------------------------------------------------------
# H6 — 导出 ZIP、排除项、symlink 拒绝、删除互斥与 A/B 隔离
# ---------------------------------------------------------------------------
def _export_members(payload: bytes) -> tuple[zipfile.ZipFile, dict]:
    archive = zipfile.ZipFile(io.BytesIO(payload))
    assert archive.testzip() is None
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    return archive, manifest


def test_h6_export_downloads_verified_zip_and_excludes_private_or_transient(
    http_client: TestClient, p1_llm
) -> None:
    a = _create(http_client, "导出科目 A")
    b = _create(http_client, "导出科目 B")
    sid = a["id"]
    # 真实复习包产物是 artifacts/ 的可核对输入。
    pdf = _review_pack(http_client, sid, "pdf", p1_llm, "S14-EXPORT-ARTIFACT-44d0")
    assert http_client.get(pdf["url"]).status_code == 200

    root = store.subject_dir(sid)
    (root / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
    (root / "chat_history.json").write_text('{"private": "chat"}', encoding="utf-8")
    (root / "settings.json").write_text('{"api_key": "sk-never-export"}', encoding="utf-8")
    (root / "_report_runs" / "run-private").mkdir(parents=True, exist_ok=True)
    (root / "_report_runs" / "run-private" / "diagnostic.log").write_text(
        "private", encoding="utf-8"
    )
    (root / "materials" / "lecture" / ".hidden").write_text("hidden", encoding="utf-8")
    (root / "materials" / "lecture" / "scratch.tmp").write_text("tmp", encoding="utf-8")
    (root / "materials" / "lecture" / "old.lock").write_text("lock", encoding="utf-8")
    (root / "materials" / "lecture" / "export-note.txt").write_text(
        "exported material", encoding="utf-8"
    )
    public = store.current_subject_paths().get_public_outputs_root() / "subjects" / sid
    public.mkdir(parents=True, exist_ok=True)
    (public / "subject-export-deadbeef.zip").write_bytes(b"PK-old")
    (public / "subject-backup-123.zip").write_bytes(b"PK-backup")

    response = http_client.get(f"{ROUTE}/{sid}/export")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == 1
    assert re.fullmatch(r"[a-f0-9]{32}", body["export_id"])
    assert body["url"].startswith(f"{OUTPUTS}/subjects/{sid}/subject-export-")
    assert body["path"] == f"subjects/{sid}/{Path(body['url']).name}"

    download = http_client.get(body["url"])
    assert download.status_code == 200, download.text
    assert download.content[:2] == b"PK" and len(download.content) == body["size"]
    archive, manifest = _export_members(download.content)
    try:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert manifest["schema_version"] == 1
        assert manifest["export_id"] == body["export_id"]
        assert manifest["subject"]["id"] == sid
        assert set(manifest) >= {
            "schema_version",
            "export_id",
            "subject",
            "files",
            "exclusions",
        }
        expected = {item["path"]: item for item in manifest["files"]}
        assert set(names) - {"manifest.json"} == set(expected)
        for name, entry in expected.items():
            assert not name.startswith("/") and ".." not in Path(name).parts
            assert "\\" not in name
            data = archive.read(name)
            assert len(data) == entry["size"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert "subject.json" in expected
        subject_json = json.loads(archive.read("subject.json"))
        assert subject_json["id"] == sid
        assert json.loads(archive.read("manifest.json")) == manifest
        exclusions = "\n".join(manifest["exclusions"])
        assert "chat_history" in exclusions
        assert "settings" in exclusions
        assert "private_runs" in exclusions
        forbidden = (
            "chat_history.json",
            "settings.json",
            "_report_runs",
            ".hidden",
            "scratch.tmp",
            "old.lock",
            "subject-export-deadbeef.zip",
            "subject-backup-123.zip",
        )
        assert not any(any(token in name for token in forbidden) for name in names)
        assert any(name.startswith("learning/materials/") for name in names)
        assert any(name.startswith("artifacts/review-guide-") for name in names)
    finally:
        archive.close()


def test_h6_export_refuses_symlink_without_url(http_client: TestClient) -> None:
    subject = _create(http_client, "导出软链科目")
    sid = subject["id"]
    root = store.subject_dir(sid)
    outside = root.parent / "outside-export.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
    (root / "materials" / "lecture" / "linked.txt").symlink_to(outside)

    response = http_client.get(f"{ROUTE}/{sid}/export")
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] in {"storage_io", "storage_corrupt"}
    assert "url" not in response.text
    assert outside.read_text(encoding="utf-8") == "outside"
    assert not list(
        (store.current_subject_paths().get_public_outputs_root() / "subjects" / sid).glob(
            "subject-export-*.zip"
        )
    )


def test_h6_delete_a_removes_only_a_and_preserves_b_and_global(http_client: TestClient) -> None:
    a = _create(http_client, "删除科目 A")
    b = _create(http_client, "删除科目 B")
    sid_a, sid_b = a["id"], b["id"]
    (store.subject_dir(sid_a) / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
    (store.subject_dir(sid_b) / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
    (store.subject_dir(sid_a) / "materials" / "lecture" / "a.txt").write_text(
        "A unique", encoding="utf-8"
    )
    (store.subject_dir(sid_b) / "materials" / "lecture" / "b.txt").write_text(
        "B unique", encoding="utf-8"
    )
    outputs_a = store.current_subject_paths().get_public_outputs_root() / "subjects" / sid_a
    outputs_a.mkdir(parents=True, exist_ok=True)
    (outputs_a / "artifact.txt").write_text("A artifact", encoding="utf-8")
    global_dir = store.current_subject_paths().get_knowledge_bases_root()
    global_dir.mkdir(parents=True, exist_ok=True)
    (global_dir / "global-marker.txt").write_text("global", encoding="utf-8")

    subject_a_root = store.subject_dir(sid_a)
    before_b = _tree(store.subject_dir(sid_b))
    before_global = _tree(global_dir)

    deleted = http_client.delete(f"{ROUTE}/{sid_a}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "deleted", "subject_id": sid_a}
    after = http_client.get(f"{ROUTE}/{sid_a}/knowledge")
    assert after.status_code == 404, after.text
    assert after.json()["error"]["code"] == "subject_not_found"
    assert not subject_a_root.exists()
    assert not outputs_a.exists()
    assert _tree(store.subject_dir(sid_b)) == before_b
    assert _tree(global_dir) == before_global
    assert sid_b in {item["id"] for item in http_client.get(ROUTE).json()["subjects"]}


def test_h6_delete_is_409_while_export_is_active_and_succeeds_after_release(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _create(http_client, "互斥删除科目")
    sid = a["id"]
    root = store.subject_dir(sid)
    (root / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
    (root / "materials" / "lecture" / "keep.txt").write_text("keep", encoding="utf-8")
    entered, release = threading.Event(), threading.Event()
    original = export_bundle._zip_content

    def blocking(content: Path, zip_path: Path) -> None:
        entered.set()
        assert release.wait(10)
        original(content, zip_path)

    monkeypatch.setattr(export_bundle, "_zip_content", blocking)

    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            export_task = asyncio.create_task(client.get(f"{ROUTE}/{sid}/export"))
            try:
                assert await asyncio.to_thread(entered.wait, 10)
                busy = await client.delete(f"{ROUTE}/{sid}")
                assert busy.status_code == 409, busy.text
                assert busy.json()["error"]["code"] in {"kb_busy", "subject_busy"}
                assert root.is_dir()
                assert (root / "materials" / "lecture" / "keep.txt").read_text() == "keep"
                assert store.get_subject(sid) is not None
            finally:
                release.set()
            exported = await asyncio.wait_for(export_task, timeout=30)
            assert exported.status_code == 200, exported.text
            deleted = await client.delete(f"{ROUTE}/{sid}")
            assert deleted.status_code == 200, deleted.text
            assert not root.exists()

    asyncio.run(scenario())

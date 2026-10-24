"""P1-18 行为测试：同名替换、manifest 与提交边界（C07/C01）。

目标：同名重传必须让 ``materials/<type>`` 与 KB 的 ``raw`` 同时更新且摘要一致，
不一致时先失败；普通异常整批回滚且不排索引；坏 manifest 不被覆盖。

必证场景（对应卡内清单）：

* ``same.txt`` 重传后两处 hash 都是 new，manifest 摘要同步更新；
* 第二处 replace 故障 → 旧一致对被保留、队列为空（有效坏对照）；
* 预置缺失/多余/hash 差异 → 409 ``material_out_of_sync`` 且不调用索引；
* 同 KB 并发重传不会产生 materials/raw 混合对，也不会重复排任务；
* 其他科目同名 KB 与 global 完全不变；
* 无 manifest 的合法旧库只读、不写；成功上传才建立 manifest；
* 首传失败不留幽灵 record/ready/task；staging/backup 不在 ``raw`` 内。
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
from pathlib import Path

import pytest

from deeptutor.api.utils.task_id_manager import TaskIDManager
from deeptutor.subjects import json_store, material_manifest, store, uploads
from tests.phase1 import helpers

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX
KB_NAME = "assignment-kb"
FAKE_MARKER = "p1-18-FAKE-METADATA-MARKER-9c3f21-DO-NOT-LEAK"


class _QueueRecorder:
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


class _FakeUpload:
    """最小 UploadFile 替身：只需要 ``filename`` 与异步 ``read``。"""

    def __init__(self, name: str, body: bytes) -> None:
        self.filename = name
        self._buffer = io.BytesIO(body)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


@pytest.fixture(autouse=True)
def _isolated_upload_registry():
    """隔离 subject 预留表与 TaskIDManager（R4 会观察任务终态）。"""
    uploads.reset_registry_for_tests()
    manager = TaskIDManager.get_instance()
    saved_ids = dict(manager._task_ids)
    saved_meta = {key: dict(value) for key, value in manager._task_metadata.items()}
    try:
        yield
    finally:
        uploads.reset_registry_for_tests()
        manager._task_ids.clear()
        manager._task_ids.update(saved_ids)
        manager._task_metadata.clear()
        manager._task_metadata.update(saved_meta)


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


def _kb_dir(subject, kb_name: str = KB_NAME) -> Path:
    return Path(subject.knowledge_bases) / kb_name


def _raw(subject, kb_name: str = KB_NAME) -> Path:
    return _kb_dir(subject, kb_name) / "raw"


def _materials(subject, kb_type: str = "assignment") -> Path:
    return Path(subject.materials) / kb_type


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_without_locks(root: Path) -> dict:
    """目录摘要，忽略 ``.deeptutor.lock``（KB 事务锁文件，不是资料残留）。"""
    return {
        key: value
        for key, value in helpers.tree_digest(root).items()
        if not key.endswith(json_store.LOCK_FILE_NAME)
    }


def _release(subject, kb_name: str = KB_NAME) -> None:
    """模拟"后台任务已结束"：清掉排队预留，允许下一批同库上传。"""
    assert uploads.clear_reservation(_kb_dir(subject, kb_name), task_id=None) in (True, False)
    uploads.reset_registry_for_tests()


def _upload_ok(client, subject, specs, *, type: str = "auto") -> dict:
    response = _upload(client, subject.subject_id, specs, type=type)
    assert response.status_code == 200, response.text
    return response.json()


def _mismatch_409(client, subject, specs):
    response = _upload(client, subject.subject_id, specs)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "material_out_of_sync"
    assert response.json()["error"]["retryable"] is True
    return response


# ---------------------------------------------------------------------------
# 同名替换：两处 + manifest
# ---------------------------------------------------------------------------
def test_same_name_reupload_updates_both_copies_and_the_manifest(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    old = b"old lecture notes"
    new = b"new lecture notes with more detail"

    first = _upload_ok(p1_route_client, subject, [("same.txt", old, None)])
    _release(subject)
    before_manifest = json.loads(
        material_manifest.manifest_path(_kb_dir(subject)).read_text(encoding="utf-8")
    )
    assert before_manifest["files"] == [
        {"path": "same.txt", "size": len(old), "sha256": _sha256(old)}
    ]

    second = _upload_ok(p1_route_client, subject, [("same.txt", new, None)])
    assert second["files"] == ["same.txt"]
    assert second["documents"] == 1

    # 两处都必须换成新字节（"同名raw确实更新"的正面证据）
    assert (_materials(subject) / "same.txt").read_bytes() == new
    assert (_raw(subject) / "same.txt").read_bytes() == new
    assert _sha256((_raw(subject) / "same.txt").read_bytes()) == _sha256(new)
    assert _sha256(new) != _sha256(old)  # 坏对照：确实换了内容

    manifest = json.loads(
        material_manifest.manifest_path(_kb_dir(subject)).read_text(encoding="utf-8")
    )
    assert manifest["files"] == [
        {"path": "same.txt", "size": len(new), "sha256": _sha256(new)}
    ]
    assert manifest["subject_id"] == subject.subject_id
    assert manifest["kb_name"] == KB_NAME

    records = store.load_knowledge_records(subject.subject_id)
    assert len(records) == 1 and records[0]["documents"] == 1

    # 第二次是重建而不是新建，并且确实排了队
    assert [call["runner"] for call in queued.calls] == [
        "run_initialization_task",
        "run_reindex_task",
    ]
    assert queued.calls[-1]["task_id"] == second["task_id"]


def test_manifest_and_backups_live_outside_the_index_source(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("same.txt", b"data", None)])

    raw = _raw(subject)
    assert sorted(entry.name for entry in raw.iterdir()) == ["same.txt"]
    assert not (raw / material_manifest.MANIFEST_NAME).exists()
    assert material_manifest.manifest_path(_kb_dir(subject)).parent == _kb_dir(subject)
    leftovers = [
        path.relative_to(_kb_dir(subject)).as_posix()
        for path in _kb_dir(subject).rglob("*")
        if (path.name.startswith(".") and path.name != json_store.LOCK_FILE_NAME)
        or path.name.endswith(uploads.PART_SUFFIX)
    ]
    assert leftovers == []
    assert not (Path(subject.root) / uploads.STAGING_DIR_NAME).exists() or not any(
        (Path(subject.root) / uploads.STAGING_DIR_NAME).iterdir()
    )


def test_second_replace_failure_keeps_the_old_pair_and_queues_nothing(
    p1_subjects, p1_route_client, queued, monkeypatch
):
    subject = p1_subjects["科目A"]
    old = b"old bytes"
    new = b"new bytes"
    _upload_ok(p1_route_client, subject, [("same.txt", old, None)])
    _release(subject)
    raw_target = _raw(subject) / "same.txt"
    manifest_before = material_manifest.manifest_path(_kb_dir(subject)).read_bytes()

    real_copy = uploads._atomic_copy

    def _fail_on_raw_publish(source, target):
        if Path(target) == raw_target:
            raise json_store.StorageIOError(
                "injected failure while publishing the index source",
                path=raw_target.name,
            )
        return real_copy(source, target)

    monkeypatch.setattr(uploads, "_atomic_copy", _fail_on_raw_publish)
    queued.calls.clear()

    response = _upload(p1_route_client, subject.subject_id, [("same.txt", new, None)])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_io"

    # 回滚成"旧的一致对"：两处仍是 old，manifest 与队列都没变
    assert (_materials(subject) / "same.txt").read_bytes() == old
    assert raw_target.read_bytes() == old
    assert material_manifest.manifest_path(_kb_dir(subject)).read_bytes() == manifest_before
    assert queued.calls == []
    assert uploads.reservation_for(_kb_dir(subject)) is None
    assert not any(path.name.endswith(uploads.PART_SUFFIX) for path in _raw(subject).iterdir())


# ---------------------------------------------------------------------------
# 一致性门：预置差异先 409
# ---------------------------------------------------------------------------
def test_preexisting_source_mismatches_return_409_before_indexing(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("same.txt", b"original", None)])
    _release(subject)
    queued.calls.clear()
    raw = _raw(subject)
    materials = _materials(subject)
    manifest_file = material_manifest.manifest_path(_kb_dir(subject))
    before_raw = (raw / "same.txt").read_bytes()
    before_materials = (materials / "same.txt").read_bytes()

    # 1) raw 里多出一个文件
    (raw / "extra.txt").write_bytes(b"extra")
    _mismatch_409(p1_route_client, subject, [("other.txt", b"payload", None)])
    assert not (materials / "other.txt").exists()

    # 2) raw 里缺少 manifest 记录的文件
    (raw / "extra.txt").unlink()
    (raw / "same.txt").unlink()
    _mismatch_409(p1_route_client, subject, [("other.txt", b"payload", None)])

    # 3) raw 内容变了（size/hash 与 manifest 不符）
    (raw / "same.txt").write_bytes(b"tampered with different length")
    _mismatch_409(p1_route_client, subject, [("other.txt", b"payload", None)])

    # 4) materials（权威资料）与 raw 不一致
    (raw / "same.txt").write_bytes(before_raw)
    (materials / "same.txt").write_bytes(b"authoritative copy changed")
    _mismatch_409(p1_route_client, subject, [("other.txt", b"payload", None)])

    assert queued.calls == []
    assert uploads.reservation_for(_kb_dir(subject)) is None
    assert json.loads(manifest_file.read_text(encoding="utf-8"))["files"][0]["size"] == len(
        b"original"
    )
    # 差异不会被"顺手上传"掩盖，也不会静默取旧 raw
    assert (materials / "same.txt").read_bytes() == b"authoritative copy changed"
    assert (raw / "same.txt").read_bytes() == before_raw
    assert before_materials == b"original"


def test_a_corrupt_manifest_is_reported_and_never_overwritten(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    kb_dir = _kb_dir(subject)
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "raw").mkdir(exist_ok=True)
    bad = {
        "schema_version": 1,
        "subject_id": "some-other-subject",
        "kb_name": KB_NAME,
        "files": [],
    }
    manifest_file = material_manifest.manifest_path(kb_dir)
    manifest_file.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    before = manifest_file.read_bytes()

    response = _upload(p1_route_client, subject.subject_id, [("new.txt", b"data", None)])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert manifest_file.read_bytes() == before
    assert not (kb_dir / "raw" / "new.txt").exists()
    assert queued.calls == []


def test_a_schema_invalid_manifest_is_corrupt(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    kb_dir = _kb_dir(subject)
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "raw").mkdir(exist_ok=True)
    manifest_file = material_manifest.manifest_path(kb_dir)
    manifest_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "subject_id": subject.subject_id,
                "kb_name": KB_NAME,
                "files": [{"path": "../escape.txt", "size": 1, "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )
    before = manifest_file.read_bytes()
    response = _upload(p1_route_client, subject.subject_id, [("new.txt", b"data", None)])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert manifest_file.read_bytes() == before


# ---------------------------------------------------------------------------
# 旧库：只读、不迁移
# ---------------------------------------------------------------------------
def test_a_legacy_library_is_read_only_until_the_first_successful_upload(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    kb_dir = _kb_dir(subject)
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = _materials(subject)
    materials.mkdir(parents=True, exist_ok=True)
    legacy = b"legacy material"
    (raw / "legacy.txt").write_bytes(legacy)
    (materials / "legacy.txt").write_bytes(legacy)
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": KB_NAME, "kb_id": "legacy-kb-id", "type": "assignment", "documents": 0},
    )
    manifest_file = material_manifest.manifest_path(kb_dir)
    assert not manifest_file.exists()

    listing = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert listing.status_code == 200, listing.text
    entry = listing.json()["knowledge"][0]
    assert entry["documents"] == 1
    # GET 只读：不建立 manifest、不写任何字节
    assert not manifest_file.exists()
    assert (raw / "legacy.txt").read_bytes() == legacy

    payload = _upload_ok(p1_route_client, subject, [("added.txt", b"added", None)])
    assert payload["documents"] == 2
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert [item["path"] for item in manifest["files"]] == ["added.txt", "legacy.txt"]
    assert (_raw(subject) / "legacy.txt").read_bytes() == legacy


def test_legacy_library_mismatch_is_refused_before_adopting_it(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    kb_dir = _kb_dir(subject)
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = _materials(subject)
    materials.mkdir(parents=True, exist_ok=True)
    # raw 里有一份材料，但权威副本里没有它 → 旧库本身就不一致
    (raw / "orphan.txt").write_bytes(b"orphan")
    before = _tree_without_locks(subject.root)

    _mismatch_409(p1_route_client, subject, [("new.txt", b"data", None)])
    assert _tree_without_locks(subject.root) == before
    assert not material_manifest.manifest_path(kb_dir).exists()


# ---------------------------------------------------------------------------
# 首传失败：无幽灵 record / KB / task
# ---------------------------------------------------------------------------
def test_first_upload_failure_leaves_no_ghost_record_or_task(
    p1_subjects, p1_route_client, queued, monkeypatch
):
    subject = p1_subjects["科目A"]
    before_index = (
        (store.subjects_root() / "index.json").read_bytes()
        if (store.subjects_root() / "index.json").exists()
        else b""
    )
    original = material_manifest.save_manifest

    def _fail_manifest(kb_dir, manifest):
        raise json_store.StorageIOError("injected manifest failure", path="subject_sources.json")

    monkeypatch.setattr(material_manifest, "save_manifest", _fail_manifest)
    response = _upload(p1_route_client, subject.subject_id, [("new.txt", b"data", None)])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_io"
    monkeypatch.setattr(material_manifest, "save_manifest", original)

    assert store.load_knowledge_records(subject.subject_id) == []
    assert not _kb_dir(subject).exists()
    assert not (_materials(subject) / "new.txt").exists()
    assert queued.calls == []
    assert uploads.reservation_for(_kb_dir(subject)) is None
    after_index = (
        (store.subjects_root() / "index.json").read_bytes()
        if (store.subjects_root() / "index.json").exists()
        else b""
    )
    assert after_index == before_index


# ---------------------------------------------------------------------------
# 并发与跨库隔离
# ---------------------------------------------------------------------------
def test_concurrent_same_kb_commits_never_mix_the_pair(p1_subjects):
    import asyncio

    subject = p1_subjects["科目A"]

    def _commit(body: bytes, name: str):
        plan = uploads.plan_batch([_FakeUpload("same.txt", body)], type="auto")
        with uploads.staging_root(subject.subject_id) as staging:
            staged = asyncio.run(uploads.stage_files(plan, staging))
            return uploads.commit_documents(
                subject_id=subject.subject_id,
                plan=plan,
                staged=staged,
                staging_dir=staging,
                task_id=f"task-{name}",
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_commit, body, name) for body, name in
                   ((b"A" * 128, "alpha"), (b"B" * 256, "beta"))]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("ok", future.result()))
            except Exception as exc:  # noqa: BLE001 - the loser must be a typed 409
                outcomes.append(("err", exc))

    winners = [value for kind, value in outcomes if kind == "ok"]
    losers = [value for kind, value in outcomes if kind == "err"]
    assert len(winners) == 1 and len(losers) == 1
    assert getattr(losers[0], "code", None) is not None
    assert losers[0].code.value == "kb_busy"

    materials_bytes = (_materials(subject) / "same.txt").read_bytes()
    raw_bytes = (_raw(subject) / "same.txt").read_bytes()
    manifest = json.loads(
        material_manifest.manifest_path(_kb_dir(subject)).read_text(encoding="utf-8")
    )
    # 没有混合对：两处字节一致，且与 manifest 的 size/hash 完全对应
    assert materials_bytes == raw_bytes
    assert manifest["files"] == [
        {"path": "same.txt", "size": len(raw_bytes), "sha256": _sha256(raw_bytes)}
    ]
    assert len(uploads.reservation_for(_kb_dir(subject))["task_id"]) > 0


def test_other_subjects_and_the_global_library_are_untouched(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    other = p1_subjects["科目B"]
    global_kb = p1_subjects["global"]
    before_other = helpers.tree_digest(other.root)
    before_global = helpers.tree_digest(global_kb)
    markers_other = helpers.kb_markers(other.knowledge_bases / "shared-kb")
    markers_global = helpers.kb_markers(global_kb)

    _upload_ok(p1_route_client, subject, [("same.txt", b"A only", None)])

    assert helpers.tree_digest(other.root) == before_other
    assert helpers.tree_digest(global_kb) == before_global
    assert helpers.kb_markers(other.knowledge_bases / "shared-kb") == markers_other
    assert helpers.kb_markers(global_kb) == markers_global
    assert not (other.knowledge_bases / "shared-kb" / "subject_sources.json").exists()


def test_two_different_kbs_of_one_subject_do_not_block_each_other(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("notes.txt", b"n", None)])
    assert first["kb_name"] == "assignment-kb"
    # assignment-kb 仍在排队中，但另一个 KB 是独立的
    second = _upload_ok(
        p1_route_client, subject, [("book.pdf", b"%PDF-1.4", None)], type="textbook"
    )
    assert second["kb_name"] == "textbook-kb"
    assert len(queued.calls) == 2
    assert (Path(subject.materials) / "textbook" / "book.pdf").is_file()
    assert (Path(subject.materials) / "assignment" / "notes.txt").is_file()
    assert uploads.reservation_for(_kb_dir(subject, "textbook-kb")) is not None


# ---------------------------------------------------------------------------
# R2（rework01）：同名同大小也要按内容区分；权威资料缺失/多余必须拦住
# ---------------------------------------------------------------------------
def test_same_size_content_change_is_a_mismatch(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("same.txt", b"old", None)])
    _release(subject)
    raw_target = _raw(subject) / "same.txt"
    assert len(b"old") == len(b"bad")
    raw_target.write_bytes(b"bad")  # 同路径、同大小、不同内容
    before = helpers.tree_digest(subject.root)
    queued.calls.clear()

    _mismatch_409(p1_route_client, subject, [("other.txt", b"payload", None)])
    assert helpers.tree_digest(subject.root) == before
    assert queued.calls == []


def test_extra_indexable_material_cannot_be_silently_omitted(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _release(subject)
    (Path(_materials(subject)) / "lost.txt").write_bytes(b"authoritative-only")
    before = helpers.tree_digest(subject.root)
    queued.calls.clear()

    _mismatch_409(p1_route_client, subject, [("two.txt", b"two", None)])
    assert helpers.tree_digest(subject.root) == before
    assert queued.calls == []
    # 非索引辅助文件/隐藏文件不算"多余的可索引材料"
    (Path(_materials(subject)) / "lost.txt").unlink()
    (Path(_materials(subject)) / ".hidden.txt").write_bytes(b"hidden")
    (Path(_materials(subject)) / "notes.bak").write_bytes(b"backup")
    response = _upload(p1_route_client, subject.subject_id, [("two.txt", b"two", None)])
    assert response.status_code == 200, response.text


def test_a_missing_materials_directory_is_out_of_sync(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _release(subject)
    import shutil

    shutil.rmtree(_materials(subject))
    queued.calls.clear()
    _mismatch_409(p1_route_client, subject, [("two.txt", b"two", None)])
    assert queued.calls == []
    # 权威资料目录没有被"顺手"建好，也没有发布任何新资料
    assert not any(_materials(subject).iterdir())


def test_an_empty_legacy_library_is_still_allowed_to_upload(
    p1_subjects, p1_route_client, queued
):
    """正对照：真正全新/空库没有权威资料可比，首次上传仍然合法。"""
    subject = p1_subjects["科目A"]
    assert not Path(_materials(subject)).exists()
    assert _upload_ok(p1_route_client, subject, [("first.txt", b"first", None)])["documents"] == 1


# ---------------------------------------------------------------------------
# R3（rework01）：replace 之后的校验失败也要回滚
# ---------------------------------------------------------------------------
def test_digest_failure_after_replace_restores_the_pair(
    p1_subjects, p1_route_client, queued, monkeypatch
):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    _release(subject)
    before = helpers.tree_digest(subject.root)
    queued.calls.clear()
    real = uploads._digest_of
    material_target = _materials(subject) / "one.txt"

    def fail(path):
        if Path(path) == material_target:
            raise OSError("injected digest failure")
        return real(path)

    monkeypatch.setattr(uploads, "_digest_of", fail)
    response = _upload(p1_route_client, subject.subject_id, [("one.txt", b"new", None)])
    assert response.status_code == 500, response.text
    assert material_target.read_bytes() == b"old", "校验失败后新资料仍留在磁盘上"
    assert (_raw(subject) / "one.txt").read_bytes() == b"old"
    assert helpers.tree_digest(subject.root) == before
    assert queued.calls == []
    assert uploads.reservation_for(_kb_dir(subject)) is None


def test_existing_metadata_and_unknown_fields_survive(
    p1_subjects, p1_route_client, queued, monkeypatch
):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    _release(subject)
    meta = _kb_dir(subject) / "metadata.json"
    value = json.loads(meta.read_text(encoding="utf-8"))
    value["preserve_me"] = FAKE_MARKER
    meta.write_text(json.dumps(value), encoding="utf-8")
    before = meta.read_bytes()

    # 记录写入失败：metadata 必须逐字节恢复
    with monkeypatch.context() as patch:
        patch.setattr(
            store,
            "upsert_knowledge_record",
            lambda *a, **k: (_ for _ in ()).throw(
                json_store.StorageIOError("injected record failure")
            ),
        )
        response = _upload(p1_route_client, subject.subject_id, [("one.txt", b"new", None)])
    assert response.status_code == 500, response.text
    assert meta.read_bytes() == before, "既有 metadata 在回滚后没有恢复"

    # 成功路径也必须保留既有描述/未知字段
    ok = _upload(p1_route_client, subject.subject_id, [("one.txt", b"newer", None)])
    assert ok.status_code == 200, ok.text
    preserved = json.loads(meta.read_text(encoding="utf-8"))
    assert preserved["preserve_me"] == FAKE_MARKER
    assert preserved.get("name") == value.get("name")


# ---------------------------------------------------------------------------
# R4（rework01）：排队注册、任务身份与跨库回滚
# ---------------------------------------------------------------------------
def test_queue_registration_failure_restores_sources_and_reservation(
    p1_subjects, p1_route_client, monkeypatch
):
    from fastapi import BackgroundTasks

    subject = p1_subjects["科目A"]
    seed = _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    uploads.clear_reservation(_kb_dir(subject), task_id=seed["task_id"])
    before = helpers.tree_digest(subject.root)

    def _fail(self, func, *args, **kwargs):
        raise RuntimeError("injected queue failure")

    monkeypatch.setattr(BackgroundTasks, "add_task", _fail)
    response = _upload(p1_route_client, subject.subject_id, [("one.txt", b"new", None)])
    assert response.status_code == 500, response.text
    assert (_materials(subject) / "one.txt").read_bytes() == b"old", "没有任务却发布了新资料"
    assert (_raw(subject) / "one.txt").read_bytes() == b"old"
    assert uploads.busy_state(_kb_dir(subject))["busy"] is False
    assert helpers.tree_digest(subject.root) == before


def test_a_failed_upload_does_not_leave_a_running_task(p1_subjects, p1_route_client, queued, monkeypatch):
    subject = p1_subjects["科目A"]
    manager = TaskIDManager.get_instance()
    before = set(manager._task_metadata)

    def _fail(kb_dir, manifest):
        raise json_store.StorageIOError("injected manifest failure")

    monkeypatch.setattr(material_manifest, "save_manifest", _fail)
    response = _upload(p1_route_client, subject.subject_id, [("new.txt", b"data", None)])
    assert response.status_code == 500, response.text

    ghosts = {
        key: value.get("status")
        for key, value in manager._task_metadata.items()
        if key not in before and value.get("status") not in ("error", "cancelled")
    }
    assert ghosts == {}, f"失败上传留下了没有工作的任务: {ghosts}"


def test_a_failed_kb_cannot_undo_another_kbs_success(p1_subjects, p1_route_client, queued, monkeypatch):
    import concurrent.futures
    import contextvars
    import threading

    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    _release(subject)

    reached = threading.Event()
    release = threading.Event()
    original = store.upsert_knowledge_record

    def hook(subject_id, record):
        if subject_id == subject.subject_id and record["kb_name"] == KB_NAME:
            reached.set()
            if not release.wait(10):
                raise RuntimeError("probe release timeout")
            raise json_store.StorageIOError("injected A failure")
        return original(subject_id, record)

    def upload_a():
        with helpers.route_client() as client:
            return client.post(
                f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/upload",
                files=[("files", ("one.txt", b"new", "text/plain"))],
            )

    monkeypatch.setattr(store, "upsert_knowledge_record", hook)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(contextvars.copy_context().run, upload_a)
        try:
            assert reached.wait(5), "A 没有到达注入点"
            response_b = _upload(
                p1_route_client,
                subject.subject_id,
                [("book.pdf", b"%PDF-1.4", None)],
                type="textbook",
            )
            assert response_b.status_code == 200, response_b.text
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 500

    assert store.get_knowledge_record(subject.subject_id, "textbook-kb") is not None, (
        "A 的回滚删除了 B 的 knowledge 记录"
    )
    assert uploads.kb_config_entry(_kb_dir(subject).parent, "textbook-kb") is not None, (
        "A 的回滚删除了 B 的 kb_config 记录"
    )
    assert (Path(subject.materials) / "textbook" / "book.pdf").read_bytes() == b"%PDF-1.4"
    assert (_materials(subject) / "one.txt").read_bytes() == b"old"


@pytest.mark.parametrize('point', ['config', 'record'])
def test_metadata_failure_after_a_successful_write_restores_its_entry(
    p1_subjects, p1_route_client, queued, monkeypatch, point
):
    from deeptutor.knowledge.manager import KnowledgeBaseManager

    subject = p1_subjects['科目A']
    _upload_ok(p1_route_client, subject, [('one.txt', b'old', None)])
    _release(subject)
    before_config = uploads.kb_config_entry(subject.knowledge_bases, KB_NAME)
    before_record = store.get_knowledge_record(subject.subject_id, KB_NAME)
    if point == 'config':
        original = KnowledgeBaseManager.update_kb_status
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise json_store.StorageIOError('injected post-config failure')
        monkeypatch.setattr(KnowledgeBaseManager, 'update_kb_status', fail)
    else:
        original = store.upsert_knowledge_record
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise json_store.StorageIOError('injected post-record failure')
        monkeypatch.setattr(store, 'upsert_knowledge_record', fail)
    queued.calls.clear()
    response = _upload(p1_route_client, subject.subject_id, [('two.txt', b'two', None)])
    assert response.status_code == 500, response.text
    assert response.json()['error']['code'] == 'storage_io'
    assert uploads.kb_config_entry(subject.knowledge_bases, KB_NAME) == before_config
    assert store.get_knowledge_record(subject.subject_id, KB_NAME) == before_record
    assert not (_raw(subject) / 'two.txt').exists()
    assert not (_materials(subject) / 'two.txt').exists()
    assert queued.calls == []


@pytest.mark.parametrize('point', ['size_limit', 'task_stream'])
def test_precommit_failure_never_leaves_a_running_task(
    p1_subjects, p1_route_client, queued, monkeypatch, point
):
    from deeptutor.api.routers import subjects as routes
    from deeptutor.api.utils.task_id_manager import TaskIDManager

    subject = p1_subjects['科目A']
    manager = TaskIDManager.get_instance()
    before = set(manager._task_metadata)
    if point == 'size_limit':
        monkeypatch.setattr(uploads.DocumentValidator, 'MAX_FILE_SIZE', 1)
        expected = 400
    else:
        def fail_stream():
            raise json_store.StorageIOError('injected stream setup failure')
        monkeypatch.setattr(routes, 'get_task_stream_manager', fail_stream)
        expected = 500
    response = _upload(p1_route_client, subject.subject_id, [('one.txt', b'too large', None)])
    assert response.status_code == expected, response.text
    assert all(value['status'] in ('error', 'cancelled') for key, value in manager._task_metadata.items() if key not in before)
    assert store.get_knowledge_record(subject.subject_id, KB_NAME) is None
    assert queued.calls == []


def test_hidden_filename_in_raw_still_has_an_authoritative_copy(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects['科目A']
    _upload_ok(p1_route_client, subject, [('.notes.txt', b'content', None)])
    assert (_raw(subject) / '.notes.txt').read_bytes() == b'content'
    assert (_materials(subject) / '.notes.txt').read_bytes() == b'content'
    assert store.get_knowledge_record(subject.subject_id, KB_NAME)['documents'] == 1

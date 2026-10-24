"""P1-19 行为测试：科目 KB 计数与"当前索引源"状态（C07/C02）。

目标：``documents`` 按当前 ``raw`` 里真正可索引的普通源文件数计算（不是 chunk、
上传次数、manifest 条数或 stage 个数）；旧索引 ready 不能被当成"新资料已可查询"；
GET 只读且状态投影已净化。

必证场景（对应卡内清单）：

* 1 个源文件 → ``documents=1``；同名替换仍是 1；新增第 2 份 → 2 且 ``rebuilding``；
* 后台任务真正成功后才 ``ready``，失败可见；
* worker 线程还活着（即使任务状态已是 error）时重复请求 409；
* "已接受但 worker 尚未开始"的排队期同样 409；
* 其他科目同名 KB / global 不受影响；
* GET 不写任何字节，错误响应与 progress 里没有原始诊断/虚构标记；
* 保留 ``{knowledge:[{...record,status:{...}}]}`` 与
  ``{kb_name,status,progress,updated_at,...}`` 既有形状（可加 task_id/documents）；
* 兼容旧库，但源不一致时绝不标 ready。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from deeptutor.api.utils.task_id_manager import TaskIDManager
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_mod
from deeptutor.subjects import json_store, material_manifest, store, uploads
from tests.phase1 import helpers

#: 真实的后台包装器：``queued`` fixture 会把模块属性换成捕获队列，显式驱动必须用原件。
_REAL_RUN_RESERVED = uploads.run_reserved_index_task

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PREFIX = helpers.ROUTE_PREFIX
KB_NAME = "assignment-kb"
FAKE_MARKER = "p1-19-FAKE-PROGRESS-MARKER-77ac1e-DO-NOT-LEAK"


class _QueueRecorder:
    """捕获队列：证明"已排队"，不真的启动索引 worker。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, kb_dir, task_id, run, *args) -> None:
        self.calls.append({"kb_dir": str(kb_dir), "task_id": task_id, "args": args})


@pytest.fixture(autouse=True)
def _isolated_registries():
    """隔离 subject 预留表与 TaskIDManager（本文件新使用的 singleton）。"""
    manager = TaskIDManager.get_instance()
    saved_ids = dict(manager._task_ids)
    saved_meta = {key: dict(value) for key, value in manager._task_metadata.items()}
    uploads.reset_registry_for_tests()
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


def _tree_without_locks(root: Path) -> dict:
    return {
        key: value
        for key, value in helpers.tree_digest(root).items()
        if not key.endswith(json_store.LOCK_FILE_NAME)
    }


def _seed(client, subject) -> dict:
    """上传一份资料并驱动后台成功：得到一个真正 ready 的已发布版本。"""
    payload = _upload_ok(client, subject, [("one.txt", b"old", None)])
    _drive_task(subject, payload["task_id"], ok=True)
    return payload


def _kb_manager(subject) -> KnowledgeBaseManager:
    return KnowledgeBaseManager(base_dir=str(subject.knowledge_bases))


def _release(subject, kb_name: str = KB_NAME) -> None:
    uploads.clear_reservation(_kb_dir(subject, kb_name), task_id=None)
    uploads.reset_registry_for_tests()


def _entry(client, subject, kb_name: str = KB_NAME) -> dict:
    response = client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert response.status_code == 200, response.text
    for item in response.json()["knowledge"]:
        if item["kb_name"] == kb_name:
            return item
    raise AssertionError(f"{kb_name} not listed: {response.text}")


def _status(client, subject, kb_name: str = KB_NAME) -> dict:
    response = client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{kb_name}/status")
    assert response.status_code == 200, response.text
    return response.json()


def _upload_ok(client, subject, specs, *, type: str = "auto") -> dict:
    response = _upload(client, subject.subject_id, specs, type=type)
    assert response.status_code == 200, response.text
    return response.json()


def _drive_task(subject, task_id: str, *, ok: bool) -> dict:
    """用可控假任务显式驱动后台成功/失败（不是把 mock 排队当成完成）。

    返回**真实落盘**的索引状态记录，证明 ready/error 来自终态而不是排队本身。
    """
    manager = _kb_manager(subject)
    if ok:
        manager.update_kb_status(
            name=KB_NAME,
            status="ready",
            progress={"stage": "completed", "message": "done", "percent": 100},
        )
        TaskIDManager.get_instance().update_task_status(task_id, "completed")
    else:
        manager.update_kb_status(
            name=KB_NAME,
            status="error",
            progress={
                "stage": "error",
                "message": f"Initialization failed: {FAKE_MARKER}",
                "error": FAKE_MARKER,
                "percent": 0,
            },
        )
        TaskIDManager.get_instance().update_task_status(task_id, "error")

    async def _run() -> None:
        return None

    asyncio.run(_REAL_RUN_RESERVED(_kb_dir(subject), task_id, _run))
    return material_manifest.load_index_state(
        _kb_dir(subject), subject_id=subject.subject_id, kb_name=KB_NAME
    )


# ---------------------------------------------------------------------------
# 计数
# ---------------------------------------------------------------------------
def test_documents_counts_the_current_index_source(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    payload = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])

    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 1
    assert entry["status"]["documents"] == 1
    assert entry["status"]["task_id"] == payload["task_id"]
    assert entry["status"]["status"] == "rebuilding"
    assert entry["status"]["busy"] is True
    assert entry["status"]["queued"] is True

    status = _status(p1_route_client, subject)
    assert status["kb_name"] == KB_NAME
    assert status["documents"] == 1
    assert set(status) >= {"kb_name", "status", "progress", "updated_at", "documents"}
    assert set(status["progress"]) >= {"stage", "message", "percent"}


def test_same_name_replacement_keeps_the_count_at_one(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _drive_task(subject, first["task_id"], ok=True)
    _upload_ok(p1_route_client, subject, [("one.txt", b"one replaced", None)])
    assert _entry(p1_route_client, subject)["documents"] == 1
    assert len(list((_kb_dir(subject) / "raw").iterdir())) == 1


def test_adding_a_second_source_raises_the_count_and_marks_rebuilding(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _drive_task(subject, first["task_id"], ok=True)
    assert _entry(p1_route_client, subject)["status"]["status"] == "ready"

    second = _upload_ok(p1_route_client, subject, [("two.txt", b"two", None)])
    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 2
    assert entry["status"]["status"] == "rebuilding"
    assert entry["status"]["busy"] is True
    assert entry["status"]["task_id"] == second["task_id"]
    # 旧索引 ready 只证明旧资料版本：新增源之后不能继续展示 ready
    assert entry["status"]["status"] != "ready"
    assert entry["status"]["index_sources"] == "stale"


def test_the_count_is_not_chunks_uploads_or_stored_counters(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _drive_task(subject, first["task_id"], ok=False)

    # 存储里的 documents 与 manager 的 chunk 计数都撒谎，投影必须以 raw 为准
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": KB_NAME, "documents": 999}
    )
    _kb_manager(subject).update_kb_status(
        name=KB_NAME,
        status="ready",
        progress={
            "stage": "completed",
            "message": FAKE_MARKER,
            "error": FAKE_MARKER,
            "indexed_count": 4242,
            "current": 4242,
            "total": 4242,
            "percent": 100,
        },
    )
    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert response.status_code == 200
    assert FAKE_MARKER not in response.text
    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 1
    assert entry["status"]["status"] == "error"
    assert entry["status"]["progress"]["message"] == "上一次索引任务失败，请重试。"
    assert entry["status"]["progress"]["percent"] == 0


# ---------------------------------------------------------------------------
# ready 只在真实成功之后
# ---------------------------------------------------------------------------
def test_ready_requires_a_real_successful_task_and_failure_is_visible(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    assert _entry(p1_route_client, subject)["status"]["status"] != "ready"

    state = _drive_task(subject, first["task_id"], ok=True)
    assert state is not None and state["status"] == "ready"
    entry = _entry(p1_route_client, subject)
    assert entry["status"]["status"] == "ready"
    assert entry["status"]["progress"]["percent"] == 100
    assert entry["status"]["busy"] is False
    assert entry["status"]["indexed_documents"] == 1
    assert uploads.reservation_for(_kb_dir(subject)) is None

    second = _upload_ok(p1_route_client, subject, [("two.txt", b"two", None)])
    assert _entry(p1_route_client, subject)["status"]["status"] == "rebuilding"

    failed = _drive_task(subject, second["task_id"], ok=False)
    assert failed is not None and failed["status"] == "error"
    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert FAKE_MARKER not in response.text
    entry = _entry(p1_route_client, subject)
    assert entry["status"]["status"] == "error"
    assert entry["status"]["progress"]["message"] == "上一次索引任务失败，请重试。"
    assert entry["status"]["progress"]["percent"] == 0


def test_a_worker_thread_that_is_still_alive_blocks_a_retry(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    # 任务状态已经是 error，但同步 worker 线程还活着 —— 仍然必须 busy
    _drive_task(subject, first["task_id"], ok=False)
    assert uploads.reservation_for(_kb_dir(subject)) is None
    key = str(_kb_dir(subject).resolve())
    marker = pipeline_mod._claim_index_worker(key)
    try:
        entry = _entry(p1_route_client, subject)
        assert entry["status"]["busy"] is True
        assert entry["status"]["worker_alive"] is True
        assert entry["status"]["status"] == "rebuilding"
        retry = _upload(p1_route_client, subject.subject_id, [("two.txt", b"two", None)])
        assert retry.status_code == 409, retry.text
        assert retry.json()["error"]["code"] == "kb_busy"
        assert _entry(p1_route_client, subject)["documents"] == 1
    finally:
        pipeline_mod._release_index_worker(key, marker)

    # 线程真正退出后可以重试
    again = _upload(p1_route_client, subject.subject_id, [("two.txt", b"two", None)])
    assert again.status_code == 200, again.text
    assert _entry(p1_route_client, subject)["documents"] == 2
    assert uploads.reservation_for(_kb_dir(subject)) is not None


def test_a_queued_but_not_started_task_blocks_a_second_request(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    second = _upload(p1_route_client, subject.subject_id, [("two.txt", b"two", None)])
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "kb_busy"
    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 1
    assert entry["status"]["status"] == "rebuilding"
    assert entry["status"]["busy"] is True and entry["status"]["queued"] is True
    assert entry["status"]["task_id"] == first["task_id"]
    assert len(queued.calls) == 1


# ---------------------------------------------------------------------------
# 跨科目隔离与 GET 只读
# ---------------------------------------------------------------------------
def test_other_subjects_and_the_global_library_are_independent(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    other = p1_subjects["科目B"]
    global_kb = p1_subjects["global"]
    before_other = helpers.tree_digest(other.root)
    before_global = helpers.tree_digest(global_kb)

    _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])

    assert helpers.tree_digest(other.root) == before_other
    assert helpers.tree_digest(global_kb) == before_global
    # 其他科目没有被写入任何同名记录
    assert store.load_knowledge_records(other.subject_id) == []
    assert _entry(p1_route_client, subject)["documents"] == 1


def test_get_never_writes(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])
    _drive_task(subject, first["task_id"], ok=True)
    before = helpers.tree_digest(subject.root)

    for _ in range(3):
        assert p1_route_client.get(
            f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge"
        ).status_code == 200
        assert p1_route_client.get(
            f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status"
        ).status_code == 200
    assert helpers.tree_digest(subject.root) == before


def test_status_endpoint_shapes_and_errors(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])

    missing = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/no-such-kb/status"
    )
    assert missing.status_code == 404
    # 历史兼容：没有 error 对象，但 detail 是固定文案（不回显调用方输入）
    assert set(missing.json()) == {"detail"}
    assert missing.json()["detail"] == "知识库不存在。"
    assert "no-such-kb" not in missing.text

    bad_subject = p1_route_client.get(
        f"{ROUTE_PREFIX}/not%20a%20slug/knowledge/{KB_NAME}/status"
    )
    assert bad_subject.status_code == 400
    assert bad_subject.json()["error"]["code"] == "invalid_subject_id"

    unknown = p1_route_client.get(f"{ROUTE_PREFIX}/nosuchsubject/knowledge/{KB_NAME}/status")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "subject_not_found"


# ---------------------------------------------------------------------------
# 旧库兼容
# ---------------------------------------------------------------------------
def test_a_legacy_ready_library_is_compatible_but_drift_is_never_ready(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    kb_dir = _kb_dir(subject)
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    materials = Path(subject.materials) / "assignment"
    materials.mkdir(parents=True, exist_ok=True)
    body = b"legacy material"
    (raw / "legacy.txt").write_bytes(body)
    (materials / "legacy.txt").write_bytes(body)
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": KB_NAME, "kb_id": "legacy-id", "type": "assignment", "documents": 0},
    )
    _kb_manager(subject).update_kb_status(
        name=KB_NAME, status="ready", progress={"stage": "completed", "percent": 100}
    )

    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 1
    assert entry["status"]["status"] == "ready"  # 旧库仍可用
    assert entry["status"]["index_sources"] == "unknown"

    # 源发生变化（raw 多出一份 materials 里没有的文件）→ 绝不再报 ready
    (raw / "drifted.txt").write_bytes(b"drifted")
    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 2
    assert entry["status"]["status"] == "stale"
    assert entry["status"]["materials_in_sync"] is False
    assert json.loads(
        (Path(REPO_ROOT) / "plans" / "phase1" / "schemas.json").read_text(encoding="utf-8")
    )["$defs"]["MaterialManifest"]["properties"]["schema_version"]["const"] == 1


# ---------------------------------------------------------------------------
# R1（rework01）：GET 无副作用、元数据严格读取
# ---------------------------------------------------------------------------
def test_get_does_not_migrate_kb_config(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    config = Path(subject.knowledge_bases) / "kb_config.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["knowledge_bases"][KB_NAME]["rag_provider"] = "historical-removed-provider"
    config.write_text(json.dumps(payload), encoding="utf-8")
    before_bytes = config.read_bytes()
    before_tree = _tree_without_locks(subject.root)

    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert response.status_code == 200, response.text
    assert config.read_bytes() == before_bytes, "GET 迁移/规范化了 kb_config.json"
    assert _tree_without_locks(subject.root) == before_tree, "GET 改动了 subject 树"


def test_get_does_not_create_a_missing_kb_root(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": "ghost-kb", "kb_id": "ghost", "type": "assignment", "documents": 0},
    )
    kb_dir = Path(subject.knowledge_bases) / "ghost-kb"
    assert not kb_dir.exists()
    before_tree = _tree_without_locks(subject.root)

    listing = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert listing.status_code == 200, listing.text
    assert not kb_dir.exists(), "GET 创建了缺失的 KB 根目录"
    status = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/ghost-kb/status"
    )
    assert status.status_code == 200, status.text
    assert not kb_dir.exists()
    assert _tree_without_locks(subject.root) == before_tree


def test_get_with_a_bad_stored_type_is_corrupt_and_writes_nothing(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    store.upsert_knowledge_record(
        subject.subject_id,
        {"kb_name": "bad-type-kb", "kb_id": "bad", "type": "../../etc", "documents": 0},
    )
    before_tree = _tree_without_locks(subject.root)
    response = p1_route_client.get(f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge")
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert "../../etc" not in response.text
    assert _tree_without_locks(subject.root) == before_tree


@pytest.mark.parametrize("leaf", [material_manifest.MANIFEST_NAME, material_manifest.INDEX_STATE_NAME])
def test_manifest_and_state_symlinks_are_not_read(
    p1_subjects, p1_route_client, queued, tmp_path, leaf
):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    path = _kb_dir(subject) / leaf
    original = path.read_bytes()
    outside = tmp_path / f"outside-{leaf}"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)

    response = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status"
    )
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] in ("storage_io", "storage_corrupt")
    assert outside.read_bytes() == original
    path.unlink()
    path.write_bytes(original)


def test_dangling_manifest_symlink_is_not_a_missing_legacy_manifest(
    p1_subjects, p1_route_client, queued, tmp_path
):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    path = material_manifest.manifest_path(_kb_dir(subject))
    path.unlink()
    path.symlink_to(tmp_path / "absent-target")

    response = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status"
    )
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] in ("storage_io", "storage_corrupt")


def test_a_null_manifest_is_corrupt_not_legacy(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    path = material_manifest.manifest_path(_kb_dir(subject))
    path.write_text("null")
    before = path.read_bytes()

    response = _upload(p1_route_client, subject.subject_id, [("two.txt", b"two", None)])
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_corrupt"
    assert path.read_bytes() == before, "坏 manifest 被覆盖成新的"
    assert not (_raw(subject) / "two.txt").exists()


def test_a_null_index_state_is_corrupt_not_missing(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    material_manifest.index_state_path(_kb_dir(subject)).write_text("null")
    response = p1_route_client.get(
        f"{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status"
    )
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "storage_corrupt"


# ---------------------------------------------------------------------------
# R2（rework01）：ready 必须对应已发布源的内容身份
# ---------------------------------------------------------------------------
def test_same_size_replacement_cannot_remain_ready(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    assert _status(p1_route_client, subject)["status"] == "ready"

    second = _upload_ok(p1_route_client, subject, [("one.txt", b"new", None)])
    assert len(b"old") == len(b"new")
    status = _status(p1_route_client, subject)
    assert status["queued"] is True
    assert status["status"] != "ready", status
    assert status["task_id"] == second["task_id"]
    assert status["published_source"]["matches_current"] is False


def test_same_size_replacement_after_reservation_loss_is_stale(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    _upload_ok(p1_route_client, subject, [("one.txt", b"new", None)])
    uploads.clear_reservation(_kb_dir(subject))
    status = _status(p1_route_client, subject)
    assert status["status"] == "stale", status
    assert status["published_source"]["documents"] == 1


def test_identical_bytes_replacement_keeps_the_published_version_usable(
    p1_subjects, p1_route_client, queued
):
    """合法对照：同名同字节重传不会把已发布版本判成过期。"""
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    uploads.clear_reservation(_kb_dir(subject))
    again = _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    # 内容逐字节相同：已发布索引确实覆盖当前资料，因此仍然 ready（同时有新任务在跑）
    status = _status(p1_route_client, subject)
    assert status["status"] == "ready", status
    assert status["published_source"]["matches_current"] is True
    assert status["busy"] is True
    assert status["task_id"] == again["task_id"]

    uploads.clear_reservation(_kb_dir(subject))
    settled = _status(p1_route_client, subject)
    assert settled["status"] == "ready", settled
    assert settled["busy"] is False


def test_a_missing_materials_directory_cannot_be_in_sync_ready(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    _seed(p1_route_client, subject)
    import shutil

    shutil.rmtree(_materials(subject))
    status = _status(p1_route_client, subject)
    assert status["materials_in_sync"] is False, status
    assert status["status"] != "ready", status
    assert status["materials_drift"]["missing"] == ["one.txt"]


def test_published_version_and_last_attempt_are_separate_fields(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _seed(p1_route_client, subject)
    second = _upload_ok(p1_route_client, subject, [("two.txt", b"two", None)])
    _drive_task(subject, second["task_id"], ok=False)

    status = _status(p1_route_client, subject)
    assert status["status"] == "error"  # 新失败可见
    assert status["published_source"] is not None  # 旧的有效索引版本仍然可见
    assert status["published_source"]["task_id"] == first["task_id"]
    assert status["published_source"]["documents"] == 1
    assert status["published_source"]["matches_current"] is False
    assert status["last_attempt"]["status"] == "error"


# ---------------------------------------------------------------------------
# R4（rework01）：后台开始前与发布 ready 前的源版本门禁
# ---------------------------------------------------------------------------
def test_queued_task_revalidates_sources_before_running_index(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    payload = _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    (_raw(subject) / "one.txt").write_bytes(b"bad")  # 同大小漂移

    calls: list[str] = []

    async def _run() -> None:
        calls.append("index started")
        manager = _kb_manager(subject)
        manager.update_kb_status(name=KB_NAME, status="ready", progress={})
        TaskIDManager.get_instance().update_task_status(payload["task_id"], "completed")

    asyncio.run(_REAL_RUN_RESERVED(_kb_dir(subject), payload["task_id"], _run))
    assert calls == [], "排队后源漂移仍然启动了索引"
    assert _status(p1_route_client, subject)["status"] != "ready"


def test_finalizer_cannot_publish_ready_for_drifted_sources(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    payload = _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    (_raw(subject) / "one.txt").write_bytes(b"bad")
    _kb_manager(subject).update_kb_status(name=KB_NAME, status="ready", progress={})
    TaskIDManager.get_instance().update_task_status(payload["task_id"], "completed")

    finished = uploads.finalize_reserved_task(_kb_dir(subject), payload["task_id"])
    assert finished["ok"] is False, "漂移的源被标成索引成功"
    assert _status(p1_route_client, subject)["status"] != "ready"


def test_a_stale_finalizer_cannot_override_a_different_reservation(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects["科目A"]
    first = _upload_ok(p1_route_client, subject, [("one.txt", b"old", None)])
    uploads.clear_reservation(_kb_dir(subject), task_id=first["task_id"])
    second = _upload_ok(p1_route_client, subject, [("one.txt", b"new", None)])

    uploads.finalize_reserved_task(_kb_dir(subject), first["task_id"])
    reservation = uploads.reservation_for(_kb_dir(subject))
    assert reservation["task_id"] == second["task_id"]
    assert not material_manifest.index_state_path(_kb_dir(subject)).exists(), (
        "过时的 finalizer 为新预留写了状态"
    )


def test_repeated_successes_and_later_failure_keep_the_latest_published_source(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects['科目A']
    for body in (b'old', b'new', b'end'):
        result = _upload_ok(p1_route_client, subject, [('one.txt', body, None)])
        state = _drive_task(subject, result['task_id'], ok=True)
        status = _status(p1_route_client, subject)
        assert status['status'] == 'ready', status
        assert status['published_source']['matches_current'] is True
    latest = state['fingerprint']
    result = _upload_ok(p1_route_client, subject, [('one.txt', b'bad', None)])
    state = _drive_task(subject, result['task_id'], ok=False)
    assert state['last_ready']['fingerprint'] == latest
    assert state['reason'] == 'task_failed'
    assert _status(p1_route_client, subject)['status'] == 'error'


def test_finalization_preserves_existing_corrupt_state(p1_subjects, p1_route_client, queued):
    subject = p1_subjects['科目A']
    result = _upload_ok(p1_route_client, subject, [('one.txt', b'old', None)])
    path = material_manifest.index_state_path(_kb_dir(subject))
    path.write_text('null', encoding='utf-8')
    _kb_manager(subject).update_kb_status(name=KB_NAME, status='ready')
    TaskIDManager.get_instance().update_task_status(result['task_id'], 'completed')
    finished = uploads.finalize_reserved_task(_kb_dir(subject), result['task_id'])
    assert finished == {'ok': False, 'reason': 'state_read_failed'}
    assert path.read_bytes() == b'null'
    assert uploads.reservation_for(_kb_dir(subject)) is None


def test_source_io_failure_fails_task_and_releases_the_queue(
    p1_subjects, p1_route_client, queued, monkeypatch
):
    subject = p1_subjects['科目A']
    result = _upload_ok(p1_route_client, subject, [('one.txt', b'old', None)])
    calls = []
    def fail_digest(_path):
        raise PermissionError('injected source read error')
    async def run():
        calls.append('index started')
    monkeypatch.setattr(material_manifest, '_sha256_file', fail_digest)
    asyncio.run(_REAL_RUN_RESERVED(_kb_dir(subject), result['task_id'], run))
    assert calls == []
    assert uploads.reservation_for(_kb_dir(subject)) is None
    assert TaskIDManager.get_instance().get_task_metadata(result['task_id'])['status'] == 'error'


def test_stored_failure_reason_is_projected_without_diagnostics(
    p1_subjects, p1_route_client, queued
):
    subject = p1_subjects['科目A']
    result = _upload_ok(p1_route_client, subject, [('one.txt', b'old', None)])
    _drive_task(subject, result['task_id'], ok=True)
    path = material_manifest.index_state_path(_kb_dir(subject))
    state = json.loads(path.read_text())
    state['reason'] = FAKE_MARKER * 1024
    path.write_text(json.dumps(state), encoding='utf-8')
    response = p1_route_client.get(f'{ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status')
    assert response.status_code == 200, response.text
    assert FAKE_MARKER not in response.text
    assert response.json()['last_attempt']['reason'] == 'unknown'

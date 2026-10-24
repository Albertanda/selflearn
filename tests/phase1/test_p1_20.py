"""P1-20 行为测试：科目 KB 作用域标识与只读解析（C08/C01/C02）。

目标：A/B/global 三处**同名**知识库被准确、授权地解析到不同的服务端目录，
解析本身不建立任何东西（KB、manager、锁、配置迁移、全量 hash 都没有）。

必证场景（对应卡内清单与 START_S07 第三节 P1-20 证据）：

* A/B/global 同名 → 各自 base/kb 目录，互不复用；
* 中文 subject/KB 往返，不被 lower/strip/ASCII 化改写；
* 越科 403 / 未知科 404 / 未登记 KB 404（含"目录存在但没登记"）/ 非 ready 409；
* 裸名只在 mounted 集合唯一匹配时接受：0 匹配 404、>1 400、``None`` 与 ``[]`` 语义不同；
* 显式 wire ref 也受本轮 mounted 集合约束；无科目的旧全局调用维持原 resolver；
* 负例不回显恶意输入；解析前后整棵临时树零写入；
* 资源投影不含 base_dir/宿主路径。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deeptutor.subjects import json_store, kb_scope, store, uploads
from deeptutor.subjects import material_manifest as manifest_mod
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    SubjectStorageError,
    map_subject_exception,
)
from tests.phase1 import helpers

KB_NAME = "assignment-kb"
KB_TYPE = "assignment"


@pytest.fixture(autouse=True)
def _isolated_registries():
    """同库预留表是模块级状态：每个用例前后都清空，避免跨用例串味。"""
    uploads.reset_registry_for_tests()
    try:
        yield
    finally:
        uploads.reset_registry_for_tests()


# ---------------------------------------------------------------------------
# 夹具：production 形状的"真正 ready"科目库
# ---------------------------------------------------------------------------
def _write_kb_config(subject, entries: dict[str, dict]) -> Path:
    """把条目合并进 ``knowledge_bases/kb_config.json``（production 顶层形状）。"""
    path = Path(subject.knowledge_bases) / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload = loaded
    current = payload.setdefault("knowledge_bases", {})
    if not isinstance(current, dict):  # pragma: no cover - defensive
        current = payload["knowledge_bases"] = {}
    current.update(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _index_files(kb_dir: Path) -> Path:
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    return raw


def _publish_ready(subject, kb_name: str, *, marker: str) -> Path:
    """raw/materials 一致 + manifest + published index → ``project_status=ready``。"""
    kb_dir = Path(subject.knowledge_bases) / kb_name
    raw = _index_files(kb_dir)
    materials = Path(subject.materials) / KB_TYPE
    materials.mkdir(parents=True, exist_ok=True)
    name = f"{marker}.txt"
    (raw / name).write_text(f"{marker}\n", encoding="utf-8")
    (materials / name).write_text(f"{marker}\n", encoding="utf-8")
    files = manifest_mod.source_files(raw)
    manifest_mod.save_manifest(
        kb_dir,
        manifest_mod.build_manifest(
            subject_id=subject.subject_id, kb_name=kb_name, files=files
        ),
    )
    manifest_mod.save_index_state(
        kb_dir,
        {
            "schema_version": manifest_mod.INDEX_STATE_SCHEMA_VERSION,
            "subject_id": subject.subject_id,
            "kb_name": kb_name,
            "status": "ready",
            "fingerprint": manifest_mod.fingerprint(files),
            "shape": manifest_mod.shape(files),
            "documents": len(files),
            "task_id": None,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    return kb_dir


def _write_global_kb_config(base: Path, kb_name: str) -> Path:
    """把全局库登记进 ``knowledge_bases/kb_config.json``（production 形状）。

    全局库的授权/发现仍归 multi_user + KnowledgeBaseManager；这里只是把"盘上
    有库"变成"已登记"，避免测试依赖 manager 的自动注册写入。
    """
    path = Path(base) / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "llamaindex",
        "updated_at": "2026-01-01T00:00:00",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _make_ready_kb(subject, kb_name: str = KB_NAME, *, marker: str | None = None) -> Path:
    kb_dir = _publish_ready(subject, kb_name, marker=marker or f"{subject.subject_id}-only")
    _write_kb_config(
        subject, {kb_name: {"status": "ready", "rag_provider": "llamaindex"}}
    )
    store.upsert_knowledge_record(
        subject.subject_id,
        {
            "kb_name": kb_name,
            "type": KB_TYPE,
            "documents": 1,
            "status": "ready",
            "created_at": 1791000000,
        },
    )
    return kb_dir


@pytest.fixture
def libraries(p1_runtime: Path) -> dict:
    """A / B 各一个同名 ready 库；global 同名库（旧全局 resolver 语义）。"""
    subject_a = helpers.make_subject(p1_runtime, "科目A")
    subject_b = helpers.make_subject(p1_runtime, "科目B")
    kb_a = _make_ready_kb(subject_a, marker="A-only")
    kb_b = _make_ready_kb(subject_b, marker="B-only")
    global_root = helpers.global_kb_root(p1_runtime)
    global_kb = helpers.make_kb(global_root, KB_NAME, "global-only")
    _write_global_kb_config(global_root, KB_NAME)
    return {
        "admin_root": p1_runtime,
        "A": subject_a,
        "B": subject_b,
        "kb_a": kb_a,
        "kb_b": kb_b,
        "global": global_kb,
        "ref_a": kb_scope.encode_subject_kb_ref(subject_a.subject_id, KB_NAME),
        "ref_b": kb_scope.encode_subject_kb_ref(subject_b.subject_id, KB_NAME),
    }


def _ref(subject, kb_name: str = KB_NAME) -> str:
    return kb_scope.encode_subject_kb_ref(subject.subject_id, kb_name)


#: 存储层与业务层是两条并行的异常层级（C02 不要求统一继承树），断言时都接受并
#: 通过 ``map_subject_exception`` 取 C02 投影。
_SUBJECT_ERRORS = (SubjectOperationError, SubjectStorageError)


def _code(exc: BaseException) -> str:
    error = exc if isinstance(exc, SubjectOperationError) else map_subject_exception(exc)
    return error.code.value


def _tree(root: Path) -> dict[str, str]:
    return {
        key: value
        for key, value in helpers.tree_digest(root).items()
        if not key.endswith(json_store.LOCK_FILE_NAME)
    }


# ---------------------------------------------------------------------------
# 同名隔离与编解码
# ---------------------------------------------------------------------------
def test_same_name_libraries_resolve_to_their_own_directories(libraries):
    subject_a, subject_b = libraries["A"], libraries["B"]
    a = kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject_a.subject_id)
    b = kb_scope.resolve_kb_ref(libraries["ref_b"], expected_subject_id=subject_b.subject_id)

    assert a.name == b.name == KB_NAME, "解析改写了磁盘库名"
    assert a.base_dir != b.base_dir
    assert a.kb_dir == libraries["kb_a"] and b.kb_dir == libraries["kb_b"]
    assert a.subject_id == subject_a.subject_id and b.subject_id == subject_b.subject_id
    assert a.read_only is False and b.read_only is False
    assert a.provider == b.provider == "llamaindex"

    markers = {
        "A": helpers.kb_markers(a.kb_dir),
        "B": helpers.kb_markers(b.kb_dir),
    }
    assert markers == {"A": {"A-only"}, "B": {"B-only"}}, markers


def test_chinese_and_mixed_case_identities_round_trip(libraries):
    subject_a = libraries["A"]
    ref = kb_scope.encode_subject_kb_ref(subject_a.subject_id, "Assignment-KB 中文 名")
    assert ref == f"subject:kb:{subject_a.subject_id}:Assignment-KB 中文 名"
    assert kb_scope.decode_subject_kb_ref(ref) == (subject_a.subject_id, "Assignment-KB 中文 名")
    # 全局 wire 不是 subject ref：编解码层不抢它。
    assert kb_scope.decode_subject_kb_ref("admin:kb:x") is None
    assert kb_scope.decode_subject_kb_ref("user:kb:x") is None
    assert kb_scope.decode_subject_kb_ref("plain") is None
    # 身份按原样比较，不做大小写/空白/翻译归一化。
    subject = libraries["A"]
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            f"subject:kb:{subject.subject_id}:ASSIGNMENT-KB",
            expected_subject_id=subject.subject_id,
        )
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value


def test_encoding_rejects_illegal_identities(libraries):
    for subject_id, kb_name in (
        ("科目A:", KB_NAME),
        ("科目A", "kb:name"),
        ("../科目A", KB_NAME),
        ("科目A", "../kb"),
        ("科目A", "kb/name"),
        ("科目A", "kb\\name"),
        ("科目A", " kb"),
        ("科目A", "kb\x07"),
        ("科目A", ""),
        ("A B", KB_NAME),
    ):
        with pytest.raises(json_store.InvalidInputError) as excinfo:
            kb_scope.encode_subject_kb_ref(subject_id, kb_name)
        assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value

    for ref in (
        "subject:kb:科目A",
        "subject:kb:科目A:kb:extra",
        "subject:kb::kb",
        "subject:kb:../科目A:kb",
        "subject:kb:科目A:../kb",
        "subject:kb:科目A:kb\x07name",
    ):
        with pytest.raises(json_store.InvalidInputError) as excinfo:
            kb_scope.decode_subject_kb_ref(ref)
        assert excinfo.value.code.value == ErrorCode.INVALID_INPUT.value


def test_resource_projection_never_exposes_server_paths(libraries):
    a = kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=libraries["A"].subject_id)
    public = a.public_dict()
    assert set(public) == {"kb_ref", "name", "subject_id", "read_only", "provider"}
    blob = json.dumps(public, ensure_ascii=False)
    assert str(libraries["admin_root"]) not in blob
    assert "base_dir" not in blob and "knowledge_bases" not in blob


# ---------------------------------------------------------------------------
# 授权与存在性
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "expected_key, ref_key", [("B", "ref_a"), (None, "ref_a"), ("A", "ref_b")]
)
def test_cross_subject_references_are_forbidden(libraries, expected_key, ref_key):
    expected = libraries[expected_key].subject_id if expected_key else None
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(libraries[ref_key], expected_subject_id=expected)
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value
    assert excinfo.value.http_status == 403
    assert excinfo.value.retryable is False


def test_unknown_or_unregistered_subject_is_not_found(libraries):
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            "subject:kb:不存在的科目:assignment-kb", expected_subject_id="不存在的科目"
        )
    assert _code(excinfo.value) == ErrorCode.SUBJECT_NOT_FOUND.value
    assert excinfo.value.http_status == 404

    # 目录存在但科目没有登记：同样 404，不因为"盘上有目录"就可用。
    orphan = Path(libraries["admin_root"]) / "user" / "workspace" / "subjects" / "孤儿科"
    (orphan / "knowledge_bases" / KB_NAME / "raw").mkdir(parents=True, exist_ok=True)
    (orphan / "knowledge_bases" / KB_NAME / "raw" / "x.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            "subject:kb:孤儿科:assignment-kb", expected_subject_id="孤儿科"
        )
    assert _code(excinfo.value) == ErrorCode.SUBJECT_NOT_FOUND.value


def test_missing_or_unregistered_library_is_not_found(libraries):
    subject = libraries["A"]
    # 未登记：没有 knowledge.json 记录，也没有 kb_config 条目（目录只是存在）。
    unregistered = Path(subject.knowledge_bases) / "ghost-kb"
    (unregistered / "raw").mkdir(parents=True, exist_ok=True)
    (unregistered / "raw" / "ghost.txt").write_text("ghost\n", encoding="utf-8")
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject, "ghost-kb"), expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value
    assert excinfo.value.http_status == 404

    # 完全不存在（连目录都没有）：同样 404，且不把 KB 根目录建出来。
    base = Path(subject.knowledge_bases)
    assert not (base / "never-kb").exists()
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject, "never-kb"), expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value
    assert not (base / "never-kb").exists()


def test_a_library_known_only_by_its_config_entry_still_resolves(libraries):
    """kb_config 条目就是登记，不需要 knowledge.json 记录 —— 但目录必须真实存在。

    一个**已有目录**、尚无源与已发布索引的 legacy 库由 S05 的兼容分支判 ready；
    这里如实断言解析沿用同一投影，而不是新造一套 ready 判据。
    """
    subject = libraries["A"]
    (Path(subject.knowledge_bases) / "config-only-kb").mkdir(parents=True, exist_ok=True)
    _write_kb_config(subject, {"config-only-kb": {"status": "ready"}})
    resolved = kb_scope.resolve_kb_ref(
        _ref(subject, "config-only-kb"), expected_subject_id=subject.subject_id
    )
    assert resolved.name == "config-only-kb"
    assert resolved.kb_dir == Path(subject.knowledge_bases) / "config-only-kb"
    assert resolved.status == "ready"
    assert kb_scope.is_subject_kb_registered(subject.subject_id, "config-only-kb") is True
    assert kb_scope.is_subject_kb_registered(subject.subject_id, "ghost-kb") is False


@pytest.mark.parametrize("require_ready", [True, False])
def test_a_registered_library_without_a_directory_is_not_a_library(libraries, require_ready):
    """登记 ≠ 存在：只有 kb_config/metadata 条目、盘上没有目录 → 404。

    两种 require_ready 都必须拒绝（这不是"就绪"问题，而是"库里没有东西"），
    并且解析**不得**把目录建出来。S05 的 legacy 兼容分支描述的是"源未测量"的库，
    不是"树不存在"的库。
    """
    subject = libraries["A"]
    _write_kb_config(subject, {"ghost": {"status": "ready", "rag_provider": "llamaindex"}})
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": "ghost", "type": KB_TYPE, "documents": 0}
    )
    path = Path(subject.knowledge_bases) / "ghost"
    assert not path.exists()
    tree_before = _tree(Path(subject.knowledge_bases).parent)

    with pytest.raises(SubjectOperationError) as excinfo:
        kb_scope.resolve_kb_ref(
            _ref(subject, "ghost"),
            expected_subject_id=subject.subject_id,
            require_ready=require_ready,
        )
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value
    assert not path.exists()
    assert _tree(Path(subject.knowledge_bases).parent) == tree_before


# ---------------------------------------------------------------------------
# readiness 只来自源/索引投影
# ---------------------------------------------------------------------------
def test_not_ready_libraries_are_refused(libraries):
    """stale / error / rebuilding / initializing / 假 ready 全部 409。"""
    subject = libraries["A"]

    # 1) 已发布索引 vs 变化的源：stale
    raw = Path(libraries["kb_a"]) / "raw"
    (raw / "A-only.txt").write_text("A-only changed bytes\n", encoding="utf-8")
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value
    assert excinfo.value.http_status == 409
    assert kb_scope.subject_kb_status(subject.subject_id, KB_NAME)["status"] == "stale"

    # 2) 恢复一致后，把索引状态写成 error：error
    (raw / "A-only.txt").write_text("A-only\n", encoding="utf-8")
    _publish_ready(subject, KB_NAME, marker="A-only")
    state_path = manifest_mod.index_state_path(libraries["kb_a"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "error"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value
    assert kb_scope.subject_kb_status(subject.subject_id, KB_NAME)["status"] == "error"

    # 3) registry 说 ready 但还没有已发布索引：rebuilding（不是 ready）
    _publish_ready(subject, KB_NAME, marker="A-only")
    manifest_mod.index_state_path(libraries["kb_a"]).unlink()
    projection = kb_scope.subject_kb_status(subject.subject_id, KB_NAME)
    assert projection["status"] == "rebuilding", projection
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value

    # 4) 已登记但还没有任何测量（无源、无 manifest、无索引状态）：initializing
    subject_b = libraries["B"]
    _write_kb_config(subject_b, {"empty-kb": {}})
    (Path(subject_b.knowledge_bases) / "empty-kb").mkdir(parents=True, exist_ok=True)
    assert kb_scope.subject_kb_status(subject_b.subject_id, "empty-kb")["status"] == "initializing"
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject_b, "empty-kb"), expected_subject_id=subject_b.subject_id)
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value


def test_require_ready_false_skips_only_readiness(libraries):
    subject = libraries["A"]
    raw = Path(libraries["kb_a"]) / "raw"
    (raw / "A-only.txt").write_text("A-only drifted\n", encoding="utf-8")

    resolved = kb_scope.resolve_kb_ref(
        libraries["ref_a"], expected_subject_id=subject.subject_id, require_ready=False
    )
    assert resolved.status == "" and resolved.kb_dir == libraries["kb_a"]

    # 其余检查一个都没跳。
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            libraries["ref_a"], expected_subject_id=libraries["B"].subject_id, require_ready=False
        )
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            _ref(subject, "never-kb"), expected_subject_id=subject.subject_id, require_ready=False
        )
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value


def test_status_projection_agrees_with_the_http_projection(libraries, p1_route_client):
    """新模块的只读投影与科目路由 GET 的状态字典一致（同一 project_status）。"""
    subject = libraries["A"]
    response = p1_route_client.get(
        f"{helpers.ROUTE_PREFIX}/{subject.subject_id}/knowledge/{KB_NAME}/status"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kb_name"] == KB_NAME
    mine = kb_scope.subject_kb_status(subject.subject_id, KB_NAME)
    assert mine == {key: value for key, value in body.items() if key != "kb_name"}


# ---------------------------------------------------------------------------
# mounted 集合约束
# ---------------------------------------------------------------------------
def test_bare_names_require_a_unique_mounted_match(libraries):
    subject_a, subject_b = libraries["A"], libraries["B"]
    ref_a, ref_b = libraries["ref_a"], libraries["ref_b"]

    only_a = kb_scope.resolve_kb_ref(
        KB_NAME,
        expected_subject_id=subject_a.subject_id,
        mounted_refs=[ref_a],
    )
    assert only_a.kb_ref == ref_a and only_a.kb_dir == libraries["kb_a"]

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            KB_NAME,
            expected_subject_id=subject_a.subject_id,
            mounted_refs=[ref_a, ref_b],
        )
    assert _code(excinfo.value) == ErrorCode.INVALID_INPUT.value
    assert excinfo.value.http_status == 400

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            KB_NAME, expected_subject_id=subject_a.subject_id, mounted_refs=[]
        )
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value
    assert excinfo.value.http_status == 404

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            "other-name", expected_subject_id=subject_a.subject_id, mounted_refs=[ref_a]
        )
    assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value

    # 别名不是兜底：有 mounted 集合时 "default"/"默认知识库" 不解析成默认库。
    for alias in ("default", "默认知识库", "current", "selected"):
        with pytest.raises(_SUBJECT_ERRORS) as excinfo:
            kb_scope.resolve_kb_ref(
                alias, expected_subject_id=subject_a.subject_id, mounted_refs=[ref_a]
            )
        assert _code(excinfo.value) == ErrorCode.KB_NOT_FOUND.value

    # 空引用不是"某个库"：它是非法输入（400），也不允许回落到默认库。
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            "", expected_subject_id=subject_a.subject_id, mounted_refs=[ref_a]
        )
    assert _code(excinfo.value) == ErrorCode.INVALID_INPUT.value


def test_explicit_references_are_constrained_by_the_mounted_set(libraries):
    subject_a = libraries["A"]
    ref_a, ref_b = libraries["ref_a"], libraries["ref_b"]

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            ref_b, expected_subject_id=subject_a.subject_id, mounted_refs=[ref_a]
        )
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            "admin:kb:not-mounted",
            expected_subject_id=subject_a.subject_id,
            mounted_refs=[ref_a],
        )
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value

    # 挂载集合里的显式全局 ref 仍走原 multi_user 授权与审计。
    mounted_global = kb_scope.resolve_kb_ref(
        f"admin:kb:{KB_NAME}",
        expected_subject_id=subject_a.subject_id,
        mounted_refs=[ref_a, f"admin:kb:{KB_NAME}"],
    )
    assert mounted_global.subject_id is None
    assert mounted_global.name == KB_NAME
    assert mounted_global.base_dir == helpers.global_kb_root(libraries["admin_root"])
    assert Path(mounted_global.kb_dir) == Path(libraries["global"])
    assert mounted_global.read_only is False


def test_no_subject_legacy_calls_keep_the_global_resolver(libraries):
    """``mounted_refs=None`` 维持原全局 resolver（含默认别名语义）。"""
    from deeptutor.multi_user.knowledge_access import resolve_for_rag

    legacy = kb_scope.resolve_kb_ref(f"user:kb:{KB_NAME}")
    reference = resolve_for_rag(f"user:kb:{KB_NAME}")
    assert reference is not None
    assert legacy.name == reference.name
    assert legacy.base_dir == Path(reference.base_dir)
    assert legacy.read_only == reference.read_only

    bare = kb_scope.resolve_kb_ref(KB_NAME)
    assert bare.name == KB_NAME and bare.subject_id is None

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(f"user:kb:{KB_NAME}", mounted_refs=[])
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value


def test_mounted_helpers_report_every_reference(libraries):
    subject_a, subject_b = libraries["A"], libraries["B"]
    resolved = kb_scope.resolve_kb_refs(
        [libraries["ref_a"], f"admin:kb:{KB_NAME}"],
        expected_subject_id=subject_a.subject_id,
    )
    assert [item.kb_ref for item in resolved] == [
        libraries["ref_a"],
        f"admin:kb:{KB_NAME}",
    ]
    with pytest.raises(_SUBJECT_ERRORS):
        kb_scope.resolve_kb_refs([libraries["ref_b"]], expected_subject_id=subject_a.subject_id)


# ---------------------------------------------------------------------------
# 恶意引用与文件系统逃逸
# ---------------------------------------------------------------------------
def test_malicious_references_are_rejected_without_echoing_them(libraries):
    subject = libraries["A"]
    evil = [
        "subject:kb:../../etc:passwd",
        "subject:kb:科目A:../../etc/passwd",
        "subject:kb:科目A:kb\x00name",
        "subject:kb:科目A:kb\x1b[31mname",
        "subject:kb:科目A:..",
        "subject:kb:科目A:.",
        "subject:kb:" + "科目A" * 40 + ":kb",
    ]
    for ref in evil:
        with pytest.raises(_SUBJECT_ERRORS) as excinfo:
            kb_scope.resolve_kb_ref(ref, expected_subject_id=subject.subject_id)
        error = excinfo.value
        assert error.code.value == ErrorCode.INVALID_INPUT.value
        assert ref not in error.message, "错误消息回显了恶意输入"
        assert str(libraries["admin_root"]) not in error.message

    for bad in (None, 7, b"subject:kb:a:b", ["subject:kb:a:b"], {"kb_ref": "x"}):
        with pytest.raises(json_store.InvalidInputError):
            kb_scope.resolve_kb_ref(bad, expected_subject_id=subject.subject_id)  # type: ignore[arg-type]


def test_a_symlinked_library_leaf_is_refused(libraries):
    subject_a, subject_b = libraries["A"], libraries["B"]
    escaped = Path(subject_a.knowledge_bases) / "linked-kb"
    os.symlink(Path(subject_b.knowledge_bases) / KB_NAME, escaped)
    _write_kb_config(subject_a, {"linked-kb": {"status": "ready"}})
    store.upsert_knowledge_record(
        subject_a.subject_id, {"kb_name": "linked-kb", "type": KB_TYPE, "documents": 1}
    )

    before_b = _tree(Path(subject_b.knowledge_bases))
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject_a, "linked-kb"), expected_subject_id=subject_a.subject_id)
    assert _code(excinfo.value) == ErrorCode.STORAGE_IO.value
    assert _tree(Path(subject_b.knowledge_bases)) == before_b

    # 悬挂链接同样是错误，不会被当作"缺失的库"。
    dangling = Path(subject_a.knowledge_bases) / "dangling-kb"
    os.symlink(Path(subject_a.knowledge_bases) / "nowhere", dangling)
    _write_kb_config(subject_a, {"dangling-kb": {"status": "ready"}})
    store.upsert_knowledge_record(
        subject_a.subject_id, {"kb_name": "dangling-kb", "type": KB_TYPE, "documents": 0}
    )
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(
            _ref(subject_a, "dangling-kb"), expected_subject_id=subject_a.subject_id
        )
    assert _code(excinfo.value) == ErrorCode.STORAGE_IO.value


def test_a_symlinked_kb_root_is_refused_before_any_read(libraries, tmp_path):
    subject = libraries["B"]
    outside = tmp_path / "outside-kb-root"
    (outside / KB_NAME / "raw").mkdir(parents=True, exist_ok=True)
    (outside / KB_NAME / "raw" / "outside.txt").write_text("outside\n", encoding="utf-8")
    for entry in sorted(Path(subject.knowledge_bases).iterdir()):
        if entry.is_dir() and not entry.is_symlink():
            for child in sorted(entry.rglob("*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            entry.rmdir()
        else:
            entry.unlink()
    Path(subject.knowledge_bases).rmdir()
    os.symlink(outside, Path(subject.knowledge_bases))

    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject), expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.STORAGE_IO.value
    assert helpers.kb_markers(outside / KB_NAME) == {"outside"}


def test_an_external_pointer_is_refused_for_the_subject_tree(libraries):
    subject = libraries["A"]
    _publish_ready(subject, "extern-kb", marker="extern")
    _write_kb_config(
        subject,
        {"extern-kb": {"status": "ready", "external_path": "/tmp/not-this-subject"}},
    )
    store.upsert_knowledge_record(
        subject.subject_id, {"kb_name": "extern-kb", "type": KB_TYPE, "documents": 1}
    )
    with pytest.raises(_SUBJECT_ERRORS) as excinfo:
        kb_scope.resolve_kb_ref(_ref(subject, "extern-kb"), expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value


# ---------------------------------------------------------------------------
# 只读
# ---------------------------------------------------------------------------
def test_resolving_writes_nothing_at_all(libraries):
    subject_a, subject_b = libraries["A"], libraries["B"]
    roots = [
        Path(libraries["admin_root"]) / "user" / "workspace" / "subjects",
        Path(libraries["admin_root"]) / "user" / "subjects",
        Path(libraries["admin_root"]) / "knowledge_bases",
    ]
    before = {str(root): _tree(root) for root in roots}

    kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject_a.subject_id)
    kb_scope.resolve_kb_ref(
        KB_NAME, expected_subject_id=subject_a.subject_id, mounted_refs=[libraries["ref_a"]]
    )
    kb_scope.resolve_kb_ref(
        libraries["ref_a"], expected_subject_id=subject_a.subject_id, require_ready=False
    )
    kb_scope.subject_kb_status(subject_a.subject_id, KB_NAME)
    kb_scope.subject_kb_names(subject_a.subject_id)
    for ref, expected in (
        ("subject:kb:不存在:kb", "不存在"),
        (_ref(subject_b, "never-kb"), subject_b.subject_id),
        ("subject:kb:../x:kb", "../x"),
    ):
        with pytest.raises(_SUBJECT_ERRORS):
            kb_scope.resolve_kb_ref(ref, expected_subject_id=expected)

    after = {str(root): _tree(root) for root in roots}
    assert after == before, "解析过程写入了临时树"


def test_resolving_does_not_bring_a_missing_kb_root_into_existence(libraries):
    subject = libraries["B"]
    root = Path(subject.knowledge_bases) / "fresh-kb"
    assert not root.exists()
    with pytest.raises(_SUBJECT_ERRORS):
        kb_scope.resolve_kb_ref(_ref(subject, "fresh-kb"), expected_subject_id=subject.subject_id)
    assert not root.exists()
    assert not (root / "raw").exists()


# ---------------------------------------------------------------------------
# 真实普通用户的同名资源：自有库 vs 已授予 admin 库
# ---------------------------------------------------------------------------
def _user(user_id: str):
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user

    return CurrentUser(
        id=user_id,
        username=user_id,
        role="user",
        scope=scope_for_user(user_id, is_admin=False),
    )


def _make_user_kb(user, kb_name: str, marker: str) -> Path:
    """在**该用户自己的**工作区建同名库（真实普通用户身份，不是 local-admin）。"""
    from deeptutor.multi_user.paths import ensure_user_workspace

    root = ensure_user_workspace(user.id)
    kb_dir = Path(root) / "knowledge_bases" / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
    config = Path(root) / "knowledge_bases" / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if config.is_file():
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "llamaindex",
    }
    config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kb_dir


def _make_admin_kb(admin_root: Path, kb_name: str, marker: str) -> Path:
    base = helpers.global_kb_root(admin_root)
    kb_dir = base / kb_name
    raw = kb_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
    config = base / "kb_config.json"
    payload: dict = {"knowledge_bases": {}}
    if config.is_file():
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("knowledge_bases"), dict):
            payload = loaded
    payload["knowledge_bases"][kb_name] = {
        "path": kb_name,
        "status": "ready",
        "rag_provider": "llamaindex",
    }
    config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kb_dir


def test_a_users_own_library_and_an_assigned_admin_library_are_two_resources(
    libraries, monkeypatch
):
    """普通用户的 ``user:kb:shared`` 与被授予的 ``admin:kb:shared`` 同名但不同资源。

    探针用替身证明这一点；这里用**真实普通用户 + 真实 grants**跑同一场景：两者都
    可访问，却绝不能互相顶替，裸名同时命中两者时是歧义而不是任选。
    """
    from deeptutor.multi_user import grants, identity
    from deeptutor.multi_user.paths import user_context

    # A real account, created through the real registry: the first account in an
    # empty store is promoted to admin by design, so a second one is the
    # ordinary user this scenario needs.
    identity.save_user("review-admin-seed", "x", role="user")
    account = identity.save_user("review-user", "x", role="user")
    user = _user(account["id"])
    monkeypatch.setattr(kb_scope, "resolve_bound_provider", lambda *a, **k: "llamaindex")
    with user_context(user):
        own = _make_user_kb(user, "shared", "own-only")
        assigned = _make_admin_kb(libraries["admin_root"], "shared", "assigned-only")
        grants.save_grant(user.id, {"knowledge_bases": [{"name": "shared"}]})

        user_res = kb_scope.resolve_kb_ref("user:kb:shared", mounted_refs=["user:kb:shared"])
        admin_res = kb_scope.resolve_kb_ref("admin:kb:shared", mounted_refs=["admin:kb:shared"])
        assert user_res.kb_ref == "user:kb:shared" and user_res.read_only is False
        assert admin_res.kb_ref == "admin:kb:shared" and admin_res.read_only is True
        assert Path(user_res.kb_dir) == own
        assert Path(admin_res.kb_dir) == assigned
        assert own != assigned

        # 只挂自有库时，显式要 admin 同名库 → 403（不是"名字一样就放行"）。
        with pytest.raises(SubjectOperationError) as excinfo:
            kb_scope.resolve_kb_ref("admin:kb:shared", mounted_refs=["user:kb:shared"])
        assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value

        # 只挂 admin 库时，显式要自有库 → 403。
        with pytest.raises(SubjectOperationError) as excinfo:
            kb_scope.resolve_kb_ref("user:kb:shared", mounted_refs=["admin:kb:shared"])
        assert _code(excinfo.value) == ErrorCode.SCOPE_FORBIDDEN.value

        # 裸名同时命中两个资源 → invalid_input，不能猜。
        with pytest.raises(SubjectOperationError) as excinfo:
            kb_scope.resolve_kb_ref(
                "shared", mounted_refs=["user:kb:shared", "admin:kb:shared"]
            )
        assert _code(excinfo.value) == ErrorCode.INVALID_INPUT.value

        # 唯一挂载时裸名仍可用（旧的免前缀写法不回归）。
        only = kb_scope.resolve_kb_ref("shared", mounted_refs=["admin:kb:shared"])
        assert only.kb_ref == "admin:kb:shared"


def test_a_not_ready_global_library_is_refused_and_a_statusless_one_still_works(libraries):
    """显式挂载的全局库也受 ready 约束：error/stale 不可查询，legacy 无状态可查。"""
    global_base = helpers.global_kb_root(libraries["admin_root"])
    ref = f"admin:kb:{KB_NAME}"
    config = global_base / "kb_config.json"
    payload = json.loads(config.read_text(encoding="utf-8"))

    payload["knowledge_bases"][KB_NAME]["status"] = "error"
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SubjectOperationError) as excinfo:
        kb_scope.resolve_kb_ref(ref, mounted_refs=[ref])
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value
    assert excinfo.value.http_status == 409

    payload["knowledge_bases"][KB_NAME]["status"] = "rebuilding"
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SubjectOperationError) as excinfo:
        kb_scope.resolve_kb_ref(ref, mounted_refs=[ref])
    assert _code(excinfo.value) == ErrorCode.KB_NOT_READY.value

    # 完全没有状态记录的 legacy 全局库维持原语义（不因为"没记录"被拒）。
    payload["knowledge_bases"][KB_NAME].pop("status", None)
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    resolved = kb_scope.resolve_kb_ref(ref, mounted_refs=[ref])
    assert resolved.kb_ref == ref and resolved.status in ("", "unknown")


def test_subject_provider_binding_is_read_strictly_and_confined(libraries):
    """坏/链接 metadata 不能悄悄改选 provider（旧读取器会吞异常并跟链接）。"""
    subject = libraries["A"]
    config = Path(subject.knowledge_bases) / "kb_config.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["knowledge_bases"][KB_NAME].pop("rag_provider", None)
    config.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    metadata = libraries["kb_a"] / "metadata.json"
    external = Path(libraries["admin_root"]) / "external-binding.json"
    external.write_text('{"rag_provider": "pageindex"}', encoding="utf-8")

    metadata.symlink_to(external)
    with pytest.raises(SubjectStorageError) as excinfo:
        kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.STORAGE_IO.value

    metadata.unlink()
    metadata.write_text("{broken", encoding="utf-8")
    with pytest.raises(SubjectStorageError) as excinfo:
        kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert _code(excinfo.value) == ErrorCode.STORAGE_CORRUPT.value

    # 合法 legacy metadata 仍然被采纳（正例先于反例）。
    metadata.write_text('{"rag_provider": "pageindex"}', encoding="utf-8")
    resolved = kb_scope.resolve_kb_ref(libraries["ref_a"], expected_subject_id=subject.subject_id)
    assert resolved.provider == "pageindex"


def test_explicit_unknown_global_state_is_not_statusless_legacy(libraries):
    path = Path(libraries["global"]).parent / "kb_config.json"
    payload = json.loads(path.read_text())
    payload["knowledge_bases"][KB_NAME]["status"] = "unknown"
    path.write_text(json.dumps(payload))
    with pytest.raises(SubjectOperationError) as caught:
        kb_scope.resolve_kb_ref("admin:kb:" + KB_NAME, mounted_refs=["admin:kb:" + KB_NAME])
    assert caught.value.code is ErrorCode.KB_NOT_READY

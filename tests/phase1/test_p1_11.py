"""P1-11 行为测试：注册表/KB 记录接入与严格当前用户路径（C01/C03）。

覆盖卡的必证场景，每个都有正例与只改一个目标字段的反例：

* 并发同名创建全部拿到唯一 id，且都在 index 里；
* registry 损坏时不创建新科、不覆盖坏文件；
* knowledge upsert 保留其他记录与未知字段；
* 中文 id 合法；末尾 LF/CRLF/空格、分隔符、百分号、非法类型、symlink 越界都被拒绝；
* 当前用户路径解析失败时，不读不写管理员默认树（并给出"旧 helper 会 fallback"的坏对照）；
* tmp 普通用户 A/B 与 tmp 管理员的数据相互隔离。

这些都只在 tmp 隔离根里进行，不触碰真实六科数据。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from deeptutor.multi_user.models import CurrentUser
from deeptutor.multi_user.paths import scope_for_user, user_context
from deeptutor.services import path_service as path_service_mod
from deeptutor.services.path_service import PathService
from deeptutor.subjects import json_store as js_module
from deeptutor.subjects import store
from deeptutor.subjects.errors import (
    ErrorCode,
    StorageCorruptError,
    StorageIOError,
    SubjectOperationError,
    map_subject_exception,
)


def _user(user_id: str) -> CurrentUser:
    return CurrentUser(
        id=user_id,
        username=user_id,
        role="user",
        scope=scope_for_user(user_id, is_admin=False),
    )


def _index(subjects_root: Path) -> list[dict]:
    return json.loads((subjects_root / "index.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", ["description", "term", "created_at"])
def test_review_registry_null_is_corrupt_not_missing(p1_runtime, key):
    record = store.create_subject("null-registry")
    path = store.subjects_root() / "index.json"
    record[key] = None
    path.write_text(json.dumps([record]))
    before = path.read_bytes()
    with pytest.raises(StorageCorruptError):
        store.create_subject("must-not-publish")
    assert path.read_bytes() == before


def test_review_blank_name_update_cannot_make_registry_corrupt(p1_runtime):
    record = store.create_subject("valid")
    path = store.subjects_root() / "index.json"
    before = path.read_bytes()
    with pytest.raises(SubjectOperationError) as error:
        store.update_subject(record["id"], name="   ")
    assert error.value.code == ErrorCode.INVALID_INPUT
    assert path.read_bytes() == before
    assert store.get_subject(record["id"]) == record


@pytest.mark.parametrize("operation", ["root", "create", "kb", "materials"])
def test_review_store_directory_io_errors_are_typed(p1_runtime, monkeypatch, operation):
    record = store.create_subject("mkdir-error")
    root = store.subjects_root()
    directory = store.subject_dir(record["id"])
    target = {"root": root, "create": root / "new-subject",
              "kb": directory / "knowledge_bases", "materials": directory / "materials" / "pdf"}[operation]
    actual = Path.mkdir

    def denied(path, *args, **kwargs):
        if path == target:
            raise PermissionError("fake denied")
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(StorageIOError):
        if operation == "root":
            store.load_subjects()
        elif operation == "create":
            store.create_subject("new-subject")
        elif operation == "kb":
            store.subject_kb_base_dir(record["id"])
        else:
            store.materials_dir(record["id"], "pdf")


# ---------------------------------------------------------------------------
# 正例基准
# ---------------------------------------------------------------------------
def test_create_subject_appends_to_the_registry_and_builds_the_tree(p1_runtime: Path):
    record = store.create_subject("线性代数", description="第一学期", term="2026春")

    assert record["id"] == "线性代数"
    assert record["term"] == "2026春"
    assert isinstance(record["created_at"], int) and not isinstance(record["created_at"], bool)

    root = store.subjects_root()
    assert _index(root) == [record]
    subject = store.subject_dir(record["id"])
    assert (subject / "knowledge.json").is_file()
    assert json.loads((subject / "knowledge.json").read_text(encoding="utf-8")) == []
    assert (subject / "knowledge_bases").is_dir()
    assert (subject / "materials").is_dir()


def test_load_subjects_returns_empty_only_when_the_registry_is_missing(p1_runtime: Path):
    assert store.load_subjects() == []


def test_get_and_update_subject_round_trip(p1_runtime: Path):
    created = store.create_subject("离散数学", term="2026春")

    assert store.get_subject(created["id"]) == created

    updated = store.update_subject(created["id"], term="2027春", description="换了学期")
    assert updated is not None
    assert updated["term"] == "2027春"
    assert updated["description"] == "换了学期"
    assert store.get_subject("不存在") is None
    assert store.update_subject("不存在", term="x") is None


# ---------------------------------------------------------------------------
# 并发创建
# ---------------------------------------------------------------------------
def test_concurrent_same_name_creation_yields_unique_ids(p1_runtime: Path):
    workers = 8
    barrier = threading.Barrier(workers)
    created: list[dict] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=15)
            record = store.create_subject("并发科目")
        except BaseException as exc:  # pragma: no cover - 失败时上报
            errors.append(exc)
            return
        with lock:
            created.append(record)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    ids = [record["id"] for record in created]
    assert len(ids) == workers
    assert len(set(ids)) == workers  # 全部唯一，没有重名覆盖

    index_ids = [entry["id"] for entry in _index(store.subjects_root())]
    assert sorted(index_ids) == sorted(ids)  # 每一个都真的进了 index
    for subject_id in ids:
        assert (store.subject_dir(subject_id) / "knowledge.json").is_file()


# ---------------------------------------------------------------------------
# 损坏的 registry
# ---------------------------------------------------------------------------
def test_a_corrupt_registry_blocks_creation_and_is_not_overwritten(p1_runtime: Path):
    root = store.subjects_root()
    index = root / "index.json"
    original = '[{"id": "破折号", "term":'
    index.write_text(original, encoding="utf-8")

    with pytest.raises(StorageCorruptError):
        store.create_subject("新科目")

    assert index.read_text(encoding="utf-8") == original  # 坏文件保持原字节
    assert not (root / "新科目").exists()                 # 没有创建替代数据


def test_a_corrupt_registry_also_blocks_update(p1_runtime: Path):
    root = store.subjects_root()
    index = root / "index.json"
    index.write_text("not json at all", encoding="utf-8")

    with pytest.raises(StorageCorruptError):
        store.update_subject("任意", term="x")

    assert index.read_text(encoding="utf-8") == "not json at all"


def test_a_wrong_top_level_registry_is_corrupt(p1_runtime: Path):
    (store.subjects_root() / "index.json").write_text('{"id": "x"}', encoding="utf-8")

    with pytest.raises(StorageCorruptError):
        store.load_subjects()


def test_a_corrupt_registry_error_projects_as_storage_corrupt_without_echoing(
    p1_runtime: Path,
):
    marker = "p1-11-FAKE-REGISTRY-DO-NOT-LEAK"
    (store.subjects_root() / "index.json").write_text(f'{{"secret": "{marker}"', encoding="utf-8")

    with pytest.raises(StorageCorruptError) as excinfo:
        store.load_subjects()

    projected = map_subject_exception(excinfo.value)
    assert projected.code is ErrorCode.STORAGE_CORRUPT
    assert marker not in projected.message
    assert str(p1_runtime) not in projected.message


# ---------------------------------------------------------------------------
# knowledge 记录
# ---------------------------------------------------------------------------
def test_upsert_preserves_other_records_and_unknown_fields(p1_runtime: Path):
    subject = store.create_subject("数据结构")["id"]
    store.upsert_knowledge_record(
        subject,
        {"kb_name": "教材库", "legacy_flag": True, "nested": {"keep": [1, 2]}},
    )
    store.upsert_knowledge_record(subject, {"kb_name": "题库", "status": "ready"})

    records = {r["kb_name"]: r for r in store.load_knowledge_records(subject)}
    assert set(records) == {"教材库", "题库"}
    assert records["教材库"]["legacy_flag"] is True          # 未知历史字段保留
    assert records["教材库"]["nested"] == {"keep": [1, 2]}

    store.upsert_knowledge_record(
        subject, {"kb_name": "教材库", "status": "indexed", "extra": 1}
    )
    after = store.load_knowledge_records(subject)
    by_name = {r["kb_name"]: r for r in after}
    assert len(after) == 2                                    # 没有重复追加
    # R4：更新是"与匹配记录合并"，未提供的旧字段（含未知 legacy）必须保留
    assert by_name["教材库"] == {
        "kb_name": "教材库",
        "status": "indexed",
        "extra": 1,
        "legacy_flag": True,
        "nested": {"keep": [1, 2]},
    }
    assert by_name["题库"] == {"kb_name": "题库", "status": "ready"}  # 别的记录没被动过


def test_knowledge_record_without_a_valid_kb_name_is_corrupt(p1_runtime: Path):
    subject = store.create_subject("操作系统")["id"]
    path = store.subject_dir(subject) / "knowledge.json"
    path.write_text(json.dumps([{"status": "ready"}]), encoding="utf-8")

    with pytest.raises(StorageCorruptError) as excinfo:
        store.load_knowledge_records(subject)
    assert excinfo.value.record_index == 0

    with pytest.raises(StorageCorruptError):
        store.upsert_knowledge_record(subject, {"kb_name": "新库"})
    # 坏文件保持不变
    assert json.loads(path.read_text(encoding="utf-8")) == [{"status": "ready"}]


def test_upsert_rejects_a_record_without_kb_name(p1_runtime: Path):
    """R4：缺 kb_name 是**调用参数**错误（400），不是磁盘损坏。"""
    subject = store.create_subject("编译原理")["id"]

    with pytest.raises(js_module.InvalidInputError) as excinfo:
        store.upsert_knowledge_record(subject, {"status": "ready"})
    assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT

    with pytest.raises(js_module.InvalidInputError):
        store.upsert_knowledge_record(subject, [])  # 非对象也不是损坏


def test_concurrent_upserts_do_not_lose_records(p1_runtime: Path):
    subject = store.create_subject("并发知识库")["id"]
    workers = 6
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            store.upsert_knowledge_record(subject, {"kb_name": f"库-{index}"})
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    names = sorted(r["kb_name"] for r in store.load_knowledge_records(subject))
    assert names == sorted(f"库-{i}" for i in range(workers))


# ---------------------------------------------------------------------------
# id 校验
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "subject_id",
    ["math", "线性代数", "a1-b2", "x" * 64],
)
def test_valid_subject_ids(subject_id: str):
    assert store.is_valid_subject_id(subject_id) is True


@pytest.mark.parametrize(
    "subject_id",
    [
        "math\n",          # 末尾 LF：``$`` 会匹配它，fullmatch 不会
        "math\r\n",
        "math\r",
        "math ",
        " math",
        "math/../etc",
        "..",
        ".",
        "a/b",
        "a\\b",
        "a%b",
        "a%2fb",
        "",
        "-leading",
        "x" * 65,
        "Math",            # slug 一律小写
        "科目 A",
    ],
)
def test_invalid_subject_ids(subject_id: str):
    assert store.is_valid_subject_id(subject_id) is False


@pytest.mark.parametrize("subject_id", [None, 7, b"math", ["math"], {"id": "math"}])
def test_non_string_subject_ids_are_rejected(subject_id):
    assert store.is_valid_subject_id(subject_id) is False


def test_invalid_ids_cannot_become_paths(p1_runtime: Path):
    store.create_subject("合法科目")
    root = store.subjects_root()
    before = sorted(p.name for p in root.iterdir())

    for bad in ["math\n", "../admin", "a/b", "x" * 65]:
        with pytest.raises(store.InvalidSubjectIdError) as excinfo:
            store.subject_dir(bad)
        projected = map_subject_exception(excinfo.value)
        assert projected.code is ErrorCode.INVALID_SUBJECT_ID
        assert projected.http_status == 400
        assert projected.retryable is False

    assert sorted(p.name for p in root.iterdir()) == before


def test_a_symlinked_subject_directory_is_refused(p1_runtime: Path):
    root = store.subjects_root()
    outside = p1_runtime / "user" / "elsewhere"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "knowledge.json").write_text('[{"kb_name": "admin-only"}]', encoding="utf-8")
    (root / "linked").symlink_to(outside)

    with pytest.raises(StorageIOError) as excinfo:
        store.subject_dir("linked")
    assert map_subject_exception(excinfo.value).code is ErrorCode.STORAGE_IO

    with pytest.raises(StorageIOError):
        store.load_knowledge_records("linked")


def test_upsert_into_a_symlinked_subject_does_not_touch_the_target(p1_runtime: Path):
    root = store.subjects_root()
    outside = p1_runtime / "user" / "victim"
    outside.mkdir(parents=True, exist_ok=True)
    victim = outside / "knowledge.json"
    victim.write_text('[{"kb_name": "victim"}]', encoding="utf-8")
    (root / "linked").symlink_to(outside)

    with pytest.raises(StorageIOError):
        store.upsert_knowledge_record("linked", {"kb_name": "attacker"})

    assert json.loads(victim.read_text(encoding="utf-8")) == [{"kb_name": "victim"}]


# ---------------------------------------------------------------------------
# 严格当前用户路径
# ---------------------------------------------------------------------------
def test_scope_resolution_failure_never_reads_or_writes_the_admin_tree(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """当前用户解析失败时必须报错；管理员默认实例一次都不能被碰到。"""
    calls = {"get_instance": 0, "workspace_read": 0}

    def spy_get_instance(cls):
        calls["get_instance"] += 1

        class _AdminSpy:
            def get_workspace_dir(self) -> Path:
                calls["workspace_read"] += 1
                return p1_runtime / "user" / "workspace"

        return _AdminSpy()

    def explode():
        raise RuntimeError("current user scope resolution failed")

    monkeypatch.setattr(
        "deeptutor.multi_user.paths.get_current_path_service", explode
    )
    monkeypatch.setattr(PathService, "get_instance", classmethod(spy_get_instance))

    with pytest.raises(RuntimeError, match="scope resolution failed"):
        store.subjects_root()
    with pytest.raises(RuntimeError):
        store.load_subjects()
    with pytest.raises(RuntimeError):
        store.create_subject("不该被创建")

    assert calls == {"get_instance": 0, "workspace_read": 0}
    assert not (p1_runtime / "user" / "workspace" / "subjects" / "不该被创建").exists()


def test_bad_control_the_generic_helper_would_fall_back_to_admin(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """坏对照：同一个故障下，通用 get_path_service 确实回退到管理员实例。

    这条证明上面那条"spy 计数为 0"是承重的——如果 store 用了通用 helper，
    计数就不会是 0。
    """
    calls = {"get_instance": 0}

    def spy_get_instance(cls):
        calls["get_instance"] += 1
        return PathService.get_instance.__wrapped__(cls) if hasattr(
            PathService.get_instance, "__wrapped__"
        ) else object()

    def explode():
        raise RuntimeError("current user scope resolution failed")

    monkeypatch.setattr(
        "deeptutor.multi_user.paths.get_current_path_service", explode
    )
    monkeypatch.setattr(PathService, "get_instance", classmethod(spy_get_instance))

    path_service_mod.get_path_service()  # 通用 helper

    assert calls["get_instance"] == 1  # 它吞掉异常并回退了


# ---------------------------------------------------------------------------
# 用户隔离
# ---------------------------------------------------------------------------
def test_user_a_user_b_and_admin_trees_stay_separate(p1_runtime: Path):
    admin_record = store.create_subject("管理员科目")

    with user_context(_user("user-a")):
        a_root = store.subjects_root()
        a_record = store.create_subject("甲的科目")
        store.upsert_knowledge_record(a_record["id"], {"kb_name": "甲库"})

    with user_context(_user("user-b")):
        b_root = store.subjects_root()
        b_record = store.create_subject("乙的科目")

    assert a_root != b_root
    assert a_root.is_relative_to(p1_runtime / "users" / "user-a")
    assert b_root.is_relative_to(p1_runtime / "users" / "user-b")
    assert store.subjects_root().is_relative_to(p1_runtime / "user" / "workspace")

    # A 看不见 B / 管理员的东西
    with user_context(_user("user-a")):
        ids = [s["id"] for s in store.load_subjects()]
        assert ids == [a_record["id"]]
        assert store.get_subject(b_record["id"]) is None
        assert store.get_subject(admin_record["id"]) is None
        assert [r["kb_name"] for r in store.load_knowledge_records(a_record["id"])] == ["甲库"]

    with user_context(_user("user-b")):
        assert [s["id"] for s in store.load_subjects()] == [b_record["id"]]
        # A 的科目不在 B 的注册表里 —— 对 B 而言是 404，不是"空集合"
        with pytest.raises(store.SubjectNotFoundError) as excinfo:
            store.load_knowledge_records(a_record["id"])
        assert map_subject_exception(excinfo.value).code is ErrorCode.SUBJECT_NOT_FOUND
        assert not (b_root / a_record["id"]).exists()
        # 在 B 里写同名科目不会碰到 A 的数据
        store.upsert_knowledge_record(b_record["id"], {"kb_name": "B库"})

    with user_context(_user("user-a")):
        assert [r["kb_name"] for r in store.load_knowledge_records(a_record["id"])] == ["甲库"]

    assert [s["id"] for s in store.load_subjects()] == [admin_record["id"]]


def test_the_same_subject_name_in_two_users_does_not_collide(p1_runtime: Path):
    with user_context(_user("user-a")):
        a = store.create_subject("同名科目")
    with user_context(_user("user-b")):
        b = store.create_subject("同名科目")

    assert a["id"] == b["id"] == "同名科目"  # 同一个 slug
    # 但落在各自的根里，互不影响
    with user_context(_user("user-a")):
        store.upsert_knowledge_record(a["id"], {"kb_name": "A库"})
        assert [r["kb_name"] for r in store.load_knowledge_records(a["id"])] == ["A库"]
    with user_context(_user("user-b")):
        assert store.load_knowledge_records(b["id"]) == []


# ---------------------------------------------------------------------------
# R1（rework01）：读取前就必须拒绝越界目标
# ---------------------------------------------------------------------------
_CONSUMERS = (
    ("wrong_book", "wrong_book.json"),
    ("exam_points", "exam_points.json"),
    ("knowledge_points", "knowledge_points.json"),
    ("profile", "profile.json"),
)


def _consumer_module(name: str):
    from deeptutor.subjects import exam_points, knowledge_points, profile, wrong_book

    return {
        "wrong_book": wrong_book,
        "exam_points": exam_points,
        "knowledge_points": knowledge_points,
        "profile": profile,
    }[name]


@pytest.mark.parametrize("module_name,filename", _CONSUMERS)
def test_readers_reject_a_cross_subject_symlink_before_reading(
    p1_runtime: Path, module_name: str, filename: str, monkeypatch: pytest.MonkeyPatch
):
    """A 的数据文件指向 B 时，load(A) 必须在不读 B 的前提下失败。"""
    module = _consumer_module(module_name)
    a = store.create_subject("symlink-a")["id"]
    b = store.create_subject("symlink-b")["id"]
    root = store.subjects_root()

    # 先各自写一份真实数据，证明基准是合法的
    if module_name == "wrong_book":
        module.add_entry(a, question="alpha")
        module.add_entry(b, question="beta")
    elif module_name == "exam_points":
        module.add_point(a, content="alpha")
        module.add_point(b, content="beta")
    elif module_name == "knowledge_points":
        module.add_point(a, name="alpha")
        module.add_point(b, name="beta")
    else:
        module.update(a, goals="alpha")
        module.update(b, goals="beta")

    assert module.load(a)

    link = root / a / filename
    victim = root / b / filename
    link.unlink()
    link.symlink_to(victim)

    reads: list[str] = []
    real_open = os.open

    def spying_open(target: object, flags: int, *args: object, **kwargs: object) -> int:
        try:
            if Path(str(target)).resolve() == victim.resolve():
                reads.append(str(target))
        except OSError:  # pragma: no cover - defensive
            pass
        return real_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spying_open)

    with pytest.raises((StorageIOError, StorageCorruptError, SubjectOperationError)):
        module.load(a)

    assert reads == [], "在拒绝之前已经读到了别的科目的数据"
    assert victim.is_file()  # 受害文件仍在


def test_the_subjects_root_itself_cannot_be_a_symlink(p1_runtime: Path):
    root = store.subjects_root()
    outside = p1_runtime / "user" / "outside-subjects"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "index.json").write_text(
        json.dumps([{"id": "foreign", "name": "foreign"}]), encoding="utf-8"
    )
    root.rename(root.with_name("subjects-original"))
    root.symlink_to(outside, target_is_directory=True)

    with pytest.raises((StorageIOError, SubjectOperationError)):
        store.load_subjects()
    with pytest.raises((StorageIOError, SubjectOperationError)):
        store.create_subject("不应创建")


def test_kb_and_material_helpers_confine_their_subdirectories(p1_runtime: Path):
    subject = store.create_subject("目录防护")["id"]
    victim = p1_runtime / "user" / "outside-kb"
    victim.mkdir(parents=True, exist_ok=True)

    kb = store.subject_dir(subject) / "knowledge_bases"
    kb.rmdir()
    kb.symlink_to(victim, target_is_directory=True)

    with pytest.raises((StorageIOError, SubjectOperationError)):
        store.subject_kb_base_dir(subject)
    with pytest.raises((StorageIOError, SubjectOperationError)):
        store.materials_dir(subject, "../../../escape")

    assert list(victim.iterdir()) == []  # 外部目录里没有新建任何东西


def test_a_symlinked_subject_directory_is_refused_before_any_read(p1_runtime: Path):
    store.create_subject("真实科目")
    root = store.subjects_root()
    other = root / "另一科"
    other.mkdir()
    (other / "wrong_book.json").write_text('[{"id": "x", "question": "other"}]', encoding="utf-8")
    (root / "linked").symlink_to(other, target_is_directory=True)

    reads: list[str] = []
    real_open = os.open

    def spying_open(target: object, flags: int, *args: object, **kwargs: object) -> int:
        reads.append(str(target))
        return real_open(target, flags, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", spying_open)
        with pytest.raises((StorageIOError, SubjectOperationError)):
            store.subject_dir("linked")

    assert reads == []


# ---------------------------------------------------------------------------
# R2（rework01）：注册表身份、创建提交与存在性
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_id", [None, 5, [], "bad/id", "UPPER", "", "x" * 65])
def test_registry_records_are_validated_before_creating(p1_runtime: Path, bad_id):
    subject = store.create_subject("基准科目")
    path = store.subjects_root() / "index.json"
    base = json.loads(path.read_text(encoding="utf-8"))
    records = json.loads(json.dumps(base))
    records[0]["id"] = bad_id
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError):
        store.create_subject("gamma")

    assert path.read_bytes() == before
    assert subject["id"] == "基准科目"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda records: records[0].pop("id"),
        lambda records: records[0].pop("name"),
        lambda records: records[0].update({"name": 5}),
        lambda records: records[0].update({"description": 5}),
        lambda records: records[0].update({"term": []}),
        lambda records: records[0].update({"created_at": True}),
        lambda records: records.append(dict(records[0])),  # 重复身份
    ],
)
def test_malformed_registry_fields_block_creation(p1_runtime: Path, mutate):
    store.create_subject("基准科目二")
    path = store.subjects_root() / "index.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    mutate(records)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(StorageCorruptError):
        store.create_subject("新科目")

    assert path.read_bytes() == before


def test_unknown_subject_does_not_create_a_learning_tree(p1_runtime: Path):
    from deeptutor.subjects import wrong_book

    root = store.subjects_root()
    destination = root / "unregistered"

    with pytest.raises(store.SubjectNotFoundError) as excinfo:
        wrong_book.add_entry("unregistered", question="ghost")

    assert map_subject_exception(excinfo.value).code is ErrorCode.SUBJECT_NOT_FOUND
    assert not destination.exists()


@pytest.mark.parametrize(
    "action",
    [
        lambda sid: _consumer_module("wrong_book").add_entry(sid, question="q"),
        lambda sid: _consumer_module("exam_points").add_point(sid, content="c"),
        lambda sid: _consumer_module("knowledge_points").add_point(sid, name="n"),
        lambda sid: _consumer_module("profile").update(sid, goals="g"),
        lambda sid: store.upsert_knowledge_record(sid, {"kb_name": "kb"}),
        lambda sid: store.load_knowledge_records(sid),
        lambda sid: store.subject_kb_base_dir(sid),
    ],
)
def test_no_ordinary_entry_point_can_create_an_unregistered_subject(p1_runtime: Path, action):
    root = store.subjects_root()
    with pytest.raises(store.SubjectNotFoundError):
        action("ghost")
    assert not (root / "ghost").exists()


def test_orphan_tree_is_not_overwritten_by_create(p1_runtime: Path):
    root = store.subjects_root()
    orphan = root / "orphan"
    orphan.mkdir()
    knowledge = orphan / "knowledge.json"
    old = b'[{"kb_name":"old-kb","legacy":true}]'
    knowledge.write_bytes(old)

    result = store.create_subject("orphan")

    assert result["id"] != "orphan"          # 换了一个唯一 id
    assert knowledge.read_bytes() == old     # 未注册的树没被动过
    assert result["id"] in [s["id"] for s in store.load_subjects()]
    assert (root / result["id"] / "knowledge.json").is_file()


def test_a_symlinked_orphan_is_not_adopted(p1_runtime: Path):
    root = store.subjects_root()
    outside = p1_runtime / "user" / "outside-orphan"
    outside.mkdir(parents=True, exist_ok=True)
    (root / "linked-orphan").symlink_to(outside, target_is_directory=True)

    result = store.create_subject("linked-orphan")

    assert result["id"] != "linked-orphan"
    assert list(outside.iterdir()) == []
    assert (root / "linked-orphan").is_symlink()


def test_tree_preparation_failure_does_not_publish_a_registry_entry(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    store.create_subject("基准科目三")
    path = store.subjects_root() / "index.json"
    before = path.read_bytes()

    def explode(_subject_id: str) -> None:
        raise StorageIOError("controlled preparation failure")

    monkeypatch.setattr(store, "_initialize_subject_tree", explode)

    with pytest.raises(StorageIOError):
        store.create_subject("failing")

    assert path.read_bytes() == before
    assert store.get_subject("failing") is None
    assert not (store.subjects_root() / "failing").exists()  # 本次新建的内容已清理


def test_registry_write_failure_removes_the_prepared_tree(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    """提交阶段失败：不返回成功、注册表旧字节保持、本次新建的树被清掉。"""
    path = store.subjects_root() / "index.json"
    store.create_subject("先有的科目")
    before = path.read_bytes()

    real = js_module.atomic_write_json

    def fail_on_index(target, payload):
        if Path(target).name == "index.json":
            raise OSError(28, "No space left on device")
        return real(target, payload)

    monkeypatch.setattr(js_module, "atomic_write_json", fail_on_index)

    with pytest.raises(StorageIOError):
        store.create_subject("提交失败科目")

    monkeypatch.undo()
    assert path.read_bytes() == before
    assert store.get_subject("提交失败科目") is None
    assert not (store.subjects_root() / "提交失败科目").exists()


def test_blank_subject_name_is_invalid_input(p1_runtime: Path):
    root = store.subjects_root()
    before = sorted(p.name for p in root.iterdir())

    for bad in ("   ", "", "\n\t"):
        with pytest.raises(js_module.InvalidInputError) as excinfo:
            store.create_subject(bad)
        assert map_subject_exception(excinfo.value).code is ErrorCode.INVALID_INPUT

    assert sorted(p.name for p in root.iterdir()) == before

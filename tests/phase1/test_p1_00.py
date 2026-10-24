"""P1-00 行为测试。

覆盖卡要求的四类独立场景（每类都有正向与反向断言）：

1. 已有 dirty + untracked + 删除文件可准确重建，且归档的是工作树内容而不是 HEAD；
2. 虚构 secret / .env / data 树不得进入快照，也不得出现在证据记录里；
3. 写快照失败（含写到一半失败）不修改原树、不留半成品；
4. 合法增量通过、白名单外增量被拒绝，且**未归档**的未知新源码同样会被发现。

另含真实仓库与真实数据保护树的集成核验。

全部使用 tmp 中的合成 Git 工作树与虚构 secret；只用标准库；不导入任何业务模块，
因此不会触发真实配置读写，也不依赖 P1-01 尚未建立的夹具。
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "phase1_snapshot.py"
EVIDENCE_DIR = REPO_ROOT / ".phase1-evidence" / "P1-00"
SECRET_SENTINEL = "P1-00-FAKE-SECRET-e3f1a9c2-DO-NOT-LEAK"

ALLOWED = [".gitignore", "scripts/phase1_snapshot.py", "tests/phase1/test_p1_00.py"]

WHITELISTED_UNTRACKED = (
    "deeptutor/subjects/generation.py",
    "deeptutor/utils/document_images.py",
    "HANDOVER.md",
    "PROJECT_AUDIT_2026-10-10.md",
    "plans/phase1/cards/P1-00.md",
)


def _load_snapshot_module():
    spec = importlib.util.spec_from_file_location("phase1_snapshot_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SNAP = _load_snapshot_module()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status_paths(root: Path) -> tuple[list[str], list[str], list[str]]:
    modified: list[str] = []
    deleted: list[str] = []
    untracked: list[str] = []
    for line in SNAP.git_status_lines(root):
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        elif "D" in code:
            deleted.append(path)
        elif "M" in code:
            modified.append(path)
    return modified, deleted, untracked


@pytest.fixture()
def synth_repo(tmp_path: Path) -> Path:
    """合成 Git 工作树：1 个 dirty、1 个删除、白名单内外的未跟踪文件、虚构 secret。"""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "p1-00@example.invalid")
    _git(root, "config", "user.name", "P1-00 Test")
    _git(root, "config", "commit.gpgsign", "false")

    _write(root, "src/app.py", "APP = 'committed'\n")
    _write(root, "src/gone.py", "GONE = 'committed'\n")
    _write(root, ".env.example", "DEEPTUTOR_HOME=\n")
    _write(root, "data/user/settings/model_catalog.json", "{}\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")

    # 前人未提交的工作树状态
    _write(root, "src/app.py", "APP = 'dirty-worktree'\n")
    (root / "src/gone.py").unlink()
    for rel in WHITELISTED_UNTRACKED:
        _write(root, rel, f"# {rel}\n")
    _write(root, "scratch_unknown.py", "UNKNOWN = 1\n")
    _write(root, "data/user/settings/secret.json", '{"api_key": "%s"}\n' % SECRET_SENTINEL)
    _write(root, ".env", "DEEPSEEK_API_KEY=%s\n" % SECRET_SENTINEL)
    return root


# ---------------------------------------------------------------------------
# 1. 可准确重建
# ---------------------------------------------------------------------------
def test_dirty_untracked_and_deleted_sources_rebuild_exactly(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-before")
    archived = before["archived_files"]

    # dirty 文件按工作树内容归档，而不是 HEAD 内容
    head_sha = hashlib.sha256(SNAP.git(root, "show", "HEAD:src/app.py")).hexdigest()
    assert archived["src/app.py"]["sha256"] == _sha256_file(root / "src/app.py")
    assert archived["src/app.py"]["sha256"] != head_sha

    # 删除的已跟踪文件被记录，且不在归档内
    assert "src/gone.py" not in archived
    assert before["deleted_tracked_files"]["src/gone.py"]["head_blob"] is not None
    assert before["deleted_tracked_files"]["src/gone.py"]["head_size"] > 0

    for rel in WHITELISTED_UNTRACKED:
        assert rel in archived, rel

    assert before["git_status_counts"]["modified"] == 1
    assert before["git_status_counts"]["deleted"] == 1

    archive = tmp_path / "snapshot.tar.gz"
    info = SNAP.build_archive(root, before, archive)
    assert info["entry_count"] == len(archived)

    baseline = dict(before)
    baseline["archive_sha256"] = info["archive_sha256"]
    report = SNAP.verify_rebuild(baseline, archive, tmp_path / "rebuild")

    assert report["ok"] is True
    assert report["missing"] == []
    assert report["unexpected"] == []
    assert report["hash_mismatches"] == []
    assert report["deleted_files_unexpectedly_present"] == []
    assert report["deleted_files_confirmed_absent"] == ["src/gone.py"]
    assert report["rebuilt_count"] == len(archived)

    # 重建出来的确实是未提交内容，且删除状态被保留
    assert (tmp_path / "rebuild" / "src/app.py").read_text(encoding="utf-8") == (
        "APP = 'dirty-worktree'\n"
    )
    assert not (tmp_path / "rebuild" / "src/gone.py").exists()
    assert (tmp_path / "rebuild" / "HANDOVER.md").is_file()


def test_archive_bytes_are_deterministic(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-det")
    first = SNAP.build_archive(root, before, tmp_path / "a.tar.gz")
    second = SNAP.build_archive(root, before, tmp_path / "b.tar.gz")
    assert first["archive_sha256"] == second["archive_sha256"]


def test_archive_refuses_entry_changed_after_capture(synth_repo, tmp_path):
    """归档取自当前工作树，因此 capture 之后被改动的条目必须让归档失败。

    改动刻意保持**字节长度不变**：只有 sha256 比对能发现它，size 比对不能。
    """
    root = synth_repo
    before = SNAP.capture(root, "synthetic-stale")

    original = (root / "src/app.py").read_text(encoding="utf-8")
    tampered = original[:-2] + "X\n"
    assert len(tampered) == len(original)
    assert tampered != original
    _write(root, "src/app.py", tampered)

    out = tmp_path / "stale.tar.gz"
    with pytest.raises(RuntimeError, match="changed since capture"):
        SNAP.build_archive(root, before, out)
    assert not out.exists()
    assert not out.with_name(out.name + ".part").exists()


# ---------------------------------------------------------------------------
# 2. 秘密排除
# ---------------------------------------------------------------------------
def test_secret_and_env_content_never_enter_snapshot(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-secret")
    archived = before["archived_files"]

    # fixture 自身确实含 sentinel —— 保证下面的“不存在”不是空断言
    assert SECRET_SENTINEL in (root / ".env").read_text(encoding="utf-8")
    assert SECRET_SENTINEL in (root / "data/user/settings/secret.json").read_text("utf-8")

    assert ".env" not in archived
    assert "data/user/settings/secret.json" not in archived
    assert "data/user/settings/model_catalog.json" not in archived
    assert "data/user/settings/model_catalog.json" in before["excluded_tracked_files"]

    # .env.example 是已跟踪模板，必须仍然归档
    assert ".env.example" in archived

    # data/ 整个不进入监控与归档
    assert not any(rel.startswith("data/") for rel in before["monitored_files"])
    assert not any(rel.startswith("data/") for rel in archived)

    archive = tmp_path / "secret-check.tar.gz"
    SNAP.build_archive(root, before, archive)
    with tarfile.open(archive, "r:gz") as tar:
        payloads = [tar.extractfile(m).read() for m in tar if m.isfile()]
    assert not any(SECRET_SENTINEL.encode() in value for value in payloads)

    record = json.dumps(before, ensure_ascii=False)
    assert SECRET_SENTINEL not in record
    assert "DEEPSEEK_API_KEY" not in record


def test_protection_record_carries_digests_only():
    payload = SNAP.protect_data(REPO_ROOT)
    settings = payload["roots"]["settings"]
    assert settings["exists"] is True
    assert "model_catalog.json" in settings["files"]

    for rel, entry in settings["files"].items():
        if entry["kind"] != "file":
            continue
        assert set(entry) == {"kind", "sha256", "size", "mode"}, rel
        assert len(entry["sha256"]) == 64
        int(entry["sha256"], 16)

    blob = json.dumps(payload, ensure_ascii=False)
    for leaked in ("api_key", "access_token", "refresh_token", "Authorization"):
        assert leaked not in blob


# ---------------------------------------------------------------------------
# 3. 失败不改原树
# ---------------------------------------------------------------------------
def test_snapshot_write_failure_leaves_source_tree_untouched(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-failure")
    baseline_state = SNAP.scan_tree(root)

    # (a) 拒绝写进项目树（.phase1-evidence/ 之外）
    with pytest.raises(ValueError):
        SNAP.guard_write_target(root, root / "snapshot.tar.gz")
    with pytest.raises(ValueError):
        SNAP.guard_write_target(root, root / "src" / "sneaky.tar.gz")

    # (b) 输出父路径是普通文件 -> OS 错误
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("regular file")
    with pytest.raises(OSError):
        SNAP.build_archive(root, before, blocked_parent / "child.tar.gz")

    # (c) 写到一半失败：不留半成品，目标文件不出现
    bogus = json.loads(json.dumps(before))
    bogus["archived_files"]["src/definitely_missing.py"] = {
        "kind": "file",
        "sha256": "0" * 64,
        "size": 1,
    }
    out = tmp_path / "partial.tar.gz"
    with pytest.raises((FileNotFoundError, OSError, RuntimeError)):
        SNAP.build_archive(root, bogus, out)
    assert not out.exists()
    assert not out.with_name(out.name + ".part").exists()

    assert SNAP.scan_tree(root) == baseline_state


def test_verify_rebuild_refuses_to_reuse_non_empty_workdir(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-reuse")
    archive = tmp_path / "reuse.tar.gz"
    info = SNAP.build_archive(root, before, archive)
    before["archive_sha256"] = info["archive_sha256"]

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / "keep.txt").write_text("do not delete\n", encoding="utf-8")

    with pytest.raises(ValueError):
        SNAP.verify_rebuild(before, archive, workdir)
    assert (workdir / "keep.txt").read_text(encoding="utf-8") == "do not delete\n"


def test_read_failure_is_not_silently_ignored(synth_repo, monkeypatch):
    def boom(path):
        raise PermissionError(f"simulated unreadable file: {path.name}")

    monkeypatch.setattr(SNAP, "sha256_stream", boom)
    with pytest.raises(PermissionError):
        SNAP.scan_tree(synth_repo)
    with pytest.raises(PermissionError):
        SNAP.capture(synth_repo, "synthetic-readfail")
    with pytest.raises(PermissionError):
        SNAP.protect_one(synth_repo, "src")


# ---------------------------------------------------------------------------
# 4. 范围检查
# ---------------------------------------------------------------------------
def test_allowed_increment_passes_and_out_of_scope_increment_is_rejected(synth_repo):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-scope-before")

    _write(root, ".gitignore", "build/\n")
    _write(root, "scripts/phase1_snapshot.py", "# snapshot tool\n")
    _write(root, "tests/phase1/test_p1_00.py", "# tests\n")
    _write(root, "src/app.py", "APP = 'tampered'\n")
    _write(root, "deeptutor/rogue_brand_new.py", "ROGUE = 1\n")
    (root / ".env.example").unlink()

    after = SNAP.capture(root, "synthetic-scope-after")
    report = SNAP.compare(before, after, ALLOWED)

    assert report["ok"] is False
    assert "src/app.py" in report["outside_changes"]
    assert "deeptutor/rogue_brand_new.py" in report["outside_changes"]
    assert ".env.example" in report["outside_changes"]
    assert ".gitignore" in report["allowed_changes"]
    assert "scripts/phase1_snapshot.py" in report["allowed_changes"]
    assert "tests/phase1/test_p1_00.py" in report["allowed_changes"]
    # 允许路径的祖先目录也算允许，否则新建 tests/phase1/ 会误报
    assert "tests/phase1" in report["allowed_changes"]

    # 未归档的未知新源码仍被范围检查发现
    assert "deeptutor/rogue_brand_new.py" not in after["archived_files"]
    assert "deeptutor/rogue_brand_new.py" in after["monitored_files"]

    # 纯白名单增量必须通过
    before_clean = SNAP.capture(root, "synthetic-clean-before")
    _write(root, ".gitignore", "build/\ncoverage/\n")
    clean = SNAP.compare(before_clean, SNAP.capture(root, "synthetic-clean-after"), ALLOWED)
    assert clean["ok"] is True
    assert clean["outside_changes"] == []
    assert clean["allowed_changes"] == [".gitignore"]


def test_symlinks_are_recorded_and_never_followed(synth_repo, tmp_path):
    root = synth_repo
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leaked.txt").write_text("outside\n", encoding="utf-8")
    os.symlink(outside, root / "linked_dir")
    os.symlink(outside / "leaked.txt", root / "linked_file.txt")

    before = SNAP.capture(root, "synthetic-symlink")
    assert before["monitored_files"]["linked_dir"]["kind"] == "symlink"
    assert before["monitored_files"]["linked_dir"]["target"] == str(outside)
    assert before["monitored_files"]["linked_file.txt"]["kind"] == "symlink"
    assert "linked_dir/leaked.txt" not in before["monitored_files"]


# ---------------------------------------------------------------------------
# 真实数据保护
# ---------------------------------------------------------------------------
def test_protection_distinguishes_missing_empty_and_detects_changes(tmp_path):
    root = tmp_path / "datasynth"
    (root / "present").mkdir(parents=True)
    (root / "present" / "a.json").write_text("{}\n", encoding="utf-8")
    (root / "empty").mkdir()

    missing = SNAP.protect_one(root, "absent")
    empty = SNAP.protect_one(root, "empty")
    assert missing["exists"] is False
    assert empty["exists"] is True
    assert empty["file_count"] == 0
    assert missing != empty

    (root / "empty" / "zero.bin").write_bytes(b"")
    zero = SNAP.protect_one(root, "empty")
    assert zero["files"]["zero.bin"]["size"] == 0

    def snap(pid: str) -> dict:
        return {"roots": {"r": SNAP.protect_one(root, "present")}, "protection_id": pid}

    base = snap("base")
    assert SNAP.compare_data(base, snap("base"))["ok"] is True

    (root / "present" / "b.json").write_text("{}\n", encoding="utf-8")
    added = SNAP.compare_data(base, snap("added"))
    assert added["ok"] is False
    assert added["roots"]["r"]["added"] == ["b.json"]

    pre_modify = snap("pre-modify")
    (root / "present" / "a.json").write_text('{"changed": 1}\n', encoding="utf-8")
    modified = SNAP.compare_data(pre_modify, snap("post-modify"))
    assert modified["ok"] is False
    assert modified["roots"]["r"]["modified"] == ["a.json"]

    pre_remove = snap("pre-remove")
    (root / "present" / "b.json").unlink()
    removed = SNAP.compare_data(pre_remove, snap("post-remove"))
    assert removed["ok"] is False
    assert removed["roots"]["r"]["removed"] == ["b.json"]

    gone = {"roots": {"r": SNAP.protect_one(root, "nope")}, "protection_id": "gone"}
    existence = SNAP.compare_data(base, gone)
    assert existence["ok"] is False
    assert existence["roots"]["r"]["existence_changed"] is True


def test_real_protected_trees_exist_and_are_unchanged():
    first = SNAP.protect_data(REPO_ROOT)
    for name in SNAP.PROTECTED_DATA_ROOTS:
        entry = first["roots"][name]
        assert entry["exists"] is True, name
        assert entry["file_count"] >= 1, name

    second = SNAP.protect_data(REPO_ROOT)
    assert SNAP.compare_data(first, second)["ok"] is True

    recorded = EVIDENCE_DIR / "real_data_protection_baseline.json"
    if recorded.is_file():
        spec = importlib.util.spec_from_file_location(
            "phase1_data_baseline", REPO_ROOT / "scripts/phase1_data_baseline.py"
        )
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        baseline = guard.load_data_baseline(REPO_ROOT, recorded)
        # Keep validating the historical S14 exception; compare today's data
        # with the runner's pinned pre-bootstrap snapshot. Normal user changes
        # after S15 closure must not be undone to run the suite.
        import hashlib
        import os
        raw_path = Path(os.environ["SELFLEARN_TEST_DATA_BASELINE"])
        assert raw_path.resolve().is_relative_to(Path(os.environ["SELFLEARN_TEST_ROOT"]).resolve())
        raw = raw_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == os.environ["SELFLEARN_TEST_DATA_BASELINE_SHA256"]
        current_baseline = json.loads(raw)
        assert current_baseline["root"] == str(REPO_ROOT)
        assert set(current_baseline["roots"]) == set(baseline["roots"])
        comparison = SNAP.compare_data(current_baseline, first)
        assert comparison["ok"] is True, json.dumps(comparison, ensure_ascii=False)
        if "supplementary_roots" in current_baseline:
            assert SNAP.compare_data(
                {"roots": current_baseline["supplementary_roots"]},
                {"roots": first["supplementary_roots"]},
            )["ok"] is True


# ---------------------------------------------------------------------------
# 真实仓库集成核验
# ---------------------------------------------------------------------------
def test_real_repo_snapshots_dirty_content_and_preserves_deletions():
    before = SNAP.capture(REPO_ROOT, "p1-00-test-real")
    archived = before["archived_files"]

    modified, deleted, _untracked = _status_paths(REPO_ROOT)
    assert modified, "expected inherited uncommitted modifications to exist"
    assert deleted, "expected inherited deletions to exist"

    for rel in modified:
        assert rel in archived, rel
    for rel in deleted:
        assert rel not in archived, rel
        assert rel in before["deleted_tracked_files"], rel

    for rel in SNAP.UNTRACKED_WHITELIST:
        if (REPO_ROOT / rel).is_file():
            assert rel in archived, rel
    assert "plans/phase1/DATA_CONTRACTS.md" in archived
    assert "plans/phase1/cards/P1-00.md" in archived
    assert "scripts/phase1_snapshot.py" not in SNAP.UNTRACKED_WHITELIST

    # 至少一个 dirty 文件与 HEAD 内容不同：证明快照的是工作树而非 HEAD
    differing = [
        rel
        for rel in modified
        if archived[rel]["sha256"]
        != hashlib.sha256(SNAP.git(REPO_ROOT, "show", f"HEAD:{rel}")).hexdigest()
    ]
    assert differing, "no dirty file differed from HEAD; snapshot may have used HEAD"


# Coordinator regressions: independent controls for gaps missed by the first suite.
def test_scope_does_not_allow_a_file_or_symlink_as_an_allowed_file_ancestor(synth_repo):
    before = SNAP.capture(synth_repo, "ancestor-before")
    (synth_repo / "tests").symlink_to("elsewhere")
    after = SNAP.capture(synth_repo, "ancestor-after")
    report = SNAP.compare(before, after, ["tests/phase1/test_p1_00.py"])
    assert report["ok"] is False
    assert "tests" in report["outside_changes"]


def test_scope_glob_only_allows_matching_direct_files():
    assert SNAP.allowed_hit("deeptutor/subjects/store.py", ["deeptutor/subjects/*.py"])
    assert not SNAP.allowed_hit("deeptutor/subjects/nested/rogue.py", ["deeptutor/subjects/*.py"])
    assert not SNAP.allowed_hit("other/deeptutor/subjects/store.py", ["deeptutor/subjects/*.py"])


def test_scope_detects_git_head_change(synth_repo):
    before = SNAP.capture(synth_repo, "head-before")
    after = json.loads(json.dumps(before))
    assert SNAP.compare(before, after, ALLOWED)["ok"]
    after["head"] = "0" * 40
    assert not SNAP.compare(before, after, ALLOWED)["ok"]


def test_protection_records_hidden_data_and_retargeted_root(tmp_path):
    root = tmp_path / "protected"
    _write(root, "settings/.env.local", "fixture-secret")
    first = SNAP.protect_one(root, "settings")
    assert ".env.local" in first["files"]
    _write(root, "settings/.env.local", "changed-secret")
    second = SNAP.protect_one(root, "settings")
    assert not SNAP.compare_data({"roots": {"r": first}}, {"roots": {"r": second}})["ok"]
    (root / "link").symlink_to("settings")
    first = SNAP.protect_one(root, "link")
    assert SNAP.compare_data({"roots": {"r": first}}, {"roots": {"r": first}})["ok"]
    (root / "link").unlink()
    (root / "link").symlink_to("different")
    second = SNAP.protect_one(root, "link")
    assert not SNAP.compare_data({"roots": {"r": first}}, {"roots": {"r": second}})["ok"]


def test_protection_detects_root_file_changes(tmp_path):
    _write(tmp_path, "single", "a")
    first = SNAP.protect_one(tmp_path, "single")
    _write(tmp_path, "single", "b")
    second = SNAP.protect_one(tmp_path, "single")
    assert not SNAP.compare_data({"roots": {"r": first}}, {"roots": {"r": second}})["ok"]


def test_unreadable_directory_is_not_silently_skipped(synth_repo, monkeypatch):
    def walk(_root, *, followlinks, onerror=None):
        if onerror is not None:
            onerror(PermissionError("fixture unreadable directory"))
        return iter(())
    monkeypatch.setattr(SNAP.os, "walk", walk)
    with pytest.raises(PermissionError):
        SNAP.scan_tree(synth_repo)


def test_source_env_variants_are_excluded(synth_repo):
    _write(synth_repo, ".env.local", SECRET_SENTINEL)
    _git(synth_repo, "add", ".env.local")
    captured = SNAP.capture(synth_repo, "env-variant")
    assert ".env.example" in captured["archived_files"]
    assert ".env.local" not in captured["archived_files"]


def test_executable_modes_survive_rebuild(synth_repo, tmp_path):
    path = synth_repo / "src/app.py"
    path.chmod(0o755)
    before = SNAP.capture(synth_repo, "executable")
    archive = tmp_path / "exec.tar.gz"
    info = SNAP.build_archive(synth_repo, before, archive)
    before["archive_sha256"] = info["archive_sha256"]
    assert SNAP.verify_rebuild(before, archive, tmp_path / "rebuilt")["ok"]
    assert (tmp_path / "rebuilt/src/app.py").stat().st_mode & 0o777 == 0o755


def test_new_approved_sources_are_recoverable(synth_repo, tmp_path):
    _write(synth_repo, "scripts/phase1_snapshot.py", "# newly implemented\n")
    _write(synth_repo, "deeptutor/subjects/errors.py", "# approved stage source\n")
    before = SNAP.capture(synth_repo, "completed", include_paths=["deeptutor/subjects/errors.py"])
    assert "scripts/phase1_snapshot.py" in before["archived_files"]
    assert "deeptutor/subjects/errors.py" in before["archived_files"]
    assert "scratch_unknown.py" not in before["archived_files"]


def test_tar_symlink_parent_cannot_escape_before_any_extraction(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("redirect")
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        tar.addfile(link)
        member = tarfile.TarInfo("redirect/escaped.txt")
        member.size = 4
        tar.addfile(member, io.BytesIO(b"evil"))
    with pytest.raises(ValueError):
        SNAP.extract_archive(archive, tmp_path / "rebuild")
    assert not (outside / "escaped.txt").exists()
    assert not (tmp_path / "rebuild/redirect").exists()


def test_verify_checks_archive_digest_before_extracting(synth_repo, tmp_path):
    baseline = SNAP.capture(synth_repo, "wrong-digest")
    archive = tmp_path / "valid.tar.gz"
    SNAP.build_archive(synth_repo, baseline, archive)
    baseline["archive_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        SNAP.verify_rebuild(baseline, archive, tmp_path / "rebuild")
    assert not (tmp_path / "rebuild").exists()


def test_archive_stream_detects_change_after_precheck(synth_repo, tmp_path, monkeypatch):
    baseline = SNAP.capture(synth_repo, "stream-change")
    original_add = SNAP.tarfile.TarFile.addfile
    def addfile(tar, member, fileobj=None):
        if member.name == "src/app.py":
            data = (synth_repo / "src/app.py").read_bytes()
            (synth_repo / "src/app.py").write_bytes(b"X" * len(data))
        return original_add(tar, member, fileobj)
    monkeypatch.setattr(SNAP.tarfile.TarFile, "addfile", addfile)
    with pytest.raises(RuntimeError, match="changed"):
        SNAP.build_archive(synth_repo, baseline, tmp_path / "changed.tar.gz")
    assert not (tmp_path / "changed.tar.gz").exists()


@pytest.mark.parametrize("command", ["compare", "compare-data", "verify-rebuild"])
def test_all_cli_output_paths_are_guarded(synth_repo, tmp_path, command):
    baseline = SNAP.capture(synth_repo, "guarded-output")
    archive = tmp_path / "guard.tar.gz"
    info = SNAP.build_archive(synth_repo, baseline, archive)
    baseline["archive_sha256"] = info["archive_sha256"]
    before_file = tmp_path / "before.json"
    after_file = tmp_path / "after.json"
    if command == "compare-data":
        payload = SNAP.protect_data(synth_repo)
    else:
        payload = baseline
    SNAP.write_json(before_file, payload)
    SNAP.write_json(after_file, payload)
    target = synth_repo / "src/app.py"
    original = target.read_bytes()
    if command == "verify-rebuild":
        args = [command, "--root", str(synth_repo), "--baseline", str(before_file),
                "--archive", str(archive), "--workdir", str(tmp_path / "rebuild")]
    else:
        args = [command, "--before", str(before_file), "--after", str(after_file)]
    with pytest.raises(ValueError):
        SNAP.main(args + ["--out", str(target)])
    assert target.read_bytes() == original


def test_archive_cli_never_rewrites_source_manifest(synth_repo, tmp_path):
    path = tmp_path / "baseline.json"
    SNAP.write_json(path, SNAP.capture(synth_repo, "immutable-baseline"))
    before = path.read_bytes()
    assert SNAP.main(["archive", "--root", str(synth_repo), "--baseline", str(path),
                      "--out", str(tmp_path / "snapshot.tar.gz")]) == 0
    assert path.read_bytes() == before


def test_scope_ignores_only_the_node_test_cache(synth_repo):
    before = SNAP.capture(synth_repo, "cache-before")
    _write(synth_repo, "web/dist/node-tests/generated.js", "compiled\n")
    _write(synth_repo, "web/lib/not-approved.ts", "rogue\n")
    report = SNAP.compare(before, SNAP.capture(synth_repo, "cache-after"), ALLOWED)
    assert "web/lib/not-approved.ts" in report["outside_changes"]
    assert not any("web/dist/node-tests" in p for p in report["outside_changes"])
    assert "web/dist" not in report["outside_changes"]


def test_manifests_and_archives_cannot_overwrite_existing_evidence(synth_repo, tmp_path):
    target = tmp_path / "existing.json"
    SNAP.write_json(target, {"original": True})
    original = target.read_bytes()
    with pytest.raises(ValueError):
        SNAP.write_json(target, {"replacement": True})
    assert target.read_bytes() == original
    with pytest.raises(ValueError):
        SNAP.build_archive(synth_repo, SNAP.capture(synth_repo, "existing"), target)
    assert target.read_bytes() == original


def test_malformed_digest_and_boolean_size_do_not_validate(synth_repo):
    before = SNAP.capture(synth_repo, "strict-metadata")
    after = json.loads(json.dumps(before))
    assert SNAP.compare(before, after, ALLOWED)["ok"]
    path = "src/app.py"
    after["monitored_files"][path]["sha256"] += "\n"
    with pytest.raises(ValueError):
        SNAP.compare(before, after, ALLOWED)
    after = json.loads(json.dumps(before))
    after["monitored_files"][path]["size"] = True
    with pytest.raises(ValueError):
        SNAP.compare(before, after, ALLOWED)


def test_chmod_is_a_data_change(tmp_path):
    path = _write(tmp_path, "tree/file", "same bytes")
    before = {"roots": {"r": SNAP.protect_one(tmp_path, "tree")}}
    assert SNAP.compare_data(before, before)["ok"]
    path.chmod(0o600)
    assert not SNAP.compare_data(before, {"roots": {"r": SNAP.protect_one(tmp_path, "tree")}})["ok"]


def test_whitelisted_symlink_records_link_without_reading_secret(synth_repo, tmp_path):
    secret = tmp_path / "outside-secret"
    secret.write_text(SECRET_SENTINEL)
    source = synth_repo / "deeptutor/subjects/generation.py"
    source.unlink()
    source.symlink_to(secret)
    captured = SNAP.capture(synth_repo, "symlink-source")
    assert captured["archived_files"]["deeptutor/subjects/generation.py"]["kind"] == "symlink"
    archive = tmp_path / "symlink-source.tar.gz"
    SNAP.build_archive(synth_repo, captured, archive)
    with tarfile.open(archive) as tar:
        assert not any(SECRET_SENTINEL.encode() in tar.extractfile(m).read() for m in tar if m.isfile())


def test_legacy_protection_does_not_drop_an_already_recorded_env_file(tmp_path):
    _write(tmp_path, "settings/.env.local", "before")
    old = SNAP.protect_one(tmp_path, "settings")
    old.pop("inventory_policy")
    _write(tmp_path, "settings/.env.local", "after")
    new = SNAP.protect_one(tmp_path, "settings")
    assert not SNAP.compare_data({"roots": {"r": old}}, {"roots": {"r": new}})["ok"]


def test_boolean_size_cannot_masquerade_as_one_in_data_record(tmp_path):
    _write(tmp_path, "file", "a")
    before = {"roots": {"r": SNAP.protect_one(tmp_path, "file")}}
    assert SNAP.compare_data(before, before)["ok"]
    after = json.loads(json.dumps(before))
    after["roots"]["r"]["size"] = True
    with pytest.raises(ValueError):
        SNAP.compare_data(before, after)

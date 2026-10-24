#!/usr/bin/env python3
"""P1-00 基线快照 / 真实数据只读保护 / 卡内增量范围检查。

子命令
------
capture          记录 HEAD、git 工作区状态、归档源码清单、被删除的已跟踪文件、
                 以及更宽的受监控文件/目录清单。
archive          把归档清单打成确定性 tar.gz（gzip mtime=0），供 tmp 重建核验。
verify-rebuild   在临时目录解包并逐文件比对 sha256，确认可准确重建。
protect-data     对真实六科学习树、产物树、settings 做不透明二进制流哈希。
compare          比较两次 capture，区分允许范围内外的变化。
compare-data     比较两次 protect-data。

安全性质（由 tests/phase1/test_p1_00.py 断言）
--------------------------------------------
* 只读源码，从不解码内容；配置文件只计算摘要，不解析、不展示、不复制。
* 归档集合与监控集合刻意不同：未列入白名单的未知新源码不入归档，
  但仍会被范围检查发现。
* 输出路径若落在项目树内且不在 .phase1-evidence/ 下则直接拒绝，
  因此任何失败都不可能改动原树。
* 符号链接只记录目标，绝不跟随；读取失败直接抛出，不会被忽略。

仅使用标准库，不导入任何业务模块，因此不会触发真实配置读写。
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time

SCHEMA_VERSION = 2
CARD_ID = "P1-00"
CHUNK_SIZE = 1024 * 1024
EVIDENCE_DIR = ".phase1-evidence"

# --------------------------------------------------------------------------
# 树排除规则：归档与监控共用同一套目录级排除；两者差别只在“文件白名单”。
# --------------------------------------------------------------------------
EXCLUDE_PREFIXES = (
    ".git",
    ".venv",
    "data",
    EVIDENCE_DIR,
    "tools/bin",
    "tools/fonts",
    "web/node_modules",
    "web/.next",
    "web/dist/node-tests",
    "deeptutor.egg-info",
)

EXCLUDE_PARTS = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".ipynb_checkpoints",
    }
)

# 精确名匹配：.env 被排除，.env.example 仍应归档。
EXCLUDE_NAMES = frozenset({".env", ".DS_Store"})

EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".tsbuildinfo")

# 卡明确要求纳入源码快照的未跟踪文件（前人未提交的已验证修复与交接材料）。
UNTRACKED_WHITELIST = (
    "deeptutor/subjects/generation.py",
    "deeptutor/utils/document_images.py",
    "HANDOVER.md",
    "PROJECT_AUDIT_2026-10-10.md",
)
UNTRACKED_WHITELIST_PREFIXES = ("plans/phase1/",)

# 必须保持字节一致的真实数据根（只哈希，不复制）。
PROTECTED_DATA_ROOTS = {
    "learning_tree": "data/user/workspace/subjects",
    "public_outputs": "data/user/subjects",
    "settings": "data/user/settings",
}

# 额外观察根：只记录，不纳入 real_data_unchanged 的合同判定。
SUPPLEMENTARY_DATA_ROOTS = {
    "global_knowledge_bases": "data/knowledge_bases",
    "memory": "data/memory",
    "system": "data/system",
}

P1_00_ALLOWED_PATHS = (
    ".gitignore",
    "scripts/phase1_snapshot.py",
    "tests/phase1/test_p1_00.py",
)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def repo_root() -> Path:
    """定位包含 .git 的工作树根。

    先看脚本所在仓库，再回退到当前工作目录。刻意不做“静默取某个目录”的
    兜底：保护工具作用在错误的根上比直接报错危险得多。
    """
    for candidate in (Path(__file__).resolve().parents[1], Path.cwd()):
        probe = candidate.resolve()
        while True:
            if (probe / ".git").exists():
                return probe
            if probe.parent == probe:
                break
            probe = probe.parent
    raise RuntimeError("cannot locate a git worktree (no .git found upward)")


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def is_excluded(rel: str) -> bool:
    """rel 为相对扫描根、以 / 分隔的 POSIX 路径。"""
    parts = rel.split("/")
    if parts[-1] in EXCLUDE_NAMES:
        return True
    if parts[-1].startswith(".env.") and parts[-1] not in {".env.example", ".env.sample", ".env.template"}:
        return True
    if any(part in EXCLUDE_PARTS for part in parts):
        return True
    if rel.endswith(EXCLUDE_SUFFIXES):
        return True
    return any(rel == p or rel.startswith(p + "/") for p in EXCLUDE_PREFIXES)


def sha256_stream(path: Path) -> tuple[str, int]:
    """按不透明二进制流计算 sha256。绝不解码内容。"""
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("cannot hash a non-regular file")
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return digest.hexdigest(), size


def symlink_entry(path: Path) -> dict:
    return {"kind": "symlink", "target": os.readlink(path)}


def file_entry(path: Path) -> dict:
    digest, size = sha256_stream(path)
    return {"kind": "file", "sha256": digest, "size": size,
            "mode": stat.S_IMODE(path.lstat().st_mode)}


def scan_tree(root: Path, *, exclude: bool = True) -> tuple[dict[str, dict], list[str]]:
    """返回 (文件条目, 目录列表)，覆盖 root 下所有未被排除的路径。

    符号链接按目标记录且不下钻；不可读文件直接抛错而不是跳过。
    """
    files: dict[str, dict] = {}
    dirs: list[str] = []
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        return files, dirs
    if not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("scan root must be a real directory")
    def fail(error):
        raise error
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=fail):
        here = Path(dirpath)
        keep: list[str] = []
        for name in sorted(dirnames):
            full = here / name
            rel = full.relative_to(root).as_posix()
            if exclude and is_excluded(rel):
                continue
            if full.is_symlink():
                files[rel] = symlink_entry(full)
                continue
            dirs.append(rel)
            keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            full = here / name
            rel = full.relative_to(root).as_posix()
            if exclude and is_excluded(rel):
                continue
            if full.is_symlink():
                files[rel] = symlink_entry(full)
            elif full.is_file():
                files[rel] = file_entry(full)
            else:
                files[rel] = {"kind": "other"}
    return files, sorted(dirs)


def write_json(path: Path, payload: object, *, root: Path | None = None) -> None:
    if root is not None:
        guard_write_target(root, path)
    if path.exists() or path.is_symlink():
        raise ValueError("refusing to overwrite an existing evidence file")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def guard_write_target(root: Path, target: Path) -> None:
    """拒绝把输出写进项目树（.phase1-evidence/ 除外）。"""
    resolved = target.resolve()
    roots = {root.resolve()}
    actual_project = Path(__file__).resolve().parents[1]
    if (actual_project / ".git").exists():
        roots.add(actual_project)
    for root_resolved in roots:
        if resolved == root_resolved or root_resolved in resolved.parents:
            rel = resolved.relative_to(root_resolved).as_posix()
            if not rel.startswith(EVIDENCE_DIR + "/"):
                raise ValueError("refusing to write inside the project tree outside evidence")


def allowed_hit(rel: str, allowed: tuple[str, ...] | list[str], *, directory: bool = False) -> bool:
    """rel 命中白名单，或为白名单条目的祖先目录。"""
    for raw in allowed:
        item = raw.rstrip("/")
        if not item:
            continue
        parts, pattern = rel.split("/"), item.split("/")
        if len(parts) == len(pattern) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts, pattern)):
            return True
        if raw.endswith("/") and rel.startswith(item + "/"):
            return True
        if directory and len(parts) < len(pattern) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts, pattern)):
            return True
    return False


# --------------------------------------------------------------------------
# git 辅助
# --------------------------------------------------------------------------
def git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: "
            + proc.stderr.decode("utf-8", "replace").strip()
        )
    return proc.stdout


def git_text(root: Path, *args: str) -> str:
    return git(root, *args).decode("utf-8", "surrogateescape")


def git_head(root: Path) -> str:
    return git_text(root, "rev-parse", "HEAD").strip()


def git_tracked(root: Path) -> list[str]:
    raw = git(root, "ls-files", "-z").decode("utf-8", "surrogateescape")
    return [item for item in raw.split("\0") if item]


def git_status_lines(root: Path) -> list[str]:
    return [line for line in git_text(root, "status", "--porcelain").splitlines() if line]


def head_blob_info(root: Path, rel: str) -> dict:
    try:
        blob = git_text(root, "rev-parse", f"HEAD:{rel}").strip()
    except RuntimeError:
        return {"head_blob": None, "head_size": None}
    size_raw = git_text(root, "cat-file", "-s", blob).strip()
    return {"head_blob": blob, "head_size": int(size_raw) if size_raw.isdigit() else None}


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------
def whitelisted_untracked(root: Path, tracked: set[str], include_paths=()) -> list[str]:
    found: set[str] = set()
    for rel in UNTRACKED_WHITELIST:
        if (root / rel).is_file() or (root / rel).is_symlink():
            found.add(rel)
    for prefix in UNTRACKED_WHITELIST_PREFIXES:
        base = root / prefix
        if base.is_symlink():
            found.add(prefix.rstrip("/"))
            continue
        if not base.parent.resolve().is_relative_to(root.resolve()):
            raise ValueError("source directory parent escapes repository")
        if not base.is_dir():
            continue
        def fail(error):
            raise error
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False, onerror=fail):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_PARTS]
            for name in filenames:
                full = Path(dirpath) / name
                rel = full.relative_to(root).as_posix()
                if is_excluded(rel) or not full.is_file():
                    continue
                found.add(rel)
    monitored, _ = scan_tree(root)
    for rel in monitored:
        if allowed_hit(rel, list(P1_00_ALLOWED_PATHS) + list(include_paths) + list(UNTRACKED_WHITELIST_PREFIXES)):
            found.add(rel)
    return sorted(item for item in found if item not in tracked)


def capture(root: Path, label: str, *, include_paths=()) -> dict:
    """记录完整基线：归档清单 + 更宽的监控清单 + 删除清单。"""
    if not (root / ".git").exists():
        raise RuntimeError(f"not a git worktree: {root}")
    head = git_head(root)
    tracked = git_tracked(root)
    tracked_set = set(tracked)

    archived: dict[str, dict] = {}
    for rel in tracked:
        if is_excluded(rel):
            continue
        full = root / rel
        if not full.parent.resolve().is_relative_to(root.resolve()):
            raise ValueError("source parent escapes repository")
        if full.is_symlink():
            archived[rel] = symlink_entry(full)
        elif full.is_file():
            archived[rel] = file_entry(full)
    for rel in whitelisted_untracked(root, tracked_set, include_paths):
        full = root / rel
        if not full.parent.resolve().is_relative_to(root.resolve()):
            raise ValueError("source parent escapes repository")
        archived[rel] = symlink_entry(full) if full.is_symlink() else file_entry(full)

    deleted: dict[str, dict] = {}
    tracked_on_disk: list[str] = []
    for rel in tracked:
        full = root / rel
        if full.exists() or full.is_symlink():
            tracked_on_disk.append(rel)
        else:
            entry = {"head_blob": None, "head_size": None}
            entry.update(head_blob_info(root, rel))
            deleted[rel] = entry

    monitored, monitored_dirs = scan_tree(root)

    status_lines = git_status_lines(root)
    counts = {"modified": 0, "deleted": 0, "untracked": 0, "other": 0}
    for line in status_lines:
        code = line[:2]
        if code == "??":
            counts["untracked"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "M" in code:
            counts["modified"] += 1
        else:
            counts["other"] += 1

    core = {
        "head": head,
        "archived_files": archived,
        "deleted_tracked_files": deleted,
        "monitored_files": monitored,
        "monitored_dirs": monitored_dirs,
    }
    identifier = (
        f"{CARD_ID}-{head[:12]}-"
        + hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )

    excluded_tracked = sorted(rel for rel in tracked if is_excluded(rel))

    return {
        "schema_version": SCHEMA_VERSION,
        "card_id": CARD_ID,
        "label": label,
        "captured_at": now_utc(),
        "root": str(root),
        "head": head,
        "baseline_id": identifier,
        "git_status_porcelain": status_lines,
        "git_status_counts": counts,
        "tracked_count": len(tracked),
        "tracked_on_disk_count": len(tracked_on_disk),
        "excluded_tracked_files": excluded_tracked,
        "archived_files": archived,
        "archived_count": len(archived),
        "deleted_tracked_files": deleted,
        "deleted_count": len(deleted),
        "monitored_files": monitored,
        "monitored_count": len(monitored),
        "monitored_dirs": monitored_dirs,
        "monitored_dir_modes": {rel: stat.S_IMODE((root / rel).lstat().st_mode) for rel in monitored_dirs},
        "monitored_dir_count": len(monitored_dirs),
    }


# --------------------------------------------------------------------------
# archive / verify-rebuild
# --------------------------------------------------------------------------
def build_archive(root: Path, baseline: dict, out: Path) -> dict:
    """写出确定性 tar.gz。

    归档内容取自**当前工作树**，因此每个条目都会先与 capture 时记录的
    sha256/size 比对：如果文件在 capture 之后被改动过，这里直接失败，
    而不是产出一个与 manifest 不符的归档。失败时不留下半成品，也不改动原树。
    """
    archived = baseline["archived_files"]
    _validate_entries(archived)
    guard_write_target(root, out)
    if out.exists() or out.is_symlink():
        raise ValueError("refusing to overwrite an existing archive")
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + out.name + ".", suffix=".part", dir=out.parent)
    part = Path(name)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                    for rel in sorted(archived):
                        _safe_member_name(rel)
                        info = archived[rel]
                        full = root / rel
                        if not full.parent.resolve().is_relative_to(root.resolve()):
                            raise ValueError("source parent escapes repository")
                        if info["kind"] == "symlink":
                            if os.readlink(full) != info.get("target"):
                                raise RuntimeError(
                                    "symlink changed since capture, refusing to archive "
                                    f"a stale baseline entry: {rel}"
                                )
                            member = tarfile.TarInfo(rel)
                            member.type = tarfile.SYMTYPE
                            member.linkname = info["target"]
                            member.mtime = 0
                            tar.addfile(member)
                        elif info["kind"] == "file":
                            current = file_entry(full)
                            if (
                                current["sha256"] != info.get("sha256")
                                or current["size"] != info.get("size")
                            ):
                                raise RuntimeError(
                                    "source changed since capture, refusing to archive "
                                    f"a stale baseline entry: {rel}"
                                )
                            member = tar.gettarinfo(str(full), arcname=rel)
                            member.mtime = 0
                            member.uid = 0
                            member.gid = 0
                            member.uname = ""
                            member.gname = ""
                            with os.fdopen(os.open(full, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
                                class CheckedReader:
                                    def __init__(self, stream):
                                        self.stream, self.digest, self.size = stream, hashlib.sha256(), 0
                                    def read(self, size=-1):
                                        value = self.stream.read(size)
                                        self.digest.update(value)
                                        self.size += len(value)
                                        return value
                                checked = CheckedReader(handle)
                                tar.addfile(member, checked)
                                extra = handle.read(1)
                                if extra or checked.size != info["size"] or checked.digest.hexdigest() != info["sha256"]:
                                    raise RuntimeError(f"source changed while archiving: {rel}")
                        else:
                            raise RuntimeError(f"unsupported archive entry: {rel}")
        os.replace(part, out)
    except BaseException:
        if part.exists():
            part.unlink()
        raise
    digest, size = sha256_stream(out)
    return {
        "archive": str(out),
        "archive_sha256": digest,
        "archive_size": size,
        "entry_count": len(archived),
        "baseline_id": baseline["baseline_id"],
    }


def _safe_member_name(name: str) -> None:
    pure = PurePosixPath(name)
    if not name or pure.is_absolute() or "\\" in name or ".." in pure.parts or str(pure) != name or name == ".":
        raise ValueError(f"unsafe archive member: {name!r}")


def extract_archive(archive: Path, workdir: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        by_name = {m.name: m for m in members}
        if len(by_name) != len(members):
            raise ValueError("duplicate archive members")
        for member in members:
            _safe_member_name(member.name)
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError("unsupported archive member type")
            for parent in PurePosixPath(member.name).parents:
                if str(parent) == ".":
                    continue
                ancestor = by_name.get(str(parent))
                if ancestor is not None and not ancestor.isdir():
                    raise ValueError("archive member has non-directory ancestor")
                if (workdir / str(parent)).is_symlink():
                    raise ValueError("extraction parent is a symlink")
        if workdir.is_symlink():
            raise ValueError("workdir is a symlink")
        workdir.mkdir(parents=True, exist_ok=True)
        for member in members:
            target = workdir / member.name
            if target.exists() or target.is_symlink():
                if not (member.isdir() and target.is_dir() and not target.is_symlink()):
                    raise ValueError("refusing to overwrite extraction target")
            if member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(member.linkname, target)
            elif member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError(f"cannot read archive member: {member.name}")
                with source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle)
                target.chmod(member.mode & 0o777)
            else:
                raise RuntimeError(f"unsupported archive member: {member.name}")


def verify_rebuild(baseline: dict, archive: Path, workdir: Path) -> dict:
    """在空目录中重建并逐文件比对。

    刻意不删除已存在的目录：宁可拒绝执行，也不对调用者给错的路径做 rm -rf。
    """
    digest, _ = sha256_stream(archive)
    if not baseline.get("archive_sha256") or digest != baseline["archive_sha256"]:
        raise ValueError("archive digest is missing or does not match")
    if workdir.is_symlink():
        raise ValueError("workdir is a symlink")
    if workdir.exists():
        if not workdir.is_dir() or any(workdir.iterdir()):
            raise ValueError(f"refusing to reuse a non-empty workdir: {workdir}")
    extract_archive(archive, workdir)
    rebuilt, rebuilt_dirs = scan_tree(workdir)

    expected = baseline["archived_files"]
    missing = sorted(set(expected) - set(rebuilt))
    unexpected = sorted(set(rebuilt) - set(expected))
    mismatches: list[dict] = []
    for rel in sorted(set(expected) & set(rebuilt)):
        want = expected[rel]
        got = rebuilt[rel]
        if want.get("kind") != got.get("kind"):
            mismatches.append({"path": rel, "reason": "kind", "expected": want, "actual": got})
        elif want.get("kind") == "file" and want.get("sha256") != got.get("sha256"):
            mismatches.append({"path": rel, "reason": "sha256", "expected": want, "actual": got})
        elif want.get("kind") == "symlink" and want.get("target") != got.get("target"):
            mismatches.append({"path": rel, "reason": "symlink_target", "expected": want, "actual": got})
        elif "mode" in want and want["mode"] != got.get("mode"):
            mismatches.append({"path": rel, "reason": "mode", "expected": want, "actual": got})

    deleted_absent: list[str] = []
    deleted_present: list[str] = []
    for rel in sorted(baseline["deleted_tracked_files"]):
        if (workdir / rel).exists() or (workdir / rel).is_symlink():
            deleted_present.append(rel)
        else:
            deleted_absent.append(rel)

    digest, _ = sha256_stream(archive)
    ok = (
        not missing
        and not unexpected
        and not mismatches
        and not deleted_present
        and digest == baseline.get("archive_sha256", digest)
    )
    return {
        "ok": ok,
        "checked_at": now_utc(),
        "baseline_id": baseline["baseline_id"],
        "archive_sha256": digest,
        "archive_sha256_expected": baseline.get("archive_sha256"),
        "expected_count": len(expected),
        "rebuilt_count": len(rebuilt),
        "rebuilt_dir_count": len(rebuilt_dirs),
        "missing": missing,
        "unexpected": unexpected,
        "hash_mismatches": mismatches,
        "deleted_files_confirmed_absent": deleted_absent,
        "deleted_files_unexpectedly_present": deleted_present,
    }


# --------------------------------------------------------------------------
# protect-data
# --------------------------------------------------------------------------
def protect_one(root: Path, rel: str) -> dict:
    full = root / rel
    try:
        info = full.lstat()
    except FileNotFoundError:
        return {"path": rel, "exists": False}
    if stat.S_ISLNK(info.st_mode):
        return {"path": rel, "exists": True, "kind": "symlink", "target": os.readlink(full)}
    if stat.S_ISREG(info.st_mode):
        entry = file_entry(full)
        entry.update({"path": rel, "exists": True})
        return entry
    files, dirs = scan_tree(full, exclude=False)
    return {
        "path": rel,
        "exists": True,
        "kind": "dir",
        "file_count": len(files),
        "dir_count": len(dirs),
        "files": files,
        "dirs": dirs,
        "mode": stat.S_IMODE(full.lstat().st_mode),
        "dir_modes": {p: stat.S_IMODE((full / p).lstat().st_mode) for p in dirs},
        "inventory_policy": "all",
    }


def protect_data(root: Path) -> dict:
    roots = {name: protect_one(root, rel) for name, rel in PROTECTED_DATA_ROOTS.items()}
    supplementary = {
        name: protect_one(root, rel) for name, rel in SUPPLEMENTARY_DATA_ROOTS.items()
    }
    core = json.dumps(roots, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "card_id": CARD_ID,
        "captured_at": now_utc(),
        "root": str(root),
        "protection_id": f"{CARD_ID}-data-{hashlib.sha256(core).hexdigest()[:16]}",
        "roots": roots,
        "supplementary_roots": supplementary,
        "note": (
            "只记录不透明二进制流的 sha256/size/kind/target；不含任何文件内容，"
            "未解析任何配置字段。real_data_unchanged 以 roots 为准。"
        ),
    }


def diff_inventory(before: dict, after: dict) -> dict:
    b_files = before.get("files", {})
    a_files = after.get("files", {})
    _validate_entries(b_files)
    _validate_entries(a_files)
    b_dirs = set(before.get("dirs", []))
    a_dirs = set(after.get("dirs", []))
    added = sorted(set(a_files) - set(b_files))
    removed = sorted(set(b_files) - set(a_files))
    modified = sorted(
        rel for rel in set(b_files) & set(a_files) if not _same_entry(b_files[rel], a_files[rel])
    )
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "dirs_added": sorted(a_dirs - b_dirs),
        "dirs_removed": sorted(b_dirs - a_dirs),
        "changed": bool(added or removed or modified or (a_dirs ^ b_dirs)),
    }


def _same_entry(before: dict, after: dict) -> bool:
    # Old immutable baselines did not record permissions; do not invent that evidence.
    b, a = dict(before), dict(after)
    if "mode" not in b or "mode" not in a:
        b.pop("mode", None)
        a.pop("mode", None)
    return b == a


def _validate_entries(entries: dict) -> None:
    for rel, entry in entries.items():
        _safe_member_name(rel)
        if entry.get("kind") not in {"file", "symlink", "other"}:
            raise ValueError("invalid inventory entry kind")
        if entry.get("kind") == "symlink" and (not isinstance(entry.get("target"), str) or "\0" in entry["target"]):
            raise ValueError("invalid symlink target")
        if entry.get("kind") == "file":
            if not isinstance(entry.get("sha256"), str) or re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) is None:
                raise ValueError("invalid file digest in inventory")
            if type(entry.get("size")) is not int or entry["size"] < 0:
                raise ValueError("invalid file size in inventory")
        if "mode" in entry and (type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o7777):
            raise ValueError("invalid file mode in inventory")


def compare_data(before: dict, after: dict) -> dict:
    report: dict[str, dict] = {}
    ok = True
    for name in sorted(set(before["roots"]) | set(after["roots"])):
        b = before["roots"].get(name, {"exists": False})
        a = after["roots"].get(name, {"exists": False})
        for value in (b, a):
            if type(value.get("exists")) is not bool:
                raise ValueError("invalid protected root existence flag")
            if value.get("kind") == "file":
                _validate_entries({"root": value})
        # Historical protection used source exclusions. New captures protect all files.
        if b.get("inventory_policy") != "all" or a.get("inventory_policy") != "all":
            b, a = dict(b), dict(a)
            for value, other in ((b, a), (a, b)):
                value["files"] = {p: v for p, v in value.get("files", {}).items()
                                  if p in other.get("files", {}) or not is_excluded(p)}
                value["dirs"] = [p for p in value.get("dirs", [])
                                 if p in other.get("dirs", []) or not is_excluded(p)]
        if b.get("exists") != a.get("exists"):
            diff = {
                "added": [],
                "removed": [],
                "modified": [],
                "dirs_added": [],
                "dirs_removed": [],
                "changed": True,
                "existence_changed": True,
            }
        else:
            diff = diff_inventory(b, a)
            top = ("kind", "sha256", "size", "target", "mode")
            for field in top:
                if field == "mode" and (field not in b or field not in a):
                    continue
                if b.get(field) != a.get(field):
                    diff["changed"] = True
                    diff["root_metadata_changed"] = True
            common = set(b.get("dir_modes", {})) & set(a.get("dir_modes", {}))
            if any(b["dir_modes"][p] != a["dir_modes"][p] for p in common):
                diff["changed"] = True
                diff["directory_modes_changed"] = True
        diff["protection_id_before"] = before.get("protection_id")
        diff["protection_id_after"] = after.get("protection_id")
        report[name] = diff
        if diff["changed"]:
            ok = False
    return {
        "ok": ok,
        "compared_at": now_utc(),
        "card_id": CARD_ID,
        "roots": report,
    }


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------
def compare(before: dict, after: dict, allowed: list[str]) -> dict:
    if before.get("root") != after.get("root"):
        raise ValueError("cannot compare different repository roots")
    b_files = {p: v for p, v in before["monitored_files"].items() if not is_excluded(p)}
    a_files = {p: v for p, v in after["monitored_files"].items() if not is_excluded(p)}
    _validate_entries(b_files)
    _validate_entries(a_files)
    b_dirs = {p for p in before["monitored_dirs"] if not is_excluded(p)}
    a_dirs = {p for p in after["monitored_dirs"] if not is_excluded(p)}

    changes: list[dict] = []
    for rel in sorted(set(b_files) | set(a_files)):
        b = b_files.get(rel)
        a = a_files.get(rel)
        if b is not None and a is not None and _same_entry(b, a):
            continue
        if b is None:
            kind = "added"
        elif a is None:
            kind = "removed"
        else:
            kind = "modified"
        changes.append({"path": rel, "change": kind, "allowed": allowed_hit(rel, allowed)})

    for rel in sorted(b_dirs ^ a_dirs):
        if rel == "web/dist" and not any(p.startswith("web/dist/") for p in set(b_files) | set(a_files)):
            continue
        kind = "dir_added" if rel not in b_dirs else "dir_removed"
        changes.append({"path": rel, "change": kind, "allowed": allowed_hit(rel, allowed, directory=True)})
    common = set(before.get("monitored_dir_modes", {})) & set(after.get("monitored_dir_modes", {}))
    for rel in sorted(common):
        if not is_excluded(rel) and before["monitored_dir_modes"][rel] != after["monitored_dir_modes"][rel]:
            changes.append({"path": rel, "change": "dir_mode", "allowed": allowed_hit(rel, allowed)})
    if before.get("head") != after.get("head"):
        changes.append({"path": "@git/HEAD", "change": "head", "allowed": False})

    outside = sorted(c["path"] for c in changes if not c["allowed"])
    inside = sorted(c["path"] for c in changes if c["allowed"])
    return {
        "ok": not outside,
        "compared_at": now_utc(),
        "card_id": CARD_ID,
        "allowed_patterns": list(allowed),
        "before_baseline_id": before.get("baseline_id"),
        "after_baseline_id": after.get("baseline_id"),
        "head_before": before.get("head"),
        "head_after": after.get("head"),
        "change_count": len(changes),
        "allowed_changes": inside,
        "outside_changes": outside,
        "changes": changes,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _root_arg(value: str | None) -> Path:
    return Path(value).resolve() if value else repo_root()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-00 snapshot / protection / scope tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capture", help="record a workspace baseline")
    p.add_argument("--root")
    p.add_argument("--out", required=True)
    p.add_argument("--label", default="capture")
    p.add_argument("--include", action="append", default=[], help="Approved additional untracked source path/glob.")

    p = sub.add_parser("archive", help="build a deterministic source snapshot")
    p.add_argument("--root")
    p.add_argument("--baseline", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--archive-info", help="Immutable sidecar metadata destination.")

    p = sub.add_parser("verify-rebuild", help="extract into tmp and compare hashes")
    p.add_argument("--root")
    p.add_argument("--baseline", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--out")
    p.add_argument("--archive-info", help="Sidecar metadata when the baseline has no archive digest.")

    p = sub.add_parser("protect-data", help="hash real-data roots read-only")
    p.add_argument("--root")
    p.add_argument("--out", required=True)

    p = sub.add_parser("compare", help="diff two captures against an allowlist")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--allow", action="append", default=[])
    p.add_argument("--out", required=True)

    p = sub.add_parser("compare-data", help="diff two protect-data records")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "capture":
        root = _root_arg(args.root)
        out = Path(args.out).resolve()
        guard_write_target(root, out)
        payload = capture(root, args.label, include_paths=args.include)
        write_json(out, payload, root=root)
        print(json.dumps({k: payload[k] for k in (
            "baseline_id", "head", "archived_count", "deleted_count",
            "monitored_count", "monitored_dir_count", "git_status_counts")},
            ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "archive":
        root = _root_arg(args.root)
        out = Path(args.out).resolve()
        guard_write_target(root, out)
        baseline = read_json(Path(args.baseline).resolve())
        metadata_out = Path(args.archive_info) if args.archive_info else out.with_name(out.name + ".manifest.json")
        guard_write_target(root, metadata_out)
        if metadata_out.exists() or metadata_out.is_symlink():
            raise ValueError("archive metadata already exists")
        info = build_archive(root, baseline, out)
        write_json(metadata_out, info, root=root)
        print(json.dumps(info, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "verify-rebuild":
        baseline = read_json(Path(args.baseline).resolve())
        if not baseline.get("archive_sha256"):
            metadata_path = Path(args.archive_info) if args.archive_info else Path(args.archive).with_name(Path(args.archive).name + ".manifest.json")
            metadata = read_json(metadata_path)
            if metadata.get("baseline_id") != baseline.get("baseline_id"):
                raise ValueError("archive metadata belongs to another baseline")
            baseline = {**baseline, "archive_sha256": metadata["archive_sha256"]}
        workdir = Path(args.workdir).resolve()
        root = _root_arg(args.root)
        guard_write_target(root, workdir)
        if args.out:
            guard_write_target(root, Path(args.out))
        report = verify_rebuild(
            baseline, Path(args.archive).resolve(), workdir
        )
        if args.out:
            write_json(Path(args.out).resolve(), report, root=root)
        print(json.dumps({k: report[k] for k in (
            "ok", "expected_count", "rebuilt_count", "missing", "unexpected",
            "hash_mismatches", "deleted_files_unexpectedly_present")},
            ensure_ascii=False, sort_keys=True))
        return 0 if report["ok"] else 1

    if args.command == "protect-data":
        root = _root_arg(args.root)
        out = Path(args.out).resolve()
        guard_write_target(root, out)
        payload = protect_data(root)
        write_json(out, payload, root=root)
        print(json.dumps({
            "protection_id": payload["protection_id"],
            "roots": {n: {"exists": r.get("exists"), "kind": r.get("kind"),
                          "file_count": r.get("file_count")}
                      for n, r in payload["roots"].items()},
        }, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "compare":
        before = read_json(Path(args.before).resolve())
        after = read_json(Path(args.after).resolve())
        allowed = list(args.allow) or list(P1_00_ALLOWED_PATHS)
        report = compare(before, after, allowed)
        write_json(Path(args.out).resolve(), report, root=Path(before["root"]))
        print(json.dumps({
            "ok": report["ok"],
            "allowed_changes": report["allowed_changes"],
            "outside_changes": report["outside_changes"],
        }, ensure_ascii=False, sort_keys=True))
        return 0 if report["ok"] else 1

    if args.command == "compare-data":
        before = read_json(Path(args.before).resolve())
        after = read_json(Path(args.after).resolve())
        report = compare_data(before, after)
        write_json(Path(args.out).resolve(), report, root=Path(before["root"]))
        print(json.dumps({"ok": report["ok"],
                          "roots": {n: r["changed"] for n, r in report["roots"].items()}},
                         ensure_ascii=False, sort_keys=True))
        return 0 if report["ok"] else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""报告运行目录、状态与**显式发布**（P1-32）。

一次报告 = 一个服务端生成的 32 位 ``report_id`` + 一个只属于它的私有工作目录。
模型/用户永远拿不到"往哪个目录写"的话语权：目录由当前用户的
:class:`~deeptutor.services.path_service.PathService` 与已登记 subject 推出，
文件名只允许裸 basename。

目录形状（C11）::

    <current user>/workspace/subjects/<sid>/_report_runs/<rid>/      # 私有 staging
        metadata.json     权威 metadata（服务端专用字段可扩展）
        attempts/         P33/P34 的"本次 attempt"记录
        work/             唯一可写工作目录：报告正文、PDF、chart_N.png
    <current user>/subjects/<sid>/reports/<rid>/                     # 正式产物（仅发布后存在）
        report.md / report.pdf / chart_N.png
        metadata.json     只含 ReportMetadata 契约字段的公开投影

三件被刻意分开的事：

* **running ≠ 可见。** create 只建私有目录；正式 URL 只在
  :func:`publish_report_run` 提交成功后存在，失败/取消一律没有 URL，也绝不覆盖
  同 id 的旧 completed。
* **声明 ≠ 事实。** publish 的 ``files`` 是服务端已验证清单（大小/sha256/角色），
  发布时逐项重新读源文件、边复制边算摘要，再原子提交目录；模型自签的清单、
  外部源路径、symlink 与穿越路径都被拒绝。
* **活跃 ≠ PID 存在。** 活跃性只由**本进程**的登记表证明：本进程 create 后未释放
  才算 running；只有 ``owner_pid`` 这个整数存在一律不算。别的进程留下的
  ``running`` 记录由 :func:`mark_abandoned_if_stale` 识别为 ``abandoned``。
  这是进程内/文件状态的诚实边界，不是跨进程调度器——本模块不引入 DB 或全局队列。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any
import uuid

from deeptutor.services.pdf import report_inputs
from deeptutor.subjects import json_store, store, subject_operations
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    SubjectStorageError,
    subject_error,
)

SCHEMA_VERSION = 1

#: 私有运行根（相对 subject 数据目录）与正式产物的目录名。
REPORT_RUNS_DIRNAME = "_report_runs"
REPORTS_DIRNAME = "reports"
WORKDIR_NAME = "work"
ATTEMPTS_DIRNAME = "attempts"
METADATA_NAME = "metadata.json"

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_ABANDONED = "abandoned"
STATUSES = frozenset({STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED, STATUS_ABANDONED})

VERIFICATION_NOT_REQUESTED = "not_requested"
VERIFICATION_PASSED = "passed"
VERIFICATION_FAILED = "failed"
VERIFICATION_STATUSES = frozenset(
    {VERIFICATION_NOT_REQUESTED, VERIFICATION_PASSED, VERIFICATION_FAILED}
)

ROLE_MARKDOWN = "markdown"
ROLE_PDF = "pdf"
ROLE_CHART = "chart"
ROLES = frozenset({ROLE_MARKDOWN, ROLE_PDF, ROLE_CHART})

#: 每份报告最多 8 张图（与 P31/P34 同一上限）。
MAX_CHART_FILES = 8

#: 单次发布允许拷贝的最大字节数（正文/PDF/单图各自）。10MiB 覆盖单图上限，
#: 同时挡住"把整个目录塞进一个声明"的输入。
MAX_PUBLISHED_FILE_BYTES = 64 * 1024 * 1024

#: ``ReportFile.path``：单个裸文件名，不是路径（与 schemas.json 的正则一致）。
REPORT_FILE_PATH_RE = re.compile(r"^(?!\.\.?$)[^/\\\x00-\x1f]+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_REPORT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
#: 旧流水线写出的已知报告名（``report-<秒级时间戳>.md/.pdf``）。
LEGACY_REPORT_RE = re.compile(r"^report-\d+\.(?:md|pdf)$")
#: 已知的旧图名（``chart_1.png`` .. ``chart_8.png``）：与执行器/输入门共用同一份正则。
_CHART_NAME_RE = report_inputs.CHART_BASENAME_RE

_MAX_REVIEWED_FROM_CHARS = 200
_COPY_CHUNK = 64 * 1024


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReportFile:
    """一个已验证的产物条目；字段与 ``schemas.json#ReportFile`` 一致。"""

    path: str
    size: int
    sha256: str
    role: str

    def as_contract(self) -> dict[str, Any]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256, "role": self.role}


@dataclass(frozen=True)
class ReportRun:
    """一次报告的私有身份；``staging_dir``/``public_dir`` 都是服务端推出的路径。"""

    report_id: str
    subject_id: str
    staging_dir: Path
    public_dir: Path
    created_at: int
    owner_pid: int
    reviewed_from: str | None = None

    @property
    def workdir(self) -> Path:
        """唯一允许写宿主文件的目录（P33 只挂载它）。"""
        return self.staging_dir / WORKDIR_NAME

    @property
    def attempts_dir(self) -> Path:
        return self.staging_dir / ATTEMPTS_DIRNAME

    @property
    def metadata_path(self) -> Path:
        return self.staging_dir / METADATA_NAME


@dataclass(frozen=True)
class ReportManifest:
    """``ReportMetadata`` 字段 + 服务端内部路径。

    :meth:`as_contract` 是**唯一**可以对外/写进公开 ``metadata.json`` 的投影：
    它只含 schema 里的契约字段（有意不含 ``owner_pid``——那是宿主诊断，
    留在私有 metadata 里）。``staging_dir``/``public_dir``/``metadata_path``
    是服务端内部信息，绝不进入任何对外 payload。
    """

    schema_version: int
    report_id: str
    subject_id: str
    status: str
    created_at: int
    reviewed_from: str | None
    verification_status: str
    files: tuple[ReportFile, ...]
    staging_dir: Path | None = None
    public_dir: Path | None = None
    metadata_path: Path | None = None
    owner_pid: int | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "subject_id": self.subject_id,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_from": self.reviewed_from,
            "verification_status": self.verification_status,
            "files": [entry.as_contract() for entry in self.files],
        }

    def file_for_role(self, role: str) -> ReportFile | None:
        for entry in self.files:
            if entry.role == role:
                return entry
        return None


# ---------------------------------------------------------------------------
# 拥有者出生标识（PID 复用不能冒充"原拥有者还活着"）
# ---------------------------------------------------------------------------
def process_birth_marker(pid: int) -> str | None:
    """Linux ``/proc/<pid>/stat`` 的 starttime（第 22 个字段）作为进程出生标识。

    不可读（进程已结束 / 非 Linux）返回 ``None``——此时**不能**声称"还活着"。
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # comm 字段可能含空格/括号：从最后一个 ')' 之后再切分。
    tail = stat.rsplit(")", 1)[-1].split()
    if len(tail) <= 19:
        return None
    return tail[19]


def _owner_state(manifest: "ReportManifest") -> str:
    """返回 ``self_stale`` / ``dead`` / ``foreign_alive`` / ``unknown``。

    * 本进程是 owner：不在活跃登记表里就说明本 run 已经结束（``self_stale``）；
    * 其它进程是 owner：原进程明确不存在或 starttime 不匹配（PID 复用）才判定
      ``dead``；出生标识匹配为 ``foreign_alive``；不可读/缺失证据为 ``unknown``。
    """
    pid = manifest.owner_pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        return "unknown"
    birth = manifest.extra.get("owner_birth")
    current = process_birth_marker(pid)
    if pid == os.getpid():
        return "self_stale"
    if current is None:
        # Unreadable /proc (or another platform) is not evidence of death.
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "dead"
        except OSError:
            return "unknown"
        return "unknown"
    if not isinstance(birth, str) or not birth:
        return "unknown"
    return "foreign_alive" if current == birth else "dead"


# ---------------------------------------------------------------------------
# 进程内活跃登记（不是 PID 猜测）
# ---------------------------------------------------------------------------
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RUNS: dict[str, tuple[int, str]] = {}
_ACTIVE_LEASES: dict[str, subject_operations.ActivityLease] = {}


def _register_active(
    run: ReportRun, lease: subject_operations.ActivityLease | None = None
) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS[run.report_id] = (os.getpid(), str(run.staging_dir))
        if lease is not None:
            _ACTIVE_LEASES[run.report_id] = lease


def _release_active(report_id: str) -> bool:
    with _ACTIVE_LOCK:
        return _ACTIVE_RUNS.pop(report_id, None) is not None


def report_run_is_active(run: ReportRun | ReportManifest) -> bool:
    """本进程是否仍持有这次 run 的活跃登记（PID 存在不算证明）。"""
    report_id = run.report_id
    staging = run.staging_dir
    with _ACTIVE_LOCK:
        entry = _ACTIVE_RUNS.get(report_id)
    if entry is None:
        return False
    pid, path = entry
    if pid != os.getpid():
        return False
    return staging is None or str(staging) == path


def active_report_runs() -> tuple[str, ...]:
    with _ACTIVE_LOCK:
        return tuple(sorted(_ACTIVE_RUNS))


def release_report_run(run: ReportRun) -> None:
    """释放活跃登记与运行租约（幂等）；publish/fail 都会在 ``finally`` 里调用。"""
    _release_active(run.report_id)
    with _ACTIVE_LOCK:
        lease = _ACTIVE_LEASES.pop(run.report_id, None)
    if lease is not None:
        lease.release()


def _reset_active_runs_for_tests() -> None:
    with _ACTIVE_LOCK:
        leases = list(_ACTIVE_LEASES.values())
        _ACTIVE_RUNS.clear()
        _ACTIVE_LEASES.clear()
    for lease in leases:
        lease.release()


# ---------------------------------------------------------------------------
# 校验工具
# ---------------------------------------------------------------------------
def _require_registered_subject(subject_id: object) -> Path:
    """当前用户 + 已登记 subject 的数据目录（未登记 404，非法 id 400）。"""
    if not isinstance(subject_id, str):
        raise json_store.invalid_input("科目标识必须是字符串")
    return store.subject_dir(subject_id)


def _public_reports_dir(subject: Path) -> Path:
    """正式产物根：**当前用户**的 public outputs 下的 ``subjects/<sid>/reports``。"""
    service = store.current_subject_paths()
    root = Path(service.get_public_outputs_root()) / "subjects" / subject.name / REPORTS_DIRNAME
    return json_store.confined(Path(service.get_public_outputs_root()), root)


def _require_report_id(value: object) -> str:
    if not isinstance(value, str) or not _REPORT_ID_RE.fullmatch(value):
        raise json_store.invalid_input("report_id 必须是 32 位小写十六进制")
    return value


def _require_reviewed_from(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise json_store.invalid_input("reviewed_from 必须是字符串或空")
    text = value.strip()
    if not text:
        return None
    if len(text) > _MAX_REVIEWED_FROM_CHARS:
        raise json_store.invalid_input("reviewed_from 过长")
    return text


def _require_verification_status(value: object) -> str:
    if not isinstance(value, str) or value not in VERIFICATION_STATUSES:
        raise json_store.invalid_input("verification_status 取值无效")
    return value


def _require_file_entry(entry: object) -> ReportFile:
    """把一个声明条目收成 :class:`ReportFile`；形状不对就是 ``invalid_input``。"""
    if isinstance(entry, ReportFile):
        payload: Mapping[str, Any] = entry.as_contract()
    elif isinstance(entry, Mapping):
        payload = entry
    else:
        raise json_store.invalid_input("产物条目必须是对象")
    unknown = set(payload) - {"path", "size", "sha256", "role"}
    if unknown:
        raise json_store.invalid_input("产物条目包含未知字段")
    path = payload.get("path")
    if not isinstance(path, str) or not REPORT_FILE_PATH_RE.fullmatch(path):
        raise json_store.invalid_input("产物路径必须是单个裸文件名")
    size = payload.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise json_store.invalid_input("产物大小必须是非负整数")
    sha = payload.get("sha256")
    if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
        raise json_store.invalid_input("产物摘要必须是 64 位小写十六进制")
    role = payload.get("role")
    if not isinstance(role, str) or role not in ROLES:
        raise json_store.invalid_input("产物角色无效")
    _require_published_name(path, role)
    return ReportFile(path=path, size=size, sha256=sha, role=role)


#: 正式目录里**允许**出现的文件名（role 与名字一一对应，不能混用）。
PUBLISHED_ROLE_NAMES: Mapping[str, str] = {ROLE_MARKDOWN: "report.md", ROLE_PDF: "report.pdf"}
#: 明确不许发布的私有/运行期文件名：权威 metadata、脚本、日志、锁、缓存。
RESERVED_PUBLISH_NAMES = frozenset(
    {METADATA_NAME, "_chart.py", "_ode_check.py", "_chart_err.txt", "_spec.json", ".deeptutor.lock"}
)
RESERVED_PUBLISH_PREFIXES = (".", "_")


def _require_published_name(path: str, role: str) -> None:
    """新发布产物必须是固定 role/名字；脚本/日志/缓存/metadata 一律不许发布。"""
    if path in RESERVED_PUBLISH_NAMES:
        raise json_store.invalid_input("该文件名是服务端私有文件，不能发布")
    if path.startswith(RESERVED_PUBLISH_PREFIXES):
        raise json_store.invalid_input("隐藏/下划线开头的文件不能发布")
    expected = PUBLISHED_ROLE_NAMES.get(role)
    if expected is not None:
        if path != expected:
            raise json_store.invalid_input(f"{role} 角色只能发布固定文件名 {expected}")
        return
    # chart：必须是服务端预分配的 chart_N.png（N 1..8），与执行器同一份正则。
    try:
        report_inputs.chart_target_basename(path)
    except SubjectOperationError as exc:
        raise json_store.invalid_input("chart 角色只能发布 chart_N.png") from exc


def _require_file_set(files: object) -> tuple[ReportFile, ...]:
    """发布清单的形状约束：一份正文、一份 PDF、图表可选且不超过 8、path 不重复。"""
    if files is None or isinstance(files, (str, bytes, Mapping)):
        raise json_store.invalid_input("发布清单必须是产物条目序列")
    try:
        entries = tuple(_require_file_entry(item) for item in files)  # type: ignore[union-attr]
    except TypeError as exc:
        raise json_store.invalid_input("发布清单必须是产物条目序列") from exc
    paths = [entry.path for entry in entries]
    if len(set(paths)) != len(paths):
        raise json_store.invalid_input("发布清单存在重复路径")
    roles = {role: sum(1 for entry in entries if entry.role == role) for role in ROLES}
    if roles[ROLE_MARKDOWN] != 1:
        raise json_store.invalid_input("发布清单必须且只能有一份 Markdown 正文")
    if roles[ROLE_PDF] != 1:
        raise json_store.invalid_input("发布清单必须且只能有一份 PDF")
    if roles[ROLE_CHART] > MAX_CHART_FILES:
        raise json_store.invalid_input(f"图表数量超过上限（最多 {MAX_CHART_FILES} 张）")
    if any(entry.size == 0 for entry in entries):
        raise json_store.invalid_input("空文件不能发布")
    return entries


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_COPY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_and_hash(source: Path, destination: Path) -> tuple[int, str]:
    """把 *source* 复制到 *destination*，返回真实 ``(size, sha256)``。

    用 ``O_NOFOLLOW`` 打开，并对**同一个 fd** 边读边算摘要：校验依据是复制到的
    字节本身，而不是先看路径再复制（避免中间被换成链接/别的文件）。
    """
    digest = hashlib.sha256()
    total = 0
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    try:
        info = os.fstat(descriptor)
        import stat as _stat

        if not _stat.S_ISREG(info.st_mode):
            raise json_store.invalid_input("发布的产物必须是常规文件")
        with os.fdopen(descriptor, "rb", closefd=False) as reader, destination.open("wb") as writer:
            while True:
                chunk = reader.read(_COPY_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PUBLISHED_FILE_BYTES:
                    raise json_store.invalid_input("产物超过单文件大小上限")
                digest.update(chunk)
                writer.write(chunk)
    finally:
        os.close(descriptor)
    return total, digest.hexdigest()


# ---------------------------------------------------------------------------
# metadata 读
# ---------------------------------------------------------------------------
def _manifest_from_payload(
    payload: object, *, staging: Path | None, public: Path | None, metadata_path: Path | None
) -> ReportManifest:
    """把一份 metadata 收成 :class:`ReportManifest`；字段不合契约即 storage_corrupt。

    先做**严格类型检查**再枚举/正则：``status``/``verification_status`` 必须是
    string（坏 list/dict 在 ``in set`` 上会抛 unhashable TypeError），
    ``schema_version`` 必须是真 int 且恰为 1（``True == 1`` 不算通过）。被拒的
    原值只留在服务端诊断里，不回显。
    """
    if not isinstance(payload, Mapping):
        raise json_store.corrupt_error(METADATA_NAME, "顶层不是对象")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise json_store.corrupt_error(METADATA_NAME, "schema_version 不受支持")
    report_id = payload.get("report_id")
    if not isinstance(report_id, str) or not _REPORT_ID_RE.fullmatch(report_id):
        raise json_store.corrupt_error(METADATA_NAME, "report_id 非法")
    subject_id = payload.get("subject_id")
    if not isinstance(subject_id, str) or not store.is_valid_subject_id(subject_id):
        raise json_store.corrupt_error(METADATA_NAME, "subject_id 非法")
    status = payload.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        raise json_store.corrupt_error(METADATA_NAME, "status 非法")
    created_at = payload.get("created_at")
    if isinstance(created_at, bool) or not isinstance(created_at, int) or created_at < 0:
        raise json_store.corrupt_error(METADATA_NAME, "created_at 非法")
    reviewed_from = payload.get("reviewed_from")
    if reviewed_from is not None and not isinstance(reviewed_from, str):
        raise json_store.corrupt_error(METADATA_NAME, "reviewed_from 非法")
    verification_status = payload.get("verification_status")
    if not isinstance(verification_status, str) or verification_status not in VERIFICATION_STATUSES:
        raise json_store.corrupt_error(METADATA_NAME, "verification_status 非法")
    if status == STATUS_COMPLETED and verification_status == VERIFICATION_FAILED:
        raise json_store.corrupt_error(METADATA_NAME, "completed 不得是失败验证")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise json_store.corrupt_error(METADATA_NAME, "files 不是数组")
    files: list[ReportFile] = []
    for item in raw_files:
        try:
            entry = _require_file_entry(item)
        except SubjectOperationError as exc:
            raise json_store.corrupt_error(METADATA_NAME, "files 条目非法") from exc
        if not isinstance(item, Mapping) or set(item) != {"path", "size", "sha256", "role"}:
            raise json_store.corrupt_error(METADATA_NAME, "files 条目字段非法")
        files.append(entry)
    owner_pid = payload.get("owner_pid")
    if owner_pid is not None and (
        isinstance(owner_pid, bool) or not isinstance(owner_pid, int) or owner_pid < 1
    ):
        raise json_store.corrupt_error(METADATA_NAME, "owner_pid 非法")
    contract = {
        "schema_version",
        "report_id",
        "subject_id",
        "status",
        "created_at",
        "reviewed_from",
        "verification_status",
        "files",
        "owner_pid",
    }
    return ReportManifest(
        schema_version=SCHEMA_VERSION,
        report_id=report_id,
        subject_id=subject_id,
        status=status,
        created_at=created_at,
        reviewed_from=reviewed_from,
        verification_status=verification_status,
        files=tuple(files),
        staging_dir=staging,
        public_dir=public,
        metadata_path=metadata_path,
        owner_pid=owner_pid,
        extra={key: value for key, value in payload.items() if key not in contract},
    )


def read_run_manifest(run: ReportRun) -> ReportManifest:
    """读私有权威 metadata（未创建/损坏都会明确失败）。"""
    run = _require_run(run)
    path = run.metadata_path
    if not path.is_file():
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    payload = json_store.read_object(path, default={})
    manifest = _manifest_from_payload(
        payload, staging=run.staging_dir, public=run.public_dir, metadata_path=path
    )
    if manifest.report_id != run.report_id or manifest.subject_id != run.subject_id:
        raise json_store.corrupt_error(METADATA_NAME, "metadata 与运行身份不一致")
    return manifest


def read_published_manifest(subject_id: str, report_id: str) -> ReportManifest | None:
    """读一份**已发布**的 metadata；不存在或未完成返回 ``None``（只读，不建目录）。"""
    subject = _require_registered_subject(subject_id)
    rid = _require_report_id(report_id)
    reports_dir = _public_reports_dir(subject)
    if not reports_dir.is_dir():
        return None
    public_dir = reports_dir / rid
    metadata = public_dir / METADATA_NAME
    if public_dir.is_symlink() or not metadata.is_file():
        return None
    payload = json_store.read_object(metadata, default={})
    manifest = _manifest_from_payload(
        payload, staging=None, public=public_dir, metadata_path=metadata
    )
    if manifest.report_id != rid or manifest.subject_id != subject.name:
        raise json_store.corrupt_error(METADATA_NAME, "公开 metadata 与目录不一致")
    if manifest.status != STATUS_COMPLETED:
        return None
    return manifest


def _derive_run_paths(subject: Path, report_id: str) -> tuple[Path, Path]:
    """从**当前用户 + 已登记 subject + 服务端 rid** 推出 (staging, public)。

    这是"服务端所有权"的唯一定义：任何传入的 ``ReportRun`` 都必须与它对上。
    """
    runs_root = subject / REPORT_RUNS_DIRNAME
    return runs_root / report_id, _public_reports_dir(subject) / report_id


def require_report_run(run: object, *, require_running: bool = False) -> ReportRun:
    """服务端身份门：类型、id、当前用户/已登记 subject、路径全部重新推出后比对。

    ``dataclass`` 类型**不是**所有权证明：``replace(run, public_dir=…)`` 之类的伪造
    对象必须在这里被拒绝，而不是被拿去做 mkdir/unlink/write/mount。合法读取允许
    消费端重建对象（只要路径与服务端推出的完全一致）；写入/执行还要 ``running``。
    """
    if type(run) is not ReportRun:
        raise json_store.invalid_input("run 必须是服务端创建的 ReportRun")
    report_id = _require_report_id(run.report_id)
    subject = _require_registered_subject(run.subject_id)
    expected_staging, expected_public = _derive_run_paths(subject, report_id)
    actual = {
        "staging_dir": Path(run.staging_dir),
        "public_dir": Path(run.public_dir),
        "workdir": Path(run.workdir),
        "attempts_dir": Path(run.attempts_dir),
        "metadata_path": Path(run.metadata_path),
    }
    expected = {
        "staging_dir": expected_staging,
        "public_dir": expected_public,
        "workdir": expected_staging / WORKDIR_NAME,
        "attempts_dir": expected_staging / ATTEMPTS_DIRNAME,
        "metadata_path": expected_staging / METADATA_NAME,
    }
    for key, value in expected.items():
        if actual[key] != value:
            raise json_store.invalid_input("运行路径与服务端推出的位置不一致")
        # The anchor must be the registered subject, not a potentially linked
        # descendant such as work/. Path equality alone does not reject links.
        if key == "public_dir":
            json_store.confined(
                Path(store.current_subject_paths().get_public_outputs_root()), value
            )
        else:
            json_store.confined(subject, value)
    if require_running:
        manifest = read_run_manifest(run)
        if manifest.status != STATUS_RUNNING:
            raise json_store.invalid_input("只有 running 的运行可以执行或写入")
    return run


def _require_run(run: object, *, require_running: bool = False) -> ReportRun:
    """:func:`require_report_run` 的内部别名。"""
    return require_report_run(run, require_running=require_running)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def create_report_run(
    subject_id: str,
    *,
    reviewed_from: str | None = None,
    lease: subject_operations.ActivityLease | None = None,
) -> ReportRun:
    """Every caller, including the synchronous API, owns a validated lease."""
    if lease is None:
        lease = subject_operations.acquire_activity(subject_id, kind="report")
    else:
        subject_operations.require_activity(lease, subject_id, mode=subject_operations.SHARED)
    try:
        return _create_report_run(subject_id, reviewed_from=reviewed_from, lease=lease)
    except BaseException:
        lease.release()
        raise


def _create_report_run(
    subject_id: str,
    *,
    reviewed_from: str | None = None,
    lease: subject_operations.ActivityLease | None = None,
) -> ReportRun:
    """创建一个新的报告运行：服务端 id + 私有目录 + ``running`` metadata。

    * ``report_id`` 是 :func:`uuid.uuid4().hex`（32 位），调用方不能指定；
    * 私有 staging ``<subject>/_report_runs/<rid>`` 与正式目录
      ``.../reports/<rid>`` 都由当前用户 PathService 推出；
    * 同 id 已存在（staging 或正式目录）→ 拒绝，绝不覆盖；
    * 只建私有目录，不产生任何正式 URL。
    """
    subject = _require_registered_subject(subject_id)
    reviewed = _require_reviewed_from(reviewed_from)
    runs_root = subject / REPORT_RUNS_DIRNAME
    json_store.make_directory(runs_root)
    json_store.confined(subject, runs_root)

    report_id = uuid.uuid4().hex
    staging_dir = json_store.confined(runs_root, runs_root / report_id)
    public_dir = _public_reports_dir(subject) / report_id
    if (
        staging_dir.exists()
        or staging_dir.is_symlink()
        or public_dir.exists()
        or public_dir.is_symlink()
    ):
        # 服务端生成的 id 撞上已有目录：宁可失败，也不复用/覆盖别人的产物。
        raise subject_error(ErrorCode.INTERNAL_ERROR)

    created_at = max(0, int(time.time()))
    owner_pid = os.getpid()
    owner_birth = process_birth_marker(owner_pid)
    run = ReportRun(
        report_id=report_id,
        subject_id=subject.name,
        staging_dir=staging_dir,
        public_dir=public_dir,
        created_at=created_at,
        owner_pid=owner_pid,
        reviewed_from=reviewed,
    )
    # **原子认领**：exist_ok=False 的 mkdir 是所有权判定；只有它成功的那次调用才有
    # 资格清理这个目录。检查 exists 之后再 mkdir 失败（竞争失败者）绝不能 rmtree，
    # 否则会把成功者刚建好的 staging 删掉。
    try:
        json_store.make_directory(staging_dir, exist_ok=False)
    except SubjectStorageError as exc:
        raise subject_error(ErrorCode.INTERNAL_ERROR, cause=exc) from exc
    try:
        json_store.make_directory(run.workdir)
        json_store.make_directory(run.attempts_dir)
        json_store.atomic_write_object(
            run.metadata_path,
            {
                "schema_version": SCHEMA_VERSION,
                "report_id": report_id,
                "subject_id": subject.name,
                "status": STATUS_RUNNING,
                "created_at": created_at,
                "reviewed_from": reviewed,
                "verification_status": VERIFICATION_NOT_REQUESTED,
                "files": [],
                "owner_pid": owner_pid,
                # 进程出生标识：PID 复用不能冒充"原拥有者还活着"。
                "owner_birth": owner_birth,
                "staging_dir": str(staging_dir),
                "public_dir": str(public_dir),
            },
        )
    except BaseException:
        # 只清理**本调用已经认领**的那棵树；公共目录一律不碰。
        shutil.rmtree(staging_dir, ignore_errors=True)
        if lease is not None:
            lease.release()
        raise
    _register_active(run, lease)
    return run


# ---------------------------------------------------------------------------
# 状态迁移
# ---------------------------------------------------------------------------
def _write_private_metadata(run: ReportRun, manifest: ReportManifest) -> None:
    payload: dict[str, Any] = dict(manifest.as_contract())
    # 私有扩展：服务端内部路径与 owner_pid 只留在这里，绝不进公开投影。
    payload["owner_pid"] = manifest.owner_pid
    payload["staging_dir"] = str(run.staging_dir)
    payload["public_dir"] = str(run.public_dir)
    payload.update(manifest.extra)
    json_store.atomic_write_object(run.metadata_path, payload)


def fail_report_run(run: ReportRun, *, detail: str = "") -> ReportManifest:
    """把本次运行标成 ``failed``（无 URL、无文件）并释放活跃登记。

    已经 ``completed`` 的运行不会被降级覆盖——失败不能抹掉已发布的旧结果。
    """
    run = _require_run(run)
    try:
        # Reading can fail with missing-entry as well as typed storage errors.
        # Neither failure may retain active ownership or replace corrupt data.
        manifest = read_run_manifest(run)
        if manifest.status == STATUS_COMPLETED:
            return manifest
        failed = replace(
            manifest,
            status=STATUS_FAILED,
            files=(),
            verification_status=(
                VERIFICATION_FAILED
                if manifest.verification_status == VERIFICATION_FAILED
                else VERIFICATION_NOT_REQUESTED
            ),
        )
        if detail:
            failed = replace(failed, extra={**manifest.extra, "failure_detail": str(detail)[:300]})
        _write_private_metadata(run, failed)
        return failed
    finally:
        release_report_run(run)


def mark_abandoned_if_stale(run: ReportRun) -> ReportManifest | None:
    """把"本进程已不再持有、记录仍是 running"的运行标成 ``abandoned``。

    返回新 manifest；运行仍然活跃或已经不是 running 时返回 ``None``（不改写）。
    本进程依登记表；其它进程必须证明原拥有者结束。仅 PID 存在不算活跃证明，
    无法读取出生标识时保守保持 running。
    """
    run = _require_run(run)
    manifest = read_run_manifest(run)
    if manifest.status != STATUS_RUNNING or report_run_is_active(manifest):
        return None
    state = _owner_state(manifest)
    if state in ("foreign_alive", "unknown"):
        # 无法证明原拥有者已结束：保守保持 running（未知 ≠ abandoned），
        # 但也不把它当成"已证明 active"。
        return None
    abandoned = replace(manifest, status=STATUS_ABANDONED, files=())
    _write_private_metadata(run, abandoned)
    release_report_run(run)
    return abandoned


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------
def _finalize_rejected_publish(run: ReportRun) -> None:
    """被拒绝的发布必须留下 ``failed`` 状态、释放活跃登记、且没有正式产物。

    只在**能读到有效 metadata** 时改写状态；metadata 已损坏时保留损坏原件并只释放
    活跃登记（不能"修复"成新的空 metadata，也不能把原始错误换成成功）。任何收尾
    异常都不允许盖过调用方正在抛出的原始错误。
    """
    try:
        manifest = read_run_manifest(run)
        if manifest.status != STATUS_COMPLETED:
            _write_private_metadata(run, replace(manifest, status=STATUS_FAILED, files=()))
    except (SubjectStorageError, SubjectOperationError):
        # Preserve invalid/missing metadata and the original publish exception.
        pass
    finally:
        release_report_run(run)


@dataclass(frozen=True)
class _PreparedPublication:
    run: ReportRun
    manifest: ReportManifest
    staging: Path


_PUBLICATION_LOCK = threading.Lock()
_PUBLICATIONS: set[str] = set()


def _discard_report_publication(prepared: _PreparedPublication) -> None:
    """Discard only this preparation's hidden directory and ownership."""
    try:
        run = _require_run(prepared.run)
        reports = _public_reports_dir(store.subject_dir(run.subject_id))
        expected = reports / f".publishing-{run.report_id}-{os.getpid()}"
        if prepared.staging != expected:
            raise json_store.invalid_input("发布暂存目录不属于当前任务")
        json_store.confined(reports, prepared.staging)
        shutil.rmtree(prepared.staging, ignore_errors=True)
    finally:
        with _PUBLICATION_LOCK:
            _PUBLICATIONS.discard(str(prepared.run.staging_dir))


def _prepare_report_publication(
    run: ReportRun, *, files: Sequence[ReportFile | Mapping[str, Any]], verification_status: str
) -> _PreparedPublication:
    """Copy/hash off-loop without completing metadata or exposing a report.

    A preparation remains owned until commit/discard. Refuse duplicate same-run
    preparations before failure finalization can damage the legitimate owner.
    """
    run = _require_run(run)
    key = str(run.staging_dir)
    with _PUBLICATION_LOCK:
        if key in _PUBLICATIONS:
            raise json_store.invalid_input("该报告正在准备发布")
        _PUBLICATIONS.add(key)
    try:
        status = _require_verification_status(verification_status)
        if status == VERIFICATION_FAILED:
            raise subject_error(ErrorCode.CHART_FAILED)
        declared = _require_file_set(files)

        current = read_run_manifest(run)
        if current.status != STATUS_RUNNING:
            # 已发布/已失败/已放弃的运行不接受第二次发布。
            raise json_store.invalid_input("只有 running 的运行可以发布")
        if run.public_dir.exists() or run.public_dir.is_symlink():
            raise json_store.invalid_input("该 report_id 已存在正式产物，拒绝覆盖")

        reports_dir = _public_reports_dir(store.subject_dir(run.subject_id))
        json_store.make_directory(reports_dir)
        staging_public = reports_dir / f".publishing-{run.report_id}-{os.getpid()}"

        workdir = run.workdir
        json_store.ensure_trusted_root(workdir)
        # Reserve under the short lock; large copies never hold a lock that the
        # event-loop commit needs. Each preparation owns a unique hidden tree.
        with json_store.json_transaction(reports_dir):
            if run.public_dir.exists() or run.public_dir.is_symlink():
                raise json_store.invalid_input("该 report_id 已存在正式产物，拒绝覆盖")
            if staging_public.exists() or staging_public.is_symlink():
                raise json_store.invalid_input("发布暂存目录已存在")
            json_store.make_directory(staging_public, exist_ok=False)
        try:
            for entry in declared:
                source = json_store.confined(workdir, workdir / entry.path)
                if not source.is_file():
                    raise json_store.invalid_input("声明的产物不存在")
                size, digest = _copy_and_hash(source, staging_public / entry.path)
                if size == 0:
                    raise json_store.invalid_input("空文件不能发布")
                if size != entry.size or digest != entry.sha256:
                    raise json_store.invalid_input("产物与声明的大小/摘要不一致")
            completed = replace(
                current, status=STATUS_COMPLETED, files=declared,
                verification_status=(VERIFICATION_PASSED if status == VERIFICATION_PASSED
                                     else VERIFICATION_NOT_REQUESTED),
            )
            json_store.atomic_write_object(staging_public / METADATA_NAME, completed.as_contract())
        except BaseException:
            shutil.rmtree(staging_public, ignore_errors=True)
            raise
    except BaseException:
        with _PUBLICATION_LOCK:
            _PUBLICATIONS.discard(key)
        _finalize_rejected_publish(run)
        raise
    return _PreparedPublication(run, completed, staging_public)


def _commit_report_publication(prepared: _PreparedPublication) -> ReportManifest:
    """Only the live async caller commits; no large file copies happen here."""
    run = prepared.run
    try:
        run = _require_run(run)
        reports = _public_reports_dir(store.subject_dir(run.subject_id))
        expected = reports / f".publishing-{run.report_id}-{os.getpid()}"
        if prepared.staging != expected:
            raise json_store.invalid_input("发布暂存目录不属于当前任务")
        json_store.confined(reports, prepared.staging)
        with json_store.json_transaction(reports):
            current = read_run_manifest(run)
            if current.status != STATUS_RUNNING:
                raise json_store.invalid_input("只有 running 的运行可以发布")
            if run.public_dir.exists() or run.public_dir.is_symlink():
                raise json_store.invalid_input("该 report_id 已存在正式产物，拒绝覆盖")
            _write_private_metadata(run, prepared.manifest)
            try:
                os.replace(prepared.staging, run.public_dir)
            except OSError as exc:
                _write_private_metadata(run, replace(prepared.manifest, status=STATUS_FAILED, files=()))
                raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
    except BaseException:
        _finalize_rejected_publish(run)
        raise
    finally:
        _discard_report_publication(prepared)
    release_report_run(run)
    return prepared.manifest


def publish_report_run(
    run: ReportRun, *, files: Sequence[ReportFile | Mapping[str, Any]], verification_status: str
) -> ReportManifest:
    """Synchronous compatibility API; same validation, copy, and atomic commit.

    Async orchestration uses the internal prepare/commit split so cancellation
    can discard an off-loop copy before any completed metadata/URL is published.
    """
    prepared = _prepare_report_publication(run, files=files, verification_status=verification_status)
    return _commit_report_publication(prepared)


def report_url(manifest: ReportManifest) -> str | None:
    """完成态 manifest 的正式 PDF URL；其它状态一律没有 URL。"""
    if manifest.status != STATUS_COMPLETED:
        return None
    pdf = manifest.file_for_role(ROLE_PDF)
    if pdf is None:
        return None
    return f"/api/outputs/subjects/{manifest.subject_id}/{REPORTS_DIRNAME}/{manifest.report_id}/{pdf.path}"


# ---------------------------------------------------------------------------
# review 解析
# ---------------------------------------------------------------------------
def _published_run_ids(subject: Path) -> list[tuple[int, str]]:
    """正式目录里**已知**的完成态运行：``(created_at, rid)``。"""
    reports_dir = _public_reports_dir(subject)
    if not reports_dir.is_dir():
        return []
    found: list[tuple[int, str]] = []
    for entry in sorted(reports_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.is_symlink() or not _REPORT_ID_RE.fullmatch(entry.name):
            continue
        manifest = read_published_manifest(subject.name, entry.name)
        if manifest is not None:
            found.append((manifest.created_at, manifest.report_id))
    return found


def _legacy_manifest(subject: Path, markdown: Path) -> ReportManifest:
    """为一个**已知**旧正文构造受约束的 legacy manifest（不伪造 UUID、不改原文件）。

    ``report_id`` 用 ``legacy:<basename>`` 标识；``files`` 列出同科的正文/PDF 与
    已存在的 ``chart_N.png``（旧图的已知形状），供 S09 复制到新 revision。
    """
    directory = markdown.parent
    files: list[ReportFile] = []

    def add(name: str, role: str) -> None:
        candidate = directory / name
        if candidate.is_symlink() or not candidate.is_file():
            return
        files.append(
            ReportFile(
                path=name, size=candidate.stat().st_size, sha256=_sha256_file(candidate), role=role
            )
        )

    add(markdown.name, ROLE_MARKDOWN)
    add(markdown.with_suffix(".pdf").name, ROLE_PDF)
    for index in range(1, MAX_CHART_FILES + 1):
        add(f"chart_{index}.png", ROLE_CHART)
    return ReportManifest(
        schema_version=SCHEMA_VERSION,
        report_id=f"legacy:{markdown.name}",
        subject_id=subject.name,
        status=STATUS_COMPLETED,
        created_at=max(0, int(markdown.stat().st_mtime)),
        reviewed_from=markdown.name,
        verification_status=VERIFICATION_NOT_REQUESTED,
        files=tuple(files),
        staging_dir=None,
        public_dir=directory,
        metadata_path=None,
        owner_pid=None,
        extra={"legacy": True},
    )


def _resolve_legacy_path(subject: Path, legacy_path: object) -> ReportManifest:
    """把兼容输入规范化到**本 subject 已有报告目录中的已知 .md/.pdf**。

    接受：已知旧名 ``report-<ts>.md/.pdf``（直接放在 reports 目录下），或
    ``reports/<已发布 rid>/`` 里的产物。拒绝：跨科路径、绝对外部路径、symlink
    越界、未知命名（目录里随便一个 md 不算已知）。
    """
    if not isinstance(legacy_path, (str, Path)) or isinstance(legacy_path, bool):
        raise json_store.invalid_input("report_path 必须是字符串")
    text = str(legacy_path).strip()
    if not text:
        raise json_store.invalid_input("report_path 不能为空")
    reports_dir = _public_reports_dir(subject)
    if not reports_dir.is_dir():
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    raw = Path(text)
    if raw.is_absolute():
        candidate = raw
    elif len(raw.parts) == 1:
        candidate = reports_dir / raw.name
    else:
        candidate = Path(text)
    try:
        relative = candidate.relative_to(reports_dir)
    except ValueError:
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND) from None
    if not relative.parts:
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    # 只允许"已知旧名"或"已发布 rid 目录里的产物"，并且整条路径不许有链接。
    narrowed = json_store.confined(reports_dir, candidate)
    if narrowed.is_symlink() or not narrowed.is_file():
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    if narrowed.suffix.lower() not in (".md", ".pdf"):
        raise json_store.invalid_input("只支持 .md/.pdf 旧报告")
    if len(relative.parts) == 1:
        if not LEGACY_REPORT_RE.fullmatch(relative.name):
            raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
        markdown = narrowed if narrowed.suffix.lower() == ".md" else narrowed.with_suffix(".md")
        if markdown.is_symlink() or not markdown.is_file():
            raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
        return _legacy_manifest(subject, markdown)
    report_id = relative.parts[0]
    manifest = read_published_manifest(subject.name, report_id)
    if manifest is None:
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    if len(relative.parts) != 2 or relative.parts[1] not in {
        entry.path for entry in manifest.files
    }:
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    return replace(manifest, reviewed_from=manifest.report_id)


def resolve_report_for_review(
    subject_id: str, *, report_id: str | None = None, legacy_path: str | None = None
) -> ReportManifest:
    """解析一次 review 的目标：只发现同 subject 的已知 completed 或受限 legacy。

    * ``report_id``：必须是本 subject 正式目录里的**完成态**运行；
    * ``legacy_path``：规范化后必须是本 subject 报告目录里的已知 ``.md``/``.pdf``
      （外部绝对路径、跨科、symlink 越界、陌生 md 都拒绝，且全程不读未知文件）；
    * 两者都省略：取最新一份已知完成报告（``running``/``failed``/``abandoned``
      一律不选）；没有任何候选时 404。

    返回的 ``reviewed_from`` 就是本次审查目标的标识（新 run 的 ``report_id`` 或
    legacy 正文名），S09 用它调用 :func:`create_report_run` 记录来源。旧文件不会被
    迁移或改写。
    """
    if report_id is not None and legacy_path is not None:
        raise json_store.invalid_input("report_id 与 report_path 不能同时给出")
    subject = _require_registered_subject(subject_id)

    if report_id is not None:
        rid = _require_report_id(report_id)
        manifest = read_published_manifest(subject.name, rid)
        if manifest is None:
            raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
        return replace(manifest, reviewed_from=rid)

    if legacy_path is not None:
        return _resolve_legacy_path(subject, legacy_path)

    candidates: list[tuple[int, int, ReportManifest]] = []
    for created_at, rid in _published_run_ids(subject):
        manifest = read_published_manifest(subject.name, rid)
        if manifest is not None:
            candidates.append((created_at, 2, replace(manifest, reviewed_from=rid)))
    reports_dir = _public_reports_dir(subject)
    if reports_dir.is_dir():
        for entry in sorted(reports_dir.iterdir(), key=lambda item: item.name):
            if entry.is_symlink() or not entry.is_file():
                continue
            if entry.suffix.lower() != ".md" or not LEGACY_REPORT_RE.fullmatch(entry.name):
                continue
            candidates.append(
                (max(0, int(entry.stat().st_mtime)), 1, _legacy_manifest(subject, entry))
            )
    if not candidates:
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND)
    candidates.sort(key=lambda item: (item[0], item[1], item[2].report_id))
    return candidates[-1][2]


__all__ = [
    "ATTEMPTS_DIRNAME",
    "LEGACY_REPORT_RE",
    "MAX_CHART_FILES",
    "MAX_PUBLISHED_FILE_BYTES",
    "METADATA_NAME",
    "REPORTS_DIRNAME",
    "REPORT_FILE_PATH_RE",
    "REPORT_RUNS_DIRNAME",
    "ROLES",
    "ROLE_CHART",
    "ROLE_MARKDOWN",
    "ROLE_PDF",
    "SCHEMA_VERSION",
    "STATUS_ABANDONED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_RUNNING",
    "STATUSES",
    "VERIFICATION_FAILED",
    "VERIFICATION_NOT_REQUESTED",
    "VERIFICATION_PASSED",
    "VERIFICATION_STATUSES",
    "WORKDIR_NAME",
    "PUBLISHED_ROLE_NAMES",
    "RESERVED_PUBLISH_NAMES",
    "ReportFile",
    "ReportManifest",
    "ReportRun",
    "active_report_runs",
    "create_report_run",
    "fail_report_run",
    "mark_abandoned_if_stale",
    "publish_report_run",
    "process_birth_marker",
    "read_published_manifest",
    "read_run_manifest",
    "release_report_run",
    "report_run_is_active",
    "report_url",
    "require_report_run",
    "resolve_report_for_review",
]

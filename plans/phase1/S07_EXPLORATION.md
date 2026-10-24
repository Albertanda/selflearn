# S07 已探索的文件清单 + 关键片段

本包由协调者在 S06-final 验收时从当前工作树生成，供 worker 直接定位。只读附件，不是代码实施结果。
优先阅读 START_S07.txt、C08/C01/C02 与本包；不重扫全仓、不重读旧长报告。实际修改时只打开相邻函数；新文件按卡实现。

已确认：start_turn 才是统一入口；legacy chat.py 不是本次入口。unified_ws.py 两个拒绝分支只 catch RuntimeError，需要窄修复。
已确认：store.subject_kb_base_dir() 会 mkdir；解析/挂载用 uploads.kb_base_path/kb_paths(create=False)，不能破坏 S05 的只读保证。
已确认：regenerate 在校验之前删除旧 assistant；应先验证原 snapshot scope，再进行任何删除。
已确认：_rag_kbs 排除 PageIndex 且 prompt 宣称 MCP；C13 本阶段只修现有 REST outline 的可达与说明，不新增 transport。manifest 的“不重复描述”仍须保留。
已确认：term_summary(term="") 不过滤却写“本学期”；无明确 term 时不注入该块，有 term 时必须显式传入该 term。
已确认：frontend 当前能力构造会覆盖 subject config，发送时 truthy 条件会丢 null，session hydration 未装 subject；三处均需贯通修复。

新文件：deeptutor/subjects/kb_scope.py；tests/phase1/test_p1_20.py…test_p1_24.py；web/lib/subject-scope.ts；web/tests/phase1-25.test.ts。

以下 SHA256 是发包时精确源码。已验收 source_artifacts 以 S06-final receipt 为准；本包补充冻结 S07 接缝。

## `deeptutor/subjects/store.py`

SHA256 `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23`。

当前 L150–L211：
```text
150: 
151: def subjects_root() -> Path:
152:     """Root of the current user's subject tree (``.../workspace/subjects``).
153: 
154:     Validated **before** it is created: if ``subjects`` is a symlink, whatever
155:     it points at is not this user's registry, so the call fails instead of
156:     reading or writing the target.
157:     """
158:     workspace = current_subject_paths().get_workspace_dir()
159:     json_store.ensure_trusted_root(workspace)
160:     root = workspace / SUBJECTS_ROOT_NAME
161:     if root.is_symlink():
162:         raise StorageIOError(
163:             "科目根目录是符号链接，已拒绝访问。", path=SUBJECTS_ROOT_NAME
164:         )
165:     if root.exists() and not root.is_dir():
166:         raise StorageIOError("科目根路径不是目录。", path=SUBJECTS_ROOT_NAME)
167:     json_store.make_directory(root)
168:     # Re-check after creating: the same path must still be a real directory
169:     # inside this user's workspace, not a target that appeared in between.
170:     json_store.confined(workspace, root)
171:     if root.is_symlink():  # pragma: no cover - defensive
172:         raise StorageIOError("科目根目录是符号链接，已拒绝访问。", path=SUBJECTS_ROOT_NAME)
173:     return root
174: 
175: 
176: def _subject_dir_unchecked(subject_id: str) -> Path:
177:     """The subject's directory without requiring a registry entry.
178: 
179:     Only the create/delete flows may use this: creating prepares a tree that is
180:     not registered *yet*, and deleting must still find the tree after the entry
181:     is gone.
182:     """
183:     if not is_valid_subject_id(subject_id):
184:         raise InvalidSubjectIdError(subject_id)
185:     root = subjects_root()
186:     return json_store.confined(root, root / subject_id)
187: 
188: 
189: def subject_dir(subject_id: str) -> Path:
190:     """The data directory for one subject in the current user's registry.
191: 
192:     Raises an explicit error for an id that is not a plain slug, for a path
193:     that resolves outside this user's subject root, and for a well-formed id
194:     that is simply not registered (404) — writing learner data must never bring
195:     a subject tree into existence.
196:     """
197:     path = _subject_dir_unchecked(subject_id)
198:     if not _is_registered(subject_id):
199:         raise SubjectNotFoundError(subject_id)
200:     return path
201: 
202: 
203: def subject_data_path(subject_id: str, name: str) -> Path:
204:     """A confined data file for *subject_id* (validation before any read).
205: 
206:     This is the single entry point the collection modules use for their JSON
207:     files, so a symlinked ``wrong_book.json`` is refused before it is opened
208:     rather than after the other subject's bytes have been read.
209:     """
210:     directory = subject_dir(subject_id)
211:     return json_store.confined(directory, directory / json_store.safe_segment(name))
```

当前 L386–L391：
```text
386: def get_subject(subject_id: str) -> dict | None:
387:     """The registry record for *subject_id*, or ``None`` when unregistered."""
388:     return next((s for s in load_subjects() if s.get("id") == subject_id), None)
389: 
390: 
391: def update_subject(subject_id: str, **fields: str) -> dict | None:
```

当前 L438–L466：
```text
438: def _validate_knowledge_records(records: list[dict], source: Path) -> list[dict]:
439:     """Every record we index by must carry a non-empty string ``kb_name``."""
440:     for index, record in enumerate(records):
441:         kb_name = record.get("kb_name")
442:         if not isinstance(kb_name, str) or not kb_name.strip():
443:             raise json_store.corrupt_error(
444:                 source.name, "知识库记录缺少合法的 kb_name", index=index
445:             )
446:     return records
447: 
448: 
449: def load_knowledge_records(subject_id: str) -> list[dict]:
450:     path = _knowledge_path(subject_id)
451:     return _validate_knowledge_records(json_store.read_list(path), path)
452: 
453: 
454: def _save_knowledge_records(
455:     subject_id: str, records: list[dict], *, require_registered: bool = True
456: ) -> None:
457:     path = _knowledge_path(subject_id, require_registered=require_registered)
458:     json_store.atomic_write_list(path, records)
459: 
460: 
461: def get_knowledge_record(subject_id: str, kb_name: str) -> dict | None:
462:     return next(
463:         (r for r in load_knowledge_records(subject_id) if r["kb_name"] == kb_name), None
464:     )
465: 
466: 
```

当前 L501–L512：
```text
501: def subject_kb_base_dir(subject_id: str) -> Path:
502:     """LlamaIndex base dir for a subject's knowledge bases.
503: 
504:     The directory is confined **before** it is created: a ``knowledge_bases``
505:     symlink pointing outside the subject is refused rather than mkdir'd
506:     through.
507:     """
508:     directory = subject_dir(subject_id)
509:     sub = json_store.confined(directory, directory / "knowledge_bases")
510:     json_store.make_directory(sub)
511:     return sub
512: 
```

## `deeptutor/subjects/uploads.py`

SHA256 `439e0de6c389f819ff8f85d54365b01baee48d15732bdefedb766ad0f7d7aba5`。

当前 L267–L314：
```text
267: def materials_path(subject_id: str, kb_type: str, *, create: bool = False) -> Path:
268:     """``materials/<type>`` without the auto-creating store helper (GET-safe)."""
269:     directory = store.subject_dir(subject_id)
270:     base = json_store.confined(directory, directory / "materials")
271:     sub = json_store.confined(
272:         base, base / json_store.safe_segment(kb_type, what="材料类型")
273:     )
274:     if create:
275:         json_store.make_directory(sub)
276:     return sub
277: 
278: 
279: def kb_base_path(subject_id: str, *, create: bool = False) -> Path:
280:     """The subject's ``knowledge_bases`` root, confined (created only on write).
281: 
282:     A GET must not bring the directory into existence, so the read paths use
283:     ``create=False`` and the store helper that always mkdir's is not used.
284:     """
285:     directory = store.subject_dir(subject_id)
286:     base = json_store.confined(directory, directory / "knowledge_bases")
287:     if create:
288:         json_store.make_directory(base)
289:     return base
290: 
291: 
292: def kb_paths(
293:     subject_id: str, kb_name: str, *, create: bool = False
294: ) -> tuple[Path, Path]:
295:     """``(kb_dir, raw_dir)`` strictly inside the subject's own KB root.
296: 
297:     A KB whose ``kb_config.json`` points at a linked external index is refused
298:     instead of being written through: the subject upload entry must never turn
299:     into a writer for a library outside this subject.
300:     """
301:     base = kb_base_path(subject_id, create=create)
302:     kb_dir = json_store.confined(
303:         base, base / json_store.safe_segment(kb_name, what="知识库名称")
304:     )
305:     if not _same_path(resolve_kb_dir(base, kb_name), kb_dir):
306:         raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
307:     raw_dir = json_store.confined(kb_dir, kb_dir / "raw")
308:     if create:
309:         json_store.make_directory(kb_dir)
310:         json_store.make_directory(raw_dir)
311:     return kb_dir, raw_dir
312: 
313: 
314: @contextmanager
```

当前 L593–L630：
```text
593: def read_kb_status(base_dir: Path | str, kb_name: str) -> dict | None:
594:     """One KB's status straight from ``kb_config.json`` — **no side effects**.
595: 
596:     ``KnowledgeBaseManager`` creates its directory and rewrites a normalized
597:     config on construction, so a read-only projection must not go through it.
598:     Missing file/entry means "no status"; an existing file that is not a JSON
599:     object is corruption rather than a silent default.
600:     """
601:     config_path = Path(base_dir) / KB_CONFIG_NAME
602:     text = json_store._read_text(config_path)
603:     if text is None:
604:         return None
605:     payload = json_store._strict_loads(text, source=config_path)
606:     if not isinstance(payload, dict):
607:         raise json_store.corrupt_error(KB_CONFIG_NAME, "顶层不是对象")
608:     entries = payload.get("knowledge_bases")
609:     if not isinstance(entries, dict):
610:         return None
611:     entry = entries.get(kb_name)
612:     if not isinstance(entry, dict):
613:         return None
614:     coverage, coverage_warning = manifest_mod.public_image_coverage(entry)
615:     return {
616:         "status": entry.get("status", "unknown"),
617:         "progress": entry.get("progress"),
618:         "updated_at": entry.get("updated_at"),
619:         # Validated, read-only projection of the last measured image coverage:
620:         # unmeasured or untrustworthy stored values come back as None instead of
621:         # being echoed, and the warning is derived from the validated counts.
622:         "image_coverage": coverage,
623:         "image_coverage_warning": coverage_warning,
624:     }
625: 
626: 
627: # ---------------------------------------------------------------------------
628: # Same-KB busy state: live worker *and* accepted-but-not-started reservation
629: # ---------------------------------------------------------------------------
630: _RESERVATIONS: dict[str, dict] = {}
```

当前 L700–L727：
```text
700:         if task_id is not None and current.get("task_id") != task_id:
701:             return False
702:         _RESERVATIONS.pop(key, None)
703:         return True
704: 
705: 
706: def reservation_for(kb_dir: Path | str) -> dict | None:
707:     with _RESERVATIONS_LOCK:
708:         current = _RESERVATIONS.get(worker_key(kb_dir))
709:         return dict(current) if current is not None else None
710: 
711: 
712: def busy_state(kb_dir: Path | str) -> dict:
713:     """Everything that must block a same-KB upload, in one read-only view."""
714:     reservation = reservation_for(kb_dir)
715:     worker = _pipeline_state(worker_key(kb_dir))
716:     queued = reservation is not None and not bool(worker.get("alive"))
717:     return {
718:         "key": worker_key(kb_dir),
719:         "reserved": reservation is not None,
720:         "reservation": reservation,
721:         "worker_alive": bool(worker.get("alive")),
722:         "worker_registered": bool(worker.get("registered")),
723:         "queued": queued,
724:         "busy": reservation is not None or bool(worker.get("alive")),
725:         "task_id": (reservation or {}).get("task_id"),
726:     }
727: 
```

## `deeptutor/subjects/material_manifest.py`

SHA256 `d80aaf5e653ff411d292001ef945b919fd5998d15793f5c303700883f422c79b`。

当前 L582–L622：
```text
582: def project_status(
583:     *,
584:     kb_dir: Path,
585:     raw_dir: Path,
586:     materials_dir: Path | None,
587:     subject_id: str,
588:     kb_name: str,
589:     manager_status: dict | None,
590:     worker_alive: bool = False,
591:     queued: bool = False,
592:     task_id: str | None = None,
593:     verify_hashes: bool = False,
594: ) -> dict:
595:     """Read-only projection of one subject KB's count, source and index state.
596: 
597:     Never writes, never schedules, never consults the auto-registering
598:     ``list_knowledge_bases``. The returned dict keeps the historical
599:     ``{status, progress, updated_at}`` shape (plus ``documents``/``task_id``/
600:     counters) and the ``progress`` payload is rebuilt from fixed copy — the
601:     global background tasks store raw diagnostics in ``progress``, and those
602:     must not reach a client.
603:     """
604:     raw_files = source_files(raw_dir, digest=verify_hashes)
605:     documents = len(raw_files)
606:     manifest = load_manifest(kb_dir, subject_id=subject_id, kb_name=kb_name)
607:     index_state = load_index_state(kb_dir, subject_id=subject_id, kb_name=kb_name)
608:     manager_status = manager_status or {}
609: 
610:     if manifest is None:
611:         # Legacy library: no recorded source identity to compare against. The
612:         # first successful upload is what establishes a manifest; a GET never
613:         # writes one.
614:         manifest_diff: dict = {"ok": True, "legacy": True}
615:         expected_fingerprint = fingerprint(raw_files) if verify_hashes else None
616:     else:
617:         manifest_diff = compare_manifest(
618:             manifest["files"], raw_files, verify_hashes=verify_hashes
619:         )
620:         expected_fingerprint = fingerprint(manifest["files"])
621: 
622:     # materials is the authoritative copy. A *missing* directory while the KB
```

当前 L645–L690：
```text
645:     stored = str((index_state or {}).get("status") or "")
646:     state_fingerprint = str((index_state or {}).get("fingerprint") or "")
647:     last_ready = (index_state or {}).get("last_ready") or None
648:     published = index_state if stored == "ready" else last_ready
649:     published_matches = bool(
650:         published and expected_fingerprint and published.get("fingerprint") == expected_fingerprint
651:     )
652: 
653:     pending = bool(queued or worker_alive)
654:     manager_error = manager_value in ("error", "failed")
655:     if not in_sync:
656:         status = "stale"
657:     elif stored == "ready" and published_matches:
658:         # Content identity, not (path, size): a same-size rewrite must not stay
659:         # "ready" for the new bytes.
660:         status = "ready"
661:     elif pending:
662:         # A task is running or accepted: the index cannot be current yet.
663:         status = "rebuilding" if (documents or index_state or stored) else "initializing"
664:     elif stored == "error" or manager_error:
665:         status = "error"
666:     elif published is not None:
667:         # A published index exists but belongs to an older source set.
668:         status = "stale"
669:     elif index_state is None and manifest is None and manager_value in ("ready", "completed"):
670:         # A legacy library whose published index was ready before this stage:
671:         # there is no recorded source change to contradict it.
672:         status = "ready"
673:     elif documents or manager_value in ("ready", "completed", "initializing", "processing"):
674:         status = "rebuilding"
675:     else:
676:         status = "initializing"
677: 
678:     percent = {"ready": 100, "error": 0}.get(status, 0)
679:     stage = _STATUS_STAGES[status]
680: 
681:     coverage, coverage_warning = public_image_coverage(manager_status)
682:     projection: dict[str, Any] = {
683:         "status": status,
684:         "progress": _bounded_progress(status, percent=percent, stage=stage),
685:         "updated_at": manager_status.get("updated_at"),
686:         "documents": documents,
687:         "materials_in_sync": in_sync,
688:         "busy": pending,
689:         "worker_alive": bool(worker_alive),
690:         "queued": bool(queued),
```

## `deeptutor/subjects/json_store.py`

SHA256 `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca`。

当前 L80–L108：
```text
80: #: Name of the per-directory lock file.
81: LOCK_FILE_NAME = ".deeptutor.lock"
82: 
83: _CORRUPT_MESSAGE = "科目数据文件已损坏，请先修复或移除该文件后重试。"
84: _IO_MESSAGE = "科目数据文件读写失败，请稍后重试。"
85: _ESCAPE_MESSAGE = "路径超出允许的科目数据目录，已拒绝访问。"
86: _SYMLINK_MESSAGE = "路径中存在符号链接，已拒绝访问。"
87: _UNSUPPORTED_MESSAGE = "当前平台缺少经过验证的文件锁支持，已拒绝并发写入。"
88: 
89: 
90: class LockUnsupportedError(StorageIOError):
91:     """Platform has no verified locking primitive (C01: never run unlocked)."""
92: 
93: 
94: class InvalidInputError(SubjectOperationError):
95:     """A caller-supplied value is unusable (C02 ``invalid_input``, 400).
96: 
97:     Deliberately distinct from :class:`~deeptutor.subjects.errors.StorageCorruptError`:
98:     a bad argument is the caller's problem and must not be reported as damage
99:     to the learner's data (nor the other way round).
100:     """
101: 
102:     def __init__(self, detail: str = "", *, cause: BaseException | None = None) -> None:
103:         spec = ERROR_SPECS[ErrorCode.INVALID_INPUT]
104:         self.detail = detail
105:         super().__init__(
106:             spec.code,
107:             spec.message,
108:             http_status=spec.http_status,
```

当前 L157–L181：
```text
157: 
158: def make_directory(path: Path, *, parents: bool = True, exist_ok: bool = True) -> None:
159:     """Create an already-confined directory, reporting OS failures as C02 IO."""
160:     try:
161:         Path(path).mkdir(parents=parents, exist_ok=exist_ok)
162:     except OSError as exc:
163:         raise _io(path, exc) from exc
164: 
165: 
166: # ---------------------------------------------------------------------------
167: # Path confinement (no symlink escape)
168: # ---------------------------------------------------------------------------
169: def ensure_trusted_root(root: Path) -> Path:
170:     """The anchor itself must be reachable without a symlink.
171: 
172:     A symlinked root cannot be "resolved and trusted": whatever it points at
173:     today is not the scope the caller asked for, and re-resolving it on every
174:     call would silently adopt a new target.
175:     """
176:     root = Path(root)
177:     if root.is_symlink():
178:         raise StorageIOError(_SYMLINK_MESSAGE, path=root.name)
179:     return root
180: 
181: 
```

## `deeptutor/subjects/errors.py`

SHA256 `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88`。

当前 L39–L66：
```text
39: class ErrorCode(str, Enum):
40:     """C02 表中的全部 code。"""
41: 
42:     INVALID_INPUT = "invalid_input"
43:     INVALID_SUBJECT_ID = "invalid_subject_id"
44:     SUBJECT_NOT_FOUND = "subject_not_found"
45:     ENTRY_NOT_FOUND = "entry_not_found"
46:     KB_NOT_FOUND = "kb_not_found"
47:     SCOPE_FORBIDDEN = "scope_forbidden"
48:     KB_NOT_READY = "kb_not_ready"
49:     KB_BUSY = "kb_busy"
50:     MATERIAL_OUT_OF_SYNC = "material_out_of_sync"
51:     STORAGE_CORRUPT = "storage_corrupt"
52:     STORAGE_IO = "storage_io"
53:     INTERNAL_ERROR = "internal_error"
54:     PROVIDER_UNAVAILABLE = "provider_unavailable"
55:     PROVIDER_TIMEOUT = "provider_timeout"
56:     EMPTY_MODEL_OUTPUT = "empty_model_output"
57:     INVALID_MODEL_OUTPUT = "invalid_model_output"
58:     OUTPUT_TRUNCATED = "output_truncated"
59:     REASONING_BUDGET_EXHAUSTED = "reasoning_budget_exhausted"
60:     SANDBOX_UNAVAILABLE = "sandbox_unavailable"
61:     SANDBOX_POLICY_UNSUPPORTED = "sandbox_policy_unsupported"
62:     CHART_FAILED = "chart_failed"
63:     RENDER_FAILED = "render_failed"
64:     FEATURE_UNAVAILABLE = "feature_unavailable"
65: 
66: 
```

当前 L302–L314：
```text
302: def subject_error(code: ErrorCode | str, *, cause: BaseException | None = None) -> SubjectOperationError:
303:     """用 C02 表中的固定投影构造错误（消息/状态/retryable 都来自表）。"""
304:     resolved = ErrorCode(code) if not isinstance(code, ErrorCode) else code
305:     spec = ERROR_SPECS[resolved]
306:     return SubjectOperationError(
307:         spec.code,
308:         spec.message,
309:         http_status=spec.http_status,
310:         retryable=spec.retryable,
311:         cause=cause,
312:     )
313: 
314: 
```

当前 L381–L415：
```text
381: def to_error_dict(error: SubjectOperationError) -> dict[str, Any]:
382:     """WS metadata / ToolResult metadata 共用的 error 数据。
383: 
384:     不改变任何既有事件协议，只提供同构的 ``{code, message, retryable}``。
385:     """
386:     return {
387:         "code": error.code.value,
388:         "message": error.message,
389:         "retryable": error.retryable,
390:     }
391: 
392: 
393: def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
394:     """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
395:     return {"detail": error.message, "error": to_error_dict(error)}
396: 
397: 
398: def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
399:     """WS terminal error / DONE failed 的 metadata 片段。"""
400:     return to_error_dict(error)
401: 
402: 
403: def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
404:     """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。
405: 
406:     调用者负责用它构造真正的 ToolResult；这里只固定失败语义与 error 数据，
407:     不返回任何 artifact URL。
408:     """
409:     return {"success": False, "metadata": {"error": to_error_dict(error)}}
410: 
411: 
412: __all__ = [
413:     "ERROR_SPECS",
414:     "ErrorCode",
415:     "ErrorSpec",
```

## `deeptutor/subjects/exam_points.py`

SHA256 `1c2f0fcd8412b0cea49ea2d11a8aed27219cedff7fb384dd9200f6b110ba7186`。

当前 L516–L529：
```text
516: def term_summary(subject_id: str, term: str = "", limit: int = 8) -> str:
517:     """Lightweight injection block: confirmed exam points for the term."""
518:     points = [p for p in load(subject_id) if p.get("confirmed")]
519:     if term:
520:         points = [p for p in points if p.get("term", "") == term]
521:     if not points:
522:         return ""
523:     points.sort(key=lambda p: p.get("created_at", 0), reverse=True)
524:     lines = ["【本学期期末考点】"]
525:     for p in points[:limit]:
526:         level = LEVEL_LABELS.get(p.get("level", "inferred"), p.get("level", "inferred"))
527:         kp = f"[{p['kp']}] " if p.get("kp") else ""
528:         lines.append(f"- {kp}{p.get('content', '')[:100]}（{level}）")
529:     return "\n".join(lines)
```

## `deeptutor/api/routers/subjects.py`

SHA256 `9349cd452698f8a52df2aab3d2ed5ec06039c521592f9c9f69409c1cdf7c59db`。

当前 L151–L201：
```text
151: 
152:     The count and status are projected from the **current** index source, not
153:     from a stored ``documents`` counter, and the projection never registers,
154:     creates or schedules anything: a GET must not have side effects.
155:     """
156:     _require_subject(subject_id)
157:     return {"knowledge": _knowledge_view(subject_id)}
158: 
159: 
160: def _confined_kb_dir(subject_id: str, kb_name: str) -> Path:
161:     """A stored record's KB path, refused before it can leave the subject."""
162:     base_dir = uploads.kb_base_path(subject_id)
163:     try:
164:         segment = json_store.safe_segment(kb_name, what="知识库名称")
165:     except json_store.InvalidInputError as exc:
166:         raise json_store.corrupt_error("knowledge.json", "知识库记录中的名称非法") from exc
167:     return json_store.confined(base_dir, base_dir / segment)
168: 
169: 
170: def _kb_projection(subject_id: str, kb_name: str, *, record: dict | None) -> dict:
171:     """The sanitized, read-only status dict for one subject KB."""
172:     from deeptutor.subjects import material_manifest
173: 
174:     # Read-only on purpose: the global KnowledgeBaseManager constructor creates
175:     # its directory and rewrites a normalized config, so a GET must not use it.
176:     manager_status = uploads.read_kb_status(uploads.kb_base_path(subject_id), kb_name)
177:     kb_dir = _confined_kb_dir(subject_id, kb_name)
178:     kb_type = (record or {}).get("type")
179:     materials_dir: Path | None = None
180:     if kb_type is not None:
181:         if not isinstance(kb_type, str) or not kb_type:
182:             raise json_store.corrupt_error("knowledge.json", "知识库记录中的材料类型非法")
183:         try:
184:             materials_dir = uploads.materials_path(subject_id, kb_type)
185:         except json_store.InvalidInputError as exc:
186:             raise json_store.corrupt_error("knowledge.json", "知识库记录中的材料类型非法") from exc
187:     busy = uploads.busy_state(kb_dir)
188:     return material_manifest.project_status(
189:         kb_dir=kb_dir,
190:         raw_dir=kb_dir / "raw",
191:         materials_dir=materials_dir,
192:         subject_id=subject_id,
193:         kb_name=kb_name,
194:         manager_status=manager_status,
195:         worker_alive=busy["worker_alive"],
196:         queued=busy["queued"],
197:         task_id=busy["task_id"],
198:     )
199: 
200: 
201: def _knowledge_view(subject_id: str) -> list[dict]:
```

当前 L406–L415：
```text
406: async def subject_kb_status(subject_id: str, kb_name: str, _: None = Depends(require_auth)):
407:     """Current count/state of one subject KB — read-only, sanitized (P1-19)."""
408:     _require_subject(subject_id)
409:     record = store.get_knowledge_record(subject_id, kb_name)
410:     if uploads.read_kb_status(uploads.kb_base_path(subject_id), kb_name) is None and record is None:
411:         # Deliberate compatibility (P1-56): this historical plain HTTPException
412:         # keeps the framework shape ``{"detail": ...}``. The detail is a fixed
413:         # message rather than the old echo of the caller's kb_name.
414:         raise HTTPException(status_code=404, detail="知识库不存在。")
415:     return {"kb_name": kb_name, **_kb_projection(subject_id, kb_name, record=record)}
```

## `deeptutor/multi_user/knowledge_access.py`

SHA256 `54bc1a02a711ced8718ac596a08d3c8169cd4403578562e61f45ac7d0e7302c2`。

当前 L15–L45：
```text
15: from .grants import load_grant
16: from .models import KnowledgeResource
17: from .paths import get_admin_path_service, get_current_path_service
18: 
19: ADMIN_PREFIX = "admin:kb:"
20: USER_PREFIX = "user:kb:"
21: DEFAULT_KB_ALIASES = {"", "default", "current", "selected", "默认", "默认知识库", "当前知识库"}
22: 
23: 
24: @lru_cache(maxsize=128)
25: def _manager_for(base_dir: str) -> KnowledgeBaseManager:
26:     return KnowledgeBaseManager(base_dir=base_dir)
27: 
28: 
29: def current_kb_base_dir() -> Path:
30:     return get_current_path_service().get_knowledge_bases_root()
31: 
32: 
33: def admin_kb_base_dir() -> Path:
34:     return get_admin_path_service().get_knowledge_bases_root()
35: 
36: 
37: def current_kb_manager() -> KnowledgeBaseManager:
38:     return _manager_for(str(current_kb_base_dir().resolve()))
39: 
40: 
41: def admin_kb_manager() -> KnowledgeBaseManager:
42:     return _manager_for(str(admin_kb_base_dir().resolve()))
43: 
44: 
45: def _strip_resource_prefix(value: str) -> tuple[str | None, str]:
```

当前 L69–L111：
```text
69: def resolve_kb(kb_ref: str, *, require_write: bool = False) -> KnowledgeResource:
70:     user = get_current_user()
71:     requested_source, name = _strip_resource_prefix(kb_ref)
72: 
73:     if user.is_admin:
74:         manager = admin_kb_manager()
75:         resolved = _resolve_default_or_name(manager, name)
76:         return KnowledgeResource(
77:             id=f"admin:kb:{resolved}",
78:             name=resolved,
79:             base_dir=admin_kb_base_dir(),
80:             source="admin",
81:             assigned=False,
82:             read_only=False,
83:         )
84: 
85:     user_manager = current_kb_manager()
86:     assigned_names = _assigned_admin_names()
87: 
88:     if requested_source == "admin":
89:         if name not in assigned_names:
90:             raise HTTPException(status_code=403, detail="Knowledge base is not assigned to you")
91:         if require_write:
92:             raise HTTPException(
93:                 status_code=403, detail="Assigned admin knowledge bases are read-only"
94:             )
95:         return KnowledgeResource(
96:             id=f"admin:kb:{name}",
97:             name=name,
98:             base_dir=admin_kb_base_dir(),
99:             source="admin",
100:             assigned=True,
101:             read_only=True,
102:         )
103: 
104:     if requested_source == "user":
105:         resolved = _resolve_default_or_name(user_manager, name)
106:         return KnowledgeResource(
107:             id=f"user:kb:{resolved}",
108:             name=resolved,
109:             base_dir=current_kb_base_dir(),
110:             source="user",
111:             assigned=False,
```

当前 L223–L251：
```text
223: def resolve_for_rag(kb_ref: str | None) -> KnowledgeResource | None:
224:     if not kb_ref:
225:         return None
226:     resource = resolve_kb(kb_ref, require_write=False)
227:     if resource.assigned:
228:         from .audit import log_usage
229: 
230:         log_usage("knowledge_base", resource.id, "rag_query")
231:     return resource
232: 
233: 
234: def resolve_kb_metadata(kb_ref: str | None) -> dict[str, Any] | None:
235:     """Access-checked KB metadata (``type`` / ``vault_path`` / …) for ``kb_ref``.
236: 
237:     Returns ``None`` when the reference is empty or not accessible to the
238:     current user. A pure read with no usage audit (unlike
239:     :func:`resolve_for_rag`) — safe to call while resolving capability bindings.
240:     """
241:     if not kb_ref:
242:         return None
243:     try:
244:         resource = resolve_kb(str(kb_ref), require_write=False)
245:     except HTTPException:
246:         return None
247:     manager = _manager_for(str(resource.base_dir.resolve()))
248:     return manager.get_metadata(resource.name)
249: 
250: 
251: def resolve_kb_manifest(
```

当前 L251–L281：
```text
251: def resolve_kb_manifest(
252:     kb_ref: str | None,
253:     *,
254:     limit: int = MANIFEST_NOTE_LIMIT,
255:     pattern: str = "",
256: ) -> KbManifest | None:
257:     """Access-checked document inventory for ``kb_ref`` (``None`` if inaccessible).
258: 
259:     The one seam through which the chat manifest and the ``kb_files`` tool read
260:     a KB's document set, so neither can bypass the per-user visibility rules
261:     :func:`resolve_kb` enforces. A pure read with no usage audit, mirroring
262:     :func:`resolve_kb_metadata`; it touches the filesystem, so async callers
263:     should hand it to a worker thread.
264:     """
265:     if not kb_ref:
266:         return None
267:     try:
268:         resource = resolve_kb(str(kb_ref), require_write=False)
269:     except HTTPException:
270:         return None
271:     manager = _manager_for(str(resource.base_dir.resolve()))
272:     entry = manager.get_kb_entry(resource.name)
273:     if entry is None:
274:         return None
275:     return build_manifest(
276:         name=resource.name,
277:         kb_dir=resource.base_dir / resource.name,
278:         entry=entry,
279:         limit=limit,
280:         pattern=pattern,
281:     )
```

## `deeptutor/multi_user/paths.py`

SHA256 `5c0a463c93b8b955458143257c395a86b5814e7186688c771b57edf586b6c153`。

当前 L140–L164：
```text
140: def get_path_service_for_scope(scope: UserScope) -> PathService:
141:     key = scope.cache_key
142:     service = _path_services.get(key)
143:     if service is None:
144:         service = PathService(workspace_root=scope.root)
145:         _path_services[key] = service
146:     return service
147: 
148: 
149: def get_admin_path_service() -> PathService:
150:     return get_path_service_for_scope(admin_scope())
151: 
152: 
153: def get_current_path_service() -> PathService:
154:     from .context import get_current_user_or_none
155: 
156:     user = get_current_user_or_none()
157:     if user is None:
158:         return PathService.get_instance()
159:     if user.scope.kind == "user":
160:         ensure_scope_workspace(user.scope)
161:     return get_path_service_for_scope(user.scope)
162: 
163: 
164: def _resolve_owner() -> tuple[str, PathService]:
```

当前 L255–L262：
```text
255: def user_context(user: CurrentUser) -> Iterator[None]:
256:     from .context import reset_current_user, set_current_user
257: 
258:     token = set_current_user(user)
259:     try:
260:         yield
261:     finally:
262:         reset_current_user(token)
```

## `deeptutor/knowledge/manifest.py`

SHA256 `cd9e7a5f2c1ee85656ec9db942eb50dd861bdcca5eb514536232816362d91356`。

当前 L69–L106：
```text
69: @dataclass(frozen=True)
70: class KbDocument:
71:     """One document in a knowledge base."""
72: 
73:     name: str
74:     """POSIX path relative to the KB's document root (folders included)."""
75: 
76:     size: int
77:     """Size in bytes, or ``0`` when the file could not be stat'ed."""
78: 
79: 
80: @dataclass(frozen=True)
81: class KbManifest:
82:     """What one knowledge base actually contains, as facts rather than passages."""
83: 
84:     name: str
85:     provider: str = ""
86:     status: str = ""
87:     kb_type: str = ""
88:     total: int = 0
89:     """Documents in the KB — always the full count, ignoring ``pattern``."""
90: 
91:     matched: int = 0
92:     """Documents matching ``pattern`` (equal to ``total`` when unfiltered)."""
93: 
94:     documents: tuple[KbDocument, ...] = ()
95:     """The matching documents, truncated to the caller's limit."""
96: 
97:     pattern: str = ""
98:     unavailable: str = ""
99:     """Reason code from this module's ``UNAVAILABLE_*`` set; ``""`` when listable."""
100: 
101:     @property
102:     def enumerable(self) -> bool:
103:         return not self.unavailable
104: 
105:     @property
106:     def omitted(self) -> int:
```

当前 L157–L181：
```text
157: def build_manifest(
158:     *,
159:     name: str,
160:     kb_dir: Path,
161:     entry: Mapping[str, Any] | None = None,
162:     limit: int = MANIFEST_NOTE_LIMIT,
163:     pattern: str = "",
164: ) -> KbManifest:
165:     """Read ``name``'s document inventory off disk.
166: 
167:     ``entry`` is the KB's ``kb_config.json`` record (provider / status / type);
168:     it is read but never trusted for counts, which come from the filesystem.
169:     ``pattern`` filters by name — a glob when it contains wildcards, otherwise a
170:     case-insensitive substring. Only the retained documents are stat'ed, so a
171:     large KB costs one directory walk rather than thousands of syscalls.
172:     """
173:     record: Mapping[str, Any] = entry or {}
174:     kb_type = str(record.get("type") or "").strip()
175:     manifest_fields: dict[str, Any] = {
176:         "name": name,
177:         "provider": str(record.get("rag_provider") or "").strip(),
178:         "status": str(record.get("status") or "").strip(),
179:         "kb_type": kb_type,
180:         "pattern": pattern.strip(),
181:     }
```

## `deeptutor/services/rag/provider_binding.py`

SHA256 `dbcb607dfe01a2924eabc57cffd71cdb22257ca6c3b7270c9f4f6b1c22869a12`。

当前 L1–L70：
```text
1: """Resolve a knowledge base's bound RAG provider.
2: 
3: DeepTutor owns the knowledge-base lifecycle and stores the authoritative
4: provider binding in ``kb_config.json``. Older KBs may only have
5: ``metadata.json``, so metadata remains a legacy fallback. Retrieval and
6: incremental indexing should use this helper instead of hand-reading either file
7: directly.
8: """
9: 
10: from __future__ import annotations
11: 
12: import json
13: from pathlib import Path
14: from typing import Any
15: 
16: from deeptutor.services.rag.factory import DEFAULT_PROVIDER, normalize_provider_name
17: 
18: 
19: def load_kb_config_entry(kb_base_dir: str | Path, kb_name: str) -> dict[str, Any]:
20:     """Return the raw ``kb_config.json`` entry for ``kb_name``, if present."""
21:     config_path = Path(kb_base_dir) / "kb_config.json"
22:     if not config_path.exists():
23:         return {}
24:     try:
25:         with open(config_path, encoding="utf-8") as handle:
26:             entry = json.load(handle).get("knowledge_bases", {}).get(kb_name, {})
27:         return entry if isinstance(entry, dict) else {}
28:     except Exception:
29:         return {}
30: 
31: 
32: def load_metadata_provider(kb_base_dir: str | Path, kb_name: str) -> str | None:
33:     """Return the provider stored in legacy ``metadata.json``, if present."""
34:     metadata_path = Path(kb_base_dir) / kb_name / "metadata.json"
35:     if not metadata_path.exists():
36:         return None
37:     try:
38:         with open(metadata_path, encoding="utf-8") as handle:
39:             provider = json.load(handle).get("rag_provider")
40:     except Exception:
41:         return None
42:     return normalize_provider_name(provider) if provider else None
43: 
44: 
45: def resolve_bound_provider(kb_base_dir: str | Path, kb_name: str | None) -> str:
46:     """Resolve the provider DeepTutor has bound to a KB.
47: 
48:     Order:
49:     1. ``kb_config.json``: authoritative runtime state.
50:     2. ``metadata.json``: legacy/import fallback.
51:     3. default provider.
52:     """
53:     if kb_name:
54:         entry = load_kb_config_entry(kb_base_dir, kb_name)
55:         provider = entry.get("rag_provider")
56:         if provider:
57:             return normalize_provider_name(provider)
58: 
59:         metadata_provider = load_metadata_provider(kb_base_dir, kb_name)
60:         if metadata_provider:
61:             return metadata_provider
62: 
63:     return DEFAULT_PROVIDER
64: 
65: 
66: __all__ = [
67:     "load_kb_config_entry",
68:     "load_metadata_provider",
69:     "resolve_bound_provider",
70: ]
```

## `deeptutor/runtime/request_contracts.py`

SHA256 `ea011e49f57b6b1fb157cbb2821d6bf04c605f5d755a6a7580142a5eff37986a`。

当前 L18–L36：
```text
18: _RUNTIME_ONLY_KEYS = {
19:     "_persist_user_message",
20:     "followup_question_context",
21:     # Per-turn subagent consult budget (composer stepper). Not part of any
22:     # capability's public config schema; stripped here so it never trips
23:     # ``extra="forbid"`` (turn_runtime carries it through to the turn config).
24:     "subagent_consult_budget",
25:     # Subject scope (composer SubjectSelector). The composer builds the whole
26:     # turn config, so the selected subject rides in ``config`` — but it is not
27:     # a capability parameter, and ``ChatRequestConfig`` declares no fields with
28:     # ``extra="forbid"``, so an unlisted key rejects the entire turn. Stripped
29:     # here and read back out of the turn config by ``turn_runtime``, which
30:     # drives the M5 subject context injection.
31:     "subject_id",
32: }
33: 
34: 
35: class ChatRequestConfig(BaseModel):
36:     model_config = ConfigDict(extra="forbid")
```

当前 L80–L103：
```text
80: 
81: def _clean_public_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
82:     if raw_config is None:
83:         return {}
84:     if not isinstance(raw_config, dict):
85:         raise ValueError("Capability config must be an object.")
86:     cleaned = dict(raw_config)
87:     for key in _RUNTIME_ONLY_KEYS:
88:         cleaned.pop(key, None)
89:     return cleaned
90: 
91: 
92: def _validate_model(
93:     model_type: type[BaseModel],
94:     raw_config: dict[str, Any] | None,
95:     *,
96:     label: str,
97: ) -> BaseModel:
98:     cleaned = _clean_public_config(raw_config)
99:     try:
100:         return model_type.model_validate(cleaned)
101:     except ValidationError as exc:
102:         details = "; ".join(
103:             f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
```

## `deeptutor/services/session/turn_runtime.py`

SHA256 `0cd192cce5a9cfff715a2090b7c6bffde80d7e2f91e94d860733250efd8be0e2`。

当前 L211–L255：
```text
211: def _request_snapshot_metadata(
212:     *,
213:     payload: dict[str, Any],
214:     content: str,
215:     capability: str,
216:     config: dict[str, Any],
217:     attachments: list[dict[str, Any]],
218:     notebook_references: list[Any],
219:     history_references: list[Any],
220:     question_notebook_references: list[Any],
221:     book_references: list[Any],
222:     persona: str,
223:     memory_references: Sequence[str],
224:     llm_selection: dict[str, str] | None,
225: ) -> dict[str, Any]:
226:     """Persist the front-end context chips with the user message."""
227:     snapshot: dict[str, Any] = {
228:         "content": content,
229:         "capability": capability,
230:         "enabledTools": _string_list(payload.get("tools")),
231:         "knowledgeBases": _string_list(payload.get("knowledge_bases")),
232:         "language": str(payload.get("language", "en") or "en"),
233:     }
234:     if attachments:
235:         snapshot["attachments"] = attachments
236:     if config:
237:         snapshot["config"] = dict(config)
238:     if notebook_references:
239:         snapshot["notebookReferences"] = notebook_references
240:     if history_references:
241:         snapshot["historyReferences"] = history_references
242:     if question_notebook_references:
243:         snapshot["questionNotebookReferences"] = question_notebook_references
244:     if book_references:
245:         snapshot["bookReferences"] = book_references
246:     mastery_path_id = _mastery_path_id(payload.get("mastery_path_id"))
247:     if mastery_path_id:
248:         snapshot["masteryPathId"] = mastery_path_id
249:     if persona:
250:         snapshot["persona"] = persona
251:     if memory_references:
252:         snapshot["memoryReferences"] = memory_references
253:     if llm_selection:
254:         snapshot["llmSelection"] = llm_selection
255:     return {"request_snapshot": snapshot}
```

当前 L760–L804：
```text
760:     async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
761:         capability = str(payload.get("capability") or "chat")
762:         if not payload.get("language"):
763:             from deeptutor.services.settings.interface_settings import (
764:                 get_response_language,
765:             )
766: 
767:             payload = {**payload, "language": get_response_language(default="en")}
768:         raw_config = dict(payload.get("config", {}) or {})
769:         runtime_only_keys = (
770:             "_persist_user_message",
771:             "_regenerate",
772:             "_regenerated_from_message_id",
773:             "_superseded_turn_id",
774:             "followup_question_context",
775:             # Per-turn subagent consult budget (composer stepper). Not part of
776:             # any capability's public config schema, so it rides as a runtime
777:             # key — stripped before validation, merged back into the turn config
778:             # and read by the subagent capability from context.config_overrides.
779:             "subagent_consult_budget",
780:             # Subject scope (composer SubjectSelector). Same contract as the
781:             # budget above: stripped before capability-config validation so it
782:             # cannot trip ``extra="forbid"``, then merged back into the turn
783:             # config where _run_turn reads it for the M5 context injection.
784:             "subject_id",
785:         )
786:         runtime_only_config = {
787:             key: raw_config.pop(key) for key in runtime_only_keys if key in raw_config
788:         }
789:         try:
790:             from deeptutor.runtime.request_contracts import validate_capability_config
791: 
792:             validated_public_config = validate_capability_config(capability, raw_config)
793:         except ValueError as exc:
794:             raise RuntimeError(str(exc)) from exc
795:         payload = {
796:             **payload,
797:             "capability": capability,
798:             "config": {**validated_public_config, **runtime_only_config},
799:         }
800:         session = await self.store.ensure_session(payload.get("session_id"))
801:         preferences = session.get("preferences") or {}
802:         # A mastery path has a longer lifetime than any one conversation.
803:         # Persist the explicit association on the session, and restore it on
804:         # later turns whose frontend payload omits the field.
```

当前 L927–L946：
```text
927:             "knowledge_bases": list(payload.get("knowledge_bases") or []),
928:             "language": str(payload.get("language") or "en"),
929:         }
930:         if llm_selection:
931:             preference_update["llm_selection"] = llm_selection
932:         if persona_explicit:
933:             # Persist explicit set AND explicit clear ("" = back to Default).
934:             preference_update["persona"] = persona_pref
935:         if mastery_path_explicit or mastery_binding is not None:
936:             # Mastery turns persist their fully resolved path so a later turn
937:             # cannot silently fall back to a different aggregate.
938:             preference_update["mastery_path_id"] = mastery_path_id
939:         await self.store.update_session_preferences(session["id"], preference_update)
940:         turn = await self.store.create_turn(session["id"], capability=capability)
941:         execution = _TurnExecution(
942:             turn_id=turn["id"],
943:             session_id=session["id"],
944:             capability=capability,
945:             payload=dict(payload),
946:         )
```

当前 L1050–L1108：
```text
1050:         if last_user is None:
1051:             raise RuntimeError("nothing_to_regenerate")
1052: 
1053:         last_message = await self.store.get_last_message(session_id)
1054:         previous_turn_id: str | None = None
1055:         if last_message is not None and last_message.get("role") == "assistant":
1056:             for event in last_message.get("events") or []:
1057:                 turn_id = str((event or {}).get("turn_id") or "")
1058:                 if turn_id:
1059:                     previous_turn_id = turn_id
1060:                     break
1061:             await self.store.delete_message(last_message["id"])
1062: 
1063:         preferences = session.get("preferences") or {}
1064:         overrides = overrides or {}
1065:         snapshot = {}
1066:         metadata = last_user.get("metadata") or {}
1067:         if isinstance(metadata, dict):
1068:             candidate = metadata.get("request_snapshot") or metadata.get("requestSnapshot")
1069:             if isinstance(candidate, dict):
1070:                 snapshot = candidate
1071: 
1072:         capability = str(
1073:             overrides.get("capability")
1074:             or last_user.get("capability")
1075:             or preferences.get("capability")
1076:             or "chat"
1077:         )
1078:         tools = list(
1079:             overrides.get("tools")
1080:             if overrides.get("tools") is not None
1081:             else preferences.get("tools") or []
1082:         )
1083:         knowledge_bases = list(
1084:             overrides.get("knowledge_bases")
1085:             if overrides.get("knowledge_bases") is not None
1086:             else preferences.get("knowledge_bases") or []
1087:         )
1088:         language = str(overrides.get("language") or preferences.get("language") or "en")
1089: 
1090:         config: dict[str, Any] = dict(overrides.get("config") or {})
1091:         config.update(
1092:             {
1093:                 "_persist_user_message": False,
1094:                 "_regenerate": True,
1095:                 "_regenerated_from_message_id": int(last_user["id"]),
1096:             }
1097:         )
1098:         if previous_turn_id:
1099:             config["_superseded_turn_id"] = previous_turn_id
1100:         llm_selection = (
1101:             overrides.get("llm_selection")
1102:             if overrides.get("llm_selection") is not None
1103:             else snapshot.get("llmSelection") or preferences.get("llm_selection")
1104:         )
1105:         mastery_path_id = _mastery_path_id(
1106:             overrides.get("mastery_path_id")
1107:             if "mastery_path_id" in overrides
1108:             else snapshot.get("masteryPathId") or preferences.get("mastery_path_id")
```

当前 L1114–L1140：
```text
1114:             "content": str(last_user.get("content", "") or ""),
1115:             "tools": tools,
1116:             "knowledge_bases": knowledge_bases,
1117:             "language": language,
1118:             "attachments": list(last_user.get("attachments") or []),
1119:             "notebook_references": list(
1120:                 overrides.get("notebook_references")
1121:                 if overrides.get("notebook_references") is not None
1122:                 else preferences.get("notebook_references") or []
1123:             ),
1124:             "history_references": list(
1125:                 overrides.get("history_references")
1126:                 if overrides.get("history_references") is not None
1127:                 else preferences.get("history_references") or []
1128:             ),
1129:             "book_references": list(
1130:                 overrides.get("book_references")
1131:                 if overrides.get("book_references") is not None
1132:                 else snapshot.get("bookReferences") or []
1133:             ),
1134:             "mastery_path_id": mastery_path_id,
1135:             "config": config,
1136:         }
1137:         if llm_selection:
1138:             payload["llm_selection"] = llm_selection
1139:         return await self.start_turn(payload)
1140: 
```

当前 L1434–L1448：
```text
1434:                 branch_parent_id = None
1435:             # The subject scope arrives either as a top-level payload field (SDK
1436:             # / direct API callers) or inside ``config`` (the composer's
1437:             # SubjectSelector builds the whole config object). Accept both so a
1438:             # subject selected in the UI is not silently dropped.
1439:             subject_id = str(
1440:                 payload.get("subject_id")
1441:                 or (payload.get("config") or {}).get("subject_id")
1442:                 or ""
1443:             ).strip()
1444:             notebook_references = payload.get("notebook_references", []) or []
1445:             history_references = payload.get("history_references", []) or []
1446:             question_notebook_references = payload.get("question_notebook_references", []) or []
1447:             book_references = payload.get("book_references", []) or []
1448:             memory_references = _extract_memory_references(payload)
```

当前 L1796–L1827：
```text
1796:             # M5: subject-scoped turns inject the lightweight context layer
1797:             # (knowledge index + exam points + wrong book + profile).
1798:             subject_context_tokens = 0
1799:             if subject_id:
1800:                 try:
1801:                     from deeptutor.services.pdf.review_guide import estimate_tokens
1802:                     from deeptutor.subjects import (
1803:                         exam_points,
1804:                         knowledge_points,
1805:                         profile as subject_profile,
1806:                         wrong_book,
1807:                     )
1808: 
1809:                     _blocks = [
1810:                         knowledge_points.context_summary(subject_id),
1811:                         exam_points.term_summary(subject_id),
1812:                         wrong_book.context_summary(subject_id),
1813:                         subject_profile.context_summary(subject_id),
1814:                     ]
1815:                     _block = "\n\n".join(b for b in _blocks if b)
1816:                     if _block:
1817:                         subject_context_tokens = estimate_tokens(_block)
1818:                         logger.warning(
1819:                             "subject context injected: %d chars, ~%d tokens",
1820:                             len(_block),
1821:                             subject_context_tokens,
1822:                         )
1823:                         conversation_history.insert(
1824:                             0, {"role": "system", "content": _block}
1825:                         )
1826:                 except Exception:
1827:                     logger.warning("subject context injection failed", exc_info=True)
```

当前 L1877–L1901：
```text
1877:                 metadata={
1878:                     "conversation_summary": history_result.conversation_summary,
1879:                     "conversation_context_text": conversation_context_text,
1880:                     "history_token_count": history_result.token_count,
1881:                     "history_budget": history_result.budget,
1882:                     "turn_id": turn_id,
1883:                     "question_followup_context": followup_question_context or {},
1884:                     "notebook_references": notebook_references,
1885:                     "history_references": history_references,
1886:                     "question_notebook_references": question_notebook_references,
1887:                     "book_references": book_references,
1888:                     "mastery_path_id": _mastery_path_id(payload.get("mastery_path_id")),
1889:                     "mastery_path_lease_managed": capability_name == "mastery_path",
1890:                     "book_context": book_context,
1891:                     "book_context_warnings": [],
1892:                     "subject_id": subject_id,
1893:                     "subject_context_tokens": subject_context_tokens,
1894:                     "memory_references": memory_references,
1895:                     "question_bank_context": question_bank_context,
1896:                     "memory_context": memory_context,
1897:                     "active_persona": active_persona,
1898:                     "llm_selection": payload.get("llm_selection") or {},
1899:                     "llm_model": str(getattr(llm_config, "model", "") or ""),
1900:                     "llm_provider": str(getattr(llm_config, "provider_name", "") or ""),
1901:                     # Per-turn full-text payload for read_source. Empty when
```

当前 L2097–L2126：
```text
2097:         except Exception as exc:
2098:             if stream_done_sent:
2099:                 logger.error(
2100:                     "Post-stream persistence for turn %s failed: %s",
2101:                     turn_id,
2102:                     exc,
2103:                     exc_info=True,
2104:                 )
2105:                 # Suppress each step separately: a flush failure must not
2106:                 # also skip the status update, or the turn stays "running"
2107:                 # forever and gets mislabelled as a server-restart orphan.
2108:                 with contextlib.suppress(Exception):
2109:                     await self._flush_buffered_events(execution)
2110:                 with contextlib.suppress(Exception):
2111:                     await self.store.update_turn_status(turn_id, "failed", str(exc))
2112:             else:
2113:                 logger.error("Turn %s failed: %s", turn_id, exc, exc_info=True)
2114:                 await self._publish_live_event(
2115:                     execution,
2116:                     StreamEvent(
2117:                         type=StreamEventType.ERROR,
2118:                         source=capability_name,
2119:                         content=str(exc),
2120:                         metadata={"turn_terminal": True, "status": "failed"},
2121:                     ),
2122:                 )
2123:                 await self._publish_live_event(
2124:                     execution,
2125:                     StreamEvent(
2126:                         type=StreamEventType.DONE,
```

## `deeptutor/api/routers/unified_ws.py`

SHA256 `f578da264d79b9d6df14f5dade1169f40fc17d24a57731148c2e1d3a491e4296`。

当前 L115–L139：
```text
115:                 from deeptutor.services.session import get_turn_runtime_manager
116: 
117:                 runtime = get_turn_runtime_manager()
118:                 try:
119:                     _, turn = await runtime.start_turn(msg)
120:                 except RuntimeError as exc:
121:                     await safe_send(
122:                         {
123:                             "type": "error",
124:                             "source": "unified_ws",
125:                             "stage": "",
126:                             "content": str(exc),
127:                             "metadata": {"turn_terminal": True, "status": "rejected"},
128:                             "session_id": str(msg.get("session_id") or ""),
129:                             "turn_id": "",
130:                             "seq": 0,
131:                         }
132:                     )
133:                     continue
134:                 await subscribe_turn(turn["id"], after_seq=0)
135:                 continue
136: 
137:             if msg_type == "ping":
138:                 # Client-side heartbeat. Respond with a lightweight pong so
139:                 # the client knows the socket is alive; the client never
```

当前 L263–L302：
```text
263:                 session_id = str(msg.get("session_id") or "").strip()
264:                 if not session_id:
265:                     await safe_send({"type": "error", "content": "Missing session_id."})
266:                     continue
267:                 from deeptutor.services.session import get_turn_runtime_manager
268: 
269:                 runtime = get_turn_runtime_manager()
270:                 overrides = msg.get("overrides") if isinstance(msg.get("overrides"), dict) else None
271:                 try:
272:                     _, turn = await runtime.regenerate_last_turn(
273:                         session_id,
274:                         overrides=overrides,
275:                     )
276:                 except RuntimeError as exc:
277:                     await safe_send(
278:                         {
279:                             "type": "error",
280:                             "source": "unified_ws",
281:                             "stage": "",
282:                             "content": str(exc),
283:                             "metadata": {
284:                                 "turn_terminal": True,
285:                                 "status": "rejected",
286:                                 "reason": str(exc),
287:                             },
288:                             "session_id": session_id,
289:                             "turn_id": "",
290:                             "seq": 0,
291:                         }
292:                     )
293:                     continue
294:                 await subscribe_turn(turn["id"], after_seq=0)
295:                 continue
296: 
297:             if msg_type == "user_input":
298:                 turn_id = str(msg.get("turn_id") or "").strip()
299:                 if not turn_id:
300:                     await safe_send({"type": "error", "content": "Missing turn_id for user_input."})
301:                     continue
302:                 from deeptutor.core.stream_bus import get_bus
```

## `deeptutor/agents/chat/agentic_pipeline.py`

SHA256 `7229d55ab86c54c916fc8d3be22c130666c58132dc10b46f54b55edd367cdc5d`。

当前 L552–L570：
```text
552:     def _pageindex_doc_maps(self, context: UnifiedContext) -> dict[str, dict[str, str]]:
553:         """kb_name -> {file: doc_id} for bound KBs on the pageindex provider."""
554:         out: dict[str, dict[str, str]] = {}
555:         for kb in self._selected_kbs(context):
556:             try:
557:                 from deeptutor.multi_user.knowledge_access import resolve_kb
558:                 from deeptutor.services.rag.factory import PAGEINDEX_PROVIDER
559:                 from deeptutor.services.rag.pipelines.pageindex.pipeline import PageIndexPipeline
560:                 from deeptutor.services.rag.provider_binding import resolve_bound_provider
561: 
562:                 resource = resolve_kb(kb, require_write=False)
563:                 base_dir = str(resource.base_dir)
564:                 if resolve_bound_provider(base_dir, resource.name) != PAGEINDEX_PROVIDER:
565:                     continue
566:                 out[kb] = PageIndexPipeline(kb_base_dir=base_dir).document_map(resource.name)
567:             except Exception:
568:                 logger.debug("pageindex doc-map resolution failed for %r", kb, exc_info=True)
569:         return out
570: 
```

当前 L610–L623：
```text
610:         composed = compose_enabled_tools(
611:             registry=self.tool_lookup,
612:             requested_tools=context.enabled_tools,
613:             optional_whitelist=CHAT_OPTIONAL_TOOLS,
614:             mount_flags=ToolMountFlags(
615:                 # PageIndex KBs are read via the preloaded MCP tools, not rag —
616:                 # a conversation with only PageIndex KBs doesn't mount rag at all.
617:                 # Excludes KBs owned by an exclusive capability (an Obsidian vault
618:                 # is read via its own tools, never rag) so a pure-vault turn still
619:                 # doesn't mount rag, while co-selected LlamaIndex KBs do (#650).
620:                 has_kb=bool(self._coexisting_rag_kbs(context)),
621:                 # read_source is owned by the explore_context pre-pass (it runs
622:                 # the investigation over attached sources), not the answer loop.
623:                 # Keep it off the answer surface even when sources are present.
```

当前 L725–L749：
```text
725:     ) -> list[dict[str, Any]]:
726:         schemas = self.tool_lookup.build_openai_schemas(enabled_tools)
727:         kb_choices = self._coexisting_rag_kbs(context)
728:         notebook_choices = self._notebook_choices()
729:         for schema in schemas:
730:             function = schema.get("function") if isinstance(schema, dict) else None
731:             if not isinstance(function, dict):
732:                 continue
733:             parameters = function.get("parameters")
734:             if not isinstance(parameters, dict):
735:                 continue
736:             properties = parameters.get("properties") or {}
737:             if function.get("name") == "rag" and isinstance(properties, dict):
738:                 if isinstance(properties.get("query"), dict):
739:                     properties["query"].setdefault("minLength", 1)
740:                 if isinstance(properties.get("kb_name"), dict):
741:                     properties["kb_name"]["enum"] = kb_choices
742:             if function.get("name") == "geogebra_analysis" and isinstance(properties, dict):
743:                 properties.pop("image_base64", None)
744:                 required = parameters.get("required")
745:                 if isinstance(required, list):
746:                     parameters["required"] = [n for n in required if n != "image_base64"]
747:             if (
748:                 function.get("name") in {"list_notebook", "write_note"}
749:                 and isinstance(properties, dict)
```

当前 L985–L1008：
```text
985:         kwargs = dict(args)
986:         workspace_key = self._workspace_key(context)
987:         task_dir = (
988:             get_path_service().get_task_workspace("chat", workspace_key) if workspace_key else None
989:         )
990:         exec_dir = task_dir / "exec" if task_dir is not None else None
991:         if tool_name == "rag":
992:             kwargs.setdefault("mode", "hybrid")
993:         elif tool_name == "kb_files":
994:             # The report is read by the user as much as by the model, so it is
995:             # written in the turn's language. Injected server-side; the tool
996:             # exposes no ``language`` parameter for the model to get wrong.
997:             kwargs["language"] = context.language or "en"
998:         elif tool_name == "load_tools":
999:             kwargs["_tool_loader"] = self._deferred_loader
1000:         elif tool_name == "generate_report":
1001:             subject_id = str(context.metadata.get("subject_id", "") or "").strip()
1002:             # Both the scope and the learner summary are server-owned: an empty
1003:             # subject means no scope at all, so neither is set. Building the
1004:             # hint unconditionally used to emit "当前科目：（错题 0 道、考点 0
1005:             # 条）" and burn two JSON reads for a turn with no subject.
1006:             if subject_id:
1007:                 kwargs["_subject_id"] = subject_id
1008:                 kwargs["_report_ctx_hint"] = (
```

当前 L1413–L1425：
```text
1413:             logger.debug("owner id resolution failed", exc_info=True)
1414:             return ""
1415: 
1416:     @staticmethod
1417:     def _selected_kbs(context: UnifiedContext) -> list[str]:
1418:         return [str(kb).strip() for kb in context.knowledge_bases if str(kb).strip()]
1419: 
1420:     def _rag_kbs(self, context: UnifiedContext) -> list[str]:
1421:         """Attached KBs served by the rag tool (PageIndex KBs are read via MCP)."""
1422:         pageindex = getattr(self, "_pageindex_docs", None) or {}
1423:         return [kb for kb in self._selected_kbs(context) if kb not in pageindex]
1424: 
1425:     def _capability_owned_kbs(self, context: UnifiedContext) -> set[str]:
```

当前 L1440–L1451：
```text
1440:         """rag-served KBs that coexist with an exclusive knowledge capability.
1441: 
1442:         When an Obsidian vault owns the turn, co-selected LlamaIndex KBs would
1443:         otherwise be silently dropped (issue #650). These stay reachable via
1444:         rag; vault KBs (which have no rag index) are excluded. Equals
1445:         ``_rag_kbs`` for a plain chat turn (no capability owns any KB).
1446:         """
1447:         owned = self._capability_owned_kbs(context)
1448:         return [kb for kb in self._rag_kbs(context) if kb not in owned]
1449: 
1450:     @staticmethod
1451:     def _workspace_key(context: UnifiedContext) -> str:
```

当前 L1496–L1523：
```text
1496:         self._kb_manifests = []
1497:         kbs = self._rag_kbs(context)
1498:         if not kbs:
1499:             return
1500:         try:
1501:             self._kb_manifests = await asyncio.to_thread(self._collect_kb_manifests, kbs)
1502:         except Exception as exc:  # pragma: no cover - defensive
1503:             logger.warning("Failed to build knowledge base manifests: %s", exc)
1504: 
1505:     @staticmethod
1506:     def _collect_kb_manifests(kbs: list[str]) -> list[KbManifest]:
1507:         from deeptutor.multi_user.knowledge_access import resolve_kb_manifest
1508: 
1509:         manifests: list[KbManifest] = []
1510:         for kb in kbs:
1511:             try:
1512:                 manifest = resolve_kb_manifest(kb)
1513:             except Exception as exc:
1514:                 logger.warning("Failed to read documents of knowledge base '%s': %s", kb, exc)
1515:                 continue
1516:             if manifest is not None:
1517:                 manifests.append(manifest)
1518:         return manifests
1519: 
1520:     def _kb_manifest_system_note(self) -> str:
1521:         """What the attached KBs contain, from :meth:`_prepare_kb_manifests`."""
1522:         if not self._kb_manifests:
1523:             return ""
```

当前 L1540–L1580：
```text
1540:             )
1541:             lines.append(f"- {kb}: {listed or '(no indexed documents)'}")
1542:         docs_block = "\n".join(lines)
1543:         if self.language == "zh":
1544:             return (
1545:                 "\n以下知识库使用托管的 PageIndex 引擎，其文档通过已加载的 "
1546:                 "PageIndex MCP 工具阅读：先用 mcp_pageindex_get_document_structure "
1547:                 "查看结构，再用 mcp_pageindex_get_page_content 读取相关页面。文档清单：\n"
1548:                 f"{docs_block}"
1549:             )
1550:         return (
1551:             "\nThe following knowledge bases are on the hosted PageIndex engine; read "
1552:             "their documents with the preloaded PageIndex MCP tools: "
1553:             "mcp_pageindex_get_document_structure for the outline, then "
1554:             "mcp_pageindex_get_page_content for the relevant pages. Documents:\n"
1555:             f"{docs_block}"
1556:         )
1557: 
1558:     def _workspace_system_note(self, context: UnifiedContext) -> str:
1559:         if not getattr(self, "_exec_enabled", False):
1560:             return ""
1561:         try:
1562:             from deeptutor.services.path_service import get_path_service
1563: 
1564:             exec_dir = (
1565:                 get_path_service().get_task_workspace(
1566:                     "chat",
1567:                     self._workspace_key(context),
1568:                 )
1569:                 / "exec"
1570:             )
1571:         except Exception:
1572:             return ""
1573:         if self.language == "zh":
1574:             return (
1575:                 "[本轮工作区]\n"
1576:                 f"脚本和临时文件应写入：{exec_dir}\n"
1577:                 "相对路径会解析到这个目录。需要创建 PDF、图片、表格或其他下载文件时，"
1578:                 "直接通过 exec 写入并运行脚本（如 heredoc：python - <<'PY' … PY，"
1579:                 "或 cat > gen.py <<'EOF' … EOF 后再运行）。生成的文件会自动以可下载"
1580:                 "卡片呈现给用户——在回答里描述你做了什么即可，不要粘贴原始 URL。"
```

## `deeptutor/tools/rag_tool.py`

SHA256 `4188fd3e2d8969b33d512244ca2ab574427c12f94140a912f42161f91a3fcd96`。

当前 L15–L52：
```text
15: async def rag_search(
16:     query: str,
17:     kb_name: str,
18:     provider: Optional[str] = None,
19:     kb_base_dir: Optional[str] = None,
20:     event_sink=None,
21:     **kwargs,
22: ) -> dict:
23:     """Retrieve passages from ``kb_name`` and synthesise an answer.
24: 
25:     ``kb_name`` must match a knowledge base the current user can access;
26:     multi-user routing is delegated to :func:`resolve_for_rag` when no
27:     explicit ``kb_base_dir`` is given.
28:     """
29:     query = query.strip() if isinstance(query, str) else ""
30:     kb_name = kb_name.strip() if isinstance(kb_name, str) else ""
31:     if not query:
32:         raise ValueError("RAG query must be a non-empty string.")
33:     if not kb_name:
34:         raise ValueError("RAG requires an explicit kb_name.")
35: 
36:     if kb_base_dir is None:
37:         from deeptutor.multi_user.knowledge_access import resolve_for_rag
38: 
39:         resource = resolve_for_rag(kb_name)
40:         if resource is None:
41:             raise ValueError(f"Knowledge base '{kb_name}' is not accessible.")
42:         kb_base_dir = str(resource.base_dir)
43:         kb_name = resource.name
44: 
45:     service = RAGService(kb_base_dir=kb_base_dir, provider=provider)
46:     return await service.search(
47:         query=query,
48:         kb_name=kb_name,
49:         event_sink=event_sink,
50:         **kwargs,
51:     )
52: 
```

## `deeptutor/tools/builtin/__init__.py`

SHA256 `3019f2295ec44275dfdea478626d513200c138bc9f78398dffd9fef6b03adc5c`。

当前 L71–L85：
```text
71: def _rag_sources(result: dict[str, Any], *, query: str, kb_name: str) -> list[dict[str, Any]]:
72:     """Citations for one ``rag`` call, from the retrieval's own provenance.
73: 
74:     Every pipeline normalises what it retrieved into ``result["sources"]``
75:     (``{title, content, source, page, chunk_id, score}`` — see the GraphRAG and
76:     LightRAG-server pipelines). Forward those so a grounded claim is traceable
77:     to the chunk / entity / report behind it; without this the tool reported
78:     only an echo of its own query (issue #694). ``type``/``kb_name`` are kept on
79:     every entry so consumers that key on them still work, and an engine that
80:     surfaces no provenance still yields the echo rather than nothing.
81:     """
82:     retrieved = [item for item in (result.get("sources") or []) if isinstance(item, dict)]
83:     if not retrieved:
84:         return [{"type": "rag", "query": query, "kb_name": kb_name}]
85:     return [{"type": "rag", "kb_name": kb_name, **item} for item in retrieved]
```

当前 L107–L134：
```text
107:     async def execute(self, **kwargs: Any) -> ToolResult:
108:         from deeptutor.tools.rag_tool import rag_search
109: 
110:         query = str(kwargs.get("query") or "").strip()
111:         if not query:
112:             raise ValueError("RAG query must be a non-empty string.")
113:         kb_name = str(kwargs.get("kb_name") or "").strip()
114:         if not kb_name:
115:             raise ValueError("RAG requires an explicit kb_name.")
116:         event_sink = kwargs.get("event_sink")
117:         extra_kwargs = {
118:             key: value
119:             for key, value in kwargs.items()
120:             if key not in {"query", "kb_name", "event_sink"}
121:         }
122: 
123:         result = await rag_search(
124:             query=query,
125:             kb_name=kb_name,
126:             event_sink=event_sink,
127:             **extra_kwargs,
128:         )
129:         content = result.get("answer") or result.get("content", "")
130:         return ToolResult(
131:             content=content,
132:             sources=_rag_sources(result, query=query, kb_name=kb_name),
133:             metadata=result,
134:         )
```

当前 L182–L212：
```text
182:     async def execute(self, **kwargs: Any) -> ToolResult:
183:         from deeptutor.knowledge.manifest import render_manifest_report
184:         from deeptutor.multi_user.knowledge_access import resolve_kb_manifest
185: 
186:         kb_name = str(kwargs.get("kb_name") or "").strip()
187:         if not kb_name:
188:             raise ValueError("kb_files requires an explicit kb_name.")
189:         pattern = str(kwargs.get("pattern") or "").strip()
190:         language = str(kwargs.get("language") or "en")
191: 
192:         manifest = await asyncio.to_thread(
193:             resolve_kb_manifest,
194:             kb_name,
195:             limit=_kb_files_limit(kwargs.get("limit")),
196:             pattern=pattern,
197:         )
198:         if manifest is None:
199:             raise ValueError(f"Knowledge base '{kb_name}' is not accessible.")
200: 
201:         return ToolResult(
202:             content=render_manifest_report(manifest, language=language),
203:             metadata={
204:                 "kb_name": manifest.name,
205:                 "total": manifest.total,
206:                 "matched": manifest.matched,
207:                 "listed": [document.name for document in manifest.documents],
208:                 "omitted": manifest.omitted,
209:                 "pattern": manifest.pattern,
210:                 "status": manifest.status,
211:                 "unavailable": manifest.unavailable,
212:             },
```

当前 L231–L261：
```text
231:             description="Search the web and return summarised results with citations.",
232:             parameters=[
233:                 ToolParameter(name="query", type="string", description="Search query."),
234:             ],
235:         )
236: 
237:     async def execute(self, **kwargs: Any) -> ToolResult:
238:         from deeptutor.tools.web_search import web_search
239: 
240:         query = kwargs.get("query", "")
241:         output_dir = kwargs.get("output_dir")
242:         verbose = kwargs.get("verbose", False)
243:         result = await asyncio.to_thread(
244:             web_search,
245:             query=query,
246:             output_dir=output_dir,
247:             verbose=verbose,
248:         )
249: 
250:         if isinstance(result, dict):
251:             answer = result.get("answer", "")
252:             citations = result.get("citations", [])
253:         else:
254:             answer = str(result)
255:             citations = []
256: 
257:         return ToolResult(
258:             content=answer,
259:             sources=[
260:                 {"type": "web", "url": citation.get("url", ""), "title": citation.get("title", "")}
261:                 for citation in citations
```

## `deeptutor/services/session/source_inventory.py`

SHA256 `75e070d48cf5645d3ae4c9eea97f305a799872e77fabbfc79b033f7158326f31`。

当前 L1–L55：
```text
1: """Branch-isolated, cumulative source inventory for the chat capability.
2: 
3: The chat pipeline shows the LLM an "Attached Sources" manifest each turn so
4: it can decide whether to call ``read_source(id)`` for full text. Historically
5: this manifest only listed sources the user attached in the *current* turn —
6: so the model forgot anything uploaded in earlier turns unless re-attached.
7: 
8: This module materialises the manifest as a **session-cumulative inventory**:
9: 
10: * Sources attached in the current turn (the "fresh" set) get a full preview
11:   in the manifest, just like before.
12: * Sources attached in *prior* turns on the active branch's ancestor chain
13:   (the "historical" set) get a compact one-line row: id, name, kind, size,
14:   and the turn ordinal where they first appeared. The LLM can call
15:   ``read_source(id)`` to load full text when the question warrants it.
16: 
17: Both sets dedupe by source id; fresh always wins on collision. Branch
18: isolation is enforced by walking ``parent_message_id`` from the active
19: branch's leaf, so sibling branches never leak sources into each other.
20: 
21: The output is decoupled from the rest of ``turn_runtime``:
22: 
23:     inventory = await build_inventory(store, ..., fresh_*=...)
24:     manifest_text, source_index = render_manifest(inventory)
25: 
26: ``source_index`` is the per-turn ``{source_id: full_text}`` map handed to
27: ``ReadSourceTool`` via tool-call kwargs injection.
28: """
29: 
30: from __future__ import annotations
31: 
32: from dataclasses import dataclass, field
33: import logging
34: from typing import Any, Sequence
35: 
36: from deeptutor.services.session.protocol import SessionStoreProtocol
37: 
38: logger = logging.getLogger(__name__)
39: 
40: # Per-source text-preview caps. Fresh sources get a meaningful preview so
41: # the model can answer simple "is this the right one?" questions without
42: # read_source. Historical sources surface only their identity — the model
43: # pays the read_source cost only when it actually needs them.
44: MANIFEST_PREVIEW_CHARS_FRESH = 2000
45: # Image attachments flow through the multimodal block path; never list them.
46: _IMAGE_MIME_PREFIX = "image/"
47: 
48: 
49: @dataclass(frozen=True)
50: class SourceEntry:
51:     """One row in the per-turn Attached Sources manifest."""
52: 
53:     sid: str
54:     kind: str  # "notebook" | "book" | "history" | "question" | "attachment"
55:     name: str
```

## `web/app/(workspace)/home/[[...sessionId]]/page.tsx`

SHA256 `d3d932f65e154cd685c90951493a18fad8b598a9fb954f91e7bd73d7ee4ac067`。

当前 L1532–L1557：
```text
1532:   // M0 trim: connected subagents were removed; keep the selector API surface
1533:   // inert (selectedAgent always null) so the composer stays type-safe.
1534:   const selectedAgent = useMemo(() => null as string | null, []);
1535:   const [subjectId, setSubjectId] = useState("");
1536:   const [subjectOptions, setSubjectOptions] = useState<{ id: string; name: string }[]>([]);
1537:   useEffect(() => {
1538:     let cancelled = false;
1539:     void (async () => {
1540:       try {
1541:         const res = await apiFetch("/api/v1/subjects");
1542:         if (res.ok) {
1543:           const data = await res.json();
1544:           if (!cancelled) setSubjectOptions(data.subjects ?? []);
1545:         }
1546:       } catch {
1547:         /* subjects unavailable */
1548:       }
1549:     })();
1550:     return () => {
1551:       cancelled = true;
1552:     };
1553:   }, []);
1554:   const subagentBudget = null;
1555: 
1556:   const handleSend = useCallback(
1557:     async (content: string) => {
```

当前 L1573–L1608：
```text
1573:         base64: a.base64,
1574:         mime_type: a.mimeType,
1575:       }));
1576:       let config: Record<string, unknown> | undefined;
1577:       if (subjectId) {
1578:         config = { ...(config ?? {}), subject_id: subjectId };
1579:       }
1580: 
1581:       if (isQuizMode) {
1582:         config = buildQuizWSConfig(quizConfig);
1583:         if (quizConfig.mode === "mimic" && quizPdf) {
1584:           const b64 = extractBase64FromDataUrl(
1585:             await readFileAsDataUrl(quizPdf),
1586:           );
1587:           extraAttachments = [
1588:             ...extraAttachments,
1589:             {
1590:               type: "pdf",
1591:               filename: quizPdf.name,
1592:               base64: b64,
1593:               mime_type: "application/pdf",
1594:             },
1595:           ];
1596:         }
1597:       }
1598:       if (isVisualizeMode) config = buildVisualizeWSConfig(visualizeConfig);
1599:       if (isResearchMode) {
1600:         if (!researchValidation.valid) return;
1601:         config = buildResearchWSConfig(researchConfig);
1602:       }
1603:       // When a connected agent is selected, carry the per-turn consult budget
1604:       // (how many times DeepTutor may ask it) so the subagent capability uses it.
1605:       if (selectedAgent && subagentBudget) {
1606:         config = { ...(config ?? {}), subagent_consult_budget: subagentBudget };
1607:       }
1608: 
```

当前 L2093–L2105：
```text
2093:               selectedBookReferences={selectedBookReferences}
2094:               selectedNotebookRecords={selectedNotebookRecords}
2095:               selectedHistorySessions={selectedHistorySessions}
2096:               selectedAgentSessions={selectedAgentSessions}
2097:               selectedQuestionEntries={selectedQuestionEntries}
2098:               notebookReferenceGroups={notebookReferenceGroups}
2099:               selectedPersona={null}
2100:               selectedMemoryFiles={selectedMemoryFiles}
2101:               selectedKnowledgeBases={selectedKbOnly}
2102:               isStreaming={state.isStreaming}
2103:               isVisualizeMode={isVisualizeMode}
2104:               capabilityNeedsConfig={capabilityNeedsConfig}
2105:               capabilityConfigConfirmed={capabilityConfigConfirmed}
```

当前 L2148–L2156：
```text
2148:                 session and starts it on the topic. */}
2149:             {!hasMessages ? (
2150:               <StarterSuggestions
2151:                 onPick={(prompt) => void handleSend(prompt)}
2152:                 disabled={state.isStreaming}
2153:               />
2154:             ) : null}
2155:             <div
2156:               aria-hidden="true"
```

## `web/context/UnifiedChatContext.tsx`

SHA256 `f1b7ec5dc9efabbc6af72f3dd0fc911277d87f0a079cb9fac76c1c5e664f42c1`。

当前 L86–L108：
```text
86: export interface ChatState {
87:   sessionId: string | null;
88:   sessionTitle: string;
89:   enabledTools: string[];
90:   activeCapability: string | null;
91:   knowledgeBases: string[];
92:   llmSelection: LLMSelection | null;
93:   /** Persistent mastery state associated with this conversation. */
94:   masteryPathId: string | null;
95:   /** Session-level persona preference; "" = Default (no persona). Applies
96:    *  to every following message until changed (persisted on the session). */
97:   personaSelection: string;
98:   messages: MessageItem[];
99:   isStreaming: boolean;
100:   currentStage: string;
101:   language: string;
102:   /** Edit-branching: keyed by stringified parent_message_id (or "null"
103:    *  for the root). Empty means "default to latest sibling everywhere". */
104:   selectedBranches: Record<string, number>;
105: }
106: 
107: interface SessionStatusSnapshot {
108:   sessionId: string;
```

当前 L1380–L1399：
```text
1380:       options?: { signal?: AbortSignal; revalidate?: boolean },
1381:     ) => {
1382:       const session = await getSession(sessionId, options?.signal);
1383:       const key = session.session_id || session.id;
1384:       const activeTurn = Array.isArray(session.active_turns)
1385:         ? session.active_turns[0]
1386:         : undefined;
1387:       if (options?.revalidate) {
1388:         // Background refresh of a session already on screen. Drop the whole
1389:         // snapshot — data *and* the re-subscribe below — once a turn is live
1390:         // locally: this tab is already receiving that turn's events, so
1391:         // re-subscribing from ``after_seq: 0`` would replay them on top of
1392:         // what we have, and the snapshot predates the turn anyway.
1393:         const local = stateRef.current.sessions[key];
1394:         if (!local || local.isStreaming || local.status === "running") return;
1395:       }
1396:       const messages = hydrateMessages(session.messages ?? []);
1397:       dispatch({
1398:         type: options?.revalidate ? "REVALIDATE_SESSION" : "LOAD_SESSION",
1399:         key,
```

当前 L1407–L1434：
```text
1407:         tools: Array.isArray(session.preferences?.tools)
1408:           ? session.preferences.tools
1409:           : [],
1410:         capability: session.preferences?.capability || null,
1411:         knowledgeBases: Array.isArray(session.preferences?.knowledge_bases)
1412:           ? session.preferences.knowledge_bases
1413:           : [],
1414:         llmSelection: asLLMSelection(session.preferences?.llm_selection),
1415:         masteryPathId:
1416:           typeof session.preferences?.mastery_path_id === "string"
1417:             ? session.preferences.mastery_path_id
1418:             : null,
1419:         personaSelection:
1420:           typeof session.preferences?.persona === "string"
1421:             ? session.preferences.persona
1422:             : "",
1423:         // Model output language is account-level state. Historical sessions
1424:         // may have stale persisted preferences, so new turns follow the
1425:         // current response-language setting rather than their original value.
1426:         language: readStoredResponseLanguage(),
1427:         selectedBranches: normalizeSelectedBranches(
1428:           session.preferences?.selected_branches,
1429:         ),
1430:       });
1431:       if (activeTurn?.turn_id || activeTurn?.id) {
1432:         // Reached on a revalidate too, when the turn is live on the server but
1433:         // not in this tab (started in another tab, or our socket dropped) —
1434:         // that is exactly the case that still needs a subscribe.
```

当前 L1591–L1618：
```text
1591:           type: a.type,
1592:           filename: a.filename,
1593:           base64: a.base64,
1594:           url: a.url,
1595:           mime_type: a.mime_type,
1596:         })) ?? msgAttachments;
1597:       const effectiveConfig = config ?? replaySnapshot?.config;
1598:       const effectiveNotebookReferences =
1599:         replaySnapshot?.notebookReferences ?? notebookReferences;
1600:       const effectiveHistoryReferences =
1601:         replaySnapshot?.historyReferences ?? historyReferences;
1602:       const effectiveQuestionNotebookReferences =
1603:         replaySnapshot?.questionNotebookReferences ??
1604:         questionNotebookReferences;
1605:       const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
1606:         content,
1607:         capability: effectiveCapability,
1608:         enabledTools: [...effectiveTools],
1609:         knowledgeBases: [...effectiveKnowledgeBases],
1610:         language: effectiveLanguage,
1611:         ...(effectiveAttachments?.length
1612:           ? { attachments: effectiveAttachments }
1613:           : {}),
1614:         ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
1615:           ? { config: effectiveConfig }
1616:           : {}),
1617:         ...(effectiveNotebookReferences?.length
1618:           ? { notebookReferences: effectiveNotebookReferences }
```

当前 L1712–L1725：
```text
1712:         ...(effectiveMemoryReferences?.length
1713:           ? { memory_references: effectiveMemoryReferences }
1714:           : {}),
1715:         ...(effectiveLLMSelection
1716:           ? { llm_selection: effectiveLLMSelection }
1717:           : {}),
1718:         ...(effectiveConfig?.subject_id
1719:           ? { subject_id: effectiveConfig.subject_id }
1720:           : {}),
1721:         ...(effectiveTurnConfig && Object.keys(effectiveTurnConfig).length > 0
1722:           ? { config: effectiveTurnConfig }
1723:           : {}),
1724:         // Send ``parent_message_id`` only when we have a real (positive)
1725:         // server id to chain under, or when the caller explicitly pinned
```

## `web/components/chat/home/SubjectSelector.tsx`

SHA256 `0759c54cb77c18c22d43957d386bcc963e430872cdb8c604f6a46e2fffdcd390`。

当前 L13–L24：
```text
13:  */
14: export default function SubjectSelector({
15:   subjects,
16:   value,
17:   onChange,
18:   placement = "top",
19: }: {
20:   subjects: SubjectOption[];
21:   value: string;
22:   onChange: (id: string) => void;
23:   /**
24:    * Which way the menu opens. The composer toolbar sits at the bottom of the
```

当前 L35–L48：
```text
35:   const current = subjects.find((s) => s.id === value);
36: 
37:   useEffect(() => {
38:     if (!open) return;
39:     const close = (e: MouseEvent) => {
40:       if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
41:     };
42:     document.addEventListener("mousedown", close);
43:     return () => document.removeEventListener("mousedown", close);
44:   }, [open]);
45: 
46:   if (subjects.length === 0) return null;
47: 
48:   // Same placement + viewport-safe width contract as the other composer
```

当前 L66–L90：
```text
66:         <span className="max-w-[9rem] truncate">
67:           {current ? current.name : t("无科目", "无科目")}
68:         </span>
69:         <ChevronDown size={12} />
70:       </button>
71:       {open && (
72:         <div
73:           className={`absolute left-0 z-50 ${menuPlacementClass} max-h-72 w-[min(240px,calc(100vw-32px))] overflow-y-auto rounded-lg border bg-background p-1 shadow-lg`}
74:         >
75:           {subjects.map((s) => (
76:             <button
77:               key={s.id}
78:               onClick={() => {
79:                 onChange(s.id);
80:                 setOpen(false);
81:               }}
82:               className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/5"
83:             >
84:               <span className="truncate">{s.name}</span>
85:               {s.id === value && <Check size={14} className="text-emerald-600" />}
86:             </button>
87:           ))}
88:         </div>
89:       )}
90:     </div>
```

## `web/scripts/run-node-tests.mjs`

SHA256 `f67c84ce249ae9cfa6607038f6be0cad0a8428aa90186df0dcc69f8870681f74`。

当前 L1–L47：
```text
1: import { readdirSync, rmSync, statSync } from "node:fs";
2: import { spawnSync } from "node:child_process";
3: import path from "node:path";
4: import { fileURLToPath } from "node:url";
5: 
6: const __filename = fileURLToPath(import.meta.url);
7: const __dirname = path.dirname(__filename);
8: const webRoot = path.resolve(__dirname, "..");
9: const distRoot = path.join(webRoot, "dist", "node-tests");
10: const testRoot = path.join(distRoot, "tests");
11: 
12: function run(cmd, args) {
13:   const result = spawnSync(cmd, args, {
14:     cwd: webRoot,
15:     stdio: "inherit",
16:     env: process.env,
17:   });
18:   if (result.status !== 0) {
19:     process.exit(result.status ?? 1);
20:   }
21: }
22: 
23: function collectTests(dir) {
24:   const entries = readdirSync(dir)
25:     .map((name) => path.join(dir, name))
26:     .sort((a, b) => a.localeCompare(b));
27:   const files = [];
28:   for (const entry of entries) {
29:     const stats = statSync(entry);
30:     if (stats.isDirectory()) {
31:       files.push(...collectTests(entry));
32:       continue;
33:     }
34:     if (entry.endsWith(".test.js")) {
35:       files.push(entry);
36:     }
37:   }
38:   return files;
39: }
40: 
41: rmSync(distRoot, { recursive: true, force: true });
42: 
43: run(process.execPath, [
44:   path.join(webRoot, "node_modules", "typescript", "bin", "tsc"),
45:   "-p",
46:   "tsconfig.node-tests.json",
47: ]);
```

## `web/tsconfig.node-tests.json`

SHA256 `b9ceadd1d99e85ff0652717f4d4635437da15cbc51dc27864ced18ba0d06ebec`。

当前 L1–L16：
```text
1: {
2:   "extends": "./tsconfig.json",
3:   "compilerOptions": {
4:     "noEmit": false,
5:     "outDir": "./dist/node-tests",
6:     "rootDir": ".",
7:     "baseUrl": ".",
8:     "module": "commonjs",
9:     "moduleResolution": "node",
10:     "incremental": false,
11:     "paths": {
12:       "@/*": ["./*"]
13:     }
14:   },
15:   "include": ["tests/**/*.ts"]
16: }
```

## `web/tests/reconnecting-websocket.test.ts`

SHA256 `e25806bc642aa693b77721316e24afeaf3397884adf363fb8ad95ea3b696f751`。

当前 L1–L35：
```text
1: import test from "node:test";
2: import assert from "node:assert/strict";
3: import { readFileSync } from "node:fs";
4: import path from "node:path";
5: import {
6:   ReconnectingWebSocket,
7:   reconnectDelayMs,
8: } from "../lib/reconnecting-websocket";
9: 
10: class FakeSocket {
11:   readyState = 0;
12:   sent: string[] = [];
13:   onopen: ((event: Event) => void) | null = null;
14:   onmessage: ((event: MessageEvent) => void) | null = null;
15:   onerror: ((event: Event) => void) | null = null;
16:   onclose: ((event: CloseEvent) => void) | null = null;
17: 
18:   open(): void {
19:     this.readyState = 1;
20:     this.onopen?.({} as Event);
21:   }
22: 
23:   drop(): void {
24:     this.readyState = 3;
25:     this.onclose?.({} as CloseEvent);
26:   }
27: 
28:   close(): void {
29:     if (this.readyState !== 3) this.drop();
30:   }
31: 
32:   send(payload: string): void {
33:     this.sent.push(payload);
34:   }
35: }
```

参考路径未存在：`web/tests/context-sources.test.ts`；不要为此补造文件。

测试只读参考（实施时按需读）：tests/phase1/helpers.py 的 make_same_name_kbs/isolated_runtime/install_provider_stubs，tests/phase1/conftest.py 的显式 p1_runtime/p1_subjects；tests/services/session/test_regenerate.py；tests/api/test_unified_ws_turn_runtime.py；tests/tools/test_rag_tool.py、test_kb_files_tool.py；tests/agents/chat/test_kb_manifest_note.py；S01 临时 HOME launcher。
跨目录 pytest 收集前必须由 S01 launcher 初始化临时 HOME。不要运行真实应用来做 orientation，不读取真实 settings/历史 memory trace。
边界：S08 报告/S14 大规模裁剪/S15 浏览器验收不提前实施；不增加新功能、provider、MCP、DB 列，不迁移或重建用户数据。

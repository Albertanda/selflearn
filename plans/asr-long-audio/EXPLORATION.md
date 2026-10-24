# ASR-R1 已探索文件清单＋关键原文片段

以下由协调者从当前源码逐行提取。先算SHA256，匹配可直接复用，只补读实现接缝。未列出的新模块目标见TASKS.json，不需要搜索上游57张卡。关键片段是现状，不是正确实现示例或新增授权；实施边界以START和CONTRACTS为准。所有源码路径相对 `/home/albert/selflearn/selflearn`，行号一基。

## 定向导航

- 配置/provider：transcribe、resolve_stt_runtime_config、STTConfig、连接测试。新长文件路径不能倒退成整文件bytes。
- 一致性：SubjectPaths/subject_dir、活动租约、upload staging/commit、export exclusions；只读查询不要触发create。
- 接口：当前subjects音频同步等待，SubjectRoute错误边界，main只需注册新router与ASR shutdown。
- 前端：Proxy matcher、专用streaming route、两页上传helper与scope回调；新route需POST/GET均转发。
- 验收：S15配置严格临时源/出口/清理保护可复用；B3跟随新入口，其他组保留；新65秒场景另建suite。

## `AGENTS.md`

SHA256：`6ae6ff588618be241ccd8320ef639c5435ed4de8882b03baa9dca5023f3cb3d7`

L137–L165：

```text
0137: ## Current Fork Differences
0138: 
0139: - The Partner (IM companion) runtime and the Book command are not part of this
0140:   fork: `deeptutor partner` and `deeptutor book` are not registered. Use upstream
0141:   DeepTutor if those features are required.
0142: - The `.[partners]`, `.[tutorbot]`, `.[matrix]` and `.[matrix-e2e]` extras and
0143:   their requirements mirrors are removed. `requirements.txt` installs the
0144:   supported `requirements/server.txt` profile.
0145: - PageIndex is available through the existing RAG outline pipeline
0146:   (`retrieval_kind=outline`); this fork has no PageIndex MCP transport. The MCP
0147:   SDK stays as a compatibility dependency pending review.
0148: - `scripts/start_selflearn.sh` is the supported fixed-home launcher: it resolves
0149:   this checkout from the script path, overrides inherited `DEEPTUTOR_HOME`, changes
0150:   to the checkout and execs its `.venv/bin/deeptutor start --home <checkout>`.
0151:   It rejects caller `--home`/`--home=` and makes missing venv/CLI a named failure.
0152:   `deeptutor/runtime/home.py` itself still falls back to cwd when no explicit
0153:   home/env is supplied; do not describe that global behavior as fixed.
0154: - Document upload (`index`) and audio upload (`transcribe`) are different: audio
0155:   transcripts go to `materials/lecture` and do not auto-build an index.
0156:   Image coverage that is unmeasured/skipped must not be reported as complete.
0157:   Knowledge points without attempt evidence are `mastery=null` / unassessed.
0158:   Subject export excludes chat history and offers no import/restore.
0159: - Learner facts are extracted only by the subject-scoped chat history summarizer
0160:   (`services/session/summarize.py` via `api/routers/chat.py`); uploads and subject
0161:   endpoints do not extract new profile facts automatically.
0162: - The report-only chart/ODE executor requires its qualified bwrap-backed boundary;
0163:   unavailable/unsupported backends return 503 with no host fallback. The normal
0164:   shared sandbox runner is not proof of report isolation. S13/P50 OS, S14
0165:   HTTP/WS and S15 Chromium browser gates have passed locally with deterministic
```

L171–L177：

```text
0171: ## Isolated Python tests
0172: 
0173: Use `.venv/bin/python scripts/run_tests_isolated.py [pytest arguments]`. With no arguments it runs the configured full suite. Direct unisolated collection fails before application imports; do not bypass the guard. Preserve both historical data evidence and the explicitly approved S14 catalog exception baseline. Any later change remains a failure.
0174: 
0175: ## Browser evidence preservation
0176: 
0177: The S15 Playwright configuration refuses sealed evidence directories. An explicitly requested rerun must set `S15_EVIDENCE_DIR` to a fresh directory under this checkout’s `.phase1-evidence/`; reuse the installed browser and isolated source runner. Never point `S15_SOURCE_COPY` at this checkout, its ancestors, or existing data. Read-only handoff instructions and verified source excerpts are in `plans/phase1/PHASE1_HANDOFF.txt`.
```
## `deeptutor/services/asr/transcribe.py`

SHA256：`7aa1e77b3fb634f3f9c860252566ce955eb53e39b0da514d6469fd3f57ffebfa`

L32–L33：

```text
0032: STT_TIMEOUT_SECONDS = 300
```

L56–L71：

```text
0056: def _stt_config() -> tuple[str, str, str]:
0057:     """Return (base_url, api_key, model) from the active STT profile."""
0058:     from deeptutor.services.config.model_catalog import get_model_catalog_service
0059:     from deeptutor.services.config.provider_runtime import _active_profile_and_model
0060: 
0061:     service = get_model_catalog_service()
0062:     catalog = service.load()
0063:     profile, model = _active_profile_and_model(catalog, service, "stt")
0064:     api_key = str((profile or {}).get("api_key") or "")
0065:     base_url = str((profile or {}).get("base_url") or DEFAULT_STT_BASE).rstrip("/")
0066:     model_name = str((model or {}).get("model") or DEFAULT_STT_MODEL)
0067:     return base_url, api_key, model_name
0068: 
0069: 
0070: _JSON_LEADING = ("{", "[", '"')
0071: _JSON_LITERALS = {"null", "true", "false"}
```

L155–L168：

```text
0155: async def transcribe(audio_path: Path, *, language: str = "zh") -> dict:
0156:     """Transcribe one audio file via the OpenAI-compatible STT endpoint.
0157: 
0158:     Returns ``{text, model, base_url}`` plus ``error``/``error_kind`` when the
0159:     call failed; ``text`` is "" on failure. A legal empty transcript is a
0160:     success with ``text == ""`` and no error.
0161:     """
0162:     try:
0163:         base_url, api_key, model_name = _stt_config()
0164:     except (SubjectOperationError, SubjectStorageError):
0165:         # Preserve already-classified local corruption/IO and domain failures.
0166:         raise
0167:     except (TimeoutError, httpx.TimeoutException) as exc:
0168:         return _unconfigured_failure("timeout", f"STT 配置读取超时：{type(exc).__name__}")
```

L184–L208：

```text
0184:     audio_path = Path(audio_path)
0185:     url = f"{base_url}/audio/transcriptions"
0186:     data = {"model": model_name, "language": language, "response_format": "text"}
0187:     headers = {"Authorization": f"Bearer {api_key}"}
0188:     try:
0189:         async with httpx.AsyncClient(timeout=STT_TIMEOUT_SECONDS) as client:
0190:             # Streamed multipart: the provider reads the file handle directly,
0191:             # so a 200MiB recording never becomes one in-memory bytes object.
0192:             with open(audio_path, "rb") as handle:
0193:                 files = {"file": (audio_path.name, handle, mime_for(audio_path))}
0194:                 resp = await client.post(url, headers=headers, files=files, data=data)
0195:     except httpx.TimeoutException as exc:
0196:         return _failure(base_url, model_name, "timeout", f"ASR 请求超时：{type(exc).__name__}")
0197:     except OSError as exc:
0198:         return _failure(base_url, model_name, "io", f"ASR 无法读取音频：{type(exc).__name__}")
0199:     except Exception as exc:  # noqa: BLE001
0200:         return _failure(base_url, model_name, "provider", f"ASR 调用异常：{type(exc).__name__}")
0201: 
0202:     if resp.status_code != 200:
0203:         return _failure(
0204:             base_url, model_name, "provider", f"ASR 请求失败，状态码 {resp.status_code}"
0205:         )
0206:     content_type = ""
0207:     try:
0208:         content_type = str(resp.headers.get("content-type") or "")
```
## `deeptutor/services/config/provider_runtime.py`

SHA256：`6872c3b1831b8ecd8cad1b860b2085ad3b6298e243fc2ccb9960f628fd406cf8`

L1021–L1052：

```text
1021: def resolve_stt_runtime_config(
1022:     catalog: dict[str, Any] | None = None,
1023:     *,
1024:     service: ModelCatalogService | None = None,
1025: ) -> STTConfig:
1026:     """Resolve the active speech-to-text config from the model catalog."""
1027:     catalog_service = service or get_model_catalog_service()
1028:     loaded = _load_catalog(catalog)
1029:     profile, model = _active_profile_and_model(loaded, catalog_service, "stt")
1030:     resolved_model = _as_str((model or {}).get("model"))
1031:     if not resolved_model:
1032:         raise ValueError("No active STT model is configured. Set it in Settings > Voice.")
1033: 
1034:     provider = _canonical_voice_provider(_as_str((profile or {}).get("binding")), STT_PROVIDERS)
1035:     spec = STT_PROVIDERS[provider]
1036:     api_base = _as_str((profile or {}).get("base_url")) or spec.default_api_base
1037:     api_key = _as_str((profile or {}).get("api_key"))
1038:     if not api_key and spec.is_local:
1039:         api_key = "sk-no-key-required"
1040: 
1041:     return STTConfig(
1042:         model=resolved_model,
1043:         provider_name=provider,
1044:         adapter=spec.adapter,
1045:         request_style=spec.request_style,
1046:         auth_style=spec.auth_style,
1047:         api_key=api_key,
1048:         base_url=api_base,
1049:         api_version=_as_str((profile or {}).get("api_version")) or None,
1050:         extra_headers=_to_headers((profile or {}).get("extra_headers")),
1051:         language=_as_str((model or {}).get("language")) or None,
1052:     )
```
## `deeptutor/services/voice/config.py`

SHA256：`8621045c3f6b0eae386f54a0e3a15e3a7310819d5c04269bb4347d2d8f94eeee`

L47–L63：

```text
0047: class STTConfig:
0048:     """Resolved speech-to-text configuration for one transcription call."""
0049: 
0050:     model: str
0051:     provider_name: str = "openai"
0052:     adapter: str = "openai_compat"
0053:     request_style: str = STT_MULTIPART
0054:     auth_style: str = AUTH_BEARER
0055:     api_key: str = ""
0056:     base_url: str = ""
0057:     api_version: str | None = None
0058:     extra_headers: dict[str, str] = field(default_factory=dict)
0059:     language: str | None = None
0060:     request_timeout: int = 120
0061: 
0062: 
0063: __all__ = [
```
## `deeptutor/services/voice/adapters/openai_compat.py`

SHA256：`b175cebedc93c12965a05e1baf6e7feeb1c06eafef706b59ce6443cfa3ea14e9`

L287–L323：

```text
0287: class OpenAICompatSTTAdapter(BaseSTTAdapter):
0288:     """POST ``{base}/audio/transcriptions``.
0289: 
0290:     Multipart ``file`` upload by default; OpenRouter uses a base64-JSON body
0291:     (``request_style == "base64_json"``) sharing the same path.
0292:     """
0293: 
0294:     async def transcribe(
0295:         self,
0296:         audio: bytes,
0297:         config: STTConfig,
0298:         *,
0299:         filename: str = "audio.webm",
0300:         content_type: str = "application/octet-stream",
0301:     ) -> str:
0302:         if not config.base_url:
0303:             raise VoiceProviderError("No endpoint URL configured for STT.")
0304:         if not audio:
0305:             raise VoiceProviderError("No audio data to transcribe.")
0306:         url = join_audio_path(config.base_url, "audio/transcriptions")
0307:         auth = build_auth_headers(config.auth_style, config.api_key)
0308: 
0309:         try:
0310:             async with httpx.AsyncClient(timeout=config.request_timeout) as client:
0311:                 if config.request_style == STT_BASE64_JSON:
0312:                     resp = await self._post_base64(client, url, auth, audio, filename, config)
0313:                 else:
0314:                     resp = await self._post_multipart(
0315:                         client, url, auth, audio, filename, content_type, config
0316:                     )
0317:         except httpx.HTTPError as exc:
0318:             raise VoiceProviderError(f"STT request error: {exc}") from exc
0319:         _raise_for_provider(resp, "Transcription")
0320:         return self._parse_text(resp)
0321: 
0322:     async def _post_multipart(
0323:         self,
```
## `deeptutor/services/config/test_runner.py`

SHA256：`5861a79b725d08238cc4d3e289805820b0d3c71ea4bd570f16bd205c9346bae7`

L480–L516：

```text
0480:     async def _test_stt(self, run: TestRun, catalog: dict[str, Any]) -> None:
0481:         import io
0482:         import wave
0483: 
0484:         from deeptutor.services.config.provider_runtime import resolve_stt_runtime_config
0485:         from deeptutor.services.voice import transcribe_audio
0486: 
0487:         run.emit("info", "Loading STT config from the active catalog selection.")
0488:         resolved = resolve_stt_runtime_config(catalog=catalog)
0489:         run.emit(
0490:             "info",
0491:             f"Resolved model `{resolved.model}` (provider `{resolved.provider_name}`, "
0492:             f"style `{resolved.request_style}`).",
0493:         )
0494:         run.emit("info", f"Request target: {resolved.base_url}")
0495: 
0496:         # One second of 16 kHz mono silence — a valid WAV that exercises the
0497:         # full upload + auth + model path. Most providers return empty/near-empty
0498:         # text; a clean HTTP 200 confirms the connection is configured correctly.
0499:         buffer = io.BytesIO()
0500:         with wave.open(buffer, "wb") as wav:
0501:             wav.setnchannels(1)
0502:             wav.setsampwidth(2)
0503:             wav.setframerate(16000)
0504:             wav.writeframes(b"\x00\x00" * 16000)
0505:         run.emit("info", "Uploading a 1s silent probe clip to validate the endpoint.")
0506:         transcript = await transcribe_audio(
0507:             buffer.getvalue(),
0508:             catalog=catalog,
0509:             filename="probe.wav",
0510:             content_type="audio/wav",
0511:         )
0512:         run.emit(
0513:             "response",
0514:             "Transcription endpoint responded successfully.",
0515:             snippet=(transcript or "(empty — expected for a silent clip)")[:200],
0516:         )
```
## `deeptutor/subjects/errors.py`

SHA256：`fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88`

L39–L73：

```text
0039: class ErrorCode(str, Enum):
0040:     """C02 表中的全部 code。"""
0041: 
0042:     INVALID_INPUT = "invalid_input"
0043:     INVALID_SUBJECT_ID = "invalid_subject_id"
0044:     SUBJECT_NOT_FOUND = "subject_not_found"
0045:     ENTRY_NOT_FOUND = "entry_not_found"
0046:     KB_NOT_FOUND = "kb_not_found"
0047:     SCOPE_FORBIDDEN = "scope_forbidden"
0048:     KB_NOT_READY = "kb_not_ready"
0049:     KB_BUSY = "kb_busy"
0050:     MATERIAL_OUT_OF_SYNC = "material_out_of_sync"
0051:     STORAGE_CORRUPT = "storage_corrupt"
0052:     STORAGE_IO = "storage_io"
0053:     INTERNAL_ERROR = "internal_error"
0054:     PROVIDER_UNAVAILABLE = "provider_unavailable"
0055:     PROVIDER_TIMEOUT = "provider_timeout"
0056:     EMPTY_MODEL_OUTPUT = "empty_model_output"
0057:     INVALID_MODEL_OUTPUT = "invalid_model_output"
0058:     OUTPUT_TRUNCATED = "output_truncated"
0059:     REASONING_BUDGET_EXHAUSTED = "reasoning_budget_exhausted"
0060:     SANDBOX_UNAVAILABLE = "sandbox_unavailable"
0061:     SANDBOX_POLICY_UNSUPPORTED = "sandbox_policy_unsupported"
0062:     CHART_FAILED = "chart_failed"
0063:     RENDER_FAILED = "render_failed"
0064:     FEATURE_UNAVAILABLE = "feature_unavailable"
0065: 
0066: 
0067: @dataclass(frozen=True)
0068: class ErrorSpec:
0069:     """一个 code 的固定投影。消息是常量，绝不拼接输入。"""
0070: 
0071:     code: ErrorCode
0072:     http_status: int
0073:     retryable: bool
```

L118–L126：

```text
0118:     ErrorCode.PROVIDER_UNAVAILABLE: _spec(
0119:         ErrorCode.PROVIDER_UNAVAILABLE, 502, True, "模型服务暂时不可用，请稍后重试。"
0120:     ),
0121:     ErrorCode.PROVIDER_TIMEOUT: _spec(
0122:         ErrorCode.PROVIDER_TIMEOUT, 504, True, "模型服务响应超时，请重试。"
0123:     ),
0124:     ErrorCode.EMPTY_MODEL_OUTPUT: _spec(
0125:         ErrorCode.EMPTY_MODEL_OUTPUT, 502, True, "模型返回空内容，请重试。"
0126:     ),
```
## `deeptutor/subjects/json_store.py`

SHA256：`719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca`

L182–L208：

```text
0182: def confined(root: Path, path: Path) -> Path:
0183:     """Return *path* after proving it stays inside *root* without symlinks.
0184: 
0185:     Checks the root, every component below it, and the final resolved location.
0186:     Nothing is created or opened here — callers run this *before* touching the
0187:     target, so a rejected path is never read, mkdir'd or locked.
0188:     """
0189:     root = ensure_trusted_root(root)
0190:     path = Path(path)
0191:     try:
0192:         relative = path.relative_to(root)
0193:     except ValueError:
0194:         raise StorageIOError(_ESCAPE_MESSAGE, path=path.name) from None
0195: 
0196:     resolved_root = root.resolve()
0197:     current = root
0198:     for part in relative.parts:
0199:         current = current / part
0200:         if current.is_symlink():
0201:             raise StorageIOError(_SYMLINK_MESSAGE, path=path.name)
0202: 
0203:     resolved = path.resolve()
0204:     if resolved != resolved_root and resolved_root not in resolved.parents:
0205:         raise StorageIOError(_ESCAPE_MESSAGE, path=path.name)
0206:     return path
0207: 
```

L390–L400：

```text
0390: def atomic_write_object(path: Path, payload: dict) -> None:
0391:     """Object counterpart of :func:`atomic_write_list`."""
0392:     path = Path(path)
0393:     if not isinstance(payload, dict):
0394:         raise UpdateCallbackError("对象文档必须是对象")
0395:     _commit(path, dict(payload))
0396: 
0397: 
0398: # ---------------------------------------------------------------------------
0399: # Locking
0400: # ---------------------------------------------------------------------------
```

L710–L716：

```text
0710: def json_transaction(lock_dir: Path) -> Iterator[JsonTransaction]:
0711:     """Hold *lock_dir*'s process + OS lock for the duration of the block."""
0712:     with JsonTransaction(Path(lock_dir)) as transaction:
0713:         yield transaction
0714: 
0715: 
0716: def transaction_depth(lock_dir: Path) -> int:
```
## `deeptutor/subjects/subject_operations.py`

SHA256：`0fa585abebe8ef8a1fc11e6e80508222014fb5edbad620322bb048a87b8282e0`

L57–L104：

```text
0057: class ActivityLease:
0058:     """One held OS lease.  ``release`` is idempotent and safe from any thread."""
0059: 
0060:     key: str
0061:     subject_id: str
0062:     mode: str
0063:     kind: str
0064:     path: Path
0065:     fd: int
0066:     _released: bool = field(default=False, repr=False)
0067:     _detached: bool = field(default=False, repr=False)
0068:     _guard: threading.Lock = field(default_factory=threading.Lock, repr=False)
0069:     _owner_pid: int = field(default_factory=os.getpid, repr=False)
0070: 
0071:     @property
0072:     def active(self) -> bool:
0073:         if self._owner_pid != os.getpid():
0074:             return False
0075:         with self._guard:
0076:             return not self._released
0077: 
0078:     @property
0079:     def detached(self) -> bool:
0080:         with self._guard:
0081:             return self._detached
0082: 
0083:     def detach(self) -> "ActivityLease":
0084:         """Hand ownership to a long-lived holder (e.g. a queued worker).
0085: 
0086:         The lease stays active; only its new owner releases it.  The route that
0087:         handed it off must not release it in a ``finally`` block.
0088:         """
0089:         with self._guard:
0090:             self._detached = True
0091:         return self
0092: 
0093:     def release(self) -> None:
0094:         """Drop the flock and close the descriptor exactly once.
0095: 
0096:         The descriptor is closed from whichever thread finishes last.  That is
0097:         what lets a cancelled request hand ownership to the still-running
0098:         render/copy thread instead of pretending the subject became idle.
0099:         """
0100:         inherited = self._owner_pid != os.getpid()
0101:         if inherited:
0102:             # A fork inherited the open file description and possibly a held
0103:             # Python mutex. Close the child's descriptor without LOCK_UN:
0104:             # unlocking that shared description would unlock the parent too.
```

L169–L207：

```text
0169: def acquire_activity(
0170:     subject_id: str, *, mode: str = SHARED, kind: str = "activity"
0171: ) -> ActivityLease:
0172:     """Try to acquire one shared/exclusive subject lease without blocking.
0173: 
0174:     Raises the historical C02 ``kb_busy`` (409, retryable) when another
0175:     thread/process holds a conflicting lease.  Missing OS locking support is a
0176:     hard storage error, never a silently unlocked success.
0177:     """
0178:     if mode not in MODES:
0179:         raise ValueError(f"unknown activity mode: {mode!r}")
0180:     if not isinstance(kind, str) or not kind:
0181:         kind = "activity"
0182:     key = lease_key(subject_id)
0183:     if fcntl is None:
0184:         raise ActivityLeaseError("当前平台缺少经过验证的文件锁支持，已拒绝并发写入。")
0185:     root = _lock_root()
0186:     path = json_store.confined(root, root / f"{subject_id}.lock")
0187:     if path.is_symlink():
0188:         raise ActivityLeaseError("活动租约文件是符号链接，已拒绝访问。")
0189:     flags = os.O_RDWR | os.O_CREAT
0190:     if hasattr(os, "O_NOFOLLOW"):
0191:         flags |= os.O_NOFOLLOW
0192:     flags |= os.O_NONBLOCK
0193:     try:
0194:         fd = os.open(path, flags, 0o600)
0195:     except OSError as exc:
0196:         raise ActivityLeaseError("无法建立活动租约。", cause=exc) from exc
0197: 
0198:     try:
0199:         if not stat.S_ISREG(os.fstat(fd).st_mode):
0200:             raise ActivityLeaseError("活动租约文件不是常规文件，已拒绝访问。")
0201:         operation = fcntl.LOCK_EX if mode == EXCLUSIVE else fcntl.LOCK_SH
0202:         fcntl.flock(fd, operation | fcntl.LOCK_NB)
0203:         # A deletion may have completed between the first identity read and
0204:         # lock acquisition. Never authorize a late writer to resurrect its tree.
0205:         if store.get_subject(subject_id) is None:
0206:             raise store.SubjectNotFoundError(subject_id)
0207:     except BlockingIOError as exc:
```

L227–L236：

```text
0227: def require_activity(lease: ActivityLease, subject_id: str, *, mode: str | None = None) -> None:
0228:     """Validate a passed server lease without releasing somebody else's lease."""
0229:     key = lease_key(subject_id)
0230:     with _DIAGNOSTIC_LOCK:
0231:         owned = any(item is lease for item in _ACTIVE.get(key, ()))
0232:     if not owned or not lease.active or lease.key != key or (mode and lease.mode != mode):
0233:         raise json_store.invalid_input("活动租约不属于当前用户和科目")
0234: 
0235: 
0236: def _after_fork_child() -> None:
```
## `deeptutor/subjects/store.py`

SHA256：`0a3d04dfdc9bb188a7e0caa1027aaf84c8dfbcabd96e1d9f7f927e165254eeff`

L192–L215：

```text
0192: def subject_dir(subject_id: str) -> Path:
0193:     """The data directory for one subject in the current user's registry.
0194: 
0195:     Raises an explicit error for an id that is not a plain slug, for a path
0196:     that resolves outside this user's subject root, and for a well-formed id
0197:     that is simply not registered (404) — writing learner data must never bring
0198:     a subject tree into existence.
0199:     """
0200:     path = _subject_dir_unchecked(subject_id)
0201:     if not _is_registered(subject_id):
0202:         raise SubjectNotFoundError(subject_id)
0203:     return path
0204: 
0205: 
0206: def subject_data_path(subject_id: str, name: str) -> Path:
0207:     """A confined data file for *subject_id* (validation before any read).
0208: 
0209:     This is the single entry point the collection modules use for their JSON
0210:     files, so a symlinked ``wrong_book.json`` is refused before it is opened
0211:     rather than after the other subject's bytes have been read.
0212:     """
0213:     directory = subject_dir(subject_id)
0214:     return json_store.confined(directory, directory / json_store.safe_segment(name))
```

L481–L523：

```text
0481: def delete_subject(subject_id: str) -> bool:
0482:     """Delete the current user's learning + public trees, then the registry.
0483: 
0484:     The exclusive activity lease covers validation, both removals and the
0485:     registry write, so an upload/index/report/review/export cannot be running
0486:     while its subject disappears. Any symlink anywhere in either tree is
0487:     refused *before* the first byte is removed. A partial cleanup is reported
0488:     honestly (``storage_io``) while the registry entry is retained, making a
0489:     later retry possible; this is deliberately not presented as a multi-tree
0490:     crash transaction.
0491:     """
0492:     if not isinstance(subject_id, str) or not is_valid_subject_id(subject_id):
0493:         raise InvalidSubjectIdError(subject_id)
0494:     if get_subject(subject_id) is None:
0495:         return False
0496: 
0497:     from deeptutor.subjects import subject_operations
0498: 
0499:     lease = subject_operations.acquire_activity(
0500:         subject_id, mode=subject_operations.EXCLUSIVE, kind="delete"
0501:     )
0502:     try:
0503:         # The mutex is held now: this is the authoritative registration check.
0504:         if get_subject(subject_id) is None:
0505:             return False
0506:         root = subjects_root()
0507:         directory = _subject_dir_unchecked(subject_id)
0508:         public = _public_subject_dir_unchecked(subject_id)
0509:         # Validate both trees *before* deleting either one.
0510:         _assert_deletable_tree(directory, root)
0511:         _assert_deletable_tree(public, current_subject_paths().get_public_outputs_root())
0512:         _remove_tree_strict(directory)
0513:         _remove_tree_strict(public)
0514: 
0515:         with json_store.json_transaction(root) as tx:
0516:             index = tx.path(_INDEX_NAME)
0517:             subjects = _validate_registry(tx.read_list(index), index)
0518:             if not any(record.get("id") == subject_id for record in subjects):
0519:                 return False
0520:             kept = [record for record in subjects if record.get("id") != subject_id]
0521:             tx.write_list(index, kept)
0522:         return True
0523:     finally:
```
## `deeptutor/subjects/uploads.py`

SHA256：`77e5a3aff42168bdf665693d5aea4bb92befff2fa373ceb6fb9a0f64dd7c54a1`

L186–L206：

```text
0186: def plan_batch(files: Sequence[Any], *, type: str) -> UploadPlan:
0187:     """Validate one whole batch and decide its single operation.
0188: 
0189:     Raises :class:`InvalidInputError` (400) for anything that must never reach
0190:     the disk — including the mixed batches the old first-file heuristic used to
0191:     mislabel.
0192:     """
0193:     if not files:
0194:         raise json_store.invalid_input("没有收到文件")
0195: 
0196:     if type == "auto":
0197:         explicit: str | None = None
0198:     else:
0199:         if type not in ALLOWED_TYPES:
0200:             raise json_store.invalid_input("未知的资料类型")
0201:         explicit = type
0202: 
0203:     supported = manifest_mod.supported_extensions()
0204:     prepared: list[BatchFile] = []
0205:     for upload in files:
0206:         original = assert_safe_original_name(getattr(upload, "filename", None))
```

L315–L331：

```text
0315: def staging_root(subject_id: str) -> Iterator[Path]:
0316:     """A private, cleaned-up staging directory inside this subject's tree."""
0317:     directory = store.subject_dir(subject_id)
0318:     root = json_store.confined(directory, directory / STAGING_DIR_NAME)
0319:     json_store.make_directory(root)
0320:     try:
0321:         os.chmod(root, 0o700)
0322:     except OSError:  # pragma: no cover - best effort on exotic filesystems
0323:         logger.debug("Could not tighten staging directory mode", exc_info=True)
0324:     slot = root / uuid.uuid4().hex
0325:     json_store.make_directory(slot)
0326:     try:
0327:         yield slot
0328:     finally:
0329:         shutil.rmtree(slot, ignore_errors=True)
0330: 
```

L347–L381：

```text
0347: async def stage_files(
0348:     plan: UploadPlan, staging_dir: Path, *, size_limit: int | None = None
0349: ) -> list[Staged]:
0350:     """Stream every part of the batch into private staging; nothing published.
0351: 
0352:     Memory stays bounded by :data:`WORK_CHUNK` (never ``upload.read()`` with no
0353:     argument, never ``read_bytes()``), the limit is enforced while writing, and
0354:     the digest computed here is the one later compared against the published
0355:     file.
0356:     """
0357:     limit = max_file_size() if size_limit is None else int(size_limit)
0358:     staged: list[Staged] = []
0359:     for entry in plan.files:
0360:         target = Path(staging_dir) / entry.name
0361:         hasher = hashlib.sha256()
0362:         size = 0
0363:         try:
0364:             with open(target, "wb") as handle:
0365:                 while True:
0366:                     chunk = await entry.upload.read(WORK_CHUNK)
0367:                     if not chunk:
0368:                         break
0369:                     size += len(chunk)
0370:                     if size > limit:
0371:                         raise json_store.invalid_input("文件超过允许的大小限制。")
0372:                     hasher.update(chunk)
0373:                     handle.write(chunk)
0374:                 handle.flush()
0375:                 os.fsync(handle.fileno())
0376:         except OSError as exc:
0377:             raise StorageIOError(
0378:                 "上传文件写入临时目录失败。", path=entry.name, cause=exc
0379:             ) from exc
0380:         staged.append(Staged(entry, target, size, hasher.hexdigest()))
0381:     return staged
```

L1029–L1070：

```text
1029: def commit_transcripts(
1030:     *,
1031:     subject_id: str,
1032:     plan: UploadPlan,
1033:     staged: Sequence[Staged],
1034:     transcripts: Sequence[dict],
1035:     staging_dir: Path,
1036: ) -> CommitResult:
1037:     """Publish transcribed audio plus its transcript text, or change nothing."""
1038:     materials_dir = materials_path(subject_id, plan.kb_type, create=True)
1039:     backup_root = Path(staging_dir) / "backup"
1040:     json_store.make_directory(backup_root)
1041:     result = CommitResult("transcribe", plan.kb_type, plan.kb_name, names=plan.names)
1042: 
1043:     with json_store.json_transaction(materials_dir):
1044:         rollback = Rollback()
1045:         try:
1046:             publish_pairs(
1047:                 [(item, materials_dir / item.entry.name) for item in staged],
1048:                 backup_root=backup_root,
1049:                 rollback=rollback,
1050:             )
1051:             for item, transcript in zip(staged, transcripts):
1052:                 target = materials_dir / f"{item.entry.name}{TRANSCRIPT_SUFFIX}"
1053:                 _reject_unsafe_leaf(target)
1054:                 if target.exists():
1055:                     backup = Path(backup_root) / f"text-{target.name}"
1056:                     _atomic_copy(target, backup)
1057:                     rollback.add(
1058:                         f"restore:{target.name}",
1059:                         lambda b=backup, t=target: _atomic_copy(b, t),
1060:                     )
1061:                 else:
1062:                     rollback.add(f"remove:{target.name}", lambda t=target: _unlink(t))
1063:                 _write_text_atomic(target, str(transcript.get("text", "")))
1064:         except BaseException as exc:
1065:             restore_or_fail(rollback, exc)
1066:         return result
1067: 
1068: 
1069: # ---------------------------------------------------------------------------
1070: # Background task wrapper: only a real terminal state publishes "ready"
```
## `deeptutor/subjects/export_bundle.py`

SHA256：`295ef59c214038147ac8f1bf1b33211253122fbc5e28017d8358ec36c2dfdc53`

L70–L72：

```text
0070: _TRANSIENT_PARTS = {".upload-staging", "_report_runs", "_review_pack", "__pycache__"}
0071: _TRANSIENT_NAMES = {".deeptutor.lock", ".progress.json", ".DS_Store"}
```

L307–L334：

```text
0307: def _collect(subject_id: str, paths: Any) -> tuple[dict[str, Any], list[_Source]]:
0308:     """Enumerate the authoritative snapshot (no files are copied here)."""
0309:     subject_dir = store.subject_dir(subject_id)
0310:     public_root = paths.get_public_outputs_root()
0311:     public_dir = json_store.confined(public_root, public_root / "subjects" / subject_dir.name)
0312:     _assert_tree_safe(subject_dir)
0313:     _assert_tree_safe(public_dir)
0314: 
0315:     record = _subject_record(subject_id)
0316:     sources: list[_Source] = []
0317:     seen: set[str] = set()
0318: 
0319:     def add(source: Path, arcname: str, category: str, *, metadata: bool = False) -> None:
0320:         if arcname in seen:
0321:             raise subject_error(ErrorCode.STORAGE_CORRUPT)
0322:         seen.add(arcname)
0323:         _verify_artifact_file(source)
0324:         if metadata:
0325:             projected = _safe_metadata(json_store.read_object(source, default={}))
0326:             payload = json.dumps(projected, ensure_ascii=False, sort_keys=True).encode("utf-8")
0327:             sources.append(_Source(arcname, source, len(payload), hashlib.sha256(payload).hexdigest(), category, payload))
0328:         else:
0329:             size, digest = _sha256(source)
0330:             sources.append(_Source(arcname, source, size, digest, category))
0331: 
0332:     # Learning JSON is *not* excluded by a blanket .json rule: these files are
0333:     # the authoritative learner state.
0334:     for child in sorted(subject_dir.iterdir(), key=lambda item: item.name):
```
## `deeptutor/api/routers/subjects.py`

SHA256：`adae1fb5bfadd9921adec8765e2432b1d8d3b57347afc5ce845da3face9e7816`

L218–L243：

```text
0218: async def upload_subject_knowledge(
0219:     subject_id: str,
0220:     background_tasks: BackgroundTasks,
0221:     files: list[UploadFile] = File(...),
0222:     type: str = Form("auto"),
0223:     _: None = Depends(require_auth),
0224: ):
0225:     """Upload files into this subject's knowledge base (default: textbook).
0226: 
0227:     The whole batch is validated before anything is created, staged privately,
0228:     and only then published: an audio batch is transcribed and published as
0229:     audio + transcripts, a document batch replaces both ``materials/<type>``
0230:     and the KB's ``raw`` copy and reserves the index task.
0231:     """
0232:     _require_subject(subject_id)
0233:     plan = uploads.plan_batch(files, type=type)
0234:     # Acceptance (staging/transcription) is already a subject activity.  A
0235:     # document batch hands this same lease to the queued index worker; an audio
0236:     # batch releases it when transcription/publish finishes.
0237:     lease = subject_operations.acquire_activity(subject_id, kind="upload")
0238:     if plan.operation == "transcribe":
0239:         return await _await_upload_operation(_upload_audio_batch(subject_id, plan), lease)
0240:     return await _upload_document_batch(
0241:         subject_id, plan, background_tasks, lease=lease
0242:     )
```

L245–L291：

```text
0245: async def _upload_audio_batch(subject_id: str, plan: "uploads.UploadPlan") -> dict:
0246:     """Transcribe a whole audio batch, then publish it (P1-16)."""
0247:     from deeptutor.services.asr import transcribe as asr_mod
0248: 
0249:     with uploads.staging_root(subject_id) as staging:
0250:         staged = await uploads.stage_files(plan, staging)
0251:         transcripts: list[dict] = []
0252:         for item in staged:
0253:             result = await asr_mod.transcribe(item.path)
0254:             failure = str(result.get("error") or "")
0255:             if failure:
0256:                 logger.warning(
0257:                     "ASR failed for one upload (%s): %s",
0258:                     result.get("error_kind") or "provider",
0259:                     failure,
0260:                 )
0261:                 raise _asr_error(result)
0262:             text = result.get("text", "")
0263:             if not isinstance(text, str):
0264:                 raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
0265:             try:
0266:                 text.encode("utf-8")
0267:             except UnicodeEncodeError:
0268:                 raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT) from None
0269:             transcripts.append(
0270:                 {
0271:                     "file": item.entry.name,
0272:                     "text": text,
0273:                     "model": str(result.get("model") or ""),
0274:                 }
0275:             )
0276:         committed = await asyncio.to_thread(
0277:             uploads.commit_transcripts,
0278:             subject_id=subject_id,
0279:             plan=plan,
0280:             staged=staged,
0281:             transcripts=transcripts,
0282:             staging_dir=staging,
0283:         )
0284:     return {
0285:         "operation": "transcribe",
0286:         "type": "lecture",
0287:         "files": committed.names,
0288:         "transcripts": transcripts,
0289:         "message": f"ASR 转写完成（{len(transcripts)} 个文件）",
0290:     }
```

L293–L310：

```text
0293: def _asr_error(result: dict) -> Exception:
0294:     """Map an ASR failure onto the fixed C02 exit; the text stays server-side."""
0295:     kind = str(result.get("error_kind") or "")
0296:     code = {
0297:         "timeout": ErrorCode.PROVIDER_TIMEOUT,
0298:         "invalid_output": ErrorCode.INVALID_MODEL_OUTPUT,
0299:         "unconfigured": ErrorCode.PROVIDER_UNAVAILABLE,
0300:         # A local read failure is storage, not the provider: the client must
0301:         # not be told to "retry the model" when the file could not be read.
0302:         "io": ErrorCode.STORAGE_IO,
0303:     }.get(kind, ErrorCode.PROVIDER_UNAVAILABLE)
0304:     return subject_error(code, cause=RuntimeError(str(result.get("error") or "")))
0305: 
0306: 
0307: async def _upload_document_batch(
0308:     subject_id: str,
0309:     plan: "uploads.UploadPlan",
0310:     background_tasks: BackgroundTasks,
```

L325–L367：

```text
0325: async def _await_upload_operation(operation, lease: subject_operations.ActivityLease) -> dict:
0326:     """Keep staging and ownership alive through an in-flight thread on cancel.
0327: 
0328:     A cancelled HTTP request never dispatches its queued background tasks. If
0329:     its commit finishes later, explicitly abort that orphaned reservation before
0330:     releasing the activity lease. Completed source bytes remain authoritative.
0331:     """
0332:     task = asyncio.create_task(operation)
0333: 
0334:     def cancelled(done: asyncio.Task) -> None:
0335:         async def finish() -> None:
0336:             kb_dir = None
0337:             task_id = None
0338:             try:
0339:                 result = done.result()
0340:                 task_id = result.get("task_id")
0341:                 if task_id:
0342:                     kb_dir = uploads.kb_paths(lease.subject_id, result["kb_name"])[0]
0343:                     reservation = uploads.reservation_for(kb_dir) or {}
0344:                     if reservation.get("task_id") == task_id:
0345:                         await asyncio.to_thread(
0346:                             uploads._abort_reserved_task, kb_dir, task_id, reservation, "request_cancelled")
0347:             except BaseException:
0348:                 logger.warning("cancelled upload completion could not be finalized")
0349:             finally:
0350:                 if kb_dir is not None and task_id is not None:
0351:                     uploads.clear_reservation(kb_dir, task_id=task_id)
0352:                 lease.release()
0353: 
0354:         asyncio.create_task(finish())
0355: 
0356:     try:
0357:         result = await asyncio.shield(task)
0358:     except BaseException:
0359:         task.add_done_callback(cancelled)
0360:         raise
0361:     if not lease.detached:
0362:         lease.release()
0363:     return result
0364: 
0365: 
0366: async def _upload_document_batch_inner(
0367:     subject_id: str,
```
## `deeptutor/api/subject_route.py`

SHA256：`c7d58298831a896fc7e2eadcd660b38e1c84c40bd246dfe4074106a869445e9c`

L146–L182：

```text
0146: class SubjectRoute(APIRoute):
0147:     """``APIRoute`` that turns subject/storage/LLM failures into C02 payloads."""
0148: 
0149:     def get_route_handler(self) -> Callable[[Request], Any]:
0150:         original = super().get_route_handler()
0151: 
0152:         async def subject_error_boundary(request: Request) -> Response:
0153:             try:
0154:                 return await original(request)
0155:             except RequestValidationError:
0156:                 # 原生参数校验：保持框架 422。
0157:                 raise
0158:             except HTTPException as exc:
0159:                 # 认证 / 原生 401/403/422 优先保留（含 WWW-Authenticate 等 headers）。
0160:                 if exc.status_code in FRAMEWORK_PRIORITY_STATUSES:
0161:                     raise
0162:                 cause = _business_cause(exc)
0163:                 if cause is None:
0164:                     # 没有明确业务 cause 的历史 HTTPException：仍是框架行为，
0165:                     # 不按 detail 文本或类名猜分类。
0166:                     raise
0167:                 error = map_subject_exception(cause)
0168:                 _log_failure(request, error, cause, wrapped=exc)
0169:                 return JSONResponse(
0170:                     status_code=error.http_status, content=to_http_payload(error)
0171:                 )
0172:             except Exception as exc:  # noqa: BLE001 - C02 统一安全出口
0173:                 error = map_subject_exception(exc)
0174:                 _log_failure(request, error, exc)
0175:                 return JSONResponse(
0176:                     status_code=error.http_status, content=to_http_payload(error)
0177:                 )
0178: 
0179:         return subject_error_boundary
0180: 
0181: 
0182: __all__ = ("CAUSE_CHAIN_DEPTH", "FRAMEWORK_PRIORITY_STATUSES", "SubjectRoute")
```
## `deeptutor/api/main.py`

SHA256：`a7a360ff67d59ad31f42d25b64a7a06a2cf7f0b9fbb070063463bceefefa042b`

L103–L112：

```text
0103: async def lifespan(app: FastAPI):
0104:     """
0105:     Application lifecycle management
0106:     Gracefully handle startup and shutdown events, avoid CancelledError
0107:     """
0108:     # Execute on startup
0109:     logger.info("Application startup")
0110: 
0111:     # Validate configuration consistency
0112:     validate_tool_consistency()
```

L153–L177：

```text
0153:     # Execute on shutdown
0154:     logger.info("Application shutdown")
0155: 
0156:     # Stop cron scheduler
0157:     try:
0158:         from deeptutor.services.cron import get_cron_service
0159: 
0160:         await get_cron_service().stop()
0161:     except Exception as e:
0162:         logger.warning(f"Failed to stop cron service: {e}")
0163: 
0164:     # Close pooled LLM SDK clients so their keep-alive sockets and transports
0165:     # are released deterministically instead of waiting for interpreter GC.
0166:     try:
0167:         from deeptutor.services.llm.provider_factory import close_runtime_provider_pool
0168: 
0169:         await close_runtime_provider_pool()
0170:         logger.info("LLM provider pool closed")
0171:     except Exception as e:
0172:         logger.warning(f"Failed to close LLM provider pool: {e}")
0173: 
0174:     try:
0175:         from deeptutor.core.agentic.client import close_agentic_client_pool
0176: 
0177:         await close_agentic_client_pool()
```

L383–L384：

```text
0383:     subjects.router, prefix="/api/v1/subjects", tags=["subjects"], dependencies=_auth
0384: )
```
## `web/proxy.ts`

SHA256：`21fdea851cc844821be1734f8a87c2a3b832ff2929791862031b3fc9113c12f0`

L42–L59：

```text
0042: export function proxy(req: NextRequest): NextResponse {
0043:   const { pathname, search } = req.nextUrl;
0044: 
0045:   if (isCodexCallbackPath(pathname)) {
0046:     return NextResponse.rewrite(
0047:       new URL(CODEX_CALLBACK_API_PATH + search, API_BASE_URL),
0048:     );
0049:   }
0050: 
0051:   // 1. Bridge the origin gap: forward backend-relative paths to the API server.
0052:   //    This keeps the URL knowledge in one place (the entrypoint + system.json)
0053:   //    rather than baked into the frontend bundle.
0054:   if (isBackendPath(pathname)) {
0055:     return NextResponse.rewrite(new URL(pathname + search, API_BASE_URL));
0056:   }
0057: 
0058:   // 2. Auth gate — multi-user mode only. Disabled by default, and never blocks
0059:   //    auth pages, Next.js internals, or public static assets (see
```

L74–L86：

```text
0074: export const config = {
0075:   // Run on every request except Next.js internals and the favicon. The /api/*
0076:   // and /ws/* paths are explicitly handled above (rewritten to the backend);
0077:   // large knowledge create/upload requests are handled by dedicated App Router
0078:   // endpoints that stream directly to FastAPI. Excluding them here is crucial:
0079:   // merely entering Proxy makes Next clone and cap the multipart body.
0080:   // the browser's /_next/image optimizer requests are excluded here, while the
0081:   // optimizer's loopback fetch for the source image (e.g. /logo.png) is let
0082:   // through the auth gate by isAuthExempt.
0083:   matcher: [
0084:     "/((?!_next/static|_next/image|favicon.ico|api/v1/knowledge/(?:create|[^/]+/upload)(?:/|$)).*)",
0085:   ],
0086: };
```
## `web/lib/streaming-upload-proxy.ts`

SHA256：`887960daa68eb56483b27d4112d28cd4c2ec0b9a9d73c8074833e7e701534f8a`

L42–L72：

```text
0042: export async function forwardBackendUpload(
0043:   request: Request,
0044:   dependencies: UploadProxyDependencies = {},
0045: ): Promise<Response> {
0046:   const apiBaseUrl =
0047:     dependencies.apiBaseUrl ||
0048:     process.env.DEEPTUTOR_API_BASE_URL ||
0049:     DEFAULT_API_BASE_URL;
0050:   const fetchImpl = dependencies.fetchImpl || globalThis.fetch;
0051:   const incomingUrl = new URL(request.url);
0052:   const upstreamUrl = new URL(
0053:     incomingUrl.pathname + incomingUrl.search,
0054:     apiBaseUrl,
0055:   );
0056: 
0057:   const init: StreamingRequestInit = {
0058:     method: request.method,
0059:     headers: forwardedHeaders(request.headers, { request: true }),
0060:     body: request.body,
0061:     signal: request.signal,
0062:     redirect: "manual",
0063:     duplex: "half",
0064:   };
0065:   const upstream = await fetchImpl(upstreamUrl, init);
0066: 
0067:   return new Response(upstream.body, {
0068:     status: upstream.status,
0069:     statusText: upstream.statusText,
0070:     headers: forwardedHeaders(upstream.headers, { request: false }),
0071:   });
0072: }
```
## `web/app/api/v1/knowledge/create/route.ts`

SHA256：`db05aefb97f7b09c840ea47e5ccf6f49eb661aee65de12bf5510febe9431397a`

L1–L8：

```text
0001: import { forwardBackendUpload } from "@/lib/streaming-upload-proxy";
0002: 
0003: export const runtime = "nodejs";
0004: export const dynamic = "force-dynamic";
0005: 
0006: export function POST(request: Request): Promise<Response> {
0007:   return forwardBackendUpload(request);
0008: }
```
## `web/lib/subject-results.ts`

SHA256：`c8dc44508de95c71365a5c1d7fb0bedc13b7aef9788ada8a13f5d8ba32fff78a`

L470–L512：

```text
0470: export async function uploadSubjectMaterialAction(options: {
0471:   request: SubjectRequest;
0472:   subjectId: string;
0473:   files: File[];
0474:   type: string;
0475:   setBusy?: (busy: boolean) => void;
0476:   isCurrent?: () => boolean;
0477:   onError: (message: string) => void;
0478:   onSuccess: (message: string) => void;
0479:   reloadKnowledge?: () => Promise<KnowledgeProjection[]>;
0480: }): Promise<boolean> {
0481:   if (options.files.length === 0) return false;
0482:   const body = buildFormData({ type: options.type });
0483:   for (const file of options.files) body.append("files", file);
0484: 
0485:   const result = await runSubjectAction(
0486:     options,
0487:     async () => {
0488:       const payload = await requestSubjectJson(
0489:         options.request,
0490:         `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/knowledge/upload`,
0491:         { method: "POST", body },
0492:       );
0493:       let record: KnowledgeProjection | undefined;
0494:       if (
0495:         options.reloadKnowledge &&
0496:         stringField(payload, "operation") === "index"
0497:       ) {
0498:         try {
0499:           const rows = await options.reloadKnowledge();
0500:           const kbName = stringField(payload, "kb_name");
0501:           record = rows.find((row) => row.kb_name === kbName);
0502:         } catch {
0503:           // The upload itself succeeded; a status reload failure must not turn
0504:           // it into a false upload failure (or fake a ready index).
0505:         }
0506:       }
0507:       return projectUploadOutcome(payload, record);
0508:     },
0509:   );
0510:   if (!result.ok || options.isCurrent?.() === false) return false;
0511:   options.onSuccess(result.value.message);
0512:   return true;
```

L738–L780：

```text
0738: export async function uploadAudioAction(options: {
0739:   request: SubjectRequest;
0740:   subjectId: string;
0741:   files: File[];
0742:   setBusy?: (busy: boolean) => void;
0743:   isCurrent?: () => boolean;
0744:   onError: (message: string) => void;
0745:   onSuccess: (outcome: AudioUploadOutcome) => void;
0746: }): Promise<boolean> {
0747:   if (options.files.length === 0) return false;
0748:   const body = buildFormData({ type: "lecture" });
0749:   for (const file of options.files) body.append("files", file);
0750: 
0751:   const result = await runSubjectAction(
0752:     options,
0753:     async () => {
0754:       const payload = await requestSubjectJson(
0755:         options.request,
0756:         `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/knowledge/upload`,
0757:         { method: "POST", body },
0758:       );
0759:       const operation = stringField(payload, "operation");
0760:       if (operation !== "transcribe") {
0761:         throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
0762:       }
0763:       const transcripts = transcriptsFrom(payload);
0764:       const text = transcripts
0765:         .map((item) => stringField(item, "text") ?? "")
0766:         .filter((value) => value.length > 0)
0767:         .join("\n\n");
0768:       const message = text
0769:         ? `转写完成（${transcripts.length} 个文件）；转写文本已保存到该科“课堂录音”材料（materials/lecture），并填入下方检测框，不会自动建立索引。`
0770:         : "转写完成，但没有返回文本内容，请检查录音。";
0771:       return { message, text, count: transcripts.length };
0772:     },
0773:   );
0774:   if (!result.ok || options.isCurrent?.() === false) return false;
0775:   options.onSuccess(result.value);
0776:   return true;
0777: }
0778: 
0779: export async function detectExamPointsAction(options: {
0780:   request: SubjectRequest;
```

L89–L100：

```text
0089: function defaultHttpMessage(status: number): string {
0090:   if (status === 401) return "登录状态已失效，请重新登录。";
0091:   if (status === 403) return "没有权限执行此操作。";
0092:   if (status === 404) return "请求的内容不存在或已被删除。";
0093:   if (status === 409) return "当前有操作正在进行，请稍后重试。";
0094:   if (status === 422 || status === 400) return "请求参数无效，请检查后重试。";
0095:   if (status >= 500) return "服务暂时不可用，请稍后重试。";
0096:   return "请求未完成，请稍后重试。";
0097: }
0098: 
0099: /** Project a non-2xx response without ever exposing its raw body. */
0100: export async function readSubjectFailure(
```
## `web/app/(workspace)/subjects/page.tsx`

SHA256：`5474afefa9957975923200179d3a52caf2dad1b12c57358344cd2c980532b9fe`

L105–L125：

```text
0105:   async function uploadFiles(subjectId: string, files: FileList | null, type: string) {
0106:     if (!files || files.length === 0) return;
0107:     await uploadSubjectMaterialAction({
0108:       request: apiFetch,
0109:       isCurrent,
0110:       subjectId,
0111:       files: Array.from(files),
0112:       type,
0113:       setBusy: (value) => setUploading((u) => ({ ...u, [subjectId]: value })),
0114:       onError: setMsg,
0115:       onSuccess: setMsg,
0116:       reloadKnowledge: async () => {
0117:         const knowledgeMap = await load(false);
0118:         return (knowledgeMap[subjectId] ?? []) as KnowledgeProjection[];
0119:       },
0120:     });
0121:   }
0122: 
0123:   async function deleteSubject(id: string) {
0124:     if (!confirm(`删除科目 ${id}？将同时删除其全部数据`)) return;
0125:     await deleteSubjectAction({
```

L187–L200：

```text
0187:                   id={`file-${s.id}`}
0188:                   onChange={(e) => uploadFiles(s.id, e.target.files, "auto")}
0189:                 />
0190:                 <label
0191:                   htmlFor={`file-${s.id}`}
0192:                   className={
0193:                     uploading[s.id] || busy
0194:                       ? "cursor-not-allowed rounded-md bg-emerald-600/60 px-3 py-1 text-sm text-white"
0195:                       : "cursor-pointer rounded-md bg-emerald-600 px-3 py-1 text-sm text-white"
0196:                   }
0197:                 >
0198:                   {uploading[s.id] ? "上传中…" : "上传材料"}
0199:                 </label>
0200:                 <button
```
## `web/app/(workspace)/subjects/[id]/page.tsx`

SHA256：`cd3fa1f246b82175f039934062aba4ab54000e20c7b4cf0018cf6159c799fa5d`

L457–L484：

```text
0457:   async function uploadAudio(files: FileList | null) {
0458:     if (!files || files.length === 0) return;
0459:     setAsrMsg("正在上传录音并转写（ASR）…");
0460:     setAsrError(false);
0461:     await uploadAudioAction({
0462:       request: apiFetch,
0463:       isCurrent,
0464:       subjectId,
0465:       files: Array.from(files),
0466:       setBusy,
0467:       onError: (message) => {
0468:         setAsrError(true);
0469:         setAsrMsg(message);
0470:       },
0471:       onSuccess: (outcome) => {
0472:         setAsrError(false);
0473:         if (outcome.text) {
0474:           setTranscript((prev) => (prev ? prev + "\n\n" + outcome.text : outcome.text));
0475:         }
0476:         setAsrMsg(outcome.message);
0477:       },
0478:     });
0479:   }
0480: 
0481:   async function run() {
0482:     if (!transcript.trim()) return;
0483:     await detectExamPointsAction({
0484:       request: apiFetch,
```
## `web/tests/phase1-42.test.ts`

SHA256：`725c579958f101c0f90661cd339b861cf17a8d8f611289dd1ad4b1c6d8ca1027`

L1–L28：

```text
0001: import assert from "node:assert/strict";
0002: import { readFileSync } from "node:fs";
0003: import path from "node:path";
0004: import test from "node:test";
0005: import ts from "typescript";
0006: 
0007: import {
0008:   EXPORT_SCOPE_NOTE,
0009:   SAFE_BAD_EXPORT_URL,
0010:   SAFE_BAD_RESPONSE,
0011:   SAFE_NETWORK_MESSAGE,
0012:   archiveEntryAction,
0013:   createSubjectAction,
0014:   deleteSubjectAction,
0015:   detectExamPointsAction,
0016:   exportSubjectAction,
0017:   generateReviewPackAction,
0018:   loadSubjectDetail,
0019:   loadSubjectsView,
0020:   recordAttemptAction,
0021:   saveProfileAction,
0022:   uploadAudioAction,
0023:   uploadSubjectMaterialAction,
0024:   type SubjectRequest,
0025: } from "../lib/subject-results";
0026: 
0027: type Reply =
0028:   | { kind: "response"; make: () => Response }
```
## `web/tests/streaming-upload-proxy.test.ts`

SHA256：`4912b91bc805a5cd676b02e250361f19a44404bf6cf3bfa29f2afd73ce3abe4a`

L1–L28：

```text
0001: import test from "node:test";
0002: import assert from "node:assert/strict";
0003: import { forwardBackendUpload } from "../lib/streaming-upload-proxy";
0004: 
0005: type StreamingRequestInit = RequestInit & { duplex: "half" };
0006: 
0007: test("upload proxy streams the original body and preserves the backend response", async () => {
0008:   const request = new Request(
0009:     "http://frontend.test/api/v1/knowledge/create?source=web",
0010:     {
0011:       method: "POST",
0012:       headers: {
0013:         connection: "keep-alive, x-remove-me",
0014:         "content-type": "multipart/form-data; boundary=example",
0015:         cookie: "deeptutor_session=token",
0016:         host: "frontend.test",
0017:         "x-remove-me": "transport-only",
0018:       },
0019:       body: new Blob(["multipart bytes"]).stream(),
0020:       duplex: "half",
0021:     } as StreamingRequestInit,
0022:   );
0023: 
0024:   const response = await forwardBackendUpload(request, {
0025:     apiBaseUrl: "http://127.0.0.1:8123",
0026:     fetchImpl: async (input, init) => {
0027:       assert.equal(
0028:         String(input),
```
## `web/tests/proxy-policy.test.ts`

SHA256：`53701effea7d1ea149db38e35f6b7adc7b4b490074edf2ae850bed68bbde2253`

L1–L20：

```text
0001: import test from "node:test";
0002: import assert from "node:assert/strict";
0003: import { readFileSync } from "node:fs";
0004: import path from "node:path";
0005: import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
0006: import { config as proxyConfig } from "../proxy";
0007: 
0008: // Unit tests for the pure middleware routing policy (web/lib/proxy-policy.ts).
0009: // The policy is deliberately decoupled from `next/server`, so it can be
0010: // exercised here without booting the Next runtime. proxy.ts itself is a thin
0011: // adapter that maps these decisions onto NextResponse.
0012: 
0013: import {
0014:   CODEX_CALLBACK_API_PATH,
0015:   CODEX_CALLBACK_PATH,
0016:   classifyToken,
0017:   isAuthExempt,
0018:   isBackendPath,
0019:   isCodexCallbackPath,
0020: } from "../lib/proxy-policy";
```
## `tests/phase1/test_p1_16.py`

SHA256：`445e929241719536e7a9acf3577a28f1616a14fca2e7cec2c5b6f12bd5449a94`

L1–L34：

```text
0001: """P1-16 行为测试：安全音频保存与 ASR 流式发送（C07/C02）。
0002: 
0003: 目标：恶意文件名/软链接不越界、限额分块、失败不留半批、转写不伪造成功，
0004: ASR 以受控文件流 + 正确 MIME 发送且不把供应商原文回显给客户端。
0005: 
0006: 必证场景（对应卡内清单）：
0007: 
0008: * 绝对路径 / ``..`` / 反斜杠 / 控制字符 / 不可 UTF-8 编码的名字被拒绝，且外部没有新增文件；
0009: * 合法 ``.wav`` / ``.m4a`` / ``.flac`` 正常保存并得到转写文本；
0010: * 恰好限额通过、限额 +1 失败（monkeypatch 小限额，不写真实大文件）；
0011: * 读取中断 / ASR 失败 → 没有假转写成功、没有残留、旧同名文件字节不变；
0012: * ASR multipart 传的是打开的文件流而不是整块 bytes，MIME 与扩展名对应；
0013: * 供应商错误正文与虚构标记不出现在任何 HTTP 响应里；
0014: * 普通文档允许集合没有被音频路径扩大。
0015: """
0016: 
0017: from __future__ import annotations
0018: 
0019: import json
0020: import os
0021: from pathlib import Path
0022: 
0023: import pytest
0024: 
0025: from deeptutor.services.asr import transcribe as transcribe_module
0026: from deeptutor.subjects import json_store, material_manifest, uploads
0027: from deeptutor.utils.document_validator import DocumentValidator
0028: from tests.phase1 import helpers
0029: 
0030: REPO_ROOT = Path(__file__).resolve().parents[2]
0031: ROUTE_PREFIX = helpers.ROUTE_PREFIX
0032: 
0033: FAKE_MARKER = "p1-16-FAKE-PROVIDER-MARKER-4f21c9-DO-NOT-LEAK"
```
## `tests/phase1/test_subject_operations.py`

SHA256：`c12a95126737cce98bc14184f4a072679fb72baa5732b269978f12e115e2a7f9`

L1–L27：

```text
0001: """P1-40: the shared subject activity protocol is a real OS lease."""
0002: 
0003: from __future__ import annotations
0004: 
0005: import asyncio
0006: from io import BytesIO
0007: import json
0008: import os
0009: from pathlib import Path
0010: import subprocess
0011: import sys
0012: import threading
0013: import time
0014: 
0015: import pytest
0016: from starlette.datastructures import UploadFile
0017: 
0018: from deeptutor.api.routers import subjects as subjects_router
0019: from deeptutor.services.pdf import report as report_mod
0020: from deeptutor.services.pdf import report_store
0021: from deeptutor.subjects import export_bundle, store, subject_operations, uploads
0022: from deeptutor.subjects.errors import ErrorCode, SubjectOperationError
0023: from tests.phase1 import helpers
0024: 
0025: 
0026: def _subject(admin_root: Path, label: str = "租约科目") -> helpers.SubjectPaths:
0027:     return helpers.make_subject(admin_root, label)
```
## `web/playwright.phase1.config.ts`

SHA256：`c18798f050efda9b8dbad16aac22c738c2d5b6bc9f55d0a72fdb2c52355ced1a`

L37–L61：

```text
0037: const STAGE = canonical(process.env.S15_EVIDENCE_DIR || path.join(REPO, ".phase1-evidence", "stages", "S15"));
0038: if (!inside(path.join(REPO, ".phase1-evidence"), STAGE)) throw new Error("S15 evidence must stay under .phase1-evidence");
0039: if (fs.existsSync(path.join(STAGE, "report.json")) || fs.existsSync(path.join(STAGE, "closing_manifest.json"))) {
0040:   throw new Error("Sealed S15 evidence: set S15_EVIDENCE_DIR to a fresh directory");
0041: }
0042: const RUN_LABEL = process.env.S15_RUN_LABEL || "good";
0043: if (!/^[a-zA-Z0-9_-]{1,48}$/.test(RUN_LABEL)) throw new Error("Invalid S15_RUN_LABEL");
0044: const PROVIDED_SOURCE = process.env.S15_SOURCE_COPY
0045:   ? canonical(process.env.S15_SOURCE_COPY)
0046:   : null;
0047: const TEMP_BASE = canonical(process.env.S15_TEMP_BASE || os.tmpdir());
0048: if (inside(REPO, TEMP_BASE) || inside(TEMP_BASE, REPO)) throw new Error("S15 temporary base must be outside the repository");
0049: process.env.S15_TEMP_BASE = TEMP_BASE;
0050: function validateSource(source: string): void {
0051:   if (!inside(TEMP_BASE, source) || inside(REPO, source) || inside(source, REPO)) {
0052:     throw new Error("S15_SOURCE_COPY must be a disposable source outside the repository");
0053:   }
0054: }
0055: if (PROVIDED_SOURCE) validateSource(PROVIDED_SOURCE);
0056: const ARTIFACTS = process.env.S15_ARTIFACTS_DIR
0057:   ? canonical(process.env.S15_ARTIFACTS_DIR)
0058:   : path.join(STAGE, "playwright-artifacts");
0059: if (!inside(STAGE, ARTIFACTS)) throw new Error("S15 artifacts must stay under the fresh evidence directory");
0060: 
0061: // Playwright evaluates this config once in the runner and again in each
```

L375–L384：

```text
0375:     if (req.method === "POST" && url.endsWith("/audio/transcriptions")) {
0376:       res.writeHead(200, { "Content-Type": "application/json" });
0377:       res.end(JSON.stringify({ text: "E2E-TRANSCRIPT-B3 课堂录音转写内容，用于考察材料去向。" }));
0378:       return;
0379:     }
0380:     if (req.method === "POST" && url.endsWith("/chat/completions")) {
0381:       let body = {};
0382:       try { body = JSON.parse(raw.toString("utf8")); } catch {}
0383:       const model = body.model || "s15-fake-chat";
0384:       const text = chatText(Array.isArray(body.messages) ? body.messages : []);
```

L551–L566：

```text
0551: const backendScript = supervisorScript("backend", {
0552:   DEEPTUTOR_HOME: SOURCE_ROOT,
0553:   HOME: path.join(RUN_ROOT, "home"),
0554:   XDG_CONFIG_HOME: path.join(RUN_ROOT, "home", ".config"),
0555:   XDG_DATA_HOME: path.join(RUN_ROOT, "home", ".local", "share"),
0556:   XDG_CACHE_HOME: path.join(RUN_ROOT, "home", ".cache"),
0557:   TMPDIR: path.join(RUN_ROOT, "tmp"),
0558:   PYTHONPATH: `${GUARD_DIR}:${SOURCE_ROOT}`,
0559:   S13_ENDPOINT_REGISTRY: GUARD_REGISTRY,
0560:   PYTHONUNBUFFERED: "1",
0561:   PYTHONDONTWRITEBYTECODE: "1",
0562:   BACKEND_PORT: String(BACKEND_PORT),
0563:   AUTH_ENABLED: "false",
0564: }, [path.join(REPO, ".venv", "bin", "python"), path.join(RUN_ROOT, "backend_launcher.py")]);
0565: 
0566: const nextScript = supervisorScript("next", {
```

L683–L700：

```text
0683: export default defineConfig({
0684:   globalTeardown: teardownFile,
0685:   testDir: "./e2e",
0686:   testMatch: "phase1.spec.ts",
0687:   fullyParallel: false,
0688:   workers: 1,
0689:   retries: 0,
0690:   forbidOnly: true,
0691:   timeout: 240_000,
0692:   expect: { timeout: 20_000 },
0693:   outputDir: ARTIFACTS,
0694:   reporter: [
0695:     ["list"],
0696:     ["json", { outputFile: path.join(LOG_DIR, `${RUN_LABEL}-playwright.json`) }],
0697:   ],
0698:   use: {
0699:     ...devices["Desktop Chrome"],
0700:     baseURL: WEB_ORIGIN,
```
## `web/e2e/phase1.spec.ts`

SHA256：`dfda38914d682a4f94ef0ea8dc2769531445ecb581aab8ca90bf28eca4c0bf3e`

L557–L568：

```text
0557: test("B3 browser document index, ASR transcript, and failure recovery", async ({ page, request }) => {
0558:   await guardBrowser(page);
0559:   attachCapture(page);
0560:   const stamp = Date.now().toString(36).slice(-4);
0561:   const docName = `s15-doc-${stamp}.txt`;
0562:   const docMarker = `E2E-B3-DOC-${stamp}`;
0563:   const docText = `${docMarker} 浏览器上传的文档索引标记。真实 multipart 上传与 LlamaIndex 检索。\n`;
0564: 
0565:   await page.goto("/subjects");
0566:   await expect(page.getByText(subjectA.name, { exact: true })).toBeVisible();
0567:   const fileInput = page.locator(`#file-${subjectA.id}`);
0568:   const row = page.locator("div.rounded-xl").filter({ has: fileInput }).first();
```

L611–L653：

```text
0611:   // Audio transcribe: real browser file input + multipart, deterministic STT
0612:   // only at the provider boundary. It must report lecture storage, never index.
0613:   await page.goto(`/subjects/${subjectA.id}`);
0614:   await page.getByRole("button", { name: "期末考点" }).click();
0615:   const card = page.getByText("课堂考点检测", { exact: true }).locator("xpath=..");
0616:   await expect(card).toBeVisible();
0617:   const audioInput = card.locator('input[type=file]');
0618:   const kbBeforeAudio = hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"));
0619:   let failAudio = true;
0620:   await page.route(`**/api/v1/subjects/${subjectA.id}/knowledge/upload`, async (route) => {
0621:     if (failAudio) {
0622:       failAudio = false;
0623:       await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E-FORCED-AUDIO-FAIL" }) });
0624:       return;
0625:     }
0626:     await route.continue();
0627:   });
0628:   const wav = wavBytes();
0629:   await audioInput.setInputFiles({ name: `s15-lecture-${stamp}.wav`, mimeType: "audio/wav", buffer: wav });
0630:   await expect(page.getByText("E2E-FORCED-AUDIO-FAIL", { exact: false })).toBeVisible();
0631:   await expect(card.getByText("上传录音（mp3/m4a/wav）", { exact: true })).toBeVisible();
0632:   expect(await page.getByText(/转写完成/).count()).toBe(0);
0633:   expect(hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"))).toEqual(kbBeforeAudio);
0634:   const audioFailureShot = await screenshot(page, "b3-audio-failure");
0635: 
0636:   await audioInput.setInputFiles({ name: `s15-lecture-${stamp}.wav`, mimeType: "audio/wav", buffer: wav });
0637:   await expect(page.getByText(/转写完成（1 个文件）/)).toBeVisible();
0638:   await expect(page.getByText(/materials\/lecture/)).toBeVisible();
0639:   await expect(page.getByText(/不会自动建立索引/)).toBeVisible();
0640:   const cardText = await card.innerText();
0641:   expect(cardText).not.toMatch(/\bready\b|已索引|图片覆盖|image coverage/i);
0642:   const transcript = card.locator("textarea");
0643:   await expect(transcript).toHaveValue(/E2E-TRANSCRIPT-B3/);
0644:   expect(hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"))).toEqual(kbBeforeAudio);
0645: 
0646:   const lectureDir = path.join(subjectDir(subjectA.id), "materials", "lecture");
0647:   const lectureFiles = fs.readdirSync(lectureDir).sort();
0648:   expect(lectureFiles.some((name) => name === `s15-lecture-${stamp}.wav`)).toBe(true);
0649:   const transcriptFile = lectureFiles.find((name) => name.startsWith(`s15-lecture-${stamp}.wav`) && name.endsWith(".txt"));
0650:   expect(transcriptFile).toBeTruthy();
0651:   expect(fs.readFileSync(path.join(lectureDir, transcriptFile!), "utf-8")).toContain("E2E-TRANSCRIPT-B3");
0652:   const audioShot = await screenshot(page, "b3-audio-success");
```
## `scripts/run_tests_isolated.py`

SHA256：`36b00721c2f87e87461bb846bb662258a8cca4a560e1045c89e28cc8531495c9`

L1–L30：

```text
0001: #!/usr/bin/env python3
0002: """Run pytest with disposable settings, credentials and a Python network guard.
0003: 
0004: Usage: .venv/bin/python scripts/run_tests_isolated.py -q tests/phase1
0005: Without arguments, pytest uses both configured testpaths. No real model/config
0006: is copied into the disposable home. This does not claim OS sandbox isolation.
0007: """
0008: 
0009: from __future__ import annotations
0010: 
0011: import os
0012: from pathlib import Path
0013: import signal
0014: import subprocess
0015: import sys
0016: import tempfile
0017: 
0018: REPO = Path(__file__).resolve().parents[1]
0019: sys.path.insert(0, str(REPO))
0020: 
0021: from scripts.phase1_verify import BOOTSTRAP_CODE, NETWORK_GUARD, clean_env  # noqa: E402
0022: 
0023: 
0024: def main(args: list[str]) -> int:
0025:     with tempfile.TemporaryDirectory(prefix="selflearn-tests-") as root_value:
0026:         root = Path(root_value)
0027:         env = clean_env(root)
0028:         env["DEEPTUTOR_HOME"] = str(root / "runtime")
0029:         Path(env["DEEPTUTOR_HOME"]).mkdir()
0030:         guard = root / "guard"
```
## `scripts/phase1_snapshot.py`

SHA256：`7dcaf3d0228a12f057698205f7b8152eaaa84c489ed8ce36508ed794c3ed7c7c`

L668–L679：

```text
0668: def protect_data(root: Path) -> dict:
0669:     roots = {name: protect_one(root, rel) for name, rel in PROTECTED_DATA_ROOTS.items()}
0670:     supplementary = {
0671:         name: protect_one(root, rel) for name, rel in SUPPLEMENTARY_DATA_ROOTS.items()
0672:     }
0673:     core = json.dumps(roots, sort_keys=True, separators=(",", ":")).encode("utf-8")
0674:     return {
0675:         "schema_version": SCHEMA_VERSION,
0676:         "card_id": CARD_ID,
0677:         "captured_at": now_utc(),
0678:         "root": str(root),
0679:         "protection_id": f"{CARD_ID}-data-{hashlib.sha256(core).hexdigest()[:16]}",
```

L794–L809：

```text
0794: def compare(before: dict, after: dict, allowed: list[str]) -> dict:
0795:     if before.get("root") != after.get("root"):
0796:         raise ValueError("cannot compare different repository roots")
0797:     b_files = {p: v for p, v in before["monitored_files"].items() if not is_excluded(p)}
0798:     a_files = {p: v for p, v in after["monitored_files"].items() if not is_excluded(p)}
0799:     _validate_entries(b_files)
0800:     _validate_entries(a_files)
0801:     b_dirs = {p for p in before["monitored_dirs"] if not is_excluded(p)}
0802:     a_dirs = {p for p in after["monitored_dirs"] if not is_excluded(p)}
0803: 
0804:     changes: list[dict] = []
0805:     for rel in sorted(set(b_files) | set(a_files)):
0806:         b = b_files.get(rel)
0807:         a = a_files.get(rel)
0808:         if b is not None and a is not None and _same_entry(b, a):
0809:             continue
```

# S05 已探索文件清单 + 关键片段

探索日期：2026-10-14；工作目录：`/home/albert/selflearn/selflearn`；HEAD：`9723f953cb6ca56f13603f76c5d07e1e2f1f4473`。
对应最新签收：`.phase1-evidence/reviews/S04-final/review.json`，当前指针：`.phase1-evidence/stages/S04/review.json`。授权和具体完成门见 `START_S05.txt`；此包只替代重复定位，不代替行为测试。
以下是已探索的局部符号/行段，不表示全仓库、真实数据或provider已检查。所有片段按当前文件原样抽取，SHA256对应整文件；hash未变可复用，变动时只补读差异及必要上下文，不能恢复旧hash。

## 已确认的问题与接口

- 当前upload只按首文件分类；ASR原名直写、无界read、MIME固定audio/mpeg且错误回显；文档copy只有raw不存在时才执行。
- 旧ready可能穿透重传，documents初始化0；全局后台函数已有正确base_dir，但会catch异常并保存原始progress，subject须安全投影并验证真实终态。
- pipeline守卫已存在，应先验证，不重写引擎。排队到worker开始有空窗；超时后thread仍活，任务error不能解除源保护。
- embedding首次调用会各自建立_thread_guard，是P30目标；batch_delay=0现有post仍串行，应保持。
- 新manifest只存relative path/size/hash。staging/backup不能落在raw，目录递归收集会将受支持后缀的备份也索引。
- S04协调者补修的UTF-8字符串校验和测试必须保持；S03 strict path、fork锁和原子JSON接口只读复用。

## 文件hash与探索范围

| 路径 | SHA256 | 已探索范围 / 用途 |
|---|---|---|
| `deeptutor/api/routers/subjects.py` | `386ac975bc998b6fbaeea16ad7ae24feae1b3ee7da9ca43ffb8aa2badb695a63` | L50–L68, L160–L168, L184–L192, L206–L219, L232–L245, L270–L280, L286–L303, L306–L313；P16/17/18/19：完整batch、音频保存、旧raw不覆盖、documents=0、状态投影 |
| `deeptutor/services/asr/transcribe.py` | `18400e0bef1cab389a80046153ec78415bf7529463c4ef9d400bb527716c0f33` | L23–L34, L50–L81；P16：STT配置来源不变；当前整文件read_bytes、固定MIME与原始错误需修 |
| `deeptutor/services/embedding/client.py` | `9033268ebf0735247cabf0ef58e91e7111a468df3b306675c2eabfdb0ab4211e` | L45–L78, L159–L165；P30：首次guard竞态、跨loop互斥、现有post节流 |
| `deeptutor/services/rag/pipelines/llamaindex/pipeline.py` | `8740175c972e6dbc43d35c008b85773ae098799cffd0761754c305e1f4716c75` | L41–L46, L61–L87, L114–L137, L143–L164；P29：当前600/5守卫；thread marker生命周期与显式callback静默 |
| `deeptutor/utils/document_validator.py` | `006920820ecaa0aa81ebe9f42f66090f9a0e1e2f91322268d5df85ae75997c49` | L15–L17, L87–L101；只读：200MiB与安全规范化；它会剥路径，subject须先拒绝恶意原名 |
| `deeptutor/services/rag/file_routing.py` | `79e909918c29eaa23eb03260256d2a7382065bd3b1baddabdf6682dbc7aea858` | L316–L342；只读：真正索引扩展及递归枚举；symlink须在subject边界另外约束 |
| `deeptutor/api/routers/knowledge.py` | `bab000ce5935ca280c0eda96b994c6cabae3942835fb590fd535f67f96771276` | L206–L211, L460–L472, L490–L498, L889–L901, L2739–L2754；只读：任务ID/queue helper；通用保存失败删除先前目标；后台错误会写raw诊断 |
| `deeptutor/knowledge/manager.py` | `e03433263d655071812ceba5d88338d88246e362041bbc68e7e2b8e7abb32f8c` | L503–L529；只读：get_kb_entry/status可投影，list会刷新并自动注册/删除，不能作无副作用GET |
| `deeptutor/knowledge/initializer.py` | `c2c7fffbae97bc94ba6188ddab42ac2464da9c9dc38591c67060d536086d5329` | L127–L139；只读：create_directory_structure有metadata/注册副作用；先预检后调用 |
| `deeptutor/api/utils/task_id_manager.py` | `8534bbf8d0a269f5d2eac77530f7ce3cac6fdca714927de70e1d8f63a5822a38` | L66–L83；只读：terminal task状态不证明线程已退出；新测试自行还原singleton |
| `deeptutor/services/rag/kb_paths.py` | `f37f0dd66464a82853ce10255e5bf8a34340ab0ff18f1dee28a77b51ee014a8a` | L24–L34；只读：linked库可能返回external_path；subject写入口不能逃逸 |
| `deeptutor/knowledge/naming.py` | `208c8d349368938218712321afe4af14ea123cb8fe3a5a08cce379717da9afc1` | L17–L30；只读：KB命名；原参数合法性/作用域仍须调用方检查 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | L467–L474, L501–L521；只读：record merge保留未知字段；strict subject目录接口；GET不要误用会mkdir的helper |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | L182–L207, L650–L673；只读S03接口：confined拒绝symlink，transaction为同步线程/进程锁，原子对象读写可用 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | L103–L110, L300–L315；只读C02：错误表/SubjectOperationError；typed错误由SubjectRoute投影 |
| `tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | L28–L40, L73–L76；只读：显式隔离fixture；p1_subjects键是标签，路径取subject_id |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | L551–L564, L805–L815；只读：SubjectPaths及FakeSTT接口；stub不证明ASR流式wire，另写假httpx transport |
| `tests/services/embedding/test_client_runtime.py` | `1d2096d8e6d7e0fe4ca8e5b292fd62ec4c22d99d3daa09a0daa4f521e6109140` | L27–L37；只读：现有假adapter；P30必须回跑此文件 |
| `deeptutor/knowledge/progress_tracker.py` | `789a383cebd89ba52349acdee4c957e81868eed67ed5efec0b0c5075692f3732` | ProgressTracker/ProgressStage；已探索任务进度与完成/错误的投影接口 |
| `deeptutor/api/subject_route.py` | `c7d58298831a896fc7e2eadcd660b38e1c84c40bd246dfe4074106a869445e9c` | S04已验收统一错误出口（read-only），未知普通HTTPException兼容行为保留 |
| `.phase1-evidence/stages/S01/rework01/run_regression_tmp_home.py` | `c40d69f6b3c4309da47bc2f026f8ed8c5413d0d1a75abcf8e05249d58ec17b59` | 跨目录测试启动前设置tmp home、默认设置与去凭据；只读复用 |

## 计划新增（当前不存在）

`deeptutor/subjects/uploads.py`、`deeptutor/subjects/material_manifest.py`；`tests/phase1/test_p1_16.py`、`test_p1_17.py`、`test_p1_18.py`、`test_p1_19.py`、`test_p1_29.py`、`test_p1_30.py`。新建接口保持小而直接，复用上表基础，不为此增加框架。

## 原样关键片段

### `deeptutor/api/routers/subjects.py`

P16/17/18/19：完整batch、音频保存、旧raw不覆盖、documents=0、状态投影

L50–L68（原样）：
```python

#: Extension → knowledge type. Uploads without an explicit ``type`` are
#: routed by extension; everything else defaults to ``textbook``.
TYPE_BY_EXTENSION = {
    ".pdf": "textbook",
    ".epub": "textbook",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".png": "board",
    ".jpg": "board",
    ".jpeg": "board",
    ".webp": "board",
    ".mp3": "lecture",
    ".m4a": "lecture",
    ".wav": "lecture",
    ".docx": "assignment",
    ".doc": "assignment",
    ".md": "assignment",
    ".txt": "assignment",
```

L160–L168（原样）：
```python
@router.get("/{subject_id}/knowledge")
async def list_subject_knowledge(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    manager = _kb_manager(subject_id)
    out = []
    for record in store.load_knowledge_records(subject_id):
        status = manager.get_kb_status(record["kb_name"]) or {}
        out.append({**record, "status": status})
    return {"knowledge": out}
```

L184–L192（原样）：
```python
    if type == "auto":
        # Route by extension; default to textbook.
        first = files[0].filename or ""
        ext = Path(first).suffix.lower()
        kb_type = TYPE_BY_EXTENSION.get(ext, "textbook")
    else:
        if type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown type '{type}'")
        kb_type = type
```

L206–L219（原样）：
```python
    # ---- Lecture audio: bypass the document whitelist, run ASR ----
    _AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".amr", ".wma"}
    if kb_type == "lecture" and any(
        Path((f.filename or "")).suffix.lower() in _AUDIO_EXTS for f in files
    ):
        from deeptutor.services.asr import transcribe as asr_mod

        saved, transcripts = [], []
        for f in files:
            name = f.filename or "lecture"
            contents = await f.read()
            (materials / name).write_bytes(contents)
            saved.append(name)
            result = await asr_mod.transcribe(materials / name)
```

L232–L245（原样）：
```python
    saved, _ = await _save_uploaded_files_off_loop(
        files, materials, allowed_extensions=None, rel_paths=None
    )

    from pathlib import Path as _Path
    import shutil

    kb_raw_dir = _Path(base_dir) / kb_name / "raw"
    kb_raw_dir.mkdir(parents=True, exist_ok=True)
    for name in saved:
        src_file = _Path(materials) / name
        dst = kb_raw_dir / name
        if src_file.exists() and not dst.exists():
            shutil.copy2(src_file, dst)
```

L270–L280（原样）：
```python
            "kb_id": store.new_kb_id(),
            "type": kb_type,
            "documents": 0,
            "created_at": manager.config.get("knowledge_bases", {})
            .get(kb_name, {})
            .get("created_at"),
        }
        store.upsert_knowledge_record(subject_id, record)
        background_tasks.add_task(run_initialization_task, initializer, task_id)
    else:
        task_id = _build_unique_task_id("subject_kb_add", kb_name)
```

L286–L303（原样）：
```python
        if current.get("status") in ("error", "failed", "initializing"):
            manager.update_kb_status(
                name=kb_name,
                status="initializing",
                progress={"stage": "reindexing", "message": "Re-indexing subject KB...", "percent": 0},
            )
        # Simplest robust path: rebuild the KB with the new file set.
        background_tasks.add_task(
            run_reindex_task, kb_name, str(base_dir), task_id, ""
        )

    return {
        "message": f"Uploaded {len(saved)} file(s) to subject KB '{kb_name}' (type={kb_type})",
        "kb_name": kb_name,
        "type": kb_type,
        "files": saved,
        "task_id": task_id,
    }
```

L306–L313（原样）：
```python
@router.get("/{subject_id}/knowledge/{kb_name}/status")
async def subject_kb_status(subject_id: str, kb_name: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    manager = _kb_manager(subject_id)
    status = manager.get_kb_status(kb_name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"KB '{kb_name}' not found")
    return {"kb_name": kb_name, **status}
```

### `deeptutor/services/asr/transcribe.py`

P16：STT配置来源不变；当前整文件read_bytes、固定MIME与原始错误需修

L23–L34（原样）：
```python
def _stt_config() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) from the active STT profile."""
    from deeptutor.services.config.model_catalog import get_model_catalog_service
    from deeptutor.services.config.provider_runtime import _active_profile_and_model

    service = get_model_catalog_service()
    catalog = service.load()
    profile, model = _active_profile_and_model(catalog, service, "stt")
    api_key = str((profile or {}).get("api_key") or "")
    base_url = str((profile or {}).get("base_url") or DEFAULT_STT_BASE).rstrip("/")
    model_name = str((model or {}).get("model") or DEFAULT_STT_MODEL)
    return base_url, api_key, model_name
```

L50–L81（原样）：
```python
        }
    url = f"{base_url}/audio/transcriptions"
    files = {"file": (audio_path.name, audio_path.read_bytes(), "audio/mpeg")}
    data = {"model": model_name, "language": language, "response_format": "text"}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
        if resp.status_code != 200:
            return {
                "text": "",
                "model": model_name,
                "base_url": base_url,
                "error": f"ASR 请求失败 ({resp.status_code}): {resp.text[:200]}",
            }
        text = resp.text.strip()
        # Some endpoints wrap in JSON {"text": ...}
        if text.startswith("{"):
            try:
                import json as _json

                text = str(_json.loads(text).get("text", text))
            except Exception:
                pass
        return {"text": text, "model": model_name, "base_url": base_url, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {
            "text": "",
            "model": model_name,
            "base_url": base_url,
            "error": f"ASR 调用异常：{exc}",
        }
```

### `deeptutor/services/embedding/client.py`

P30：首次guard竞态、跨loop互斥、现有post节流

L45–L78（原样）：
```python
    _spacing_lock: Any = None
    _last_request_monotonic: float = 0.0
    _thread_guard: Any = None

    @classmethod
    def _global_spacing_lock(cls):
        import threading

        if cls._spacing_lock is None:
            cls._thread_guard = threading.Lock()
            with cls._thread_guard:
                if cls._spacing_lock is None:
                    from threading import Lock as _TLock

                    cls._spacing_lock = _TLock()
        return cls._spacing_lock

    @staticmethod
    @asynccontextmanager
    async def _hold_spacing_lock():
        """Acquire the cross-thread lock without blocking the current loop."""
        import asyncio

        lock = EmbeddingClient._global_spacing_lock()
        while not lock.acquire(blocking=False):
            await asyncio.sleep(0.05)
        try:
            yield
        finally:
            lock.release()

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or get_embedding_config()
        self.logger = logging.getLogger(__name__)
```

L159–L165（原样）：
```python
                async with EmbeddingClient._hold_spacing_lock():
                    if batch_delay > 0:
                        elapsed = _mono() - EmbeddingClient._last_request_monotonic
                        if elapsed < batch_delay:
                            await asyncio.sleep(batch_delay - elapsed)
                    EmbeddingClient._last_request_monotonic = _mono()
                    response = await self.adapter.embed(request)
```

### `deeptutor/services/rag/pipelines/llamaindex/pipeline.py`

P29：当前600/5守卫；thread marker生命周期与显式callback静默

L41–L46（原样）：
```python
_INDEX_STALL_TIMEOUT_SECONDS = 600.0
# How often the stall guard checks the progress heartbeat.
_INDEX_STALL_POLL_SECONDS = 5.0
_INDEX_WORKERS: dict[str, threading.Event] = {}
_INDEX_WORKERS_LOCK = threading.Lock()
```

L61–L87（原样）：
```python
def _ensure_index_worker_available(key: str) -> None:
    with _INDEX_WORKERS_LOCK:
        marker = _INDEX_WORKERS.get(key)
        if marker is not None and not marker.is_set():
            raise _worker_busy_error()


def _claim_index_worker(key: str | None) -> threading.Event | None:
    if not key:
        return None
    event = threading.Event()
    with _INDEX_WORKERS_LOCK:
        existing = _INDEX_WORKERS.get(key)
        if existing is not None and not existing.is_set():
            raise _worker_busy_error()
        _INDEX_WORKERS[key] = event
    return event


def _release_index_worker(key: str | None, marker: threading.Event | None) -> None:
    if not key or marker is None:
        return
    marker.set()
    with _INDEX_WORKERS_LOCK:
        if _INDEX_WORKERS.get(key) is marker:
            _INDEX_WORKERS.pop(key, None)
```

L114–L137（原样）：
```python
    worker_marker = _claim_index_worker(worker_key)
    progress_live = threading.Event()
    progress_live.set()
    last_progress = {"at": time.monotonic()}

    def _heartbeat(*args: Any, **kwargs: Any) -> None:
        if not progress_live.is_set():
            return
        last_progress["at"] = time.monotonic()
        if progress_callback is not None:
            progress_callback(*args, **kwargs)

    def _work() -> Any:
        try:
            return fn()
        finally:
            _release_index_worker(worker_key, worker_marker)

    set_progress_callback(_heartbeat)
    try:
        future = asyncio.get_running_loop().run_in_executor(
            None, contextvars.copy_context().run, _work
        )
    except BaseException:
```

L143–L164（原样）：
```python
        # The stalled thread may finish after we raise; retrieve its exception
        # so it is not reported as "exception was never retrieved".
        if not fut.cancelled():
            fut.exception()

    try:
        while True:
            done, _ = await asyncio.wait({future}, timeout=_INDEX_STALL_POLL_SECONDS)
            if done:
                return future.result()
            stalled_for = time.monotonic() - last_progress["at"]
            if stalled_for > stall_timeout:
                raise IndexingStallError(
                    f"Indexing made no progress for {stalled_for:.0f}s while "
                    "embedding documents. Check the embedding endpoint; wait "
                    "for the worker to finish or restart DeepTutor before retrying."
                )
    finally:
        progress_live.clear()
        if not future.done():
            future.add_done_callback(_consume_terminal_exception)
```

### `deeptutor/utils/document_validator.py`

只读：200MiB与安全规范化；它会剥路径，subject须先拒绝恶意原名

L15–L17（原样）：
```python

    # Maximum file size in bytes (200MB), applied uniformly to every format.
    MAX_FILE_SIZE: ClassVar[int] = 200 * 1024 * 1024
```

L87–L101（原样）：
```python
        safe_name = normalized_filename.replace("\\", "/").rsplit("/", 1)[-1]
        # Remove null bytes and other control characters
        safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name)
        # Replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", safe_name)
        stem, ext = os.path.splitext(safe_name)
        ext = ext.lower()
        safe_name = f"{stem}{ext}"

        if not safe_name or safe_name in (".", "..") or safe_name.strip("_") == "":
            raise ValueError("Invalid filename")

        # Check file extension
        exts_to_check = allowed_extensions or DocumentValidator.ALLOWED_EXTENSIONS
        if ext not in exts_to_check:
```

### `deeptutor/services/rag/file_routing.py`

只读：真正索引扩展及递归枚举；symlink须在subject边界另外约束

L316–L342（原样）：
```python
    def get_supported_extensions(cls) -> set[str]:
        """Get the set of all supported file extensions."""
        return cls.PARSER_EXTENSIONS | cls.TEXT_EXTENSIONS | cls.IMAGE_EXTENSIONS

    @classmethod
    def has_supported_extension(cls, file_path: str | Path) -> bool:
        """Return True when ``file_path`` has a supported extension.

        The check is case-insensitive so files such as ``Report.PDF`` are
        discovered consistently across upload, CLI, folder sync, and reindex.
        """
        return Path(file_path).suffix.lower() in cls.get_supported_extensions()

    @classmethod
    def collect_supported_files(cls, directory: str | Path, recursive: bool = False) -> list[Path]:
        """Collect supported files from a directory with case-insensitive suffix matching."""
        root = Path(directory)
        if not root.exists() or not root.is_dir():
            return []

        paths = root.rglob("*") if recursive else root.iterdir()
        return sorted(
            (path for path in paths if path.is_file() and cls.has_supported_extension(path)),
            key=lambda path: str(path).lower(),
        )

    @classmethod
```

### `deeptutor/api/routers/knowledge.py`

只读：任务ID/queue helper；通用保存失败删除先前目标；后台错误会写raw诊断

L206–L211（原样）：
```python
def _build_unique_task_id(task_type: str, task_key_prefix: str) -> str:
    task_manager = TaskIDManager.get_instance()
    task_key = f"{task_key_prefix}_{datetime.now().isoformat()}_{uuid4().hex[:8]}"
    return task_manager.generate_task_id(task_type, task_key)
```

L460–L472（原样）：
```python
                raise HTTPException(status_code=400, detail=error_message) from e
    except Exception:
        for written_path in written_file_paths:
            if written_path.exists():
                try:
                    os.unlink(written_path)
                except OSError:
                    pass
        raise

    return uploaded_files, uploaded_file_paths
```

L490–L498（原样）：
```python
    """
    return await asyncio.to_thread(
        _save_uploaded_files,
        files,
        target_dir,
        allowed_extensions=allowed_extensions,
        kb_name=kb_name,
        rel_paths=rel_paths,
    )
```

L889–L901（原样）：
```python
                    "message": f"Initialization failed: {error_msg}",
                    "percent": 0,
                    "error": error_msg,
                    **failure_metadata,
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            if initializer.progress_tracker:
                initializer.progress_tracker.update(
                    ProgressStage.ERROR,
                    f"Initialization failed: {error_msg}",
```

L2739–L2754（原样）：
```python
            task_manager.update_task_status(task_id, "completed")
            task_stream_manager.emit_complete(task_id, f"Re-index of '{kb_name}' complete")
        except Exception as e:
            import traceback as _tb

            error_msg = str(e)
            trace = _tb.format_exc()
            failure_metadata = _exception_failure_metadata(e)
            _task_log(task_id, f"Re-index failed: {error_msg}", level="error")
            _server_task_trace(task_id, trace)
            task_manager.update_task_status(task_id, "error", error=error_msg)
            try:
                ProgressTracker(kb_name, Path(base_dir)).update(
                    ProgressStage.ERROR,
                    f"Re-index failed: {error_msg}",
                    error=error_msg,
```

### `deeptutor/knowledge/manager.py`

只读：get_kb_entry/status可投影，list会刷新并自动注册/删除，不能作无副作用GET

L503–L529（原样）：
```python
    def get_kb_status(self, name: str) -> dict | None:
        """Get status and progress for a knowledge base."""
        self.config = self._load_config()
        kb_config = self.config.get("knowledge_bases", {}).get(name)
        if not kb_config:
            return None
        return {
            "status": kb_config.get("status", "unknown"),
            "progress": kb_config.get("progress"),
            "updated_at": kb_config.get("updated_at"),
        }

    def list_knowledge_bases(self) -> list[str]:
        """List all available knowledge bases.

        This method:
        1. Loads registered KBs from kb_config.json
        2. Drops registered entries whose on-disk directory no longer exists
           (orphans from failed inits or manual ``rm -rf`` of a KB folder).
        3. Scans the directory for existing KBs not yet registered
        4. Auto-registers discovered KBs with valid raw/index structure
        """
        # Always reload config from file to ensure we have the latest data
        self.config = self._load_config()

        config_kbs = self.config.get("knowledge_bases", {})
        kb_list: set[str] = set()
```

### `deeptutor/knowledge/initializer.py`

只读：create_directory_structure有metadata/注册副作用；先预检后调用

L127–L139（原样）：
```python
        metadata = {
            "name": self.kb_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": f"Knowledge base: {self.kb_name}",
            "version": "1.0",
            "rag_provider": self.rag_provider,
            "needs_reindex": False,
        }

        atomic_write_json(self.kb_dir / "metadata.json", metadata)

        self._register_to_config()
```

### `deeptutor/api/utils/task_id_manager.py`

只读：terminal task状态不证明线程已退出；新测试自行还原singleton

L66–L83（原样）：
```python
    def get_task_id(self, task_key: str) -> str | None:
        """Get task ID"""
        with self._lock:
            return self._task_ids.get(task_key)

    def update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task status"""
        with self._lock:
            if task_id in self._task_metadata:
                self._task_metadata[task_id]["status"] = status
                self._task_metadata[task_id].update(kwargs)
                if status in ["completed", "error", "cancelled"]:
                    self._task_metadata[task_id]["finished_at"] = datetime.now().isoformat()

    def get_task_metadata(self, task_id: str) -> dict | None:
        """Get task metadata"""
        with self._lock:
            return self._task_metadata.get(task_id, {}).copy()
```

### `deeptutor/services/rag/kb_paths.py`

只读：linked库可能返回external_path；subject写入口不能逃逸

L24–L34（原样）：
```python
def resolve_kb_dir(kb_base_dir: str | Path, kb_name: str) -> Path:
    """Return the directory holding ``kb_name``'s index.

    For a linked KB this is the user's external folder; for every other KB it
    is the conventional ``<kb_base_dir>/<kb_name>``.
    """
    base = Path(kb_base_dir)
    external = _external_path(base, kb_name)
    if external:
        return Path(external).expanduser()
    return base / kb_name
```

### `deeptutor/knowledge/naming.py`

只读：KB命名；原参数合法性/作用域仍须调用方检查

L17–L30（原样）：
```python
    common punctuation, but must not contain filesystem or URL-reserved
    separators that would break KB directories or API route paths.
    """
    normalized = unicodedata.normalize("NFC", str(name or "")).strip()
    if not normalized:
        raise ValueError("Knowledge base name is required")
    if normalized in {".", ".."}:
        raise ValueError("Knowledge base name cannot be '.' or '..'")
    if len(normalized) > _MAX_KB_NAME_LENGTH:
        raise ValueError(
            f"Knowledge base name is too long; maximum length is {_MAX_KB_NAME_LENGTH}"
        )
    if _CONTROL_CHARS.search(normalized):
        raise ValueError("Knowledge base name cannot contain control characters")
```

### `deeptutor/subjects/store.py`

只读：record merge保留未知字段；strict subject目录接口；GET不要误用会mkdir的helper

L467–L474（原样）：
```python
def upsert_knowledge_record(subject_id: str, record: dict) -> None:
    """Insert or update one KB record under the subject lock.

    An update **merges** into the matching record, so fields the caller did not
    supply (including unknown historical ones) survive; only the supplied keys
    are overwritten. Other records are left as they are.
    """
    if not isinstance(record, dict):
```

L501–L521（原样）：
```python
def subject_kb_base_dir(subject_id: str) -> Path:
    """LlamaIndex base dir for a subject's knowledge bases.

    The directory is confined **before** it is created: a ``knowledge_bases``
    symlink pointing outside the subject is refused rather than mkdir'd
    through.
    """
    directory = subject_dir(subject_id)
    sub = json_store.confined(directory, directory / "knowledge_bases")
    json_store.make_directory(sub)
    return sub


def materials_dir(subject_id: str, kb_type: str) -> Path:
    """``materials/<type>`` for one subject; *kb_type* must be one segment."""
    segment = json_store.safe_segment(kb_type, what="材料类型")
    directory = subject_dir(subject_id)
    base = json_store.confined(directory, directory / "materials")
    sub = json_store.confined(base, base / segment)
    json_store.make_directory(sub)
    return sub
```

### `deeptutor/subjects/json_store.py`

只读S03接口：confined拒绝symlink，transaction为同步线程/进程锁，原子对象读写可用

L182–L207（原样）：
```python
def confined(root: Path, path: Path) -> Path:
    """Return *path* after proving it stays inside *root* without symlinks.

    Checks the root, every component below it, and the final resolved location.
    Nothing is created or opened here — callers run this *before* touching the
    target, so a rejected path is never read, mkdir'd or locked.
    """
    root = ensure_trusted_root(root)
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise StorageIOError(_ESCAPE_MESSAGE, path=path.name) from None

    resolved_root = root.resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise StorageIOError(_SYMLINK_MESSAGE, path=path.name)

    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise StorageIOError(_ESCAPE_MESSAGE, path=path.name)
    return path
```

L650–L673（原样）：
```python
    def path(self, name: str) -> Path:
        """A confined path for *name* inside this transaction's directory."""
        root = self._current_root()
        return confined(root, root / safe_segment(name))

    # -- reads ----------------------------------------------------------------
    def read_list(self, path: Path) -> list[dict]:
        return read_list(confined(self._current_root(), Path(path)))

    def read_object(self, path: Path, *, default: dict) -> dict:
        return read_object(confined(self._current_root(), Path(path)), default=default)

    # -- writes ---------------------------------------------------------------
    def write_list(self, path: Path, records: list[dict]) -> None:
        path = confined(self._current_root(), Path(path))
        _require_records(records)
        _commit(path, list(records))

    def write_object(self, path: Path, payload: dict) -> None:
        path = confined(self._current_root(), Path(path))
        if not isinstance(payload, dict):
            raise UpdateCallbackError("对象文档必须是对象")
        _commit(path, dict(payload))
```

### `deeptutor/subjects/errors.py`

只读C02：错误表/SubjectOperationError；typed错误由SubjectRoute投影

L103–L110（原样）：
```python
    ErrorCode.KB_BUSY: _spec(
        ErrorCode.KB_BUSY, 409, True, "该知识库已有任务进行中，请稍后重试。"
    ),
    ErrorCode.MATERIAL_OUT_OF_SYNC: _spec(
        ErrorCode.MATERIAL_OUT_OF_SYNC, 409, True, "资料与索引源不一致，需要重新建立索引。"
    ),
    ErrorCode.STORAGE_CORRUPT: _spec(
        ErrorCode.STORAGE_CORRUPT, 500, False, "本地数据文件已损坏，未做任何修改。"
```

L300–L315（原样）：
```python


def subject_error(code: ErrorCode | str, *, cause: BaseException | None = None) -> SubjectOperationError:
    """用 C02 表中的固定投影构造错误（消息/状态/retryable 都来自表）。"""
    resolved = ErrorCode(code) if not isinstance(code, ErrorCode) else code
    spec = ERROR_SPECS[resolved]
    return SubjectOperationError(
        spec.code,
        spec.message,
        http_status=spec.http_status,
        retryable=spec.retryable,
        cause=cause,
    )


def _timeout_types() -> tuple[type[BaseException], ...]:
```

### `tests/phase1/conftest.py`

只读：显式隔离fixture；p1_subjects键是标签，路径取subject_id

L28–L40（原样）：
```python
def p1_runtime(tmp_path: Path) -> Iterator[Path]:
    """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root


@pytest.fixture
def p1_subjects(p1_runtime: Path) -> dict:
    """在隔离根下建 A / B / global 三处**同名**知识库，各带独立标记。"""
    subjects = helpers.make_same_name_kbs(p1_runtime)
    subjects["_admin_root"] = p1_runtime
    return subjects
```

L73–L76（原样）：
```python
def p1_route_client(p1_runtime: Path) -> Iterator[object]:
    """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
    with helpers.route_client() as client:
        yield client
```

### `tests/phase1/helpers.py`

只读：SubjectPaths及FakeSTT接口；stub不证明ASR流式wire，另写假httpx transport

L551–L564（原样）：
```python
class SubjectPaths:
    subject_id: str
    admin_root: Path
    root: Path
    outputs: Path
    marker: str

    @property
    def knowledge_bases(self) -> Path:
        return self.root / "knowledge_bases"

    @property
    def materials(self) -> Path:
        return self.root / "materials"
```

L805–L815（原样）：
```python
    async def transcribe(self, audio_path: Path, *, language: str = "zh") -> dict[str, Any]:
        self._record(audio_path=str(audio_path), language=language)
        payload: dict[str, Any] = {
            "text": "" if self.error else str(self.response),
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.error:
            payload["error"] = self.error
        return payload
```

### `tests/services/embedding/test_client_runtime.py`

只读：现有假adapter；P30必须回跑此文件

L27–L37（原样）：
```python
    async def embed(self, request):
        self.calls.append(request)
        return type(
            "Resp",
            (),
            {
                "embeddings": [
                    [float(i)] * (request.dimensions or 2) for i, _ in enumerate(request.texts)
                ],
            },
        )()
```

## 相关冻结Schema（从schemas.json抽取）

相对路径和当前身份的安全约束由代码额外落实，不可把Schema的普通string误当可任意路径。
```json
{
"SourceFile": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1}, "size": {"type": "integer", "minimum": 0}, "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}(?![\\s\\S])"}}, "required": ["path", "size", "sha256"], "additionalProperties": false},
"MaterialManifest": {"type": "object", "properties": {"schema_version": {"const": 1}, "subject_id": {"type": "string", "pattern": "^[a-z0-9\\u4e00-\\u9fff][a-z0-9\\u4e00-\\u9fff-]{0,63}(?![\\s\\S])"}, "kb_name": {"type": "string"}, "files": {"type": "array", "items": {"$ref": "#/$defs/SourceFile"}}}, "required": ["schema_version", "subject_id", "kb_name", "files"], "additionalProperties": false},
"Transcript": {"type": "object", "properties": {"file": {"type": "string", "pattern": "^(?!\\.\\.?$)[^/\\\\\\x00-\\x1f]+(?![\\s\\S])"}, "text": {"type": "string"}, "model": {"type": "string"}}, "required": ["file", "text", "model"], "additionalProperties": false},
"UploadIndex": {"type": "object", "properties": {"operation": {"const": "index"}, "kb_name": {"type": "string"}, "type": {"enum": ["textbook", "ppt", "board", "lecture", "assignment", "past_exam", "other"]}, "files": {"type": "array", "items": {"type": "string", "pattern": "^(?!\\.\\.?$)[^/\\\\\\x00-\\x1f]+(?![\\s\\S])"}}, "task_id": {"type": "string", "minLength": 1}, "message": {"type": "string"}}, "required": ["operation", "kb_name", "type", "files", "task_id", "message"], "additionalProperties": true},
"UploadTranscribe": {"type": "object", "properties": {"operation": {"const": "transcribe"}, "type": {"const": "lecture"}, "files": {"type": "array", "items": {"type": "string", "pattern": "^(?!\\.\\.?$)[^/\\\\\\x00-\\x1f]+(?![\\s\\S])"}}, "transcripts": {"type": "array", "items": {"$ref": "#/$defs/Transcript"}}, "message": {"type": "string"}}, "required": ["operation", "type", "files", "transcripts", "message"], "additionalProperties": false}
}
```

## 必须保留的范围决定

ZIP/目录上传不新增；不更改全局文档白名单、不迁移真实资料、不升级引擎/模型。不提前修S07 query策略、S10 P1-39/P1-54。S04显式cause≤4只用于当前已测试路径，__context__不自动追溯；本阶段新失败直接使用typed C02边界，不新增原始detail。

阶段完整目标、低依赖实施顺序、允许符号、每单元证据与完成条件均在START_S05.txt中；只读基础的最小必要上下文可以定向补读，无须新的orientation汇报。

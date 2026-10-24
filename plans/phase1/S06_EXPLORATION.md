# S06 已探索的文件清单 + 关键片段

派发基准：2026-10-14 S05-final，HEAD 9723f953cb6ca56f13603f76c5d07e1e2f1f4473，保留当前dirty。
当前完整执行指令是 START_S06.txt。下文片段从当前文件逐行生成；核验整文件SHA-256一致即可复用，hash不符只补读对应符号。无需重新orientation、扫描全仓或复读历史报告。片段是当前实现证据，旧的“必须双多模态/文本embedding跳图”正是本阶段要修的问题。

调用图：FileTypeRouter → LlamaIndexDocumentLoader.load → parser(to_thread)/text/standalone image → 新describe_image_for_index → 普通Document或原ImageNode → pipeline.initialize → storage.create_index。现有coverage尚未接通；P27把本次结果加法式传至initializer metadata与ProgressTracker最终保存/事件。保留原bool返回、两参数embedding进度、S05 worker门禁与原子callback注册。

范围：11条见START_S06/stages.json；initializer、progress_tracker、旧loader测试是P27已明确的最小扩展。其余片段是只读依赖，不授权改resolver、factory、parsing、storage或共享fixture。新helper与三份测试当前缺失，必须新建，不能误把“未找到”当环境阻塞。

容易误判：策略getter目前只有设置接口调用，不能假定已有通用vision selector可直接调用；resolver只取dedicated。旧LLMClient.complete丢finish_reason；新helper用factory.complete_response。parser资产平铺收集没有page映射，缺位置null。原extractor更新列表把图片记录放在document前，不能按列表顺序猜页码；应验证文内标记、编号和源对应。reading_image_budget是独立宽松场景，不能改成索引默认。

coverage口径已在START_S06冻结：images计数只针对实际观察到的去重图，seen=indexed+skipped；parser_no_assets按无法验证的源计数，不伪造image数量；警告放外层，不扩展ImageCoverage五字段。完成事件必须保留coverage，不只内部日志。新字段不许带绝对缓存路径/base64/provider异常。

## 当前不存在、获准新建的文件

- `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/image_description.py`
- `/home/albert/selflearn/selflearn/tests/phase1/test_p1_26.py`
- `/home/albert/selflearn/selflearn/tests/phase1/test_p1_27.py`
- `/home/albert/selflearn/selflearn/tests/phase1/test_p1_28.py`

## 已探索现有文件的指纹清单

| 文件 | SHA-256 | 定位用途 |
|---|---|---|
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/document_loader.py` | `36a9361b24539eca1241e02cb1d8dbb2c6be8caf2f72d2781c6573ff7795f08d` | P27主要接缝：原file分类、to_thread、parser tuple/资产收集、必须双多模态的缺陷和旧字符串描述。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/pipeline.py` | `1f83216ede73b19dee02c4e2185483c70e2273479a2ec3799ff332d10901a9b3` | P27初始化投影；前一片段是S05刚验收的ContextVar分发/注册锁，必须保留。 |
| `/home/albert/selflearn/selflearn/deeptutor/knowledge/initializer.py` | `c2c7fffbae97bc94ba6188ddab42ac2464da9c9dc38591c67060d536086d5329` | P27最小扩展：metadata合并、bool initialize和两参数进度callback、CLI最终progress覆盖点。 |
| `/home/albert/selflearn/selflearn/deeptutor/knowledge/progress_tracker.py` | `789a383cebd89ba52349acdee4c957e81868eed67ed5efec0b0c5075692f3732` | P27最小扩展：kb_config progress白名单、update字段、task event和notify；最终事件不能丢coverage。 |
| `/home/albert/selflearn/selflearn/deeptutor/utils/document_images.py` | `87f41dc99bfa61f306e366383426a2a341cd128d24496141b9582d85d33cf3ba` | P28：默认与reading专用预算、原始bytes限额、DOCX去重/OOXML关系、PPTX和PDF入口。 |
| `/home/albert/selflearn/selflearn/deeptutor/utils/document_extractor.py` | `7e09575b57680d140de005c167126f1d3d7a7bda575b0de6118f748379144b89` | P28：turn限额、按格式抽图、实际image record及document record位置/统计。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/settings/vision_strategy.py` | `bc85e0a0f7f1846c33af8c06db28c344f77489664a65fdb985395e45bef6f045` | 只读P26：现有三策略；prefer_dedicated与dedicated_only当前同义，不能臆造回main策略。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/config/provider_runtime.py` | `6872c3b1831b8ecd8cad1b860b2085ad3b6298e243fc2ccb9960f628fd406cf8` | 只读P26：dedicated resolver返回ResolvedLLMConfig或None；它本身不替你选择main。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/llm/factory.py` | `8710db552f199dd8156152fda44513abb1a4f3c4f9a01cd495a666b0d01918f5` | 只读P26：complete_response保留finish_reason，并接收image_data等参数；不要用仅字符串complete做截断校验。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/llm/client.py` | `417516d62d8755eb6371a1dbfe7a4c098346d8c24981a9f3f7dba46a41bc0035` | 只读P26：旧complete压缩为字符串，capability依据config；避免创建client导致全局OPENAI环境副作用。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/llm/capabilities.py` | `d0afcd3cb4761665b3489cfcd2af1895c82ce586af19dead3d59b11779014998` | 只读P26：supports_vision(binding, model)，不能用embedding是否多模态替代vision判断。 |
| `/home/albert/selflearn/selflearn/deeptutor/subjects/generation.py` | `831c50decd82ee2977e2e3046346044d7ab7f08659cd25c79070d015f63969bc` | 只读S02产物：先检查finish_reason，正文截断/空截断/普通空回答分别失败；复用不可弱化。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/parsing/types.py` | `c71af832dea76b2498763f685c5c3f1ce57e7cd1834af8c2d68d16c291faa82a` | 只读P27：ParsedDocument markdown/blocks/asset_dir；位置仅来自真实blocks，缺失不猜。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/service.py` | `c720aed1e7c732e6ff90cca62e3976980b3020b687e6411398f2ae1149962c73` | 只读接缝：initialize的kwargs透传到pipeline，bool返回保持。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/storage.py` | `6b29336228586ff5bf08b199e49f6286a450c02a731f6826cf274790f916ea02` | 只读P27测试接缝：使用真实文本index/retrieve和离线embedding，不替换成预制命中结果。 |
| `/home/albert/selflearn/selflearn/tests/services/rag/test_llamaindex_document_loader.py` | `a41005bcd44855b2f298424aceba30b9f744f97e4d32048feda8cbfd56e4af26` | 有限可改测试：6字节图和旧跳图/旧日志断言须适配C09；不是允许删掉场景或S01隔离。 |
| `/home/albert/selflearn/selflearn/tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | 只读S01共享夹具：显式p1_runtime/p1_providers；新的factory图调用仍需本测试安装恰当替身。 |
| `/home/albert/selflearn/selflearn/tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 只读S01：services测试可用isolated_runtime；默认guard网络，finally恢复全局状态。 |
| `/home/albert/selflearn/selflearn/.phase1-evidence/stages/S01/rework01/run_regression_tmp_home.py` | `c40d69f6b3c4309da47bc2f026f8ed8c5413d0d1a75abcf8e05249d58ec17b59` | 只读证据脚本：跨目录收集前设临时HOME/清理key并初始化临时配置。不要改脚本。 |

## 关键原文片段

以下保留原文行号，允许定向扩读相邻实现；源码编辑后行号自然变化，以符号定位。

### deeptutor/services/rag/pipelines/llamaindex/document_loader.py

P27主要接缝：原file分类、to_thread、parser tuple/资产收集、必须双多模态的缺陷和旧字符串描述。

L44–L61（整文件hash见表）：

```python
class _ImageSource:
    """An image to embed as an ``ImageNode``, plus the document it came from.

    ``path`` is the image file on disk (what gets embedded and served).
    ``origin`` is the document it belongs to: the image itself for a standalone
    image file, or the source PDF/e-book for an image extracted during parsing —
    so retrieval cites the source document rather than an opaque cache asset.
    """

    path: Path
    origin: Path


class LlamaIndexDocumentLoader:
    """Convert source files into LlamaIndex ``Document`` / ``ImageNode`` objects."""

    def __init__(self, logger=None) -> None:
        self.logger = logger or logging.getLogger(__name__)
```

L63–L95（整文件hash见表）：

```python
    async def load(self, file_paths: Iterable[str]) -> list[Any]:
        documents: list[Any] = []
        image_sources: list[_ImageSource] = []
        classification = FileTypeRouter.classify_files(list(file_paths))

        for file_path_str in classification.parser_files:
            file_path = Path(file_path_str)
            self.logger.info(f"Parsing document: {file_path.name}")
            # MinerU cloud parsing blocks end to end (upload + 300s polling +
            # archive download) on a synchronous httpx.Client — running it on
            # the event loop stalls every other request for the whole PDF
            # (same class of bug as upstream #761/#777). Hand it to a thread.
            text, extracted_images = await asyncio.to_thread(self._parse_document, file_path)
            self._append_if_nonempty(documents, file_path, text)
            image_sources.extend(extracted_images)

        for file_path_str in classification.text_files:
            file_path = Path(file_path_str)
            self.logger.info(f"Parsing text: {file_path.name}")
            text = await FileTypeRouter.read_text_file(str(file_path))
            self._append_if_nonempty(documents, file_path, text)

        for file_path_str in classification.image_files:
            path = Path(file_path_str)
            image_sources.append(_ImageSource(path=path, origin=path))

        if image_sources:
            documents.extend(await self._load_image_nodes(image_sources))

        for file_path_str in classification.unsupported:
            self.logger.warning(f"Skipped unsupported file: {Path(file_path_str).name}")

        return documents
```

L116–L150（整文件hash见表）：

```python
        text = parsed.markdown.strip() or self._text_from_blocks(parsed.blocks)
        images = self._collect_asset_images(parsed.asset_dir, origin=file_path)
        return text, images

    @staticmethod
    def _text_from_blocks(blocks: list[dict] | None) -> str:
        """Fall back to concatenating block text when an engine emits no markdown."""
        if not blocks:
            return ""
        parts = [
            str(block.get("text") or block.get("content") or "").strip()
            for block in blocks
            if isinstance(block, dict)
        ]
        return "\n\n".join(part for part in parts if part)

    def _collect_asset_images(self, asset_dir: Path | None, *, origin: Path) -> list[_ImageSource]:
        """Gather images the parse engine extracted into ``asset_dir``.

        Engines that don't extract images (text-only, markitdown) leave
        ``asset_dir`` empty, so this returns nothing and the document is indexed
        as text alone.
        """
        if not asset_dir or not Path(asset_dir).is_dir():
            return []
        images = [
            _ImageSource(path=child, origin=origin)
            for child in sorted(Path(asset_dir).iterdir())
            if child.is_file() and child.suffix.lower() in FileTypeRouter.IMAGE_EXTENSIONS
        ]
        if images:
            self.logger.info(
                f"Extracted {len(images)} image(s) from {origin.name} for multimodal indexing"
            )
        return images
```

L152–L184（整文件hash见表）：

```python
    async def _load_image_nodes(self, sources: list[_ImageSource]) -> list[ImageNode]:
        embedding_client = get_embedding_client()
        llm_client = get_llm_client()

        unsupported_reasons = []
        if not embedding_client.supports_multimodal_contents():
            unsupported_reasons.append(
                "embedding provider/model does not support multimodal contents "
                f"(binding={embedding_client.config.binding}, "
                f"model={embedding_client.config.model})"
            )
        if not llm_client.supports_multimodal_images():
            unsupported_reasons.append(
                "LLM provider/model does not support multimodal image input "
                f"(binding={llm_client.config.binding}, model={llm_client.config.model})"
            )
        if unsupported_reasons:
            reason_text = "; ".join(unsupported_reasons)
            for source in sources:
                self.logger.warning(
                    "Skipped image because image indexing requires both "
                    f"multimodal embedding and multimodal LLM support; {reason_text}: "
                    f"{source.path.name}"
                )
            return []

        embedded: list[_ImageSource] = []
        descriptions: list[str] = []
        contents = []
        for source in sources:
            try:
                image_payload = self._load_image_payload(source.path)
                description = await self._describe_image(
```

L244–L268（整文件hash见表）：

```python
    async def _describe_image(self, file_path: Path, image_base64: str, mimetype: str) -> str:
        llm_client = get_llm_client()
        response = await llm_client.complete(
            IMAGE_DESCRIPTION_PROMPT,
            system_prompt=IMAGE_DESCRIPTION_SYSTEM_PROMPT,
            image_data=image_base64,
            image_mime_type=mimetype,
            image_filename=file_path.name,
        )
        return response.strip()

    def _load_image_payload(self, file_path: Path) -> dict[str, str]:
        size = file_path.stat().st_size
        if size > DocumentValidator.MAX_FILE_SIZE:
            raise OSError(
                f"image file too large: {size} bytes; "
                f"maximum allowed: {DocumentValidator.MAX_FILE_SIZE} bytes"
            )
        mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
        return {
            "base64": encoded,
            "data_uri": f"data:{mimetype};base64,{encoded}",
            "mimetype": mimetype,
        }
```

### deeptutor/services/rag/pipelines/llamaindex/pipeline.py

P27初始化投影；前一片段是S05刚验收的ContextVar分发/注册锁，必须保留。

L119–L150（整文件hash见表）：

```python
        return _dispatch_progress if _PROGRESS_CALLBACKS else None


def _dispatch_progress(*args: Any, **kwargs: Any) -> None:
    """Forward one progress event to the heartbeat of the calling worker.

    No worker context (or a finished one) means the event is dropped: progress
    is never broadcast to every live run, and the newest installed run is never
    used as a stand-in for the others.
    """
    heartbeat = _CURRENT_HEARTBEAT.get(None)
    if heartbeat is None:
        return
    heartbeat(*args, **kwargs)


def _install_progress_callback(callback: Callable[..., Any]) -> None:
    """Register *callback* and make sure the shared dispatcher is installed."""
    with _PROGRESS_CALLBACK_LOCK:
        _PROGRESS_CALLBACKS.append(callback)
        set_progress_callback(_dispatch_progress)


def _restore_progress_callback(callback: Callable[..., Any]) -> None:
    """Drop *callback*; only still-live runs keep the dispatcher installed."""
    with _PROGRESS_CALLBACK_LOCK:
        if callback in _PROGRESS_CALLBACKS:
            _PROGRESS_CALLBACKS.remove(callback)
        if not _PROGRESS_CALLBACKS:
            # Keep the adapter update inside the registry lock. A concurrent
            # installation must not be cleared after it installs a live run.
            set_progress_callback(None)
```

L303–L362（整文件hash见表）：

```python
    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        progress_callback = kwargs.get("progress_callback")
        self._configure_settings()

        self.logger.info(
            f"Initializing KB '{kb_name}' with {len(file_paths)} files using LlamaIndex"
        )

        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        signature = self._current_signature()
        storage_dir = resolve_storage_dir_for_rebuild(kb_dir, signature)

        # A stalled worker keeps its thread alive after the guard raises (Python
        # cannot interrupt synchronous code), so a same-KB retry must be refused
        # rather than racing the corpse of the previous run.
        _ensure_index_worker_available(str(kb_dir.resolve()))

        try:
            await self._verify_embedding_connectivity()
            documents = await self.document_loader.load(file_paths)
            if not documents:
                self.logger.error("No valid documents found")
                return False

            self.logger.info(
                f"Creating VectorStoreIndex with {len(documents)} documents "
                f"(chunking + embedding)..."
            )

            # Bounded instead of unbounded: an embedding endpoint that accepts a
            # request and never answers used to block this thread forever, so
            # the whole indexing task hung with no error. The guard fails once
            # the progress heartbeat goes quiet for too long.
            await _run_with_stall_guard(
                lambda: storage.create_index(documents, storage_dir, show_progress=True),
                progress_callback=progress_callback,
                worker_key=str(kb_dir.resolve()),
            )

            self.logger.info(f"Index persisted to {storage_dir}")
            if signature is not None:
                write_version_meta(kb_dir, signature, storage_dir=storage_dir)

            self.logger.info(f"KB '{kb_name}' initialized successfully with LlamaIndex")
            return True

        except Exception as exc:
            self.logger.error(f"Failed to initialize KB: {exc}")
            self.logger.error(traceback.format_exc())
            self._cleanup_failed_version_dir(storage_dir, signature)
            raise

    async def search(
        self,
        query: str,
        kb_name: str,
        **kwargs,
    ) -> Dict[str, Any]:
        kwargs.pop("mode", None)
        self._configure_settings()
```

### deeptutor/knowledge/initializer.py

P27最小扩展：metadata合并、bool initialize和两参数进度callback、CLI最终progress覆盖点。

L79–L101（整文件hash见表）：

```python
    def _update_metadata_with_provider(self, provider: str) -> None:
        metadata_file = self.kb_dir / "metadata.json"
        metadata: dict = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                metadata = {}

        metadata["rag_provider"] = provider
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata["last_updated"] = timestamp
        metadata["last_indexed_at"] = timestamp
        metadata["last_indexed_count"] = len(
            FileTypeRouter.collect_supported_files(self.raw_dir, recursive=True)
        )
        metadata["last_indexed_action"] = "create"

        atomic_write_json(metadata_file, metadata)

        try:
            # Scope the config write to *this* initializer's own KB root.
```

L188–L230（整文件hash见表）：

```python
        )
        file_paths = [str(doc_file) for doc_file in doc_files]

        def _on_progress(batch_num, total_batches):
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Embedding batches: {batch_num}/{total_batches} complete",
                current=batch_num,
                total=total_batches,
            )

        try:
            success = await rag_service.initialize(
                kb_name=self.kb_name,
                file_paths=file_paths,
                progress_callback=_on_progress,
            )
            if not success:
                self.progress_tracker.update(
                    ProgressStage.ERROR,
                    "Document processing failed",
                    error="RAG pipeline returned failure",
                )
                raise RuntimeError("RAG pipeline returned failure")

            self._update_metadata_with_provider(provider)
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                "Documents processed successfully",
                current=len(doc_files),
                total=len(doc_files),
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing documents: {error_msg}")
            self.progress_tracker.update(
                ProgressStage.ERROR,
                "Failed to process documents",
                error=error_msg,
            )
            raise

        await self.fix_structure()
```

L274–L294（整文件hash见表）：

```python
        initializer.create_directory_structure()
        copied_files = initializer.copy_documents(source_files)
        await initializer.process_documents()
        manager.update_kb_status(
            name=kb_name,
            status="ready",
            progress={
                "stage": "completed",
                "message": "Knowledge base initialization complete!",
                "percent": 100,
                "current": 1,
                "total": 1,
                "file_name": "",
                "error": None,
                "timestamp": datetime.now().isoformat(),
                "indexed_count": len(copied_files),
                "index_changed": True,
                "index_action": "create",
            },
        )
        return True
```

### deeptutor/knowledge/progress_tracker.py

P27最小扩展：kb_config progress白名单、update字段、task event和notify；最终事件不能丢coverage。

L96–L129（整文件hash见表）：

```python
                "processing_file",
            ]:
                status = "processing"
            else:
                status = "initializing"

            # Update kb_config.json with status and progress
            manager.update_kb_status(
                name=self.kb_name,
                status=status,
                progress={
                    "stage": progress.get("stage"),
                    "message": progress.get("message"),
                    "percent": progress.get("progress_percent", 0),
                    "current": progress.get("current", 0),
                    "total": progress.get("total", 0),
                    "file_name": progress.get("file_name"),
                    "error": progress.get("error"),
                    "error_code": progress.get("error_code"),
                    "retryable": progress.get("retryable"),
                    "timestamp": progress.get("timestamp"),
                    "task_id": progress.get("task_id"),
                    "indexed_count": progress.get("indexed_count"),
                    "index_changed": progress.get("index_changed"),
                    "index_action": progress.get("index_action"),
                },
            )
        except Exception as e:
            _logger_instance().warning("Failed to save progress to kb_config.json: %s", e)

        # Persist the last seen progress snapshot so websocket subscribers and
        # page reloads can recover the live state without relying on in-memory callbacks.
        try:
            atomic_write_json(self.progress_file, progress)
```

L135–L173（整文件hash见表）：

```python
    def update(
        self,
        stage: ProgressStage,
        message: str = "",
        current: int = 0,
        total: int = 0,
        file_name: str = "",
        error: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        indexed_count: int | None = None,
        index_changed: bool | None = None,
        index_action: str | None = None,
    ):
        """Update progress"""
        progress = {
            "kb_name": self.kb_name,
            "task_id": self.task_id,
            "stage": stage.value,
            "message": message,
            "current": current,
            "total": total,
            "file_name": file_name,
            "progress_percent": int(current / total * 100) if total > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }
        if indexed_count is not None:
            progress["indexed_count"] = indexed_count
        if index_changed is not None:
            progress["index_changed"] = index_changed
        if index_action:
            progress["index_action"] = index_action

        if error:
            progress["error"] = error
            progress["stage"] = ProgressStage.ERROR.value
        if error_code:
            progress["error_code"] = error_code
        if retryable is not None:
```

L208–L221（整文件hash见表）：

```python

        self._save_progress(progress)

        if self.task_id:
            try:
                from deeptutor.api.utils.task_log_stream import get_task_stream_manager

                get_task_stream_manager().emit(self.task_id, "progress", progress)
            except Exception as e:
                _logger_instance().debug("Failed to emit task progress event: %s", e)

        self._notify(progress)

    def get_progress(self) -> dict | None:
```

### deeptutor/utils/document_images.py

P28：默认与reading专用预算、原始bytes限额、DOCX去重/OOXML关系、PPTX和PDF入口。

L46–L79（整文件hash见表）：

```python
MAX_IMAGES_PER_DOC = 12
MAX_TOTAL_IMAGE_BYTES_PER_DOC = 12 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MIN_IMAGE_BYTES = 1_200  # below this it is a bullet point or a divider, not a figure


def reading_image_budget() -> ImageBudget:
    """Looser per-document caps for the reading-area ingest path.

    The reading store keeps the image bytes on disk, and a single chat turn
    inflates only the *current page's* images into the request, so the caps
    split in two directions: the document-wide caps can be far looser than the
    chat-attachment defaults, while the per-page cap is tightened to what one
    request can carry. ``max_images_per_page=4`` mirrors
    ``READING_VIEWPORT_MAX_IMAGES`` in ``services/session/_turn_runtime_shared``
    (kept as a literal so this utils module stays free of a services import).
    """
    return ImageBudget(
        max_images=120,
        max_total_bytes=60 * 1024 * 1024,
        max_images_per_page=4,
    )


# Raster formats vision models and the browser can both consume. Everything
# else (EMF/WMF vector, TIFF, SVG, …) is skipped with a note.
SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
)

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
```

L121–L139（整文件hash见表）：

```python
    def register_other_skip(self) -> None:
        self.skipped_other += 1

    def try_admit(self, ext: str, data: bytes) -> EmbeddedImage | None:
        """Admit one candidate image, applying every budget. ``None`` = skip."""
        if len(data) < self.min_image_bytes or len(data) > self.max_image_bytes:
            self.skipped_budget += 1
            return None
        if self.count >= self.max_images or self.total_bytes + len(data) > self.max_total_bytes:
            self.skipped_budget += 1
            return None
        self.count += 1
        self.total_bytes += len(data)
        return EmbeddedImage(
            name=f"image-{self.count:02d}{ext}",
            mime_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
            data=data,
        )

```

L236–L255（整文件hash见表）：

```python
def extract_docx_rich(data: bytes, *, budget: ImageBudget | None = None) -> DocxRich:
    """Walk ``word/document.xml`` once, collecting ordered paragraphs and images.

    Only the main body is mined (header/footer images are decoration). A
    relationship target referenced by several paragraphs is extracted once but
    marked at every position, so repeated/floating figures stay anchored to
    the text around them.
    """
    budget = budget or ImageBudget()
    images: list[EmbeddedImage] = []
    by_target: dict[str, EmbeddedImage] = {}
    attempted: set[str] = set()

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        rel_targets = _office_rels(zf, "word/_rels/document.xml.rels")
        root = _parse_xml(zf.read("word/document.xml"))

        paragraphs: list[str] = []
        for node in root.iter():
```

L303–L325（整文件hash见表）：

```python
def _office_rels(zf: zipfile.ZipFile, rels_member: str) -> dict[str, str]:
    """rId → normalised archive path for internal media targets."""
    try:
        raw = zf.read(rels_member)
    except KeyError:
        return {}
    try:
        root = _parse_xml(raw)
    except Exception:
        return {}
    base = posixpath.dirname(posixpath.dirname(rels_member))  # …/word/_rels → …/word
    targets: dict[str, str] = {}
    for node in root.iter():
        if _local_name(node.tag) != "Relationship":
            continue
        if (node.get("TargetMode") or "").lower() == "external":
            continue
        rid = node.get("Id") or ""
        target = node.get("Target") or ""
        if rid and target:
            targets[rid] = posixpath.normpath(posixpath.join(base, target))
    return targets

```

L368–L394（整文件hash见表）：

```python
def extract_pptx_rich(data: bytes, *, budget: ImageBudget | None = None) -> PptxRich:
    """Slide texts with markers plus pictures, via python-pptx when available.

    python-pptx resolves picture placeholders and grouped shapes cleanly and
    only reports images actually placed on a slide (layout/master decoration
    stays out). The raw-OOXML fallback additionally catches background fills
    when python-pptx is missing or fails.
    """
    try:
        from pptx import Presentation
    except ImportError:
        return _extract_pptx_rich_ooxml(data, budget=budget)

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception:
        return _extract_pptx_rich_ooxml(data, budget=budget)

    budget = budget or ImageBudget()
    images: list[EmbeddedImage] = []
    slides: list[str] = []
    for slide in prs.slides:
        lines: list[str] = []
        _collect_shape_rich(slide.shapes, lines, budget, images)
        slides.append("\n".join(line for line in lines if line))

    return PptxRich(slides=tuple(slides), collection=_collection_from(budget, images))
```

L509–L532（整文件hash见表）：

```python
def extract_pdf_images(data: bytes, *, budget: ImageBudget | None = None) -> PdfImages:
    """Raster images per page via PyMuPDF, deduplicated across the document.

    Running headers/footers embed the same logo xref on every page. Store its
    bytes once, but map that image to every page where it appears.

    ``budget`` defaults to the chat-attachment caps (unchanged behaviour). When
    it carries a non-zero ``max_images_per_page``, a page stops admitting once
    it hits that many images and the rest of that page's candidates are counted
    as page-budget skips. Reused xrefs still count toward the per-page cap,
    but do not consume the document-wide image or byte budgets again.
    """
    try:
        import pymupdf
    except ImportError:
        return PdfImages()

    budget = budget or ImageBudget()
    images: list[EmbeddedImage] = []
    page_map: list[tuple[int, tuple[int, ...]]] = []
    xref_to_index: dict[int, int] = {}
    rejected_xrefs: set[int] = set()

    try:
```

### deeptutor/utils/document_extractor.py

P28：turn限额、按格式抽图、实际image record及document record位置/统计。

L71–L81（整文件hash见表）：

```python
MAX_DOC_BYTES = 20 * 1024 * 1024
MAX_TOTAL_DOC_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARS_PER_DOC = 200_000
MAX_EXTRACTED_CHARS_TOTAL = 150_000

# Embedded pictures harvested from a document ride the turn as ordinary image
# attachments (see ``extract_documents_from_records``). These are the per-turn
# ceilings across all documents; the per-document caps live in
# ``document_images``. Ported from upstream v1.6.11.
MAX_EMBEDDED_IMAGES_PER_TURN = 16
MAX_EMBEDDED_IMAGE_BYTES_PER_TURN = 12 * 1024 * 1024
```

L929–L947（整文件hash见表）：

```python
def _embedded_images_for_document(filename: str, data: bytes) -> tuple[EmbeddedImage, ...]:
    """Best-effort embedded-image harvest for the chat attachment path.

    Re-parses the document after the text pass (the shared text API stays
    text-only for its many callers). Failures never fail the message — the
    text extraction result stands on its own. Ported from upstream v1.6.11.
    """
    ext = _ext(filename)
    try:
        if ext == ".docx":
            return extract_docx_rich(data).collection.images
        if ext == ".pptx":
            return extract_pptx_rich(data).collection.images
        if ext == ".pdf":
            return extract_pdf_images(data).collection.images
    except Exception:  # noqa: BLE001
        logger.info("embedded image extraction failed for %s", filename, exc_info=True)
    return ()

```

L1038–L1097（整文件hash见表）：

```python
            continue

        remaining_budget = max_chars_total - total_chars
        if remaining_budget <= 0:
            doc_texts.append(f"[File: {filename} — skipped: total extracted-text quota exceeded]")
            record["base64"] = ""
            record["extracted_chars"] = 0
            updated.append(record)
            continue

        if len(text) > remaining_budget:
            text = (
                text[:remaining_budget]
                + f"... (truncated, {len(text)} chars total; turn quota hit)"
            )

        # Harvest embedded pictures and emit them as image-type records right
        # after the document, so vision models see what the text refers to and
        # the UI previews them like any pasted screenshot. Ported from upstream
        # v1.6.11.
        doc_id = str(record.get("id") or "")
        stem = filename[: -len(_ext(filename))] or filename
        images = _embedded_images_for_document(filename, data)
        emitted: list[EmbeddedImage] = []
        for image in images:
            if embedded_images >= MAX_EMBEDDED_IMAGES_PER_TURN:
                break
            if embedded_image_bytes + len(image.data) > MAX_EMBEDDED_IMAGE_BYTES_PER_TURN:
                break
            ext = f".{image.name.rsplit('.', 1)[-1]}" if "." in image.name else ".png"
            embedded_images += 1
            embedded_image_bytes += len(image.data)
            emitted.append(image)
            updated.append(
                {
                    "type": "image",
                    "url": "",
                    "base64": base64.b64encode(image.data).decode("ascii"),
                    "filename": f"{stem}-图{image_index_from_name(image.name)}{ext}",
                    "mime_type": image.mime_type,
                    "id": f"{doc_id}-e{image_index_from_name(image.name):02d}" if doc_id else "",
                    "embedded": True,
                }
            )
        if images and len(emitted) < len(images):
            text += f"\n[本文件还有 {len(images) - len(emitted)} 张图片因数量/大小上限未随消息提供]"
        if emitted:
            text += (
                f"\n[本文件内嵌 {len(emitted)} 张图片，已作为图片附件随本条消息提供，"
                "编号与本文件文本中的 [图片 N] 标记对应]"
            )

        total_chars += len(text)
        doc_texts.append(f"[File: {filename}]\n{text}")
        record["base64"] = ""
        record["extracted_chars"] = len(text)
        record["extracted_text"] = text
        updated.append(record)

    return doc_texts, updated
```

### deeptutor/services/settings/vision_strategy.py

只读P26：现有三策略；prefer_dedicated与dedicated_only当前同义，不能臆造回main策略。

L1–L38（整文件hash见表）：

```python
"""Vision routing strategy (M8): how image-understanding tools pick a model.

    strategy:
      auto              — probe the main LLM's multimodal capability; use it
                           when supported, otherwise the dedicated vision model
                           (dedicated model as fallback).
      prefer_dedicated  — always use the dedicated vision model.
      dedicated_only    — same as prefer_dedicated (alias, kept for clarity).

Stored in ``data/user/settings/vision_strategy.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.path_service import get_path_service

DEFAULTS = {"strategy": "auto"}
VALID = ("auto", "prefer_dedicated", "dedicated_only")


def _path() -> Path:
    return get_path_service().get_settings_file("vision_strategy")


def get_vision_strategy() -> str:
    path = _path()
    if not path.exists():
        return DEFAULTS["strategy"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULTS["strategy"]
    strategy = str(data.get("strategy", DEFAULTS["strategy"]))
    return strategy if strategy in VALID else DEFAULTS["strategy"]

```

### deeptutor/services/config/provider_runtime.py

只读P26：dedicated resolver返回ResolvedLLMConfig或None；它本身不替你选择main。

L1136–L1169（整文件hash见表）：

```python
def resolve_vision_runtime_config(
    catalog: dict[str, Any] | None = None,
    *,
    service: ModelCatalogService | None = None,
) -> ResolvedLLMConfig | None:
    """Resolve the active vision (multimodal image-understanding) config.

    Returns ``None`` when no vision model is configured — callers (e.g. the
    ``geogebra_analysis`` tool) then fall back to the main LLM config, which
    is the right default when the everyday model is itself multimodal.
    """
    catalog_service = service or get_model_catalog_service()
    loaded = _load_catalog(catalog)
    profile, model = _active_profile_and_model(loaded, catalog_service, "vision")
    resolved_model = _as_str((model or {}).get("model"))
    if not profile or not resolved_model:
        return None
    api_key = _as_str((profile or {}).get("api_key"))
    api_base = _as_str((profile or {}).get("base_url"))
    if not api_key and api_base:
        # Local endpoints (ollama / lm studio) may not need a key.
        api_key = "sk-no-key-required"
    return ResolvedLLMConfig(
        model=resolved_model,
        provider_name="vision",
        provider_mode="openai_compat",
        binding_hint=_as_str((profile or {}).get("binding")) or "openai",
        binding="openai",
        api_key=api_key,
        base_url=api_base or None,
        effective_url=api_base or None,
        api_version=_as_str((profile or {}).get("api_version")) or None,
        extra_headers=_to_headers((profile or {}).get("extra_headers")),
    )
```

### deeptutor/services/llm/factory.py

只读P26：complete_response保留finish_reason，并接收image_data等参数；不要用仅字符串complete做截断校验。

L338–L369（整文件hash见表）：

```python
async def complete_response(
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    binding: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    exponential_backoff: bool = DEFAULT_EXPONENTIAL_BACKOFF,
    **kwargs: Any,
) -> "LLMResponse":
    """Like :func:`complete`, but returns the full provider response.

    :func:`complete` collapses the response to its text, which loses
    ``finish_reason``. Callers that need to tell a finished answer from one the
    provider cut off at an output cap (see
    :func:`deeptutor.services.llm.types.finish_was_truncated`) use this instead.
    """
    caller_extra_headers = kwargs.pop("extra_headers", None)
    reasoning_effort = kwargs.pop("reasoning_effort", None)
    image_data = kwargs.pop("image_data", None)
    image_mime_type = kwargs.pop("image_mime_type", "image/png")
    image_filename = kwargs.pop("image_filename", "image.png")

    config, provider_spec = _resolve_call_config(
        model=model,
        api_key=api_key,
        base_url=base_url,
        api_version=api_version,
```

### deeptutor/services/llm/client.py

只读P26：旧complete压缩为字符串，capability依据config；避免创建client导致全局OPENAI环境副作用。

L64–L101（整文件hash见表）：

```python
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> str:
        """
        Call LLM completion via Factory.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            history: Optional conversation history
            **kwargs: Additional arguments passed to the API

        Returns:
            LLM response text
        """
        from . import factory

        factory_complete = cast(Callable[..., Awaitable[str]], factory.complete)
        messages = history or None
        return await factory_complete(
            prompt=prompt,
            system_prompt=system_prompt or "You are a helpful assistant.",
            model=self.config.model,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            api_version=getattr(self.config, "api_version", None),
            binding=getattr(self.config, "binding", "openai"),
            reasoning_effort=getattr(self.config, "reasoning_effort", None),
            extra_headers=getattr(self.config, "extra_headers", None),
            messages=messages,
            **kwargs,
        )

    def complete_sync(
        self,
```

L143–L145（整文件hash见表）：

```python
    def supports_multimodal_images(self) -> bool:
        """Return whether the configured LLM can accept image input."""
        return supports_vision(getattr(self.config, "binding", "openai"), self.config.model)
```

### deeptutor/services/llm/capabilities.py

只读P26：supports_vision(binding, model)，不能用embedding是否多模态替代vision判断。

L511–L525（整文件hash见表）：

```python
def supports_vision(binding: str, model: str | None = None) -> bool:
    """
    Check if the provider/model supports multimodal (image) input.

    Args:
        binding: Provider binding name
        model: Optional model name for model-specific overrides

    Returns:
        True if the model can accept image content in messages
    """
    value = get_capability(binding, "supports_vision", model, default=False)
    return bool(value)


```

### deeptutor/subjects/generation.py

只读S02产物：先检查finish_reason，正文截断/空截断/普通空回答分别失败；复用不可弱化。

L31–L76（整文件hash见表）：

```python
def validate_subject_response(response: Any, *, max_tokens: int | None = None) -> str:
    """Return the usable, trimmed text of one completion response.

    Pure: it only reads ``response.content`` / ``response.finish_reason`` /
    ``response.usage`` — no retries, no network, no budget changes.

    Raises:
        LLMReasoningBudgetExhausted: ``finish_reason`` is a truncation reason and
            the body is empty (the reasoning-burned-the-budget case). Preserved
            unchanged from the earlier contract.
        SubjectOutputTruncated: ``finish_reason`` is a truncation reason **and**
            the body is non-empty — a half-written artifact must not be treated
            as a finished one.
        LLMEmptyResponseError: not truncated, but the body is blank.
    """
    content = getattr(response, "content", None)
    text = (content or "").strip()
    finish_reason = getattr(response, "finish_reason", None)

    # 1) finish_reason 先判：有正文但被截断同样不能算成功。
    if finish_was_truncated(finish_reason):
        usage = dict(getattr(response, "usage", None) or {})
        diagnostics = {
            "finish_reason": finish_reason,
            "usage": usage,
            "max_tokens": max_tokens,
            "content_chars": len(text),
        }
        if text:
            raise SubjectOutputTruncated(diagnostics=diagnostics)
        raise LLMReasoningBudgetExhausted(
            "模型把输出预算耗尽在推理上，没有产出正文"
            f"（finish_reason={finish_reason}，"
            f"completion_tokens={usage.get('completion_tokens', '?')}，"
            f"max_tokens={max_tokens}）。请提高 max_tokens 或降低推理强度后重试。",
            diagnostics=diagnostics,
        )

    # 2) 非截断但空白：provider 没给出可用正文。
    if not text:
        raise LLMEmptyResponseError(
            "模型返回空内容，请重试。",
            details={"finish_reason": finish_reason, "max_tokens": max_tokens},
        )

    return text
```

### deeptutor/services/parsing/types.py

只读P27：ParsedDocument markdown/blocks/asset_dir；位置仅来自真实blocks，缺失不猜。

L24–L45（整文件hash见表）：

```python
class ParsedDocument:
    """The bridge IR.

    ``markdown`` is always present — the lowest common denominator every engine
    produces (MinerU writes ``.md``, Docling exports markdown, markitdown and
    text-only produce markdown/plain text). ``blocks`` is the richer MinerU
    ``content_list``-shaped structure: native for MinerU, mapped for Docling,
    ``None`` for text-only/markitdown. Consumers that only need text read
    ``markdown``; consumers wanting multimodal structure prefer ``blocks`` and
    fall back to chunking ``markdown`` when it is absent.
    """

    markdown: str
    blocks: Optional[list[dict[str, Any]]] = None
    asset_dir: Optional[Path] = None
    source_hash: str = ""
    parser_signature: str = ""
    engine: str = ""
    # The on-disk cache dir holding the raw engine artifacts. Consumers that
    # still operate on a directory (e.g. the question extractor's glob loader)
    # use this; pure-IR consumers ignore it.
    workdir: Optional[Path] = None
```

### deeptutor/services/rag/service.py

只读接缝：initialize的kwargs透传到pipeline，bool返回保持。

L68–L72（整文件hash见表）：

```python
    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        provider = self._resolve_provider(kb_name)
        self.logger.info(f"Initializing KB '{kb_name}' (provider={provider})")
        pipeline = self._get_pipeline(provider)
        return await pipeline.initialize(kb_name=kb_name, file_paths=file_paths, **kwargs)
```

### deeptutor/services/rag/pipelines/llamaindex/storage.py

只读P27测试接缝：使用真实文本index/retrieve和离线embedding，不替换成预制命中结果。

L88–L94（整文件hash见表）：

```python
def create_index(documents: list[Any], storage_dir: Path, *, show_progress: bool = True) -> int:
    index, count = ingestion.create_index_from_documents(
        documents, storage_dir, show_progress=show_progress
    )
    retrievers.persist_bm25_retriever(index, storage_dir, top_k=20)
    return count

```

L282–L286（整文件hash见表）：

```python
def retrieve_nodes(storage_dir: Path, query: str, *, top_k: int = 5) -> list[Any]:
    index = _cached_index(Path(storage_dir))
    retriever = retrievers.build_retriever(index, Path(storage_dir), top_k=top_k)
    return retriever.retrieve(query)

```

### tests/services/rag/test_llamaindex_document_loader.py

有限可改测试：6字节图和旧跳图/旧日志断言须适配C09；不是允许删掉场景或S01隔离。

L197–L237（整文件hash见表）：

```python
def test_loader_skips_images_when_embedding_provider_is_text_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("llama_index.core")
    from deeptutor.services.rag.pipelines.llamaindex import document_loader as loader_module

    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"\x89PNG\r\n")

    class _TextOnlyClient:
        config = type("Config", (), {"binding": "openai", "model": "text-embedding-3-small"})()

        def supports_multimodal_contents(self) -> bool:
            return False

    class _TextOnlyLLM:
        """Text-only LLM stub: no real config read, no provider call.

        Without this the loader falls through to the real ``get_llm_client`` and
        raises ``LLMConfigError`` on a machine with an empty model catalog, which
        made the test depend on the developer's settings.
        """

        config = type("Config", (), {"binding": "openai", "model": "text-only-llm"})()

        def supports_multimodal_images(self) -> bool:
            return False

        async def complete(self, *_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("text-only skip path must not call the LLM")

    monkeypatch.setattr(loader_module, "get_embedding_client", lambda: _TextOnlyClient())
    monkeypatch.setattr(loader_module, "get_llm_client", lambda: _TextOnlyLLM())

    documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(image_path)]))

    assert documents == []


def test_loader_embeds_images_with_qwen38_max_vision_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
```

L320–L352（整文件hash见表）：

```python
def test_loader_logs_all_missing_multimodal_image_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("llama_index.core")
    from deeptutor.services.rag.pipelines.llamaindex import document_loader as loader_module

    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"\x89PNG\r\n")

    class _TextOnlyEmbeddingClient:
        config = type("Config", (), {"binding": "openai", "model": "text-embedding-3-small"})()

        def supports_multimodal_contents(self) -> bool:
            return False

    class _TextOnlyLLMClient:
        config = type("Config", (), {"binding": "openai", "model": "gpt-3.5-turbo"})()

        def supports_multimodal_images(self) -> bool:
            return False

    monkeypatch.setattr(loader_module, "get_embedding_client", lambda: _TextOnlyEmbeddingClient())
    monkeypatch.setattr(loader_module, "get_llm_client", lambda: _TextOnlyLLMClient())

    with caplog.at_level("WARNING"):
        documents = asyncio.run(loader_module.LlamaIndexDocumentLoader().load([str(image_path)]))

    assert documents == []
    assert "requires both multimodal embedding and multimodal LLM support" in caplog.text
    assert "embedding provider/model does not support multimodal contents" in caplog.text
    assert "LLM provider/model does not support multimodal image input" in caplog.text
    assert "text-embedding-3-small" in caplog.text
    assert "gpt-3.5-turbo" in caplog.text
```

### tests/phase1/conftest.py

只读S01共享夹具：显式p1_runtime/p1_providers；新的factory图调用仍需本测试安装恰当替身。

L27–L31（整文件hash见表）：

```python
@pytest.fixture
def p1_runtime(tmp_path: Path) -> Iterator[Path]:
    """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root
```

L58–L76（整文件hash见表）：

```python
@pytest.fixture
def p1_providers(
    monkeypatch: pytest.MonkeyPatch,
    p1_runtime: Path,
    p1_llm: helpers.FakeLLMClient,
    p1_embedding: helpers.FakeEmbeddingClient,
    p1_stt: helpers.FakeSTT,
) -> dict:
    """把三个替身装到真实被调用的模块上，避免任何真实供应商调用。"""
    return helpers.install_provider_stubs(
        monkeypatch, llm=p1_llm, embedding=p1_embedding, stt=p1_stt
    )


@pytest.fixture
def p1_route_client(p1_runtime: Path) -> Iterator[object]:
    """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
    with helpers.route_client() as client:
        yield client
```

### tests/phase1/helpers.py

只读S01：services测试可用isolated_runtime；默认guard网络，finally恢复全局状态。

L508–L534（整文件hash见表）：

```python
@contextlib.contextmanager
def isolated_runtime(
    tmp_path: Path,
    *,
    guard_network: bool = True,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
    **kwargs: Any,
) -> Iterator[Path]:
    """重定向到 tmp 并在退出时无条件恢复；默认同时启用网络 guard。"""
    snap, admin_root = redirect_runtime(tmp_path, **kwargs)
    active_token = _ACTIVE_ROOT.set(admin_root)
    try:
        if guard_network:
            with block_external_network(
                allow_endpoints=allow_endpoints, allow_unix_paths=allow_unix_paths
            ):
                yield admin_root
        else:
            yield admin_root
    finally:
        try:
            restore_runtime(snap)
        finally:
            _ACTIVE_ROOT.reset(active_token)


```

### .phase1-evidence/stages/S01/rework01/run_regression_tmp_home.py

只读证据脚本：跨目录收集前设临时HOME/清理key并初始化临时配置。不要改脚本。

L27–L51（整文件hash见表）：

```python
with tempfile.TemporaryDirectory(prefix="s01-rework-regression-") as bootstrap:
    for name in tuple(os.environ):
        if "API_KEY" in name or name.startswith(
            ("OPENAI_", "ANTHROPIC_", "CODEBUDDY_", "DEEPTUTOR_CODEBUDDY_")
        ):
            os.environ.pop(name, None)
    os.environ["DEEPTUTOR_HOME"] = bootstrap
    os.environ["DEEPTUTOR_CODEBUDDY_AUTH_FILE"] = str(Path(bootstrap) / "missing-auth.json")

    from deeptutor.services.setup.init import init_user_directories
    from deeptutor.services.config import ensure_runtime_settings_files

    init_user_directories()
    ensure_runtime_settings_files()

    import pytest

    args = sys.argv[1:] or [
        "-q",
        "tests/phase1",
        "tests/services",
        "tests/api",
    ]
    result = pytest.main(args)
    raise SystemExit(result)
```

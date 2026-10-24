# S06 返修：已探索的文件清单 + 关键片段

探索日期：2026-10-16，HEAD 9723f953cb6ca56f13603f76c5d07e1e2f1f4473，当前S06审查为changes_requested。执行入口REWORK_S06.txt；本包只定位本轮R1–R6。hash吻合即可复用原样片段，不重读全仓/历史57卡。编辑需要时仅定向补读当前符号，不恢复旧hash。

业务已能走默认描述→真实文本索引/检索；137项定向与2940项相关回归通过。缺口在实际边界：loader仅检叶且根仍follow；计费在成功后；legacy仍read_bytes/字符串complete；helper调用的真实factory会内部重试甚至去图；pipeline先发布version，initializer后写metadata；ready删除进度且科目投影白名单丢字段；新run首事件和metadata串旧值；PDF像素门漏计。完整证据/完成条件以返修指令及独立probe为准。

新增四接缝factory/manager/uploads/material_manifest已明确窄授权，禁止因此改通用SDK、全局状态机、来源/上传规则。阶段总范围15，本轮14（document_extractor只读）；59条当前源码基准中45只读。59是当前可复核基准，不是accepted声明。当前所有返修目标文件已存在，无需创建新模块。

独立probe含18方法、3个合法控制，含子场景18个目标失败；真实factory测试只替provider/config，不替factory或重试逻辑。首次试跑两个abstract-method框架错误已经修正，最后sealed命令零框架错误；旧日志保留，不算行为证据。探针源文件只读；新增永久断言放P26/P27/P28测试。

## 文件清单与指纹

| 文件 | SHA-256 | 单元/关键点 |
|---|---|---|
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/image_description.py` | `c6f04445d0a906ca3eec569dfd25ca28517ebee40cb3990445e182e72e1e1e36` | R1/R2：仅叶O_NOFOLLOW、配置异常逃逸、factory未禁用内部重试/去图；_ORIGINALS/_live仅为替身多路兼容。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/document_loader.py` | `85cfeec2f4fc54d8a6d791e81b64b29b21d88c739e63cec1a5cf4bd646e8ff34` | R1/R2：root.is_dir/os.walk跟随根；成功后才计费；legacy绕过受限读取/完整响应/超时。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/pipelines/llamaindex/pipeline.py` | `2a1d62ddcb1eaaa288c6efda426c3a30d7206484d61d0d1b14bfd8b812bcbbf6` | R3：索引persist后直接write_version_meta，随后initializer元数据失败无法撤销；S05 guard/ContextVar保持。 |
| `/home/albert/selflearn/selflearn/deeptutor/knowledge/initializer.py` | `22058883bb0b3f8b73f032cd1fdc2579cf72677bdff4e2fb4b93584cf9ead9ff` | R3/R4：坏JSON降空对象；只在非None时写coverage而保留旧字段；reset晚于前置进度。 |
| `/home/albert/selflearn/selflearn/deeptutor/knowledge/progress_tracker.py` | `37783b214fbe4db44a9b6fe01936809b2a9930c1197b7ffe440b3d6c6b55ba4c` | R4/R5：同task/None的新run需显式reset；_save_progress调用manager ready后字段消失。 |
| `/home/albert/selflearn/selflearn/deeptutor/knowledge/manager.py` | `e03433263d655071812ceba5d88338d88246e362041bbc68e7e2b8e7abb32f8c` | R5新增窄授权：ready删除progress是原UI稳定语义，要另存安全coverage，不能恢复完成横幅/重写状态机。 |
| `/home/albert/selflearn/selflearn/deeptutor/subjects/uploads.py` | `80362a15dff676fd9fcfa991cd9ad67bc089c2b34d95d12531562670e0e8f55b` | R5新增窄授权：只读读取目前仅返回status/progress/updated_at；其余上传事务/预留保持。 |
| `/home/albert/selflearn/selflearn/deeptutor/subjects/material_manifest.py` | `dce70f0a3fa4159b6cfc5efc4696831995ebc2f1ab44937dc33c640f596eb94f` | R5新增窄授权：固定安全progress投影需要显式加入coverage，不能返回raw进度。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/llm/factory.py` | `8710db552f199dd8156152fda44513abb1a4f3c4f9a01cd495a666b0d01918f5` | R2新增窄授权：默认retry_delays及allow_image_fallback；新增逐调用严格选项，其他调用默认行为不变。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/llm/provider_core/base.py` | `a035f72f33173ba5f2467bea08ceef80833096de394ed2c92c7874ff8ab14b5b` | 只读R2实际wire机制：非瞬态错误可移除图片再问一次，helper顶层一次调用不是一次请求。 |
| `/home/albert/selflearn/selflearn/deeptutor/utils/document_images.py` | `460097cad01d440690fc5f9bb23ecbe7a7d311d2266382a615af7787e52889e4` | R6：小像素门直接continue，漏skip计数；rejected_xrefs去重须保留。 |
| `/home/albert/selflearn/selflearn/deeptutor/services/rag/index_versioning.py` | `02e77206ada0c8e2fd759316ed2ab1e1e2e315d6c908e641de5e0850f6cfcaba` | 只读R3：发布meta、读路径有signature和无signature分支；fresh rebuild目录归属与安全撤销。 |
| `/home/albert/selflearn/selflearn/deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 只读R3：缺失才用default，已有坏对象/编码/非有限数字必须报错；路径先confined。 |
| `/home/albert/selflearn/selflearn/tests/phase1/test_p1_26.py` | `52f81c9633360849820fc2a994a116e5ddaac0bf9e4992e7a722a86caea9029f` | R2测试盲点：现有替身在factory.complete_response上层，观察不到provider retry/去图。 |
| `/home/albert/selflearn/selflearn/tests/phase1/test_p1_27.py` | `5a1626f3472182ce5283db61c7058bace83bec9ac24852fc2cea967ed31f4eaf` | R4/R5测试盲点：第二次只看最终.progress；注册表只验processing，完成只验文件/事件。 |
| `/home/albert/selflearn/selflearn/tests/phase1/test_p1_28.py` | `98c2683050fb9b554856ac4b594d99ec25fe5d6995cd1b60d6e7446ac6360584` | R6：已有真实PDF正向fixture可复用，但补小像素/重复xref跳过计数。 |
| `/home/albert/selflearn/selflearn/deeptutor/utils/document_extractor.py` | `7e09575b57680d140de005c167126f1d3d7a7bda575b0de6118f748379144b89` | 只读P28消费者：collection.images被发为附件；本轮不改extractor或reading消费者。 |
| `/home/albert/selflearn/selflearn/.phase1-evidence/reviews/S06/probe_s06.py` | `78f156ac8db397c145c976281d7ee0cf190bc8f6a710147b2fbeffa7f6b8ecbd` | 只读独立验收探针：真实factory/provider重试层、合法ready前置和真实HTTP；原样跑，不编辑。 |

## 原样关键片段

行号对应本次探索时版本，编辑后按符号定位。仅摘录当前关键效果；这不是要求保留错误行为。

### deeptutor/services/rag/pipelines/llamaindex/image_description.py

R1/R2：仅叶O_NOFOLLOW、配置异常逃逸、factory未禁用内部重试/去图；_ORIGINALS/_live仅为替身多路兼容。

L338–L369：

```python
        info = os.lstat(path)
    except OSError:
        return _ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    if stat_module.S_ISLNK(info.st_mode) or not stat_module.S_ISREG(info.st_mode):
        # Symlinked or non-regular leaves are never followed into the read.
        return _ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    if info.st_size < MIN_IMAGE_BYTES or info.st_size > MAX_IMAGE_BYTES:
        return _ImageInspection(skip_reason=SKIP_BUDGET)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        handle = os.open(path, flags)
    except OSError:
        return _ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    try:
        stat_result = os.fstat(handle)
        if not stat_module.S_ISREG(stat_result.st_mode):
            return _ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
        size = stat_result.st_size
        if size < MIN_IMAGE_BYTES or size > MAX_IMAGE_BYTES:
            return _ImageInspection(skip_reason=SKIP_BUDGET)
        chunks: list[bytes] = []
        remaining = MAX_IMAGE_BYTES + 1
        while remaining > 0:
            chunk = os.read(handle, min(remaining, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        return _ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
```

L456–L479：

```python
    strategy = _live("get_vision_strategy", vision_strategy_module)()
    dedicated = _live("resolve_vision_runtime_config", provider_runtime)()
    if strategy in ("prefer_dedicated", "dedicated_only"):
        return [("dedicated", dedicated)] if _usable(dedicated) else []

    main = _live("resolve_llm_runtime_config", provider_runtime)()
    candidates: list[tuple[str, Any]] = []
    if _usable(main) and _live("supports_vision", capabilities_module)(
        getattr(main, "binding", ""), getattr(main, "model", None)
    ):
        candidates.append(("main", main))
    if _usable(dedicated):
        candidates.append(("dedicated", dedicated))
    return candidates[:MAX_CANDIDATE_ATTEMPTS]


def failure_kind(exc: BaseException) -> str:
    """Stable internal diagnostic for one failed description attempt.

    Public results only ever say ``vision_failed``; this mapping keeps the
    empty / truncated / budget / timeout / provider cases distinguishable for
    tests and server logs without exposing the exception text.
    """
    from deeptutor.services.llm.exceptions import (
```

L505–L536：

```python
    response = await asyncio.wait_for(
        factory.complete_response(
            prompt=IMAGE_DESCRIPTION_PROMPT,
            system_prompt=IMAGE_DESCRIPTION_SYSTEM_PROMPT,
            model=getattr(config, "model", None),
            api_key=getattr(config, "api_key", "") or None,
            base_url=getattr(config, "base_url", None),
            api_version=getattr(config, "api_version", None),
            binding=getattr(config, "binding", None),
            extra_headers=getattr(config, "extra_headers", None) or None,
            max_tokens=DESCRIBE_MAX_TOKENS,
            image_data=payload["base64"],
            image_mime_type=payload["mime_type"],
            # The *source document's* name, never the cache asset path.
            image_filename=source_file,
        ),
        timeout=DESCRIBE_TIMEOUT_SECONDS,
    )
    return _live("validate_subject_response", generation_module)(
        response, max_tokens=DESCRIBE_MAX_TOKENS
    )


def _header(source_file: str, page: int | None, location: str | None) -> str:
    header = f"{DESCRIPTION_PREFIX}{source_file}"
    if page is not None:
        header += f"（第 {page} 页）"
    if location:
        header += f"（位置：{location}）"
    return header


```

### deeptutor/services/rag/pipelines/llamaindex/document_loader.py

R1/R2：root.is_dir/os.walk跟随根；成功后才计费；legacy绕过受限读取/完整响应/超时。

L397–L435：

```python
        root = Path(asset_dir)
        try:
            if not root.is_dir():
                return []
        except OSError:  # pragma: no cover - defensive
            return []

        positions = self._block_positions(blocks)
        images: list[_ImageSource] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for filename in sorted(filenames):
                child = Path(dirpath) / filename
                if child.suffix.lower() not in FileTypeRouter.IMAGE_EXTENSIONS:
                    continue
                if not _is_regular_leaf(child):
                    coverage.observe(origin, None, SKIP_UNSUPPORTED_IMAGE)
                    self.logger.warning(
                        "Skipped image asset that is not a regular file inside the "
                        "parsing asset root: %s",
                        child.name,
                    )
                    continue
                try:
                    asset_ref = asset_ref_from_root(child, root)
                except ValueError:
                    coverage.observe(origin, None, SKIP_UNSUPPORTED_IMAGE)
                    self.logger.warning(
                        "Skipped image asset outside the parsing asset root: %s",
                        child.name,
                    )
                    continue
                page, location = self._position_for(asset_ref, positions)
                images.append(
                    _ImageSource(
                        path=child,
                        origin=origin,
                        asset_ref=asset_ref,
                        source_file=origin.name,
```

L529–L555：

```python
    def _budget_allows(self, source: _ImageSource, budgets: dict[str, ImageBudget]) -> bool:
        """Whether one more image of this source still fits the C09 caps.

        Checked immediately before the image is described/embedded — the caps are
        per *source document*, and the counters are charged only after an image
        really became a node, so a run can never admit image 13 of 12.
        """
        budget = budgets.setdefault(str(source.origin), ImageBudget())
        size = _leaf_size(source.path) or 0
        return (
            budget.count < budget.max_images
            and budget.total_bytes + size <= budget.max_total_bytes
        )

    def _charge_budget(self, source: _ImageSource, budgets: dict[str, ImageBudget]) -> None:
        """Charge one successfully indexed image against its document budget."""
        budget = budgets.setdefault(str(source.origin), ImageBudget())
        size = _leaf_size(source.path) or 0
        budget.count += 1
        budget.total_bytes += size

    def _skip_over_budget(self, source: _ImageSource, coverage: _ImageCoverage) -> None:
        coverage.observe(source.origin, source.asset_ref, SKIP_BUDGET)
        self.logger.warning(
            "Skipped image beyond the per-document budget: %s", source.asset_ref
        )

```

L600–L609：

```python
            self._charge_budget(source, budgets)
            documents.append(
                Document(
                    text=description.text,
                    metadata=_description_metadata(source, description),
                )
            )
        if documents:
            self.logger.info(
                f"Indexed {len(documents)} image description(s) as text documents"
```

L631–L651：

```python
                image_payload = self._load_image_payload(source.path)
                description = await self._describe_image(
                    source.path,
                    image_payload["base64"],
                    image_payload["mimetype"],
                )
                if not description:
                    self.logger.warning(
                        "Skipped image because the configured multimodal LLM "
                        f"returned no description: {source.path.name}"
                    )
                    coverage.observe(source.origin, source.asset_ref, SKIP_VISION_FAILED)
                    continue
                contents.append({"image": image_payload["data_uri"]})
                embedded.append(source)
                descriptions.append(description)
                self._charge_budget(source, budgets)
            except OSError as exc:
                self.logger.error(f"Failed to read image {source.path.name}: {exc}")
                coverage.observe(source.origin, source.asset_ref, SKIP_UNSUPPORTED_IMAGE)
            except Exception as exc:
```

L711–L726：

```python
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

    def _append_if_nonempty(self, documents: list[Any], file_path: Path, text: str) -> bool:
```

### deeptutor/services/rag/pipelines/llamaindex/pipeline.py

R3：索引persist后直接write_version_meta，随后initializer元数据失败无法撤销；S05 guard/ContextVar保持。

L350–L418：

```python
    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        progress_callback = kwargs.get("progress_callback")
        image_coverage_callback = kwargs.get("image_coverage_callback")
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
            # This run's image coverage travels with the load result. Project it
            # before the zero-node decision so a rejected initialization still
            # reports *why* the images are missing.
            coverage = getattr(documents, "image_coverage", None)
            coverage_warning = getattr(documents, "image_coverage_warning", None)
            if coverage is not None:
                self.logger.info(
                    f"Image coverage for KB '{kb_name}': {coverage}"
                    + (f" (warning: {coverage_warning})" if coverage_warning else "")
                )
            _emit_image_coverage(image_coverage_callback, coverage, coverage_warning)
            if not documents:
                self.logger.error("No valid documents found")
                # Nothing indexable: drop the version dir created for this
                # attempt so a failed run cannot look like a published version.
                self._cleanup_failed_version_dir(storage_dir, signature)
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
```

### deeptutor/knowledge/initializer.py

R3/R4：坏JSON降空对象；只在非None时写coverage而保留旧字段；reset晚于前置进度。

L95–L127：

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
        # Additive coverage of the run that just finished: the merge above keeps
        # every pre-existing field.
        if self.image_coverage is not None:
            metadata["image_coverage"] = self.image_coverage
            metadata["image_coverage_warning"] = self.image_coverage_warning

        atomic_write_json(metadata_file, metadata)

        try:
            # Scope the config write to *this* initializer's own KB root.
            # ``get_kb_config_service()`` is hard-wired to the caller's global
            # KB root, so using it here registered a subject-scoped KB in the
            # global registry as a phantom entry (no directory behind it) every
            # time a subject material finished indexing.
            from deeptutor.services.config.knowledge_base_config import (
```

L174–L217：

```python
    async def process_documents(
        self,
    ) -> bool:
        """Process documents with the KB's bound provider."""
        provider = self.rag_provider

        self.progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Starting to process documents with {provider} provider...",
            current=0,
            total=0,
        )

        # recursive=True so documents organized into folders are indexed too
        # (folders are display-only and don't otherwise affect retrieval).
        doc_files = FileTypeRouter.collect_supported_files(self.raw_dir, recursive=True)

        if not doc_files:
            self.progress_tracker.update(
                ProgressStage.ERROR,
                "No documents found to process",
                error="No documents found",
            )
            raise ValueError("No documents found to process")

        self.progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Found {len(doc_files)} documents, starting to process...",
            current=0,
            total=len(doc_files),
        )

        rag_service = RAGService(
            kb_base_dir=str(self.base_dir),
            provider=provider,
        )
        file_paths = [str(doc_file) for doc_file in doc_files]

        self._reset_image_coverage()

        def _on_progress(batch_num, total_batches):
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Embedding batches: {batch_num}/{total_batches} complete",
```

L226–L256：

```python
            success = await rag_service.initialize(
                kb_name=self.kb_name,
                file_paths=file_paths,
                progress_callback=_on_progress,
                image_coverage_callback=_on_image_coverage,
            )
            if not success:
                self.progress_tracker.update(
                    ProgressStage.ERROR,
                    "Document processing failed",
                    error="RAG pipeline returned failure",
                    image_coverage=self.image_coverage,
                    image_coverage_warning=self.image_coverage_warning,
                )
                raise RuntimeError("RAG pipeline returned failure")

            self._update_metadata_with_provider(provider)
            self.progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                "Documents processed successfully",
                current=len(doc_files),
                total=len(doc_files),
                image_coverage=self.image_coverage,
                image_coverage_warning=self.image_coverage_warning,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing documents: {error_msg}")
            self.progress_tracker.update(
                ProgressStage.ERROR,
                "Failed to process documents",
```

### deeptutor/knowledge/progress_tracker.py

R4/R5：同task/None的新run需显式reset；_save_progress调用manager ready后字段消失。

L73–L85：

```python
    def _remembered_image_coverage(self) -> tuple[dict, str | None] | None:
        if self._image_coverage is None:
            return None
        if self._image_coverage_task != self.task_id:
            # Another task owns this tracker now; its numbers must never be
            # attributed to the previous run.
            self.reset_image_coverage()
            return None
        return self._image_coverage, self._image_coverage_warning

    def _notify(self, progress: dict):
        """Notify progress update (call all callbacks)"""
        from deeptutor.runtime.mode import is_server
```

L117–L145：

```python
            if stage == "completed":
                status = "ready"
            elif stage == "error":
                status = "error"
            elif stage in [
                "initializing",
                "processing_documents",
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
```

L203–L215：

```python
        if image_coverage is not None or image_coverage_warning is not None:
            self.record_image_coverage(image_coverage, image_coverage_warning)
        remembered = self._remembered_image_coverage()
        if remembered is not None:
            progress["image_coverage"] = remembered[0]
            if remembered[1]:
                progress["image_coverage_warning"] = remembered[1]

        if error:
            progress["error"] = error
            progress["stage"] = ProgressStage.ERROR.value
        if error_code:
            progress["error_code"] = error_code
```

### deeptutor/knowledge/manager.py

R5新增窄授权：ready删除progress是原UI稳定语义，要另存安全coverage，不能恢复完成横幅/重写状态机。

L443–L465：

```python
        if status == "ready":
            # Ready KBs should look like stable resources in the UI instead of
            # permanently carrying a "completed" progress banner.
            kb_config.pop("progress", None)
            kb_config.pop("last_error", None)
            kb_config.pop("last_error_at", None)
            if progress is not None:
                kb_config["last_completed_at"] = (
                    progress.get("timestamp") or datetime.now().isoformat()
                )
                if index_changed:
                    kb_config["last_indexed_at"] = kb_config["last_completed_at"]
                    if indexed_count is not None:
                        kb_config["last_indexed_count"] = max(indexed_count, 0)
                    if index_action:
                        kb_config["last_indexed_action"] = index_action
        elif status == "error":
            if progress is not None:
                kb_config["progress"] = progress
                kb_config["last_error"] = progress.get("error") or progress.get("message")
                kb_config["last_error_at"] = progress.get("timestamp") or datetime.now().isoformat()
        elif progress is not None:
            kb_config["progress"] = progress
```

### deeptutor/subjects/uploads.py

R5新增窄授权：只读读取目前仅返回status/progress/updated_at；其余上传事务/预留保持。

L593–L625：

```python
def read_kb_status(base_dir: Path | str, kb_name: str) -> dict | None:
    """One KB's status straight from ``kb_config.json`` — **no side effects**.

    ``KnowledgeBaseManager`` creates its directory and rewrites a normalized
    config on construction, so a read-only projection must not go through it.
    Missing file/entry means "no status"; an existing file that is not a JSON
    object is corruption rather than a silent default.
    """
    config_path = Path(base_dir) / KB_CONFIG_NAME
    text = json_store._read_text(config_path)
    if text is None:
        return None
    payload = json_store._strict_loads(text, source=config_path)
    if not isinstance(payload, dict):
        raise json_store.corrupt_error(KB_CONFIG_NAME, "顶层不是对象")
    entries = payload.get("knowledge_bases")
    if not isinstance(entries, dict):
        return None
    entry = entries.get(kb_name)
    if not isinstance(entry, dict):
        return None
    return {
        "status": entry.get("status", "unknown"),
        "progress": entry.get("progress"),
        "updated_at": entry.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Same-KB busy state: live worker *and* accepted-but-not-started reservation
# ---------------------------------------------------------------------------
_RESERVATIONS: dict[str, dict] = {}
_RESERVATIONS_LOCK = threading.Lock()
```

### deeptutor/subjects/material_manifest.py

R5新增窄授权：固定安全progress投影需要显式加入coverage，不能返回raw进度。

L590–L610：

```python
    projection: dict[str, Any] = {
        "status": status,
        "progress": _bounded_progress(status, percent=percent, stage=stage),
        "updated_at": manager_status.get("updated_at"),
        "documents": documents,
        "materials_in_sync": in_sync,
        "busy": pending,
        "worker_alive": bool(worker_alive),
        "queued": bool(queued),
    }
    if task_id:
        projection["task_id"] = task_id
    if index_state is not None:
        projection["indexed_documents"] = int(index_state.get("documents", 0))
        projection["index_sources"] = "ready" if status == "ready" else "stale"
    else:
        projection["index_sources"] = "unknown"
    # The current index version and the newest attempt are separate facts: a
    # failed task must be visible without erasing the last published version.
    projection["published_source"] = (
        {
```

### deeptutor/services/llm/factory.py

R2新增窄授权：默认retry_delays及allow_image_fallback；新增逐调用严格选项，其他调用默认行为不变。

L338–L361：

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
```

L391–L413：

```python
        response = await provider.chat_with_retry(
            messages=request_messages,
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            retry_delays=retry_delays,
            allow_image_fallback=not supports_vision(capability_binding, config.model),
            **extra_kwargs,
        )
    except Exception as exc:
        raise map_error(exc, provider=config.provider_name) from exc

    if response.finish_reason == "error":
        raise map_error(
            RuntimeError(response.content or "LLM request failed"), provider=config.provider_name
        )
    return response


async def complete(
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    model: str | None = None,
    api_key: str | None = None,
```

### deeptutor/services/llm/provider_core/base.py

只读R2实际wire机制：非瞬态错误可移除图片再问一次，helper顶层一次调用不是一次请求。

L326–L348：

```python
                if allow_image_fallback and has_image_parts(messages):
                    logger.warning(
                        "Non-transient LLM error with image content; model is not"
                        " known vision-capable, retrying once without images"
                    )
                    retry_response = await call(
                        messages=strip_image_parts(messages),
                        tools=tools,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        tool_choice=tool_choice,
                        **kwargs,
                    )
                    if retry_response.finish_reason != "error":
                        strip_image_parts_inplace(messages)
                    return retry_response
                return response

            if attempt > len(delays):
                return response

```

### deeptutor/utils/document_images.py

R6：小像素门直接continue，漏skip计数；rejected_xrefs去重须保留。

L577–L593：

```python
                        int(extracted.get("width") or 0) < 64
                        or int(extracted.get("height") or 0) < 64
                    ):
                        continue
                    ext = _normalise_ext("." + (extracted.get("ext") or ""))
                    if ext in {".emf", ".wmf"}:
                        budget.register_vector_skip()
                        continue
                    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                        budget.register_other_skip()
                        continue
                    admitted = budget.try_admit(ext, raw)
                    if admitted is not None:
                        images.append(admitted)
                        xref_to_index[xref] = len(images) - 1
                        indices.append(xref_to_index[xref])
                        admitted_on_page += 1
```

### deeptutor/services/rag/index_versioning.py

只读R3：发布meta、读路径有signature和无signature分支；fresh rebuild目录归属与安全撤销。

L263–L280：

```python
def write_version_meta(
    kb_dir: Path, signature: EmbeddingSignature, storage_dir: Path | None = None
) -> None:
    """Persist metadata next to the LlamaIndex store."""
    target = storage_dir or resolve_storage_dir_for_write(kb_dir, signature)
    target.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": target.name,
        "signature": signature.hash(),
        **asdict(signature),
        "layout": "flat" if target.parent == kb_dir else "nested_legacy",
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
    }
    with open(target / META_FILENAME, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def resolve_storage_dir_for_read(
```

L280–L301：

```python
def resolve_storage_dir_for_read(
    kb_dir: Path, signature: Optional[EmbeddingSignature]
) -> Optional[Path]:
    """Return the storage dir to read for the active embedding signature."""
    if signature is not None:
        match = find_matching_version(kb_dir, signature)
        if match:
            return Path(str(match["storage_path"]))
    else:
        latest_flat = _latest_ready_flat_version(kb_dir)
        if latest_flat:
            return Path(str(latest_flat["storage_path"]))

    root_legacy = legacy_storage_dir(kb_dir)
    if _is_storage_ready(root_legacy):
        return root_legacy

    return None


def resolve_storage_dir_for_write(kb_dir: Path, signature: Optional[EmbeddingSignature]) -> Path:
    """Return the flat storage dir to write for the active embedding signature.
```

L315–L326：

```python
def resolve_storage_dir_for_rebuild(kb_dir: Path, signature: Optional[EmbeddingSignature]) -> Path:
    """Return a fresh flat storage dir for a full index rebuild.

    Incremental writes reuse a matching flat version, but a full rebuild should
    not overwrite the last matching version until the new index has been
    persisted successfully. Keeping the old version in place lets a failed
    rebuild remain diagnosable and avoids stale vector-store files.
    """
    _ = signature
    target = _next_flat_version_dir(kb_dir)
    target.mkdir(parents=True, exist_ok=True)
    return target
```

### deeptutor/subjects/json_store.py

只读R3：缺失才用default，已有坏对象/编码/非有限数字必须报错；路径先confined。

L339–L358：

```python
def read_object(path: Path, *, default: dict) -> dict:
    """Read a top-level object document.

    A **fresh deep copy** of *default* when the file does not exist — never the
    caller's object itself, so a mutable default cannot leak between calls.
    An existing file is returned as stored, keeping unknown historical fields.
    """
    path = Path(path)
    text = _read_text(path)
    if text is None:
        return copy.deepcopy(default)
    value = _strict_loads(text, source=path)
    if not isinstance(value, dict):
        raise _corrupt(path, "顶层不是对象")
    return value


# ---------------------------------------------------------------------------
# Unlocked atomic writers
# ---------------------------------------------------------------------------
```

### tests/phase1/test_p1_26.py

R2测试盲点：现有替身在factory.complete_response上层，观察不到provider retry/去图。

L147–L164：

```python
def vision(monkeypatch: pytest.MonkeyPatch):
    """Install a vision stub at the real factory seam plus deterministic config."""

    def install(*outcomes: Any, dedicated: Any = _DEDICATED, main: Any = _MAIN, vision_capable: bool = True):
        stub = _VisionStub(*outcomes)
        helpers.install_provider_stubs(monkeypatch, llm=stub)
        monkeypatch.setattr(desc, "get_vision_strategy", lambda: "auto")
        monkeypatch.setattr(desc, "resolve_llm_runtime_config", lambda *a, **k: main)
        monkeypatch.setattr(desc, "resolve_vision_runtime_config", lambda *a, **k: dedicated)
        monkeypatch.setattr(desc, "supports_vision", lambda binding, model=None: vision_capable)
        return stub

    return install


def _describe(image: Path, **kwargs: Any):
    params = {"source_file": "notes.pdf", "asset_ref": "images/figure.png"}
    params.update(kwargs)
```

### tests/phase1/test_p1_27.py

R4/R5测试盲点：第二次只看最终.progress；注册表只验processing，完成只验文件/事件。

L965–L994：

```python
def test_initializer_second_run_does_not_reuse_the_previous_coverage(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_streams
) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage

    initializer, tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
    assert asyncio.run(initializer.process_documents()) is True
    assert json.loads((kb_dir / ".progress.json").read_text())["image_coverage"] == _COVERAGE

    # A second run whose pipeline reports nothing must not inherit run #1.
    from deeptutor.knowledge import initializer as initializer_module

    class _SilentRAG:
        def __init__(self, **kwargs) -> None:
            pass

        async def initialize(self, kb_name, file_paths, **kwargs):
            return True

    monkeypatch.setattr(initializer_module, "RAGService", lambda **kwargs: _SilentRAG())
    assert asyncio.run(initializer.process_documents()) is True

    saved = json.loads((kb_dir / ".progress.json").read_text())
    assert "image_coverage" not in saved
    assert "image_coverage_warning" not in saved
    tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1)
    assert "image_coverage" not in json.loads((kb_dir / ".progress.json").read_text())

```

L944–L972：

```python
    # kb_config progress carries it while the KB is still processing.
    manager = KnowledgeBaseManager(base_dir=str(kb_dir.parent))
    status = manager.get_kb_status("kb") or {}
    assert status.get("progress", {}).get("image_coverage") == _COVERAGE

    # The subject task's final COMPLETED update is written by the caller and has
    # no coverage of its own: the tracker must keep this run's numbers.
    tracker.update(ProgressStage.COMPLETED, "done", current=1, total=1, indexed_count=1)
    final = json.loads((kb_dir / ".progress.json").read_text(encoding="utf-8"))
    assert final["stage"] == "completed"
    assert final["image_coverage"] == _COVERAGE
    assert final["image_coverage_warning"] == _WARNING

    progress_events = [event for event in task_streams.events if event[1] == "progress"]
    assert progress_events, "the task stream must see progress events"
    assert progress_events[-1][2]["image_coverage"] == _COVERAGE
    assert progress_events[-1][2]["stage"] == "completed"
    assert notifications[-1]["image_coverage"] == _COVERAGE
    assert notifications[-1]["image_coverage_warning"] == _WARNING


def test_initializer_second_run_does_not_reuse_the_previous_coverage(
    p1_runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_streams
) -> None:
    from deeptutor.knowledge.progress_tracker import ProgressStage

    initializer, tracker, _stub, kb_dir = _run_initializer(
        tmp_path, monkeypatch, coverage=_COVERAGE, warning=_WARNING
    )
```

### tests/phase1/test_p1_28.py

R6：已有真实PDF正向fixture可复用，但补小像素/重复xref跳过计数。

L219–L241：

```python
def test_pdf_markers_land_on_the_page_that_holds_the_image(p1_runtime: Path) -> None:
    page1_image = _png_bytes(seed=4)
    page2_image = _png_bytes(seed=5)
    data = _pdf_bytes([("page one text", [page1_image]), ("page two text", [page2_image])])
    record = _record("paper.pdf", data, record_id="doc-c")

    doc_texts, updated = extractor.extract_documents_from_records([record])

    text = _assert_stats_consistent(doc_texts, updated, "paper.pdf")
    page_one, _, page_two = text.partition("--- Page 2 ---")
    assert find_markers(page_one) == [(1, "image-01.png")]
    assert find_markers(page_two) == [(2, "image-02.png")]

    records = _image_records(updated)
    assert [item["filename"] for item in records] == ["paper-图1.png", "paper-图2.png"]
    assert [item["id"] for item in records] == ["doc-c-e01", "doc-c-e02"]
    assert _emitted_bytes(records) > 0
    decoded = [base64.b64decode(item["base64"]) for item in records]
    # PyMuPDF re-encodes the embedded stream, so the emitted bytes are asserted
    # to be real, decodable images (and distinct), not byte-identical copies.
    for payload in decoded:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
```

### deeptutor/utils/document_extractor.py

只读P28消费者：collection.images被发为附件；本轮不改extractor或reading消费者。

L929–L947：

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

### .phase1-evidence/reviews/S06/probe_s06.py

只读独立验收探针：真实factory/provider重试层、合法ready前置和真实HTTP；原样跑，不编辑。

L216–L233：

```python
    def test_real_factory_does_not_promote_an_imageless_fallback_to_ocr(self):
        file = self.root / 'figure.png'; file.write_bytes(png())
        provider = self.wire(lambda has_image, n: LLMResponse(
            content='unsupported image input' if has_image else 'PHANTOM ANSWER WITHOUT SEEING IMAGE',
            finish_reason='error' if has_image else 'stop'))
        result = asyncio.run(desc.describe_image_for_index(file, source_file='source.pdf'))
        self.assertEqual(result.skip_reason, 'vision_failed', f'phantom OCR: {result.text}; wire={provider.wire_calls}')
        self.assertEqual(provider.wire_calls, [True])

    def test_real_factory_respects_one_wire_attempt_per_candidate(self):
        file = self.root / 'figure.png'; file.write_bytes(png())
        provider = self.wire(lambda has_image, n: LLMResponse(
            content='503 temporarily unavailable' if n == 1 else 'second attempt should not happen',
            finish_reason='error' if n == 1 else 'stop'))
        result = asyncio.run(desc.describe_image_for_index(file, source_file='source.pdf'))
        self.assertEqual(len(provider.wire_calls), 1, provider.wire_calls)
        self.assertEqual(result.skip_reason, 'vision_failed')

```

L280–L309：

```python
    def test_ready_keeps_coverage_in_registry_and_real_subject_http(self):
        sid = store.create_subject('review-subject', term='2026秋')['id']
        kb = 'assignment-kb'
        base = store.subject_kb_base_dir(sid); raw = base / kb / 'raw'; raw.mkdir(parents=True)
        (raw / 'source.txt').write_text('review body')
        materials = store.subject_dir(sid) / 'materials' / 'assignment'; materials.mkdir(parents=True, exist_ok=True)
        (materials / 'source.txt').write_text('review body')
        store.upsert_knowledge_record(sid, {'kb_name': kb, 'type': 'assignment', 'documents': 1})
        tracker = ProgressTracker(kb, base)
        tracker.update(ProgressStage.PROCESSING_DOCUMENTS, 'processing', image_coverage=dict(COVERAGE), image_coverage_warning=loader.IMAGE_COVERAGE_WARNING)
        tracker.update(ProgressStage.COMPLETED, 'done', current=1, total=1)
        entry = json.loads((base / 'kb_config.json').read_text())['knowledge_bases'][kb]
        with helpers.route_client() as client:
            response = client.get(f'{helpers.ROUTE_PREFIX}/{sid}/knowledge/{kb}/status')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'ready', response.text)
        with self.subTest(surface='registry'):
            actual = entry.get('image_coverage') or (entry.get('progress') or {}).get('image_coverage')
            self.assertEqual(actual, COVERAGE, entry)
        with self.subTest(surface='http'):
            payload = response.json()
            actual = payload.get('image_coverage') or (payload.get('progress') or {}).get('image_coverage')
            self.assertEqual(actual, COVERAGE, payload)

    def test_failed_metadata_commit_does_not_publish_a_new_version(self):
        init, _ = self.initializer()
        from deeptutor.services.rag.index_versioning import EmbeddingSignature, write_version_meta, find_matching_version
        sig = EmbeddingSignature(binding='openai', model='review-embed', dimension=2, base_url='', api_version='')
        old = init.kb_dir / 'version-1'; old.mkdir()
        (old / 'docstore.json').write_text('{}')
```

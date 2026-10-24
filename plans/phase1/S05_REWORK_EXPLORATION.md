# S05返修：已探索文件清单 + 关键片段

日期：2026-10-14；项目根：`/home/albert/selflearn/selflearn`。局部审查，不表示全仓库或真实供应商已验收。
本包配套`REWORK_S05.txt`；最新当前源码基准是`.phase1-evidence/stages/S05/review.json`所指changes_requested receipt的48条source_artifacts。旧S05提交report/归档、旧S04-final和其Unicode修复保留，不能恢复旧hash。
hash未变时复用下列定位与原样片段，只定向补读实现上下文；不重新orientation。范围、证据与完成门以REWORK_S05.txt为准，片段不是授权扩大到全局依赖文件。

## 实测结论

- 126项提交测试与12路径Ruff通过，机械证据12源码/19证据/25命令匹配；独立23方法含子场景有24处失败，零错误。
- 相关目录为2739 passed / 1 failed / 18历史skip；P30差值断言实测zero=0.20116055、delay=0.452074863，不满足差值>0.3。单独重跑通过，不能称已稳定。
- 临时音频part软链接实际改写tmp外部目标；null/软链接manifest读取、回滚遗漏、跨KB撤销成功记录、假ready、队列及实际回调串库均有独立复现。所有实验只使用tmp，不是实际用户数据。
- 原实现可保留：整批分类、流式限额/MIME、合法空转写、操作响应、busy字段、默认600秒及P30生产guard。只修具体失败，不重写整个阶段。

## 探索清单与当前整文件SHA256

| 路径 | SHA256 | 局部范围/用途 |
|---|---|---|
| `deeptutor/subjects/uploads.py` | `191ba601d7846bbe1b71d0a6513f98980e77b34ea8f85f78f55baed712736627` | L387–L414, L461–L475, L718–L750, L773–L797, L800–L825, L866–L883；R1/R3/R4：临时叶open、undo登记时机、共享元数据回滚、音频try边界、finalizer身份与run前缺门禁 |
| `deeptutor/subjects/material_manifest.py` | `2e95c2f01f9bcab4316c133c7bbcb43707805b88b7a410ad5323ec8ec96b6beb` | L269–L290, L369–L397, L435–L484；R1/R2：宽松缺失/null、单向materials比较、shape代替已发布fingerprint |
| `deeptutor/api/routers/subjects.py` | `b2915792ff4fa21d04bb2cbaab683bed9fb3693e43d15b28c6e95b9318922867` | L172–L204, L304–L322, L345–L374；R1/R4：GET构造manager有副作用、吞材料路径异常、初始化元数据、提交后才add_task |
| `deeptutor/services/asr/transcribe.py` | `5d8c35339e634c6670ad57f969ebb714c5d147a143c5f78164933ec5268d00c5` | L68–L94, L119–L139, L145–L162；R6：JSON只识别左花括号、配置读取在try外、IO错误kind |
| `deeptutor/services/rag/pipelines/llamaindex/pipeline.py` | `634be4de13419ef21641cb1e6f4224b017dda875b685df961b0a06330bb19d61` | L47–L54, L94–L113, L169–L196；R5：全局栈不能识别实际进度worker；复制context已有，可最小接线复用 |
| `tests/phase1/test_p1_30.py` | `bd3017f9a7284127a392ee09a44ab24dc125ba194bb3998acf0d7f5f7a612811` | L291–L326；R7：wall-clock上界和不成立的0.3s差值断言，生产锁本身保留 |
| `deeptutor/services/rag/pipelines/llamaindex/embedding_adapter.py` | `ed9ee52514d4a40243626dd2c284475b29dbef16afa5793a565df21a898b182f` | L110–L122, L163–L167；只读：真实embedding把共享属性callback传给client；setter作用于全局Settings模型 |
| `deeptutor/knowledge/manager.py` | `e03433263d655071812ceba5d88338d88246e362041bbc68e7e2b8e7abb32f8c` | L247–L260, L288–L306, L330–L337；只读：构造器会mkdir、配置归一化后可能atomic_write；GET不能直接复用有副作用的构造路径 |
| `deeptutor/knowledge/initializer.py` | `c2c7fffbae97bc94ba6188ddab42ac2464da9c9dc38591c67060d536086d5329` | L118–L139；只读：create_directory_structure重写metadata及注册，不适合无条件用于已有KB |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | L260–L282, L339–L353；只读S03基础：NOFOLLOW/NONBLOCK与strict read_object，拒绝已有null；不可改共享fixture/存储协议 |
| `tests/phase1/test_p1_16.py` | `d9a5fa1501586b324fe47d0b9d7126f2a5c210145971d384d5ef061d13894282` | 已探索音频、wire、错误与软链接测试；新增R1/R3/R6回归 |
| `tests/phase1/test_p1_18.py` | `990e7bb295156a20bc305e8989132c88b20926c7c75e26d8fb2b3d6aec7024a6` | 已探索12项提交/回滚场景；补replace后、共享元数据交错、排队失败 |
| `tests/phase1/test_p1_19.py` | `7f41a929018735cf24e9ebeda2910142dbf1723f3df7132f4a8ca1f8b3399c41` | 已探索状态与_drive_task；同名测试只查count，未查同大小fingerprint |
| `tests/phase1/test_p1_29.py` | `dafe0b316c40e44c3b6a3caa327e9bbfc7d3ed437f9b68e6fdd36885df995b95` | 已探索11项生命周期场景；栈顶回调模拟不能证明真实adapter归属 |
| `tests/phase1/test_p1_17.py` | `f1105020d81a26d030b3eb3897312051101a55e06b8838547c02c74cc51779d0` | 只读保留整批分类26项；仍需回归 |
| `deeptutor/services/embedding/client.py` | `a9eeebe77bebb4489b7c561da8f8d5130bf154d872239d6cf53619e753a9f21d` | 只读保留类定义guard；不因P30测试失败改正确生产锁 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 只读：显式isolated_runtime、网络拦截、fake provider；FakeEmbeddingClient本身不会发progress，真实回调测试需会回调的假client |

## 原样关键片段

### `deeptutor/subjects/uploads.py`

R1/R3/R4：临时叶open、undo登记时机、共享元数据回滚、音频try边界、finalizer身份与run前缺门禁

L387–L414（原样）：
```python
def _atomic_copy(source: Path, target: Path) -> None:
    """Copy *source* next to *target* and replace it atomically."""
    target = Path(target)
    part = target.parent / f".{target.name}{PART_SUFFIX}"
    try:
        with open(source, "rb") as src, open(part, "wb") as dst:
            shutil.copyfileobj(src, dst, WORK_CHUNK)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(part, target)
    except OSError as exc:
        _unlink(part)
        raise StorageIOError("资料写入失败。", path=target.name, cause=exc) from exc


def _write_text_atomic(target: Path, text: str) -> None:
    target = Path(target)
    part = target.parent / f".{target.name}{PART_SUFFIX}"
    try:
        with open(part, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, target)
    except OSError as exc:
        _unlink(part)
        raise StorageIOError("转写文本写入失败。", path=target.name, cause=exc) from exc
```

L461–L475（原样）：
```python
        if target.exists():
            backup = Path(backup_root) / f"{index:03d}-{target.name}"
            _atomic_copy(target, backup)
        _atomic_copy(staged.path, target)
        size, digest = _digest_of(target)
        if (size, digest) != (staged.size, staged.sha256):
            raise StorageIOError("发布后的文件校验失败。", path=target.name)
        if backup is None:
            rollback.add(f"remove:{target.name}", lambda t=target: _unlink(t))
        else:
            rollback.add(
                f"restore:{target.name}",
                lambda b=backup, t=target: _atomic_copy(b, t),
            )
    return rollback
```

L718–L750（原样）：
```python
            if not materials_check["ok"]:
                raise StorageIOError("发布后的资料与索引源不一致。", path=plan.kb_name)

            if hooks.prepare_kb is not None:
                _backup_or_remove(
                    store.subject_kb_base_dir(subject_id) / "kb_config.json",
                    rollback=rollback,
                    backup_root=backup_root,
                    label="kb_config.json",
                )
                hooks.prepare_kb(new_kb)

            result.documents = len(published)
            if hooks.write_record is not None:
                _backup_or_remove(
                    store.subject_data_path(subject_id, "knowledge.json"),
                    rollback=rollback,
                    backup_root=backup_root,
                    label="knowledge.json",
                )
                hooks.write_record(result.documents)

            reserve_index_task(
                kb_dir,
                task_id=task_id,
                subject_id=subject_id,
                kb_name=plan.kb_name,
                fingerprint=manifest_mod.fingerprint(published),
                shape=manifest_mod.shape(published),
                documents=result.documents,
                action="create" if new_kb else "reindex",
            )
        except BaseException as exc:
```

L773–L797（原样）：
```python
        publish_pairs(
            [(item, materials_dir / item.entry.name) for item in staged],
            backup_root=backup_root,
            rollback=rollback,
        )
        try:
            for item, transcript in zip(staged, transcripts):
                target = materials_dir / f"{item.entry.name}{TRANSCRIPT_SUFFIX}"
                _reject_unsafe_leaf(target)
                if target.exists():
                    backup = Path(backup_root) / f"text-{target.name}"
                    _atomic_copy(target, backup)
                    rollback.add(
                        f"restore:{target.name}",
                        lambda b=backup, t=target: _atomic_copy(b, t),
                    )
                else:
                    rollback.add(f"remove:{target.name}", lambda t=target: _unlink(t))
                _write_text_atomic(target, str(transcript.get("text", "")))
        except BaseException as exc:
            restore_or_fail(rollback, exc)
        return result


# ---------------------------------------------------------------------------
```

L800–L825（原样）：
```python
def finalize_reserved_task(kb_dir: Path | str, task_id: str) -> dict:
    """Record which source fingerprint the finished task actually produced."""
    reservation = reservation_for(kb_dir) or {}
    subject_id = str(reservation.get("subject_id") or "")
    kb_name = str(reservation.get("kb_name") or "")
    fingerprint = str(reservation.get("fingerprint") or "")
    state_shape = str(reservation.get("shape") or "")
    documents = int(reservation.get("documents") or 0)
    ok = False
    detail = "error"
    try:
        from deeptutor.api.utils.task_id_manager import TaskIDManager
        from deeptutor.knowledge.manager import KnowledgeBaseManager

        metadata = TaskIDManager.get_instance().get_task_metadata(task_id) or {}
        status = str(metadata.get("status") or "")
        manager = KnowledgeBaseManager(
            base_dir=str(store.subject_kb_base_dir(subject_id)) if subject_id else ""
        )
        manager_value = str((manager.get_kb_status(kb_name) or {}).get("status") or "")
        ok = status == "completed" and manager_value == "ready"
        detail = "ready" if ok else (status or "unknown")
    except Exception:  # noqa: BLE001 - a failed probe must not claim ready
        logger.warning("Could not confirm terminal index state", exc_info=True)
        ok = False
        detail = "error"
```

L866–L883（原样）：
```python
async def run_reserved_index_task(
    kb_dir: Path | str,
    task_id: str,
    run: Callable[..., Any],
    *args: Any,
) -> None:
    """Run one reserved task, then publish the *real* terminal state.

    ``run`` is the existing background function (``run_initialization_task`` /
    ``run_reindex_task``); those catch their own errors and store raw
    diagnostics in the progress record, so success is decided by the terminal
    task status and the KB's own status — never by "the call returned".
    """
    try:
        await run(*args)
    except Exception:  # noqa: BLE001 - recorded as a failed run below
        logger.error("Index task %s failed", task_id, exc_info=True)
    finally:
```

### `deeptutor/subjects/material_manifest.py`

R1/R2：宽松缺失/null、单向materials比较、shape代替已发布fingerprint

L269–L290（原样）：
```python
def _read_object(path: Path, *, what: str) -> dict | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StorageIOError("本地数据读取失败，请稍后重试。", path=path.name, cause=exc) from exc
    except UnicodeDecodeError as exc:
        raise json_store.corrupt_error(what, "文件不是合法 UTF-8") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise json_store.corrupt_error(what, "JSON 无法解析") from exc


def load_manifest(kb_dir: Path, *, subject_id: str, kb_name: str) -> dict | None:
    """Read the KB's manifest; ``None`` only when the file does not exist."""
    payload = _read_object(manifest_path(kb_dir), what=MANIFEST_NAME)
    if payload is None:
        return None
    return validate_manifest(payload, subject_id=subject_id, kb_name=kb_name)
```

L369–L397（原样）：
```python
def compare_materials(
    raw_files: Sequence[dict], material_files: Sequence[dict], *, verify_hashes: bool = True
) -> dict:
    """Every index source file must exist in ``materials`` with the same bytes.

    ``materials`` may legitimately hold more than ``raw`` (lecture transcripts,
    the original recording, later manual notes), so extra material files are not
    a mismatch. A raw file that is missing from — or differs from — the
    authoritative copy is.
    """
    authoritative = _by_path(material_files)
    missing = sorted(path for path in (str(i["path"]) for i in raw_files) if path not in authoritative)
    changed: list[str] = []
    for item in raw_files:
        path = str(item["path"])
        counterpart = authoritative.get(path)
        if counterpart is None:
            continue
        if int(counterpart["size"]) != int(item["size"]):
            changed.append(path)
            continue
        if verify_hashes and item.get("sha256") and counterpart.get("sha256"):
            if counterpart["sha256"] != item["sha256"]:
                changed.append(path)
    return {
        "ok": not (missing or changed),
        "missing_in_materials": missing,
        "changed_in_materials": sorted(changed),
    }
```

L435–L484（原样）：
```python
        # (the first successful upload is what establishes one).
        manifest_diff = {"ok": True, "legacy": True}
        expected_shape = shape(raw_files)
        expected_fingerprint = fingerprint(raw_files) if verify_hashes else None
    else:
        manifest_diff = compare_manifest(
            manifest["files"], raw_files, verify_hashes=verify_hashes
        )
        expected_shape = shape(manifest["files"])
        expected_fingerprint = fingerprint(manifest["files"])

    material_diff: dict = {"ok": True}
    if materials_dir is not None and Path(materials_dir).is_dir():
        material_files = enumerate_files(materials_dir, digest=verify_hashes)
        material_diff = compare_materials(raw_files, material_files, verify_hashes=verify_hashes)

    in_sync = bool(manifest_diff.get("ok", False)) and bool(material_diff.get("ok", False))
    manager_value = str(manager_status.get("status") or "").lower() or "unknown"
    stored = str((index_state or {}).get("status") or "")
    state_shape = str((index_state or {}).get("shape") or "")

    pending = bool(queued or worker_alive)
    manager_error = manager_value in ("error", "failed")
    if not in_sync:
        status = "stale"
    elif stored == "ready" and state_shape == expected_shape:
        status = "ready"
    elif pending:
        # A task is running or accepted: the index cannot be current yet.
        status = "rebuilding" if (documents or index_state or stored) else "initializing"
    elif stored == "error" or manager_error:
        status = "error"
    elif stored == "ready":
        # The published index belongs to an older source set.
        status = "stale"
    elif index_state is None and manifest is None and manager_value in ("ready", "completed"):
        # A legacy library whose published index was ready before this stage:
        # there is no recorded source change to contradict it.
        status = "ready"
    elif documents or manager_value in ("ready", "completed", "initializing", "processing"):
        status = "rebuilding"
    else:
        status = "initializing"

    percent = {"ready": 100, "error": 0}.get(status, 0)
    stage = _STATUS_STAGES[status]

    projection: dict[str, Any] = {
        "status": status,
        "progress": _bounded_progress(status, percent=percent, stage=stage),
```

### `deeptutor/api/routers/subjects.py`

R1/R4：GET构造manager有副作用、吞材料路径异常、初始化元数据、提交后才add_task

L172–L204（原样）：
```python
    from deeptutor.subjects import material_manifest

    manager = _kb_manager(subject_id)
    kb_dir = _confined_kb_dir(subject_id, kb_name)
    kb_type = (record or {}).get("type")
    materials_dir: Path | None = None
    if isinstance(kb_type, str) and kb_type:
        try:
            materials_dir = uploads.materials_path(subject_id, kb_type)
        except Exception:  # noqa: BLE001 - a bad stored type must not read elsewhere
            materials_dir = None
    busy = uploads.busy_state(kb_dir)
    return material_manifest.project_status(
        kb_dir=kb_dir,
        raw_dir=kb_dir / "raw",
        materials_dir=materials_dir,
        subject_id=subject_id,
        kb_name=kb_name,
        manager_status=manager.get_kb_status(kb_name),
        worker_alive=busy["worker_alive"],
        queued=busy["queued"],
        task_id=busy["task_id"],
    )


def _knowledge_view(subject_id: str) -> list[dict]:
    manager = _kb_manager(subject_id)
    out: list[dict] = []
    for record in store.load_knowledge_records(subject_id):
        kb_name = record["kb_name"]
        projection = _kb_projection(subject_id, kb_name, record=record)
        out.append({**record, "documents": projection["documents"], "status": projection})
    _ = manager
```

L304–L322（原样）：
```python
    initializer = KnowledgeBaseInitializer(
        kb_name=plan.kb_name,
        base_dir=str(base_dir),
        progress_tracker=progress_tracker,
        rag_provider="llamaindex",
    )

    def _prepare_kb(new_kb: bool) -> None:
        initializer.create_directory_structure()
        manager.update_kb_status(
            name=plan.kb_name,
            status="initializing" if new_kb else "rebuilding",
            progress={
                "stage": "initializing" if new_kb else "reindexing",
                "message": (
                    "Initializing subject KB..." if new_kb else "Re-indexing subject KB..."
                ),
                "percent": 0,
            },
```

L345–L374（原样）：
```python
            staging_dir=staging,
            task_id=task_id,
            hooks=uploads.CommitHooks(prepare_kb=_prepare_kb, write_record=_write_record),
        )

    if committed.new_kb:
        background_tasks.add_task(
            uploads.run_reserved_index_task,
            kb_dir,
            task_id,
            run_initialization_task,
            initializer,
            task_id,
        )
    else:
        from deeptutor.api.routers.knowledge import run_reindex_task

        background_tasks.add_task(
            uploads.run_reserved_index_task,
            kb_dir,
            task_id,
            run_reindex_task,
            plan.kb_name,
            str(base_dir),
            task_id,
            "",
        )

    return {
        "operation": "index",
```

### `deeptutor/services/asr/transcribe.py`

R6：JSON只识别左花括号、配置读取在try外、IO错误kind

L68–L94（原样）：
```python
def extract_transcript_text(body: str) -> str | None:
    """The transcript in a provider body, or ``None`` when there is none.

    A plain-text body is the transcript (an empty body is a legal empty
    transcript). A JSON body must carry a real string ``text`` field: a JSON
    object without one is a malformed provider answer, not a transcript, and is
    never stringified into one.
    """
    raw = body if isinstance(body, str) else ""
    if raw.lstrip().startswith("{"):
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        value = payload.get("text")
        if not isinstance(value, str):
            return None
        return value.strip()
    text = raw.strip()
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return text
```

L119–L139（原样）：
```python
    if not api_key:
        return _failure(
            base_url,
            model_name,
            "unconfigured",
            "STT 服务未配置（请在 设置→模型→语音识别 配置 API Key 与模型）",
        )

    audio_path = Path(audio_path)
    url = f"{base_url}/audio/transcriptions"
    data = {"model": model_name, "language": language, "response_format": "text"}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_SECONDS) as client:
            # Streamed multipart: the provider reads the file handle directly,
            # so a 200MiB recording never becomes one in-memory bytes object.
            with open(audio_path, "rb") as handle:
                files = {"file": (audio_path.name, handle, mime_for(audio_path))}
                resp = await client.post(url, headers=headers, files=files, data=data)
    except httpx.TimeoutException as exc:
        return _failure(base_url, model_name, "timeout", f"ASR 请求超时：{type(exc).__name__}")
```

L145–L162（原样）：
```python
    if resp.status_code != 200:
        return _failure(
            base_url, model_name, "provider", f"ASR 请求失败，状态码 {resp.status_code}"
        )
    text = extract_transcript_text(resp.text)
    if text is None:
        return _failure(base_url, model_name, "invalid_output", "ASR 响应缺少文本字段")
    return {"text": text, "model": model_name, "base_url": base_url, "error": ""}


__all__ = [
    "DEFAULT_STT_BASE",
    "DEFAULT_STT_MODEL",
    "MIME_BY_EXTENSION",
    "STT_TIMEOUT_SECONDS",
    "extract_transcript_text",
    "mime_for",
    "transcribe",
```

### `deeptutor/services/rag/pipelines/llamaindex/pipeline.py`

R5：全局栈不能识别实际进度worker；复制context已有，可最小接线复用

L47–L54（原样）：
```python
#: Stack of the guard heartbeats currently installed on the process-wide
#: embedding adapter. Only the top one may forward progress; when a run ends we
#: fall back to the next live run (or to "no callback"), so two KBs indexing at
#: the same time cannot make each other's heartbeat look dead.
_PROGRESS_CALLBACKS: list[Any] = []
_PROGRESS_CALLBACK_LOCK = threading.Lock()

SignatureProvider = Callable[[], EmbeddingSignature | None]
```

L94–L113（原样）：
```python
def active_progress_callback() -> Any:
    """The heartbeat currently installed on the embedding adapter (or ``None``)."""
    with _PROGRESS_CALLBACK_LOCK:
        return _PROGRESS_CALLBACKS[-1] if _PROGRESS_CALLBACKS else None


def _install_progress_callback(callback: Callable[..., Any]) -> None:
    with _PROGRESS_CALLBACK_LOCK:
        _PROGRESS_CALLBACKS.append(callback)
    set_progress_callback(callback)


def _restore_progress_callback(callback: Callable[..., Any]) -> None:
    """Drop *callback*; only the still-live runs keep a heartbeat installed."""
    with _PROGRESS_CALLBACK_LOCK:
        if callback in _PROGRESS_CALLBACKS:
            _PROGRESS_CALLBACKS.remove(callback)
        target = _PROGRESS_CALLBACKS[-1] if _PROGRESS_CALLBACKS else None
    set_progress_callback(target)
```

L169–L196（原样）：
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

    _install_progress_callback(_heartbeat)
    try:
        future = asyncio.get_running_loop().run_in_executor(
            None, contextvars.copy_context().run, _work
        )
    except BaseException:
        progress_live.clear()
        _restore_progress_callback(_heartbeat)
        _release_index_worker(worker_key, worker_marker)
```

### `tests/phase1/test_p1_30.py`

R7：wall-clock上界和不成立的0.3s差值断言，生产锁本身保留

L291–L326（原样）：
```python

    assert not errors, errors
    adapter = _ConcurrencyAdapter.instances[0]
    return adapter, max(adapter.left) - min(adapter.entered)


def test_delay_zero_still_serializes_posts_without_extra_config_delay(monkeypatch):
    zero_adapter, zero_span = _run_concurrent(monkeypatch, threads=3, delay=0.0)
    assert zero_adapter.max_active == 1
    assert len(zero_adapter.calls) == 3
    # 三次 post 的全部耗时 ≈ adapter 自身的 3×0.05s，没有被"额外配置延时"拉长
    assert zero_span < 0.45, zero_span

    # 对照：同样的并发 + 配置延时必须明显更慢，证明上面的下界确实在测"没有配置延时"
    delayed_adapter, delayed_span = _run_concurrent(monkeypatch, threads=3, delay=0.2)
    assert delayed_adapter.max_active == 1
    assert delayed_span > zero_span + 0.3, (zero_span, delayed_span)
    assert delayed_span >= 0.4, delayed_span


@pytest.mark.asyncio
async def test_configured_delay_is_still_applied(monkeypatch):
    client = _build_client(monkeypatch, delay=0.15)
    started = time.monotonic()
    await client.embed(["a", "b"])
    # batch_size=8 会合成一次 post，所以这里只证明 delay 不阻塞单批；
    # 真正的节流证据在下面的单条文本两次 embed 上。
    assert time.monotonic() - started < 0.5

    adapter = _ConcurrencyAdapter.instances[0]
    adapter.calls.clear()
    first = time.monotonic()
    await client.embed(["a"])
    await client.embed(["b"])
    second = time.monotonic() - first
    assert len(adapter.calls) == 2
```

### `deeptutor/services/rag/pipelines/llamaindex/embedding_adapter.py`

只读：真实embedding把共享属性callback传给client；setter作用于全局Settings模型

L110–L122（原样）：
```python
    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        client = self.refresh_client()
        embeddings = await client.embed(
            texts,
            progress_callback=self._progress_callback,
            input_type="search_document",
        )
        return validate_embedding_batch(
            embeddings,
            expected_count=len(texts),
            binding=self._binding,
            model=self._model,
        )
```

L163–L167（原样）：
```python
def set_progress_callback(callback) -> None:
    """Attach an indexing progress callback to the active embedding adapter."""
    embed_model = getattr(Settings, "_embed_model", None)
    if isinstance(embed_model, CustomEmbedding):
        embed_model.set_progress_callback(callback)
```

### `deeptutor/knowledge/manager.py`

只读：构造器会mkdir、配置归一化后可能atomic_write；GET不能直接复用有副作用的构造路径

L247–L260（原样）：
```python
    def __init__(self, base_dir="./data/knowledge_bases"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Config file to track knowledge bases
        self.config_file = self.base_dir / "kb_config.json"
        self.config = self._load_config()

        # PocketBase sync — enabled when integrations.pocketbase_url is set.
        # The local JSON file stays the source of truth; PocketBase gets a
        # mirrored copy for admin-panel visibility and future multi-user access.
        from deeptutor.services.pocketbase_client import is_pocketbase_enabled

        self._pb_enabled = is_pocketbase_enabled()
```

L288–L306（原样）：
```python
                config_changed = False
                for kb_name, kb_entry in knowledge_bases.items():
                    if not isinstance(kb_entry, dict):
                        continue

                    # Connected KBs (Obsidian vaults, linked indexes) are
                    # pointers with no index pipeline — none of the
                    # provider/embedding normalization below applies. Leave
                    # their type/external pointer untouched.
                    if is_connected_kb(kb_entry):
                        continue

                    raw_provider = kb_entry.get("rag_provider")
                    provider = normalize_provider_name(raw_provider)
                    if kb_entry.get("rag_provider") != provider:
                        kb_entry["rag_provider"] = provider
                        config_changed = True

                    raw_provider_text = str(raw_provider or "").strip().lower()
```

L330–L337（原样）：
```python

                if config_changed:
                    try:
                        atomic_write_json(self.config_file, config)
                    except Exception as save_err:
                        logger.warning(f"Failed to persist normalized KB config: {save_err}")

                return config
```

### `deeptutor/knowledge/initializer.py`

只读：create_directory_structure重写metadata及注册，不适合无条件用于已有KB

L118–L139（原样）：
```python
    def create_directory_structure(self) -> None:
        """Create KB directory structure."""
        logger.info(f"Creating directory structure for knowledge base: {self.kb_name}")

        for dir_path in [
            self.raw_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

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

### `deeptutor/subjects/json_store.py`

只读S03基础：NOFOLLOW/NONBLOCK与strict read_object，拒绝已有null；不可改共享fixture/存储协议

L260–L282（原样）：
```python
def _read_text(path: Path) -> str | None:
    """Read ``path`` without following a symlink; ``None`` means "absent".

    ``O_NOFOLLOW`` makes the check atomic: a JSON file swapped for a symlink
    between the confinement check and the open is refused (``ELOOP``) instead of
    read. A *dangling* symlink therefore reports an error rather than looking
    like a missing file.
    """
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise StorageIOError(_SYMLINK_MESSAGE, path=path.name, cause=exc) from exc
        raise _io(path, exc) from exc
```

L339–L353（原样）：
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
```

## 协调者独立探针（只读、可运行）

路径：`.phase1-evidence/reviews/S05/probe_s05.py`；SHA256：`5a98eb379437242dbecd6f6d3840df853b35f2b62ac80203873cef655944cd0c`。
运行全体：`./.venv/bin/python .phase1-evidence/reviews/S05/probe_s05.py`。只运行一项可在末尾加`Review.test_...`。末次实测23方法/24处失败；原样保留作返修基线，不编辑探针来过关。
其中实际embedding回调用真实CustomEmbedding/Settings和跨线程event loop，只替换provider client，先证明会发进度的合法控制；不是手工调用栈顶函数。早期一次探针用不会发进度的stub导致等待失败，已修探针，旧尝试日志保留，末次结论不以该等待失败作为产品缺陷。

- `Review.test_same_size_replacement_cannot_remain_ready`（L82）
- `Review.test_same_size_replacement_after_crash_is_stale`（L87）
- `Review.test_missing_materials_directory_cannot_be_in_sync_ready`（L91）
- `Review.test_manifest_null_is_corrupt_not_legacy`（L95）
- `Review.test_index_state_null_is_corrupt_not_missing`（L101）
- `Review.test_manifest_and_state_symlinks_are_not_read`（L106）
- `Review.test_broken_manifest_symlink_is_not_a_missing_legacy_manifest`（L122）
- `Review.test_get_does_not_migrate_kb_config`（L127）
- `Review.test_extra_indexable_material_cannot_be_silently_omitted`（L134）
- `Review.test_document_digest_failure_after_replace_restores_the_pair`（L140）
- `Review.test_audio_second_publication_failure_rolls_back_first_audio`（L150）
- `Review.test_existing_metadata_restored_when_record_update_fails`（L162）
- `Review.test_queue_registration_failure_restores_sources_and_reservation`（L169）
- `Review.test_failed_upload_does_not_leave_running_task_metadata`（L178）
- `Review.test_queued_task_revalidates_sources_before_running_index`（L185）
- `Review.test_finalizer_cannot_publish_ready_for_drifted_sources`（L197）
- `Review.test_stale_finalizer_cannot_override_a_different_reservation`（L206）
- `Review.test_stt_configuration_failure_is_a_provider_error_without_publishing`（L212）
- `Review.test_json_array_stt_response_is_not_a_transcript`（L218）
- `Review.test_audio_predictable_part_symlinks_cannot_overwrite_outside`（L229）
- `Review.test_failed_kb_a_cannot_undo_concurrent_kb_b_success`（L244）
- `Review.test_concurrent_real_embedding_callbacks_belong_to_their_worker`（L271）
- `Review.test_valid_controls_remain_legal`（L324）

## 只读契约/实现决定

C01/C02/C07/C14、MaterialManifest/UploadResponse不变。额外index_state是subject内部辅助记录，不改全局引擎version schema。R2修记录指纹比较，不要求GET每次全量hash；R4在实际run前和最终确认ready前做完整一致性检查。
metadata短事务可用subject锁协调多个KB共享JSON，不用把所有KB设成同一个busy key，也不持锁跨网络/await。失败任务可保留error/cancelled历史，不能留下无工作的running。ZIP/目录上传、真实资料迁移、全局manager/initializer改造、新调度系统和第二阶段功能均不新增。
S06及其他后续阶段不授权。执行完R1–R7与阶段回归后一次提交verified_local，等待独立审阅。

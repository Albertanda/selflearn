# S10 已探索的文件清单 + 关键片段

2026-10-19，S09-final验收后的实际文件；配套START_S10及最新签收receipt。此包是有关接缝的定向探索，不声称已重读全仓。核完整SHA后直接按符号进入实现；需要补读时只读相邻调用上下文。

## 接缝与实施边界

- S10尚未实施。export_bundle.py、subject_operations.py、P39/P40/P41/P54及test_subject_operations五个测试文件当前不存在，按白名单新增。
- 原export仅同步打学习树ZIP，旧delete先移registry/ignore_errors且漏公开树；P39无证据1.0、静态关联和None格式化都是真实未修复现状。
- subject JSON短锁、单KB reservation和report的进程内active登记各有用途；它们目前不足以证明整个上传/排队worker/报告/取消线程/导出与删除互斥。本次明确授权共享活动协议及必要接入，不要求worker卡在原白名单限制。
- S09已将报告与复习包复制移到线程；正式提交仍在live await之后。不要把整条会发布的同步函数搬进线程后宣称取消安全。取消后的线程在S10必须继续持有活动权直到真正结束。
- C10按有有效attempt的entry均值，entry层仍0/untracked；null模板写未评估。C12固定四组目录、manifest覆盖/排除，拒绝任意symlink和未知完成产物。
- 保持当前用户严格路径，不用可fallback的全局get_path_service。真实outputs下载需要鉴权用户上下文；不修改其allowlist，不单独公开manifest.json。
- 99前置源码/14允许路径/107 capture并集；6重叠可改、93只读。完整目标、证据、边界及通过条件见START_S10；只做P39→P40→P41→P54，一次交付。

## 已探索文件与完整SHA256

| 文件 | SHA256 | 关联与限制 |
|---|---|---|
| `deeptutor/subjects/knowledge_points.py` | `bc087b86a9c709e2a6227371c891c93a4fe8552ada632efe619566583052e87c` | P39：无证据1.0、旧关联和null排序需修复。 |
| `deeptutor/services/pdf/review_guide.py` | `34df402d9820a82acefae768436aead50cc80501abdff415f6d84595730e9a59` | P39仅学情聚合/格式化；renderer和S02生成门保持。 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | P54：严格当前用户根；旧delete先删registry并忽略IO。 |
| `deeptutor/api/routers/subjects.py` | `763827b06c423b6a090e3f9b2bac0933e1ae3dd7d8027d2b456b4e4a2d230430` | P39/41/54及活动租约的最小路由接入。 |
| `deeptutor/subjects/uploads.py` | `439e0de6c389f819ff8f85d54365b01baee48d15732bdefedb766ad0f7d7aba5` | 仅P40活动权/任务移交；原来源版本、回滚、忙状态不弱化。 |
| `deeptutor/services/pdf/report_store.py` | `ec51c047268ba2b54c485876377fcda1ac83e7c5d8aff67b06117873d974cbff` | 仅租约接入：原同步API与S09 prepare/commit/discard保持。 |
| `deeptutor/services/pdf/report.py` | `d9daa085a58e14f9957e779311f6281f1118b2f3c130f8df7c08b7a8bf280af4` | 仅thread生命周期租约：取消后底层线程仍可能工作。 |
| `deeptutor/subjects/wrong_book.py` | `957813c428f45a8f8d691e28bc580c70f4b00110a2820381de6fed65fde2d6ab` | 只读：以attempt派生view为准；无attempt的stored mastery不可作证据。 |
| `deeptutor/subjects/exam_points.py` | `1c2f0fcd8412b0cea49ea2d11a8aed27219cedff7fb384dd9200f6b110ba7186` | 只读：本科/确认/学期语义和严格结构校验。 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 只读：链接检查先于IO；目录短锁不是完整长任务协调协议。 |
| `deeptutor/subjects/material_manifest.py` | `d80aaf5e653ff411d292001ef945b919fd5998d15793f5c303700883f422c79b` | 只读：source/hash/完整性及KB状态不能冒充全科任务租约。 |
| `deeptutor/knowledge/progress_tracker.py` | `3c0a64605d780e7bd36f7ed6184103d517d2d8670cdf0854cecfaa93499f59d2` | 只读：状态显示不是跨进程互斥。 |
| `deeptutor/api/routers/outputs.py` | `ff89210fadad958b5e99efa0fc2955dd02e119f6f06493f49f280701a6719bed` | 只读：用真实鉴权下载链路，不改allowlist。 |
| `deeptutor/services/path_service.py` | `01505ea0a473ba16b09bd27a9afd1a6795f4ddff1eef4a7b34f89ee7c748bd3d` | 只读：全局getter可fallback；导出用store严格接口，private后缀仍不可下载。 |
| `deeptutor/multi_user/context.py` | `57cf4b481dd5646b907f6b3696e14e31440f143469d1570c0441f0d72017992a` | 只读：contextvars跨to_thread和非管理员隔离测试。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 只读：busy沿用kb_busy409，storage与provider投影不拼raw。 |
| `deeptutor/api/routers/unified_ws.py` | `5a6bed835c44b05702bc32b0e0c0a1a2c9843a5fc420a1e0f954c1b55e5e7b60` | 只读：旧session删除后必须仍subject_not_found；复用已有发送回路。 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 只读：临时HOME/runtime、network guard、route app/subjects原语。 |
| `tests/phase1/test_p1_14.py` | `a350b78901678dda67ff8ea0e2b077ed38b68b49e6b9d56c1aa5944b87818248` | 只读：知识点存储并发和未知字段保护的前置行为。 |
| `tests/phase1/test_p1_19.py` | `35ac20cd4ff7f1a849f42116778c90a4f3cda454c3d95aa79a541b0bcd623403` | 只读：reservation/worker全key忙协议不得破坏。 |
| `tests/phase1/test_p1_32.py` | `dfe4b28ba92f1f1fcc99baf5810b5265cc06f5af63301dafc18778762184a996` | 只读：已验收报告身份/发布/失败与私有字段边界。 |
| `tests/phase1/test_p1_35.py` | `862ac3606061d130cf0e5c712ab41508d323c8753158889663edadaa135ecff3` | 只读：同步publish兼容、真实Typst和失败保护；新增18回归的一部分。 |
| `tests/phase1/test_p1_36.py` | `ad49d45a1f181603be72f688d8cf2637c4b31cd26d7ae06e4fa002b22eaa0205` | 只读：附件ID、review原件和复制PNG严格策略。 |
| `tests/phase1/test_p1_38.py` | `6c087ba156f5e64128481e496e4a9cef744ae395a8aa1ebc9cdc794845b89a12` | 只读：实际HTTP并发/线程/取消/路径边界，不能弱化。 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | C10/C12与附录A权威固定契约。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | 按定义验证KnowledgeAssessment、ExportManifest及文件entry。 |
| `plans/phase1/cards/P1-39.md` | `919c7abac2935fadd065b19bce4e2c5cef91313af3266b7373bf1a0a05dff9ba` | P39目标/证据/范围/完成条件。 |
| `plans/phase1/cards/P1-40.md` | `d40b645e91033e71448c8bd41b9b62c0d686e37594fd6e51942a8e9b4b558605` | P40包含协调者明确补充的活动协议接入授权。 |
| `plans/phase1/cards/P1-41.md` | `bd3a7d6bf70e86e8f3c5158d498a3b4e5856c23a37fa1ee27adfedc2baad3666` | P41真实导出HTTP和鉴权下载。 |
| `plans/phase1/cards/P1-54.md` | `ebdad76228a509695c4f87b0e19c999452f961f0c9a57c27238b7e849561286f` | P54两树删除/忙科目/IO失败与旧session。 |

## 关键片段

### deeptutor/subjects/knowledge_points.py

P39：无证据1.0、旧关联和null排序需修复。

L214–L232

```python

def aggregate(subject_id: str) -> list[dict]:
    """Knowledge points enriched with wrong-book + exam-point aggregates.

    Each point gains ``wrong_count``, ``mastery`` (mean of linked wrong
    entries, 1.0 when none) and ``exam_count`` so the context summary and
    review guide can rank by weakness.
    """
    from deeptutor.subjects import exam_points as ep_mod
    from deeptutor.subjects import wrong_book

    wrongs = {e["id"]: e for e in wrong_book.load(subject_id) if not e.get("archived")}
    exams = {p["id"]: p for p in ep_mod.load(subject_id) if p.get("confirmed")}
    out = []
    for p in load(subject_id):
        item = dict(p)
        item["wrong_count"] = sum(1 for wid in p.get("wrong_ids", []) if wid in wrongs)
        scores = [
            wrongs[wid].get("mastery", 0.0)
```

L241–L259

```python

def context_summary(subject_id: str, limit: int = 12) -> str:
    """Lightweight knowledge-map injection block (常驻轻量层)."""
    points = aggregate(subject_id)
    if not points:
        return ""
    weak = [p for p in points if p["wrong_count"] > 0 or p["exam_count"] > 0]
    weak.sort(key=lambda p: (p["mastery"], -p["wrong_count"]))
    lines = ["【该科目知识点索引】"]
    for p in points[:limit]:
        tags = []
        if p["wrong_count"]:
            tags.append(f"错题{p['wrong_count']}")
        if p["exam_count"]:
            tags.append("考点")
        suffix = f"（{'、'.join(tags)}）" if tags else ""
        lines.append(f"- {p['name']}{suffix}")
    if weak and len(points) > limit:
        lines.append(f"……共 {len(points)} 个知识点，最薄弱：{weak[0]['name']}（掌握度 {weak[0]['mastery']}）")
```

L115–L133

```python

def add_point(subject_id: str, *, name: str, path: str = "", source: str = "manual") -> dict:
    """Add a named point, reusing an existing one.

    The "already exists?" lookup and the append share one transaction, so two
    concurrent adds of the same name cannot both decide to append.
    """
    cleaned = _required_name(name)

    d = store.subject_dir(subject_id)
    with json_store.json_transaction(d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)
        existing = next((p for p in points if p.get("name") == cleaned), None)
        if existing is not None:
            return existing
        point = _build_point(subject_id, name=name, path=path, source=source)
        points.append(point)
        tx.write_list(file_path, points)
```

L175–L193

```python

def _link(subject_id: str, kp: str, linked_id: str, key: str) -> dict | None:
    """Idempotently append *linked_id* to *key* on the point named *kp*.

    Lookup, existence check and append all happen under one lock, so two
    concurrent links cannot drop one of the ids, and re-linking the same id is
    a no-op (the existing "don't add twice" rule).
    """
    if not isinstance(kp, str) or not isinstance(linked_id, str):
        raise json_store.invalid_input("知识点名称与关联 id 必须是字符串")
    target = kp.strip().lower()
    if not target or not linked_id:
        return None

    d = store.subject_dir(subject_id)
    with json_store.json_transaction(d) as tx:
        file_path = tx.path(KNOWLEDGE_POINTS_NAME)
        points = _validate(tx.read_list(file_path), file_path)
        for point in points:
```

### deeptutor/services/pdf/review_guide.py

P39仅学情聚合/格式化；renderer和S02生成门保持。

L30–L48

```python

def _aggregate(subject_id: str, term: str) -> dict:
    exam_points = [p for p in ep_mod.load(subject_id) if p.get("confirmed")]
    if term:
        exam_points = [p for p in exam_points if p["term"] == term]
    wrongs = [e for e in wrong_book.load(subject_id) if not e.get("archived")]
    points = knowledge_points.aggregate(subject_id)
    return {"exam_points": exam_points, "wrong_entries": wrongs, "knowledge_points": points}


def _format_input(data: dict) -> str:
    lines = ["## 期末考点"]
    for p in data["exam_points"]:
        lines.append(
            f"- [{p['level']}] {p['content']}"
            + (f"（证据：{p['evidence'][:60]}）" if p.get("evidence") else "")
        )
    lines.append("")
    lines.append("## 错题集")
```

L39–L57

```python

def _format_input(data: dict) -> str:
    lines = ["## 期末考点"]
    for p in data["exam_points"]:
        lines.append(
            f"- [{p['level']}] {p['content']}"
            + (f"（证据：{p['evidence'][:60]}）" if p.get("evidence") else "")
        )
    lines.append("")
    lines.append("## 错题集")
    order = {"repeated": 0, "missed": 1, "basic": 2, "mastered": 3}
    wrongs = sorted(data["wrong_entries"], key=lambda e: order.get(e["status"], 9))
    for e in wrongs:
        lines.append(
            f"- [{e['status']}] 知识点: {e.get('kp') or '未标注'} | 题目: {e['question'][:80]}"
            + (f" | 答案要点: {e['answer'][:60]}" if e.get("answer") else "")
        )
    lines.append("")
    lines.append("## 知识点索引")
```

L62–L80

```python

async def generate_guide_markdown(subject_id: str, term: str = "") -> str:
    """LLM-generated review guide (Markdown subset).

    Raises ``LLMReasoningBudgetExhausted`` when the provider stopped at an
    output cap (the reasoning model burned the budget), or
    ``LLMEmptyResponseError`` for any other empty result: a blank guide must
    never be rendered into a PDF/DOCX that looks like a successful generation.
    """
    data = _aggregate(subject_id, term)
    if not data["exam_points"] and not data["wrong_entries"]:
        return "# 期末复习指南\n\n该科目暂无已确认的考点与错题，请先上传材料并确认考点。"
    cfg = get_llm_config()
    return await complete_subject_text(
        prompt=GUIDE_PROMPT + "\n\n## 科目数据\n" + _format_input(data),
        system_prompt="你是课程助教，输出 Markdown 复习指南。",
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
```

### deeptutor/subjects/store.py

P54：严格当前用户根；旧delete先删registry并忽略IO。

L113–L131

```python

def current_subject_paths() -> PathService:
    """The **current user's** ``PathService``, resolved strictly (C01).

    :func:`deeptutor.services.path_service.get_path_service` wraps this in a
    ``try/except`` that falls back to the default (admin) instance. That is the
    right thing for best-effort display paths and exactly the wrong thing for
    learner data: if the current scope cannot be resolved, subject storage must
    fail loudly rather than quietly read or write the administrator's tree.

    Every subject/output helper in this module resolves through here.
    """
    from deeptutor.multi_user.paths import get_current_path_service

    service = get_current_path_service()
    if service is None:  # pragma: no cover - defensive
        raise StorageIOError("无法解析当前用户的科目数据根，已拒绝访问。")
    return service

```

L150–L168

```python

def subjects_root() -> Path:
    """Root of the current user's subject tree (``.../workspace/subjects``).

    Validated **before** it is created: if ``subjects`` is a symlink, whatever
    it points at is not this user's registry, so the call fails instead of
    reading or writing the target.
    """
    workspace = current_subject_paths().get_workspace_dir()
    json_store.ensure_trusted_root(workspace)
    root = workspace / SUBJECTS_ROOT_NAME
    if root.is_symlink():
        raise StorageIOError(
            "科目根目录是符号链接，已拒绝访问。", path=SUBJECTS_ROOT_NAME
        )
    if root.exists() and not root.is_dir():
        raise StorageIOError("科目根路径不是目录。", path=SUBJECTS_ROOT_NAME)
    json_store.make_directory(root)
    # Re-check after creating: the same path must still be a real directory
```

L188–L206

```python

def subject_dir(subject_id: str) -> Path:
    """The data directory for one subject in the current user's registry.

    Raises an explicit error for an id that is not a plain slug, for a path
    that resolves outside this user's subject root, and for a well-formed id
    that is simply not registered (404) — writing learner data must never bring
    a subject tree into existence.
    """
    path = _subject_dir_unchecked(subject_id)
    if not _is_registered(subject_id):
        raise SubjectNotFoundError(subject_id)
    return path


def subject_data_path(subject_id: str, name: str) -> Path:
    """A confined data file for *subject_id* (validation before any read).

    This is the single entry point the collection modules use for their JSON
```

L411–L429

```python

def delete_subject(subject_id: str) -> bool:
    """Remove a subject from the registry and delete its tree.

    NOTE: still a two-step operation with ``ignore_errors=True`` on the tree
    removal. The registry/path handling is strict, but the deletion product
    policy (both trees, no ignored failures, busy state) is deferred to P1-54.
    The path is taken *before* de-registering so it is still resolvable after.
    """
    root = subjects_root()
    with json_store.json_transaction(root) as tx:
        index = tx.path(_INDEX_NAME)
        subjects = _validate_registry(tx.read_list(index), index)
        if not any(s.get("id") == subject_id for s in subjects):
            return False
        directory = _subject_dir_unchecked(subject_id)
        kept = [s for s in subjects if s.get("id") != subject_id]
        tx.write_list(index, kept)

```

### deeptutor/api/routers/subjects.py

P39/41/54及活动租约的最小路由接入。

L140–L158

```python
@router.delete("/{subject_id}")
async def delete_subject(subject_id: str, _: None = Depends(require_auth)):
    _require_subject(subject_id)
    store.delete_subject(subject_id)
    return {"status": "deleted", "subject_id": subject_id}


@router.get("/{subject_id}/knowledge")
async def list_subject_knowledge(subject_id: str, _: None = Depends(require_auth)):
    """Read-only view of this subject's KBs (C07).

    The count and status are projected from the **current** index source, not
    from a stored ``documents`` counter, and the projection never registers,
    creates or schedules anything: a GET must not have side effects.
    """
    _require_subject(subject_id)
    return {"knowledge": _knowledge_view(subject_id)}


```

L209–L227

```python
@router.post("/{subject_id}/knowledge/upload")
async def upload_subject_knowledge(
    subject_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    type: str = Form("auto"),
    _: None = Depends(require_auth),
):
    """Upload files into this subject's knowledge base (default: textbook).

    The whole batch is validated before anything is created, staged privately,
    and only then published: an audio batch is transcribed and published as
    audio + transcripts, a document batch replaces both ``materials/<type>``
    and the KB's ``raw`` copy and reserves the index task.
    """
    _require_subject(subject_id)
    plan = uploads.plan_batch(files, type=type)
    if plan.operation == "transcribe":
        return await _upload_audio_batch(subject_id, plan)
```

L292–L310

```python

async def _upload_document_batch(
    subject_id: str, plan: "uploads.UploadPlan", background_tasks: BackgroundTasks
) -> dict:
    """Publish a document batch and queue its index task (P1-17/P1-18/P1-19)."""
    kb_dir, _raw_dir = uploads.kb_paths(subject_id, plan.kb_name)
    uploads.assert_kb_not_busy(kb_dir)

    base_dir = uploads.kb_base_path(subject_id)
    task_id = _build_unique_task_id("subject_kb", plan.kb_name)

    def _prepare_kb(new_kb: bool) -> None:
        with json_store.json_transaction(store.subject_dir(subject_id)):
            # Only a brand-new KB gets the initializer's directory structure: its
            # metadata.json + registration are the KB's own creation. An existing
            # KB keeps its metadata (description/created_at/unknown fields) instead
            # of being reset by a re-upload.
            if new_kb:
                initializer.create_directory_structure()
```

L335–L353

```python

    def _register_task(new_kb: bool) -> None:
        """Queue the background job — inside the commit's rollback boundary."""
        if new_kb:
            background_tasks.add_task(
                uploads.run_reserved_index_task,
                kb_dir,
                task_id,
                run_initialization_task,
                initializer,
                task_id,
            )
            return
        from deeptutor.api.routers.knowledge import run_reindex_task

        background_tasks.add_task(
            uploads.run_reserved_index_task,
            kb_dir,
            task_id,
```

L703–L721

```python
@router.post("/{subject_id}/knowledge-points/build")
async def build_knowledge_points(subject_id: str, _: None = Depends(require_auth)):
    """Build/link the knowledge map from existing subject data.

    Creates points for every knowledge point named in the wrong book and
    the confirmed exam points, then links both ways. Optionally the LLM
    can enrich with textbook-derived points via ``llm=True`` (future).
    """
    _require_subject(subject_id)
    from deeptutor.subjects import exam_points as ep_mod
    from deeptutor.subjects import wrong_book

    created = []
    # 1. Points from wrong-book kp labels.
    for e in wrong_book.load(subject_id):
        kp = (e.get("kp") or "").strip()
        if not kp:
            continue
        point = knowledge_points.add_point(subject_id, name=kp, source="wrong_book")
```

L823–L841

```python

def _prepare_review_pack_copy(
    subject_id: str, markdown: str, extension: str, token: str, expected_workspace: str
) -> Path:
    """Render and copy off-loop; only return an owned, unpublished part file."""
    import os
    import shutil

    paths = store.current_subject_paths()
    final_name = f"review-guide-{token}.{extension}"
    staging = _render_review_pack_private(
        subject_id, markdown, extension, token, expected_workspace
    )
    try:
        subject_dir = store.subject_dir(subject_id)
        public_root = paths.get_public_outputs_root()
        # Validate every component before mkdir/open, including in-root aliases.
        public_dir = json_store.confined(public_root, public_root / "subjects" / subject_dir.name)
        json_store.make_directory(public_dir)
```

L866–L884

```python

async def _publish_review_pack(subject_id: str, markdown: str, extension: str) -> tuple[str, str]:
    """Offload all large IO; commit only after a live request resumes.

    Shielding retains ownership of the thread's result after cancellation. Its
    completion callback removes only its own unpublished part; no worker thread
    can publish a final name. The event-loop commit is one no-overwrite link.
    """
    import os
    import uuid

    paths = store.current_subject_paths()
    expected_workspace = str(paths.workspace_root)
    token = uuid.uuid4().hex
    final_name = f"review-guide-{token}.{extension}"
    prepared = asyncio.create_task(asyncio.to_thread(
        _prepare_review_pack_copy, subject_id, markdown, extension, token, expected_workspace
    ))

```

L1010–L1028

```python
@router.get("/{subject_id}/export")
async def export_subject_data(subject_id: str, _: None = Depends(require_auth)):
    """Bundle a subject's whole data tree (knowledge, wrong book, exam
    points, profile, materials) into a downloadable ZIP."""
    _require_subject(subject_id)
    import zipfile

    from deeptutor.services.path_service import get_path_service

    src_dir = store.subject_dir(subject_id)
    if not src_dir.exists() or not any(src_dir.rglob("*")):
        raise HTTPException(status_code=404, detail="Subject has no data yet")
    outputs_root = get_path_service().get_public_outputs_root()
    out_dir = outputs_root / "subjects" / subject_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    zip_path = out_dir / f"subject-backup-{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.rglob("*"):
```

### deeptutor/subjects/uploads.py

仅P40活动权/任务移交；原来源版本、回滚、忙状态不弱化。

L314–L332

```python
@contextmanager
def staging_root(subject_id: str) -> Iterator[Path]:
    """A private, cleaned-up staging directory inside this subject's tree."""
    directory = store.subject_dir(subject_id)
    root = json_store.confined(directory, directory / STAGING_DIR_NAME)
    json_store.make_directory(root)
    try:
        os.chmod(root, 0o700)
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        logger.debug("Could not tighten staging directory mode", exc_info=True)
    slot = root / uuid.uuid4().hex
    json_store.make_directory(slot)
    try:
        yield slot
    finally:
        shutil.rmtree(slot, ignore_errors=True)


# ---------------------------------------------------------------------------
```

L711–L729

```python

def busy_state(kb_dir: Path | str) -> dict:
    """Everything that must block a same-KB upload, in one read-only view."""
    reservation = reservation_for(kb_dir)
    worker = _pipeline_state(worker_key(kb_dir))
    queued = reservation is not None and not bool(worker.get("alive"))
    return {
        "key": worker_key(kb_dir),
        "reserved": reservation is not None,
        "reservation": reservation,
        "worker_alive": bool(worker.get("alive")),
        "worker_registered": bool(worker.get("registered")),
        "queued": queued,
        "busy": reservation is not None or bool(worker.get("alive")),
        "task_id": (reservation or {}).get("task_id"),
    }


def assert_kb_not_busy(kb_dir: Path | str) -> dict:
```

L659–L677

```python

def reserve_index_task(
    kb_dir: Path | str,
    *,
    task_id: str,
    subject_id: str,
    kb_name: str,
    fingerprint: str,
    shape: str,
    documents: int,
    action: str,
    materials_dir: str | None = None,
) -> dict:
    """Reserve this KB for one index task; raises ``kb_busy`` if already held."""
    key = worker_key(kb_dir)
    reservation = {
        "key": key,
        "task_id": task_id,
        "subject_id": subject_id,
```

L879–L897

```python

def commit_documents(
    *,
    subject_id: str,
    plan: UploadPlan,
    staged: Sequence[Staged],
    staging_dir: Path,
    task_id: str,
    hooks: CommitHooks | None = None,
) -> CommitResult:
    """Publish a document batch and reserve the index task, or change nothing.

    Everything happens inside the KB directory's transaction: the busy check,
    the source-consistency gate, both replacements, the manifest write and the
    task reservation. Nothing else may publish into this KB in between, so a
    "request accepted but the worker has not started yet" window cannot be
    entered twice.
    """
    hooks = hooks or CommitHooks()
```

L1245–L1263

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
    task status, the KB's own status *and* a re-check of the reserved source
    version — never by "the call returned".

    The reservation is re-validated **before** the index worker is called: a
    queue entry whose sources changed while it waited is failed safely instead
    of indexing material the caller never accepted.
    """
```

L1200–L1218

```python

def finalize_reserved_task(kb_dir: Path | str, task_id: str) -> dict:
    """Record which source fingerprint the finished task actually produced.

    A reservation that is no longer *this* task's is a stale callback: it writes
    nothing at all. Otherwise "ready" additionally requires the sources still to
    match the reserved fingerprint, so a drifted run cannot be published as
    covering the current material.
    """
    reservation = reservation_for(kb_dir) or {}
    if str(reservation.get("task_id") or "") != task_id:
        logger.info("Ignoring finalizer for a stale or foreign reservation")
        return {"ok": False, "reason": "stale_reservation"}

    gate = verify_reserved_sources(kb_dir, reservation)
    terminal = _terminal_task_status(task_id)
    ok = gate["ok"] and terminal == "completed"
    reason = gate["reason"] if not gate["ok"] else (
        "task_failed" if terminal in ("error", "cancelled") else "task_incomplete"
```

### deeptutor/services/pdf/report_store.py

仅租约接入：原同步API与S09 prepare/commit/discard保持。

L626–L644

```python
# ---------------------------------------------------------------------------
def create_report_run(subject_id: str, *, reviewed_from: str | None = None) -> ReportRun:
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
```

L714–L732

```python

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
```

L812–L830

```python

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
```

L880–L898

```python

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
```

L797–L815

```python

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
```

L911–L929

```python

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
```

L543–L561

```python

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
```

L1043–L1061

```python

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
```

### deeptutor/services/pdf/report.py

仅thread生命周期租约：取消后底层线程仍可能工作。

L495–L513

```python

async def _publish_rendered(
    run: report_store.ReportRun,
    *,
    markdown: str,
    charts: list[dict[str, Any]],
    verification_status: str,
) -> tuple[report_store.ReportManifest, str]:
    """Render/verify/publish one already-complete run; no partial URL survives."""
    chart_names = [str(entry["path"]) for entry in charts]
    _sanitize_image_references(markdown, chart_names)
    report_md = run.workdir / "report.md"
    report_md.write_text(markdown, encoding="utf-8")
    pdf_path = run.workdir / "report.pdf"
    typst_bin = Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst"
    expected_workspace = str(store.current_subject_paths().workspace_root)
    rendered = await asyncio.to_thread(
        _render_in_owned_context,
        markdown,
```

L597–L615

```python
# ---------------------------------------------------------------------------
async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path | None = None,
    ode_rhs: str = "",
    subject_context: str = "",
) -> dict:
    """Generate a complete report and publish it as one atomic run.

    ``out_dir`` is retired: when a legacy caller still passes it, it must name
    the server-canonical public reports directory for this subject, otherwise
    the call is rejected before any run or file exists.

    Returns the public projection (``report_id``/``status``/``chart_count``/
    ``markdown_tokens``/``url``/``path``/``verification_status``) plus the
    rendered Markdown for consumers that already display it.  Every failure
```

L674–L692

```python

async def review_report(
    subject_id: str,
    *,
    report_id: str | None = None,
    legacy_path: str | None = None,
    instructions: str = "",
    subject_context: str = "",
) -> dict:
    """Review one known report and publish a **new** run without touching it.

    The target is discovered by ``report_store.resolve_report_for_review``;
    the original Markdown/PDF/charts are only read after their manifest hashes
    match, and every retained chart is copied into the new run's own directory.
    The reviewed Markdown may not introduce new image references, and the new
    document is never labelled as numerically verified (only the original
    figures retain their provenance).
    """
    if not isinstance(instructions, str) or not isinstance(subject_context, str):
```

L465–L483

```python

def _copy_verified_charts(
    source: report_store.ReportManifest, run: report_store.ReportRun
) -> list[dict[str, Any]]:
    """Copy every original chart into the new run after independent verification.

    This is a trusted server-side copy of bytes that already passed publication;
    it deliberately does **not** create a P34 attempt record or pretend a worker
    executed anything.  Only the real bytes (size/sha256) are bound for publish.
    """
    copied: list[dict[str, Any]] = []
    names: set[str] = set()
    for entry in source.files:
        if entry.role != report_store.ROLE_CHART:
            continue
        if entry.path in names:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        names.add(entry.path)
        data = _manifest_file_bytes(source, entry)
```

### deeptutor/subjects/wrong_book.py

只读：以attempt派生view为准；无attempt的stored mastery不可作证据。

L160–L178

```python

def _project(entry: dict) -> dict:
    """The read view of one entry.

    Mastery and status are always **derived from the attempt history**, never
    taken from the stored values: a legacy row carrying ``mastery: 1.0`` /
    ``status: "mastered"`` with no attempts reads as 0.0 / untracked. The
    projection is a copy — reading never rewrites the file.
    """
    view = dict(entry)
    correctness = [attempt["correct"] for attempt in entry.get("attempts", [])]
    view["mastery"] = mastery_score(correctness)
    view["status"] = classify(correctness)
    view.setdefault("archived", False)
    view.setdefault("attempts", [])
    return view


def load(subject_id: str) -> list[dict]:
```

L177–L195

```python

def load(subject_id: str) -> list[dict]:
    """Load the collection as read views; ``[]`` only when the file is absent."""
    path = _path(subject_id)
    return [_project(entry) for entry in _validate(json_store.read_list(path), path)]


def _save(subject_id: str, entries: list[dict]) -> None:
    """Atomically write the collection (the caller already holds the lock)."""
    path = _path(subject_id)
    json_store.atomic_write_list(path, entries)


def _recompute(entry: dict) -> dict:
    """Refresh mastery score + status from the attempt history.

    ``correct`` is taken as-is: :func:`_validate`/``record_attempt`` already
    guarantee it is a real bool, so nothing here can coerce ``"false"``.
    """
```

### deeptutor/subjects/exam_points.py

只读：本科/确认/学期语义和严格结构校验。

L120–L138

```python

def load(subject_id: str) -> list[dict]:
    """Load the collection; ``[]`` only when the file does not exist."""
    path = _path(subject_id)
    return _validate(json_store.read_list(path), path, subject_id)


def _save(subject_id: str, points: list[dict]) -> None:
    """Atomically write the collection (the caller already holds the lock)."""
    path = _path(subject_id)
    json_store.atomic_write_list(path, points)


def _text(raw: dict, key: str, default: str) -> str:
    value = raw.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise json_store.invalid_input(f"{key} 必须是字符串")
```

L68–L86

```python

def _validate(points: list[dict], source: Path, subject_id: str) -> list[dict]:
    """Check the fields this module reads; keep every unknown field.

    ``id`` and ``content`` are required; the display/query text fields and
    ``confirmed`` are validated only when present (a missing optional field is
    a legacy record, an explicitly wrong type is corruption).

    Two *identity* checks matter for the response contract (C01/R3): a stored
    ``subject_id`` that is present must be a legal slug **and** the subject this
    file belongs to — a record that claims another subject (or carries ``null``,
    a number, or ``bad/id``) must not be returned as if it belonged here. A
    missing key stays legal for legacy rows and is filled in the read view only.
    A present ``level`` must be one of :data:`STORED_LEVELS`.
    """
    for index, point in enumerate(points):
        if not isinstance(point.get("id"), str) or not point["id"]:
            raise json_store.corrupt_error(source.name, "考点记录缺少合法 id", index=index)
        if not isinstance(point.get("content"), str):
```

### deeptutor/subjects/json_store.py

只读：链接检查先于IO；目录短锁不是完整长任务协调协议。

L181–L199

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
```

L409–L427

```python

class _PathLock:
    """A cached reentrant thread lock + ``flock`` pair for one directory.

    One instance lives in :data:`_LOCKS` per normalized directory, so callers
    never re-create the lock (which would let two "holders" exist at once) and
    never re-open the ``flock`` fd while already holding it (which on Linux
    would drop the first lock: ``flock`` on a *different* fd for the same file
    is a separate lock, and closing the original fd releases it).
    """

    def __init__(self, key: str, lock_path: Path) -> None:
        self.key = key
        self.lock_path = lock_path
        self._rlock = threading.RLock()
        self._local = threading.local()

    def _handle(self) -> _LockHandle:
        handle: _LockHandle | None = getattr(self._local, "handle", None)
```

L709–L727

```python
@contextmanager
def json_transaction(lock_dir: Path) -> Iterator[JsonTransaction]:
    """Hold *lock_dir*'s process + OS lock for the duration of the block."""
    with JsonTransaction(Path(lock_dir)) as transaction:
        yield transaction


def transaction_depth(lock_dir: Path) -> int:
    """How many times the current thread holds *lock_dir* (diagnostics/tests)."""
    lock_dir = Path(lock_dir)
    try:
        key = str(lock_dir.resolve())
    except OSError:  # pragma: no cover - unreadable path
        return 0
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
    return 0 if lock is None else lock.held_depth()


```

### deeptutor/subjects/material_manifest.py

只读：source/hash/完整性及KB状态不能冒充全科任务租约。

L159–L177

```python

def source_files(raw_dir: Path, *, digest: bool = True) -> list[dict]:
    """The indexable regular files that currently make up a KB's index source."""
    return enumerate_files(raw_dir, extensions=supported_extensions(), digest=digest)


def fingerprint(records: Sequence[dict]) -> str:
    """Stable digest over ``(path, size, sha256)`` of a source set."""
    payload = [
        [str(item["path"]), int(item["size"]), str(item.get("sha256") or "")]
        for item in sorted(records, key=lambda entry: str(entry["path"]))
    ]
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def shape(records: Sequence[dict]) -> str:
    """Cheap digest over ``(path, size)`` only — used by read-only GETs."""
    payload = [
```

L97–L115

```python

def enumerate_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    digest: bool = True,
) -> list[dict]:
    """Enumerate sources with a typed boundary for filesystem failures."""
    try:
        return _enumerate_files(root, extensions=extensions, digest=digest)
    except OSError as exc:
        raise StorageIOError("索引源读取失败。", path=Path(root).name, cause=exc) from exc


def _enumerate_files(
    root: Path,
    *,
    extensions: Iterable[str] | None = None,
    digest: bool = True,
```

L387–L405

```python

def compare_manifest(
    manifest_files: Sequence[dict], actual_files: Sequence[dict], *, verify_hashes: bool = True
) -> dict:
    """Diff a recorded source set against what is on disk right now."""
    recorded = _by_path(manifest_files)
    actual = _by_path(actual_files)
    missing = sorted(set(recorded) - set(actual))
    extra = sorted(set(actual) - set(recorded))
    changed: list[str] = []
    for path in sorted(set(recorded) & set(actual)):
        left, right = recorded[path], actual[path]
        if int(left["size"]) != int(right["size"]):
            changed.append(path)
            continue
        if verify_hashes and right.get("sha256") and left["sha256"] != right["sha256"]:
            changed.append(path)
    return {
        "ok": not (missing or extra or changed),
```

L581–L599

```python

def project_status(
    *,
    kb_dir: Path,
    raw_dir: Path,
    materials_dir: Path | None,
    subject_id: str,
    kb_name: str,
    manager_status: dict | None,
    worker_alive: bool = False,
    queued: bool = False,
    task_id: str | None = None,
    verify_hashes: bool = False,
) -> dict:
    """Read-only projection of one subject KB's count, source and index state.

    Never writes, never schedules, never consults the auto-registering
    ``list_knowledge_bases``. The returned dict keeps the historical
    ``{status, progress, updated_at}`` shape (plus ``documents``/``task_id``/
```

### deeptutor/knowledge/progress_tracker.py

只读：状态显示不是跨进程互斥。

L34–L52

```python

class ProgressTracker:
    """Progress tracker"""

    def __init__(self, kb_name: str, base_dir: Path):
        self.kb_name = kb_name
        self.base_dir = base_dir
        self.kb_dir = base_dir / kb_name
        self.progress_file = self.kb_dir / ".progress.json"
        self._callbacks: list = []  # Support multiple callbacks
        self.task_id: str | None = None  # Task ID (for log identification)
        # This run's image coverage (P1-27), remembered so the *later* updates of
        # the same run — including the final COMPLETED event written by the
        # caller — keep it instead of overwriting it with a coverage-less dict.
        self._image_coverage: dict | None = None
        self._image_coverage_warning: str | None = None
        self._image_coverage_task: str | None = None

    def set_callback(self, callback: Callable[[dict], None]):
```

L264–L282

```python

    def get_progress(self) -> dict | None:
        """Get current progress"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _logger_instance().debug(f"Failed to read progress file for '{self.kb_name}': {e}")

        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager

            manager = KnowledgeBaseManager(base_dir=str(self.base_dir))
            status = manager.get_kb_status(self.kb_name)
            if status and status.get("progress"):
                return status.get("progress")
        except Exception as e:
            _logger_instance().debug(
```

### deeptutor/api/routers/outputs.py

只读：用真实鉴权下载链路，不改allowlist。

L18–L36

```python

def _request_path_service() -> PathService:
    """Resolve the workspace installed by ``require_auth`` without fallback.

    The general-purpose ``get_path_service()`` retains a compatibility fallback
    to the local admin workspace for non-request callers.  A download endpoint
    must fail closed instead: otherwise an authentication/context regression
    could expose an administrator artifact to an ordinary request.
    """
    user = get_current_user_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output not found")
    return get_path_service_for_scope(user.scope)


def _resolve_output(path_service: PathService, relative_path: str) -> Path:
    output_path = path_service.resolve_public_output_path(relative_path)
    if output_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output not found")
```

L40–L47

```python
@router.api_route("/{output_path:path}", methods=["GET", "HEAD"])
async def read_output(
    output_path: str,
    _auth: TokenPayload | None = Depends(require_auth),
) -> FileResponse:
    """Serve one allowlisted artifact from the authenticated user's workspace."""
    path = _resolve_output(_request_path_service(), output_path)
    return FileResponse(path)
```

### deeptutor/services/path_service.py

只读：全局getter可fallback；导出用store严格接口，private后缀仍不可下载。

L134–L152

```python

    def resolve_public_output_path(self, path: str | Path) -> Path | None:
        """Return a safe, public output file below this service's user root.

        Resolving and authorizing the path in one operation gives callers the
        exact canonical path they may read.  In particular, callers should not
        validate against one workspace and then reconstruct the file path from
        a different root.
        """
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.get_public_outputs_root() / candidate).resolve()
        else:
            candidate = candidate.resolve()

        root = self.get_public_outputs_root().resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError:
```

L131–L149

```python

    def get_public_outputs_root(self) -> Path:
        return self._user_data_dir

    def resolve_public_output_path(self, path: str | Path) -> Path | None:
        """Return a safe, public output file below this service's user root.

        Resolving and authorizing the path in one operation gives callers the
        exact canonical path they may read.  In particular, callers should not
        validate against one workspace and then reconstruct the file path from
        a different root.
        """
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.get_public_outputs_root() / candidate).resolve()
        else:
            candidate = candidate.resolve()

        root = self.get_public_outputs_root().resolve()
```

L444–L462

```python

def get_path_service() -> PathService:
    try:
        from deeptutor.multi_user.paths import get_current_path_service

        return get_current_path_service()
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "get_path_service() fell back to default instance; multi-user path resolution failed",
            exc_info=True,
        )
        return PathService.get_instance()


__all__ = [
    "AgentModule",
    "ChatWorkspaceFeature",
```

### deeptutor/multi_user/context.py

只读：contextvars跨to_thread和非管理员隔离测试。

L25–L43

```python

def get_current_user_or_none() -> CurrentUser | None:
    return _current_user.get()


def user_from_token_payload(payload: Any | None) -> CurrentUser:
    if payload is None:
        return local_admin_user()
    user_id = str(getattr(payload, "user_id", "") or "")
    username = str(getattr(payload, "username", "") or "local")
    role = str(getattr(payload, "role", "user") or "user")
    if role not in {"admin", "user"}:
        role = "user"
    if not user_id:
        user_id = "local-admin" if role == "admin" and username == "local" else username
    return CurrentUser(
        id=user_id,
        username=username,
        role=role,  # type: ignore[arg-type]
```

L13–L31

```python

def set_current_user(user: CurrentUser) -> Token[CurrentUser | None]:
    return _current_user.set(user)


def reset_current_user(token: Token[CurrentUser | None]) -> None:
    _current_user.reset(token)


def get_current_user() -> CurrentUser:
    return _current_user.get() or local_admin_user()


def get_current_user_or_none() -> CurrentUser | None:
    return _current_user.get()


def user_from_token_payload(payload: Any | None) -> CurrentUser:
    if payload is None:
```

### deeptutor/subjects/errors.py

只读：busy沿用kb_busy409，storage与provider投影不拼raw。

L38–L56

```python

class ErrorCode(str, Enum):
    """C02 表中的全部 code。"""

    INVALID_INPUT = "invalid_input"
    INVALID_SUBJECT_ID = "invalid_subject_id"
    SUBJECT_NOT_FOUND = "subject_not_found"
    ENTRY_NOT_FOUND = "entry_not_found"
    KB_NOT_FOUND = "kb_not_found"
    SCOPE_FORBIDDEN = "scope_forbidden"
    KB_NOT_READY = "kb_not_ready"
    KB_BUSY = "kb_busy"
    MATERIAL_OUT_OF_SYNC = "material_out_of_sync"
    STORAGE_CORRUPT = "storage_corrupt"
    STORAGE_IO = "storage_io"
    INTERNAL_ERROR = "internal_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    EMPTY_MODEL_OUTPUT = "empty_model_output"
```

L333–L351

```python

def map_subject_exception(exc: BaseException) -> SubjectOperationError:
    """把服务端异常映射成 C02 投影；未知异常安全兜底为 ``internal_error``。

    顺序很重要：``LLMReasoningBudgetExhausted`` 是 ``LLMProviderError`` 的子类，
    而 ``LLMEmptyResponseError`` **不是** ``LLMProviderError`` 的子类，两者都必须
    在各自的基类之前判断。

    这里**不猜**：泛型 ``ValueError``/``TypeError``/``KeyError`` 以及类名里带
    "timeout" 的普通异常都不是领域依据，一律按 :data:`ErrorCode.INTERNAL_ERROR`
    处理。调用者若已确认是参数问题，应显式构造 ``INVALID_INPUT``。
    """
    if isinstance(exc, SubjectOperationError):
        return exc

    if isinstance(exc, SubjectStorageError):
        code = ErrorCode.STORAGE_CORRUPT if exc.corrupt else ErrorCode.STORAGE_IO
        return subject_error(code, cause=exc)

```

L392–L410

```python

def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}


def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
    """WS terminal error / DONE failed 的 metadata 片段。"""
    return to_error_dict(error)


def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
    """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。

    调用者负责用它构造真正的 ToolResult；这里只固定失败语义与 error 数据，
    不返回任何 artifact URL。
    """
    return {"success": False, "metadata": {"error": to_error_dict(error)}}

```

### deeptutor/api/routers/unified_ws.py

只读：旧session删除后必须仍subject_not_found；复用已有发送回路。

L81–L99

```python

    async def reject_subject_error(
        exc: BaseException, *, session_id: str, reason: bool = False
    ) -> None:
        """Terminal rejection envelope for a subject-scope/storage failure.

        The client already renders terminal errors, so the *shape* stays exactly
        what the historical ``RuntimeError`` branches send (``session_id``, empty
        ``turn_id``, ``seq`` 0, ``status: rejected``); only the payload changes:
        ``content`` is the fixed C02 message and ``metadata.error`` carries the
        same ``{code, message, retryable}`` triple the HTTP entries return. The
        raw exception never reaches the wire, and the receive loop keeps running
        (``busy`` is not left set) so the next message can still be sent.
        """
        from deeptutor.subjects.errors import map_subject_exception, to_ws_error_metadata

        mapped = map_subject_exception(exc)
        metadata: dict[str, Any] = {
            "turn_terminal": True,
```

L162–L180

```python
                    # ``RuntimeError`` compatibility branch below is unchanged.
                    await reject_subject_error(
                        exc, session_id=str(msg.get("session_id") or "")
                    )
                    continue
                except RuntimeError as exc:
                    await safe_send(
                        {
                            "type": "error",
                            "source": "unified_ws",
                            "stage": "",
                            "content": str(exc),
                            "metadata": {"turn_terminal": True, "status": "rejected"},
                            "session_id": str(msg.get("session_id") or ""),
                            "turn_id": "",
                            "seq": 0,
                        }
                    )
                    continue
```

### tests/phase1/helpers.py

只读：临时HOME/runtime、network guard、route app/subjects原语。

L508–L526

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
```

L583–L601

```python

def make_subject(
    admin_root: Path,
    subject_id: str,
    *,
    term: str = "2026春",
    marker: str | None = None,
    description: str = "",
) -> SubjectPaths:
    """建合法的临时科目；展示标签保留，实际 id 按生产 slug 规则生成。

    后续消费者使用返回值的 subject_id，不能把展示标签当作路径 id。
    非法记录反例应从这个合法基准单独修改目标字段。
    """
    from deeptutor.subjects.store import slugify

    name = subject_id.strip()
    if not name:
        raise IsolationError("subject fixture label must be nonempty")
```

L1147–L1165

```python
@contextlib.contextmanager
def route_client() -> Iterator[Any]:
    """在当前隔离作用域内创建并**关闭**一个真实路由客户端。"""
    if _ACTIVE_ROOT.get() is None:
        raise IsolationError("route_client requires an active isolated_runtime scope")
    from fastapi.testclient import TestClient

    with TestClient(build_route_app()) as client:
        yield client


def shared_http_client() -> Any:
    """已移除：进程级共享客户端会把 lifespan 状态锚定到启动根。"""
    raise IsolationError(
        "shared_http_client() was removed in S01 rework01: a process-wide TestClient keeps "
        "lifespan state (cron/EventBus/LLM) anchored to the root it started in. "
        "Use route_client() inside an isolated_runtime scope."
    )

```

L1130–L1148

```python

def build_route_app():
    """构造只含真实科目路由的轻量 app，**不挂**后台 lifespan。

    用带完整 lifespan 的 ``deeptutor.api.main.app`` 做普通路由测试，会把 EventBus/cron/
    LLM 锚定在启动时的根上并跨隔离作用域存活。完整 lifespan 的验收放在独立子进程里
    （:func:`full_lifespan_probe`）。
    """
    from fastapi import FastAPI

    from deeptutor.api.routers import subjects

    app = FastAPI()
    app.include_router(subjects.router, prefix=ROUTE_PREFIX)
    return app


@contextlib.contextmanager
def route_client() -> Iterator[Any]:
```

### tests/phase1/test_p1_14.py

只读：知识点存储并发和未知字段保护的前置行为。

L47–L65

```python
@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_review_mixed_name_batch_rejects_invalid_element_without_write(p1_runtime, value):
    sid = _subject()
    kp.add_point(sid, name="existing")
    path = _kp_path(sid)
    before = path.read_bytes()
    with pytest.raises(SubjectOperationError) as error:
        kp.add_many(sid, ["valid new name", value])
    assert error.value.code == ErrorCode.INVALID_INPUT
    assert path.read_bytes() == before


@pytest.mark.parametrize("key", ["path", "source", "created_at"])
def test_review_knowledge_record_null_is_corrupt_not_missing(p1_runtime, key):
    sid = _subject()
    record = kp.add_point(sid, name="valid")
    assert kp.load(sid)
    record[key] = None
    path = _kp_path(sid)
```

### tests/phase1/test_p1_19.py

只读：reservation/worker全key忙协议不得破坏。

L183–L201

```python
# ---------------------------------------------------------------------------
def test_documents_counts_the_current_index_source(p1_subjects, p1_route_client, queued):
    subject = p1_subjects["科目A"]
    payload = _upload_ok(p1_route_client, subject, [("one.txt", b"one", None)])

    entry = _entry(p1_route_client, subject)
    assert entry["documents"] == 1
    assert entry["status"]["documents"] == 1
    assert entry["status"]["task_id"] == payload["task_id"]
    assert entry["status"]["status"] == "rebuilding"
    assert entry["status"]["busy"] is True
    assert entry["status"]["queued"] is True

    status = _status(p1_route_client, subject)
    assert status["kb_name"] == KB_NAME
    assert status["documents"] == 1
    assert set(status) >= {"kb_name", "status", "progress", "updated_at", "documents"}
    assert set(status["progress"]) >= {"stage", "message", "percent"}

```

### tests/phase1/test_p1_32.py

只读：已验收报告身份/发布/失败与私有字段边界。

L124–L142

```python
# ---------------------------------------------------------------------------
def test_two_runs_get_independent_ids_and_private_dirs(p1_subject) -> None:
    first = rs.create_report_run(p1_subject.subject_id)
    second = rs.create_report_run(p1_subject.subject_id)

    assert first.report_id != second.report_id
    assert len(first.report_id) == 32 and first.report_id == first.report_id.lower()
    assert first.staging_dir != second.staging_dir
    assert first.public_dir != second.public_dir
    assert first.staging_dir.parent.name == rs.REPORT_RUNS_DIRNAME
    assert first.public_dir.parent.name == rs.REPORTS_DIRNAME
    # create 只建私有目录：正式 URL/目录都不存在。
    assert first.staging_dir.is_dir() and second.staging_dir.is_dir()
    assert not first.public_dir.exists() and not second.public_dir.exists()
    assert rs.report_url(rs.read_run_manifest(first)) is None

    (first.workdir / "chart_1.png").write_bytes(_png_bytes())
    assert not (second.workdir / "chart_1.png").exists()
    assert sorted(item.name for item in first.workdir.iterdir()) == ["chart_1.png"]
```

### tests/phase1/test_p1_35.py

只读：同步publish兼容、真实Typst和失败保护；新增18回归的一部分。

L72–L90

```python

def test_duplicate_preparation_does_not_invalidate_the_legitimate_publication(subject) -> None:
    import pymupdf

    run = report_store.create_report_run(subject.subject_id)
    (run.workdir / "report.md").write_text("# 正文", encoding="utf-8")
    with pymupdf.open() as document:
        document.new_page()
        document.save(str(run.workdir / "report.pdf"))
    files = [report_mod._file_entry(run.workdir / name, role)
             for name, role in [("report.md", "markdown"), ("report.pdf", "pdf")]]
    prepared = report_store._prepare_report_publication(
        run, files=files, verification_status="not_requested")
    with pytest.raises(SubjectOperationError):
        report_store._prepare_report_publication(run, files=files, verification_status="not_requested")
    assert report_store.read_run_manifest(run).status == "running"
    committed = report_store._commit_report_publication(prepared)
    assert committed.status == "completed"
    assert (committed.public_dir / "report.pdf").is_file()
```

L57–L75

```python

def test_primary_report_error_survives_missing_cleanup_metadata(subject, monkeypatch) -> None:
    original = subject_error(ErrorCode.CHART_FAILED)

    async def failing(*args):
        for metadata in (subject.root / "_report_runs").glob("*/metadata.json"):
            metadata.unlink()
        raise original

    monkeypatch.setattr(report_mod, "_llm", failing)
    with pytest.raises(SubjectOperationError) as error:
        asyncio.run(report_mod.generate_report(subject.subject_id, title="题目", requirements=""))
    assert error.value is original
    assert report_store.active_report_runs() == ()


def test_duplicate_preparation_does_not_invalidate_the_legitimate_publication(subject) -> None:
    import pymupdf

```

L39–L57

```python
@pytest.mark.parametrize("kind", ["oversized", "symlink", "fifo"])
def test_file_entry_refuses_unbounded_or_nonregular_artifacts(tmp_path, kind) -> None:
    import os

    path = tmp_path / "report.pdf"
    if kind == "oversized":
        with path.open("wb") as handle:
            handle.truncate(report_store.MAX_PUBLISHED_FILE_BYTES + 1)
    elif kind == "symlink":
        target = tmp_path / "other.pdf"
        target.write_bytes(b"%PDF-keep")
        path.symlink_to(target)
    else:
        os.mkfifo(path)
    with pytest.raises(SubjectOperationError) as error:
        report_mod._file_entry(path, "pdf")
    assert error.value.code == ErrorCode.RENDER_FAILED


```

### tests/phase1/test_p1_36.py

只读：附件ID、review原件和复制PNG严格策略。

L543–L561

```python
@pytest.mark.parametrize("source_id", ["src-1", "/etc/passwd"])
def test_review_source_file_is_validated_and_used(subject, monkeypatch, source_id) -> None:
    captured = []

    async def reviewing(*args, **kwargs):
        captured.append(kwargs)
        return {"report_id": "a" * 32, "status": "completed", "chart_count": 0,
                "markdown_tokens": 12, "path": "subjects/s/reports/r/report.pdf",
                "url": "/api/outputs/subjects/s/reports/r/report.pdf",
                "verification_status": "not_requested"}

    monkeypatch.setattr(report_mod, "review_report", reviewing)
    result = asyncio.run(ReportTool().execute(
        _subject_id=subject.subject_id, action="review", source_file=source_id,
        requirements="核查附件要求", _source_index={"src-1": "附件独有要求-97ab"},
    ))
    if source_id == "src-1":
        assert result.success
        assert "附件独有要求-97ab" in captured[0]["instructions"]
```

L571–L589

```python
@pytest.mark.parametrize("fault", ["animated", "oversized", "warning"])
def test_copied_chart_uses_the_same_strict_png_policy(monkeypatch, fault) -> None:
    from io import BytesIO
    import warnings

    from PIL import Image

    data = _png_bytes()
    if fault == "animated":
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "red").save(
            buffer, format="PNG", save_all=True,
            append_images=[Image.new("RGB", (20, 20), "blue")], duration=100,
        )
        data = buffer.getvalue()
    elif fault == "oversized":
        data += b"\0" * (10 * 1024 * 1024)
    else:
        real_open = Image.open
```

### tests/phase1/test_p1_38.py

只读：实际HTTP并发/线程/取消/路径边界，不能弱化。

L349–L367

```python
@pytest.mark.asyncio
async def test_review_pack_copy_does_not_block_http_and_cancellation_never_commits(
    p1_subjects, monkeypatch
) -> None:
    import shutil

    subject = p1_subjects["科目A"]
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    cleaned = threading.Event()
    real_copy, real_copyobj = shutil.copyfile, shutil.copyfileobj
    real_unlink = Path.unlink

    def unlinking(path, *args, **kwargs):
        result = real_unlink(path, *args, **kwargs)
        if path.name.startswith(".review-guide-") and path.name.endswith(".part"):
            cleaned.set()
        return result

    def blocking(operation):
```

L407–L425

```python
@pytest.mark.parametrize("cancel", [False, True])
async def test_report_publication_copy_keeps_loop_responsive_and_cancel_never_commits(
    p1_subjects, monkeypatch, cancel
) -> None:
    entered, release = threading.Event(), threading.Event()
    finished, cleaned = threading.Event(), threading.Event()
    subject = p1_subjects["科目A"]
    original_copy = report_store._copy_and_hash

    def copying(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5)
            return original_copy(*args, **kwargs)
        finally:
            finished.set()

    async def writer(*args):
        return "# 报告\n\n发布复制测试。\n"
```

### plans/phase1/DATA_CONTRACTS.md

C10/C12与附录A权威固定契约。

L127–L145

```text

## C10：知识点掌握证据与关联

entry 层保持 C05 的 0/untracked。聚合 knowledge point 无有作答证据的关联错题时 mastery=null、evidence_count=0、assessment_status=unassessed；有证据时沿用有效关联 entry mastery 均值（三位），assessment_status=assessed。没有证据不等于已掌握。旧接口新增字段而不重写历史 stored mastery；模板/前端消费 null 显示“未评估”，不能显示 None/NaN。

知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
{"report_id":"...","status":"completed","chart_count":1,"markdown_tokens":600,"url":"/api/outputs/subjects/复变函数/reports/<rid>/report.pdf","path":"<server-owned-path>","verification_status":"not_requested"}
```

正文完整，所有声明图表均成功且有效，PDF 确实编译/可打开后才 completed/发布 URL。允许无声明图的纯正文报告，但不能把声明图的失败变成 completed；缺图为 chart_failed。CHART 正则识别与替换使用同一个 match，支持零空格/多空格。脚本成功需退出码为 0（ExecResult.ok 本身不检查 exit_code），目标 PNG 是当前任务的新常规非 symlink 文件，Pillow验证有效、路径被限定、size 上限，不能仅检查 exists。所有正文/核查 Markdown 图片引用都只能是本任务经过验证的 chart_N.png 白名单；包括模型自行输出的图片引用，也不得接受外部URL、绝对/相对穿越或引号注入到Typst。临时脚本/错误日志不能随目录整包发布，正式目录只发布文档、验证图片及私有manifest。

```

L157–L175

```text

## C12：导出内容与完整性

保留 `GET /subjects/{id}/export`；用 uuid 导出文件名，响应保留 url 并增加 export_id/schema_version。ZIP schema_version=1，内容固定：

```text
manifest.json                        版本、subject元信息、文件清单、覆盖/排除声明
subject.json                         index.json 中该 subject 的完整记录
learning/                            该科材料、KB原件/已完成索引、学情JSON
artifacts/                           该科 completed PDF/DOCX/图表/正文
```

manifest.files 每项：path（ZIP 内 POSIX 相对路径）、size、sha256、category。清单覆盖除了 manifest 自身以外的全部归档条目；subject.json 也计算 hash。subject metadata 包括 id/name/description/term/created_at 和未知非敏感历史字段。

明确排除 settings、model catalog、密钥、全局其他科目/用户数据、所有 subject-backup-*.zip、本次/历史导出 ZIP、锁/临时文件、_report_runs 与 failed/incomplete 产物。聊天历史没有可靠科目归属，所以 manifest.exclusions 写 `chat_history:not_included_no_subject_binding`，界面称“科目资料与学习记录导出”，不能称完整聊天备份。不新增 import/恢复 API。

先检查该科没有活跃资料更新/索引/报告发布，再在 subject snapshot 锁下把权威数据和 completed 产物复制到私有 staging，释放锁后压缩；内容变化/hash不符则失败或重试一次，不产出假 complete 清单。任何 symlink 或越界源条目拒绝导出，不跟随到外面，不把当前 ZIP 加入下一份。用户删除科目与导出必须互斥。归档失败只清理本次 staging/临时 ZIP，不删除旧导出。

## C13：UI、裁剪与能力说明
```

L220–L229

```text
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

## 附录B：机器可检验的字段示例

`schemas.json` 使用 JSON Schema 2020-12 的 `$defs` 定义错误、规范化批改/检测结果、上传、作用域、知识点评估、图像覆盖、报告、source manifest、导出manifest和completion。`examples.json` 记录每种形状的有效样例及必须拒绝的反例，均为虚构数据。

Schema验证字段和枚举，不替代行为验证：路径包含关系、授权、来源真实性、事务锁、失败字节不变、provider截断、网络/沙箱等仍按C01–C14执行测试。也不要求生产添加jsonschema依赖；可用既有Pydantic/代码验证实现相同义务。schema中的批改输出是trim/lower归一化后的结果，允许预验证进行C05规定的大小写归一化。
```

### plans/phase1/schemas.json

按定义验证KnowledgeAssessment、ExportManifest及文件entry。

L610–L628

```json
    },
    "KnowledgeAssessment": {
      "type": "object",
      "properties": {
        "mastery": {
          "anyOf": [
            {
              "type": "number",
              "minimum": 0,
              "maximum": 1
            },
            {
              "type": "null"
            }
          ]
        },
        "evidence_count": {
          "type": "integer",
          "minimum": 0
```

L1036–L1054

```json
    },
    "ExportManifest": {
      "type": "object",
      "properties": {
        "schema_version": {
          "const": 1
        },
        "export_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{32}(?![\\s\\S])"
        },
        "subject": {
          "$ref": "#/$defs/SubjectRecord"
        },
        "files": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/ExportFile"
          }
```

### plans/phase1/cards/P1-39.md

P39目标/证据/范围/完成条件。

L4–L22

```text

## 目标

未作答知识点不标已掌握，关联统计随已有学情变更有效且可重建。

## 已有问题证据

scores else 1.0错误；build关联之后新/归档/删除可能过时。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C10；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。

## 允许更改范围

- `deeptutor/subjects/knowledge_points.py`
```

L19–L37

```text

## 允许更改范围

- `deeptutor/subjects/knowledge_points.py`
- `deeptutor/services/pdf/review_guide.py`
- `deeptutor/api/routers/subjects.py`
- `tests/phase1/test_p1_39.py`

符号范围：aggregate/context_summary/review input及build_knowledge_points；不自动抽取教材知识点。

历史单卡模式的证据目录为 `.phase1-evidence/P1-39/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 仅有有效attempt的未归档同科entry计算均值；无证据null+evidence_count+unassessed。
2. 派生关联对照当前kp/记录，build幂等，保留人工点和未知字段。
3. review/template处理null写未评估，不输出None/NaN。

## 证据：如何证明完成
```

L36–L54

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] 无entry/无attempt都是未评估
- [ ] 有attempt均值三位
- [ ] 归档/删除后统计不残留
- [ ] build重复不重复
- [ ] 人工点保留、另科学情不进统计

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_39.py
```

## 完成条件

```

### plans/phase1/cards/P1-40.md

P40包含协调者明确补充的活动协议接入授权。

L4–L22

```text

## 目标

ZIP含元信息、学情与completed产物，清单hash吻合，无密钥/递归/别科数据。

## 已有问题证据

旧export只src subject学习树，没有subject registry/outputs且未来可能递归ZIP。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C12, C01；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。

## 允许更改范围

- `deeptutor/subjects/export_bundle.py`
```

L19–L37

```text

## 允许更改范围

- `deeptutor/subjects/export_bundle.py`
- `tests/phase1/test_p1_40.py`

- `deeptutor/subjects/subject_operations.py`
- `deeptutor/subjects/uploads.py`
- `deeptutor/services/pdf/report_store.py`
- `deeptutor/services/pdf/report.py`
- `deeptutor/api/routers/subjects.py`
- `tests/phase1/test_subject_operations.py`

2026-10-19协调者补充授权：原白名单缺少长任务互斥接入点，已明确增加共享subject_operations及上传/报告/复习包生命周期的最小适配，详见START_S10。禁止只在导出端查一个内存bool就宣称完成；不重写索引器或降低报告验证。

符号范围：新snapshot/archive helper；不在本卡改HTTP接口或新增恢复API。

历史单卡模式的证据目录为 `.phase1-evidence/P1-40/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

```

L43–L61

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] subject元信息/学情/PDF/图在正确分组
- [ ] 每文件sha256/size匹配
- [ ] 第二次导出不包含首ZIP
- [ ] 设置密钥/别科/未完成run未入包
- [ ] active修改409、snapshot故障不发布
- [ ] symlink拒绝

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_40.py
```

## 完成条件
```

### plans/phase1/cards/P1-41.md

P41真实导出HTTP和鉴权下载。

L4–L22

```text

## 目标

现有export路由返回真实完成包URL且ZIP压缩不阻塞事件循环。

## 已有问题证据

旧route直接同步遍历/压缩、名称秒时间、范围不足。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C12, C02, C13；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。

## 允许更改范围

- `deeptutor/api/routers/subjects.py`
```

L19–L37

```text

## 允许更改范围

- `deeptutor/api/routers/subjects.py`
- `tests/phase1/test_p1_41.py`

符号范围：export_subject_data函数；复用outputs鉴权，禁止改全局public allowlist。

历史单卡模式的证据目录为 `.phase1-evidence/P1-41/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 委托export_bundle off-loop，响应增加export_id/schema_version保留url。
2. 错误用C02，失败不给url；取消仅清理自己tmp。
3. 通过已有outputs下载链路验证ZIP同用户可下载，不为manifest.json开放任意静态读取。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：
```

L34–L52

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] HTTP完成后url实际可下载ZIP
- [ ] export失败非2xx无链接
- [ ] 并发不同科导出不串
- [ ] 压缩耗时时另一只读请求可先返回
- [ ] 未授权输出仍拒绝

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_41.py
```

## 完成条件

```

### plans/phase1/cards/P1-54.md

P54两树删除/忙科目/IO失败与旧session。

L4–L22

```text

## 目标

删除不留下本科学习产物或忽略IO错误，也不与活跃索引/报告/导出竞争。

## 已有问题证据

当前store只rmtree学习树且ignore_errors，注册先删；产物树保留。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C03, C01, C12；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。

## 允许更改范围

- `deeptutor/subjects/store.py`
```

L19–L37

```text

## 允许更改范围

- `deeptutor/subjects/store.py`
- `deeptutor/api/routers/subjects.py`
- `tests/phase1/test_p1_54.py`

符号范围：delete_subject数据函数与delete route；不扫描清理其他科/legacy目录。

历史单卡模式的证据目录为 `.phase1-evidence/P1-54/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 校验current subject两树安全及busy状态；锁内处理，成功才移注册。
2. 两树清理失败返回安全错误/保留注册及诊断，允许后续重试，不误报deleted。
3. 禁止跟随symlink/删除别科输出；只删明确当前科产物，不触碰证据目录。

## 证据：如何证明完成

```

L35–L53

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] A删除两树、B字节不变
- [ ] busy索引/报告/导出409
- [ ] 模拟rmtree失败非deleted且注册保留
- [ ] 越界/symlink拒绝
- [ ] 删除后旧session发送明确subject_not_found

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_54.py
```

## 完成条件

```

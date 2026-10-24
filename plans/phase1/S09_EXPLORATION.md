# S09 已探索的文件清单 + 关键片段

2026-10-17，S08-final签收后的实际源码。配套START_S09和最新receipt。先核对完整SHA，再按符号直达，不做全仓orientation。下面旧不安全片段仅是定位点，不能当安全实现复用。

## 接缝决策

- P35→P36→P37→P38一次交付，9路径/99项capture；94条当前基准中90只读、4条窄允许修改（report.py/subjects.py/agentic_pipeline.py/P31测试）。ReportTool虽不在94条中，仍是已探索现有文件，四个P35–38测试当前不存在。
- S08基础模块全部只读；同一个run只能顺序图表/ODE，独立run可并发。新输出由ReportStore决定，调用方不再自己写公开MD或按秒猜URL。
- P31有旧fixture依赖裸host helper、未登记subject、假PNG/无PDF；其“图失败仍返回成功”是应删除的错误行为预期。已提前窄授权fixture和7个pipeline接缝改为新接口/合法数据，纯输入门不动。此为修复接线的必要测试适配，非让生产代码保留旧漏洞。
- source_index=context.metadata中的source_id→全文字典，无scope/无附件也覆盖模型kwargs为空。source_file只是这个字典的key，不是宿主路径。
- 生成图通过P34；review复制图在report.py做可信受限复制/PNG验证，不伪造worker成功记录。原件hash保持，review新rid。
- 图片引用只允许服务端已验证的本run basename；Typst模板只用固定白名单生成image语句，不能插入模型原路径。真实PDF用现有parser验证。
- pypdf、PyMuPDF、Pillow、python-docx与本仓tools/bin/typst已存在。工具/依赖只读，无安装/下载。真实Typst图文验证本阶段必做，最终OS/浏览器验收仍S15。
- 复习包保留原format/url等接口，先私有渲染验证后原子公开；不为ReportFile新增DOCX角色。同步render/重IO使用to_thread并验证实际非管理员context传播，取消后无正式产物。

## 文件清单与完整SHA256

| 文件 | SHA256 | 用途 |
|---|---|---|
| `deeptutor/services/pdf/report.py` | `26c9395f7ec2c185d13abc2f3c526bde61a90b52bcff07e68121af1ffe9d379e` | P35/36/38：唯一报告编排，旧裸执行与原地review需替换。 |
| `deeptutor/tools/report_tool.py` | `a9ab8549c41cf2b4a49c8c7769169825a2afc86ff17490cb0f3f693d34d3410a` | P36/37：任意report_path、旧URL与另写MD都在这里，不能保留。 |
| `deeptutor/agents/chat/agentic_pipeline.py` | `28d484ab1d536f427a43d7137c234a6ca37899d799bc845efed0ef510a51c7f3` | P36：生成报告分支需无条件覆盖scope/hint/index，空scope同样覆盖。 |
| `deeptutor/api/routers/subjects.py` | `9349cd452698f8a52df2aab3d2ed5ec06039c521592f9c9f69409c1cdf7c59db` | P37/38：报告与复习包入口，只改这两个现有路由。 |
| `deeptutor/services/pdf/report_inputs.py` | `451304af413499067650b540d39fd1132a870b1ab2f9fa8f8583c5efabb806e2` | 只读，S08已签收纯输入/JSON/placeholder接口。 |
| `deeptutor/services/pdf/report_store.py` | `0952cd787be05047689bd7239f85d2eb283a6212585b87cfe6ff010b465fa1b5` | 只读：当前user身份、run、完成发布及review已知目标。 |
| `deeptutor/services/pdf/chart_executor.py` | `22125329ade3a332408d47ec01880c2c8ddab31e40f79362091cb63f5924257d` | 只读：同run执行互斥，独立run并发；失败门不能绕过。 |
| `deeptutor/services/pdf/chart_validation.py` | `3d71c01ef23fa803c2e4a8a0b6a2d42004531ce60f37dd33e0adaa67ffd2f20a` | 只读：生成图绑定当前成功worker；复制旧图需report.py独立受限验证，不伪造worker。 |
| `deeptutor/services/pdf/chart_worker.py` | `b8c9e8b0606379664e4c4127356dfb41829ccb096558fb4d2ad4cc908bd6fea4` | 只读：可信父在隔离内计算参考，采样超额拒绝。 |
| `deeptutor/services/pdf/review_guide.py` | `34df402d9820a82acefae768436aead50cc80501abdff415f6d84595730e9a59` | 只读：已有S02生成门/字体/可信Typst及DOCX；调用方负责私有渲染与offload。 |
| `deeptutor/subjects/generation.py` | `831c50decd82ee2977e2e3046346044d7ab7f08659cd25c79070d015f63969bc` | 只读：所有完整响应/预算/截断仍用此门。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 只读：HTTP/Tool统一固定安全错误，绝不拼raw原因。 |
| `deeptutor/api/subject_route.py` | `c7d58298831a896fc7e2eadcd660b38e1c84c40bd246dfe4074106a869445e9c` | 只读：router已包C02，并保留原生401/403/422。 |
| `deeptutor/services/session/source_inventory.py` | `75e070d48cf5645d3ae4c9eea97f305a799872e77fabbfc79b033f7158326f31` | 只读：source_index是真正的source_id到已附全文。 |
| `deeptutor/capabilities/explore_context/capability.py` | `71ef3ded633c925486df16ebf3a1f6428be40277248849e55f94cc500e92fd88` | 只读：context.metadata source_index真实来源语义。 |
| `deeptutor/core/tool_protocol.py` | `8d07f2b6462c8fc74bb34edebf2b070873e6c44c05dadbeb571f2bd0853f32e4` | 只读：ToolResult构造字段，错误投影进metadata。 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | 只读：已登记subject与strict current-user路径。 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 只读：链接/路径检查在读写前，别随手resolve后信任。 |
| `tests/phase1/test_p1_31.py` | `f67c34b0415ba5cda5e92d9b7e8d2ca3737cb20512d40936987bb91500d99f60` | 窄授权旧pipeline接缝；纯输入assert全部保持，旧坏成功需改。 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 只读：隔离runtime/真实route client与合法subject fixtures。 |
| `tests/phase1/test_p1_56.py` | `51ec2c49f35e40d0cec14b5da2d167516c74e9d99d344b98077f9ab99d3adb4f` | 只读：既有真实review-pack错误边界回归。 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | C11及固定基础接口权威；不得自行改契约。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | ReportFile/Metadata/Response完整定义按名读取。 |
| `plans/phase1/cards/P1-35.md` | `a120454c222c7f842200517657d1cbd43b2d4ec93f4e742cf5daeb90948e36e0` | P35包括已同步的P31测试适配窄范围。 |
| `plans/phase1/cards/P1-36.md` | `0640a55832e9a91424f0c7d92b629a3fbb2c5bacaae0e650b2cacd65f2997798` | P36 review与附件source_id，不新增API。 |
| `plans/phase1/cards/P1-37.md` | `444ccb41d087f5b6d69faef6a204055543e86999cb256dcd184560c4080853d0` | P37两入口/复习包统一失败行为。 |
| `plans/phase1/cards/P1-38.md` | `4562b3375993fa675f888f2a9a31eb68f65d195ec92f67b7a924ebb229364105` | P38真实并发请求/线程用户/cancel。 |

## 关键片段

### deeptutor/services/pdf/report.py

P35/36/38：唯一报告编排，旧裸执行与原地review需替换。

L75–L89

```python

async def _llm(prompt: str, system: str) -> str:
    """One report-pipeline completion.

    Runs through the shared subject-feature helper, which applies the explicit
    generation budget (a reasoning model bills its chain-of-thought against the
    same ``max_tokens``, and the 4096 default can be spent entirely on reasoning)
    and reports a budget-truncated generation by name instead of returning "".
    """
    cfg = get_llm_config()
    return await complete_subject_text(
        prompt=prompt,
        system_prompt=system,
        model=cfg.model,
        api_key=cfg.api_key,
```

L153–L167

```python

def _run_chart_code(code: str, workdir: Path) -> bool:
    """Execute LLM-generated matplotlib code in a subprocess."""
    from deeptutor.services.pdf.review_guide import _FONT_DIR

    font_paths = [str(_FONT_DIR / n) for n in ("SimsunExtG.ttf", "msyh.ttc")]
    script = workdir / "_chart.py"
    script.write_text(
        _FONT_REGISTER.format(font_paths=font_paths) + code, encoding="utf-8"
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(workdir),
            capture_output=True,
```

L94–L108

```python

def _chart_ode_matches(workdir: Path, ode_rhs: str) -> bool:
    """Verify the chart's f(x, y) against the declared ODE on test points."""
    check = f"""
import sys
sys.path.insert(0, {str(workdir)!r})
import _chart as _c
_declared = lambda x, y: {ode_rhs}
_pts = [(-2.5, 1.0), (0.0, 0.5), (1.7, -2.0), (2.2, 2.5), (-0.8, -3.0)]
_got = [_c.f(x, y) for x, y in _pts]
_exp = [_declared(x, y) for x, y in _pts]
_err = max(abs(a - b) for a, b in zip(_got, _exp))
print("ODE_CHECK_ERR", _err)
raise SystemExit(0 if _err < 1e-6 else 1)
"""
```

L179–L193

```python

def _render_report_pdf(markdown: str, charts: list[Path], out_path: Path, typst_bin: Path) -> bool:
    """Render report markdown (with chart image lines) to PDF via Typst."""
    # ``_md_to_typst`` escapes Typst markup in body text, so the ``#image(…)``
    # call cannot ride through it as a literal line: the leading ``#`` and the
    # ``_`` in ``chart_1.png`` would be escaped and the chart would silently
    # degrade into literal text (a PDF with no embedded images). Park each
    # chart behind an escape-proof token and substitute the real call in after
    # the conversion.
    tokens: dict[str, str] = {}
    lines = []
    for line in markdown.splitlines():
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
        if m:
            token = f"CHARTIMAGE{len(tokens)}TOKEN"
```

L207–L221

```python

async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path,
    ode_rhs: str = "",
    subject_context: str = "",
) -> dict:
    """Generate a report with charts and render it to PDF.

    ``subject_context`` is the per-subject learner summary built by the chat
    pipeline (``_report_ctx_hint``). It is included in the writer prompt so the
    report can key off the subject's wrong-book and exam-point state; an empty
```

L318–L330

```python

async def _render_reviewed(markdown: str, out_dir: Path, old_md: Path) -> Path | None:
    """Render a revised report PDF next to its markdown source."""
    # Chart image references are relative to the .md, which lives beside the
    # charts — the markdown is rewritten in place below, so the paths resolve.
    ts = int(time.time())
    pdf_path = out_dir / f"report-{ts}.pdf"
    typst_bin = Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst"
    ok = _render_report_pdf(markdown, [], pdf_path, typst_bin)
    if not ok:
        return None
    old_md.write_text(markdown, encoding="utf-8")
    return pdf_path
```

### deeptutor/tools/report_tool.py

P36/37：任意report_path、旧URL与另写MD都在这里，不能保留。

L33–L47

```python

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_report",
            description=(
                "课程报告助手：用户要求【生成或核查课程报告】时必须调用本工具（不要自己用文字替代，"
                "本工具产出排版好的 PDF 并给出下载链接）。"
                "action=create：传入 title 与 requirements（可附教师题目文件路径 source_file、"
                "微分方程 ode_rhs 如 'x**2 - y'）。"
                "action=review：核查最近一次生成的报告并用 LLM 修复后重新渲染 PDF——"
                "**无需也不允许传 report_path**（工具自动取最近报告），不要自行查找或读取报告文件。"
            ),
            parameters=[
                ToolParameter(name="action", type="string", enum=["create", "review"], required=True),
                ToolParameter(name="title", type="string", description="报告题目", required=False),
```

L73–L87

```python

        if action == "review":
            report_path = str(kwargs.get("report_path") or "").strip()
            if report_path in ("latest", "recent", "最近", "最新", "last"):
                report_path = ""
            if not report_path:
                # No path given: review the most recent report for this subject.
                candidates = sorted(out_dir.glob("report-*.md"))
                if not candidates:
                    return ToolResult(content="该科目还没有可核查的报告，请先创建一份。", success=False)
                md_path = candidates[-1]
            else:
                md_path = Path(report_path).with_suffix(".md")
            if not md_path.exists():
                # Accept the .pdf path: look for the sibling .md.
```

L118–L132

```python
        # The teacher's assignment file may ride as an attachment content ref.
        source_file = str(kwargs.get("source_file") or "").strip()
        if source_file and requirements:
            requirements = f"{requirements}\n（教师题目文件：{source_file}）"

        try:
            result = await report_mod.generate_report(
                subject_id,
                title=title,
                requirements=requirements,
                out_dir=out_dir,
                ode_rhs=ode_rhs,
                # Server-injected per-subject learner summary (wrong-book and
                # exam-point counts). Never taken from the model.
                subject_context=str(kwargs.get("_report_ctx_hint") or "").strip(),
```

L123–L137

```python
        try:
            result = await report_mod.generate_report(
                subject_id,
                title=title,
                requirements=requirements,
                out_dir=out_dir,
                ode_rhs=ode_rhs,
                # Server-injected per-subject learner summary (wrong-book and
                # exam-point counts). Never taken from the model.
                subject_context=str(kwargs.get("_report_ctx_hint") or "").strip(),
            )
        except LLMEmptyResponseError as exc:
            # A blank body would otherwise render as a "successful" empty PDF.
            return ToolResult(content=f"报告生成失败：{exc.message}", success=False)
        if not result["pdf_ok"]:
```

L142–L151

```python
        md_path = out_dir / md_name
        md_path.write_text(result["markdown"], encoding="utf-8")
        return ToolResult(
            content=(
                f"报告《{title}》已生成（{result['chart_count']} 张图表，{result['markdown_tokens']} tokens）。"
                f"\n\n下载：`/api/outputs/subjects/{subject_id}/reports/{pdf_path.name}`"
                f"\n\n如需我核查修改，请回复：核查这份报告（或指出具体问题）。"
                f"\n\n（报告路径：{md_path}）"
            )
        )
```

### deeptutor/agents/chat/agentic_pipeline.py

P36：生成报告分支需无条件覆盖scope/hint/index，空scope同样覆盖。

L122–L136

```python

def _context_subject_id(context: UnifiedContext) -> str | None:
    """The turn's validated subject, read verbatim from the runtime metadata.

    ``None`` (no subject) and ``""`` are both "no subject"; a value is the slug
    ``turn_runtime`` already validated. This is the only source the tool scope is
    built from — the model cannot contribute to it.
    """
    raw = (context.metadata or {}).get("subject_id")
    if isinstance(raw, str):
        value = raw.strip()
        return value or None
    return None


```

L1136–L1150

```python
            kwargs["_tool_loader"] = self._deferred_loader
        elif tool_name == "generate_report":
            subject_id = str(context.metadata.get("subject_id", "") or "").strip()
            # Both the scope and the learner summary are server-owned: an empty
            # subject means no scope at all, so neither is set. Building the
            # hint unconditionally used to emit "当前科目：（错题 0 道、考点 0
            # 条）" and burn two JSON reads for a turn with no subject.
            if subject_id:
                kwargs["_subject_id"] = subject_id
                kwargs["_report_ctx_hint"] = (
                    f"当前科目：{subject_id}（错题 {_wrong_book_count(subject_id)} 道、"
                    f"考点 {_exam_point_count(subject_id)} 条）"
                )
        elif tool_name == "exec":
            from deeptutor.services.sandbox import Mount
```

### deeptutor/api/routers/subjects.py

P37/38：报告与复习包入口，只改这两个现有路由。

L52–L66

```python
#: 科目路由专用错误出口：只影响本 router，其他上游 router 的异常机制不变（C02/P1-56）。
router = APIRouter(route_class=SubjectRoute)

#: Extension → knowledge type for ``type=auto`` uploads. The single source of
#: truth lives with the upload preflight (``subjects/uploads.py``); the name is
#: re-exported here because it is part of this router's historical surface.
TYPE_BY_EXTENSION = uploads.TYPE_BY_EXTENSION
ALLOWED_TYPES = uploads.ALLOWED_TYPES


def _require_subject(subject_id: str) -> dict:
    """Resolve one subject in the **current user's** registry (C01/C02).

    The id is validated as a plain slug before anything is resolved: an id that
    cannot be a single path segment is ``invalid_subject_id`` (400) rather than a
```

L61–L75

```python

def _require_subject(subject_id: str) -> dict:
    """Resolve one subject in the **current user's** registry (C01/C02).

    The id is validated as a plain slug before anything is resolved: an id that
    cannot be a single path segment is ``invalid_subject_id`` (400) rather than a
    lookup miss, and no "clean-up" or admin fallback is attempted. A well-formed
    but unregistered id raises the named ``subject_not_found`` (404) instead of an
    ``HTTPException`` whose detail echoed the caller's input.
    """
    if not store.is_valid_subject_id(subject_id):
        raise store.InvalidSubjectIdError(subject_id)
    subject = store.get_subject(subject_id)
    if subject is None:
        raise store.SubjectNotFoundError(subject_id)
```

L745–L759

```python
@router.post("/{subject_id}/review-pack")
async def generate_review_pack(
    subject_id: str,
    format: str = Form("pdf"),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a printable review guide from exam points + wrong book.

    Writes the artifact under the public outputs tree and returns a
    download URL served by ``/api/outputs``.
    """
    _require_subject(subject_id)
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.pdf import review_guide
```

L780–L794

```python
    ok = (
        review_guide.render_pdf(markdown, out_path)
        if format == "pdf"
        else review_guide.render_docx(markdown, out_path)
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Render failed (is Typst installed?)")
    return {
        "format": format,
        "markdown_tokens": review_guide.estimate_tokens(markdown),
        "url": f"/api/outputs/subjects/{subject_id}/review-guide-{ts}.{ext}",
        "path": str(out_path),
    }


```

L823–L837

```python
@router.post("/{subject_id}/report")
async def generate_subject_report(
    subject_id: str,
    title: str = Form(...),
    requirements: str = Form(""),
    ode_rhs: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a chart-bearing report and export it as PDF."""
    _require_subject(subject_id)
    if not title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.pdf import report as report_mod

```

### deeptutor/services/pdf/report_inputs.py

只读，S08已签收纯输入/JSON/placeholder接口。

L80–L94

```python

def chart_target_basename(name: object, *, what: str = "图表文件名") -> str:
    """校验并返回服务端预分配的固定图名（``chart_N.png``，N 1..8）。

    纯输入 helper：report_inputs / chart_executor / report_store 共用同一份正则，
    避免三处各写一套"看起来差不多"的校验。非法输入抛 C02 ``invalid_input``。
    """
    if not isinstance(name, str):
        raise json_store.invalid_input(f"{what}必须是字符串")
    if CHART_BASENAME_RE.fullmatch(name) is None:
        raise json_store.invalid_input(
            f"{what}必须是服务端预分配的 chart_N.png（N=1..{MAX_CHARTS}）"
        )
    return name

```

L248–L262

```python

def validated_chart_placeholders(markdown: object) -> tuple[ChartPlaceholder, ...]:
    """识别并校验占位符：每张都要有描述，且总数不超过 :data:`MAX_CHARTS`。

    这是 report.py 与后续 P35 共用的入口——数量超限是明确失败，不是静默截断。
    返回的对象同时带 ``raw`` 与 ``spec``，调用方替换时用**同一个 match** 的原文，
    不需要按描述重新拼一遍占位符。
    """
    placeholders = find_chart_placeholders(markdown)
    if len(placeholders) > MAX_CHARTS:
        raise json_store.invalid_input(
            f"报告声明的图表数量超过上限（最多 {MAX_CHARTS} 张）"
        )
    for placeholder in placeholders:
        if not placeholder.spec:
```

L324–L338

```python

def parse_chart_code_response(raw: object) -> str:
    """从模型响应里取出图表代码：``{"code": "<非空字符串>"}``。

    ``code`` 缺失、不是字符串（list/dict/数字/bool/None）、只有空白，都是
    ``invalid_model_output``。返回前还要证明这段文本**可以 UTF-8 编码**：孤立
    surrogate（JSON 里的 ``"\\ud800"``）能通过 JSON 解析，却会在写脚本文件时炸成
    裸 ``UnicodeEncodeError``；这里提前映射成同一个固定 C02 错误。
    """
    payload = parse_chart_object(raw)
    if "code" not in payload:
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
    code = payload["code"]
    if not isinstance(code, str) or not code.strip():
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
```

### deeptutor/services/pdf/report_store.py

只读：当前user身份、run、完成发布及review已知目标。

L574–L588

```python

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
```

L626–L640

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
```

L786–L800

```python

def publish_report_run(
    run: ReportRun, *, files: Sequence[ReportFile | Mapping[str, Any]], verification_status: str
) -> ReportManifest:
    """校验并**显式发布**一次运行；只有成功返回的 manifest 才代表正式产物。

    步骤：服务端身份校验 → 形状校验 → 逐项按源字节校验（常规文件/非链接/大小/
    摘要）→ 在正式目录同级建临时目录、逐项复制并复核摘要 → 写入公开 metadata 投影
    → 原子 ``rename`` 提交。任何拒绝或异常都走 :func:`_finalize_rejected_publish`：
    状态落 ``failed``、活跃登记释放、不留半完成目录、不覆盖旧 completed、不产生 URL。

    本函数**不替代** P35 对全文/编译完成的质量检查：``files`` 必须来自服务端
    已验证清单（例如 P34 的 ``validate_chart_output`` 返回值），不接受模型自签。
    """
    run = _require_run(run)
```

L988–L1002

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
```

L868–L882

```python

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
```

L359–L373

```python

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
```

### deeptutor/services/pdf/chart_executor.py

只读：同run执行互斥，独立run并发；失败门不能绕过。

L273–L287

```python
@contextlib.contextmanager
def _exclusive_run_execution(run: report_store.ReportRun):
    key = str(run.staging_dir)
    with _EXECUTING_RUNS_LOCK:
        if key in _EXECUTING_RUNS:
            raise subject_error(ErrorCode.CHART_FAILED)
        _EXECUTING_RUNS.add(key)
    try:
        yield
    finally:
        with _EXECUTING_RUNS_LOCK:
            _EXECUTING_RUNS.discard(key)


# ---------------------------------------------------------------------------
```

L1299–L1313

```python

async def execute_chart_code(
    code: str,
    *,
    run: report_store.ReportRun,
    expected_png: str,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
    """在报告沙箱里运行模型图表代码，并返回结构化结果。

    * ``code`` 必须先通过 P31 输入契约（非空字符串）；本函数把它写成工作目录里的
      ``_chart.py``（服务端固定名字）。
    * 执行前清除 ``expected_png`` 的旧产物并写下 attempt 记录，因此执行结束后该路径
      上的文件只可能来自本次 attempt。
    * 无合格 backend → ``sandbox_unavailable``/``sandbox_policy_unsupported``（503），
```

L1352–L1366

```python

async def execute_ode_check(
    run: report_store.ReportRun,
    expression: object,
    *,
    points: object,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
    """用**同一个**受限执行器与 trusted worker 做 5 点 ODE 数值检查。

    表达式先过 P31 的 AST 白名单（拒绝即 ``invalid_input``，不会进入执行器）；
    检查在隔离环境内读取当前脚本的 ``f``，结果放在 :attr:`ChartExecutionResult.checks`。
    """
    report_store.require_report_run(run, require_running=True)
    validated = validate_ode_expression(expression)
```

L1380–L1394

```python

def chart_failure_error(result: ChartExecutionResult) -> SubjectOperationError | None:
    """把执行结果映射成 C02 固定错误；**完整成功**才返回 ``None``。

    * 基础设施错误 → 对应的 503/502 固定错误；
    * 非 0 退出码或超时 → ``chart_failed``（即使某个 ``ExecResult.ok`` 说成功）；
    * chart 模式：必须 ``status == "ok"`` 且带**严格结构**的产物（名字/正 size/64 位
      hash）；"exit 0 但没图"不是成功；
    * ODE 模式：必须给出可信父 worker 计算出的 ``checks.ok is True``。
    """
    if result.error:
        if result.error in {"sandbox_spawn_failed", "sandbox_unavailable"}:
            return subject_error(ErrorCode.SANDBOX_UNAVAILABLE)
        if result.error == "sandbox_policy_unsupported":
            return subject_error(ErrorCode.SANDBOX_POLICY_UNSUPPORTED)
```

### deeptutor/services/pdf/chart_validation.py

只读：生成图绑定当前成功worker；复制旧图需report.py独立受限验证，不伪造worker。

L168–L182

```python

def validate_chart_output(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """验证本次 attempt 的 ``expected_png``，返回 ``ReportFile`` 形状的字典。

    成功：``{"path": "chart_N.png", "size": int, "sha256": str, "role": "chart"}``。
    失败：抛 C02 固定错误（``chart_failed``；名字非法是 ``invalid_input``）。
    """
    report_store.require_report_run(run)
    name = chart_target_name(expected_png, policy=policy)
    max_bytes = min(policy.max_artifact_bytes, MAX_CHART_BYTES)
```

L231–L245

```python

async def check_ode_numeric(
    run: report_store.ReportRun,
    ode_rhs: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """在隔离环境里用固定 5 点检查 ``f`` 与声明表达式的数值一致性。

    返回 ``{"status": "passed", "max_abs_error": float, "points": int}``；缺 ``f``、
    数值不符、NaN/Inf、坏输出、超时都抛 ``chart_failed``。表达式本身先过 P31 的
    AST 白名单（非法表达式是 ``invalid_input``，不会进入执行器）。

    结论范围仅限"给定 5 点的数值检查通过"，不是解析解证明。
    """
```

### deeptutor/services/pdf/chart_worker.py

只读：可信父在隔离内计算参考，采样超额拒绝。

L204–L218

```python
# ---------------------------------------------------------------------------
def _run_bounded_child(
    argv: list[str],
    workdir: str,
    *,
    timeout_s: int,
    tail_chars: int = MAX_TAIL_CHARS,
) -> dict:
    """运行 *argv*，只保留 stdout/stderr 的尾部，绝不整段物化。"""
    try:
        process = subprocess.Popen(
            argv,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
```

L428–L442

```python

def _ode_mode(spec: dict, workdir: str) -> int:
    """**可信**父 worker：起不可信子进程取采样，自己算参考值/误差/有限性。"""
    script = _safe_basename(spec.get("script"), "script")
    expression = spec.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise WorkerError("expression 不能为空")
    points = _validate_points(spec.get("points"))
    wall_clock_s = _require_int(spec, "wall_clock_s", minimum=1, maximum=600)
    limits = _set_hard_limits(spec)
    inner = {"script": script, "points": points, **limits}
    outcome = _run_bounded_child(
        [
            sys.executable,
            "-I",
```

### deeptutor/services/pdf/review_guide.py

只读：已有S02生成门/字体/可信Typst及DOCX；调用方负责私有渲染与offload。

L62–L76

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
```

L167–L181

```python

def typst_compile(typ_path: Path, out_path: Path, typst_bin: Path | None = None) -> bool:
    """Compile a .typ file to PDF with the project CJK font path.

    Centralizes font-path wiring so every renderer (review guide, report)
    picks up the Windows CJK fonts (Microsoft YaHei) shipped in tools/fonts.
    """
    typst_bin = typst_bin or (Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst")
    if not typst_bin.exists():
        return False
    try:
        proc = subprocess.run(
            [
                str(typst_bin),
                "compile",
```

L196–L210

```python

def render_pdf(markdown: str, out_path: Path, typst_bin: Path | None = None) -> bool:
    """Compile Markdown to PDF via Typst. Returns success."""
    src = _TYST_DOC.format(body=_md_to_typst(markdown))
    tmp = out_path.with_suffix(".typ")
    tmp.write_text(src, encoding="utf-8")
    return typst_compile(tmp, out_path, typst_bin)


def render_docx(markdown: str, out_path: Path) -> bool:
    """Render Markdown subset to DOCX via python-docx."""
    from docx import Document

    doc = Document()
    in_list = False
```

L204–L218

```python

def render_docx(markdown: str, out_path: Path) -> bool:
    """Render Markdown subset to DOCX via python-docx."""
    from docx import Document

    doc = Document()
    in_list = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            in_list = False
            continue
        if stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=0)
        elif stripped.startswith("## "):
```

### deeptutor/subjects/generation.py

只读：所有完整响应/预算/截断仍用此门。

L30–L44

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
```

L78–L92

```python

async def complete_subject_text(
    *,
    prompt: str,
    system_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    max_tokens: int | None = None,
) -> str:
    """Run one subject-feature completion and return its trimmed text.

    The public signature and parameter semantics are unchanged; the result
    check is delegated to :func:`validate_subject_response`.

```

### deeptutor/subjects/errors.py

只读：HTTP/Tool统一固定安全错误，绝不拼raw原因。

L333–L347

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

```

L392–L406

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
```

L402–L416

```python

def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
    """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。

    调用者负责用它构造真正的 ToolResult；这里只固定失败语义与 error 数据，
    不返回任何 artifact URL。
    """
    return {"success": False, "metadata": {"error": to_error_dict(error)}}


__all__ = [
    "ERROR_SPECS",
    "ErrorCode",
    "ErrorSpec",
    "MAX_MESSAGE_LENGTH",
```

### deeptutor/api/subject_route.py

只读：router已包C02，并保留原生401/403/422。

L145–L159

```python

class SubjectRoute(APIRoute):
    """``APIRoute`` that turns subject/storage/LLM failures into C02 payloads."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def subject_error_boundary(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                # 原生参数校验：保持框架 422。
                raise
            except HTTPException as exc:
                # 认证 / 原生 401/403/422 优先保留（含 WWW-Authenticate 等 headers）。
```

L157–L171

```python
                raise
            except HTTPException as exc:
                # 认证 / 原生 401/403/422 优先保留（含 WWW-Authenticate 等 headers）。
                if exc.status_code in FRAMEWORK_PRIORITY_STATUSES:
                    raise
                cause = _business_cause(exc)
                if cause is None:
                    # 没有明确业务 cause 的历史 HTTPException：仍是框架行为，
                    # 不按 detail 文本或类名猜分类。
                    raise
                error = map_subject_exception(cause)
                _log_failure(request, error, cause, wrapped=exc)
                return JSONResponse(
                    status_code=error.http_status, content=to_http_payload(error)
                )
```

### deeptutor/services/session/source_inventory.py

只读：source_index是真正的source_id到已附全文。

L164–L178

```python

def render_manifest(inv: SourceInventory) -> tuple[str, dict[str, str]]:
    """Render the inventory into (manifest_text, source_index).

    ``manifest_text`` is the human/LLM-readable block injected at the tail
    of the chat system prompt. ``source_index`` maps each source id to its
    full extracted text and is handed to ``ReadSourceTool`` so the LLM can
    read on demand.
    """
    if inv.is_empty():
        return "", {}

    source_index: dict[str, str] = {sid: e.full_text for sid, e in _iter_sid_entries(inv)}
    rendered_rows: list[str] = []
    for entry in inv.entries:
```

### deeptutor/capabilities/explore_context/capability.py

只读：context.metadata source_index真实来源语义。

L67–L81

```python

def _has_readable_sources(context: UnifiedContext) -> bool:
    """Whether the turn has any readable (non-image) attached source.

    ``source_index`` is the per-turn ``{source_id: full_text}`` map the chat
    pipeline builds from the (session-cumulative) Attached Sources manifest. It
    is non-empty whenever the turn carries any textual source — whether
    attached this turn or carried over from an earlier turn on the branch — so
    the investigation runs query-driven on every turn that has sources to read,
    not just the turn they were first attached.
    """
    idx = context.metadata.get("source_index")
    return isinstance(idx, dict) and bool(idx)


```

### deeptutor/core/tool_protocol.py

只读：ToolResult构造字段，错误投影进metadata。

L121–L135

```python
@dataclass
class ToolResult:
    """Standardised return value from a tool execution.

    Attributes:
        content: Text returned to the LLM as the ``role=tool`` message body.
        sources: Citation rows surfaced through ``stream.sources``.
        metadata: Free-form payload — also used by the chat pipeline as a
            channel for structured UI hints (e.g. ``ask_user.options``
            for chip rendering).
        success: ``False`` marks an explicit failure path; the LLM is
            still allowed to read ``content`` (often an error message).
        terminate_turn: When ``True`` the agentic chat loop must stop
            iterating after dispatching this tool, treating the tool's
            output as the assistant's final turn artefact. Reserved for
```

### deeptutor/subjects/store.py

只读：已登记subject与strict current-user路径。

L113–L127

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
```

L188–L202

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


```

### deeptutor/subjects/json_store.py

只读：链接/路径检查在读写前，别随手resolve后信任。

L181–L195

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

```

L389–L403

```python

def atomic_write_object(path: Path, payload: dict) -> None:
    """Object counterpart of :func:`atomic_write_list`."""
    path = Path(path)
    if not isinstance(payload, dict):
        raise UpdateCallbackError("对象文档必须是对象")
    _commit(path, dict(payload))


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------
@dataclass
class _LockHandle:
    """Bookkeeping for one thread's hold on a path lock."""
```

### tests/phase1/test_p1_31.py

窄授权旧pipeline接缝；纯输入assert全部保持，旧坏成功需改。

L381–L395

```python
# ---------------------------------------------------------------------------
class _Recorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.executed: list[str] = []
        self.ode_checks: list[str] = []
        self.renders = 0

    def install(self, monkeypatch: pytest.MonkeyPatch, responses: list[str]) -> None:
        pending = list(responses)

        async def fake_llm(prompt: str, system: str) -> str:
            self.prompts.append(prompt)
            if not pending:
                raise AssertionError("模型替身被调用的次数超过预期")
```

L421–L435

```python

def _run_report(tmp_path: Path, **kwargs: object) -> dict:
    out_dir = tmp_path / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        report_mod.generate_report(
            "sub",
            title="标题",
            requirements="要求",
            out_dir=out_dir,
            **kwargs,  # type: ignore[arg-type]
        )
    )


```

L465–L479

```python

def test_bad_code_response_never_reaches_the_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "# 报告\n{CHART: 柱状图}\n"
    recorder = _Recorder()
    recorder.install(monkeypatch, [body, *['{"code": [1, 2]}'] * 3])

    result = _run_report(tmp_path)

    assert recorder.executed == []
    assert result["chart_count"] == 0
    assert "{CHART" not in result["markdown"]
    assert "图 1 生成失败" in result["markdown"]

```

L527–L541

```python

def test_truncated_generation_is_not_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """沿用生成服务的预算/截断边界：``_llm`` 抛出的截断错误必须原样传播。"""
    from deeptutor.subjects.errors import ErrorCode as _Code
    from deeptutor.subjects.errors import subject_error

    async def truncating_llm(prompt: str, system: str) -> str:
        raise subject_error(_Code.OUTPUT_TRUNCATED)

    monkeypatch.setattr(report_mod, "_llm", truncating_llm)
    out_dir = tmp_path / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

```

### tests/phase1/helpers.py

只读：隔离runtime/真实route client与合法subject fixtures。

L508–L522

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
```

L583–L597

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
```

L1147–L1161

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
```

### tests/phase1/test_p1_56.py

只读：既有真实review-pack错误边界回归。

L692–L706

```python

def test_r4_the_real_review_pack_route_does_not_leak_the_wrapped_llm_detail(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    """真实 review-pack endpoint：LLMEmptyResponseError 被包成 HTTPException from exc。"""
    from jsonschema import validate

    from deeptutor.services.llm.exceptions import LLMEmptyResponseError

    subject = p1_subjects["科目A"]

    async def failing(*args, **kwargs):
        raise LLMEmptyResponseError(f"{FAKE_MARKER} {HOST_PATH_MARKER}")

    monkeypatch.setattr(
```

### plans/phase1/DATA_CONTRACTS.md

C11及固定基础接口权威；不得自行改契约。

L133–L147

```text

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
{"report_id":"...","status":"completed","chart_count":1,"markdown_tokens":600,"url":"/api/outputs/subjects/复变函数/reports/<rid>/report.pdf","path":"<server-owned-path>","verification_status":"not_requested"}
```

正文完整，所有声明图表均成功且有效，PDF 确实编译/可打开后才 completed/发布 URL。允许无声明图的纯正文报告，但不能把声明图的失败变成 completed；缺图为 chart_failed。CHART 正则识别与替换使用同一个 match，支持零空格/多空格。脚本成功需退出码为 0（ExecResult.ok 本身不检查 exit_code），目标 PNG 是当前任务的新常规非 symlink 文件，Pillow验证有效、路径被限定、size 上限，不能仅检查 exists。所有正文/核查 Markdown 图片引用都只能是本任务经过验证的 chart_N.png 白名单；包括模型自行输出的图片引用，也不得接受外部URL、绝对/相对穿越或引号注入到Typst。临时脚本/错误日志不能随目录整包发布，正式目录只发布文档、验证图片及私有manifest。

source_file 是当前 turn source_index 中的附件 source_id，只能读取服务端已附着文本；无可解析 ID 返回 invalid_input。禁止读取模型给的宿主任意路径。API 使用 requirements 即可，不为其新增通用文件读取参数。

```

L215–L229

```text
| 26 | `async describe_image_for_index(image_path, *, source_file, page=None, location=None)` | fields为text/content_kind/source_file/page/location/asset_ref/skip_reason；描述或具名跳过，不伪造页码 |
| 32 | `create_report_run(subject_id, *, reviewed_from=None) -> ReportRun` | fields为report_id/subject_id/staging_dir/public_dir；生成服务端id |
| 32 | `publish_report_run(run, *, files, verification_status) -> ReportManifest` | 校验并发布；fields对应schema；不发布临时脚本 |
| 32 | `resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest` | 当前科已知报告，可发现legacy；不得任意文件读 |
| 33 | `async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult` | fields为exit_code/timed_out/error/stdout/stderr；合格policy才执行，无裸fallback |
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

## 附录B：机器可检验的字段示例

`schemas.json` 使用 JSON Schema 2020-12 的 `$defs` 定义错误、规范化批改/检测结果、上传、作用域、知识点评估、图像覆盖、报告、source manifest、导出manifest和completion。`examples.json` 记录每种形状的有效样例及必须拒绝的反例，均为虚构数据。

Schema验证字段和枚举，不替代行为验证：路径包含关系、授权、来源真实性、事务锁、失败字节不变、provider截断、网络/沙箱等仍按C01–C14执行测试。也不要求生产添加jsonschema依赖；可用既有Pydantic/代码验证实现相同义务。schema中的批改输出是trim/lower归一化后的结果，允许预验证进行C05规定的大小写归一化。
```

L218–L229

```text
| 32 | `resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest` | 当前科已知报告，可发现legacy；不得任意文件读 |
| 33 | `async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult` | fields为exit_code/timed_out/error/stdout/stderr；合格policy才执行，无裸fallback |
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

## 附录B：机器可检验的字段示例

`schemas.json` 使用 JSON Schema 2020-12 的 `$defs` 定义错误、规范化批改/检测结果、上传、作用域、知识点评估、图像覆盖、报告、source manifest、导出manifest和completion。`examples.json` 记录每种形状的有效样例及必须拒绝的反例，均为虚构数据。

Schema验证字段和枚举，不替代行为验证：路径包含关系、授权、来源真实性、事务锁、失败字节不变、provider截断、网络/沙箱等仍按C01–C14执行测试。也不要求生产添加jsonschema依赖；可用既有Pydantic/代码验证实现相同义务。schema中的批改输出是trim/lower归一化后的结果，允许预验证进行C05规定的大小写归一化。
```

### plans/phase1/schemas.json

ReportFile/Metadata/Response完整定义按名读取。

L836–L850

```json
    },
    "ReportFile": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "pattern": "^(?!\\.\\.?$)[^/\\\\\\x00-\\x1f]+(?![\\s\\S])"
        },
        "size": {
          "type": "integer",
          "minimum": 0
        },
        "sha256": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}(?![\\s\\S])"
```

L867–L881

```json
    },
    "ReportMetadata": {
      "type": "object",
      "properties": {
        "schema_version": {
          "const": 1
        },
        "report_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{32}(?![\\s\\S])"
        },
        "subject_id": {
          "type": "string",
          "pattern": "^[a-z0-9\\u4e00-\\u9fff][a-z0-9\\u4e00-\\u9fff-]{0,63}(?![\\s\\S])"
        },
```

L961–L975

```json
    },
    "ReportResponse": {
      "type": "object",
      "properties": {
        "report_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{32}(?![\\s\\S])"
        },
        "status": {
          "const": "completed"
        },
        "chart_count": {
          "type": "integer",
          "minimum": 0,
          "maximum": 8
```

### plans/phase1/cards/P1-35.md

P35包括已同步的P31测试适配窄范围。

L4–L18

```text

## 目标

每声明图都属于本任务且有效，正文/图/PDF完整后一次发布。

## 已有问题证据

{CHART:图}被regex解析却不能replace；图失败仍产成功PDF。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C11, C04；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。
```

L19–L33

```text

## 允许更改范围

- `deeptutor/services/pdf/report.py`
- `tests/phase1/test_p1_35.py`
- `tests/phase1/test_p1_31.py`（仅_Recorder/_run_report及7个generate_report接缝用例适配）

符号范围：generate_report/_run_chart_code/_chart_ode_matches/_render_report_pdf接入helper；review留36。2026-10-17协调者窄授权P31旧流水线接缝适配，因其fixture依赖未登记subject/host helper/假产物且将图失败当成功，必须跟随本卡契约修正；所有纯输入/AST/JSON断言保持，不为旧错误保留不安全兼容路径。详见START_S09。

历史单卡模式的证据目录为 `.phase1-evidence/P1-35/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 编排独立run、generation、executor、validation；按同一match替换不同空白占位。
2. 有限重试沿用<=3，每失败尝试不能用前次png；全部图或渲染失败不publish。
```

L35–L49

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] 0/1/多空格marker都替换
- [ ] 任一声明图失败整体失败无正式URL
- [ ] 两并发报告相互独立
- [ ] 空/截断正文不编译
- [ ] API/tool所用同一pipeline能找到md
- [ ] 真实Typst中文+图PDF可打开
- [ ] 模型自行输出的外部/越界/引号注入图片引用拒绝，未验证文件不得送入Typst

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```

### plans/phase1/cards/P1-36.md

P36 review与附件source_id，不新增API。

L4–L18

```text

## 目标

核查只读当前科已知报告，新版本不覆盖原件，预算/渲染错误一致。

## 已有问题证据

review接受任意report_path；_render_reviewed写回old_md；API旧报告不一定有正文。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C11, C02；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。
```

L19–L33

```text

## 允许更改范围

- `deeptutor/tools/report_tool.py`
- `deeptutor/services/pdf/report.py`
- `deeptutor/agents/chat/agentic_pipeline.py`
- `tests/phase1/test_p1_36.py`

符号范围：review输入解析/_render_reviewed及generate_report分支的服务端source_index注入；不新增通用文件读取或新review API。

历史单卡模式的证据目录为 `.phase1-evidence/P1-36/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 通过ReportStore解析report_id/latest和受限legacy path；schema保留兼容但文案一致。
```

L37–L51

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] latest同科报告成功新revision
- [ ] 跨科/../绝对外部/symlink/未知md拒绝且不读取
- [ ] budget/provider错误success=false
- [ ] 丢原图失败且原件不变
- [ ] 旧合法同科报告可核查

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_36.py
```

### plans/phase1/cards/P1-37.md

P37两入口/复习包统一失败行为。

L4–L18

```text

## 目标

两入口均无空白/截断成功，真实预算异常被处理，URL与实际文件一致。

## 已有问题证据

routes只catch LLMEmptyResponseError，预算异常属于其他子类；md持久化以前只tool完成。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C02, C11, C04；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。
```

L19–L33

```text

## 允许更改范围

- `deeptutor/api/routers/subjects.py`
- `deeptutor/tools/report_tool.py`
- `tests/phase1/test_p1_37.py`

符号范围：generate_review_pack/generate_subject_report与ReportTool create结果投影；不改其他tools。

历史单卡模式的证据目录为 `.phase1-evidence/P1-37/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 用C02 shared mapper处理所有subject generation错误，ToolResult失败code同HTTP。
2. result映射新task目录及旧兼容字段；不要继续out_dir/md另写一次。
```

L35–L49

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] ReasoningBudgetExhausted两入口都具名失败
- [ ] partial truncation无url
- [ ] completed URL实际存在同科目录
- [ ] API创建报告可被tool latest发现
- [ ] review/render失败不返回success
- [ ] 无学情复习提示PDF正常

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
```

### plans/phase1/cards/P1-38.md

P38真实并发请求/线程用户/cancel。

L4–L18

```text

## 目标

报告/复习编译耗时时，独立HTTP请求仍能响应；thread上下文不串用户。

## 已有问题证据

async route直接调用同步Typst/compiler和部分图执行函数。

## 必读输入

- 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
- DATA_CONTRACTS.md 的 C11, C13；此处不得自行改契约。
- 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
- PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。
```

L19–L33

```text

## 允许更改范围

- `deeptutor/api/routers/subjects.py`
- `deeptutor/services/pdf/report.py`
- `tests/phase1/test_p1_38.py`

符号范围：render_pdf/render_docx/Typst同步调用与review render offload；不得新增后台任务产品。

历史单卡模式的证据目录为 `.phase1-evidence/P1-38/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。

## 执行步骤

1. 同步可信渲染用asyncio.to_thread，LLM和sandbox async链仍await。
2. 写入前明确server PathService/subject scope，to_thread context传播验证；不把全函数盲目to_thread。
```

L34–L48

```text

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] compile阻塞event时第二个只读请求先完成
- [ ] thread内仍是本user输出目录
- [ ] render exception映射C02
- [ ] 取消/异常不发布正式artifact

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_38.py
```
```

## 执行与交付

详细目标、证据、白名单、完成门和精确命令见START_S09.txt。先建立独立stage基线，所有业务收集前隔离HOME；四单元连续完成，阶段末一个report/log/archive，严格串行日志。保持当前94条合并基准内90只读、真实六树和全部旧证据不变，不进入S10。

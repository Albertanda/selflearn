# S08 已探索的文件清单 + 关键片段

2026-10-16，基于S07-final签收后的当前源码。与START_S08.txt及最终review receipt配套；本包只冻结接缝，不代表S08已经实现。优先按下列符号直接定位，免去全仓orientation；只在具体依赖缺口时补读。行号为生成时一基行号，完整SHA256用于开工一致性检查，worker修改已授权report.py后无需保持其旧hash。

## 阶段边界与决策

- 四单元P31→P32→P33→P34一次阶段交付，白名单10路径详见START_S08。除report.py外5个生产模块及4个测试文件当前均不存在；新建即可，不扫描寻找旧实现。
- S08只建输入、私有run/publish辅助、专用executor、验证器；generate_report/review/图片引用与工具/API统一接入属S09/P35–38。P31允许在现有调用处最小接线以消除默认ODE、执行前验证及JSON错误；不提前大改编排。
- 固定async execute_chart_code；ReportRun/Manifest使用DATA_CONTRACTS附录A字段；内部类/helper可自定但不要改公开契约。C02稳定错误不回显脚本/表达式/路径/环境。
- 当前bwrap二进制路径存在不等于OS隔离已验收。P33离线验证policy和受控进程边界；真实OS门是S15/P50。无合格backend应503，fake不能被生产路径当合格能力，不安装环境。
- BwrapBackend只是底座参考：广挂/etc、host env继承、ok不看非零、health与communicate弱点均需report-only边界补足。全局sandbox/backend/runner只读。trusted worker单独只读，代码/结果不共用其他run。
- 当前继承5个tracked deletion保留；84前置产物+10本阶段路径=94 include，无重叠。六真实根仅不透明snapshot、比较文件/目录/权限；不读取配置内容或memory trace。旧证据只读。

## 文件清单（完整SHA256）

| 文件 | SHA256 | 用途 |
|---|---|---|
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | C11/附录A为权威契约；S08建基础，S09接入口。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | ReportFile/Metadata/Response字段；完整定义按名称读取，不自行扩公网字段。 |
| `deeptutor/services/pdf/report.py` | `6881b59c2fb0496177d79e7b3b4a1f7fe6b868635931819936e4c0e9f1b3f743` | P31唯一现有可改文件：输入/prompt/JSON。其余编排/helper是P35只读接缝。 |
| `deeptutor/subjects/model_output.py` | `7ebe1f77d497ed3dcf11914540f14e4d83d026160e3165d7311dc1a2c95e77f8` | 复用完整对象解析，别另写贪婪regex或repair半JSON。 |
| `deeptutor/subjects/generation.py` | `831c50decd82ee2977e2e3046346044d7ab7f08659cd25c79070d015f63969bc` | 既有输出预算/截断验证，不回退裸LLM call。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 固定C02安全错误：sandbox_unavailable/policy_unsupported503、chart_failed502等。 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | 严格current-user根及已登记subject；subject_kb_base_dir会mkdir，不是报告路径构造器。 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 复用拒绝路径链接/严格JSON/原子写/可重入目录短锁，别做real-data迁移。 |
| `deeptutor/services/path_service.py` | `01505ea0a473ba16b09bd27a9afd1a6795f4ddff1eef4a7b34f89ee7c748bd3d` | public根来自当前用户PathService；不硬编码管理员。 |
| `deeptutor/multi_user/paths.py` | `5c0a463c93b8b955458143257c395a86b5814e7186688c771b57edf586b6c153` | 当前用户context；读only。 |
| `deeptutor/services/sandbox/spec.py` | `3fd1906248bd0ed4a38deeb770cf0da35414bd38ee3271a64c39ff01e303bacf` | ExecRequest argv/limits及结果契约；ok并不检查exit_code。 |
| `deeptutor/services/sandbox/backends.py` | `78544bd063dae285ab52d13fcfb353194f67c6ae695bcbebea6231d0e906a326` | 不能直接继承其全部行为：广挂/etc、继承环境、无内存输出上限/整组清理。仅report新模块窄实现。 |
| `deeptutor/services/sandbox/config.py` | `377a8df583cc80fa21561e5f94d9580db109f534b25341e95a1e006089471dff` | 现有选择可含shared runner/APPLICATION，不能当report合格策略。 |
| `deeptutor/services/sandbox/service.py` | `40cf59ae1a7ee94fdf4ce72ee569cf10e47d08741cd2df98d13f716d44aa78a7` | 普通service/health cache不代替逐任务report隔离证明。 |
| `deeptutor/services/pdf/review_guide.py` | `34df402d9820a82acefae768436aead50cc80501abdff415f6d84595730e9a59` | 字体/Typst可信模板能力在P35复用，本阶段不改。 |
| `deeptutor/tools/report_tool.py` | `a9ab8549c41cf2b4a49c8c7769169825a2afc86ff17490cb0f3f693d34d3410a` | P36未来输入source_index/review入口；S08只读，不顺手接通。 |
| `deeptutor/api/routers/subjects.py` | `9349cd452698f8a52df2aab3d2ed5ec06039c521592f9c9f69409c1cdf7c59db` | P37/38未来入口；当前共用公开out，S08不改。 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 隔离runtime/subject fake fixtures；业务导入收集前仍先隔离HOME。 |
| `tests/services/sandbox/test_sandbox.py` | `f2c21ada20a502d2117062101b770fe1e39b40ede3312f5e0640229effb41f2f` | 共享backend历史断言只读；相关目录最终回归覆盖。 |
| `tests/services/sandbox/test_argv_exec.py` | `3a9cfac0b397a854a42920064f889f81a1cc3fa633230c6b8d32ac26d9cb9549` | argv一致性回归只读。 |
| `plans/phase1/cards/P1-31.md` | `3b3e183a3fa699cf294f188db3afa7e2c9672f89b8af5bca35faf09f8e4ec472` | P31目标/白名单/验收反例。 |
| `plans/phase1/cards/P1-32.md` | `40f376371bcb08231598175d234ad5973c8019799dfed34d4e959574e26f06ef` | P32服务端run/publish/review基础。 |
| `plans/phase1/cards/P1-33.md` | `7e2eb6d359178cf73fb0a7be8eee1136d3ac7c3fb894913ddfcbca6e73f1b2ac` | P33策略/worker/非零退出/无fallback。 |
| `plans/phase1/cards/P1-34.md` | `32dd4f23bdfb3cdbd9ad78e15a5cc33b9176d88a2047808e9c729d7d41a665d3` | P34PNG/数值检查；不宿主import模型。 |

## 关键片段

以下是实际源码片段。已有不安全实现只用于定位替换边界，不是可复用安全范例。

### plans/phase1/DATA_CONTRACTS.md

C11/附录A为权威契约；S08建基础，S09接入口。

L134–L154

```text
## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
{"report_id":"...","status":"completed","chart_count":1,"markdown_tokens":600,"url":"/api/outputs/subjects/复变函数/reports/<rid>/report.pdf","path":"<server-owned-path>","verification_status":"not_requested"}
```

正文完整，所有声明图表均成功且有效，PDF 确实编译/可打开后才 completed/发布 URL。允许无声明图的纯正文报告，但不能把声明图的失败变成 completed；缺图为 chart_failed。CHART 正则识别与替换使用同一个 match，支持零空格/多空格。脚本成功需退出码为 0（ExecResult.ok 本身不检查 exit_code），目标 PNG 是当前任务的新常规非 symlink 文件，Pillow验证有效、路径被限定、size 上限，不能仅检查 exists。所有正文/核查 Markdown 图片引用都只能是本任务经过验证的 chart_N.png 白名单；包括模型自行输出的图片引用，也不得接受外部URL、绝对/相对穿越或引号注入到Typst。临时脚本/错误日志不能随目录整包发布，正式目录只发布文档、验证图片及私有manifest。

source_file 是当前 turn source_index 中的附件 source_id，只能读取服务端已附着文本；无可解析 ID 返回 invalid_input。禁止读取模型给的宿主任意路径。API 使用 requirements 即可，不为其新增通用文件读取参数。

ode_rhs 为空时不强行注入 `x**2-y`，普通图提示只按 spec 画图。非空表达式用 AST 白名单验证：x/y，有限数字，+ - * / ** 和一元 +/-，调用 sin/cos/exp/log/sqrt/abs（仅这些名字）；无属性、下标、import、lambda、列表推导、双下划线和未知变量。指数等计算量仍受资源限额。检查通过的表达式在隔离环境执行；verification_status=passed 仅说明给定 5 点的 f(x,y) 数值吻合，不代表解析解/整篇数学正确。失败不发布完整报告。

图表代码和 ODE 检查都只能由专用 chart executor 执行。必须同时保证：OS 隔离、只挂当前任务 workdir 可写和字体/解释器必要文件只读、网络禁用、env 白名单且无密钥、超时终止进程组、CPU/内存/产物大小受限。现有 BwrapBackend 可作为底座，trusted worker 在执行模型脚本之前施加资源限额；普通 APPLICATION backend、未证明逐任务隔离的共享 runner 不合格。不存在合格 backend 返回 503；不得裸 subprocess fallback、自动下载/安装 sandbox 或修改系统策略。

资源默认：脚本墙钟 60s、CPU 30s、内存上限 1536MiB、stdout/stderr 10000 字符、单图 10MiB/20百万像素、每报告最多 8 张图；ODE 检查墙钟 30s。CPU/内存用进程级hard RLIMIT且子进程继承，不能宣称已实现整棵进程树累计cgroup配额；墙钟超时必须终止整个执行进程组。资源数值可在新内部 ReportExecutionPolicy 定义，未授权不改变部署 settings schema。trusted worker 代码单独只读挂载，不能放在模型可覆盖的工作目录中；配置阈值由服务端提供，模型不能传 limits/mounts/env。OOM/超时/非法输出为 chart_failed。Typst只执行可信转换模板，不执行模型 Python。

review 接受 report_id 或 latest；旧 report_path 仅作为兼容输入，规范化后必须是该科已有报告目录中的已知 .md/.pdf，严格拒绝跨科、绝对外部路径和 symlink 越界。任意未知 md 不得读取。review 新建 report_id，并复制原图到自己的目录，不覆盖原正文/PDF，metadata 记录 reviewed_from；若正文要求保留的原图丢失/指向外部路径就失败。
```

L216–L224

```text
| 32 | `create_report_run(subject_id, *, reviewed_from=None) -> ReportRun` | fields为report_id/subject_id/staging_dir/public_dir；生成服务端id |
| 32 | `publish_report_run(run, *, files, verification_status) -> ReportManifest` | 校验并发布；fields对应schema；不发布临时脚本 |
| 32 | `resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest` | 当前科已知报告，可发现legacy；不得任意文件读 |
| 33 | `async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult` | fields为exit_code/timed_out/error/stdout/stderr；合格policy才执行，无裸fallback |
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

```

### plans/phase1/schemas.json

ReportFile/Metadata/Response字段；完整定义按名称读取，不自行扩公网字段。

L837–L866

```json
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
        },
        "role": {
          "enum": [
            "markdown",
            "pdf",
            "chart"
          ]
        }
      },
      "required": [
        "path",
        "size",
        "sha256",
        "role"
      ],
      "additionalProperties": false
```

L868–L921

```json
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
        "status": {
          "enum": [
            "running",
            "completed",
            "failed",
            "abandoned"
          ]
        },
        "created_at": {
          "type": "integer",
          "minimum": 0
        },
        "reviewed_from": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ]
        },
        "verification_status": {
          "enum": [
            "not_requested",
            "passed",
            "failed"
          ]
        },
        "files": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/ReportFile"
          }
        },
        "owner_pid": {
          "anyOf": [
            {
              "type": "integer",
              "minimum": 1
```

L962–L986

```json
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
        },
        "markdown_tokens": {
          "type": "integer",
          "minimum": 0
        },
        "url": {
          "type": "string",
          "pattern": "^/api/outputs/subjects/"
        },
        "path": {
          "type": "string"
```

### deeptutor/services/pdf/report.py

P31唯一现有可改文件：输入/prompt/JSON。其余编排/helper是P35只读接缝。

L30–L47

```python
logger = logging.getLogger(__name__)

REPORT_PROMPT = """你是一名大学助教，根据题目要求撰写一份课程报告（中文）。

## 报告题目
{title}

## 题目要求
{requirements}
{subject_context}
## 写作要求
1. 结构：# 标题 开头，然后是 ## 引言、## 各分析章节（按题目要求组织）、## 结论。
2. 需要用图表达的地方插入占位符：{{CHART: 图表描述}}——描述里写清楚要画什么（函数/数据、坐标轴含义、x 范围）。每张图占位符独占一行。
3. 数学公式用 Unicode 文本（如 y′ = x² − y、e^(−x)），不要用 LaTeX 命令。
4. 只使用 Markdown 子集：#、##、-、**加粗**；不要表格、代码块、链接。
5. 正文 800-1200 字（不含图），内容准确、结构完整，直接基于题目要求。
6. 数学严谨性：凡是给出解析解、平衡点、稳定性等结论，必须代入原方程验证后再写；精确解写出来前先自查（例如 y' = x² − y 的通解是 y = x² − 2x + 2 + C·e^(−x)，代回可验证）；不要臆造公式或结论。
"""
```

L58–L74

```python
CHART_CODE_PROMPT = """为下面这张图生成 matplotlib Python 代码。

## 微分方程（必须严格遵守，禁止修改）
本题微分方程为 y′ = f(x, y)，其中：
f(x, y) = {ode_rhs}
代码中必须定义：def f(x, y): return {ode_rhs}，不得使用其他任何方程！

## 图表需求
{description}

## 代码要求
1. 完整可运行的脚本：import numpy 和 matplotlib.pyplot as plt。
2. 中文字体设置：plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']；plt.rcParams['axes.unicode_minus'] = False。
3. 图内文字可用中文或英文（数学变量用 x, y, t）。
4. 保存：plt.savefig('{out_path}', dpi=150, bbox_inches='tight')；不要 plt.show()。
5. 只输出 JSON：{{"code": "..."}}（code 为完整脚本字符串，转义换行）。
"""
```

L77–L93

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
        base_url=cfg.base_url,
    )

```

L96–L118

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
    script = workdir / "_ode_check.py"
    script.write_text(check, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(workdir),
            capture_output=True,
            timeout=30,
        )
```

L124–L136

```python
def _extract_json(raw: str) -> dict:
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
```

L148–L171

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
            timeout=60,
        )
        if proc.returncode != 0:
            (workdir / "_chart_err.txt").write_text(
                (proc.stderr or b"").decode(errors="replace")[:500], encoding="utf-8"
            )
        return proc.returncode == 0
    except Exception as exc:
        (workdir / "_chart_err.txt").write_text(str(exc)[:500], encoding="utf-8")
        return False
```

L174–L195

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
            tokens[token] = f'#image("{m.group(1)}", width: 85%)'
            lines.append(token)
            lines.append("")
            continue
        lines.append(line)
    body = _md_to_typst("\n".join(lines))
    for token, raw in tokens.items():
        body = body.replace(token, raw)
```

L202–L219

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
    value leaves the prompt byte-for-byte as before.

    Returns ``{title, markdown, markdown_tokens, chart_count, pdf_path}``.

```

L235–L258

```python
            "报告正文生成失败：模型返回空内容。"
            f"通常是推理模型的思考 token 耗尽了 max_tokens（当前 {LLM_MAX_TOKENS}），请重试。",
            details={"subject_id": subject_id, "max_tokens": LLM_MAX_TOKENS},
        )

    chart_specs = re.findall(r"\{CHART:\s*([^}]+)\}", markdown)
    chart_paths: list[Path] = []
    for i, spec in enumerate(chart_specs):
        png = out_dir / f"chart_{i + 1}.png"
        chart_ok = False
        for attempt in range(3):  # up to 2 retries on failed ODE self-check
            raw = await _llm(
                CHART_CODE_PROMPT.format(
                    description=spec.strip(), out_path=png.name, ode_rhs=ode_rhs or "x**2 - y"
                ),
                "你生成 matplotlib 代码，只输出 JSON。",
            )
            data = _extract_json(raw)
            code = data.get("code", "")
            if code and _run_chart_code(code, out_dir) and png.exists():
                if not ode_rhs or _chart_ode_matches(out_dir, ode_rhs):
                    chart_ok = True
                    break
                logger.warning("chart %d ODE mismatch (attempt %d)", i + 1, attempt + 1)
```

L270–L285

```python
            else f"**（图 {i + 1} 生成失败：{spec.strip()[:60]}）**"
        )
        markdown = markdown.replace("{CHART: " + spec + "}", replacement, 1)

    typst_bin = Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst"
    ts = int(time.time())
    pdf_path = out_dir / f"report-{ts}.pdf"
    ok = _render_report_pdf(markdown, chart_paths, pdf_path, typst_bin)
    return {
        "title": title,
        "markdown": markdown,
        "markdown_tokens": estimate_tokens(markdown),
        "chart_count": len(chart_paths),
        "pdf_ok": ok,
        "pdf_path": str(pdf_path),
    }
```

L288–L299

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

### deeptutor/subjects/model_output.py

复用完整对象解析，别另写贪婪regex或repair半JSON。

L205–L236

```python
def parse_model_object(raw: str) -> dict[str, Any]:
    """返回 ``raw`` 中**唯一**的 JSON 对象。

    Raises:
        ModelOutputError: 顶层不是对象、JSON 截断/非法、存在两个及以上候选、
            围栏或 think 未闭合、以及围栏/对象之后还有非空内容。
    """
    if not isinstance(raw, str):
        raise ModelOutputError(REASON_NOT_A_STRING)
    text = _strip_think_blocks(raw)
    if not text:
        raise ModelOutputError(REASON_EMPTY)
    text = _strip_code_fence(text)
    if not text.strip():
        raise ModelOutputError(REASON_EMPTY)
    return _decode_single_object(text)


__all__ = [
    "ModelOutputError",
    "REASON_DECODER_LIMIT",
    "REASON_EMPTY",
    "REASON_INVALID_JSON",
    "REASON_NON_FINITE_NUMBER",
    "REASON_NOT_A_STRING",
    "REASON_NOT_AN_OBJECT",
    "REASON_TRAILING_AFTER_FENCE",
    "REASON_TRAILING_CONTENT",
    "REASON_UNCLOSED_FENCE",
    "REASON_UNCLOSED_THINK",
    "parse_model_object",
]
```

### deeptutor/subjects/generation.py

既有输出预算/截断验证，不回退裸LLM call。

L31–L49

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

```

L79–L102

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

    Raises:
        LLMReasoningBudgetExhausted: the provider stopped at an output cap
            (``finish_reason`` is a truncation reason) without producing text —
            the reasoning-burned-the-budget case, reported as such.
        SubjectOutputTruncated: the provider stopped at an output cap but had
            already produced partial text.
        LLMEmptyResponseError: the provider returned no text for any other
            reason.
    """
    from deeptutor.services.llm.factory import complete_response
```

### deeptutor/subjects/errors.py

固定C02安全错误：sandbox_unavailable/policy_unsupported503、chart_failed502等。

L133–L147

```python
    ErrorCode.REASONING_BUDGET_EXHAUSTED: _spec(
        ErrorCode.REASONING_BUDGET_EXHAUSTED, 502, True, "模型把输出预算耗尽在推理上，请重试。"
    ),
    ErrorCode.SANDBOX_UNAVAILABLE: _spec(
        ErrorCode.SANDBOX_UNAVAILABLE, 503, False, "隔离执行环境不可用。"
    ),
    ErrorCode.SANDBOX_POLICY_UNSUPPORTED: _spec(
        ErrorCode.SANDBOX_POLICY_UNSUPPORTED, 503, False, "当前部署不支持所需的隔离执行策略。"
    ),
    ErrorCode.CHART_FAILED: _spec(
        ErrorCode.CHART_FAILED, 502, True, "图表生成失败。"
    ),
    ErrorCode.RENDER_FAILED: _spec(
        ErrorCode.RENDER_FAILED, 502, True, "文档渲染失败。"
    ),
```

L302–L313

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

```

L381–L412

```python
def to_error_dict(error: SubjectOperationError) -> dict[str, Any]:
    """WS metadata / ToolResult metadata 共用的 error 数据。

    不改变任何既有事件协议，只提供同构的 ``{code, message, retryable}``。
    """
    return {
        "code": error.code.value,
        "message": error.message,
        "retryable": error.retryable,
    }


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


__all__ = [
```

### deeptutor/subjects/store.py

严格current-user根及已登记subject；subject_kb_base_dir会mkdir，不是报告路径构造器。

L114–L130

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

L189–L211

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
    files, so a symlinked ``wrong_book.json`` is refused before it is opened
    rather than after the other subject's bytes have been read.
    """
    directory = subject_dir(subject_id)
    return json_store.confined(directory, directory / json_store.safe_segment(name))
```

### deeptutor/subjects/json_store.py

复用拒绝路径链接/严格JSON/原子写/可重入目录短锁，别做real-data迁移。

L182–L207

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

L339–L357

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
```

L390–L400

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
```

L607–L639

```python
class JsonTransaction:
    """A locked read-modify-write scope over one directory.

    Reentrant: entering the same directory's transaction again from the same
    thread reuses the same lock, and the inner exit does not release the outer
    hold. All paths used here must stay inside :attr:`lock_dir`.
    """

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = Path(lock_dir)
        self._lock: _PathLock | None = None
        self._resolved = ""

    def __enter__(self) -> "JsonTransaction":
        lock = _lock_for(self.lock_dir)
        lock.acquire()
        self._lock = lock
        # Remember the directory the lock was validated for, so later checks
        # cannot silently adopt a target the path was swapped to.
        self._resolved = lock.key
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        lock, self._lock = self._lock, None
        if lock is None:
            return False
        try:
            lock.release()
        except BaseException:
            if exc_type is None:
                raise
            # An error in the body is the meaningful one; a cleanup failure must
            # not replace it.
```

L710–L714

```python
def json_transaction(lock_dir: Path) -> Iterator[JsonTransaction]:
    """Hold *lock_dir*'s process + OS lock for the duration of the block."""
    with JsonTransaction(Path(lock_dir)) as transaction:
        yield transaction

```

### deeptutor/services/path_service.py

public根来自当前用户PathService；不硬编码管理员。

L129–L139

```python
    def get_chat_history_db(self) -> Path:
        return self._user_data_dir / "chat_history.db"

    def get_public_outputs_root(self) -> Path:
        return self._user_data_dir

    def resolve_public_output_path(self, path: str | Path) -> Path | None:
        """Return a safe, public output file below this service's user root.

        Resolving and authorizing the path in one operation gives callers the
        exact canonical path they may read.  In particular, callers should not
```

L232–L245

```python
    def get_task_workspace(self, feature: str, task_id: str) -> Path:
        task_root = self._resolve_feature_root(feature)
        return task_root / task_id

    def get_session_workspace(self, feature: str, session_id: str) -> Path:
        session_root = self._resolve_feature_root(feature)
        return session_root / session_id

    def _resolve_feature_root(self, feature: str) -> Path:
        if feature in {
            "chat",
            "deep_solve",
            "deep_question",
            "deep_research",
```

### deeptutor/multi_user/paths.py

当前用户context；读only。

L153–L162

```python
def get_current_path_service() -> PathService:
    from .context import get_current_user_or_none

    user = get_current_user_or_none()
    if user is None:
        return PathService.get_instance()
    if user.scope.kind == "user":
        ensure_scope_workspace(user.scope)
    return get_path_service_for_scope(user.scope)

```

L255–L262

```python
def user_context(user: CurrentUser) -> Iterator[None]:
    from .context import reset_current_user, set_current_user

    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)
```

### deeptutor/services/sandbox/spec.py

ExecRequest argv/limits及结果契约；ok并不检查exit_code。

L25–L56

```python
    SYSTEM = "system"  # OS-enforced (container / bubblewrap namespaces)
    APPLICATION = "application"  # in-process guards only (path + deny rules)
    OFF = "off"  # no sandbox available

    def rank(self) -> int:
        return {"off": 0, "application": 1, "system": 2}[self.value]


@dataclass(frozen=True)
class ResourceLimits:
    """Per-execution resource ceilings. Enforcement is best-effort per backend."""

    timeout_s: int = 30
    memory_mb: int = 512
    max_output_chars: int = 10_000
    cpu_seconds: int = 30


@dataclass(frozen=True)
class Mount:
    """A directory exposed inside the sandbox."""

    host_path: str
    sandbox_path: str
    read_only: bool = True


@dataclass(frozen=True)
class ExecRequest:
    """A command to run inside the sandbox.

    Two spellings of the same request, and both are always present:
```

L58–L90

```python
    ``command``  a shell string — what a model-authored ``exec`` call is.
    ``argv``     an argument vector, empty unless the caller built one.

    When ``argv`` is set a backend runs it **without a shell**, which is how a
    caller that assembles arguments from model output (a CLI app invocation)
    avoids shell metacharacters mattering at all. ``command`` still holds the
    equivalent shell string, produced by :meth:`of_argv` via ``shlex.join``, so a
    runner sidecar built before ``argv`` existed keeps working — an older image is
    the normal state of affairs during a rolling deploy, and a request it does not
    fully understand must degrade to a correct execution rather than a wrong one.
    """

    command: str
    workdir: str = ""
    mounts: tuple[Mount, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    #: Argument vector; when non-empty it is authoritative and no shell is used.
    argv: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # The two fields must describe the same execution. Constructing them
        # separately is the mistake this forbids: a caller that set `argv` and
        # left `command` at some earlier value would run one thing on a new
        # runner and a different thing on an old one.
        if self.argv and self.command != shlex.join(self.argv):
            raise ValueError(
                "ExecRequest.argv and .command disagree; build argv requests with "
                "ExecRequest.of_argv()"
            )

    @classmethod
    def of_argv(cls, argv: Sequence[str], **kwargs: object) -> "ExecRequest":
```

L93–L112

```python
        if not items:
            raise ValueError("ExecRequest.of_argv needs at least one argument")
        return cls(command=shlex.join(items), argv=items, **kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ExecResult:
    """Outcome of a sandboxed execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    error: str = ""  # set when the sandbox itself failed (not the command)

    @property
    def ok(self) -> bool:
        return not self.error and not self.timed_out

    def render(self, max_chars: int) -> str:
```

### deeptutor/services/sandbox/backends.py

不能直接继承其全部行为：广挂/etc、继承环境、无内存输出上限/整组清理。仅report新模块窄实现。

L113–L142

```python
class BwrapBackend(SandboxBackend):
    """Bubblewrap mount-namespace isolation (Linux only)."""

    level = IsolationLevel.SYSTEM

    _RO_SYSTEM_DIRS = ("/usr", "/usr/local", "/bin", "/lib", "/lib64", "/etc", "/sbin")
    _DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    def __init__(
        self,
        bwrap_path: str = "bwrap",
        *,
        venv_path: str | Path | None = None,
        inherit_virtualenv: bool = True,
    ) -> None:
        self._bwrap = bwrap_path
        detected_virtualenv = (
            venv_path is None and inherit_virtualenv and sys.prefix != sys.base_prefix
        )
        if venv_path is not None:
            candidate = Path(venv_path).resolve()
        elif detected_virtualenv:
            candidate = Path(sys.prefix).resolve()
        else:
            candidate = None
        self._venv_path = candidate if candidate is not None and candidate.is_dir() else None
        self._python_runtime_mounts = (
            self._detect_python_runtime_mounts() if self._venv_path and detected_virtualenv else ()
        )

```

L170–L221

```python
    def _build_argv(self, request: ExecRequest) -> list[str]:
        argv = [
            self._bwrap,
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",  # nosec B108 — path inside the bwrap mount namespace, not the host
        ]
        for system_dir in self._RO_SYSTEM_DIRS:
            if Path(system_dir).exists():
                argv += ["--ro-bind", system_dir, system_dir]
        for mount in request.mounts:
            flag = "--ro-bind" if mount.read_only else "--bind"
            argv += [flag, mount.host_path, mount.sandbox_path]
        # uv-managed venvs can link their interpreter to a versioned runtime
        # outside /usr. Mount only those concrete runtime roots, never their
        # shared manager/home parent. Both the resolved and alias destinations
        # may be needed because venv shebangs preserve the alias path.
        for source, destination in self._python_runtime_mounts:
            argv += ["--ro-bind", str(source), str(destination)]
        # Mount only the environment itself, never its workspace or home-dir
        # parent. Keeping the original absolute path preserves venv shebangs
        # and direct sys.executable argv while the later mount order ensures a
        # writable request mount cannot make the environment writable.
        if self._venv_path is not None and self._venv_path.is_dir():
            venv = str(self._venv_path)
            argv += ["--ro-bind", venv, venv]
        if request.workdir:
            argv += ["--chdir", request.workdir]
        env = dict(request.env)
        if self._venv_path is not None and self._venv_path.is_dir():
            venv = str(self._venv_path)
            venv_bin = str(self._venv_path / "bin")
            base_path = env.get("PATH") or os.environ.get("PATH") or self._DEFAULT_PATH
            path_entries = [part for part in base_path.split(os.pathsep) if part != venv_bin]
            env["PATH"] = os.pathsep.join([venv_bin, *path_entries])
            # The mounted environment is authoritative. A model-supplied env
            # must not redirect Python tooling to an unmounted host path.
            env["VIRTUAL_ENV"] = venv
        for key, value in env.items():
            argv += ["--setenv", key, value]
        if request.argv:
            # No shell in between: bwrap execs the vector directly.
            argv += ["--", *request.argv]
        else:
            argv += ["/bin/sh", "-c", request.command]
        return argv
```

L223–L245

```python
    async def exec(self, request: ExecRequest) -> ExecResult:
        argv = self._build_argv(request)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ExecResult(error="bwrap not found on host")
        return await _communicate(process, request.limits.timeout_s)

    async def health(self) -> tuple[bool, str]:
        if shutil.which(self._bwrap) is None:
            return False, "bwrap not installed"
        # bwrap needs unprivileged user namespaces; a default-seccomp Docker
        # container blocks them, so confirm a trivial sandbox actually runs.
        probe = ExecRequest(command="true")
        result = await self.exec(probe)
        if result.error:
            return False, result.error
        return True, "bwrap functional"

```

L280–L296

```python
async def _communicate(process: asyncio.subprocess.Process, timeout_s: int) -> ExecResult:
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        process.kill()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=5.0)
        return ExecResult(timed_out=True, exit_code=124)
    return ExecResult(
        stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
        stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
        exit_code=process.returncode if process.returncode is not None else 0,
    )


__all__ = [
    "BwrapBackend",
```

### deeptutor/services/sandbox/config.py

现有选择可含shared runner/APPLICATION，不能当report合格策略。

L66–L92

```python
def build_backend(settings: SandboxSettings) -> SandboxBackend | None:
    """Pick the backend implied by *settings*; ``None`` when none is usable.

    Note: returns the candidate by configuration shape. Liveness (e.g. can
    bwrap actually create namespaces here) is confirmed lazily via the
    backend's ``health()`` — see :mod:`deeptutor.services.sandbox.service`.
    """
    import sys

    if settings.runner_url:
        return RunnerSidecarBackend(settings.runner_url)
    if sys.platform.startswith("linux"):
        import shutil

        if shutil.which("bwrap"):
            return BwrapBackend()
    if settings.allow_subprocess:
        return RestrictedSubprocessBackend()
    return None


__all__ = [
    "ALLOW_SUBPROCESS_ENV",
    "RUNNER_URL_ENV",
    "SandboxSettings",
    "build_backend",
]
```

### deeptutor/services/sandbox/service.py

普通service/health cache不代替逐任务report隔离证明。

L45–L63

```python
    async def _ensure_healthy(self) -> bool:
        if self._backend is None:
            return False
        if self._healthy is not None:
            return self._healthy
        async with self._health_lock:
            if self._healthy is None:
                try:
                    self._healthy, self._health_detail = await self._backend.health()
                except Exception as exc:
                    self._healthy = False
                    self._health_detail = f"health check failed: {exc}"
                if not self._healthy:
                    logger.warning(
                        "sandbox backend %s unhealthy: %s",
                        type(self._backend).__name__,
                        self._health_detail,
                    )
        return bool(self._healthy)
```

L74–L97

```python
    async def run(self, request: ExecRequest, *, user_id: str) -> ExecResult:
        """Run *request* for *user_id*, enforcing quota; never raises for
        command failure — only the sandbox/quota envelope is reported via
        :attr:`ExecResult.error`."""
        if not await self._ensure_healthy() or self._backend is None:
            return ExecResult(error=self._health_detail or t("sandbox.no_backend"))
        # Backstop for the per-user exec grant: pipelines hide the exec tool
        # when the grant denies it, but any path that reaches the sandbox
        # directly still answers to the same policy.
        try:
            from deeptutor.multi_user.tool_access import exec_override

            if exec_override() is False:
                return ExecResult(error=t("sandbox.disabled_for_account"))
        except Exception:
            logger.warning("per-user exec policy check failed; continuing", exc_info=True)
        try:
            lease = await self._quota.acquire(user_id)
        except QuotaExceeded as exc:
            return ExecResult(error=str(exc))
        async with lease:
            return await self._backend.exec(request)


```

### deeptutor/services/pdf/review_guide.py

字体/Typst可信模板能力在P35复用，本阶段不改。

L165–L194

```python
_FONT_DIR = Path(__file__).resolve().parents[3] / "tools" / "fonts"


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
                "--font-path",
                str(_FONT_DIR),
                str(typ_path),
                str(out_path),
            ],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning("typst compile failed: %s", proc.stderr.decode(errors="replace")[:300])
        return proc.returncode == 0 and out_path.exists()
    except Exception:
        return False
```

L197–L203

```python
def render_pdf(markdown: str, out_path: Path, typst_bin: Path | None = None) -> bool:
    """Compile Markdown to PDF via Typst. Returns success."""
    src = _TYST_DOC.format(body=_md_to_typst(markdown))
    tmp = out_path.with_suffix(".typ")
    tmp.write_text(src, encoding="utf-8")
    return typst_compile(tmp, out_path, typst_bin)

```

### deeptutor/tools/report_tool.py

P36未来输入source_index/review入口；S08只读，不顺手接通。

L51–L81

```python
                ToolParameter(name="report_path", type="string", description="要核查的报告路径（action=review）", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        subject_id = str(kwargs.get("_subject_id", "") or "").strip()
        action = str(kwargs.get("action") or "create").lower()
        if not subject_id:
            return ToolResult(content="此功能需要先选择一个科目（聊天工具栏的科目选择器）。", success=False)

        # Deferred imports: builtin -> report_tool -> pdf.report -> subjects
        # -> path_service -> runtime.registry -> builtin would otherwise cycle.
        # ``services.llm`` is deferred for the same reason — importing it at
        # module scope pulls the whole config chain in before path_service is
        # ready.
        from deeptutor.services.llm.exceptions import LLMEmptyResponseError
        from deeptutor.services.path_service import get_path_service
        from deeptutor.services.pdf import report as report_mod

        outputs_root = get_path_service().get_public_outputs_root()
        out_dir = outputs_root / "subjects" / subject_id / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)

        if action == "review":
            report_path = str(kwargs.get("report_path") or "").strip()
            if report_path in ("latest", "recent", "最近", "最新", "last"):
                report_path = ""
            if not report_path:
                # No path given: review the most recent report for this subject.
                candidates = sorted(out_dir.glob("report-*.md"))
                if not candidates:
```

L116–L141

```python
        requirements = str(kwargs.get("requirements") or "").strip()
        ode_rhs = str(kwargs.get("ode_rhs") or "").strip()
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
            )
        except LLMEmptyResponseError as exc:
            # A blank body would otherwise render as a "successful" empty PDF.
            return ToolResult(content=f"报告生成失败：{exc.message}", success=False)
        if not result["pdf_ok"]:
            return ToolResult(content="报告渲染失败，请重试。", success=False)
        pdf_path = Path(result["pdf_path"])
        # Persist the markdown next to the PDF so `review` can re-read it.
        md_name = pdf_path.with_suffix(".md").name
```

### deeptutor/api/routers/subjects.py

P37/38未来入口；当前共用公开out，S08不改。

L824–L862

```python
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

    outputs_root = get_path_service().get_public_outputs_root()
    out_dir = outputs_root / "subjects" / subject_id / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = await report_mod.generate_report(
            subject_id,
            title=title,
            requirements=requirements,
            out_dir=out_dir,
            ode_rhs=ode_rhs,
        )
    except LLMEmptyResponseError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    if not result["pdf_ok"]:
        raise HTTPException(status_code=500, detail="Report PDF render failed")
    pdf_name = Path(result["pdf_path"]).name
    return {
        "title": result["title"],
        "markdown_tokens": result["markdown_tokens"],
        "chart_count": result["chart_count"],
        "url": f"/api/outputs/subjects/{subject_id}/reports/{pdf_name}",
        "path": result["pdf_path"],
    }

```

### tests/phase1/helpers.py

隔离runtime/subject fake fixtures；业务导入收集前仍先隔离HOME。

L509–L536

```python
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


# ---------------------------------------------------------------------------
# 临时科目 / 知识库
```

L584–L605

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
    subject_id = slugify(name)
    admin_root = Path(admin_root)
    marker = marker or f"marker-{subject_id}"
    root = learning_root(admin_root) / subject_id
```

L828–L845

```python
def install_provider_stubs(
    monkeypatch,
    *,
    llm: "FakeLLMClient | None" = None,
    embedding: "FakeEmbeddingClient | None" = None,
    stt: "FakeSTT | None" = None,
) -> dict[str, Any]:
    """把替身装到真实被调用的模块上；返回已安装的替身。"""
    ensure_bootstrap_home()
    installed: dict[str, Any] = {}

    def replace_callable(module_name: str, name: str, replacement: Any) -> None:
        original = getattr(_module(module_name), name)
        # Packages re-export these functions; loaded consumers may already have
        # imported the same function. Patch those identities as well.
        for loaded_name, module in tuple(sys.modules.items()):
            if (loaded_name.startswith("deeptutor.")
                    and getattr(module, "__dict__", {}).get(name) is original):
```

### tests/services/sandbox/test_sandbox.py

共享backend历史断言只读；相关目录最终回归覆盖。

L1–L26

```python
"""Sandbox: backend selection, restricted subprocess exec, quota, level gating."""

from __future__ import annotations

import asyncio
import sys

import pytest

from deeptutor.services.sandbox.backends import BwrapBackend, RestrictedSubprocessBackend
from deeptutor.services.sandbox.config import SandboxSettings, build_backend
from deeptutor.services.sandbox.quota import QuotaExceeded, UserExecQuota
from deeptutor.services.sandbox.service import SandboxService
from deeptutor.services.sandbox.spec import (
    ExecRequest,
    ExecResult,
    IsolationLevel,
    Mount,
    ResourceLimits,
)


def test_backend_selection_runner_url() -> None:
    from deeptutor.services.sandbox.backends import RunnerSidecarBackend

    settings = SandboxSettings(runner_url="http://sandbox-runner:8900")
```

### tests/services/sandbox/test_argv_exec.py

argv一致性回归只读。

L1–L30

```python
"""Running a command as an argument vector rather than as a shell string.

A CLI app's arguments come from the model, so the program is fixed and the
arguments are not — the one exec path where a shell buys nothing and costs
everything. Two properties are pinned here:

* ``argv`` and ``command`` always describe the same execution, enforced at
  construction so no caller can set one and forget the other;
* every backend honours ``argv``, and the shell string that travels alongside it
  (for a runner image that predates the field) is quoted such that a hostile
  argument is still just an argument.
"""

from __future__ import annotations

import asyncio
import shlex

import pytest

from deeptutor.services.sandbox.backends import (
    BwrapBackend,
    RestrictedSubprocessBackend,
    RunnerSidecarBackend,
)
from deeptutor.services.sandbox.runner import server as runner_server
from deeptutor.services.sandbox.spec import ExecRequest

#: Arguments that would each do something different if a shell saw them.
HOSTILE_ARGS = [
```

### plans/phase1/cards/P1-31.md

P31目标/白名单/验收反例。

L5–L11

```text
## 目标

非ODE报告不被默认方程污染，表达式和模型code对象输入可诊断。

## 已有问题证据

ode_rhs为空仍硬塞x**2-y；ODE checker把输入直接插入Python。
```

L21–L27

```text

- `deeptutor/services/pdf/report.py`
- `deeptutor/services/pdf/report_inputs.py`
- `tests/phase1/test_p1_31.py`

符号范围：CHART_CODE_PROMPT/_extract_json与纯report input/AST验证；执行器留33/34。

```

L39–L47

```text

- [ ] 统计图prompt无x**2-y默认
- [ ] 合法x**2-y/sin(x)-y接受
- [ ] import/attribute/lambda/subscript/unknown name拒绝
- [ ] code非string/半JSON失败
- [ ] 超过8占位图明确失败

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```

### plans/phase1/cards/P1-32.md

P32服务端run/publish/review基础。

L5–L11

```text
## 目标

报告不共享脚本/图片，不靠秒时间命名；仅完成后暴露正式产物。

## 已有问题证据

所有报告同一reports目录内chart_1/_chart.py/_ode_check.py可碰撞。
```

L21–L27

```text

- `deeptutor/services/pdf/report_store.py`
- `tests/phase1/test_p1_32.py`

符号范围：新report_id/staging/manifest/publish读取辅助；本卡不执行模型或图表。

历史单卡模式的证据目录为 `.phase1-evidence/P1-32/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。
```

L39–L48

```text
- [ ] 两任务名字不同且互不覆盖
- [ ] 失败无正式url/path
- [ ] legacy可发现但不改写
- [ ] symlink/越界publish拒绝
- [ ] 完成metadata与文件hash匹配

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_32.py
```

### plans/phase1/cards/P1-33.md

P33策略/worker/非零退出/无fallback。

L5–L11

```text
## 目标

模型代码只能访问当前任务，无网络/密钥，超时和资源受限；不合格backend拒绝。

## 已有问题证据

原_run_chart_code是宿主subprocess；shared sidecar的SYSTEM不证明逐任务文件隔离。
```

L21–L28

```text

- `deeptutor/services/pdf/chart_executor.py`
- `deeptutor/services/pdf/chart_worker.py`
- `tests/phase1/test_p1_33.py`

符号范围：新report-only executor/trusted worker；复用已有BwrapBackend，不重构一般exec/runner。

历史单卡模式的证据目录为 `.phase1-evidence/P1-33/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。
```

L39–L49

```text

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] mount仅current task可写、字体只读
- [ ] fake secret env不进request
- [ ] application/shared runner/off拒绝不调用subprocess
- [ ] exit_code非0即失败即便ok=True
- [ ] timeout整组清理和policy固定

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```

### plans/phase1/cards/P1-34.md

P34PNG/数值检查；不宿主import模型。

L5–L11

```text
## 目标

退出成功不等于有正确新图；旧图/软链接/无效图都不得通过。

## 已有问题证据

现有只检查png.exists，旧chart_1可被pass脚本当成功。
```

L21–L27

```text

- `deeptutor/services/pdf/chart_validation.py`
- `tests/phase1/test_p1_34.py`

符号范围：pure PNG/路径/hash验证及通过executor运行ODE数值检查；不编排全文report。

历史单卡模式的证据目录为 `.phase1-evidence/P1-34/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。
```

L39–L50

```text
- [ ] 合法新PNG通过
- [ ] 旧run图/软链接/空文件/超10MiB失败
- [ ] 超20百万像素PNG拒绝，Pillow解码警告不得被当作合法成功
- [ ] code成功无图失败
- [ ] ODE mismatch/nonfinite失败
- [ ] 合法ODE只标数值检查passed

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q tests/phase1/test_p1_34.py
```
```

## 后续实现必须覆盖的接缝

1. **P31**：在调用provider/executor前做纯输入校验；无ODE普通图正例。完整JSON code类型校验、0/1/8/9占位均有真实断言。保留S02预算/错误接口。
2. **P32**：服务端UUID、运行状态、短锁发布及严格白名单。多图都可role=chart，但不得重复path，主正文/主PDF各一。调用方得到的内部路径不能直接扩成公开payload。对active登记/PID复用/普通失败/崩溃边界明确描述，不宣称多文件跨进程崩溃原子性。
3. **P33**：写出实际mount/env/argv向量；从执行前hard limits到执行中有界读取再到超时/取消整组reap。不能只mock一个.ok。OS隔离与process-level配额证明范围分开记录。
4. **P34**：预分配本次attempt目标、先清除旧产物；Pillow verify+实际解码+byte/pixel上限。ODE必须走P33可信worker，并以五点finite/误差检查的真实结构化结果作判定；仅是数值一致性检查。

精确测试命令、坏对照要求、StageReport及closing manifest规则见START_S08.txt。所有新测试必须执行；19项既有条件skip逐项沿用真实原因，不能给本阶段必需断言新加skip。

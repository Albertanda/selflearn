# selflearn 项目现状核查（2026-10-10）

本报告对照 `HANDOVER.md`、实际 Git 历史、工作区源码、运行配置和本地检查。核查基准为 `main` 的 `9723f95` 加上已有未提交改动。原交接文档最后更新于 2026-09-28，其中的在线实测结果是历史记录，不能直接视为今天的运行结果。

**结论：项目已实现以科目为中心的 M1–M8 功能，但还没有形成可靠的端到端学习闭环。最关键的断点是主聊天没有接通科目知识库、当前配置无法索引文档图片，以及模型失败会污染或掩盖学习记录。现有大量测试主要验证保留的上游框架，不能证明分科新增功能全部正确。**

本轮没有修改业务代码、运行配置或真实科目数据，没有提交已有改动。简单的 Git/测试覆盖清点由 GPT‑6 Luna 子代理完成；关键路径审查与离线复现由主代理完成。

> **制定修复计划时的补充核实**：不能仅因 pyproject 的注释就断言 MCP 正在为 PageIndex 提供运行服务；当前工作树没有该client注册链路，PageIndex REST search提供目录概览，而聊天提示仍要求调用不存在的MCP工具。沙箱 SYSTEM 也不能自动证明逐任务的数据隔离。预算异常实际继承LLMProviderError，现有仅catch LLMEmptyResponseError的PDF入口覆盖不足；ReportTool review还允许任意路径。上述补充纳入 [第一阶段修复任务包](plans/phase1/README.md)，未在本轮实施业务修复。

## 1. 裁剪与修改的准确规模

基线 `15bf5ad` 是上游 v1.5.13 之后的 vision-model 提交。本地总计 94 个提交，其中 `15bf5ad..HEAD` 的 17 个属于本 fork，HEAD 仍是 `9723f95`。

以下均为两端快照的文本 diff，不是逐提交累加；不同区间存在重叠，不能把各行数字直接相加。

| 比较范围 | 新增路径 | 删除路径 | 修改路径 | 增加行 | 删除行 |
|---|---:|---:|---:|---:|---:|
| 基线 → M0 裁剪提交 `2b6be38` | 1 | 345 | 17 | 102 | 85,161 |
| M0 → 当前 HEAD | 23 | 28 | 21 | 4,776 | 7,080 |
| 基线 → 当前 HEAD | 23 | 372 | 34 | 4,671 | 92,034 |
| 基线 → 本次核查前的工作区（已跟踪文件） | 23 | 377 | 60 | 5,734 | 93,100 |
| HEAD → 工作区（已跟踪文件） | 0 | 5 | 43 | 1,146 | 1,149 |

核查开始时另有 3 个未跟踪文件：`HANDOVER.md` 657 行、`subjects/generation.py` 79 行、`utils/document_images.py` 603 行。因此原文的“50 处改动、2 个新增”只在排除交接文档后成立；Git 实际显示 **51 条路径**。原文的 `+1146/-1149` 也没有计算新增文件。计入两个新增业务文件后，工作区相对基线增加 6,416 行、删除 93,100 行；计入原交接文档再加 657 行。本报告是本轮新增加的第 4 个未跟踪文件，不计入以上历史代码统计。

基线有 2,061 个已跟踪文件；M0 后为 1,717 个，HEAD 为 1,712 个。M0 文件净减少 344 个，约为原仓库的 16.7%；不能据此计算功能或业务代码的裁剪百分比。M0 删除的 85,161 行全部是文本，不包含二进制行。后续 `69b64b1` 只修改忽略规则和说明，工具/字体本来就没有进入这段 Git 历史。

实际裁掉了电子书生成、伙伴/IM 渠道、子代理编排、旧 MCP 配置服务与界面、外部 CLI 应用集成、Obsidian 能力，以及相关 API、前端和测试。它仍然保留很大一块上游：聊天循环、深度解题/出题/研究、可视化、数学动画、Guided Learning、RAG、记忆、技能、笔记、co-writer、语音和多用户框架。

**裁剪并不等于依赖完全清理。** `pyproject.toml` 仍保留 partners/matrix/tutorbot extras 及相应 requirements；Obsidian 创建界面还存在。另一方面，MCP 依赖仍服务于保留的 deferred tools/PageIndex，不能把所有 MCP 协议支持都当死代码删除。

## 2. fork 新增了什么

核心新增的科目层、科目 API、PDF 生成、报告工具及两张科目页面约 3,087 行（包含未跟踪的 generation.py），此外还有 ASR、视觉策略、聊天上下文、运行契约、配置和上游修复移植等改动。

| 功能 | 实际实现与边界 |
|---|---|
| 科目管理 | 科目创建、描述/学期更新、删除；模型配置全局共享，学习数据按科目目录存储。 |
| 科目知识库 | 原始材料保存，按类型使用 `assignment-kb`、`textbook-kb` 等名称；目录隔离而非全局 `subject_kb_*` 前缀。有初始化、重建、状态与独立查询 API。 |
| 错题本 | 题目、参考答案、知识点、作答记录、归档；掌握度和四档分类；AI 批改 API。科目详情 UI 主要是记录答对/答错及归档，没有完整的 AI 作答批改表单。 |
| 考点 | 粘贴转写或上传音频 → 检测候选 → 保存考点。**explicit 会自动确认**，其他候选等待人工确认；并非全部经过人工确认。负向信号依靠提示词，服务端没有独立的证据真实性验证。 |
| 课堂 ASR | 上传音频调用配置的 OpenAI-compatible STT；保存原音频和文本，详情页将文本填入检测框。该分支直接返回，不建 lecture KB；科目列表页仍统一显示“正在建索引”，存在文案错位。 |
| 知识点索引 | 人工添加，或从错题/考点已经标注的 `kp` 聚合关联；**没有从全部讲义自动抽取完整知识体系**。 |
| 学习画像与上下文 | 注入知识点摘要、确认考点、错题摘要和学习偏好；主聊天可以选科目。但这些摘要不包含讲义全文，也不自动触发科目 KB 检索。 |
| 历史压缩 | 上游主聊天 ContextBuilder 有持久化摘要。fork 的学生事实抽取/写入 profile 位于旧 `/chat` 路径，主 `/ws` 路径没有调用这套事实写入逻辑；不要把两条聊天路径的行为混为一谈。 |
| 复习包 | 以确认考点、错题、知识点为输入生成 Markdown，再渲染 PDF/DOCX；没有检索讲义来校验生成内容。空考点/错题时生成提示性指南。 |
| 图表报告 | 题目/要求 → 正文 → matplotlib 脚本 → 图片 → PDF；API 和聊天工具均有入口。指定 ode_rhs 后只检查代码的 `f(x,y)` 在 5 个点是否吻合，不能证明图中解析解、曲线或整篇报告数学正确。科目 API 没有把具体学情传给 report，聊天工具目前只传科目及错题/考点数量。 |
| 导出 | ZIP 包含科目工作数据树，**不包含生成的 PDF/图表、科目注册元数据和完整聊天历史**；也没有对应的恢复/导入流程，因此“整科备份”应缩小表述。 |
| 文档内嵌图片 | 聊天 DOCX/PPTX/PDF 抽图后作为图片附件送入已有多模态链路；知识库另走 parser/ImageNode 路径，二者不等价。 |

保留的 7 个 capability 在 `runtime/bootstrap/builtin_capabilities.py` 注册。实际仍有 home、subjects、co-writer、playground、knowledge、notebook、memory、space 和多个 settings/admin 页面。这个项目是保留通用学习底座再增建科目层的 fork。

## 3. 当前环境、服务、数据与检查结果

- Python 3.12.14；主要已安装依赖与原交接文档列出的版本一致；前端声明 Next 16.2.3。
- Typst 二进制与中文字体实际存在，模型目录文件未被 Git 跟踪，当前权限为 `0600`。本报告不记录密钥。
- 配置端口仍为后端 8001、前端 3782，但核查时 `ss -ltnp` 显示两者均没有监听，未启动应用或重建生产前端。
- 六个科目注册记录仍存在。每科各有 1 个 assignment KB，配置状态均为 ready、各有 1 个 raw 文件；**这是磁盘元数据检查，没有进行在线检索验证**。
- 其中复变函数当前各有 1 个错题、1 个考点、1 个知识点，产物目录有 17 个 PDF；另外五科的这些记录为空。原文“六科完好”只能理解为数据仍在，不能理解为六科都已有丰富学习记录或已全面验证。

实际数据分布：

```text
data/user/workspace/subjects/index.json             科目注册表
data/user/workspace/subjects/<id>/                   学习数据与原始资料
data/user/workspace/subjects/<id>/knowledge_bases/   每科知识库
data/user/subjects/<id>/                            PDF/报告/ZIP 等公开产物
data/knowledge_bases/                               全局知识库
data/user/settings/                                全局运行配置
```

原文第 7.3 节混淆了学习数据和产物目录。未设置 `DEEPTUTOR_HOME` 时以启动 cwd 为数据 home 的陷阱仍然存在，应固定 home 或从 `/home/albert/selflearn/selflearn` 启动。

| 本轮检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q`，完整 testpaths | **2917 passed、1 failed、22 skipped**，共 2940 项，约 31 秒 |
| 前端 node 测试 | **403 passed、0 failed** |
| `web/node_modules/.bin/tsc --noEmit -p .` | 退出码 0，无错误 |
| Ruff，只查 deeptutor/deeptutor_cli | 12 个告警：11 个 I001、1 个 E741 |
| `git diff --check` | 通过 |
| 临时数据离线探针 | 18 项，详见下节；模型/ASR 调用使用模拟响应，PDF 编译使用真实 Typst |

后端失败项是 `tests/services/test_codebuddy_credentials.py:57`：夹具固定 `expiresAt=1791055241000`，即北京时间 **2026-10-04 03:20:41**，如今却仍断言未过期。单独重跑也失败。这是上游测试的时间依赖，不能据此认定真实 CodeBuddy 凭证解析坏了。

原文的 Ruff 数量与“均为上游遗留”不准确：实际告警包含本 fork 新增的 subjects/PDF 代码；F841 在当前规则中被忽略。该检查范围与原文可能不同，不能直接用数字作全仓库对比。

## 4. 已确认的问题与修复优先级

优先级为本次审计建议，不表示已经修复。P1 是影响学习正确性、资料一致性或文件写入边界；P2 是流程/输出缺陷；P3 是测试与文档噪音。

### P1：应先修的关键断点

1. **选择科目没有接通该科知识库检索。** home 只增加 config.subject_id；UnifiedTurnRuntime 注入摘要，却不把科目 KB 加入 knowledge_bases。`agentic_pipeline.py:993` 的 rag 分支也只补 mode，未传 subject 的 kb_base_dir；rag 默认走 `multi_user/knowledge_access.py` 的全局库。离线调用实际 kwargs 只有 query/kb_name/mode。因此科目 query API 有实现，不等于主聊天能够检索上传到该科的材料；全局同名 KB 还可能造成错误来源。

   修改位置：`web/app/(workspace)/home/[[...sessionId]]/page.tsx:1535`、`services/session/turn_runtime.py:1796`、`agents/chat/agentic_pipeline.py:993`、`tools/rag_tool.py:36`、`multi_user/knowledge_access.py:81`。需要统一 scope 与访问检查，覆盖 rag/kb_files/read_source 的来源解析，而不是只在 prompt 写科目名称。

2. **批改失败被当作学生答错并落盘。** `_ai_grade` 捕获所有异常后返回 wrong；`check_answer` 接着写入错误作答，降低掌握度。模拟断网后，正确答案“2”也产生 correct=false、status=missed 的记录。非 JSON 或非法 verdict 同样默认 wrong。应区分服务失败、格式失败和明确判错，失败时不更新学习记录。

   证据：`api/routers/subjects.py:410`、`:443` 及 `:389` 附近的入库流程。

3. **音频上传绕过安全上传器。** 该分支直接用未经清理的 filename 拼路径，并整块读取内容。用临时目录中的绝对路径作为音频名，可在 materials 之外写出音频及 transcript；本轮只写无害的临时文件。相对穿越同理。还缺少普通上传器的体积与扩展名检查。应统一使用安全命名、目录约束与限额校验。

   证据：`api/routers/subjects.py:158`–`:175`；普通上传器位于 `api/routers/knowledge.py:347`。

4. **同名材料重新上传时索引保留旧内容。** materials 文件被覆盖，但复制到 KB raw 时带 `not dst.exists()`，所以重建仍读取旧文件。离线复现 materials=new-source、raw=old-index-source。应明确采用替换或版本化策略，并让索引与权威原件一致。

   证据：`api/routers/subjects.py:193`。

5. **当前科目 KB 不能检索图像内容。** loader 要同时满足多模态 embedding 和主 LLM 的能力检测；实际 `Qwen/Qwen3-Embedding-8B` 返回 False，主 LLM 在这条检测路径也返回 False，图片被直接跳过，未调用描述模型。聊天附件抽图能工作，并不绕过 KB 的这个门槛。应先实现“独立 vision → 图片描述/OCR → 现有文本 embedding”的路径，不必为此更换整套向量模型。

   证据：`services/rag/pipelines/llamaindex/document_loader.py:152`。离线探针使用实际配置，在模型调用前即得到 0 个 ImageNode。parser 是否抽出图片也是前置条件，新增索引路径必须显式报告覆盖情况。

6. **报告图表运行没有文件/网络隔离。** `_run_chart_code` 只是同 Python 环境的 subprocess，加 cwd 和 timeout；临时探针可成功写到报告目录之外。它没有使用项目已有 sandbox，不能把“子进程执行”视为受限沙箱。应复用隔离执行并限制产物路径、环境和资源。

   证据：`services/pdf/report.py:147`。本轮没有读取任何真实配置或密钥来验证这个问题。

7. **报告可能把旧图算作新图。** 同一科目共用 reports 目录，图片固定为 chart_1.png 等。只要新脚本退出成功且旧图片还存在，即被计入成功；模拟 `pass` 脚本后旧图片仍被接受。并发生成还会共用脚本和检查文件。应每次生成使用独立任务目录，并验证新图确实由当前任务产生。

   证据：`services/pdf/report.py:243`、`:254`。

### P2：明确的接口与输出缺陷

8. **考点检测错误被外层 API 丢弃。** `exam_detection.detect_points` 返回 error，但路由只取 points/version/raw，外层表现为成功检出 0 条；前端因此显示“0 条候选”。离线已复现。JSON 解析失败也会静默变空列表。应保留错误或返回明确失败状态，不能混同于真的没有考点。

   证据：`subjects/exam_detection.py:81`、`api/routers/subjects.py:512`、`:530`。

9. **只修改描述也会清空学期。** PATCH 将缺省字段用 `or ""` 替换再传入 store；只传 description 时，原 term 被清空。反向修改 term 同样会清空 description。应只更新实际提供的字段。

   证据：`api/routers/subjects.py:98`，已用临时科目复现。

10. **非空截断正文仍被视为成功。** generation.py 先判断有文本就返回，之后才判断 finish_reason；所以 length + 半篇正文不会触发预算错误。空正文预算守卫有效，但没有覆盖所有截断情况。应区分完整成功、可恢复截断与空响应，并为 PDF/JSON 生成设定不同策略。

   证据：`subjects/generation.py:55`，模拟 length + `# 半篇报告` 可正常返回。

11. **图表占位符允许解析的形式未必能被替换。** 正则接受 `{CHART:图}`，后续 replace 只匹配 `{CHART: 图}`。离线复现占位符残留、chart_count=0，但 PDF 结果可标记成功。应使用同一正则的 span/sub 替换，并向调用者报告图表生成失败。

   证据：`services/pdf/report.py:240`、`:272`。

12. **“整科备份”不覆盖全部相关数据。** export 的 src_dir 与 outputs_root 分离；临时探针 ZIP 有 wrong_book.json，但没有已生成 PDF，也没有全局科目注册表中的 name/term/description。没有恢复 API。应先定义备份清单/schema，再补导入恢复及兼容验证。

   证据：`api/routers/subjects.py:740`。这属于承诺与实现范围不一致，不代表当前 ZIP 压缩算法失败。

13. **裁剪后的 Obsidian 死入口仍在界面。** CreateKbModal 仍提供连接调用，后端明确返回 501。应去掉选择项并清理“可连接/导航写入”的说明；保留后端明确拒绝可以服务旧调用者。

   证据：`web/components/knowledge/CreateKbModal.tsx:305`、`KnowledgeHome.tsx:191`、`api/routers/knowledge.py:1657`。

### 已见技术债，不能冒充已复现故障

- subjects/wrong_book/exam_points/profile 等 JSON 存储多为直接 write_text、读改写、无事务和锁；并发可能丢更新，写入中断可能留下损坏文件，load 又常把错误当空列表。建议统一原子写入与并发策略；规模增大时再考虑 SQLite。这是代码结构风险，本轮没有制造真实数据损坏。
- KB record 的 documents 初始写成 0，没有随重建同步，六科界面都会显示 0，虽然 raw 实际各有文件。应从索引统计或文件清单派生。
- 选科目下拉没有“取消科目”项；home 的 subjectId 是本地 useState，没有对应 session 恢复逻辑。需要浏览器回归切换/刷新/能力切换；deep_question 的 config 赋值还会覆盖此前加入的 subject_id。
- 默认没有排除未验证知识点：`knowledge_points.aggregate` 在没有作答证据时给 mastery=1.0，应改为未知状态。索引建立主要靠手动 build，新增记录关联未形成统一自动更新。
- PDF/图表执行和 ZIP 打包在 async 路由中调用同步函数，可能阻塞同进程请求；长任务宜使用后台任务、进度、取消与独立任务 ID。
- 索引停滞守卫可报错，但 Python 线程仍继续存在；同库重试会被拒直到线程结束或进程重启。10 分钟“报错”不等于强制停止或可立即恢复。
- 运行时依赖无完整 Python 锁定文件、工具链和字体需另备、继承 CI 被移除，重新部署的可重复性仍需补强。

## 5. 本轮确实验证通过的修复

1. `[False, True, True, True]` 得到 mastery=0.8、status=mastered，边界舍入修复有效。
2. NotebookManager 拒绝三类越界 id，路径守卫有效。
3. 空正文 + finish_reason=length 抛出 LLMReasoningBudgetExhausted。
4. 真实 DOCX 内嵌图片抽出 1 张图片附件，并在文本中保留 `[图片 1: ...]` 标记；**没有调用真实视觉模型验证识图答案**。
5. 缩短测试超时的索引停滞探针能报错、阻止活跃 worker 重入、worker 结束后释放；没有真的断网等待 600 秒。
6. 真实 Typst 编译中文复习 PDF 成功，1 页，提取文本中中文及 `0<a<1` 正常。

本轮没用真实供应商生成完整报告、批改、ASR 或执行在线 RAG，也没有做浏览器端到端回归。既有“33 项 E2E 全通过”只能保留为上一位 agent 的历史自述，当前仓库未找到对应可重复执行的完整验收套件。

测试覆盖搜索范围为 `tests/`、`deeptutor/learning/tests/`、`web/tests/`。没有找到 subjects 包/路由、PDF 报告、生成预算、document_images 抽取和 LlamaIndex 新停滞守卫的直接测试。learning 下的 knowledge_points 是另一套 Guided Learning 数据，不等于 subjects 数据层；现有 multimodal/loader 测试只覆盖部分下游行为。后续应把本报告关键缺陷变成自动化回归案例。

## 6. 后续修改的建议顺序

1. **整理并保存已存在的工作区改动，再建立可信基线。** 原文分组可参考，但文件的修复批次有交叉，不宜机械按文件拆提交。本轮没有替用户提交历史改动。先处理固定时间夹具，并为分科核心补少量有价值的失败路径测试。
2. **修 P1 的学习闭环与数据边界。** 优先接通科目聊天 RAG；阻止批改失败入库；修安全音频上传与同名文件替换；独立报告目录和隔离执行。让成功/失败语义可靠以后再加新功能。
3. **把材料真正变成可检索学习证据。** 用现有独立 vision + 文本 embedding 生成图像描述/OCR，保留图片来源、页码、位置和覆盖状态；建立小型真实教材检索评估集。图像与公式支持要有单独验收，不只检查索引 ready。
4. **完善现有工作台。** 补 AI 作答批改入口、知识点 build/关联、科目选择取消与会话恢复、检测失败提示、任务进度/取消，明确音频转写和索引的不同流程。
5. **完善数据保障和导出恢复。** 原子写/错误诊断，版本化备份清单、科目元信息、聊天关联与产物；加入恢复验证。若确实需要多用户，另做作用域与文件授权审计。
6. **在可靠检索上增加学习价值。** 优先围绕已有错题集做相似题、复测与间隔复习；question_bank 应先确认现有 Space/questions 数据和 Guided Learning 的重复面。远程 rerank 可作为可选阶段，先以检索评估证明收益再实现；多 key 轮换等获得实际多 key 需求后再做。

## 7. 上游信息的更新与移植边界

本轮查看官方发布页，截至 2026-10-10 最新公开发布为 **v1.6.14（2026-10-08）**，原文“最新 v1.6.11”已过时。来源：[DeepTutor 官方 v1.6.14 发布说明](https://github.com/HKUDS/DeepTutor/releases/tag/v1.6.14)。

v1.6.13/14 的图片描述缓存、来源图像/页图检索、索引检查点与恢复、发布索引前验证等方向与本项目实际缺口相关。来源：[v1.6.13](https://github.com/HKUDS/DeepTutor/releases/tag/v1.6.13)、[v1.6.14](https://github.com/HKUDS/DeepTutor/releases/tag/v1.6.14)。本轮只核实发布信息，**没有逐行审查这些新版本源码，不能承诺直接移植的规模或兼容性**。

推荐维持定点移植，不整包合并上游。当前仍跨越了上游配置/协议大改，现有 fork 的数据、前端和运行契约需要保留；但原文“不建议跟进”是当时的成本判断，不应解释为以后任何上游修复都不再评估。此前移植的 encoding_format 重试、节流、空库引导、HNSW、抽图、预算诊断等应先对照当前代码，再决定补缺。

## 8. 证据和后续定位

本轮临时核查产物（`/tmp` 文件可能被系统清理，结论已保存在本报告）：

- `/tmp/selflearn-audit-pytest-20261010.log`
- `/tmp/selflearn-audit-node-20261010.log`
- `/tmp/selflearn-audit-tsc-20261010.log`
- `/tmp/selflearn-audit-ruff-20261010.log`
- `/tmp/selflearn-audit-probes-20261010.py`
- `/tmp/selflearn-audit-probes-20261010.json`

离线探针使用临时科目目录，模拟 LLM/ASR，报告边界实验只写临时无害标记；真实六科数据未用于写入实验。生产服务和配置没有变更。后续开始改代码时，先选本报告中明确的一个功能闭环，围绕对应真实路径验证，避免继续用上游大套测试的通过数替代分科验收。

# selflearn 项目交接文档（HANDOVER）

> **2026-10-21 S15及第一阶段最终签收**。浏览器5/5通过，协调者直接修复RAG来源隐藏与实际下载失败仍报成功，补强可重复运行的浏览器隔离、网络和清理边界，新增12项永久Node回归。最终结果以 `.phase1-evidence/stages/S15/review.json` 指向的S15-final receipt为准。S00–S15覆盖57张卡，第一阶段关闭；没有S16，不自动实施第二阶段。旧catalog损失未恢复，继续适用用户已批准的单项基线例外；相对于获准新基线及本轮到达时六树均无新增变化。详见 [第一阶段验收与限制](plans/phase1/PHASE1_ACCEPTANCE.md) 及 [只读交接指令（含已探索文件清单+关键片段）](plans/phase1/PHASE1_HANDOFF.txt)。以下“下一阶段/尚未验收”均为历史。

> **2026-10-20 S14协调者复核与单项数据例外**。已补修线程日志异步回调、取消终态/清理及隔离测试入口，修正WS验收时序并增加真实图表失败与取消边界回归。原worker报告blocked_scope及事故原件保持；用户明确批准仅model_catalog.json旧配置损失的完整性例外，新基线见 `plans/phase1/data_baseline_exception.json`，旧基线不覆写，原配置未恢复、未验证真实模型。其他五树与S13相同，协调者到达后六树不再新增变化。当前最终结果和签收以 `.phase1-evidence/stages/S14/review.json` 指向的S14-final receipt为准。下一阶段为 [S15开工指令](plans/phase1/START_S15.txt)，附 [已探索文件清单+关键片段](plans/phase1/S15_EXPLORATION.md)；仅浏览器验收两新文件，尚未实施。第一阶段仍待S15及协调者最终签收，第二阶段不在本轮范围。以下较早“下一阶段/未实施”属历史。

> **2026-10-20 S13最终签收**。协调者补修两项门禁脚本的独立运行、凭证/网络与六树保护、收集计数、自检/结果审计和真实OS断言。完整Python4757通过/20条件skip，实际collect4777（原5499多计类/参数分隔符）；Node477、整站tsc及Ruff通过。真实bwrap七组与16项独立门禁回归通过；145原源码未因worker变化，协调者状态文档更新另有范围记录；当前147源码/1911成员恢复归档，六真实树零变化、8删除保留。签收入口 `.phase1-evidence/stages/S13/review.json` 指向S13-final。原worker21条命令未覆盖完整执行历史，原件保留，独立日志取代其不完整汇总。下一阶段 [S14开工指令](plans/phase1/START_S14.txt) 附 [已探索文件清单+关键片段](plans/phase1/S14_EXPLORATION.md)，P51→P52一次交付；仅两项新验收测试、147前置只读、capture149，S14未实施。OS门仅为本机隔离环境与fake LLM验收，不代表真实供应商/部署/HTTP-WS/浏览器完成；以下旧“最新/下一阶段/未通过OS”按本段和当前receipt解释。

> **2026-10-20 S12最终签收**。协调者独立复跑并补修继承 CDPATH 下的相对路径/相对链接启动，新增两项永久回归；修正环境观察与易碎文档断言。最终361项定向/1既有终端skip、4022项相关目录/20条件skip及完整业务Ruff通过；六真实树零变化，8条tracked deletion保留。签收入口 `.phase1-evidence/stages/S12/review.json` 指向 S12-final，145条当前源码与1907成员最终恢复归档。推荐 `scripts/start_selflearn.sh` 固定home，runtime/home.py全局cwd回退未改；独立Node为v22.22.1，worker v24缺已保存命令证据，原报告保留。S11-final Node测试为477，459为早期提交。下一阶段 [S13开工指令](plans/phase1/START_S13.txt) 附 [已探索文件清单+关键片段](plans/phase1/S13_EXPLORATION.md)，P49→P50一次交付；仅两项新增验收脚本、145既有源码只读、capture147，S13尚未实施。最终OS/HTTP-WS/浏览器门仍S13/S14/S15；以下“最新/下一阶段/未实施”属历史。

> **2026-10-19 最新进度：S11最终签收**。协调者补修4生产/3测试，新增19项永久回归，最终49项定向、3843相关目录/19既有skip、477项Node、全CLI66/1终端skip及tsc/限定Ruff通过；六真实树零变化。签收入口`.phase1-evidence/stages/S11/review.json`，133源码/1902成员归档。下一阶段[S12开工指令](plans/phase1/START_S12.txt)附[已探索文件清单+关键片段](plans/phase1/S12_EXPLORATION.md)，P47→P48一次交付，32具体路径/145 capture；S12未实施。当前仅3 I001+1 E741留给P48；旧阶段“最新/下一阶段/全部可用”均属历史，最终门仍S13 OS/S14 HTTP-WS/S15浏览器。


> **2026-10-19 最新进度：S10最终签收**。协调者复现并修复25项独立边界，补修11生产/5测试；最终121项S10/执行器定向、3806项相关目录/19历史skip及Ruff通过，六真实树零变化。`.phase1-evidence/stages/S10/review.json`指向S10-final，107条源码及1897成员最终恢复归档见receipt。下一阶段[S11开工指令](plans/phase1/START_S11.txt)附[已探索文件清单+关键片段](plans/phase1/S11_EXPLORATION.md)，P42→P43→P44→P45→P46一次交付，29路径/134 capture；S11尚未实施。最终门仍S13/P50 OS沙箱、S14 HTTP/WS、S15浏览器；以下较早“最新/下一阶段”属历史。


> **2026-10-19 最新进度：S09最终签收**。worker原183项定向通过，协调者新增18项永久回归并补修5生产/4测试；最终348项定向（含S08基础）、3739项相关目录/19历史skip及Ruff通过，六真实树零变化。最新`.phase1-evidence/stages/S09/review.json`指向S09-final，99条合并源码及恢复归档见receipt。下一阶段[S10开工指令](plans/phase1/START_S10.txt)附[已探索文件清单+关键片段](plans/phase1/S10_EXPLORATION.md)，P39→P40→P41→P54一次交付；必要共享活动互斥接入已明确授权并同步计划，14路径/107项capture，S10尚未实施。以下旧“下一阶段”叙述属于历史；第一阶段未整体完成，最终真实OS门为S13/P1-50，HTTP/WebSocket为S14，浏览器为S15；以下历史P50/S15混写按此更正。


> **2026-10-17 最新进度：S08最终签收**：Harness返修原32探针通过后，协调者追加13场景复现11项边界失败，已直接补修四生产/三测试文件并新增11项永久回归。最终309项定向/独立检查、3655项相关目录/19历史skip及Ruff通过，真实六树本轮零变化。当前指针`.phase1-evidence/stages/S08/review.json`指向S08-final，94条合并源码与1882成员恢复归档见receipt。下一阶段为[S09开工指令](plans/phase1/START_S09.txt)及[已探索文件清单+关键片段](plans/phase1/S09_EXPLORATION.md)，P35→P36→P37→P38一次交付；额外窄授权P31旧流水线接缝适配，9路径/99项capture，S09尚未实施。以下较早changes_requested/下一阶段均属历史；第一阶段未整体完成，最终OS/浏览器/真实供应商仍未获端到端验收。


> **2026-10-17 当前进度：S08初审未签收**：Harness四卡verified_local后，协调者复跑165项定向、3556项相关目录/19历史skip及Ruff通过，但独立32场景复现28项失败/4通过。确认run路径/metadata、创建竞争和失败收尾、进程deadline/组清理/worker日志内存、结果协议、attempt以及真实bwrap ODE自签问题。当前changes_requested，按[S08合并返修](plans/phase1/REWORK_S08.txt)及[19文件77片段探索包](plans/phase1/S08_REWORK_EXPLORATION.md)完成R1–R8，不进入S09。最新指针`.phase1-evidence/stages/S08/review.json`；94条源码基准、原十路径授权/84前置只读。协调者本轮未修改生产或既有测试，真实六树无变化。以下S07等“最新/下一阶段”均为历史进度；S08 API接入和最终OS门分别仍在后续S09/S15。


> **2026-10-16 最新进度：S07最终签收**：S07返修后协调者仍复现11项边界失败，已直接补修四生产/五测试文件及11项永久回归；17项Question测试环境失败也已隔离配置消除。最终244项定向/独立后端、3391项相关回归/19历史条件skip、429项Node/7前端独立探针、tsc/Ruff通过，真实六树本轮零变化。以`.phase1-evidence/stages/S07/review.json`指向的S07-final为当前签收，84条合并源码hash和1869成员恢复归档详见receipt。下一阶段为[START_S08](plans/phase1/START_S08.txt)，附[24文件65片段探索包](plans/phase1/S08_EXPLORATION.md)，P31→P32→P33→P34按阶段一次交付；S08尚未实施。以下较早“下一阶段/未实施/changes_requested”均为历史进度，当前以本段及阶段索引为准；第一阶段整体尚未完成，真实供应商/浏览器及OS隔离未因此获端到端验收。


> **2026-10-10 核查补充**：已对照 Git、源码、配置和本地测试复核，详细结果见 [项目现状核查报告](PROJECT_AUDIT_2026-10-10.md)。本文以下保留 2026-09-28 的历史交接记录。当前服务未运行；真实科目数据位于 `data/user/workspace/subjects/`；核查开始时 Git 有 51 条未提交路径（含本文）；本轮后端基线为 2917 passed / 1 failed / 22 skipped（固定时间夹具已过期），前端 403 项和类型检查通过。新增审查确认了科目聊天检索未接通、批改失败误入错题、音频路径校验缺口等问题，不能继续把下文的“全部可用”视为今日端到端结论。

> **第一阶段修复计划**：后续执行以 [任务包入口](plans/phase1/README.md)、[数据契约](plans/phase1/DATA_CONTRACTS.md) 和逐卡任务为准。任务包当前为 planned；产出计划不代表已经修复，第二阶段新增功能不在本包范围内。

> **2026-10-11执行更新**：P1-00已执行并验收；S01已在Harness rework01基础上由协调者补修验收，相关跨目录回归1742 passed/18 skipped、API优先286 passed，实际数据本轮未变，历史memory trace保留。当前签收见.phase1-evidence/stages/S01/review.json，旧changes_requested记录只作历史。后续按[阶段流程2.0](plans/phase1/STAGE_WORKFLOW.md)执行，下一阶段为[S02开工指令](plans/phase1/START_S02.txt)，S02及其他业务功能尚未完成。

> **S02审查更新**：S02初次提交指定213项与协调者补跑的services/API/phase1相关1849项通过，但独立行为检查复现错误消息/状态可覆盖、异常误分类和JSON数字/包装解析缺陷，当前为changes_requested。按[S02合并返修指令](plans/phase1/REWORK_S02.txt)处理，不进入S03；本轮真实数据无新变化，旧证据保留。

> **S02最终签收**：上述changes_requested记录已由后续验收取代。Harness rework01后，协调者补修围栏首行吞对象、状态值比较及固定错误字段，并修正S03前置fixture为合法slug/空KB记录。最终相关目录1907 passed/18 skipped、独立14项通过、Ruff通过，实际数据本轮不变；当前签收见.phase1-evidence/stages/S02/review.json，最新源码hash覆盖必要的fixture更新。下一阶段按[S03开工指令](plans/phase1/START_S03.txt)执行，其余业务修复尚未完成。

> **S03初次审查**：指定466项、完整相关目录2102项/18 skipped和Ruff通过，但独立检查复现跨科symlink读取、创建/注册异常留下无效状态、已有树覆写、字段/legacy默认遗漏以及fork/解锁异常的锁故障。当前changes_requested，按[S03合并返修指令](plans/phase1/REWORK_S03.txt)处理，不进入S04；本轮真实数据无新变化，初次代码与证据保留。

> **2026-10-13 S03最终签收**：上述changes_requested已被最新验收取代。Harness rework01旧309项与17探针均通过，但补充边界检查仍复现继承线程锁死锁、FIFO阻塞、IO错误裸漏、显式null绕过以及空白名称/非法输入遗漏；协调者已直接修复六个生产文件与五份测试，最终355项定向、2262项相关目录/18历史skip及Ruff通过。当前签收见`.phase1-evidence/stages/S03/review.json`，最新receipt合并27个前置源码hash；真实数据无本轮新增变化。下一阶段是[S04开工指令](plans/phase1/START_S04.txt)，附[已探索文件清单+关键片段](plans/phase1/S04_EXPLORATION.md)，按阶段流程2.1复用定位；尚未实施S04代码或第二阶段新功能。

> **2026-10-13 S04初次审查**：worker六卡实现已提交，协调者复跑298项定向、2560项相关目录/18历史skip及Ruff通过，归档1833/1833。但独立14方法含子场景复现28处失败：检测枚举/批量必填字段遗漏、重复候选漏确认、坏旧元数据返回成功、已包装LLM/存储cause未投影而泄漏诊断。当前changes_requested，按[S04合并返修](plans/phase1/REWORK_S04.txt)及[更新探索包](plans/phase1/S04_REWORK_EXPLORATION.md)处理，不进入S05；本轮协调者未改生产/原有测试，真实六树无新变化，旧提交证据保留。

> **2026-10-14 S04最终签收**：上述S04 changes_requested已被最终验收取代。Harness R1–R5返修与357项定向结果相符；协调者补充检查复现不可UTF-8编码的模型feedback可能先写attempt再HTTP500，以及坏检测字符串晚失败，已直接修复并增加12项测试。最终369项定向、2631项相关目录/18历史skip、18方法扩展探针及Ruff通过；真实六树无本轮新增变化。当前指针`.phase1-evidence/stages/S04/review.json`指向S04-final，合并37条当前源码hash。下一阶段为[S05开工指令](plans/phase1/START_S05.txt)及[已探索文件清单+关键片段](plans/phase1/S05_EXPLORATION.md)；S05尚未实施。P1-39/P1-54留S10，真实供应商/浏览器/系统沙箱仍按后续验收门，不把本次离线通过说成全项目完成。

> **2026-10-14 S05初次审查**：Harness六卡已提交verified_local，12源码/19证据/25命令核验一致，126项定向与Ruff复跑通过；但独立23方法含子场景复现24处失败：临时音频part软链接越界写、manifest/state软链接/null读取、GET迁移配置、同大小替换假ready、部分回滚/跨KB共享记录丢失、排队/任务身份及源门禁遗漏、进度串worker、ASR配置/JSON边界。相关目录2739 passed、1 failed、18历史skip，P30时序测试单跑可通过。当前changes_requested，按[S05合并返修](plans/phase1/REWORK_S05.txt)及[返修探索包](plans/phase1/S05_REWORK_EXPLORATION.md)在原阶段修补，不进入S06；协调者未改生产/测试，所有故障实验在tmp，真实六树本轮不变。当前48条源码hash见`.phase1-evidence/stages/S05/review.json`所指receipt。

> **2026-10-14 S05最终签收**：上述S05初次changes_requested已由S05-final取代。Harness R1–R7及原探针通过，但协调者追加检查仍发现连续重建误stale、后写失败回滚遗漏、预提交任务未结束、源IO门禁清理、损坏state被覆盖、隐藏文件双副本不一致、ASR类型及回调注销竞争，已直接修复五生产/四测试文件并新增13项永久回归。最终197项定向、2811项相关目录/18历史skip、33方法独立探针、Ruff、六树保护及恢复归档核验通过，真实数据无本轮新变化。当前指针`.phase1-evidence/stages/S05/review.json`指向S05-final，合并48条当前源码hash。下一阶段为[S06开工指令](plans/phase1/START_S06.txt)，附[已探索文件清单+关键片段](plans/phase1/S06_EXPLORATION.md)；P26→P27→P28按阶段一次交付，不重做全仓orientation。真实供应商/浏览器、进程外调度和崩溃原子性仍不在本次离线签收证明内；P39/P54等后续问题按原进度处理。

> **2026-10-16 S06初次审查**：Harness P26–P28已提交verified_local，协调者复跑137项合并、2940项相关目录/18历史skip与Ruff通过，25产物/38命令/46只读源码/29前置证据核验一致，归档1853/1853；但独立18方法含子场景复现18处失败，包括资产根软链接、旧ImageNode门禁/超时/截断、失败额度不扣、factory去图后冒充OCR、元数据失败仍发布、旧coverage残留、ready公开警告丢失与PDF漏计。当前changes_requested，按[S06合并返修](plans/phase1/REWORK_S06.txt)和[已探索文件清单+关键片段](plans/phase1/S06_REWORK_EXPLORATION.md)完成R1–R6，不进入S07。新增四个生产接缝已明确窄授权；最新59条源码基准/返修14路径/45只读见阶段receipt。协调者未改生产/既有测试，真实六树本轮不变，普通失败回滚与公开覆盖投影须本阶段补齐。

> **2026-10-16 S06最终签收**：初次changes_requested与worker返修verified_local已由S06-final取代。协调者确认157项与旧18方法通过后，追加复现9类/11断言失败并直接修复六生产/两测试文件：元数据部分提交/后续发布失败恢复、超时/取消待活线程退出再清理、busy拒绝不创建版本、同任务/null任务清旧coverage、统计守恒、嵌套深拷贝及独立图片父链接拒绝。最终168项合并、2971项相关目录/18历史skip、27方法独立探针、Ruff、六树保护与恢复归档核验通过。返修派生证据1条hash漂移已原样保留并独立复核；当前指针`.phase1-evidence/stages/S06/review.json`指向S06-final，合并59条当前源码hash。下一阶段为[S07开工指令](plans/phase1/START_S07.txt)与[已探索文件清单+关键片段](plans/phase1/S07_EXPLORATION.md)，P20→P25六卡一次交付；新增窄授权统一WS拒绝分支及测试，共18路径。S07尚未实施，真实供应商/浏览器与崩溃原子性不在本次离线验收证明内。

> **2026-10-16 S07初次审查**：Harness六卡提交verified_local；127项定向/2旧环境skip、420项Node、Ruff/tsc独立复跑通过，相关回归3264 passed/21 skipped/2历史模型配置失败已在S06封存归档独立重建复现。46产物hash匹配，42列出命令核对一致，另2个最终收尾命令未列入report。独立探针26后端+7前端场景确认30处目标失败（3正例通过）：身份/挂载/存在/provider、三态与原始挂载重放、前端快照/加载/清空、warning不可见、公开结果及异常泄漏、PageIndex缺标记、Question/Research端漏scope。当前changes_requested，按[S07合并返修](plans/phase1/REWORK_S07.txt)与[已探索文件清单+关键片段](plans/phase1/S07_REWORK_EXPLORATION.md)执行R1–R8；窄补5个既有接缝，23允许路径/82源码基准，其余59只读。不进入S08，协调者未改生产或现有测试，真实六树无本轮新变化。

> **文档定位**：本文档面向**接手本项目的下一个人或 AI Agent**，目标是让你在最短时间内准确掌握：这个项目是什么、从上游 DeepTutor 裁剪掉了什么、做过哪些修改、当前功能与状态如何、以及要动手改代码时该从哪里入手。
>
> **阅读顺序建议**：第 1–3 章（建立全局认知）→ 第 6–8 章（把环境跑起来）→ 第 9 章（了解改动全貌）→ 第 11–12 章（知道有哪些坑和可做项）。
>
> **最后更新**：2026-09-28
> **文档基准**：工作区最新代码（含**尚未提交**的 50 处改动，见第 9.6 节，这一点非常重要）

---

## 1. 项目是什么

**selflearn（分科学习助手）** 是一个面向**单人多科目**的学习辅助系统。它不是通用聊天机器人，而是围绕**"科目"**这一核心实体组织的学习工作台。

一个"科目"（如"复变函数"）拥有自己独立的一整套数据：知识库、考点、错题本、知识点索引、学习画像，并能据此生成复习指南 PDF、图表报告 PDF、整科备份。

它支持两种使用方式：
- **主聊天路径**：与通用 AI 聊天，但可挂载"科目上下文"，让回答基于该科目的资料与错题
- **科目工作台**：`/subjects` 页面的分科目管理界面，覆盖考点确认、错题录入、复习材料生成等流程

---

## 2. 与上游 DeepTutor 的关系（**这是理解本项目的前提**）

本项目是 **[HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor)**（Apache-2.0）的 **fork**，不是从零开始的项目。

### 2.1 分叉点

| 项 | 值 |
|---|---|
| 上游仓库 | `https://github.com/HKUDS/DeepTutor` |
| **分叉点 commit** | **`15bf5ad`** — `feat: add dedicated vision model slot to model catalog` |
| 分叉时上游版本 | **v1.5.13** |
| 分叉日期 | 2026-08-19 |
| 本仓库 | `https://github.com/Albertanda/selflearn.git`（私有） |
| 本仓库分支 | `main` |
| fork 后提交数 | **17 个**（`15bf5ad..HEAD`） |
| 当前上游版本 | **v1.6.11**（2026-09-24），已领先 **14 个 release** |

> ⚠️ **重要**：本仓库的 git 历史**包含上游全部历史**（共 94 个提交）。因此 `git log` 里绝大多数提交是上游的，不是本项目的。**只有 `2b6be38` 之后的 17 个提交属于本 fork**。
>
> 判断某个文件是不是本项目改的，用：`git log --oneline 15bf5ad..HEAD -- <路径>`

### 2.2 上游文档如何区分

仓库根目录有三个容易混淆的文档：

| 文件 | 是什么 | 归属 |
|---|---|---|
| `UPSTREAM.md` | 上游 DeepTutor 的 README 全文（894 行，含多语言徽章） | **上游存档**，未删以便对照 |
| `AGENTS.md` | 上游的架构说明（工具/能力两层插件模型） | **上游文档**，大部分内容仍然适用 |
| `README.md` | 本项目的说明（已按 fork 现状改写） | **本项目** |
| `HANDOVER.md` | **本文档** | **本项目** |

> `AGENTS.md` 描述的架构在裁剪后**仍有参考价值**，但它提到的部分能力（Obsidian、subagent、MCP、partners、book）在本 fork 中**已被删除**，阅读时注意第 3 章的裁剪清单。

---

## 3. 从 DeepTutor 裁剪了什么（M0 裁剪）

fork 后的**第一个实质提交**就是大规模裁剪：

```
2b6be38  M0: trim unused subsystems for subject-learning fork
         363 files changed, 102 insertions(+), 85161 deletions(-)
```

**裁剪动机**：上游是个"全能学习伴侣"，包含大量与"分科学习助手"定位无关的子系统。保留它们会带来巨量维护面、依赖负担和攻击面。

### 3.1 被整体删除的后端子系统

| 删除路径 | 文件数 | 是什么 | 为何删 |
|---|---|---|---|
| `deeptutor/book/` | ~69 | AI 生成交互式电子书（含 prompts、blocks、agents） | 与分科学习无关 |
| `deeptutor/partners/` | ~30 | "伙伴"系统（多渠道、总线、配置、人格） | 需要外部渠道集成，本项目不用 |
| `deeptutor/services/subagent/` | 17 | 子代理编排 | 复杂度高、本项目用不到 |
| `deeptutor/services/mcp/` | 13 | MCP 协议接入 | 外部工具协议，本项目不用 |
| `deeptutor/services/cli_apps/` | 10 | 外部 CLI 应用集成 | 同上 |
| `deeptutor/services/partners/` | 9 | 伙伴服务层 | 随 partners 一并删 |
| `deeptutor/capabilities/obsidian/` | 7 | Obsidian 笔记库集成 | 本项目不用 Obsidian |
| `deeptutor/capabilities/subagent/` | 4 | 子代理能力 | 随 subagent 一并删 |
| `deeptutor/api/routers/` 下若干 | 9 | 上述子系统对应的 API | 路由随之删除 |
| `deeptutor/tools/` 下若干 | 4 | `tex_downloader`、`tex_chunker`、`partner_memory`、`github_query` | 依赖已删子系统 |

### 3.2 被删除的前端

| 删除路径 | 文件数 | 说明 |
|---|---|---|
| `web/app/(workspace)/` 下若干 | 30 | book、partners、mcp、agents 等页面 |
| `web/components/partners/` | 15 | `SoulEditor`、`SoulPicker`、`ToolPicker`、`schema-form` 等 |
| `web/components/mcp/` | 11 | MCP 配置界面 |
| `web/app/(utility)/` 下若干 | 4 | 相关工具页 |
| `web/components/agents/` | 3 | 代理相关组件 |
| `web/components/cli-apps/` | 1 | CLI 应用组件 |

### 3.3 被删除的测试

`tests/` 下 **109 个测试文件**被删除——它们测试的是上述已删子系统。

### 3.4 裁剪后**保留**的上游能力（仍然可用）

这些是上游原有、本项目继续使用的：

- **核心 agent 循环**：`deeptutor/core/agentic/`（标签驱动迭代、工具派发、流式总线）
- **RAG 管线**：`deeptutor/services/rag/pipelines/llamaindex/`（LlamaIndex + FAISS + BM25 混合检索）
- **多模态与视觉**：图片/附件 → 视觉模型
- **PDF 生成**：Typst 编译（含 CJK 字体处理）
- **记忆系统**：`deeptutor/services/memory/`
- **技能系统**：`deeptutor/skills/`、skills hub 安装
- **多用户与鉴权**：`deeptutor/multi_user/`
- **notebook / 错题本基础**：`deeptutor/services/notebook/`
- **co-writer（协作写作）**：`deeptutor/co_writer/`
- **CLI**：`deeptutor_cli/`

### 3.5 裁剪带来的**已知副作用**（已在后续修复）

裁剪不是完全干净的，后续发现并修复了这些问题（详见第 9 章）：

1. **前端导航断裂** — 删页面后残留引用 → 提交 `396106a` 修复
2. **CLI 死命令** — `deeptutor_cli/book.py`、`partner.py` 仍被注册，一调用就 `ModuleNotFoundError` → 已删除（见 9.3）
3. **死代码引用已删子系统** — `_vault_path` 注入、`obsidian_*` 工具被引用但不存在 → 已修（见 9.3）
4. **失败测试残留** — 测试已删子系统的用例 → 已删（见 9.3）

---

## 4. 本 fork 的 17 个提交（时间线）

```
9723f95  feat(M4+/M7+): real lecture audio -> ASR; report tool inside chat
0616271  feat(ui): subject selectors and subject context on the main chat path
396106a  fix(ui): restore navigation after M0 trim; vision provider presets
3158928  chore: drop inherited upstream CI workflows
69b64b1  build(release): exclude toolchain binaries and fonts from VCS
62f18d2  M8: polish release — vision strategy, subject workbench UI, backups, docs
eb4153f  fix(report): LLM-authored chart equations now numerically self-checked
a74e4eb  fix(PDF): CJK fonts missing in Typst and matplotlib child processes
6fb6bcf  M7: chart-bearing report writing with PDF export
ca69542  M5+: subject profile, history summarization, token-saver switch
dc53606  M5+M6 follow-up: output allowlist for subjects, token observability
71e238d  M5+M6: knowledge-point index, 3-layer context injection, PDF review packs
4426c20  M4: exam-point detection pipeline with iterative prompt tuning
4bbefce  M3: per-subject wrong-question book with four-level mastery
162cea0  M1+M2: subject-scoped data layer and per-subject knowledge bases
7f3bc17  M0: fix frontend references after trim
2b6be38  M0: trim unused subsystems for subject-learning fork
```

**里程碑（M0–M8）就是分科目功能的建设顺序**，第 5 章按里程碑列功能。

---

## 5. 功能清单与现状

### 5.1 分科目功能（本项目的核心增量）

| 里程碑 | 功能 | 关键文件 | 现状 |
|---|---|---|---|
| **M0** | 裁剪上游无关子系统 | 见第 3 章 | ✅ 完成 |
| **M1** | 科目数据层（科目 CRUD、每科独立存储） | `deeptutor/subjects/store.py` | ✅ 可用 |
| **M2** | 每科独立知识库（上传→索引→检索） | `deeptutor/api/routers/subjects.py`、`deeptutor/knowledge/` | ✅ 实测可用 |
| **M3** | 错题本（AI 批改 + 四级掌握度） | `deeptutor/subjects/wrong_book.py` | ✅ 可用 |
| **M4** | 考点检测（课堂转写→考点候选→人工确认）<br>**+ 真实课堂音频 → ASR** | `deeptutor/subjects/exam_detection.py`、`exam_points.py` | ✅ 可用 |
| **M5** | 知识点索引、三层上下文注入、学习画像、历史摘要、token 观测 | `deeptutor/subjects/knowledge_points.py`、`profile.py` | ✅ 可用 |
| **M6** | 复习指南 PDF 生成（Typst，中文排版） | `deeptutor/services/pdf/review_guide.py` | ✅ 实测可用 |
| **M7** | 图表报告生成（LLM 写代码→matplotlib 出图→嵌入 PDF）<br>**+ 报告工具可在聊天内调用** | `deeptutor/services/pdf/report.py`、`deeptutor/tools/report_tool.py` | ✅ 实测可用 |
| **M8** | 发布打磨：视觉策略、科目工作台 UI、整科备份/导出、文档 | `deeptutor/api/routers/subjects.py` | ✅ 可用 |

### 5.2 继承自上游、仍可用的能力

| 能力 | 入口 | 说明 |
|---|---|---|
| 主聊天（agent 循环 + 工具调用） | `/home` 页面、`/api/v1/ws` | 支持科目上下文挂载 |
| 知识库管理 | `deeptutor_cli/kb.py`、`/api/v1/knowledge/*` | LlamaIndex + FAISS + BM25 混合检索 |
| 文档解析 | `deeptutor/services/parsing/`、`deeptutor/utils/document_extractor.py` | PDF/DOCX/PPTX/XLSX/EPUB 等 |
| **文档内嵌图片 → 视觉模型** | `deeptutor/utils/document_images.py` | ✅ 2026-09-28 新增，见 9.6 |
| 多模态聊天（图片附件） | `deeptutor/services/llm/multimodal.py` | 任意模型乐观注入，失败降级纯文本 |
| 记忆系统 | `/api/v1/memory/*`、`deeptutor_cli/memory.py` | |
| 技能系统 | `/api/v1/skills/*`、skills hub | |
| co-writer 协作写作 | `/co-writer` | |
| notebook 笔记 | `/api/v1/notebook/*` | |
| 多用户与鉴权 | `deeptutor/multi_user/` | 本项目单人使用，但代码路径存在 |
| 语音能力 | `/api/v1/voice/*` | |

> **注意**："可用"= 我在 2026-09-28 实测通过（见第 8 章）。未在表中标注"实测"的，是继承了上游测试（pytest 2918 项）但未做人工端到端验证。

---

## 6. 环境与依赖

### 6.1 运行时

| 项 | 值 |
|---|---|
| Python | **3.12.14**（必须，见下方约束） |
| 虚拟环境 | `/home/albert/selflearn/selflearn/.venv` |
| Node.js | Next.js **16.2.3** |
| 包管理器 | `uv`（Python）、`npm`（前端） |
| Typst | `tools/bin/typst`（本地二进制，PDF 编译用） |
| 中文字体 | `tools/fonts/{SimsunExtG.ttf, msyh.ttc, simhei.ttf}` |

> ⚠️ **Python 版本约束**：`pyproject.toml` 声明 `requires-python = ">=3.11,<3.14"`。**系统自带的 Python 3.14 不受支持**，必须用 `.venv` 里的 3.12。若你重建环境，用 `uv python install 3.12`。

> ⚠️ **依赖安装必须用 `--link-mode=copy`**：NLTK 3.10.3 加了硬链接安全校验（`st_nlink` 检查），而 uv 默认用硬链接装包，会触发 `Security Violation [pathsec.open]: refusing multiply-linked file`。重建环境时：
> ```bash
> uv pip install --link-mode=copy -e ".[cli]"
> ```

### 6.2 关键依赖版本（实测）

```
fastapi                          0.141.1
uvicorn                          0.52.4
llama-index-core                 0.14.24
llama-index-vector-stores-faiss  0.7.0
llama-index-retrievers-bm25      0.7.1
faiss-cpu                        1.15.0
pymupdf                          1.28.2
python-docx                      1.2.0
python-pptx                      1.0.2
matplotlib                       3.11.2
pillow                           12.3.0
defusedxml                       0.7.1
httpx                            0.28.1
numpy                            2.5.3
websockets                       17.1
openai                           2.54.0
pytest                           9.1.1
```

### 6.3 外部服务依赖

| 用途 | 提供商 | 模型 | 备注 |
|---|---|---|---|
| **LLM** | DeepSeek | `deepseek-flash`（另有 `deepseek-v4-pro`） | 主模型 |
| **视觉模型** | DeepSeek | `deepseek-flash` | 图片理解 |
| **Embedding** | **SiliconFlow** | `Qwen/Qwen3-Embedding-8B`（**4096 维**） | 备选：`4B`(2560维)、`BAAI/bge-m3`(1024维) |
| **Web 搜索** | Bocha | — | |

> ⚠️ **换 embedding 模型会触发全量重建索引**：不同模型的向量维度/空间不兼容。本项目有 embedding 签名机制（`deeptutor/services/rag/embedding_signature.py`）会自动检测并重建，但**重建很慢**（SiliconFlow 8B 模型 + 网络抖动时，一个小知识库可能要几分钟到十几分钟）。

---

## 7. 配置

### 7.1 配置文件位置（**全部在 `data/user/settings/`**）

| 文件 | 内容 |
|---|---|
| `data/user/settings/model_catalog.json` | LLM / embedding / search / vision 的 provider 与模型配置 |
| `data/user/settings/system.json` | 端口、附件限额、SSL 校验开关等运行时设置 |
| `data/user/settings/*.json` | 其它运行时设置（工具开关、能力开关等） |

> ⚠️ **API 密钥就明文存在 `model_catalog.json` 里**。本文档**故意不抄录密钥**——你需要时自己打开该文件。若要把仓库推公开，**务必先清理此文件并从 git 历史移除**。
>
> ⚠️ **项目刻意忽略仓库根目录的 `.env`**：所有运行时设置都从 `data/user/settings/*.json` 读。改 `.env` 不会生效。

### 7.2 数据根目录的陷阱（**极易踩**）

数据根目录的解析顺序是：`DEEPTUTOR_HOME` 环境变量 → **未设置则回退到「当前工作目录」**。

> 🔴 **因此：必须在仓库根目录 `/home/albert/selflearn/selflearn` 下启动服务。** 从其它目录启动会**静默**在别处创建一棵空数据树，表现为"我的科目/知识库全不见了"，而实际数据完好。

### 7.3 数据目录结构

```
data/
├── knowledge_bases/          # 知识库原始文件与索引
├── user/
│   ├── settings/             # 运行时配置（含密钥）
│   ├── subjects/<科目名>/    # 每科的产物：review-guide-*.pdf/.typ、report-*、subject-backup-*.zip
│   ├── logs/deeptutor.jsonl  # 结构化日志（排查问题先看这里）
│   └── workspace/            # chat 历史、notebook、personas、co-writer 等
├── memory/                   # 记忆系统
└── system/grants/            # 多用户授权
```

---

## 8. 启动、测试与验证

### 8.1 启动（推荐方式）

```bash
cd /home/albert/selflearn/selflearn
./.venv/bin/deeptutor start
```

`deeptutor start` 会**同时启动前后端**，源码模式默认走生产构建（构建产物在 `web/.next-deeptutor/`，刻意不污染 `next dev` 用的 `.next`）。

前端开发模式（改前端代码时用，带热更新）：

```bash
./.venv/bin/deeptutor start --dev
```

### 8.2 手工分开启动（备用）

```bash
# 终端 1 — 后端
cd /home/albert/selflearn/selflearn
PYTHONPATH=$PWD ./.venv/bin/python -m uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001

# 终端 2 — 前端
cd /home/albert/selflearn/selflearn/web
npx next start -p 3782 -H 0.0.0.0
```

> 关于前端启动方式的一个坑：本项目 `next.config` 用了 `output: "standalone"`，所以 Next.js 会警告 `next start` 不是官方路径。**但直接 `node .next/standalone/server.js` 目前不能用**——standalone 目录里缺少 `.next/static` 和 `public`，直接跑会丢失 CSS/JS。**日常请用 `deeptutor start`**；手工启动时 `npx next start` 实测正常（只是会打印那条警告）。

### 8.3 访问地址

| 用途 | 地址 |
|---|---|
| **主界面（聊天）** | **http://localhost:3782/home** |
| 科目工作台 | http://localhost:3782/subjects |
| 模型设置 | http://localhost:3782/settings/models |
| 后端 API 文档（Swagger） | http://localhost:8001/docs |
| 从 Windows 访问（WSL IP） | `http://$(hostname -I \| awk '{print $1}'):3782`（本机为 `172.17.105.150`） |

端口可在 `data/user/settings/system.json` 的 `backend_port` / `frontend_port` 修改。

### 8.4 测试命令

```bash
# Python 测试 —— 必须用裸 pytest！
cd /home/albert/selflearn/selflearn
./.venv/bin/python -m pytest -q

# 前端测试
cd /home/albert/selflearn/selflearn/web
node ./scripts/run-node-tests.mjs

# 前端类型检查
cd /home/albert/selflearn/selflearn/web
npx tsc --noEmit -p .
```

> 🔴 **不要用 `pytest tests/`**：`pyproject.toml` 里配了 `testpaths = ["tests", "deeptutor/learning/tests"]`，裸 `pytest` 才会跑全部。用 `pytest tests/` 会**漏掉 `deeptutor/learning/tests`**（约 293 项）。
>
> 另一个坑：`pkill -f "uvicorn deeptutor"` 和 `pgrep -f "next-server"` 会**匹配到执行命令的 shell 自身**，把当前会话杀掉。用括号技巧规避：`pgrep -f "uvicorn[ ]deeptutor"`。

### 8.5 当前基线（2026-09-28 实测）

| 测试 | 结果 |
|---|---|
| `pytest`（完整 testpaths） | **2918 passed / 0 failed / 22 skipped**（收集 2940 项） |
| 前端 node 测试 | **403 passed / 0 failed** |
| `tsc --noEmit` | **0 错误** |
| 端到端回归（M1–M8 + 各批次修复） | **33 项全通过** |

### 8.6 已知的非阻塞噪音

- **ruff**：残留 10 处 `I001`（import 排序）、1 处 `E741`（`summarize.py:71` 变量名 `l`）、3 处上游既有 `F841`（未使用变量）。属**上游遗留**，明确不在本项目修复范围。
- **SiliconFlow embedding 偶发 `ReadTimeout`**：日志里会看到重试警告，自动重试可恢复，但会让索引耗时从几十秒变成几分钟。**不是 bug**。

---

## 9. 改动全貌

本章分两部分：**9.1–9.5 是已提交到 git 的历史**，**9.6 是尚未提交的 50 处改动（最重要）**。

### 9.1 M1+M2（`162cea0`）— 科目数据层与每科知识库

新建 `deeptutor/subjects/`（数据层）、`deeptutor/api/routers/subjects.py`（API）。引入"科目"作为一等实体，每科拥有独立的知识库（`subject_kb_*` 命名）、独立的考点/错题/知识点存储。

### 9.2 M3/M4（`4bbefce`、`4426c20`）— 错题本与考点检测

- `wrong_book.py`：AI 批改（correct/partial/wrong）+ **四级掌握度**状态机
- `exam_detection.py` + `exam_points.py`：课堂转写 → LLM 提取考点候选 → 人工确认；含"负向信号"排除（如"这个不考"）

### 9.3 M5/M6（`71e238d`、`dc53606`、`ca69542`）— 知识点索引、上下文注入、复习 PDF

- `knowledge_points.py`：知识点索引与关联
- **三层上下文注入**：科目资料 / 错题 / 画像分层进入 prompt
- `services/pdf/review_guide.py`：Typst 渲染复习指南 PDF
- 输出白名单、token 可观测性
- `profile.py`：学习画像、历史摘要、token-saver 开关

### 9.4 M7（`6fb6bcf`、`a74e4eb`、`eb4153f`）— 图表报告

- `services/pdf/report.py`：LLM 生成 matplotlib 代码 → 执行出图 → 嵌入 PDF
- `a74e4eb`：**修复 Typst 与 matplotlib 子进程的中文字体缺失**（关键，否则中文全是方块）
- `eb4153f`：LLM 写的图表方程做**数值自检**（防止图画错）

### 9.5 M8 + UI（`62f18d2`、`396106a`、`0616271`、`9723f95`）

- `62f18d2`：视觉策略（独立 vision 模型槽位）、科目工作台 UI、整科备份/导出
- `396106a`：修复 M0 裁剪导致的前端导航断裂
- `0616271`：主聊天路径接入科目选择器与科目上下文
- `9723f95`：**真实课堂音频 → ASR**；报告工具可在聊天内调用

### 9.6 ⚠️ 尚未提交的 50 处改动（**接手后请优先了解**）

> **状态**：全部已在工作区，**已测试通过，但未 `git commit`**。
> `git status` 显示：`2 个新增 / 5 个删除 / 43 个修改`，合计 **+1146 / −1149 行**。
> **建议接手后第一件事就是把这些改动分批提交**，否则容易与后续工作混淆或丢失。

#### 9.6.1 安全修复

| 文件 | 改动 | 影响 |
|---|---|---|
| `services/notebook/service.py` | +15 −1 | **路径穿越漏洞**：notebook id 形如 `../../kb_config` 可逃出数据目录。现用 `is_relative_to` 拦截。**实测：3 种穿越 id 全部被拒** |

#### 9.6.2 缺陷修复（P0/P1/P2/P3 系列）

| 文件 | 改动 | 修的是什么 |
|---|---|---|
| `runtime/request_contracts.py` | +7 | `subject_id` 被当成非法字段拒绝（`Extra inputs are not permitted`） |
| `services/session/turn_runtime.py` | +17 −? | 配套：把 `subject_id` 作为运行时键处理 |
| `knowledge/initializer.py` | +13 | 知识库配置未限定在 base_dir 内 |
| `multi_user/{paths,router,partner_access}.py` | +76 −? | 已删 partners 子系统的残留引用 |
| `agents/chat/agentic_pipeline.py` | +30 −? | 科目上下文在主聊天路径的接入 |
| `subjects/{__init__,store,wrong_book}.py` | +64 −? | **掌握度显示不一致**：0.8 却显示"基础"。现统一用 `MASTERY_PRECISION=3` 舍入 |
| `services/pdf/{review_guide,report}.py` | +153 −33 | **空白 PDF**（HTTP 200 但 `markdown_tokens: 0`）：推理模型把 `max_tokens` 全烧在思考上。现提到 16000 并加空响应守卫；另修 Typst 转义（`0<a<1` 导致 `unclosed label`） |
| `tools/report_tool.py` | +38 −? | 提示词转发、改懒加载 |
| `api/routers/{chat,knowledge,settings,subjects}.py` | +143 −? | 若干接口缺陷 |
| `web/components/chat/home/SubjectSelector.tsx` | +18 −? | **UI**：科目下拉菜单向下展开被裁切 → 改为向上展开（用户已确认修复） |
| `deeptutor_cli/main.py` | +12 −? | 移除指向已删模块的死命令 |
| `deeptutor_cli/{book,partner}.py` | **删除** | 一调用就 `ModuleNotFoundError` 的死命令 |
| `pyproject.toml`、`requirements/cli.txt` | +11 | 补 `matplotlib` 依赖（M7 图表需要） |
| `README.md` | +23 −? | 修正硬编码的 Python 路径、说明 `DEEPTUTOR_HOME` 陷阱 |
| 5 个测试文件 | 删除/修改 | 移除测试已删子系统的过期用例（`test_research_obsidian_tools.py` 等） |

#### 9.6.3 移植上游 v1.6.11 的修复（Batch 1 + Batch 2）

> 这批是**参照上游 v1.6.11 源码逐行对照**移植的，不是凭发布说明猜测。

**Batch 1**

| 文件 | 改动 | 来源版本 | 影响 |
|---|---|---|---|
| `services/notebook/service.py` | 见 9.6.1 | v1.6.11 | 路径穿越 |
| `services/llm/types.py` | +35 | v1.6.10 | 新增 `TRUNCATED_FINISH_REASONS`、`finish_was_truncated()`、`StreamOutcome` |
| `services/llm/exceptions.py` | +40 | v1.6.10 | 新增 `LLMReasoningBudgetExhausted`（`error_code=reasoning_budget_exhausted`） |
| `services/llm/factory.py` | +48 −2 | v1.6.10 | 新增 `complete_response()` 暴露 `finish_reason`；**`complete()` 改为委托，行为逐字节不变** |
| `subjects/generation.py` | **新增 79 行** | 本项目适配 | 科目功能统一 LLM 调用；预算耗尽时抛出**具名可诊断错误**（含 `finish_reason`/`completion_tokens`/`max_tokens`）。接入 M3 批改、M4 考点、M6 指南、M7 报告共 4 处 |
| `core/agentic/labeled_step.py` | +14 −1 | v1.6.10 | `LabeledStepResult.finish_reason`（纯增量，默认 `None`） |
| `core/agentic/loop.py` | +23 | v1.6.10 | `LoopOutcome.truncated` + 截断警告日志 |
| `services/rag/.../pipeline.py` | +168 −15 | **v1.5.17** | **索引停滞守卫**：上游把索引跑在线程池里，provider 接受请求但不返回会**永久挂起**。现用心跳 + 超时（600秒）抛 `IndexingStallError`，并防止同库重入。接入首次索引与两条增量索引 |

**Batch 2**

| 文件 | 改动 | 来源版本 | 影响 |
|---|---|---|---|
| `knowledge/add_documents.py` | +29 −1 | **v1.6.9** | **空知识库首次上传**：原来只要没有就绪索引就报 `Knowledge base not initialized`。现区分「**无任何版本=空库，允许引导**」与「**有版本但未就绪=坏索引，仍要求 reindex**」 |
| `services/embedding/adapters/openai_compatible.py` | +41 | v1.5.16 | **`encoding_format` 400 重试**：ModelScope 类网关要求显式传该字段。默认仍省略（SiliconFlow 属于"省略"派），**只有网关明确抱怨时才重试一次** |
| `services/embedding/client.py` | +53 −1 | **v1.5.17** | **进程级发帖节流**：用**线程锁**（非 asyncio 锁——LlamaIndex 用线程池，每线程独立 event loop，asyncio 锁跨 loop 既不互斥还会挂死） |
| `services/rag/.../config.py` | +21 | v1.6.3 | 新增 `VectorIndexConfig`、HNSW 常量 |
| `services/rag/.../vector_store.py` | +35 −4 | v1.6.3 | **FAISS HNSW 可选**。**默认仍是精确 `IndexFlatIP`，行为不变** |

#### 9.6.4 移植上游 v1.6.11 的 B3-8（文档图片 → 视觉模型）

| 文件 | 改动 | 影响 |
|---|---|---|
| `utils/document_images.py` | **新增 603 行** | OOXML/PDF 图片抽取工具（上游原样移植）：预算控制、`[图片 N]` 标记、矢量图/超限跳过统计 |
| `utils/document_extractor.py` | +145 | PDF 按页插入图片标记；DOCX/PPTX 改走**富文本路径**（唯一知道图片位置的路径）；新增 `_embedded_images_for_document()`；**`extract_documents_from_records()` 把抽出的图片作为额外 `type:"image"` 附件记录发出** |

> **机制要点**（很巧妙，值得理解）：抽出的图片**变成普通图片附件记录**，因此**复用了既有的多模态管线**（`services/llm/multimodal.py` → 注入最后一条用户消息），**没有新增任何视觉转发逻辑**。
>
> **护栏**（上游值）：单文档 ≤12 张 / 单图 ≤4MB / **<1200 字节的图视为项目符号或分隔线而跳过** / 单轮 ≤16 张、≤12MB。被跳过的会在文本里说明原因。

#### 9.6.5 这批改动的**行为变化清单**（做回归时重点看）

**行为确实改变的地方**：
1. notebook 路径穿越现在被拒
2. 索引停滞 600 秒后会**报错**而不是永久挂起
3. **空知识库可以首次上传并引导索引**
4. 掌握度 0.8 现在判为"已掌握"（此前判"基础"）
5. 科目下拉菜单向上展开
6. **文档内嵌图片会随消息送进视觉模型**（并在文本里留下 `[图片 N]` 标记）
7. 模型预算耗尽时给出**明确中文错误**，而不是空白 PDF

**行为刻意保持不变的地方**（不要误以为改坏了）：
1. FAISS 默认仍是精确 `IndexFlatIP`（HNSW 需显式开启）
2. `complete()` 的对外契约不变
3. embedding 默认仍**省略** `encoding_format`
4. 节流不引入额外延迟（默认 `batch_delay=0`，锁只做串行化）

---

## 10. 当前服务状态（2026-09-28 22:30）

| 项 | 状态 |
|---|---|
| 后端 `:8001` | ✅ 运行中，200 |
| 前端 `:3782` | ✅ 运行中，200 |
| 数据 | ✅ 6 个科目完好（常微分方程、线性代数、概率论、离散数学、数值分析、复变函数） |
| **运行中的代码版本** | ✅ **已确认是最新**——通过对运行中的后端做 B3-8 功能测试验证（见 11.1） |

---

## 11. 验证方法（如何自己确认一切正常）

### 11.1 验证运行中的后端是否加载了最新代码

有一个很干净的判据：**B3-8 的行为无法被旧代码伪造**。

构造一个内嵌图片的 DOCX（图里写着某个随机字符串），在聊天里上传它，问模型图里写的是什么。**只有加载了 B3-8 的进程**才能把图片从文档里抽出来送进视觉模型。如果模型答对，说明运行中的就是最新代码。

（我最后一次验证：图中写 `OTTER-5182`，模型准确回答 `OTTER-5182`。）

### 11.2 分科目端到端回归

推荐的手工验证顺序（也是我用的）：

1. 新建科目 → 上传讲义到该科知识库 → 等状态 `ready` → 提问，确认**返回引用来源**
2. 错题录入（AI 批改）→ 连续答对 → 确认掌握度与状态**一致**
3. 课堂转写 → 考点检测 → 确认**负向表述被排除**（"这个不考"不该成为考点）→ 确认考点
4. 生成复习指南 PDF → 确认**有内容**（`markdown_tokens > 0`）且中文正常
5. 生成图表报告 → 确认 `chart_count > 0` **且图片真的嵌进了 PDF**
6. 整科导出 ZIP

### 11.3 建议重点复测的新功能

1. **上传带图的 DOCX/PPTX/PDF 到聊天**，问图里内容（B3-8 主场景）
2. **上传带图的讲义到科目知识库**，再针对该科提问图片内容
3. **索引过程中断网**，确认约 10 分钟后**明确报错**而非无限转圈
4. 笔记本 API 传 `../` 类 id，确认被拒绝
5. 掌握度恰好 0.8 的错题显示"已掌握"
6. 模型预算耗尽时看到**明确中文错误**而非空白 PDF

---

## 12. 已知问题与技术债

### 12.1 明确的限制

| 项 | 说明 |
|---|---|
| **上游已领先 14 个 release** | 当前上游 v1.6.11。其中 **v1.6.3 是破坏性重构**（canonical contracts、`/ws/...` 命名空间、前端强类型化），**不建议跟进**——代价极大且会摧毁现有 fork 结构 |
| **Python 版本上限** | 卡在 `<3.14`，依赖链（部分库未适配 3.14） |
| **ruff 噪音** | 14 处上游既有告警，未清理（见 8.6） |
| **50 处改动未提交** | **最大的工程风险**，见 9.6 |
| **embedding key 池未实现** | 见 12.2 |
| **cross-encoder 重排未实现** | 见 12.3 |

### 12.2 有意未实现：embedding 多 key 轮换

上游 v1.5.17 有 key 池轮换（一个 429 就切下一个 key）。**本项目有意未移植**，理由：

- 上游该特性波及 **14 个文件**，同时改 LLM 与 embedding 两侧、配置层（`api_key: str` → `str | list[str]`）、设置界面
- 本项目配置链全程是单字符串（`_as_str()` 解析），设置页也没有多 key 输入
- **当前只有 1 个 SiliconFlow key**，移植后没有任何配置能填充这个池 → **纯死代码**

同一上游修复的**另一半（进程级节流）已实现并生效**。若日后获得多个 key，需要连带改造配置层才能启用轮换。

### 12.3 有意未实现：cross-encoder 重排

上游有本地 cross-encoder 重排。**本项目有意未移植**，理由：

- 需要**新增重型可选依赖** `sentence-transformers`（torch 栈），上游自己也是 opt-in extra
- **更关键**：上游实现是**本地** cross-encoder（`sentence_transformers.CrossEncoder`），**无法使用已有的 SiliconFlow rerank API 模型**（如 `Qwen/Qwen3-Reranker-8B`）

> 💡 若要做重排，**更合适的路径是另写一个走 SiliconFlow rerank API 的实现**——上游没有这条路径，需要自己开发。

---

## 13. 与上游的差距（可移植项，按性价比排序）

以下是我实测评估过、**尚未移植**的上游能力：

| 项 | 上游来源 | 规模 | 依赖 | 评价 |
|---|---|---|---|---|
| **question_bank 工具** | v1.5.15 / v1.6.9 | ~536 行 | 无 | **性价比最高**：单文件工具，直接增强 M3 错题集 |
| **Practice 子系统** | v1.6.9 | ~1834 行（`services/practice/`）+ API 368 行 + 前端 | 无 | **偏大**：等于新建一个子系统 + 新 API + 新前端；与现有 M3 错题集**功能重叠**，建议只取其中 question_bank 部分 |
| **connections + task models** | v1.6.1 | ~2900 行（含前端 1147 行 + `provider_runtime`/`settings` 改动 ~1400 行） | 无 | **风险最高**：改的是**配置 schema**，而本项目已定制 `model_catalog.json` 与设置页，**冲突面很大** |

> 对照上游可用：`git clone --depth 1 --branch v1.6.11 https://github.com/HKUDS/DeepTutor.git /tmp/upstream_dt`
> 版本对比页：https://github.com/HKUDS/DeepTutor/compare/v1.5.13...v1.6.11

### 13.1 已经移植过的上游修复（**不要重复移植**）

以下**已在本项目中生效**，重新移植会冲突：

- DeepSeek flash 的 thinking-off 规则
- `deeptutor.plugins` / `loop_capabilities`
- `CAPABILITY_COMPLETE`
- 密钥文件 `0o600` 权限、配置原子写
- embedding 的 `Retry-After` 处理
- embedding `encoding_format` 的**发送逻辑**（`request_options.py`）
- notebook 路径穿越守卫（v1.6.11）
- 截断响应诊断原语（v1.6.10）
- 索引停滞守卫（v1.5.17）
- 空知识库引导（v1.6.9）
- embedding `encoding_format` 400 重试（v1.5.16）
- 进程级发帖节流（v1.5.17）
- FAISS HNSW（v1.6.3）
- 文档内嵌图片 → 视觉模型（v1.6.11）

---

## 14. 给接任者的行动建议

### 第一优先级

1. **把那 50 处未提交改动分批 commit**（建议按 9.6.1–9.6.4 的四组拆成 4~5 个提交）。这是当前最大的风险。
2. **跑一遍基线测试**，确认从你这里开始时是绿的：
   ```bash
   cd /home/albert/selflearn/selflearn && ./.venv/bin/python -m pytest -q    # 期望 2918 passed
   cd web && node ./scripts/run-node-tests.mjs                              # 期望 403 passed
   cd web && npx tsc --noEmit -p .                                          # 期望 0 错误
   ```
3. **读 9.1–9.6 建立改动心智模型**，特别是 9.6.5 的"行为变化清单"。

### 动手改代码前

- **别碰无关的上游代码**：本项目刻意保持 diff 聚焦。上游代码越少动，将来对照/移植越容易。
- **改前端记得重建**：`next start` 用的是构建产物，改源码后需重新构建（或改用 `deeptutor start --dev`）。
- **改 RAG/embedding 相关要想着重建索引**：向量维度一变就要全量重建，且很慢。
- **用 `data/user/logs/deeptutor.jsonl` 排查问题**：结构化日志，比翻 stdout 高效。

### 如果需要参考上游实现

- 用 `git log 15bf5ad..HEAD` 区分"本项目改的"和"上游的"
- `UPSTREAM.md` 是上游 README 存档，可查上游功能说明
- `AGENTS.md` 描述的两层插件架构（Tools / Capabilities）**仍然适用**，是理解 `deeptutor/core/` 与 `deeptutor/capabilities/` 的好入口

### 关于"偏离清单"的决策风格

本项目此前的决策遵循一个原则，建议延续：**先验证上游修复是否真的适用于本项目的实际配置，再决定是否移植**。9.6.3 中每一项都标注了来源版本和"为何这样改"；12.2 / 12.3 两项则是**经过论证后有意不移植**（因为在本项目配置下会是死代码或不匹配现有服务），而不是遗漏。如果你有不同判断，文档里保留了推理依据供你复核。

---

## 附录 A：关键文件速查

| 我想改… | 去哪 |
|---|---|
| 科目数据模型 | `deeptutor/subjects/store.py` |
| 科目 API | `deeptutor/api/routers/subjects.py` |
| 错题本 / 掌握度 | `deeptutor/subjects/wrong_book.py` |
| 考点检测 | `deeptutor/subjects/exam_detection.py`、`exam_points.py` |
| 科目 LLM 调用（含预算诊断） | `deeptutor/subjects/generation.py` |
| 复习指南 PDF | `deeptutor/services/pdf/review_guide.py` |
| 图表报告 PDF | `deeptutor/services/pdf/report.py` |
| 文档解析 | `deeptutor/utils/document_extractor.py` |
| 文档图片抽取 | `deeptutor/utils/document_images.py` |
| RAG 管线 | `deeptutor/services/rag/pipelines/llamaindex/` |
| agent 循环 | `deeptutor/core/agentic/loop.py`、`labeled_step.py` |
| LLM 调用 | `deeptutor/services/llm/factory.py` |
| embedding | `deeptutor/services/embedding/client.py`、`adapters/openai_compatible.py` |
| 多模态注入 | `deeptutor/services/llm/multimodal.py` |
| 前端聊天页 | `web/app/(workspace)/home/` |
| 前端科目工作台 | `web/app/(workspace)/subjects/` |
| 运行时配置 | `data/user/settings/*.json` |

## 附录 B：认证与密钥来源（**不含密钥本身**）

- 主配置：`data/user/settings/model_catalog.json`（DeepSeek / SiliconFlow / Bocha 的 key 都在这里，明文）
- 原始密钥来源（用户机器）：Windows 桌面 `API keys/ds-api.txt`（含 2 个 DeepSeek key + bocha key），在 WSL 下路径为 `/mnt/c/Users/<用户名>/Desktop/API keys/`
- SiliconFlow key 由用户直接提供，已写入上述配置文件

> 🔴 **安全提醒**：`model_catalog.json` 含明文密钥。**不要**把它提交到公开仓库，也不要贴进 issue / 文档 / 截图。

---

*文档结束。如发现本文档与代码不符，以代码为准，并请顺手修正本文档。*

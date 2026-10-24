# S14 已探索文件与关键片段

本文件由 `.phase1-evidence/reviews/S13-final/build_s14_packet.py` 生成。文件 SHA 对应生成时完整字节；定位片段是原文、行号一基。参考文件只用于定向理解，不获得写权限；实际改动只受 stages.json 当前白名单约束。

## 阶段信息与新增测试

S14：HTTP与WebSocket集成验收；顺序 P1-51, P1-52；契约 C02, C05, C06, C07, C08, C09, C10, C11, C12, C14。范围从 stages.json 动态展开：2 项，现存 0 项，缺失 2 项。缺失项：tests/phase1/test_http_acceptance.py, tests/phase1/test_ws_acceptance.py。

两项预期新增文件是 `tests/phase1/test_http_acceptance.py` 与 `tests/phase1/test_ws_acceptance.py`；本包记录其是否缺失，不预先创建。P1-51/P1-52 的任务内容只用于说明目标，文件/符号范围仍服从阶段白名单。

## 接线与安全测试提示

- `deeptutor.api.main.app` 是正式 FastAPI app，模块导入会执行 runtime settings 初始化与环境导出。不要在 pytest 收集阶段导入后把真实根固定在进程单例中。phase1 `isolated_runtime`/`p1_runtime` 会将 PathService 根重定向到临时目录并启用网络 guard；`helpers.route_client()` 每次构建真实 FastAPI app 并挂载真实 subjects router，但故意不启动后台 lifespan。若场景要求正式 app/lifespan，必须复用独立临时 HOME 的隔离模式，禁止读取本机真实设置。

- HTTP 场景应通过 `TestClient` 的实际 method、path、Form/File、响应头/body 与 outputs 下载路由验证接线。subjects router 覆盖 create/patch/delete、知识资料 multipart、wrong-book check、exam-point 检测、review pack、report、ZIP export；不能只直接调用领域函数。已有 p1_06/p1_07/p1_08/p1_16/p1_38/p1_41/p1_54 是对应路由边界参考。

- 上传拒绝路径穿越/超限并保持旧字节；同名替换后应从新源检索。provider 失败响应使用固定 C02 消息，不能把 cause/provider 原文回显；批改失败应验证相关学习树 bytes 不变。导出需拿返回 URL 再通过 outputs router 下载实际 ZIP，检查 manifest/hash/exclusions；delete 要验证 A/B 隔离及 export/report 忙租约的冲突行为。

- P1-51 流程的验收边界是实际 HTTP CRUD→multipart 资料→批改→考点→复习/报告→ZIP 下载→删除；成功下载文件须可读且清单哈希有效。反例分别验证 provider 失败为非 2xx 且学情 bytes 不变、multipart 路径穿越/超限被拒、同名更新检索使用新文件、删除 A 不修改 B。

- WebSocket handler 为 `/api/v1/ws`。已有 turn runtime 管理 preferences 与请求快照、subject scope/KB mount、replay/subscribe、取消和 regenerate；真实 websocket 测试用 `TestClient.websocket_connect` 并观察 ERROR/DONE 与后续 socket 可用性，而非只调用 runtime 或检查 kwargs。

- P1-52 应在真实 turn 中以同名 A/B/global KB、确定性模型 stub 与工具调用验证：A 的回答和 sources 只含 A 标记；切换/clear/省略/retry 遵 C08；伪造 base/ref 不跨库；科库失败不回退 global 且 terminal failed 可见；图片描述独有标记可检索并归属原文档。

- AgenticChatPipeline 按 server 端 ToolScope/KbRef 组织 RAG 工具与 source provenance；模型提供的 scope/base/ref 不应成为授权依据。PageIndex 当前是 outline/document map，不是 passage search 或 MCP transport。图像描述经 `describe_image_for_index` 生成带原文档来源的 text node；验收应检查 source_file 等出处与独有标记真正可检索。

- 新测试应从现有隔离 fixtures 组合小场景，不自行造新的共享 TestClient/全局 client。外部 provider 使用 stub/loopback fixture，错误/网络失败均须确定性、无真实密钥/供应商。坏对照从通过的正例只改一个目标条件。

## 范围文件哈希

### 阶段范围中已存在文件

| 文件 | SHA-256 | 字节 |
|---|---|---:|

### 只读参考文件

| 文件 | SHA-256 | 字节 |
|---|---|---:|
| `plans/phase1/stages/S14.md` | `39bf7f62b20fcfbb039a3befdfef5978ebfab190e8822e7baa08ac06d4571dee` | 2833 |
| `plans/phase1/cards/P1-51.md` | `0a618fc78dc83d5de0699cbe2d95dcc331df821d87d4ec4b8d2c83666ed4b8c1` | 3710 |
| `plans/phase1/cards/P1-52.md` | `52bc70311b06d9d67d158daffbb223f2d013ea5678db27e94592eee5fd12969e` | 3733 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | 31470 |
| `deeptutor/api/main.py` | `a7a360ff67d59ad31f42d25b64a7a06a2cf7f0b9fbb070063463bceefefa042b` | 14688 |
| `deeptutor/api/subject_route.py` | `c7d58298831a896fc7e2eadcd660b38e1c84c40bd246dfe4074106a869445e9c` | 7058 |
| `deeptutor/core/errors.py` | `a73546175877394d32fe34e4c79f4c05aeb8991237f8267a13d2d61774f69c2e` | 1311 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 16060 |
| `deeptutor/api/routers/subjects.py` | `adae1fb5bfadd9921adec8765e2432b1d8d3b57347afc5ce845da3face9e7816` | 42205 |
| `deeptutor/api/routers/outputs.py` | `ff89210fadad958b5e99efa0fc2955dd02e119f6f06493f49f280701a6719bed` | 1840 |
| `deeptutor/subjects/store.py` | `0a3d04dfdc9bb188a7e0caa1027aaf84c8dfbcabd96e1d9f7f927e165254eeff` | 24650 |
| `deeptutor/api/routers/unified_ws.py` | `5a6bed835c44b05702bc32b0e0c0a1a2c9843a5fc420a1e0f954c1b55e5e7b60` | 16458 |
| `deeptutor/services/session/turn_runtime.py` | `6d138673b31ee786692f8e96c8ccc20a42efa610c14ddfdfc9b1bde5953d42fe` | 128886 |
| `deeptutor/agents/chat/agentic_pipeline.py` | `f10a631e506fd93c5e72e07e5d518e2702bc28e9dd49c5402121607628e2b3b0` | 80935 |
| `deeptutor/tools/rag_tool.py` | `65dd8d551984cc6b757baaf66a27141bfadea91737dac9e9ad1d58ce1533c67c` | 7293 |
| `deeptutor/knowledge/kb_types.py` | `39cc6fcc0d875496ec6747949095429c9ebff27120c4a1392ffc24e219197c5c` | 5917 |
| `deeptutor/services/rag/service.py` | `c720aed1e7c732e6ff90cca62e3976980b3020b687e6411398f2ae1149962c73` | 12244 |
| `deeptutor/services/rag/pipelines/pageindex/pipeline.py` | `adac998cbbb152880245de0374fe88f61aade5cde87a759abdd9830945972237` | 13450 |
| `deeptutor/services/rag/pipelines/pageindex/client.py` | `bf865b664db2c6c1c87668a4a3540ad646c483d369c84a993a578035c7190967` | 4847 |
| `deeptutor/services/rag/pipelines/llamaindex/image_description.py` | `6cbe985b58da4289fe69fdb2d4f4808a581c1de8917b2ec2aaebc3c33c0f2480` | 27473 |
| `tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | 2376 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 49819 |
| `tests/api/test_unified_ws_turn_runtime.py` | `796074d768bc0f02719d6fc19067bac1dde96830d9fd09c63f9d791eff54dba5` | 42003 |
| `tests/phase1/test_p1_06.py` | `0587c43ea7424e4760114a302433abdb8af54d235a81f150adbc03b2fe85cae6` | 29047 |
| `tests/phase1/test_p1_07.py` | `73a1e571a79c431ecd806349570bc786d33b640ef36db59613afbc4cab8f05c1` | 28067 |
| `tests/phase1/test_p1_08.py` | `799208c6f124b0d82046c3454bce72f75700e258383e1f52bf37b18c6a06fd33` | 42041 |
| `tests/phase1/test_p1_16.py` | `445e929241719536e7a9acf3577a28f1616a14fca2e7cec2c5b6f12bd5449a94` | 32777 |
| `tests/phase1/test_p1_22.py` | `97a5ce4a99552761adc4e279d5fc08fed5e597f2590c65d1635786a18cca135b` | 23885 |
| `tests/phase1/test_p1_23.py` | `bb6a4425316afd62929856717d63a29add2ffb0adb504a7c3b463e0ac23022a0` | 27424 |
| `tests/phase1/test_p1_24.py` | `1dc380fedb4c832549b2811b72b28972086248cbcd25a22a62993698e5cf6d51` | 17242 |
| `tests/phase1/test_p1_35.py` | `862ac3606061d130cf0e5c712ab41508d323c8753158889663edadaa135ecff3` | 22331 |
| `tests/phase1/test_p1_38.py` | `6c087ba156f5e64128481e496e4a9cef744ae395a8aa1ebc9cdc794845b89a12` | 17706 |
| `tests/phase1/test_p1_41.py` | `dcaf63a4340cc8b5be5d65401335680a6fdeb01416e585b68971c81d726b4a38` | 12235 |
| `tests/phase1/test_p1_46.py` | `16cf9e61836b0f90f1c22bab205a6531c1de89f71ca6a99844940d8105a601a6` | 11537 |
| `tests/phase1/test_p1_54.py` | `7b7ececfcb82d953a19cfc4ec65d267a178ff20c0535f23417bd9b66d15ccc74` | 14376 |

## 原文定位片段

### 1. `plans/phase1/stages/S14.md:1-1`（定位词 `# S14`）

```text
# S14：HTTP与WebSocket集成验收
```

### 2. `plans/phase1/cards/P1-51.md:1-7`（定位词 `# P1-51`）

```text
# P1-51：HTTP现有功能闭环验收

状态：planned；类型：python；审阅风险：gate。依赖：P1-49, P1-50, P1-54。

## 目标

从真实路由和临时磁盘验证CRUD→资料→批改→考点→复习→报告→ZIP→删除。
```

### 3. `plans/phase1/cards/P1-52.md:1-7`（定位词 `# P1-52`）

```text
# P1-52：WebSocket科目检索与失败闭环验收

状态：planned；类型：python；审阅风险：gate。依赖：P1-49, P1-22, P1-23, P1-24, P1-46。

## 目标

通过/api/v1/ws真实turn验证作用域/工具/来源和失败事件，不只测试kwargs。
```

### 4. `plans/phase1/DATA_CONTRACTS.md:17-25`（定位词 `## C02：错误与各入口的一致性`）

```text
- 不承诺多文件跨崩溃数据库事务。学情的一个业务提交应写一个权威集合；知识点关联为可重建派生数据。写错误或生成失败不能以“派生数据先存了”当作成功。导出按快照规约另行验证。

## C02：错误与各入口的一致性

subject HTTP 业务错误保留旧 `detail: string`，增加结构化 `error`。不把 detail 从字符串改成对象，不改全局 FastAPI 校验形状。

```json
{"detail":"批改服务返回的结果无法解析，请重试。","error":{"code":"invalid_model_output","message":"批改服务返回的结果无法解析，请重试。","retryable":true}}
```
```

### 5. `plans/phase1/DATA_CONTRACTS.md:62-70`（定位词 `## C05：批改与错题`）

```text
不自动无限重试，不继续渲染半篇报告，不提高 16000 上限作为唯一修复。计费/上下文等上游 complete 契约保持。模型 JSON 消费者必须解析一个完整对象（允许包围代码围栏/思考标签）；不使用贪婪抓取后默认 wrong/空列表，不把数组/null/数字当对象。

## C05：批改与错题

模型数据：`{"verdict":"correct|partial|wrong","feedback":"string"}`；字段必须存在，verdict trim/lower 后精确枚举，feedback 必须字符串。未知模型字段可忽略；缺字段/错误类型/非法 enum/多个候选 JSON 对象均 invalid_model_output。

成功 HTTP 响应保持 verdict/feedback/correct/entry，增加 saved:boolean。已有同题 entry：一次成功批改写一次 attempt；partial 在本阶段仍映射 correct=false，不重设掌握公式。新题正确：不创建“错题”，entry=null、saved=false；新题 partial/wrong：创建 entry 和首次 attempt 在一次集合更新提交中完成，saved=true。失败和解析失败：现有 wrong_book 字节不变；不创建新 entry、不计次数、不改掌握度。

attempt 的 correct 必须真实布尔。entry 无 attempts：mastery=0、status=untracked；有 attempts：沿用三位舍入和现有 classify。不能因 0.7999999999999 而把显示 0.8 判 basic。反馈不替换参考答案，不把模型的错误详情写进 analysis。
```

### 6. `plans/phase1/DATA_CONTRACTS.md:70-78`（定位词 `## C06：考点检测`）

```text
attempt 的 correct 必须真实布尔。entry 无 attempts：mastery=0、status=untracked；有 attempts：沿用三位舍入和现有 classify。不能因 0.7999999999999 而把显示 0.8 判 basic。反馈不替换参考答案，不把模型的错误详情写进 analysis。

## C06：考点检测

模型输出只接受完整 `{"points": [...]}`；[] 是合法“未发现”，缺 points、非法 JSON、错误 level/字段类型属于失败。检测 level 仅 explicit/emphasis，manual 历史 inferred 可读。每候选 content/evidence/kp 字符串，content/evidence trim 非空；evidence 必须是转写中的直接引用（只允许空白归一化匹配，不做语义相似替代）。

负向证据中的直接短语“不考/不会考/不用重点看/了解即可”等按现有提示词规则排除，响应 warnings 说明排除数量；这是确定性文字护栏，不承诺完整语义理解。其余不存在原文的 evidence 使整轮 invalid_model_output，整轮不入库；不能部分保存后才失败。

成功响应保留 version/detected/stored/raw，增加 warnings；detected 等于实际保存候选数，raw 为既有模型正文，不含思考/供应商诊断。confirmed 保留旧政策：auto_confirm=true 或 validated explicit；emphasis 默认 false。同科/同学期/content/evidence 归一化完全相同候选重复检测不重复追加，返回复用条目。批量写一次集合。模型失败不能返回 200+detected=0。
```

### 7. `plans/phase1/DATA_CONTRACTS.md:80-88`（定位词 `## C07：资料上传与索引源`）

```text
term 未提供或为空字符串时采用 subject.term；聊天考点摘要按当前学期过滤。subject.term 空时可以显示所有已确认点，但标题写“已确认考点”，不能声称本学期。不新增考试预测器。

## C07：资料上传与索引源

```json
{"operation":"index","kb_name":"assignment-kb","type":"assignment","files":["notes.txt"],"task_id":"...","message":"已保存，正在建立索引"}
```

```json
```

### 8. `plans/phase1/DATA_CONTRACTS.md:100-108`（定位词 `## C08：聊天科目作用域与知识库标识`）

```text
并发初始化/重建：同库只允许一个活跃任务；600 秒无进度守卫语义保留，无进度后 API 报错，worker 不被当成已终止；活跃 worker 未退出仍禁止同库重入。任务状态必须能区分错误、索引 ready、重建进行中；不改核心引擎版本协议，不强制替换 embedding 模型。

## C08：聊天科目作用域与知识库标识

输入 subject_id 采用三态：未提供沿用当前 session.preferences.subject_id，null/空字符串明确清空，非空字符串设置。支持顶层字段及旧 config.subject_id；两者同时提供且不相等为 invalid_input。不能用 `a or b` 丢掉清空值。验证发生在创建 turn/写用户消息前。新 session 无值即 null；切换 session 不继承另一 session 的选择。

复用已存在 preferences_json 保存 subject_id，不新增 SQLite 列或配置数据库，不改变 session store API。运行 metadata 带 resolved subject_id，request_snapshot 保存本轮 resolved 值，以便重试/再生成使用原作用域；UI 恢复 preferences 后才允许发送。被删科目的历史会话提示 subject_not_found，用户显式清空后恢复普通聊天，不静默选别科。

subject KB wire id：`subject:kb:<subject_id>:<kb_name>`。subject_id/kb_name 均不含冒号；中文按字符串存储，URL 路径各段单独编码。既有 admin:kb:/user:kb: 保留。不修改知识库磁盘名字。
```

### 9. `plans/phase1/DATA_CONTRACTS.md:116-124`（定位词 `## C09：图片与索引覆盖`）

```text
不能因科库检索失败悄悄改用全局 KB 回答；WS/工具失败必须可见。全局用户访问规则保持。PageIndex 的概览路径在 C13 单列，不宣称本阶段新增深度 MCP 检索。

## C09：图片与索引覆盖

保留支持多模态 embedding 的 ImageNode 路径；文本 embedding 的现有默认配置不再直接跳过所有图片，而使用：现有 parser/image asset → 根据 vision_strategy 选择视觉模型 → 生成事实性描述/OCR → 普通文本 Document。不更换 embedding 模型/维度，不生成伪 image vector，不在 metadata 存 base64。

描述文本前缀标明来自图像，携带 source file、可用的 page/location、图片相对 asset 标识、content_kind=image_description。仅记录 parser 确实提供的位置，缺页码为 null，不猜页码。描述不为空才建立文本节点；主 LLM 检测不支持时可走独立 vision；dedicated_only 没配置时明确错误/覆盖降级，不偷用主模型。main optimistic image 调用失败遵循已有降级策略并计入 coverage。

coverage 是加法式 metadata：text_sources、images_seen、images_indexed、images_skipped，以及 skip_reasons 计数（parser_no_assets / vision_unavailable / vision_failed / budget / unsupported_image）。parser 不提供图时只说“未提取/未验证”，不能说 0 张且覆盖完整。有正文且图片跳过可继续文本索引，但公开 coverage warning；只有图片且全部失败、没有任何节点时初始化失败，不标 ready。
```

### 10. `plans/phase1/DATA_CONTRACTS.md:126-134`（定位词 `## C10：知识点掌握证据与关联`）

```text
抽图预算沿用 document_images 现有常量：每文档 12 张、单图 4MB、<1200 字节跳过；聊天单轮 16 张/12MB。索引每文档沿用相同上限并记录跳过，不引入无界全图调用。缓存、并行图片描述、批量 OCR 与全量真实知识库重建不属于本阶段。

## C10：知识点掌握证据与关联

entry 层保持 C05 的 0/untracked。聚合 knowledge point 无有作答证据的关联错题时 mastery=null、evidence_count=0、assessment_status=unassessed；有证据时沿用有效关联 entry mastery 均值（三位），assessment_status=assessed。没有证据不等于已掌握。旧接口新增字段而不重写历史 stored mastery；模板/前端消费 null 显示“未评估”，不能显示 None/NaN。

知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物
```

### 11. `plans/phase1/DATA_CONTRACTS.md:132-140`（定位词 `## C11：报告、执行与产物`）

```text
知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
```

### 12. `plans/phase1/DATA_CONTRACTS.md:156-164`（定位词 `## C12：导出内容与完整性`）

```text
模型/渲染/图失败时无正式 URL；私有失败诊断可保留，但不覆盖旧 completed 报告。API 与 ToolResult 都适用 C02。报告生成不承诺自动从讲义检索/数学形式化证明。

## C12：导出内容与完整性

保留 `GET /subjects/{id}/export`；用 uuid 导出文件名，响应保留 url 并增加 export_id/schema_version。ZIP schema_version=1，内容固定：

```text
manifest.json                        版本、subject元信息、文件清单、覆盖/排除声明
subject.json                         index.json 中该 subject 的完整记录
```

### 13. `plans/phase1/DATA_CONTRACTS.md:183-191`（定位词 `## C14：证据与阶段验收`）

```text
- 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。

## C14：证据与阶段验收（2026-10-11修订）

每张小卡仍需正向和独立反向行为证据；合法负例从已证明有效的base只改一个字段/故障点。高风险用一个针对性坏对照确认断言捕获真实效果，禁止只看源码contains或mock自证。该义务不要求每卡交付一份独立人工报告。

每阶段一个执行会话，阶段内按stages.json既定顺序串行卡。报告/审查为阶段粒度，规则见STAGE_WORKFLOW.md。新阶段使用StageReport schema：stage_id/status/baseline_id/card_results/commands/scope_check/real_data_unchanged/limitations。card_results含卡ID、目标、修改路径、断言、命令定位和限制；commands保存实际命令、cwd、exit、共享execution.log行号，不能只写摘要“通过”。

单元状态verified_local表示本地验证；阶段末由协调者独立复核并写review.json的accepted，执行者不能自签。历史P1-00/completion.json保持原样，协调修补/签收另存reviews/P1-00；旧Completion schema继续兼容明确单卡调用，不强制后续每卡创建文件。
```

### 14. `deeptutor/api/main.py:101-109`（定位词 `async def lifespan(app: FastAPI):`）

```text

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    Gracefully handle startup and shutdown events, avoid CancelledError
    """
    # Execute on startup
    logger.info("Application startup")
```

### 15. `deeptutor/api/main.py:191-199`（定位词 `app = FastAPI(`）

```text


app = FastAPI(
    title="DeepTutor API",
    version="1.0.0",
    lifespan=lifespan,
    # Disable automatic trailing slash redirects to prevent protocol downgrade issues
    # when deployed behind HTTPS reverse proxies (e.g., nginx).
    # Without this, FastAPI's 307 redirects may change HTTPS to HTTP.
```

### 16. `deeptutor/api/main.py:398-406`（定位词 `app.include_router(unified_ws.router`）

```text
# Unified WebSocket endpoint — auth is checked inside the handler (WebSockets
# cannot use FastAPI dependencies in the standard way)
app.include_router(unified_ws.router, prefix="/api/v1", tags=["unified-ws"])

# Quiz AI-judge WebSocket — same caveat as unified_ws above; auth is checked
# inside the handler so the WS upgrade isn't rejected by an HTTP-style dep.
app.include_router(quiz_judge.router, prefix="/api/v1", tags=["quiz-judge"])


```

### 17. `deeptutor/api/subject_route.py:144-152`（定位词 `class SubjectRoute(APIRoute):`）

```text


class SubjectRoute(APIRoute):
    """``APIRoute`` that turns subject/storage/LLM failures into C02 payloads."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def subject_error_boundary(request: Request) -> Response:
```

### 18. `deeptutor/api/subject_route.py:147-155`（定位词 `def get_route_handler(`）

```text
    """``APIRoute`` that turns subject/storage/LLM failures into C02 payloads."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def subject_error_boundary(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
```

### 19. `deeptutor/core/errors.py:8-16`（定位词 `class DeepTutorError(Exception):`）

```text


class DeepTutorError(Exception):
    """Base class for all application errors in DeepTutor."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
```

### 20. `deeptutor/core/errors.py:28-36`（定位词 `class ValidationError(DeepTutorError):`）

```text


class ValidationError(DeepTutorError):
    """Raised when input validation fails."""

    pass


class ServiceError(DeepTutorError):
```

### 21. `deeptutor/subjects/errors.py:181-189`（定位词 `class SubjectOperationError(Exception):`）

```text


class SubjectOperationError(Exception):
    """科目业务错误：对外可安全投影的异常。

    对外字段（``message`` / ``http_status`` / ``retryable``）**永远**取自
    :data:`ERROR_SPECS` 中该 code 的固定规格：

    * 调用方传入的 ``message`` 不会成为对外消息——即使它看起来"安全"；
```

### 22. `deeptutor/subjects/errors.py:332-340`（定位词 `def map_subject_exception(`）

```text


def map_subject_exception(exc: BaseException) -> SubjectOperationError:
    """把服务端异常映射成 C02 投影；未知异常安全兜底为 ``internal_error``。

    顺序很重要：``LLMReasoningBudgetExhausted`` 是 ``LLMProviderError`` 的子类，
    而 ``LLMEmptyResponseError`` **不是** ``LLMProviderError`` 的子类，两者都必须
    在各自的基类之前判断。

```

### 23. `deeptutor/subjects/errors.py:391-399`（定位词 `def to_http_payload(`）

```text


def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}


def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
    """WS terminal error / DONE failed 的 metadata 片段。"""
```

### 24. `deeptutor/subjects/errors.py:396-404`（定位词 `def to_ws_error_metadata(`）

```text


def to_ws_error_metadata(error: SubjectOperationError) -> dict[str, Any]:
    """WS terminal error / DONE failed 的 metadata 片段。"""
    return to_error_dict(error)


def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
    """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。
```

### 25. `deeptutor/api/routers/subjects.py:81-89`（定位词 `async def list_subjects(`）

```text

@router.get("")
async def list_subjects(_: None = Depends(require_auth)):
    return {"subjects": store.load_subjects()}


@router.post("")
async def create_subject(
    name: str = Form(...),
```

### 26. `deeptutor/api/routers/subjects.py:86-94`（定位词 `async def create_subject(`）

```text

@router.post("")
async def create_subject(
    name: str = Form(...),
    description: str = Form(""),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    if not name.strip():
```

### 27. `deeptutor/api/routers/subjects.py:99-107`（定位词 `async def patch_subject(`）

```text

@router.patch("/{subject_id}")
async def patch_subject(
    request: Request,
    subject_id: str,
    description: str = Form(None),
    term: str = Form(None),
    _: None = Depends(require_auth),
):
```

### 28. `deeptutor/api/routers/subjects.py:139-147`（定位词 `async def delete_subject(`）

```text

@router.delete("/{subject_id}")
async def delete_subject(subject_id: str, _: None = Depends(require_auth)):
    """Delete this subject's learning + public trees and only then its registry.

    The synchronous deletion (validation, both trees, registry write) holds an
    exclusive activity lease; it runs off-loop and a busy/failed deletion never
    reports ``deleted``.
    """
```

### 29. `deeptutor/api/routers/subjects.py:216-224`（定位词 `async def upload_subject_knowledge(`）

```text

@router.post("/{subject_id}/knowledge/upload")
async def upload_subject_knowledge(
    subject_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    type: str = Form("auto"),
    _: None = Depends(require_auth),
):
```

### 30. `deeptutor/api/routers/subjects.py:602-610`（定位词 `async def check_answer(`）

```text

@router.post("/{subject_id}/wrong-book/check")
async def check_answer(
    subject_id: str,
    question: str = Form(...),
    student_answer: str = Form(...),
    reference_answer: str = Form(""),
    kp: str = Form(""),
    _: None = Depends(require_auth),
```

### 31. `deeptutor/api/routers/subjects.py:702-710`（定位词 `async def detect_exam_points(`）

```text

@router.post("/{subject_id}/exam-points/detect")
async def detect_exam_points(
    subject_id: str,
    transcript: str = Form(...),
    term: str = Form(""),
    source: str = Form("lecture"),
    auto_confirm: bool = Form(False),
    _: None = Depends(require_auth),
```

### 32. `deeptutor/api/routers/subjects.py:985-993`（定位词 `async def generate_review_pack(`）

```text

@router.post("/{subject_id}/review-pack")
async def generate_review_pack(
    subject_id: str,
    format: str = Form("pdf"),
    term: str = Form(""),
    _: None = Depends(require_auth),
):
    """Generate a printable review guide from exam points + wrong book.
```

### 33. `deeptutor/api/routers/subjects.py:1049-1057`（定位词 `async def generate_subject_report(`）

```text

@router.post("/{subject_id}/report")
async def generate_subject_report(
    subject_id: str,
    title: str = Form(...),
    requirements: str = Form(""),
    ode_rhs: str = Form(""),
    _: None = Depends(require_auth),
):
```

### 34. `deeptutor/api/routers/subjects.py:1088-1096`（定位词 `async def export_subject_data(`）

```text

@router.get("/{subject_id}/export")
async def export_subject_data(subject_id: str, _: None = Depends(require_auth)):
    """Snapshot the current subject into a verified ZIP and return its URL.

    The heavy snapshot/compression runs in a worker thread and only prepares a
    private file; this live request commits the public name after the await.
    If the request is cancelled, the preparation is discarded when its thread
    finishes: no public ZIP and no URL from this attempt survive.
```

### 35. `deeptutor/api/routers/outputs.py:39-47`（定位词 `async def read_output(`）

```text

@router.api_route("/{output_path:path}", methods=["GET", "HEAD"])
async def read_output(
    output_path: str,
    _auth: TokenPayload | None = Depends(require_auth),
) -> FileResponse:
    """Serve one allowlisted artifact from the authenticated user's workspace."""
    path = _resolve_output(_request_path_service(), output_path)
    return FileResponse(path)
```

### 36. `deeptutor/subjects/store.py:115-123`（定位词 `def current_subject_paths(`）

```text


def current_subject_paths() -> PathService:
    """The **current user's** ``PathService``, resolved strictly (C01).

    :func:`deeptutor.services.path_service.get_path_service` wraps this in a
    ``try/except`` that falls back to the default (admin) instance. That is the
    right thing for best-effort display paths and exactly the wrong thing for
    learner data: if the current scope cannot be resolved, subject storage must
```

### 37. `deeptutor/subjects/store.py:351-359`（定位词 `def create_subject(`）

```text


def create_subject(name: str, description: str = "", term: str = "") -> dict:
    """Create a subject and its data directory.

    Ordering is deliberate: the id is chosen, the whole tree is **prepared**,
    and only then is the single registry write committed. A preparation failure
    therefore never publishes a registry entry — no "publish, then try to write
    it back" rollback.
```

### 38. `deeptutor/subjects/store.py:479-487`（定位词 `def delete_subject(`）

```text


def delete_subject(subject_id: str) -> bool:
    """Delete the current user's learning + public trees, then the registry.

    The exclusive activity lease covers validation, both removals and the
    registry write, so an upload/index/report/review/export cannot be running
    while its subject disappears. Any symlink anywhere in either tree is
    refused *before* the first byte is removed. A partial cleanup is reported
```

### 39. `deeptutor/api/routers/unified_ws.py:46-54`（定位词 `async def unified_websocket(`）

```text

@router.websocket("/ws")
async def unified_websocket(ws: WebSocket) -> None:
    from deeptutor.api.routers.auth import ws_auth_failed, ws_require_auth
    from deeptutor.multi_user.context import reset_current_user

    user_token = await ws_require_auth(ws)
    if user_token is ws_auth_failed:
        return
```

### 40. `deeptutor/api/routers/unified_ws.py:80-88`（定位词 `async def reject_subject_error(`）

```text
            pass

    async def reject_subject_error(
        exc: BaseException, *, session_id: str, reason: bool = False
    ) -> None:
        """Terminal rejection envelope for a subject-scope/storage failure.

        The client already renders terminal errors, so the *shape* stays exactly
        what the historical ``RuntimeError`` branches send (``session_id``, empty
```

### 41. `deeptutor/services/session/turn_runtime.py:288-296`（定位词 `def mount_turn_knowledge_bases(`）

```text


def mount_turn_knowledge_bases(
    explicit_refs: Sequence[Any] | None, subject_id: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    """This turn's KB mount set and the degradations that kept one out (C08).

    The mounted set is the user's explicit references **plus every ready KB of
    the current subject** — stable, deduplicated, server-resolved. Nothing is
```

### 42. `deeptutor/services/session/turn_runtime.py:426-434`（定位词 `def resolve_subject_scope(`）

```text


def resolve_subject_scope(
    requested: Any, stored: Any, *, validate: bool = True
) -> str | None:
    """Turn the three-state request plus the session preference into one value.

    Omitted keeps the session's stored subject (including its ``None``), an
    explicit ``None``/``""`` clears it, and a non-empty value must be a valid
```

### 43. `deeptutor/services/session/turn_runtime.py:1009-1017`（定位词 `async def start_turn(`）

```text
            ) from exc

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        capability = str(payload.get("capability") or "chat")
        if not payload.get("language"):
            from deeptutor.services.settings.interface_settings import (
                get_response_language,
            )

```

### 44. `deeptutor/services/session/turn_runtime.py:1483-1491`（定位词 `async def subscribe_turn(`）

```text
        return True

    async def subscribe_turn(
        self,
        turn_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        backlog = await self.store.get_turn_events(turn_id, after_seq=after_seq)
        last_seq = after_seq
```

### 45. `deeptutor/services/session/turn_runtime.py:1436-1444`（定位词 `async def cancel_turn(`）

```text
        return await self.start_turn(payload)

    async def cancel_turn(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
        if execution is None or execution.task is None or execution.task.done():
            turn = await self.store.get_turn(turn_id)
            if turn is None or turn.get("status") != "running":
                return False
```

### 46. `deeptutor/agents/chat/agentic_pipeline.py:281-289`（定位词 `class AgenticChatPipeline:`）

```text


class AgenticChatPipeline:
    """Run chat as one exploring agent loop followed by a respond stage."""

    def __init__(
        self,
        language: str = "en",
        *,
```

### 47. `deeptutor/agents/chat/agentic_pipeline.py:606-614`（定位词 `def _tool_scope(`）

```text
        self._deferred_pool = list(view.pool)

    def _tool_scope(self, context: UnifiedContext) -> ToolScope:
        """Per-turn policy inputs for the provider layer."""
        raw_filter = context.metadata.get("mcp_tools_filter")
        # NOTE: upstream also passed
        # ``implicit_provider_ids={PAGEINDEX_SERVER_NAME} if self._pageindex_docs ...``
        # to auto-authorise the PageIndex MCP server when a PageIndex KB was
        # attached. Two things removed that: the M0 trim dropped MCP (and the
```

### 48. `deeptutor/agents/chat/agentic_pipeline.py:1305-1313`（定位词 `def _retrieve_kb_seed_block(`）

```text
    # ---- KB seed ---------------------------------------------------------

    async def _retrieve_kb_seed_block(
        self,
        context: UnifiedContext,
        stream: StreamBus,
    ) -> str:
        # Seed every selected KB except those owned by an exclusive capability
        # (an Obsidian vault is read agentically via its own tools, not seeded).
```

### 49. `deeptutor/agents/chat/agentic_pipeline.py:1712-1720`（定位词 `def _prepare_kb_manifests(`）

```text
        )

    async def _prepare_kb_manifests(self, context: UnifiedContext) -> None:
        """Read the attached KBs' document inventories once per turn.

        Retrieval cannot answer "how many files are in here" — the passages it
        returns say nothing about the size of the collection they came from. The
        inventory is a filesystem fact, so it is read here (off the event loop,
        one directory walk per KB) and rendered into the system prompt, which
```

### 50. `deeptutor/agents/chat/agentic_pipeline.py:630-638`（定位词 `def _pageindex_doc_maps(`）

```text
        )

    def _pageindex_doc_maps(self, context: UnifiedContext) -> dict[str, dict[str, Any]]:
        """wire ref -> ``{name, documents: {file: doc_id}}`` for PageIndex KBs.

        The KB is resolved through the **same** subject-scoped resolver the rag
        tool uses (never the old global one), so a subject library and a global
        library with the same name cannot be confused here either.
        """
```

### 51. `deeptutor/tools/rag_tool.py:32-40`（定位词 `async def rag_search(`）

```text


async def rag_search(
    query: str,
    kb_name: str,
    provider: Optional[str] = None,
    kb_base_dir: Optional[str] = None,
    event_sink=None,
    *,
```

### 52. `deeptutor/tools/rag_tool.py:135-143`（定位词 `async def initialize_rag(`）

```text


async def initialize_rag(
    kb_name: str,
    documents: List[str],
    provider: Optional[str] = None,
    kb_base_dir: Optional[str] = None,
    **kwargs,
) -> bool:
```

### 53. `deeptutor/knowledge/kb_types.py:88-96`（定位词 `def is_connected_kb(`）

```text


def is_connected_kb(entry: Any) -> bool:
    """True for pointer KBs whose data lives outside ``data/knowledge_bases``."""
    return isinstance(entry, dict) and entry.get("type") in CONNECTED_KB_TYPES


def supports_local_raw_files(entry: Any) -> bool:
    """Whether the KB owns a DeepTutor-managed local ``raw/`` directory.
```

### 54. `deeptutor/knowledge/kb_types.py:103-111`（定位词 `def external_root_of(`）

```text


def external_root_of(entry: Any) -> str | None:
    """Absolute path a connected KB points at, or ``None`` for ordinary KBs.

    ``linked`` KBs store it under ``external_path``; ``obsidian`` vaults under
    the older ``vault_path`` field. One accessor so callers don't care which.
    """
    if not isinstance(entry, dict):
```

### 55. `deeptutor/services/rag/service.py:21-29`（定位词 `class RAGService:`）

```text


class RAGService:
    """Unified RAG service that routes to a KB's bound pipeline.

    The provider is resolved per knowledge base: an explicit ``provider`` passed
    to the constructor wins (used at create time); otherwise it is read from
    DeepTutor's authoritative KB config, with metadata as a legacy fallback.
    """
```

### 56. `deeptutor/services/rag/service.py:82-90`（定位词 `async def search(`）

```text
        return await pipeline.add_documents(kb_name=kb_name, file_paths=file_paths, **kwargs)

    async def search(
        self,
        query: str,
        kb_name: str,
        event_sink=None,
        **kwargs,
    ) -> Dict[str, Any]:
```

### 57. `deeptutor/services/rag/pipelines/pageindex/pipeline.py:55-63`（定位词 `class PageIndexPipeline:`）

```text


class PageIndexPipeline:
    """Index/retrieve KB content via the hosted PageIndex service."""

    def __init__(
        self,
        kb_base_dir: Optional[str] = None,
        *,
```

### 58. `deeptutor/services/rag/pipelines/pageindex/pipeline.py:165-173`（定位词 `async def search(`）

```text
    RETRIEVAL_KIND = "outline"

    async def search(self, query: str, kb_name: str, **_kwargs) -> Dict[str, Any]:
        """Return each document's tree outline (titles / pages / summaries).

        The deprecated REST retrieval endpoint is gone and this build has no
        PageIndex MCP tools: what remains is the *outline* — the documents' real
        structure (titles, pages, per-section summaries) — which is shallow but
        honest grounding for a programmatic caller. Every result therefore
```

### 59. `deeptutor/services/rag/pipelines/pageindex/pipeline.py:287-295`（定位词 `def document_map(`）

```text
        return text, sources

    def document_map(self, kb_name: str) -> dict[str, str]:
        """file name -> cloud doc_id for the KB's current manifest.

        Used by the chat layer to inject the doc list into the system prompt.
        """
        kb_dir = resolve_kb_dir(self.kb_base_dir, kb_name)
        manifest = storage.read_manifest(resolve_storage_dir_for_read(kb_dir, None))
```

### 60. `deeptutor/services/rag/pipelines/pageindex/client.py:34-42`（定位词 `class PageIndexClient:`）

```text


class PageIndexClient:
    """Stateless wrapper over the PageIndex REST API.

    A fresh :class:`httpx.AsyncClient` is opened per call so the object is safe
    to construct once and reuse across requests without managing a connection
    lifecycle.
    """
```

### 61. `deeptutor/services/rag/pipelines/pageindex/client.py:89-97`（定位词 `async def get_document(`）

```text
        return str(doc_id)

    async def get_document(self, doc_id: str, *, summary: bool = False) -> dict[str, Any]:
        """GET /doc/{id}/ — status plus the document tree in ``result``.

        ``summary=True`` asks the API to include per-node summaries.
        """
        params = {"summary": "true"} if summary else None
        async with self._open() as client:
```

### 62. `deeptutor/services/rag/pipelines/llamaindex/image_description.py:151-159`（定位词 `class ImageDescription(`）

```text

@dataclass(frozen=True, eq=False)
class ImageDescription(Mapping[str, Any]):
    """The fixed ``ImageDescription`` projection.

    Frozen *and* mapping-like: ``result.text``, ``result["text"]``,
    ``dict(result)`` and ``dataclasses.asdict(result)`` all yield the same
    seven fields, and equality works against another instance or a plain dict.
    """
```

### 63. `deeptutor/services/rag/pipelines/llamaindex/image_description.py:606-614`（定位词 `async def describe_image_for_index(`）

```text


async def describe_image_for_index(
    image_path: str | os.PathLike[str],
    *,
    source_file: str,
    page: int | None = None,
    location: str | None = None,
    asset_ref: str | None = None,
```

### 64. `tests/phase1/conftest.py:26-34`（定位词 `def p1_runtime(`）

```text

@pytest.fixture
def p1_runtime(tmp_path: Path) -> Iterator[Path]:
    """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root


@pytest.fixture
```

### 65. `tests/phase1/conftest.py:33-41`（定位词 `def p1_subjects(`）

```text

@pytest.fixture
def p1_subjects(p1_runtime: Path) -> dict:
    """在隔离根下建 A / B / global 三处**同名**知识库，各带独立标记。"""
    subjects = helpers.make_same_name_kbs(p1_runtime)
    subjects["_admin_root"] = p1_runtime
    return subjects


```

### 66. `tests/phase1/conftest.py:71-76`（定位词 `def p1_route_client(`）

```text

@pytest.fixture
def p1_route_client(p1_runtime: Path) -> Iterator[object]:
    """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
    with helpers.route_client() as client:
        yield client
```

### 67. `tests/phase1/helpers.py:507-515`（定位词 `def isolated_runtime(`）

```text

@contextlib.contextmanager
def isolated_runtime(
    tmp_path: Path,
    *,
    guard_network: bool = True,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
    **kwargs: Any,
```

### 68. `tests/phase1/helpers.py:1129-1137`（定位词 `def build_route_app(`）

```text


def build_route_app():
    """构造只含真实科目路由的轻量 app，**不挂**后台 lifespan。

    用带完整 lifespan 的 ``deeptutor.api.main.app`` 做普通路由测试，会把 EventBus/cron/
    LLM 锚定在启动时的根上并跨隔离作用域存活。完整 lifespan 的验收放在独立子进程里
    （:func:`full_lifespan_probe`）。
    """
```

### 69. `tests/phase1/helpers.py:1146-1154`（定位词 `def route_client(`）

```text

@contextlib.contextmanager
def route_client() -> Iterator[Any]:
    """在当前隔离作用域内创建并**关闭**一个真实路由客户端。"""
    if _ACTIVE_ROOT.get() is None:
        raise IsolationError("route_client requires an active isolated_runtime scope")
    from fastapi.testclient import TestClient

    with TestClient(build_route_app()) as client:
```

### 70. `tests/api/test_unified_ws_turn_runtime.py:965-973`（定位词 `def _unified_ws_app(`）

```text


def _unified_ws_app():
    """只挂真实 unified WS 路由的轻量 app（不经完整 lifespan）。"""
    from fastapi import FastAPI

    from deeptutor.api.routers import unified_ws

    app = FastAPI()
```

### 71. `tests/api/test_unified_ws_turn_runtime.py:991-999`（定位词 `def test_unified_ws_projects_subject_errors_and_keeps_the_socket_usable(`）

```text


def test_unified_ws_projects_subject_errors_and_keeps_the_socket_usable(ws_home) -> None:
    from fastapi.testclient import TestClient

    with TestClient(_unified_ws_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
```

### 72. `tests/api/test_unified_ws_turn_runtime.py:1041-1049`（定位词 `def test_unified_ws_regenerate_refusal_keeps_the_old_assistant_message(`）

```text


def test_unified_ws_regenerate_refusal_keeps_the_old_assistant_message(ws_home) -> None:
    from fastapi.testclient import TestClient

    from deeptutor.services.session import get_turn_runtime_manager
    from deeptutor.subjects import store as subject_store

    subject = helpers.make_subject(ws_home, "科目A")
```

### 73. `tests/phase1/test_p1_06.py:670-678`（定位词 `def test_http_grading_failures_are_non_2xx_c02_and_change_nothing(`）

```text
    ],
)
def test_http_grading_failures_are_non_2xx_c02_and_change_nothing(
    p1_subjects,
    p1_route_client,
    p1_providers,
    p1_llm: helpers.FakeLLMClient,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
```

### 74. `tests/phase1/test_p1_06.py:707-715`（定位词 `def test_http_provider_failure_is_502_and_leaks_neither_message_nor_path(`）

```text


def test_http_provider_failure_is_502_and_leaks_neither_message_nor_path(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
):
    subject = p1_subjects["科目A"]
    before = _data_digest(subject.root)
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
```

### 75. `tests/phase1/test_p1_07.py:165-173`（定位词 `def test_detect_points_returns_the_four_documented_keys(`）

```text


def test_detect_points_returns_the_four_documented_keys(
    p1_runtime: Path, p1_providers, p1_llm: helpers.FakeLLMClient, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    p1_llm.response = _points_json(
        {
            "content": "消元法解方程组",
```

### 76. `tests/phase1/test_p1_07.py:571-579`（定位词 `def test_a_provider_failure_is_not_a_zero_point_success(`）

```text


def test_a_provider_failure_is_not_a_zero_point_success(
    p1_runtime: Path, monkeypatch: pytest.MonkeyPatch
):
    _install_cfg(monkeypatch)
    helpers.install_provider_stubs(
        monkeypatch, llm=_RaisingLLM(LLMProviderTransportError(f"连接失败 {FAKE_BODY_MARKER}"))
    )
```

### 77. `tests/phase1/test_p1_08.py:149-157`（定位词 `def test_explicit_is_confirmed_and_emphasis_is_not(`）

```text
# 确认策略
# ---------------------------------------------------------------------------
def test_explicit_is_confirmed_and_emphasis_is_not(p1_runtime: Path):
    subject_id = _subject()

    stored = exam_points.upsert_detected(subject_id, [POINT_B, POINT_A])

    by_content = {p["content"]: p for p in stored}
    assert by_content[POINT_B["content"]]["confirmed"] is True
```

### 78. `tests/phase1/test_p1_16.py:94-102`（定位词 `def test_legal_audio_formats_are_published_with_transcripts(`）

```text
# 合法路径：保存 + 转写
# ---------------------------------------------------------------------------
def test_legal_audio_formats_are_published_with_transcripts(
    p1_subjects, p1_route_client, p1_providers
):
    subject = p1_subjects["科目A"]
    response = _upload(
        p1_route_client,
        subject.subject_id,
```

### 79. `tests/phase1/test_p1_16.py:195-203`（定位词 `def test_absolute_and_traversal_names_never_reach_the_filesystem(`）

```text


def test_absolute_and_traversal_names_never_reach_the_filesystem(
    p1_subjects, p1_route_client, p1_providers
):
    subject = p1_subjects["科目A"]
    for bad in ("/tmp/abs.wav", "../sibling.wav", "a\\b.wav"):
        with pytest.raises(Exception):
            uploads.assert_safe_original_name(bad)
```

### 80. `tests/phase1/test_p1_22.py:237-245`（定位词 `def test_a_subject_turn_mounts_only_its_own_same_name_library(`）

```text
# 挂载集合
# ---------------------------------------------------------------------------
def test_a_subject_turn_mounts_only_its_own_same_name_library(runtime_env):
    admin_root = runtime_env.admin_root
    subject_a = helpers.make_subject(admin_root, "科目A")
    subject_b = helpers.make_subject(admin_root, "科目B")
    _make_ready_kb(subject_a, marker="A-only")
    _make_ready_kb(subject_b, marker="B-only")
    _register_global_kb(admin_root, KB_NAME, marker="global-only")
```

### 81. `tests/phase1/test_p1_23.py:234-242`（定位词 `def test_each_same_name_library_is_queried_in_its_own_directory(`）

```text


def test_each_same_name_library_is_queried_in_its_own_directory(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)

    result_a = _execute(
        monkeypatch,
```

### 82. `tests/phase1/test_p1_23.py:299-307`（定位词 `def test_a_forged_cross_subject_reference_is_refused_and_never_queried(`）

```text


def test_a_forged_cross_subject_reference_is_refused_and_never_queried(
    monkeypatch, service, three_libraries
):
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id="科目a", mounted=[three_libraries.ref_a])

    result = _execute(
```

### 83. `tests/phase1/test_p1_24.py:238-246`（定位词 `def test_sources_cannot_re_label_their_scope(`）

```text


def test_sources_cannot_re_label_their_scope(monkeypatch, libraries):
    """来源里伪造的 kb_ref/subject_id 被服务端身份覆盖（P1-23 的公开投影）。

    走**真实**执行链（pipeline → builtin → rag_search → 解析器），只在
    ``RAGService`` 边界放替身，并让它回一个带伪造身份与宿主路径的来源。
    """
    pipeline = _pipeline(monkeypatch)
```

### 84. `tests/phase1/test_p1_24.py:337-345`（定位词 `def test_a_pageindex_turn_reaches_the_existing_outline_without_inventing_mcp(`）

```text


def test_a_pageindex_turn_reaches_the_existing_outline_without_inventing_mcp(
    monkeypatch, p1_runtime
):
    from deeptutor.subjects import kb_scope as scope

    subject = helpers.make_subject(p1_runtime, "科目A")
    _make_pageindex_kb(subject)
```

### 85. `tests/phase1/test_p1_35.py:309-317`（定位词 `def test_any_declared_chart_failure_fails_the_whole_report(`）

```text
# 失败：整体失败、无 URL、旧报告不变
# ---------------------------------------------------------------------------
def test_any_declared_chart_failure_fails_the_whole_report(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:柱状图}\n"
    stub.chart_response = '{"code": [1, 2]}'
    stub.install(monkeypatch)
```

### 86. `tests/phase1/test_p1_35.py:401-409`（定位词 `def test_sandbox_unavailable_is_reported_without_retry_or_host_fallback(`）

```text


def test_sandbox_unavailable_is_reported_without_retry_or_host_fallback(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:图}\n"
    stub.execute_error = "sandbox_unavailable"
    stub.install(monkeypatch)
```

### 87. `tests/phase1/test_p1_38.py:158-166`（定位词 `def test_render_exception_maps_to_render_failed_on_http(`）

```text


def test_render_exception_maps_to_render_failed_on_http(
    p1_subjects, p1_route_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    marker = "p1-38-RENDER-SECRET-91af"

    def exploding(markdown: str, path: Path, typst_bin: Path | None = None):
```

### 88. `tests/phase1/test_p1_38.py:87-95`（定位词 `def test_report_route_keeps_responding_while_pdf_compile_is_blocked(`）

```text

@pytest.mark.asyncio
async def test_report_route_keeps_responding_while_pdf_compile_is_blocked(
    p1_subjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = p1_subjects["科目A"]
    entered = threading.Event()
    release = threading.Event()

```

### 89. `tests/phase1/test_p1_41.py:93-101`（定位词 `def test_http_export_url_downloads_the_same_verified_zip(`）

```text


def test_http_export_url_downloads_the_same_verified_zip(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)

    async def scenario() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
```

### 90. `tests/phase1/test_p1_41.py:124-132`（定位词 `def test_export_failure_is_non_2xx_without_a_url(`）

```text


def test_export_failure_is_non_2xx_without_a_url(p1_runtime: Path, monkeypatch) -> None:
    subject = _subject(p1_runtime)

    def failing(_subject_id: str):
        from deeptutor.subjects import json_store

        raise SubjectOperationError(
```

### 91. `tests/phase1/test_p1_46.py:104-112`（定位词 `def test_pageindex_only_mounts_the_existing_rag_outline(`）

```text


def test_pageindex_only_mounts_the_existing_rag_outline(monkeypatch, p1_runtime):
    subject = helpers.make_subject(p1_runtime, "科目A")
    _make_pageindex_kb(subject)
    ref = kb_scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")
    pipeline = _pipeline(monkeypatch)
    context = _context(subject_id=subject.subject_id, mounted=[ref])

```

### 92. `tests/phase1/test_p1_46.py:170-178`（定位词 `def test_real_outline_result_has_no_passage_or_query_grounded_hit(`）

```text


def test_real_outline_result_has_no_passage_or_query_grounded_hit():
    pipeline = object.__new__(PageIndexPipeline)
    pipeline.document_map = lambda _name: {"paper.pdf": "doc-1"}

    async def get_document(*_args, **_kwargs):
        return {
            "result": {
```

### 93. `tests/phase1/test_p1_54.py:155-163`（定位词 `def test_http_delete_is_real_and_subsequent_reads_are_404(`）

```text


def test_http_delete_is_real_and_subsequent_reads_are_404(p1_runtime: Path) -> None:
    subject = _subject(p1_runtime)
    with TestClient(helpers.build_route_app()) as client:
        response = client.delete(f"/api/v1/subjects/{subject.subject_id}")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "deleted"
        assert not subject.root.exists() and not subject.outputs.exists()
```

### 94. `tests/phase1/test_p1_54.py:186-194`（定位词 `def test_concurrent_export_and_delete_never_overlap(`）

```text


def test_concurrent_export_and_delete_never_overlap(p1_runtime: Path, monkeypatch) -> None:
    subject = _subject(p1_runtime)
    entered, release = threading.Event(), threading.Event()
    original = export_bundle._zip_content

    def blocking(content, zip_path):
        entered.set()
```

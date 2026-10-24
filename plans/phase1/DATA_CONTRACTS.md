# 第一阶段数据契约 1.1（阶段证据流程2.0）

状态：执行规范，尚未实现。仅作用于本阶段新修复的 subject 路径；全局上游 API 不做统一重构。数据源是当前工作树及旧数组 JSON，字段以当前既有格式兼容为先。C 编号供任务卡精准读取。

## C01：存储、身份与兼容

- subject_id 使用 `subjects/store.py` 的 slug 校验，中文合法；不是用户显示名，也不接受路径/百分号/分隔符。先校验再转路径，存在性再由当前用户作用域中的注册表确认。路径 resolve 后必须仍在该用户 subjects 根内，防 symlink 越界。
- 学习数据根：当前 PathService 的 `get_workspace_dir()/subjects`；产物根：当前 `get_public_outputs_root()/subjects`。不能硬编码管理员 data/user，也不能让调用者/模型传 base_dir。已存在结构不移动。
- subject 读写使用直接且严格的当前用户 PathService 解析；当前路径解析失败必须报错，不使用通用 get_path_service 的异常后默认管理员实例 fallback。报告和导出辅助也复用这个严格入口。
- index.json、knowledge.json、wrong_book.json、exam_points.json、knowledge_points.json 顶层仍是数组；profile.json 顶层仍是对象。不切换成统一 envelope，不给所有历史对象批量补 schema_version。新增字段只能可选且读旧数据有确定默认。
- 文件不存在时按集合定义返回 []/profile defaults。存在但 JSON 损坏、顶层类型错误或读取权限失败时抛明确 StorageError；不得返回空集合，不得随后覆盖坏文件。不自动修复/删坏文件。
- 保留记录中的未知历史字段。读取至少校验使用到的 id、subject_id、attempts、correct、level、confirmed 等类型；invalid record 应报有相对文件及记录序号的错误，不把任意字符串转 bool 或把损坏条目跳过。
- 记录时间沿用 Unix 秒；legacy float 可读，不因本轮格式整理重写旧文件。新写入统一整数秒。名称/内容 trim 后验证非空，不改变 question 的精确匹配去重政策。
- 集合写入采用同目录临时文件 → flush/fsync → atomic replace；失败保持旧目标。一次读改写必须在同一 subject/registry 锁内执行，锁不能只覆盖最后一次 write。同进程多线程与 WSL/Linux 多进程必须互斥；不同 subject 锁独立，注册表另锁。嵌套调用要可重入，锁释放不依赖成功路径。
- JSON写入拒绝NaN/Infinity，读取已有集合也拒绝这些非标准常量；不能把它们当作合法掌握度继续流入模板。原子写入序列化失败保持旧文件。
- 允许标准库 Linux flock + 线程重入锁，在本项目 WSL 部署验收。其他平台若没有经过验证的锁实现，应明确拒绝并发写/报告 unsupported，不能静默退回无锁。不得引入重型存储依赖。
- 不承诺多文件跨崩溃数据库事务。学情的一个业务提交应写一个权威集合；知识点关联为可重建派生数据。写错误或生成失败不能以“派生数据先存了”当作成功。导出按快照规约另行验证。

## C02：错误与各入口的一致性

subject HTTP 业务错误保留旧 `detail: string`，增加结构化 `error`。不把 detail 从字符串改成对象，不改全局 FastAPI 校验形状。

```json
{"detail":"批改服务返回的结果无法解析，请重试。","error":{"code":"invalid_model_output","message":"批改服务返回的结果无法解析，请重试。","retryable":true}}
```

| code | HTTP | retryable | 约束 |
|---|---:|---|---|
| invalid_input / invalid_subject_id | 400 | false | 不落盘 |
| subject_not_found / entry_not_found | 404 | false | 不创建替代数据 |
| kb_not_found | 404 | false | 不回退全局同名库 |
| scope_forbidden | 403 | false | 不回退其他作用域 |
| kb_not_ready / kb_busy / material_out_of_sync | 409 | true | 不启动冲突 worker |
| storage_corrupt / storage_io | 500 | false/true | 原文件保留；corrupt=false, io=true |
| internal_error | 500 | false | 安全固定消息，服务端记录原cause |
| provider_unavailable | 502 | true | 不落学情/正式产物 |
| provider_timeout | 504 | true | 不落学情/正式产物 |
| empty_model_output / invalid_model_output / output_truncated / reasoning_budget_exhausted | 502 | true | 不伪造成功正文 |
| sandbox_unavailable / sandbox_policy_unsupported | 503 | false | 不退回裸 subprocess |
| chart_failed / render_failed | 502 | true | 不返回正式 PDF URL |
| feature_unavailable | 501 | false | 兼容保留 Obsidian 拒绝接口 |

上传限额/不支持扩展名第一阶段沿用现有上传器 400，不全局改成 413；原框架的 422 参数校验保持，require_auth产生的401/403及WWW-Authenticate等认证headers也原样保留，不能被业务错误包装改成另一状态。WS 使用既有 terminal error / DONE failed 协议，在 error metadata 增加同样的 code/retryable。ToolResult 失败必须 success=false，metadata.error 同构，不返回有效 artifact URL。所有入口业务错误语义相同，不要求统一底层异常继承树。

日志可以记录 request/task ID、finish_reason、token 数和相对文件定位；对外不得回传 API key、Authorization、原 provider 全响应、全量转写/题目或任意宿主路径。错误 cause 保留在服务端，响应是固定安全消息。测试要覆盖 `LLMReasoningBudgetExhausted` 的实际继承关系。使用 subject-only APIRoute 包装全部现有 subject HTTP 路由；其他上游 router 的异常机制不变，原生422不替换。

## C03：科目更新与删除

PATCH 只更新实际提供的 description/term；未提供保持原值，提供空字符串明确清空，name 改名不在本阶段扩展。科目删除时删学习树与其专属产物树（如果现有产物保留政策另有约定，则改为明确拒绝删除有产物科目；本包选用两树一并清理），两者都必须限定当前 subject，不能以用户输入直接 rmtree。

删除采用锁保护、已存在行为清晰：先验证两路径安全及该科无活跃上传/报告，再清理科目数据/产物，最后更新注册表；任一步失败不得返回 deleted。不能以 ignore_errors 掩盖清理失败。中途失败需记录可诊断状态，保留注册项，下一次可重试；不新增广义垃圾回收系统。本阶段不扫描/删除其他科目或历史未知目录。

## C04：模型正文完成结果

保留 `complete_subject_text(...) -> str` 公共签名。内部用 complete_response 检查 response：

1. 传输/供应商错误抛相应业务异常；
2. finish_reason 属于 length/max_tokens/max_output_tokens 时，无论正文是否为空都失败；空正文沿用 reasoning_budget_exhausted，非空为 output_truncated；
3. 非截断但 strip 后空字符串为 empty_model_output；
4. 其他正文返回 trim 后文本。legacy finish_reason=None 可接受，不能凭空断言完整。

不自动无限重试，不继续渲染半篇报告，不提高 16000 上限作为唯一修复。计费/上下文等上游 complete 契约保持。模型 JSON 消费者必须解析一个完整对象（允许包围代码围栏/思考标签）；不使用贪婪抓取后默认 wrong/空列表，不把数组/null/数字当对象。

## C05：批改与错题

模型数据：`{"verdict":"correct|partial|wrong","feedback":"string"}`；字段必须存在，verdict trim/lower 后精确枚举，feedback 必须字符串。未知模型字段可忽略；缺字段/错误类型/非法 enum/多个候选 JSON 对象均 invalid_model_output。

成功 HTTP 响应保持 verdict/feedback/correct/entry，增加 saved:boolean。已有同题 entry：一次成功批改写一次 attempt；partial 在本阶段仍映射 correct=false，不重设掌握公式。新题正确：不创建“错题”，entry=null、saved=false；新题 partial/wrong：创建 entry 和首次 attempt 在一次集合更新提交中完成，saved=true。失败和解析失败：现有 wrong_book 字节不变；不创建新 entry、不计次数、不改掌握度。

attempt 的 correct 必须真实布尔。entry 无 attempts：mastery=0、status=untracked；有 attempts：沿用三位舍入和现有 classify。不能因 0.7999999999999 而把显示 0.8 判 basic。反馈不替换参考答案，不把模型的错误详情写进 analysis。

## C06：考点检测

模型输出只接受完整 `{"points": [...]}`；[] 是合法“未发现”，缺 points、非法 JSON、错误 level/字段类型属于失败。检测 level 仅 explicit/emphasis，manual 历史 inferred 可读。每候选 content/evidence/kp 字符串，content/evidence trim 非空；evidence 必须是转写中的直接引用（只允许空白归一化匹配，不做语义相似替代）。

负向证据中的直接短语“不考/不会考/不用重点看/了解即可”等按现有提示词规则排除，响应 warnings 说明排除数量；这是确定性文字护栏，不承诺完整语义理解。其余不存在原文的 evidence 使整轮 invalid_model_output，整轮不入库；不能部分保存后才失败。

成功响应保留 version/detected/stored/raw，增加 warnings；detected 等于实际保存候选数，raw 为既有模型正文，不含思考/供应商诊断。confirmed 保留旧政策：auto_confirm=true 或 validated explicit；emphasis 默认 false。同科/同学期/content/evidence 归一化完全相同候选重复检测不重复追加，返回复用条目。批量写一次集合。模型失败不能返回 200+detected=0。

term 未提供或为空字符串时采用 subject.term；聊天考点摘要按当前学期过滤。subject.term 空时可以显示所有已确认点，但标题写“已确认考点”，不能声称本学期。不新增考试预测器。

## C07：资料上传与索引源

```json
{"operation":"index","kb_name":"assignment-kb","type":"assignment","files":["notes.txt"],"task_id":"...","message":"已保存，正在建立索引"}
```

```json
{"operation":"transcribe","type":"lecture","files":["lecture.wav"],"transcripts":[{"file":"lecture.wav","text":"课堂文本","model":"..."}],"message":"转写完成"}
```

保留旧键，仅增加 operation，ASR 没有 KB/task_id 就不宣传索引。filename 使用现有安全命名/validator；绝对路径、..、反斜杠/分隔符、symlink 越界拒绝；不能把恶意名静默修成另一个现有文件并覆盖。音频后缀扩展在 subject endpoint 局部白名单，不扩大普通文档全局允许集合；限额复用配置/validator，分块读写，超限留下的临时文件清理。ASR发送multipart使用受控文件流和与扩展名对应的MIME，不再次把整个录音read_bytes进内存；STT配置/provider选择不变。

auto 分类以完整 batch 为单位验证：每文件类型都一致才接受，不按第一个文件给其他文件分类。混合类别/音频+文档返回 400，整批不保存。显式 type 同样不允许把非音频送 ASR；支持现有合法类型与扩展映射（补齐已在 ASR/UI 声明的 wav/flac/ogg/aac 等）。空 batch、同 batch 重名、非支持扩展、损坏压缩路径先拒绝。

文档同名重传的政策是替换。同 subject/KB 写锁内 staging 验证 → materials/raw 都替换 → 校验 hash 一致 → 才排索引任务。常规异常应回滚成旧一致版本，不开始索引。不要求跨目录原子提交：进程崩溃造成差异必须在下一次索引入口检查并返回 material_out_of_sync，不能使用旧 raw 当成功。新资料更新后旧已发布索引仍代表旧版本，状态标记 rebuilding/stale，不能说新资料已检索。

每 KB 在 `<kb_dir>/subject_sources.json` 存内部 source manifest（相对文件名、size、sha256，不含题目内容/密钥），documents 表示当前 raw 可索引源文件数，不是 chunk 数或上传次数，既有 record 仍保持 documents 字段。已有材料无 manifest 时只读重算，首次成功上传才写新增 manifest；不批量迁移真实六科。

并发初始化/重建：同库只允许一个活跃任务；600 秒无进度守卫语义保留，无进度后 API 报错，worker 不被当成已终止；活跃 worker 未退出仍禁止同库重入。任务状态必须能区分错误、索引 ready、重建进行中；不改核心引擎版本协议，不强制替换 embedding 模型。

## C08：聊天科目作用域与知识库标识

输入 subject_id 采用三态：未提供沿用当前 session.preferences.subject_id，null/空字符串明确清空，非空字符串设置。支持顶层字段及旧 config.subject_id；两者同时提供且不相等为 invalid_input。不能用 `a or b` 丢掉清空值。验证发生在创建 turn/写用户消息前。新 session 无值即 null；切换 session 不继承另一 session 的选择。

复用已存在 preferences_json 保存 subject_id，不新增 SQLite 列或配置数据库，不改变 session store API。运行 metadata 带 resolved subject_id，request_snapshot 保存本轮 resolved 值，以便重试/再生成使用原作用域；UI 恢复 preferences 后才允许发送。被删科目的历史会话提示 subject_not_found，用户显式清空后恢复普通聊天，不静默选别科。

subject KB wire id：`subject:kb:<subject_id>:<kb_name>`。subject_id/kb_name 均不含冒号；中文按字符串存储，URL 路径各段单独编码。既有 admin:kb:/user:kb: 保留。不修改知识库磁盘名字。

内部 resolved resource 包含 wire id、真实 name、subject_id|null、当前用户 base_dir、read_only；base_dir 不进入模型工具 schema/公开响应。显式 subject ref 必须属于本轮 subject，且该科/KB存在、权限通过；scope mismatch 报 403，缺库报 404，不回退全局。所有构造路径在服务端。

本轮 knowledge_bases = 用户显式挂载的合法全局 ref + 当前科目所有 ready 的 subject refs，稳定去重。未 ready 的当前科库用 warning 表达，不挂载成功检索列表；空科目不附加全局默认库。模型工具参数 enums 使用 wire id。legacy bare name 仅在本轮已挂载资源中唯一匹配时接受；重名为 invalid_input，不能猜 subject/global 任一来源。

rag 和 kb_files 使用同一 resolver，ready/权限制约一致。返回来源必须带 kb_ref、subject_id、源文件名/页码（若原 parser提供），不只带重名 kb_name。已有 read_source 仅从 server source_index 读附件 ID，保持此约束，不增加“任意文件路径读取”或新的全文 KB 阅读功能。附件来源和 KB 引用不可混为同一个 id。

不能因科库检索失败悄悄改用全局 KB 回答；WS/工具失败必须可见。全局用户访问规则保持。PageIndex 的概览路径在 C13 单列，不宣称本阶段新增深度 MCP 检索。

## C09：图片与索引覆盖

保留支持多模态 embedding 的 ImageNode 路径；文本 embedding 的现有默认配置不再直接跳过所有图片，而使用：现有 parser/image asset → 根据 vision_strategy 选择视觉模型 → 生成事实性描述/OCR → 普通文本 Document。不更换 embedding 模型/维度，不生成伪 image vector，不在 metadata 存 base64。

描述文本前缀标明来自图像，携带 source file、可用的 page/location、图片相对 asset 标识、content_kind=image_description。仅记录 parser 确实提供的位置，缺页码为 null，不猜页码。描述不为空才建立文本节点；主 LLM 检测不支持时可走独立 vision；dedicated_only 没配置时明确错误/覆盖降级，不偷用主模型。main optimistic image 调用失败遵循已有降级策略并计入 coverage。

coverage 是加法式 metadata：text_sources、images_seen、images_indexed、images_skipped，以及 skip_reasons 计数（parser_no_assets / vision_unavailable / vision_failed / budget / unsupported_image）。parser 不提供图时只说“未提取/未验证”，不能说 0 张且覆盖完整。有正文且图片跳过可继续文本索引，但公开 coverage warning；只有图片且全部失败、没有任何节点时初始化失败，不标 ready。

抽图预算沿用 document_images 现有常量：每文档 12 张、单图 4MB、<1200 字节跳过；聊天单轮 16 张/12MB。索引每文档沿用相同上限并记录跳过，不引入无界全图调用。缓存、并行图片描述、批量 OCR 与全量真实知识库重建不属于本阶段。

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

source_file 是当前 turn source_index 中的附件 source_id，只能读取服务端已附着文本；无可解析 ID 返回 invalid_input。禁止读取模型给的宿主任意路径。API 使用 requirements 即可，不为其新增通用文件读取参数。

ode_rhs 为空时不强行注入 `x**2-y`，普通图提示只按 spec 画图。非空表达式用 AST 白名单验证：x/y，有限数字，+ - * / ** 和一元 +/-，调用 sin/cos/exp/log/sqrt/abs（仅这些名字）；无属性、下标、import、lambda、列表推导、双下划线和未知变量。指数等计算量仍受资源限额。检查通过的表达式在隔离环境执行；verification_status=passed 仅说明给定 5 点的 f(x,y) 数值吻合，不代表解析解/整篇数学正确。失败不发布完整报告。

图表代码和 ODE 检查都只能由专用 chart executor 执行。必须同时保证：OS 隔离、只挂当前任务 workdir 可写和字体/解释器必要文件只读、网络禁用、env 白名单且无密钥、超时终止进程组、CPU/内存/产物大小受限。现有 BwrapBackend 可作为底座，trusted worker 在执行模型脚本之前施加资源限额；普通 APPLICATION backend、未证明逐任务隔离的共享 runner 不合格。不存在合格 backend 返回 503；不得裸 subprocess fallback、自动下载/安装 sandbox 或修改系统策略。

资源默认：脚本墙钟 60s、CPU 30s、内存上限 1536MiB、stdout/stderr 10000 字符、单图 10MiB/20百万像素、每报告最多 8 张图；ODE 检查墙钟 30s。CPU/内存用进程级hard RLIMIT且子进程继承，不能宣称已实现整棵进程树累计cgroup配额；墙钟超时必须终止整个执行进程组。资源数值可在新内部 ReportExecutionPolicy 定义，未授权不改变部署 settings schema。trusted worker 代码单独只读挂载，不能放在模型可覆盖的工作目录中；配置阈值由服务端提供，模型不能传 limits/mounts/env。OOM/超时/非法输出为 chart_failed。Typst只执行可信转换模板，不执行模型 Python。

review 接受 report_id 或 latest；旧 report_path 仅作为兼容输入，规范化后必须是该科已有报告目录中的已知 .md/.pdf，严格拒绝跨科、绝对外部路径和 symlink 越界。任意未知 md 不得读取。review 新建 report_id，并复制原图到自己的目录，不覆盖原正文/PDF，metadata 记录 reviewed_from；若正文要求保留的原图丢失/指向外部路径就失败。

模型/渲染/图失败时无正式 URL；私有失败诊断可保留，但不覆盖旧 completed 报告。API 与 ToolResult 都适用 C02。报告生成不承诺自动从讲义检索/数学形式化证明。

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

- 所有修改的 async action 有 try/catch/finally，失败解除 busy，不显示成功计数/生成链接。post 非 2xx 不继续按成功刷新；读取 error.message，兼容旧 detail 文本。界面不展示 traceback/provider密钥/宿主路径。
- subject selector 提供无科目选项；从当前 session 的 preferences 恢复，能力参数与 subject_id 合并不能覆盖彼此。刷新恢复未完成时不能发送旧科目的请求。
- 上传 operation=transcribe 时显示转写完成与文本去向；index 时显示任务/状态；documents从C07，coverage降级可见。不新增“音频自动建库”或全新批改界面。
- 去掉 Obsidian 可点击创建入口及活跃宣传。保留 501 API 和合法历史数据读取拒绝；不删除用户原 vault/旧 KB 目录。
- 删除 partners/tutorbot/matrix 依赖 extras 和 requirements 镜像，root requirements 改 server；修对应打包断言。保留 CLI、scheduler、sandbox runner、office skills、built-in deferred_tools、load_tools、多用户上下文和现有内置 capability。不按词删 runtime/providers。
- PageIndex 可用 REST outline 能力保留且如实标注 retrieval_kind=outline，不宣称有不存在的 MCP 深度检索工具。当前 prompt/挂载应能走既有概览检索，不引入外部 transport。MCP SDK 暂保留但注释标“兼容待审查”，不是“当前自动注入client”；后续若需要移除，另立有完整动态插件/打包证据的卡。
- 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。

## C14：证据与阶段验收（2026-10-11修订）

每张小卡仍需正向和独立反向行为证据；合法负例从已证明有效的base只改一个字段/故障点。高风险用一个针对性坏对照确认断言捕获真实效果，禁止只看源码contains或mock自证。该义务不要求每卡交付一份独立人工报告。

每阶段一个执行会话，阶段内按stages.json既定顺序串行卡。报告/审查为阶段粒度，规则见STAGE_WORKFLOW.md。新阶段使用StageReport schema：stage_id/status/baseline_id/card_results/commands/scope_check/real_data_unchanged/limitations。card_results含卡ID、目标、修改路径、断言、命令定位和限制；commands保存实际命令、cwd、exit、共享execution.log行号，不能只写摘要“通过”。

单元状态verified_local表示本地验证；阶段末由协调者独立复核并写review.json的accepted，执行者不能自签。历史P1-00/completion.json保持原样，协调修补/签收另存reviews/P1-00；旧Completion schema继续兼容明确单卡调用，不强制后续每卡创建文件。

真实数据保护失败立即停止；环境缺失用blocked_environment，不以skip/mock作为真实验收。源码增量按阶段开始前快照和阶段白名单并集检查，不把继承dirty计为新改动。日志仅追加保存失败尝试；原始baseline/归档不可覆写。新v2快照包含批准新增源文件和mode，历史v1只能证明它当时记录的范围。

最终验收仍需完整pytest 0 failed、原403前端测试保留且新增行为测试通过、tsc/相关ruff通过、scope/data不变，以及真实HTTP/WS/OS sandbox/浏览器场景。passed计数可随新增用例增长；合法旧skip保留，不新建skip/xfail逃避本阶段要求。主审阅者可在已授权范围直接修复并复测，披露自己的修改，不能用新的自证代替独立验收。

共享严格ID/hash模式使用JSON Schema真正的字符串结束约束，不能用单独$假定fullmatch；Python用re.fullmatch。错误message/detail至少非空且≤512字符，仅固定安全消息，不得仅截断原输入或cause冒充去密。

2026-10-20用户明确批准的唯一数据例外：S14事故改写 `data/user/settings/model_catalog.json`，原3608字节配置未恢复。授权、新旧精确SHA与基线引用见 `data_baseline_exception.json`；旧P1-00/S13基线与事故证据不变。协调者receipt须保留相对事故前 `real_data_unchanged=false`，另记用户例外与获准基线后的零增量；不得改写原worker报告来冒充未发生事故。例外验证只允许该文件的既定SHA/size变化，其他五树、settings其他文件、目录/权限均不放宽，之后所有变化仍失败。后续阶段从获准新基线开始保护；这不证明原配置恢复或真实模型可用。

## 附录A：基础卡必须提供的内部接口

这些名称/返回字段固定，避免消费者卡再次自行选接口；额外私有 helper 可以在本卡允许模块内实现。均不向模型暴露磁盘路径。调用者要在明确当前用户上下文中调用，不能在模块import时读取真实配置。

| 基础卡 | 接口 | 返回/异常义务 |
|---|---|---|
| 03 | `SubjectOperationError(code, message, *, http_status, retryable, cause=None)` | cause只在服务端；字段不可缺 |
| 03 | `map_subject_exception(exc)` / `to_http_payload(error)` | 返回领域错误 / C02响应对象；未知异常internal_error |
| 04 | `validate_subject_response(response) -> str` | C04的空/截断检查pure函数，供正文与图像描述共用 |
| 55 | `parse_model_object(raw: str) -> dict` | 一个完整对象，否则invalid_model_output |
| 05 | `async grade_answer(question, student_answer, reference_answer) -> GradeResult` | 只含验证后的verdict/feedback；无磁盘写入 |
| 10 | `read_list(path: Path) -> list[dict]` / `read_object(path: Path, *, default: dict) -> dict` | 缺失默认、存在损坏报错，不静默覆盖 |
| 10 | `json_transaction(lock_dir: Path)` | 可重入contextmanager，持有目录对应读改写锁；_save嵌套不得提前释放 |
| 11 | `current_subject_paths() -> PathService` | 严格current-user路径解析，失败不回管理员root |
| 20 | `encode_subject_kb_ref(subject_id, kb_name) -> str` | 不改磁盘名称，非法slug拒绝 |
| 20 | `resolve_kb_ref(kb_ref, *, expected_subject_id, mounted_refs=None, require_ready=True) -> ResolvedSubjectKb` | fields为kb_ref/name/base_dir/subject_id/read_only/provider；严格授权且有C08歧义策略 |
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

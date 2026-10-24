# MD-R2 验收与交付

仅测试 fixture/local model server，不读取真实 key。运行阶段先记录到达快照，结束比较真实六树 opaque inventory。工作区本来 dirty，不以 git diff 整体为空作为成功条件，不恢复旧基线。

## A. 硬性行为证据

| 编号 | 必须证明的行为 | 最少反例/边界 |
|---|---|---|
| A01 | registry 全部 38 项有显式策略，新增遗漏会失败 | 3 managed 不派发；未知注册名不悄悄继承 OAuth 或其他身份 |
| A02 | DeepSeek、OpenRouter 等缺口进入实际目录请求 | 非特殊 compatible binding 不再立刻 unsupported；同协议不同身份不串 key/cache |
| A03 | 阿里 LLM 下拉有明确中文身份，现有 dashscope 可用 | aliyun 作为 LLM 别名；STT/embedding 没有变更 adapter；不新增重复项 |
| A04 | 学校式网关目录及可选覆盖 URL | 代理前缀/端口/query/version/额外头；末端 /v1 两路径；未知别名 model ID 原样保存 |
| A05 | 错误语义正确，不被回退隐藏 | 401、403、404/405、429、timeout、TLS、HTML 200、坏 JSON、成功空目录分别断言；404 不变成 empty |
| A06 | 原生 Anthropic/Gemini 分页与认证 | 游标停滞；旧字段缺失；Gemini embed-only、输入上限不等同总容量；不向原厂发送自定义代理 key |
| A07 | Azure offering/deployment 分开 | v1、旧 deployment URL、资源根、API version；需要用户部署名时不能无提示自动添加调用 |
| A08 | 官方结构化参数归一化 | DeepSeek 1048576/393216、Ali model_info、OpenRouter 嵌套、Mistral/Groq 文档化字段；无效整数/不同型号/区域/模式不串 |
| A09 | 文档资料来源真实且有限 | 官方 URL/日期/精确匹配；不把文档核验时间改成刷新时间；endpoint 小限制优先；同名学校模型不套原厂值 |
| A10 | 参数缓存 round-trip 与升级 | 旧 cache 可重查；冷却/single-flight/取消/损坏/IO 错误；失败保留 stale 和原 checked_at；缓存不写 catalog |
| A11 | 新 LLM 参数自动填入并生效 | 缺字段显示未知；最大输出并非 context；无 metadata 的旧配置仍 4096；schema1 旧响应兼容 |
| A12 | 新 embedding 默认/可选维度及协议 | 默认1024、choices含2048时填1024；只有 choices 不猜默认；supports_dimensions=false 不发参数；未知保留旧协议语义 |
| A13 | 手工设置、更新预览和保存失败 | legacy 非空值视 manual；主动清空保留；恢复自动；取消差异不改 draft；刷新不改 active/id/name/授权/维度 |
| A14 | 输出预算贯穿两条实际请求构造 | mock捕获 factory chat/stream 与 core agentic；显式较小预算保留，超已知上限限制，换模型不串 metadata |
| A15 | 长历史与实际输入/输出限额一致 | 大输出默认不导致 input+output 超窗；输入与 combined 分开；保留项目安全 cap，官方原数不截断保存 |
| A16 | 自定义名称覆盖所有 picker 状态 | 选中/未选中/隐藏当前项/重名/空白名/题目跟进；保存返回、刷新、旧请求竞态，调用 ID 不变 |
| A17 | 权限、凭据和真实数据 | 普通用户不可查目录；同 profile mask/header 恢复；改 binding/origin/目录origin 要重填；query日志/redirect/上游body无密钥 |
| A18 | 原功能和已有防护仍有效 | 阿里 ASR、SF、旧 discovery review regressions、显示隐藏授权及真实六树不变 |

测试必须包含生产函数/实际请求构造的行为断言，不用搜索源码字符串充当功能验收。参数缺失不是目录失败；没有 endpoint 目录也不能冒充全厂商成功。

## B. 浏览器交互

新增独立 MD-R2 wrapper/e2e，复用 `web/playwright.phase1.config.ts` 的 disposable source、本地 endpoints、认证、cleanup 和已安装 Chromium。新的 MODEL_SERVER fixture 只能在 base config 的隔离服务中加路由，不在生产 API 中增加测试后门。

最少完整执行：

1. 设置选择 DeepSeek，查询显示两个 fixture 模型；添加 Pro；核对官方参数默认填入，保存、返回聊天，别名显示正确；本地 provider 捕获实际调用 ID/预算。
2. 同 profile 已存在 Flash 的手工 1000000 和别名在查询、重复添加、刷新后保持；显式更新参数预览可取消，恢复自动后才改变。
3. 选择阿里 LLM，目录中混合 LLM/embedding/ASR 正确分类；加入一个 Qwen 文本模型保存。独立 embedding 设置用 1024 默认/2048 choice fixture 演示自动值，已有维度不被覆盖，不发生索引操作。
4. 配置学校式网关带代理前缀、额外头、模型别名；未知类型可以一次批量确认用途，缺参数显示未知；目录覆盖字段可用。
5. 401 和刷新失败保留旧候选/原参数时间；改目录 origin + mask 必须提示重填。保存失败保留 draft。
6. 主聊天与题目跟进 picker、隐藏当前项都显示自定义名称；重新载入后仍一致。浏览器 network 只在本地隔离 endpoints，零真实厂商推理。

不能以 APIRequestContext 代替点击输入、保存和聊天交互。截图只辅助，断言和 fixture 请求记录是主要证据。

## C. 检查入口

项目根：

```bash
.venv/bin/python scripts/run_tests_isolated.py -q tests/services/model_discovery tests/api/test_model_discovery.py tests/api/test_model_visibility.py tests/services/config tests/services/llm tests/core/test_agentic_client_provider_kwargs.py tests/agents/chat/test_context_budget.py tests/services/session/test_context_builder.py
```

上述相关门通过后，在最终源码上运行一次完整 Python 回归：

```bash
.venv/bin/python scripts/run_tests_isolated.py
```

web 目录：

```bash
npm run test:node
npx tsc --noEmit
npm run i18n:check
```

对实际改动文件运行项目已有 Ruff/ESLint 和 `git diff --check`。记录既有 warning，不为了清 warnings 扩大修改。只在新代码/失败/未解决风险支持时重跑，不按每卡全量测试。

浏览器执行示例（先实现对应 wrapper，路径必须新建且未封存）：

```bash
S15_EVIDENCE_DIR=/home/albert/selflearn/selflearn/.phase1-evidence/model-discovery/MD-R2-<new-run>/browser npx playwright test --config playwright.model-discovery-r2.config.ts
```

不要把 `<new-run>` 原样当命令执行；实际使用本阶段新的唯一 run_id。若当前执行环境禁止本地 listen/Chromium 启动，先完成其他工作并准确记录限制，不绕过网络 guard 或降低测试定义，不写“全验收通过”。

## D. 交付件

在新 `.phase1-evidence/model-discovery/MD-R2-<run>/` 提供：

- source_arrival/source_final 清单、源码可重建归档及 verify-rebuild 结果，覆盖新增未跟踪源码；不打包真实数据/密钥。
- data_before/data_after 及 compare-data，涵盖 runner 规定的真实六树，不把合法用户到达前变化归为本阶段事故。
- `provider_results.json`：恰好覆盖 registry 全量，分别记策略、fixture 测试 ID、目录字段支持、未具备的能力与 live_tested=false；不得每项都粗写 supported。
- `acceptance.json`：A01–A18，每项测试位置/结果/证据路径；完整命令、退出码、Python/Node 计数、browser_assertions 和限制。
- `metadata_sources.json`：新增官方资料 entry 对应 URL、核验日期、地域/模式、字段，不包含真实账户目录结果。
- `report.json` 和 `report.md`：完成、剩余、风险、数据不变、未进行真实学校/各厂商验证的说明。代码修好但硬性 gate 未过时标 changes_requested/blocked_environment，不能 accepted。

`plans/model-discovery-r2/EXECUTION.md` 只索引最终执行证据，不改本规划的“尚未实施”历史事实或封存 MD-R1 结果。最终报告不要求用户逐卡继续，也不擅自开启科目 UI/知识库可达性或其它第二阶段功能。

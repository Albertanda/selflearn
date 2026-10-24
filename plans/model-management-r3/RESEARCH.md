# MM-R3 官方资料和本机实现核对

日期：2026-10-24，Asia/Shanghai。本次无真实厂商推理。下面是已阅读的实现与官方协议，不从应用界面的档位数量推断厂商能力。

## 当前源码事实

- web/lib/reasoning-effort.ts：BINARY_THINKING_PROVIDERS 包含 deepseek/dashscope 等；supported 匹配不含 deepseek-flash；返回 minimal/high。
- deeptutor/services/llm/reasoning_params.py：minimal 被映射为 thinking disabled，DeepSeek patterns 也漏 deepseek-flash；Qwen enable_thinking 分支抑制顶层 effort。现代型号已不适用。
- MD-R2 参数白名单没有 effort.supported_levels；不能仅靠保存 name/context/max_tokens 自动修复强度。
- web/lib/unified-ws.ts 的请求只有 llm_selection；runtime/request_contracts.py 的 ChatRequestConfig extra=forbid。新增控件必须有正式 request schema 与turn scope。
- ServiceConfigEditor 点击profile/model直接写 draft.services[service].active_*；SettingsContext addProfile/addModel 同样修改。默认项隐蔽问题来自状态混用，不能只新增一个外观页面。
- ModelCatalogService 已有 update(mutator) 锁内读改写；新默认 API 应复用它，不在路由比 hash 后裸写。

## 官方档位与映射

| 系列/接口 | 已核实依据 | 实施要求 |
|---|---|---|
| [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) | low/high/max；minimal→low、medium/xhigh→high、ultra→max；thinking 开关独立 | Flash 和 Pro 都应有三档；minimal 不等于关闭 |
| [DeepSeek Models](https://api-docs.deepseek.com/api/list-models/) | effort.supported_levels/default_level | 获取时一同解析；不只靠长期硬编码 |
| [阿里 DeepSeek](https://help.aliyun.com/zh/model-studio/deepseek-api) | low 的支持型号有限制，旧 Pro 与快照差异存在 | 精确供应商+型号+版本判定，不能套原厂同名策略 |
| [阿里深度思考](https://help.aliyun.com/zh/model-studio/deep-thinking) | 混合模式开关、thinking_budget 等 | 预算预设要标明控制方式，不与强度字段冲突 |
| [阿里 DashScope 参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-dashscope) | 新 Qwen 支持 effort，部分系列 effort/budget 互斥 | 编写规则时限定型号和实际 OpenAI-compatible wire，而非把所有模型当 binary |
| [OpenAI Reasoning](https://developers.openai.com/api/docs/guides/reasoning) | 档位与是否可关闭依模型而异；Chat Completions 与 Responses 字段不同 | 采用模型能力表/专用适配器，不能全厂商套固定五档。已使用 OpenAI Docs 技能查询和阅读官方文档 |
| [Claude Effort](https://platform.claude.com/docs/en/build-with-claude/effort) | 原生 low/medium/high/xhigh/max 随型号变化；新模型有不能关闭思考者 | adaptive 是模式，effort 是强度，分别发送 |
| [Claude Adaptive Thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking) | 自适应模式不使用旧 budget_tokens | 不将所有档位只变成一个 adaptive 开关 |
| [Gemini Thinking](https://ai.google.dev/gemini-api/docs/generate-content/thinking) | 2.5 budget、新系列 level；minimal 不保证关闭 | 确认具体系列，不造 none |
| [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) | 项目所用 compatible transport 的 thinking 参数 | 原生字段与 compatible wire 不可直接混用 |

上表是方法与已核实约束，不是全系列永远相同的枚举。需要用 fixtures 固定具体规则，来源日期保留，不从新的显示名称猜版本。官方资料有歧义时用有证据的保守子集并在报告列明。

## 本机 Hermes/Chatbox

- Hermes：`/mnt/c/Users/17261/AppData/Local/hermes/hermes-agent/agent/reasoning_effort.py`，内部 EFFORT_LADDER 是 none/minimal/low/medium/high/xhigh/max/ultra。这是跨接口词汇表，非每个模型都有八档。clamp_effort 用支持集合和特例转换，值得借鉴其单一策略层。
- 该本机版本的 DEEPSEEK_V4_OVERRIDES 把 xhigh→max；这与上面当前 DeepSeek 官方文档 xhigh→high 不同。**以当前官方协议为准，不复制旧规则**。
- Chatbox：`/home/albert/chatbox/work/cb/src/shared/models/utils/deepseek.ts` 区分支持 effort 的 V4 与旧型号并过滤发送值。它的静态集合也不等于当前所有服务商的能力，不能当权威模型目录。

## 嵌入问题的复核结果（前置修复）

当前用户配置包含 qwen3.7-text-embedding、tongyi-embedding-vision-flash-2026-03-06。官方给了默认维度，分别1024/768；缺失来自目录未返回与项目资料未覆盖，不能笼统称官方没公布。

依据：[阿里文本向量API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)、[多模态向量API](https://help.aliyun.com/zh/model-studio/multimodal-embedding-api-reference)。协调者已补资料、维度与限制同取、预览更新、原生SDK send_dimensions=false、通义视觉路由及诊断能力。真实配置/索引未修改。后续阶段只需保持回归，不重复重写这些模块。

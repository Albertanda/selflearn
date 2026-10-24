# MM-R3 数据与行为契约

## C1 范围和稳定引用

基于已签收的 MD-R2 协调者最终源码。只实现本阶段三项用户功能及其必要参数/权限/缓存接缝。保护真实数据与原证据，不修改真实默认项、密钥、索引，不主动调用付费模型。当前阿里 ASR 与嵌入配置不做开发 fixture。

模型身份继续是 `{profile_id, model_id}`；model 是请求名称；name/model_name 是展示名。分组、改名、强度与默认设置都不能改这些 ID 或扩大授权。

## C2 两层选择

- 以已授权 options 的 profile_id 为第一层稳定分组键，显示 registry provider_label；自定义连接显示用户配置名。同厂商多个 profile 用“供应商 · 配置名”区别，不能把同厂商不同 key/endpoint 的模型合为一个连接。不要用 model ID 前缀或 owned_by 当实际服务来源。
- 第一层列供应商/连接与可见模型数量；选连接进入第二层。第二层仅列该 profile 的可见模型，提供返回；选模型才调用 onChange，不因选第一层就自动切模型。鼠标点击、键盘方向/Enter/Escape、触屏可用；不依赖 hover 才能操作。
- 按钮与第二层页头显示供应商/连接 + 用户模型名，tooltip 带真实调用 ID。原厂 DeepSeek 与阿里同名模型始终可辨。默认项明确标注，当前选中/隐藏当前项/刷新失败/空目录/系统默认行为沿用。
- 搜索可以跨连接，但每条结果必须显示其服务来源；清空后回到原两层，不重置当前引用。普通用户只分组已授权/个人模型，不调用管理员 catalog 接口补全组，不泄露其他连接/URL/key。
- 主聊天与题目跟进复用同一组件。选中隐藏模型可继续显示和使用，不能因为分组隐藏取消授权。既有“当前默认不能隐藏”服务端规则不修改；测试隐藏其他已选项即可。

## C3 思考能力契约

新增可选 `reasoning_controls`，由后端针对**供应商身份 + 具体调用 ID + 实际推理协议**解析，不从显示名称推断。LLM options（含 hidden_options 和普通用户授权路径）返回安全能力摘要，模型配置页和聊天读取同一策略。

```json
{
  "supported": true,
  "control": "effort",
  "levels": ["low", "high", "max"],
  "can_disable": true,
  "default_level": "high",
  "aliases": {"minimal":"low","medium":"high","xhigh":"high","ultra":"max"},
  "source": {"kind":"provider_api","source_url":"https://api.deepseek.com/models","checked_at":"2026-10-24T00:00:00Z"}
}
```

- supported 为 true/false/null（未知），control 为 effort/budget/toggle/adaptive/unknown。levels 仅真实 UI 可选档位，预算控制可用 low/medium/high 并标明预算预设；aliases 是有依据的兼容输入映射，不能误称新增原生档位。
- 内部可接受词汇包含 none/minimal/low/medium/high/xhigh/max/ultra；inherit/provider_default 是选择语义，不是厂商 effort 字符串。adaptive 是协议模式，不和 high 等档位混为同一强度列表。
- metadata 优先于精确供应商/模型/地域/协议官方资料；旧目录缺 effort 字段可用已核验资料，注明来源与日期。未知代理不因 model ID 名称类似原厂就套原厂策略；用户已有显式设置保留可见但提示不支持/待确认，不能默默放大计算量。
- DeepSeek 官方目录的 effort.supported_levels/default_level 必须解析、缓存、导入、保存、更新预览及展示贯通；缓存 schema/指纹考虑新能力版本，避免旧目录吞掉字段。可在候选与 provider_metadata 中增加 sibling reasoning_controls，保持 MD-R2 parameters 白名单类型清晰，后端保存校验同步更新。
- 安全摘要不返回 headers/key/base URL。能力来源 URL 同 MD-R2 去 query/userinfo，不用响应里的任意 URL 再携带认证抓取。

## C4 档位和协议映射

- DeepSeek 原厂 deepseek-flash/deepseek-v4-pro：原生 low/high/max；关闭使用其协议 thinking disabled，开启使用 thinking enabled。minimal→low、medium→high、xhigh→high、ultra→max。**minimal 不是关闭**。Auto 不发字符串 auto。兼容映射以官方为准，本机 Hermes 的旧 xhigh→max 规则不照搬。
- 阿里 DeepSeek：使用阿里自己的 API 规则，不把 dashscope 的所有模型都用 enable_thinking。当前官方明确 deepseek-v4.1-flash、deepseek-v4-flash-0731、deepseek-v4-pro-0813 有 low/high/max；旧 deepseek-v4-pro 只保证 high/max，不伪造 low。1017 快照按其精确文档或实时能力处理，不能凭 Flash 名称继承原厂版本。
- 阿里 Qwen：按确切系列采用 enable_thinking + thinking_budget 或原生 reasoning_effort。两者不能冲突发送，尤其 qwen3.8 的 reasoning_effort 与 thinking_budget 互斥。只有有预算控制依据时才提供低/中/高预算预设，数值满足该模型上下限和实际输出预算；预算不足给清楚校验，不悄悄全映射同值还声称三档。
- OpenAI/Azure/Codex/Copilot：按具体模型/专用适配器公布的 levels，不能用 gpt-5/codex 子串硬套所有模型。max/xhigh/none 是否允许因型号而异。Chat Completions 的 reasoning_effort 与 Responses 的 reasoning.effort 正确区分，OAuth 仍走原 token/协议，不新增登录。某型号当前推理协议不支持工具等条件，不借本阶段新增整套推理协议。
- Claude：effort 与 thinking 模式分离。新模型用 adaptive + output_config.effort，旧预算模式使用 enabled/budget_tokens 且预算低于 max_tokens；只给原生支持的 levels，不能将 low/medium/high 全变成 adaptive 而不传 effort。部分模型不能关闭思考，要反映 can_disable=false。型号的 xhigh/max 支持以官方表为准，不一概套所有 Claude。
- Gemini：2.5 budget 与新系列 level 分开；本项目当前 Gemini backend 是 OpenAI-compatible，应遵循 Google 兼容接口文档，不把原生 thinkingConfig 直接塞到不支持的 wire。不可关闭的型号不显示 none，minimal 不等于关。原生 level 数量按型号，不能因为默认最少三档而给不支持的型号造参数。
- 其他已注册供应商使用文档/元数据的明确策略或 unknown。不需要凭空完成 38 厂商真实验证；必须保证未知配置不乱发通用 reasoning_effort。支持三档及以上者完整展示，只有 binary 者如实显示开关。
- native formatter、HTTP fallback、SDK/core client 的实际请求语义一致。枚举映射纯函数唯一，前端不维护另一套不同判定；前端仅展示后端策略。旧配置中 minimal 原先被当关闭是历史歧义，本阶段明确：off 用 none，minimal 按供应商官方语义。不得批量重写旧数据；UI 提示并让用户选择。

## C5 每轮覆盖与会话生命周期

新增正式请求字段 `reasoning_override?: {mode:"inherit"|"provider_default"|"effort", effort?:string}`，同时定义 TS、HTTP/WS 及 Python 校验。mode=effort 必须有合法 effort，另两种不得带 effort，额外字段拒绝。省略等于 inherit，兼容旧客户端。

解析顺序：先解析并授权 llm_selection/当前默认，取得该模型策略，再验证强度；请求不可越权挑模型。选择 inherit 时使用该模型已保存 reasoning_effort/既有默认；provider_default 时**抑制项目默认注入**，不把字符串 auto/provider_default 发给厂商；effort 按 C4 解析实际 wire 值。强度只在本 turn 的 scoped config 中生效，不改 model_catalog、全局默认或别的会话。

聊天状态按 session + profile_id/model_id 保存覆盖偏好；切模型恢复该模型的选择或 inherit，不将 A 的 max 带给仅支持 high 的 B。全新会话继承模型设置，不用全局 localStorage 一个字符串污染所有模型。有效偏好可按现有 session preferences 存储；保存前校验，换连接失效不能误投。

重新生成保留原请求强度快照，用户明确 override 时才变更；会话刷新、重连、分支、题目跟进请求一致。turn request snapshot 可存 requested/effective/映射来源以便验收，不记密钥；不要为了本阶段重写历史消息或数据库全量迁移。已有 config 的 extra=forbid 不能被随意绕过；使用正式运行时字段，不增加任意 kwargs 通道。

测试至少捕获 services complete/stream 和主 agentic 请求，以及题目跟进真实发出一轮，证明 UI 值最终进入正确 provider 字段。Auto、off、minimal、medium、xhigh、ultra 的相异语义都要有反例。

## C6 默认模型 API 与引用

默认值继续存现有 services[service].active_profile_id/active_model_id；不得新建第二份 preferences.default_models 与其竞争。

新增管理员 `GET /api/v1/settings/default-models` 和 `PATCH /api/v1/settings/default-models`，返回已保存引用与可选摘要及 opaque revision。PATCH 仅接收 revision + 被修改服务的引用；不得接受 key/base/model参数/任意 catalog。search 只选 profile_id，其余七服务要求该 profile 下真实存在的 model_id。

```json
{
  "expected_revision": "opaque-revision",
  "defaults": {
    "llm": {"profile_id":"deepseek","model_id":"flash"},
    "stt": {"profile_id":"aliyun-asr","model_id":"asr-flash"}
  }
}
```

- 后端重新载入当前已保存 catalog，在原写入同步机制/有约束事务中只 patch 默认引用，保留所有其它模型、顺序、参数、密钥、维度、显示偏好与未知 legacy 字段。revision 不匹配或候选已删返回 409，非法跨 profile 引用 422，普通用户 403。空请求/未知服务/不相关字段拒绝，重复同值更新可幂等。
- 并发普通 catalog 保存和默认更新不能丢配置；需要源码服务层统一读校验写同步，不只在路由先比较 hash 再裸 save。不得用恢复旧 catalog 处理冲突。空服务显示“未配置”，不为不存在模型发请求；不新增启用/禁用服务语义。
- 当前 ModelCatalogService 已有锁内 update(mutator)，应优先复用：在 mutator 内核对 revision 并 patch 引用。新 UI 的普通 Save/Apply 同样携带对应已保存 revision，服务端在相同锁内做比较后保存，冲突保留 draft。旧客户端不带 revision 的原兼容行为如实保留，不声称具有跨进程、所有旧客户端的无条件事务保证；不要为本功能重写通用存储层。
- managed/read_only 模型可作为合法默认引用（若现有策略允许），但不得改其只读配置或 OAuth 登录状态。隐藏候选遵守现有 default visibility 规则，不能借新接口绕过禁止隐藏当前默认的规则。
- 成功后更新运行时缓存和 options；已开始 turn 的快照保持，默认更新影响后续未显式选模型的调用。失败不得乐观显示成功或切换真实默认。
- 默认 embedding 的真实用户变更沿用原索引签名保护及清楚提示；保存默认引用不立即发 embedding、不重建索引、不改已有索引。开发阶段仅隔离 fixture 演示。

## C7 默认页与编辑选择分离

新路由 `/settings/default-models` 为设置→模型固定首项，中文 LLM 页、导航、面包屑统一“大语言模型（LLM）”。默认页列一个默认 LLM，embedding、搜索服务、STT、TTS、视觉、图片、视频按现有服务支持显示；不新增标题、搜索词、OCR、重排独立模型服务。

页面使用已保存 catalog 的可选项，未保存新模型提示“先保存模型配置”。本页清楚显示当前已保存默认与拟修改项，提供“保存默认设置”/取消，调用专用 PATCH。进入此页/选下拉/取消都不改变默认。错误保留选择并解释，不吞 409。

SettingsContext 增加按服务的本地 editing_selection。ServiceConfigEditor 的 profile/model tab、新增/删除、测试连接、目录添加、参数更新预览、重命名等都改用本地编辑选择；不要继续依赖 draft.active_* 定位。点击浏览、测试或切换服务不更改默认。

仅首次配置空服务可按原系统规则初始化其首个默认，界面明确提示；新增后续模型绝不替换已有默认。删除真实默认必须提示先换默认/或在同一明确操作指定替代，不能把误点编辑当授权。managed 只读、诊断结果归属、迟到响应、保存失败后 draft 保留均不得退化。

保留“应用”，说明其为保存并使配置生效；它不再把当前编辑模型暗设默认。原 Save/Apply 仍保存用户真正修改的配置，但默认引用只来自默认页或明确的删除替代/首次初始化操作。默认页 PATCH 成功时仅合并服务 active 引用到本地 draft，不能把其它页面未保存参数清掉或一并提交。设置跨页面 dirty 状态和返回导航保持可理解。

普通用户不显示管理员默认设置修改入口；聊天仍可选自己获授权模型与强度。系统默认与个人可用默认现有授权退路保持，不把未授权系统默认暴露为可调用选项。

## C8 交付边界

仅任务白名单源码及新 MM-R3 证据根。先对真实六树做 opaque inventory；不用真实 key/catalog 当 fixture，不运行真实厂商推理或学校接口，不停止用户服务，不重写 MD-R2/第一阶段历史。测试走 scripts/run_tests_isolated.py 和已安装浏览器隔离 wrapper。

依赖按卡推进，无逐卡审批。局部必要接缝记录原因后处理；新增独立产品功能不混入。最后统一交付所有用户行为、协议请求、并发默认更新、权限、数据不变和可重建源码证据。

# MD-R2 数据与行为契约

用户本次明确授权规划：修复所有普通 LLM 供应商的查询策略，阿里 LLM 可见可用，自定义网关查询，官方参数默认填入，自定义名称显示。此文件规定后续 Harness 的实现边界。执行中常规设计选择自行处理，整阶段完成后统一交付。

## C1 身份、协议与全量覆盖

- registry 的供应商身份、推理 backend、目录 adapter 分开。新增显式目录策略表（可用独立 `provider_policy.py`，不把网络请求塞进 registry）。每个 LLM 供应商必须命中策略；测试对比当前 registry 的完整 name 集合，不能只测 DeepSeek。
- 不将 DeepSeek/OpenRouter/所有 compatible 供应商规范成一个身份来绕过凭据保护。修正 discovery 当前把 openai/custom/vllm/lm_studio 合并为同一 canonical_binding 的隐患：缓存/凭据身份用真实供应商和有证据的同厂商别名，transport family 单独计算。旧缓存使用新的 policy/schema 命名空间，不读取即重写真实配置。
- LLM `dashscope` 保持稳定；显示“阿里云百炼（千问 / DashScope）”，接受 aliyun/alibaba/bailian 等作为其真实别名。别名处理不能使 STT/embedding 的 aliyun 变成其他推理适配，不扫描迁移旧 profile。
- 27 个普通 compatible backend 走通用目录或其已知增强策略；3 个 Anthropic backend 走 Anthropic directory；Gemini、Azure、阿里、SF、Ollama 各走明确策略；3 个托管/OAuth 维持专用流程。矩阵必须覆盖这 38 个现有名字及实际公共别名。
- Codex、CodeBuddy、Copilot 不被通用 API key 查询接管，不增加登录/刷新 token/读用户 OAuth 文件；保持专用管理行为和 managed/read_only 限制，并如实标出专用入口。不得为“31 个都修了”发送 OAuth token 到 /models。
- 推理已支持而目录端点不存在，是 endpoint 能力不足。返回有语义的目录不可用状态；不再由供应商名字白名单直接拒绝普通兼容服务。不得把 401/403/timeout 当目录不支持，不得把 404 当成功空目录。

## C2 用户网关、路径和凭据

兼容默认目录为 `<有效 API base>/models`，读取 data[] 或已支持裸列表；preserve base 的代理前缀、端口、query、API version 和 extra_headers。base 是 `/school/ai/v1` 时应访问 `/school/ai/v1/models`，不是站点根 `/v1/models`。

允许新增 `CatalogProfile.model_directory_url?: string`，值为**完整目录 URL**，用于推理与目录路径不同的网关或阿里业务空间。Connection、前端连接快照、服务器指纹、cache key、masked-key revision 检查都必须纳入该字段，空值保留现有行为。禁止将该字段当 chat URL 或修改推理 base_url。

默认仅在 404/405 时按已知协议作**至多一次**同 origin 路径回退：追加/移除末端 /v1，保留代理前缀；不为已有 /v2、/v3、/v4、业务路径、明确 model_directory_url 随意删改路径。成功后只报告解析目录路径，不偷偷保存新的推理 base。401/403/429、TLS、超时、JSON 损坏不触发路径轮询。

- 不跟随跨 origin redirect；不自动探测其他域名，不发送学校 key 到模型原厂。
- 改供应商身份、推理 origin 或目录 origin 时，沿用的 masked key/敏感 headers 必须触发 409 CREDENTIAL_REENTRY_REQUIRED；用户显式输入凭据并查询后才可到新 origin。已保存的明确目录配置可按原样使用。显式 cross-origin 目录配置需要该认证边界，不加默认跨域例外。
- model_directory_url 未指定时只能按已有官方、同 origin 路径映射使用阿里 native endpoint。北京老域名目录 404 应提示填写业务空间目录地址，不能伪造 WorkspaceId，也不能将阿里其他地域 key 搬过去。
- 自定义私网/localhost 允许，保留现有管理员权限。绝不开放普通用户目录管理权，不引入浏览器直接调用厂商的 CORS 路径。
- key 是不透明字符串；mask/null/空串、敏感 extra_headers 恢复语义保持 MD-R1。请求 URL 中敏感 query、上游 body、认证头值不进日志/错误/缓存。
- 总时限 30 秒、4 并发、100 页、10000 模型、2MiB/页、16MiB/刷新不扩大。分页/回退共用预算；不为每个模型发一次请求，不调用推理/向量化/下载来猜参数。没有结构化 metadata 的服务器允许部分字段未知。

## C3 原生目录的确定规则

- Anthropic（anthropic/custom_anthropic/minimax_anthropic）：按有效 base 拼 models，使用原生认证和版本配置；额外 headers 采用已有显式优先级，不能静默覆盖用户版本。支持 after_id/has_more/last_id，检测游标停滞。display_name → name。原生 max_tokens 为厂商最大输出容量，不误作用户预算。旧版本缺 metadata 字段仍能列出模型。兼容网关可用，目录不存在明确回退手填；不改 Messages 推理版本。
- Gemini：仅识别的官方域名允许从已知 compatible 路径同 origin 映射到 v1beta/models；用户自定义代理优先明确目录地址，不将凭据送 Google。解析 models[]/nextPageToken、supportedGenerationMethods。resource_name 原样留作元数据；转换到兼容推理 model 时仅移除协议规定的 `models/` 前缀，不破坏版本。只有 embedContent 的模型不得列为 LLM；generateContent 不能单独证明是普通文本 LLM（也可能是音频/图片用途）。inputTokenLimit 是输入上限，不冒充总上下文。
- Azure：v1 base 支持 /openai/v1/models 与 api-key；旧 deployment URL 与资源根按明确策略处理，不能盲目 append /models。保存 API version，不把它硬转 v1。目录 offering 不等于已部署调用 ID；无法证明 deployment_name 时，候选给出 deployment_mapping_required，并允许用户明确填写部署名；已有配置与历史引用不改。无目录时保留部署名手填，不请求 ARM、不新增管理凭据。
- DeepSeek/OpenRouter/Mistral/Groq 等结构化扩展走已核验 JSON 字段映射；其他兼容服务仍可列目录，没有声明的类别为 unknown，可批量确认用途，不凭某个 model ID 在别处出现就断言能力/参数。
- 阿里按 capabilities、inference_metadata、inference_provider 与 routing 共同判定。阿里云目录里的第三方托管项、实时 ASR 等不自动标为项目已支持。

## C4 规范化参数：可选、精确、有来源

现有 HTTP response `schema_version=1` 保留（兼容旧客户端）；新增 `metadata_schema_version=1` 及可选 `parameters`，旧字段 context_window 若存在必须与 parameters 中同名字段一致。不复制任意上游 JSON。

```json
{
  "id": "deepseek-flash",
  "name": "DeepSeek-V4.1-Flash",
  "services": ["llm", "vision"],
  "classification": "provider",
  "runtime_compatibility": "supported",
  "reason_code": null,
  "source": "remote",
  "callability": "not_tested",
  "context_window": 1048576,
  "metadata_schema_version": 1,
  "parameters": {
    "context_window": 1048576,
    "max_output_tokens": 393216,
    "input_modalities": ["text", "image"],
    "output_modalities": ["text"],
    "provenance": {
      "context_window": {
        "kind": "provider_api",
        "source_url": "https://api.deepseek.com/models",
        "checked_at": "2026-10-24T00:00:00Z",
        "json_path": "data[].context_window"
      },
      "max_output_tokens": {
        "kind": "provider_api",
        "source_url": "https://api.deepseek.com/models",
        "checked_at": "2026-10-24T00:00:00Z",
        "json_path": "data[].max_output_tokens"
      },
      "input_modalities": {
        "kind": "provider_api",
        "source_url": "https://api.deepseek.com/models",
        "checked_at": "2026-10-24T00:00:00Z",
        "json_path": "data[].input_modalities"
      },
      "output_modalities": {
        "kind": "provider_api",
        "source_url": "https://api.deepseek.com/models",
        "checked_at": "2026-10-24T00:00:00Z",
        "json_path": "data[].output_modalities"
      }
    }
  }
}
```

`parameters` 可含：context_window（输入输出总容量）、max_input_tokens、max_output_tokens、max_reasoning_tokens、default_dimensions、supported_dimensions（去重正整数列表，至多 128 项）、supports_dimensions_parameter（显式 boolean）、input_modalities/output_modalities（已知枚举）。缺失值省略，null/0/负数/boolean/小数/NaN 不变成数字；仅接受 JSON 安全正整数。上限缺失不当 unlimited。不能递归搜索第一个同名字段。

每个实际返回字段都要求 provenance；kind 固定 provider_api / endpoint_api / official_docs。官方精确域名/已知协议才能标 provider_api；自定义学校网关即使 model ID 是 deepseek-flash 也标 endpoint_api。source_url 仅作为来源展示，剥离 userinfo/query/fragment，不作为下一次自动请求目标；禁从响应里的链接取回认证元数据。checked_at 为在线抓取时刻或文档条目最后核验时刻，不伪造为本次刷新。来源路径文本有长度限制、按纯文本渲染。

官方文档补充使用小型显式 JSON 数据文件，按 provider + 精确 model/明确 alias + region + mode 限定，含 URL、核验日期和字段；不抓全量网站、不新增 models.dev/LiteLLM 依赖、不拿 HuggingFace 原始模型容量替代云 API 限制。最低覆盖 DeepSeek 两型号、阿里一个可文本测试的 Qwen（如 qwen-plus）、阿里 text-embedding-v3/v4，以及当前 Qwen embedding 已有映射中能由官方证实的项目。其他型号没证据留空。

同一有效 endpoint 的在线值优先于其文档资料；学校网关的上限优先于原厂模型上限。对于第三方网关，只有它明确声明 upstream provider/model 关联且有受控映射，才可把原厂资料作为参考；不依靠 ID 猜上游，不用原厂较大值覆盖网关较小值。模式限定值不能升格为所有模式通用值；无法判定当前模式时使用有依据的保守公共上限或未知。

文档补充失败、可选字段非法不使已成功取得的模型目录整体消失；展示参数不完整，不假报“全部参数已获取”。字段冲突/无效须能被回归测试定位。数值不错误换算为 128k 或将 1000000 与 1048576 混同。

## C5 缓存与参数时效

- 模型目录及其参数同条缓存、同凭据/owner/service/profile/完整 endpoint/目录 URL/policy version 指纹；不另建不隔离的全局 model-ID 参数缓存。
- 缓存结构扩展须保证全字段 round-trip；metadata parser 不能丢 provenance/维度。保留 MD-R1 的 single-flight、取消清理、失败冷却、1h/5min TTL、7d stale 和旧目录保留。
- 旧缓存可失效后重查，不更新真实 catalog、不把旧缓存字段缺失解释为“厂商不支持参数”。升级后第一次查询要能获得新元数据，不能被仍有效的旧参数缺失缓存吞掉。
- 刷新失败可展示旧参数，但标 stale 和原 checked_at；不能用刷新按钮把旧资料时间改成当前时间。

## C6 默认填入、人工修改和稳定引用

CatalogModel 继续使用稳定内部 id、model 调用 ID、name 显示名称。扩展：

- `provider_metadata?: {schema_version:1, parameters:...}`：厂商/网关能力事实和来源；不是任意请求 kwargs。
- `max_tokens?: string`：用户可改的 LLM 默认输出预算。
- `parameter_overrides?: {context_window?:boolean,max_tokens?:boolean,dimension?:boolean,send_dimensions?:boolean}`：true 表示人工覆盖（包括用户主动清空），false 表示自动值。旧模型没有标记且已有非空值，一律视为人工设置。
- 沿用 context_window/source/detected_at、dimension、supported_dimensions、send_dimensions 等既有字段；UI/后端只在用户保存 draft 时持久化。新增字段前后端类型与校验一致，不在读取时为旧数据批量补字段。

新添加 LLM：总 context_window 有官方值就填该值；厂商最大输出同时填 provider_metadata.parameters.max_output_tokens，并初始化 max_tokens 为该上限，override=false。只有输入上限时记录 max_input_tokens，UI 显示输入上限，不把它冒充总容量。无最大输出时保持旧 4096 回退，显示未知，不声称 4096 是官方值。

新添加 embedding：dimension 采用厂商 default_dimensions；supported_dimensions 填允许列表，不能取列表最大值冒充默认。知道 default 但不知道 choices，可以填默认并保留未知 choices。只有 choices、没有默认时保持维度未定，提示选择；不猜第一个或最大值。send_dimensions 只有已证实协议支持时初始化 true，明确不支持时 false，未知时保留既有协议默认语义，不能仅因获取到维度就强行 true。

参数 API 的 supported_dimensions 是整数数组，旧 CatalogModel.supported_dimensions 是 CSV 字符串；仅在 catalog/UI 接缝显式转换，排序/去重不丢值，不改变旧 runtime 的兼容字段类型。上下文和 max_tokens 的旧 catalog 字符串也只在接缝与规范化整数相互转换。

重复添加同 profile 同 model：复用旧内部 id，不改 name/active/授权/显示偏好/参数。目录刷新不更新已配置模型；新增“更新官方参数”显式操作，把差异预览到 draft：自动值和空缺值可更新，人工覆盖默认保留，用户明确选择恢复自动才替换。取消预览不改 draft；保存失败保留 draft。

模型调用 ID 或连接身份改变时，旧模型 metadata 不能沿用到新目标。清除失效事实及仅由旧事实自动生成的值，保留人工值并提示重新核对；迟到响应不得把 A 的参数填到 B。name 重命名不改变调用 ID、元数据、历史引用或授权。

新增/查询模型不能自动改 active 模型或删除候选未包含的配置。已有 embedding 维度/模型不因获取或刷新而变化，不触发索引重建。用户主动保存确实改变维度的操作走原签名/重建提示，不绕过保护。

## C7 参数确实影响运行时

1. `provider_runtime.ResolvedLLMConfig`、LLMConfig/Update、scoped selection、factory 重建 config、core/agentic client 均保留目标模型的预算/容量字段。同请求上下文中的显式 model 覆盖不能继承另一个模型的 metadata。
2. 预算优先级：业务显式 max_tokens/max_completion_tokens（含原有摘要/出题等较小预算） > 选中模型 max_tokens > 旧默认 4096。显式 None 与省略按既有 API 语义明确处理。最后与已知厂商 max_output_tokens 取小；不将较小业务预算放大成厂商最大输出。超范围的手工预算在保存 UI 给出清楚校验，运行时再防御。
3. 沿用实际 provider 的 max_tokens/max_completion_tokens 等协议映射；容量元数据绝不整块传到 SDK。对未知限制保持兼容，不把 max_input_tokens 填到 max_tokens。
4. 总上下文模式下，输入 + 实际输出预算 + 既有安全余量不能超出上下文；长历史须按原压缩/裁剪流程处理，不能因默认输出预算较大制造上游 400。输入上限单独约束输入，不能把 max_input_tokens/max_output_tokens 相加伪造 context_window。禁止大规模重写会话压缩；必要仅修参数接缝及清楚的空间不足错误。
5. 保留现有运行时上下文安全上限 1000000，UI 区分“厂商容量”和“项目有效预算”；没有用户要求不要借此扩到任意大容量。metadata 1048576 必须按原数保存和展示，安全预算可取较小值。
6. 两条调用路径分别测试：普通 chat/stream factory 与主聊天 core/agentic client。不能只测配置对象。用隔离 mock provider 捕获实际请求证明参数生效；不做 393216 token 的真实生成测试。

## C8 自定义名称、刷新和权限

聊天下拉行及选中按钮统一 `trim(model_name) || model`；tooltip 可显示 name、model、profile。重名时用供应商/profile 辅助区分，不通过改内部 ID 解决。隐藏但当前已选模型、主聊天、题目跟进聊天均遵守。普通用户保留已有授权别名规则，不能显示未授权模型或额外配置。

设置 Save/Apply 成功后使相关缓存失效，并使仍挂载的 picker 在返回/重新激活时获得新名称；失败不能假刷新成功。处理旧未完成 options 请求在保存后回写旧缓存的竞态（只在本资源所需范围修复）；不改全项目通用缓存语义。现有 active/history 保持稳定。

## C9 交付与真实数据

本阶段实际写入仅在任务卡白名单生产源码、新测试和新 evidence 根。真实六树仅做 opaque hash，禁止 fixture 拷贝真实 key/catalog。不得复写 S14 例外基线或旧验收，不 reset/clean 工作区。

联网与付费推理不作为 worker 自动验收。学校端点信息尚未提供，使用本地 fixture；阿里“添加到 LLM 供应商”是入口、别名、协议和参数贯通，不自动复制 ASR 密钥、创建真实 profile、切换默认模型。最终报告列代码策略覆盖、隔离测试覆盖和真实厂商验证三种证据，缺少的如实报告，不逐卡停工。

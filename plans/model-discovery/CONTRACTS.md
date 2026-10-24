# MD-R1 数据与行为契约

## D1 范围与不变量

- 服务枚举固定为 `llm | embedding | stt | tts | imagegen | videogen | vision`；`search` 不显示模型查询按钮，API 收到该值返回 422。
- 七类服务都提供统一候选管理入口。首批目录适配：阿里云百炼、硅基流动、OpenAI-compatible、Ollama。其他供应商必须明确显示不支持在线查询，并保留手工配置；不能谎称全厂商已适配。
- 供应商目录、已配置模型、默认项、显示偏好、授权是不同数据。目录查询不得写 `model_catalog.json`；所有添加/显示变更先进入 draft，由现有 Save/Apply 保存。
- 本阶段不新增 ASR/TTS/生图/视频等推理适配器。目录中的模型即使厂商提供，也可能需要项目尚未实现的协议。
- 普通用户不获得目录查询及管理员模型配置权限。Codex OAuth/CodeBuddy 保持原专用管理和身份边界；其 managed/read_only profile 不进入通用自动查询/添加流程。
- 真实数据、历史基线、已封存验收、当前阿里云 ASR 和原硅基流动配置保持不变。只有隔离测试产生的配置和缓存允许写入。

## D2 新 API 与凭据解析

新增管理员接口 `POST /api/v1/settings/model-discovery`。保留旧 `/fetch-models` 及现有专用 OAuth 接口兼容；普通供应商的新 UI 使用新接口。不要借此重写推理 client。

```json
{
  "service": "stt",
  "profile_id": "profile-1",
  "mode": "cache_first",
  "connection": {
    "binding": "aliyun",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "***",
    "api_version": "",
    "extra_headers": {}
  }
}
```

- `connection` 可省略：按本服务的 saved profile 解析；`profile_id` 不存在返回 404，不回退到其他 profile/service。
- 未保存草稿可显式提交 connection；`profile_id` 可空。`mode` 仅 `cache_first | refresh`。
- 明文密钥作为不透明字符串处理，包含点号也必须完整保留。`null`/省略表示沿用同服务同 profile 的已存值；空字符串表示清空；`***` 表示恢复已存值。未保存 profile 的 mask 返回 400。
- 恢复所有敏感 extra_headers 的 mask；不把 `***` 发到上游。复用 `restore_catalog_secrets` 的行为，但只处理目标服务/profile，不能给响应附带其他配置。
- 使用已存凭据且 connection 改变供应商身份或 URL origin 时，返回 409 `CREDENTIAL_REENTRY_REQUIRED`；要求用户重新输入凭据后显式查询。不能把旧密钥自动发给新域名。
- 仅 HTTP/HTTPS，禁 userinfo/fragment；保留合法路径、端口、查询参数和 API version。支持管理员明确配置的 localhost/局域网服务，不加阻断 Ollama 的全局私网禁令。
- 不跟随跨 origin 重定向，不把认证头转发到另一台主机。上游响应文本、密钥、认证头和含敏感参数的 URL 不进入日志/错误/缓存。

## D3 响应、分类与错误

```json
{
  "schema_version": 1,
  "service": "stt",
  "profile_id": "profile-1",
  "status": "ok",
  "models": [{
    "id": "qwen3-asr-flash",
    "name": "千问 ASR Flash",
    "services": ["stt"],
    "classification": "provider",
    "runtime_compatibility": "supported",
    "reason_code": null,
    "source": "remote",
    "callability": "not_tested"
  }],
  "cache": {"state": "miss", "fetched_at": "2026-10-23T00:00:00Z", "expires_at": "2026-10-23T01:00:00Z"},
  "complete": true,
  "error": null
}
```

- `status`: `ok | empty | unsupported | error`。有旧目录而刷新失败：`status=error`，保留 models，`cache.state=stale`，显示失败提示。不是成功刷新。
- `cache.state`: `miss | fresh | stale | none`；无成功缓存时时间可 null。空目录是成功结果，不能当 401，也不能冒充 unsupported。
- models[].id 是厂商调用名称，**不是** CatalogModel.id。按精确字符串、同 profile 去重，保留大小写和合法 `/ : . -`；拒绝控制字符，id/name 各限 512/256 字符，输出按普通文本渲染。
- `services` 为厂商声明/有依据的类别列表；无法分类为 `[]`。`classification`: `provider | curated | unknown`。`source`: `remote | preset`。预置项必须标明来源，不冒充账号目录。
- `runtime_compatibility`: `supported | unsupported | unknown`，只表示项目协议适配判断；`callability` 固定 `not_tested`。目录查询不证明付费状态、权限、稳定性或质量。
- 明确不同类别的模型不放入当前类别普通列表；未知类别放在单独的“类型待确认”区，用户明确确认当前用途后可加入。明确 unsupported 项禁一键添加，提供理由；保留原高级手填入口。
- 可选 `context_window` 为正整数；不复制任意上游字段。不自动填写/覆盖 embedding 维度、音色、视频参数、用户别名或既有模型参数。
- error 固定结构 `{code,message,retryable}`，message 为项目文案。code 至少：`AUTH_FAILED, FORBIDDEN, RATE_LIMITED, TIMEOUT, UNAVAILABLE, UNSUPPORTED, INVALID_RESPONSE, INCOMPLETE, CACHE_IO`。
- 本地请求/权限错误使用 400/401/403/404/409/422；已合法派发后的上游结果使用 200 envelope，依据 status/error 判断。API 前端测试必须检查语义，不只检查 HTTP 200。

## D4 目录适配矩阵

### 阿里云

- 兼容 `dashscope`（LLM）、`aliyun`（embedding/STT）现有身份。只有已识别的官方地域域名才做阿里专用路由；不能把自定义代理 host 偷换成官方 host。
- 官方目录为 `/api/v1/models`，解析 `output.models[]`；分页参数 `page_no/page_size`。与推理 `/compatible-mode/v1` 不同；基于同 origin 的已知路径映射，单测覆盖旧北京/国际域名和业务空间专属域名。未知路由返回 unsupported，不能猜业务空间 ID。
- 旧域名目录若实际返回 404，报告该目录路径不可用/可能需业务空间域名；不得伪装为账号没有模型，也不得因推理接口可用就声称目录接口实测通过。
- 类别依据官方 capabilities 映射：TG/Reasoning→llm，TR/ME→embedding，VU→vision，ASR→stt，TTS→tts，IG→imagegen，VG→videogen。实时能力不能映射为已支持的非实时协议。
- 还须核对 inference_provider/routing：目录中的第三方托管项不能自动宣称可通过当前百炼推理地址使用。
- 当前阿里 STT 只对已实现的 `qwen3-asr-flash` 判定 supported；Filetrans、Fun-ASR、Realtime 或其他未经适配的系列不得因含“ASR”就标 supported。其他类别同样以实际 registry/adapter 为准；不新增尚无推理实现的供应商下拉选项。

来源：[阿里云目录接口](https://help.aliyun.com/en/model-studio/list-models)。

### 硅基流动

- `/models` 支持 type/sub_type。已明确文档化的 sub_type：chat、embedding、speech-to-text、text-to-image、text-to-video，分别用于对应服务；不把 reranker 当 embedding。
- TTS、vision 若当前接口无精确类型，不虚构筛选值；用维护的小型、可追溯预置分类或 unknown 区，并如实显示。不要把未分类模型全部认作 LLM。
- 既有 OpenAI-compatible 推理适配仍是运行协议边界，不新增音色/生成协议。

来源：[硅基流动目录接口](https://api-docs.siliconflow.cn/docs/api/models-get)。

### OpenAI-compatible 与 Ollama

- 通用兼容目录读取 `<api-base>/models` 的 `data[]` 或现有兼容裸列表，使用有效认证、extra_headers/API version。无能力字段时不依据 id 做无来源的确定分类；可用明确 provider 的小型已知映射，其他归 unknown。
- Ollama 查询原生 `/api/tags`，根据配置移除明确的 `/v1` 后缀，保留代理前缀；解析 models[].name/model。只列已安装模型，不查询云模型库，不 pull/download，不调用 generate。
- 不为每个模型发一次推理或 metadata 请求。Ollama 未提供能力的条目可在 unknown 区由用户确认。

来源：[Ollama 本地目录](https://docs.ollama.com/api/tags)。

### 共同资源界限

缺少在线目录/能力信息时，可用现有 registry.default_model 等有依据的项目预置候选，source=preset、callability=not_tested；不能把回退目录伪装成实时查询成功。禁止为本阶段接入第三方全量模型库依赖。

单次刷新总截止 30 秒、最多 100 页/10,000 模型、单页 2MiB/累计 16MiB，目录网络并发最多 4。
分页必须去重并检测游标/页码不前进；到上限为 INCOMPLETE，不能以 complete=true 缓存半份目录覆盖完整旧目录。
有证据的分页协议才继续翻页；不发明通用参数。无分页协议且返回合法完整列表视为 complete=true。

## D5 缓存与首次自动获取

- 服务端持久目录缓存：`get_path_service().get_user_root()/cache/model-discovery/`；不是 model_catalog 的一部分，也不写浏览器 localStorage 密钥。
- namespace 包含 workspace/owner、service、profile_id、canonical binding、完整有效端点、api_version、凭据摘要和按名称排序的有效 headers 摘要。缓存里只存不可逆连接摘要、净化目录、状态和时间，不能存原始凭据或原始 header 值。凭据摘要不返回浏览器、不写日志。
- 同 URL 不同 key、不同服务/profile/owner/header/API version 不得串缓存；连接变化时旧响应不得进入新连接视图。
- 完整非空成功缓存 1 小时；完整空目录缓存 5 分钟；失败/不支持的自动获取冷却 60 秒。手动 refresh 可显式重试；同连接并发仍合并为一次实际刷新。
- 同连接成功旧目录最多保留 7 天，刷新失败可带 stale 结果和错误；不能把失败时间更新成 fetched_at，也不能用空错误覆盖旧成功缓存。
- 缓存文件原子写、进程内 single-flight/互斥；损坏缓存忽略并重新获取。写失败给出 CACHE_IO 提示，本次成功目录仍可用，不把缓存故障伪装成厂商故障。容量最多 128 个连接，按最近使用清理旧项；文件权限 0600、目录 0700。
- 当前管理员打开某个**已保存**普通 profile 的模型区域时，按连接发一次 cache_first；无缓存则自动获取。保存新连接后，其首次进入该区域也会自动获取。不是应用启动时扫描全部账号。
- 输入 key/URL 期间不自动发请求；未保存草稿仅显式“查询模型”发送。保存前后同连接不重复取目录。缓存过期只有再次访问该区域或手动刷新才取，不做定时后台轮询。
- React 重挂载、StrictMode、切换 tab 都不得形成请求风暴；挂载/本地重绘不解除失败冷却。提供明确刷新按钮。

## D6 候选管理、并发与保存

- 共用候选面板支持名称/ID搜索、类别筛选、来源/协议状态提示、勾选和“添加所选”。候选选择是面板临时状态；确认添加后才修改设置 draft，Save/Apply 后持久化。
- 新模型创建稳定内部 id（uuid 等），写 provider id 到 model 字段；同 profile 同 model 已存在时复用原项，不复制，不改其内部 id/别名/参数。其他 profile 同名是合法独立项。
- 刷新和自动获取永不改 profile.models/active ids，也不把结果默认全选。尚无 active model 的空配置，查询后仍为空；用户添加后可使用现有首次配置选择规则。
- 当前 provider/profile/service/draft connection 改变时，取消或丢弃迟到响应。需要 generation/request token + 连接身份校验；只检查 binding 不够。保存期间/保存返回后的旧请求也不能覆盖 draft。
- 删除 profile、密钥轮换、刷新失败、空列表、后台缓存完成均不触发目录向 catalog 的自动同步。
- 查询失败保留用户未保存更改和上一次候选；显示重试/手工添加，编辑区其他功能可用。

## D7 聊天显示与权限

- 新增 CatalogModel 可选 `visible_in_picker: boolean`，本阶段只对 LLM 使用；缺省 true，旧数据不迁移、不因读取补写字段。其他类别保持已有选择器行为。
- 新加入 LLM 默认显示。设置页已配置列表提供显示开关；隐藏保留 CatalogModel、API id、参数和 grants，不能以删除实现隐藏。
- 禁止隐藏当前全局默认模型：UI 禁用并解释先换默认；PUT/Apply 对明确隐藏当前默认的请求返回 400、保存前失败。绝不能自动切换默认来迎合隐藏操作。
- 显示是部署管理员管理的全局配置，本阶段不新增普通用户个人偏好存储。当前会话已选但后来隐藏的模型继续显示为“当前模型（已从列表隐藏）”等可解释状态，仍可继续使用；不自动切换。
- `/settings/llm-options` 的新候选列表过滤 hidden；授权解析、has_capability_access、apply_allowed_llm_selection、运行时按 id 解析不得把 hidden 解释成撤权。普通用户依旧先授权后展示；个人 OAuth 模型保持原规则。
- 向原响应增加 `hidden_options: LLMOption[]` 和 `has_usable_models: boolean`：前者只含本账号**已授权**但隐藏的脱敏条目，供展示当前已选项，不混入新候选；后者依据过滤显示前的已授权可用模型计算。保留原 active/options 字段。老 fixture 缺新字段时，前端按 hidden_options=[]、has_usable_models=options.length>0 兼容。
- `CapabilityAccessContext` 当前用 options.length 判断功能权限，必须改读 has_usable_models，不能因仅有的获授权模型被隐藏而锁死既有会话。ModelSelector 只在当前值命中 hidden_options 时显示该当前项，不重新列出全部隐藏项。
- 不要直接给所有 `list_llm_options` 调用加过滤而破坏授权/既有会话；可新增 presentation-only helper，在 UI 列表边界调用。非管理员 options 中也必须尊重相应管理员模型的显示标记，但不能暴露未授权 id。
- 保存成功后复用 invalidateLLMOptionsCache；保存失败保留 dirty draft，展示错误，不清空 catalog。

## D8 交付范围边界

不做全厂商全协议适配、自动增删模型、自动变更默认、自动授权、全局后台 SWR、逐模型可用性压测、下载模型、模型价格计费系统。unknown/unsupported 是合法但必须可解释的结果，不能借此把已明确要求的首批适配全部留空。
实际已支持组合须在最终 report 中逐项列出，并区分 remote/preset/unknown/unsupported。目录能力测试用 fixture，不能替代真实推理质量承诺。

# MD-R2 调研与证据

核对日期：2026-10-24，Asia/Shanghai。供应商策略属于代码审计；没有全厂商真实凭据，不作全厂商联网成功声明。

## 本机客户端的通用方案

Chatbox 源码根 `/home/albert/chatbox/work/cb`，只读：

- `src/shared/providers/definitions/models/custom-openai.ts` 的 listModels 调用 fetchRemoteModels。
- `src/shared/models/openai-compatible.ts` 的 fetchRemoteModels 请求 `${apiHost}/models`，Bearer 加 extraHeaders，读取 data[]。
- `src/shared/providers/definitions/models/custom-claude.ts` 使用自定义 apiHost、`/models`、x-api-key 和 anthropic-version。
- `src/renderer/packages/model-setting-utils/base-config.ts` 合并本地、远程配置、供应商目录，并有 models.dev 回退/补充；显示列表不全代表刚刚联网确认。
- `src/shared/providers/definitions/deepseek.ts` 有 V4 Pro 预置；`models/deepseek.ts` 也有官方 GET /models。

Hermes 源码根 `/mnt/c/Users/17261/AppData/Local/hermes/hermes-agent`，只读：

- `hermes_cli/models.py:probe_api_models` 先查用户 base，再试 base±/v1 的目录；支持 Bearer、Anthropic 认证和 extra_headers。
- 同文件 cached_fetch_api_models 按连接凭据隔离缓存；列表获取不是模型推理测试。
- `hermes_cli/model_switch_providers.py` 在自定义配置和 picker 中复用这些路径。

可复用的是“按协议对接用户指定 endpoint”的思路，不要复制吞错为空、无差别路径探测或将 models.dev 当官方参数的做法。学校网关没有提供地址和凭据，本阶段使用含代理前缀、别名、私网地址和自定义头的隔离服务验证，不能宣称已经实测该校系统。

## 官方结构化元数据

| 来源 | 已确认内容 | 本阶段用途 |
|---|---|---|
| [DeepSeek /models](https://api-docs.deepseek.com/api/list-models/) | name、context_window、max_output_tokens、input/output_modalities、effort | 直接解析；区分 Flash/Pro 能力，不靠深度求索名称一概授予视觉 |
| [阿里模型目录](https://help.aliyun.com/zh/model-studio/list-models) | output.models 分页，model_info.context_window/max_input_tokens/max_output_tokens/max_reasoning_tokens；北京等地域要求业务空间域名 | 专用目录、来源与地域；旧北京域名不可凭空拼 WorkspaceId |
| [阿里 qwen-plus](https://help.aliyun.com/zh/model-studio/qwen-plus) | 官方模型、地域、模式差异；页面当前明确列上下文/输入/输出 | 最小阿里 LLM 文档预置，按地域/模式限定，编写时再核对相应段落 |
| [阿里 Embedding 兼容接口](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai) | text-embedding-v3/v4 默认 1024，支持特定维度；多模态 embedding 非同一兼容协议 | 文档参数条目、dimension 默认/choices、请求参数支持，不能取最大维度作为默认 |
| [阿里向量模型汇总](https://help.aliyun.com/zh/model-studio/embedding-rerank-model/) | 各系列维度、默认值和输入限制不同 | 辅助核对，不将某个型号参数套整个供应商 |
| [Claude List Models](https://platform.claude.com/docs/en/api/models/list) | 原生 /v1/models、游标分页、display_name；新版可有 max_input_tokens/max_tokens/capabilities | 原生目录，兼容老版本缺字段，不为目录升级推理协议 |
| [Gemini models](https://ai.google.dev/api/models) | models[]、nextPageToken、inputTokenLimit/outputTokenLimit、supportedGenerationMethods | 原生目录；输入上限不自动等同总上下文，资源名与调用名称分开 |
| [Azure Models](https://learn.microsoft.com/en-us/rest/api/aifoundry/azureopenai/models) | 新 v1 /openai/v1/models，api-key；基础模型信息 | v1 查询路径；与旧部署式地址分开 |
| [Azure 部署与 endpoint](https://learn.microsoft.com/en-us/azure/ai-studio/ai-services/concepts/endpoints) | 请求 model 是部署名，不一定是基础模型名称 | 未知部署映射必须提示用户输入，不拿基础模型直接冒充部署 |
| [OpenRouter models](https://openrouter.ai/docs/api/api-reference/models/get-models) | context_length、top_provider.max_completion_tokens、支持参数等 | 显式增强解析；端点范围上限优先，不能当路由到任意后端的保证 |
| [Mistral Models](https://docs.mistral.ai/api/endpoint/models) | 兼容目录及模型能力、上下文等模型结构 | 在实际 JSON 路径核实后增强解析，缺值不推测 |
| [Groq API](https://console.groq.com/docs/api-reference) | /openai/v1/models，模型对象可包含 context_window 等 | 通用读取加有依据的字段归一化 |
| [硅基流动目录](https://api-docs.siliconflow.cn/docs/api/models-get) | 现有 MD-R1 采用的分类目录 | 保留适配，参数以返回字段为准；不能承诺一定返回维度 |
| [Ollama tags](https://docs.ollama.com/api/tags) | 已安装模型列表，非官方云模型库 | 保留本地路径；缺少 limits 时未知，不下载模型 |

注意：文档示例用于结构 fixture，不把示例模型的数值认定为同厂商所有型号的真值。max_input_tokens、总 context_window、max_output_tokens、max_reasoning_tokens 语义不同，不递归搜到第一个整数就使用。模式/地域不匹配时不能套用文档值。

## 供应商覆盖声明的限度

兼容聊天协议不意味着一定实现 /models。矩阵的 generic_probe 表示本项目应尝试用户配置站点上的标准只读目录，并正确呈现 401/403/404/405/429/错误 JSON；它不是该厂商在线目录已被真实验证的声明。代码不得为了“全覆盖”编造未验证的专用控制面 API。

能查询的返回目录，不能查询的明确说明该 endpoint 无目录并保留手填/有来源预置。所有 38 个供应商都有正确策略与行为，是本阶段完成条件；“38 个账号全部实测成功”不属于可作出的声明。

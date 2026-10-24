# 38 个 LLM 供应商审计矩阵

来源为当前 registry 与 discovery 纯函数 AST；没有导入应用、读取真实配置或使用密钥。数值：38 项，当前可路由 7，当前通用查询拦截 31，其中托管 3，普通 API 缺口 28。

target_policy 代表本项目处理策略；openai_compatible 是有界协议查询，不代表服务商目录已实测。全量机器记录和默认 URL 见 PROVIDER_MATRIX.json。

| binding | 当前目录 | 目标策略 | 处理说明 |
|---|---|---|---|
| `custom` | openai_compatible | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `custom_anthropic` | unsupported | anthropic | 原生认证/版本、display_name、游标；兼容端点无目录如实提示。 |
| `azure_openai` | unsupported | azure | 新 v1 与旧 deployment 地址分开；offering 不是 deployment，不取 ARM 凭据。 |
| `openrouter` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 增加已核验结构化字段的专用归一化。 |
| `orcarouter` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `edenai` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `aihubmix` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `siliconflow` | siliconflow | siliconflow | 已有分类目录；补有依据的参数，目录缺维度时使用官方文档资料或未知。 |
| `novita` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `atlascloud` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `volcengine` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `volcengine_coding_plan` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `byteplus` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `byteplus_coding_plan` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `anthropic` | unsupported | anthropic | 原生认证/版本、display_name、游标；兼容端点无目录如实提示。 |
| `openai` | openai_compatible | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `openai_codex` | unsupported | managed | 保留专用管理和凭据，不进入通用 key 查询；通用 unsupported 不代表其专用路径失效。 |
| `github_copilot` | unsupported | managed | 保留专用管理和凭据，不进入通用 key 查询；通用 unsupported 不代表其专用路径失效。 |
| `codebuddy` | unsupported | managed | 保留专用管理和凭据，不进入通用 key 查询；通用 unsupported 不代表其专用路径失效。 |
| `deepseek` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 增加已核验结构化字段的专用归一化。 |
| `gemini` | unsupported | gemini | 官方 host 原生分页目录和 token limits；代理不跨域，保留资源名/调用 ID 区别。 |
| `zhipu` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `dashscope` | aliyun | aliyun | 已有专用目录；改可见名称和别名；补完整参数。北京旧 host 404 要求业务空间目录，不猜 WorkspaceId。 |
| `moonshot` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `minimax` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `minimax_anthropic` | unsupported | anthropic | 原生认证/版本、display_name、游标；兼容端点无目录如实提示。 |
| `mistral` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 增加已核验结构化字段的专用归一化。 |
| `stepfun` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `xiaomi_mimo` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |
| `vllm` | openai_compatible | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `ollama` | ollama | ollama | 原生 api/tags，保留代理前缀；只列已安装，参数不足留未知，不 pull。 |
| `lm_studio` | openai_compatible | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `llama_cpp` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `lemonade` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `ovms` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `nvidia_nim` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 |
| `groq` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 增加已核验结构化字段的专用归一化。 |
| `qianfan` | unsupported | openai_compatible | 在用户配置站点有界 GET models；无声明类别可批量确认，无声明参数未知。 generic_probe，不宣称厂商一定有目录；404/405 可提示目录覆盖地址或手填。 |

已有 7 个适配仍要参与本阶段元数据和默认值回归。所有供应商保持自己的身份；不能把矩阵中同策略的条目改成相同 binding。

验收要求由 registry 集合与策略集合对比，加上每个条目的请求路径/认证/非支持行为表驱动测试，防止下一次增加供应商再次漏接。

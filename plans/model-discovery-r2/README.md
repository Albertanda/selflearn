# MD-R2：供应商目录覆盖、官方参数默认值与模型名称

派发日期：2026-10-24，Asia/Shanghai。状态：**已规划，尚未实施/验收**。

这是一个阶段，内部任务是实施和验证单元，不逐卡请求用户批准。用户要求本轮生成方案和开工指令；本轮没有修改生产代码、真实配置或密钥。

工作目录固定为 `/home/albert/selflearn/selflearn`。入口 [START_MD_R2.txt](START_MD_R2.txt) 可以直接粘贴给 DeepSeek Harness。

## 已确认的问题

1. 设置页 LLM 下拉框从 `provider_registry.PROVIDERS` 派生，共 38 个供应商。只读 AST 检查发现当前 7 个 binding 可进入目录适配，其余 31 个被本地 unsupported 拦截，其中 3 个是 OAuth/托管专用流程。因此还有 **28 个普通 API 供应商缺少通用查询路径**。这是代码覆盖检查，不是 38 个真实账号的联网测试。
2. 7 个已接通名称为 custom、siliconflow、openai、dashscope、vllm、ollama、lm_studio。未知类别、缺失参数、旧阿里域名路径等仍可能影响这些配置，不能称为全面验收。
3. 阿里 LLM 已以 DashScope 存在，无需新增第二套重复供应商。改为“阿里云百炼（千问 / DashScope）”，保留 dashscope 内部身份，接受 aliyun/alibaba/bailian 的 LLM 别名；不重写真实 profile。
4. 2026-10-23 协调者用当前 DeepSeek 凭据直接只读 GET 官方 `/models` 得到 HTTP 200，含 deepseek-flash 和 deepseek-v4-pro，context_window 均为 1048576，max_output_tokens 均为 393216。Flash 支持 text/image，Pro 为 text。该结果是上一轮现场检查，不是本阶段新的执行凭据或测试 fixture。
5. 聊天选择器两处 `model || model_name` 导致别名只出现在 tooltip。后端已返回 model_name。
6. 导入函数只复制 id/name/model，丢弃 context_window；模型最大输出参数当前没有从 catalog 到 ResolvedLLMConfig/LLMConfig 的完整通路。仅增加表单不能满足需求。

完整 38 项审计及逐项目标见 [PROVIDER_MATRIX.md](PROVIDER_MATRIX.md)、[PROVIDER_MATRIX.json](PROVIDER_MATRIX.json)。

## 总体方案

将供应商身份、推理协议、目录协议拆开：普通兼容供应商复用 OpenAI-compatible 目录读取；Anthropic、Gemini、Azure 使用明确的目录规则；阿里和硅基流动保留既有专用规则；托管供应商保持原流程。所有注册供应商必须有显式策略和测试，新增供应商若遗漏策略应使测试失败。

学校网关选择“自定义（OpenAI 兼容）”，输入 API base、key、必要 extra_headers 即可查询 `<base>/models`。同 origin 有界路径回退和可选目录地址覆盖非标准部署。不能保证服务器没有实现的目录或参数也能自动出现。

同次目录查询解析厂商实际返回的参数。缺失字段可用小型、注明核验日期的**官方文档资料**补充；这必须标为文档资料，不能声称实时返回。不接第三方全量模型库，不运行时抓取任意网页，不靠模型名称猜参数。未知值保留未知。

新导入模型默认填入官方上下文、最大输出、embedding 默认维度等已知值；旧模型、手工设置及已建索引不因刷新改变。最大输出上限与每次业务请求的输出预算分开，已有更小预算继续生效。显示名称优先使用用户名称，调用仍用原 model ID。

## 包内容与顺序

- [CONTRACTS.md](CONTRACTS.md)：字段、凭据、缺失值、默认值、运行时规则。
- [TASKS.json](TASKS.json)：一个阶段内的低依赖任务卡，含目标、证据、范围、完成条件。
- [ACCEPTANCE.md](ACCEPTANCE.md)：独立验收、回归和交付清单。
- [EXPLORATION.md](EXPLORATION.md)：当前源码 hash、已探索文件及关键片段；替代全项目 orientation 重读。
- [RESEARCH.md](RESEARCH.md)：本机 Chatbox/Hermes 路径及官方资料。

## 阶段内部任务

| 卡 | 确定的工作单元 |
|---|---|
| R2-00 | 到达源码、数据不透明哈希和独立证据入口 |
| R2-01 | 参数类型、来源、人工覆盖和合并纯函数 |
| R2-02 | 38 个供应商显式策略、真实身份和阿里 LLM 入口 |
| R2-03 | 通用网关、目录地址覆盖、认证与有界路径回退 |
| R2-04 | Anthropic 类原生目录 |
| R2-05 | Gemini 原生目录 |
| R2-06 | Azure 目录与部署名边界 |
| R2-07 | 官方结构化参数、有限文档资料和缓存 |
| R2-08 | 自动填入、人工优先和参数更新预览 |
| R2-09 | 参数贯通实际 LLM 请求及上下文预算 |
| R2-10 | 聊天自定义名称和保存后缓存同步 |
| R2-11 | 阶段回归、浏览器交互和统一交付 |

每张卡的目标、证据、允许更改范围和完成条件均在 TASKS.json，依赖图已校验；R2-10 仅依赖到达基线，其他卡按字段/协议接缝拆分，没有逐卡人工审批环节。

本契约明确取代 MD-R1 中“不自动填入官方参数”的旧范围限制；其权限、真实数据保护、缓存隔离和有界请求约束继续有效。原 MD-R1 文件和封存证据不改写。

所有生产改动由后续 Harness 执行。此规划包不授权恢复/编辑真实 model_catalog、改当前默认模型、实际调用学校网关、借用 ASR key 自动建立 LLM profile、付费推理或重建索引。

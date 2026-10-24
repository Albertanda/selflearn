# CP-R1 数据与行为契约

## C1 身份与保存结构

在现有 catalog 根新增可选 `custom_providers` 数组；缺失表示空，不为了补空数组在只读请求中重写真实 catalog。继续使用原 catalog 保存、锁、revision 和密钥遮罩机制，不另建一套供应商配置数据库。

```json
{
  "custom_providers": [{
    "id": "cp_<uuid>",
    "service": "llm",
    "binding": "custom",
    "name": "Agnes",
    "icon": {"kind": "builtin", "value": "flask"}
  }],
  "services": {"llm": {"profiles": [{
    "id": "existing-profile-id",
    "name": "Agnes",
    "binding": "custom",
    "custom_provider_id": "cp_<uuid>",
    "base_url": "<existing endpoint>",
    "api_key": "<existing credential, never in reports>",
    "models": [{"id": "existing-model-id", "model": "agnes-3.0-flash"}]
  }]}}
}
```

定义的 id、service、binding 一旦保存即不可通过重命名操作改变。名字修改不改变 profile/model ID、权限、默认引用、请求协议、密钥、目录缓存身份或思考能力。一个定义可被该服务的多个连接引用；聊天仍按 profile_id 分组，不合并多把 key。

定义不存 URL、凭据或推理参数，它们仍只属于 profile/model。每服务名字去首尾空白后 1–80 字符、禁止控制字符，同服务内大小写折叠后唯一；不同服务允许同名。最多 100 个定义。id 必须有界且唯一；引用必须存在、service 匹配，profile.binding 必须等于定义.binding。

对新字段采用显式 schema/白名单校验，额外字段、非法引用、协议不匹配返回 422；不误删旧 catalog 其它未知字段。旧无 custom_provider_id 的 custom 配置照常可读、可保存、可调用。仍被引用的定义不能直接删除，返回 409；删除功能可仅限未引用定义，不实现级联删除。managed/read_only 配置不可借此改凭据/授权身份。

## C2 协议矩阵与范围

| service | 允许的定义.binding | 用户看到的接口格式 |
|---|---|---|
| llm | custom / custom_anthropic | OpenAI 兼容聊天 / Anthropic Messages |
| vision | custom / custom_anthropic | 复用现有图像理解聊天协议 |
| embedding | custom | 现有 OpenAI 兼容嵌入 |
| stt | custom | 现有 OpenAI 兼容录音转写 |
| tts | custom | 现有 OpenAI 兼容语音合成 |
| imagegen | custom / custom_chat | 现有 Images API / 聊天图片输出 |
| videogen | custom | 现有 Async Task 适配器格式 |

这不表示任意 Coding Plan 或大学网关都实现这些协议。界面在选择协议时简要说明格式要求；不承诺仅凭 URL/key 就能兼容全部平台。search 没有通用模型调用协议，本阶段不改搜索供应商体系。

不增加任意动态 binding，不把显示名 Agnes/大学/DeepSeek 写进注册表成为真实请求身份。复用现有协议适配器，不修改全局静态 PROVIDERS 以“新增 Agnes 大厂预设”。

## C3 下拉与编辑交互

每个适用模型服务按“原有可用预设 → 已命名自定义供应商 → 自定义供应商配置…”排列，最后一项始终在末尾。原匿名 Custom 项使用清楚的中文兼容协议标签，旧配置不变成空选择。保留原预设的 auth_mode/托管入口，不按名字硬编码排序。

最后一项是 UI 动作哨兵，例如 `__create_custom_provider__`，绝不能保存进 binding、custom_provider_id、API payload 或发给模型。选中后弹出名字、接口格式、图标编辑；取消完全不改草稿或默认；确认只添加草稿定义并关联当前编辑连接，正常“保存/应用”才持久化。不在打开弹窗时调用模型或修改已有默认。

已保存自定义项有“编辑供应商”入口，能修改名字和图标；连接名仍独立可改。协议已保存后显示为只读，想换协议应明确新建或重新配置连接，不能用改名暗换协议。管理界面及名称翻译需中英完整。

图标本阶段支持：

- `{kind:"builtin",value:"bot"|"server"|"school"|"flask"|"cloud"|"network"}`，使用现有 lucide 图标，不新增依赖。
- `{kind:"emoji",value:"…"}`，1–8 个 Unicode code point，拒绝控制字符/换行，以 React 纯文本显示。
- 省略或 null 使用通用 Bot。用户可随时改选图标/输入 emoji；本阶段不添加图片上传、外链图标或 SVG/HTML 存储。

原生 select 的 option 允许只显示文字；已选供应商旁、profile 标签、聊天第一层/模型项/触发按钮和默认候选的可见位置要显示正确图标。不得把“配置了图标但只在弹窗中能看到”当完成。

## C4 安全展示摘要

建立后端单一纯函数 `resolve_provider_presentation(catalog,service,profile)`（命名可微调），统一决定 provider_label/provider_icon/custom_provider_id。`provider` 仍为真实技术 binding；profile_name 仍为连接名。

设置页、默认模型候选、管理员 LLM options、普通用户授权模型 options、hidden_options 均使用同一摘要。普通用户只收到其已授权连接的名字和有界图标，不收到完整自定义供应商目录、URL、headers、key 或管理员 catalog。所有 ProviderIcon 使用处兼容新可选 icon，旧调用者不破坏。

自定义展示字段不得成为请求 kwargs；聊天仍只传已有 profile_id/model_id 和正式 reasoning_override。不猜测 Agnes 的思考强度、上下文或免费额度；不存在的官方参数保持未知。按已有规则保留人工输入和接口实际返回的参数。

## C5 查询、缓存、权限与并发

保留 binding 非空校验；创建/选择自定义项时明确填入 C2 的 binding，自然能够查询和调用。目录请求仅提交既有技术连接字段，使用现有 custom / custom_anthropic 适配器。模型获取失败或网关不提供目录时，仍可手动填 ID，不能禁止保存有效连接。

首次获取、缓存、显式目录 URL、超时、分页、凭据轮换、跨源密钥遮罩校验继续沿用 MD-R2/MM-R3。纯名字/图标修改不触发外网重查，不改变 auth 身份，不拿显示名推断原厂模型参数。不同真实连接维持既有缓存隔离。

新增定义与 profile 关联一次 catalog 保存，在现有锁内 expected_revision 校验之后统一验证和写入。默认 PATCH、普通 Save/Apply、其它窗口并发保持 409。保持 MM-R3 的旧草稿版本保护、编辑目标固定、隐藏项、会话强度恢复等协调者修复。

## C6 Agnes 迁移与 vLLM 恢复

当前定位提示（到场重新验证，不能对不匹配对象强行执行）：

- profile：`llm-profile-1792841570392`，当前 name=OpenAI、binding=vllm。
- model：`llm-model-51f6b172-f944-40e7-b251-279b227757c4`，call ID=`agnes-3.0-flash`。
- URL：`https://apihub.agnes-ai.com/v1`；已存在 key。本包不包含 key、headers 或其副本。

迁移创建 service=llm、binding=custom、name=Agnes、icon=flask 的定义，复用已有定义则不重复创建。将原 profile 改名 Agnes，binding 改为 custom，关联定义。profile/model ID、URL、key、headers、模型名和参数、其它 profile、授权和默认引用全部保持。当前默认是 DeepSeek，不把 Agnes 设置为默认。

vLLM 静态预设实际上未被修改。迁移后不再有该 Agnes 地址冒充 vllm。若无其它干净的 vllm 配置，新增一个 `name=vLLM/Local,binding=vllm,base_url="",api_key="",models=[]` 的非默认空配置槽；不猜过去的本地端口、key 或模型。已有真实 vllm 连接全部保留，不批量清空。

迁移工具默认 dry-run，显示去密钥的预期差异；显式 --apply 是本任务已授权的最后实施步骤，不需逐卡再请求许可。工具只可针对上面的精确匹配或等价到场确认目标；重复执行为无操作。未知差异/不匹配/并发变化停止迁移，不回滚用户到历史配置。

**不要从独立 CLI 进程直接 save 文件并声称线程锁能阻止运行中服务覆盖。** 优先经当前本地管理 API `/settings/catalog` 获取 revision 并提交 PUT，让服务器同一锁执行；必要的原 key/headers只从当前文件在内存读取，限定同一来源、同一 profile，作为显式新凭据提交以通过既有身份变化检查。禁止删除或放宽 `_reject_masked_identity_change`。请求体不落日志、shell、截图或报告；其它 profile 使用遮罩保留。401/403 不绕过登录；409 有界重读复核，仍冲突则如实留待完成。

实现与隔离测试先完成，迁移最后执行。基线分三段：T0 到场、T1 隔离验收后六树不变、T2 授权迁移后仅 model_catalog.json 发生白名单语义变化。保留 S14 历史例外和 MM-R3 基线；不要把本次有意配置迁移伪装成数据未变化。迁移不新增秘密备份文件，不复制真实 catalog 到 fixture/evidence。

真实服务当前运行时，不能为测试杀掉它；配置迁移使用可用的标准管理 API。未重启则交付明确说明源码需重启加载；不在旧进程中看到新菜单就谎报新界面已生效。独立浏览器验收使用新源码副本。

## C7 真实测试与未来政策

用户已允许后续涉及 LLM 的测试使用 Agnes `agnes-3.0-flash`。把该偏好补入 AGENTS.md 测试段和独立 live smoke 工具说明：这是可用的外部测试选项，不是把全部自动化测试接入外网。

固定输入只用无个人信息的合成短句；显式选 Agnes 连接/模型、max_tokens≤64、禁止自动标题/默认模型回退；本阶段至多 3 次推理，关闭重试放大，单次超时≤45 秒。目录查询至多 2 次，凭据不得跟随跨源重定向。只保存成功状态、model ID、耗时和去密钥错误类别，不记录 headers/raw catalog。

不承诺免费额度永久有效，不拿 Agnes 替代 ASR/嵌入/多模态供应商。批量回归、异常和协议断言仍用本地 fixture。Agnes 服务不可用时仍完成隔离验收和可验证的迁移，live_smoke 如实 failed/blocked，不能声称真实调用通过，也不切到 DeepSeek/千问消耗其它额度。

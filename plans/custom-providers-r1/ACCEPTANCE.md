# CP-R1 验收门

每门必须有实际行为证据，不能只检查源码字符串。普通 API 成功不等于浏览器交互成功。所有自动化使用一次性数据和本地服务，真实 Agnes smoke 独立执行。

| 门 | 必须证明 |
|---|---|
| A01 | 旧 catalog 无 custom_providers 仍可读写调用；非法字段/重复 ID/同服务重名/跨服务关联/协议不匹配被拒；取消或失败不落盘 |
| A02 | 七个已有模型服务最后一项均为“自定义供应商配置…”；现有大厂/本地/托管预设保留；所有 UI 哨兵都不进入持久数据和请求 |
| A03 | LLM 创建“学校网关”并选 OpenAI 协议，保存后重开仍存在；改名、改内置图标、改 emoji 后各展示位置一致，取消保留原值 |
| A04 | 另建 Anthropic 自定义连接，目录与推理真正走 Messages 格式；同名模型、不同连接各走正确 endpoint/key，不按模型别名套原厂规则 |
| A05 | OpenAI 自定义 GET /models、首次获取/缓存/刷新/手动 ID 可用；404/401/429/超时不清已有模型；改名图标不触发目录外网查询 |
| A06 | 嵌入、STT/TTS、图像、视频服务创建时只复用各自 C2 既有协议；不把 chat/completions 当所有服务的通用格式；不虚构目录能力 |
| A07 | 主聊天与题目跟进实际发送均带正确模型选择、连接来源和图标；普通用户只看到授权摘要；隐藏项和同供应商多连接不回归 |
| A08 | 改名/图标/浏览/导入不暗改默认；默认候选显示新名称；默认 PATCH 与 Save/Apply 并发返回正确 409，MM-R3 旧草稿保护/编辑目标固定不回归 |
| A09 | 两个自定义供应商、内置/emoji/fallback 图标、非法图标、重复名字、刷新失败、重命名后会话保持等有反例；非管理员不能改供应商定义 |
| A10 | 迁移 dry-run 和 --apply 使用同一变换；模拟数据迁移保留 ID/key/headers/参数/默认，二次运行 no-op；既有本地 vllm 保留；409 不覆盖；遮罩保护不被禁用 |
| A11 | 先证明隔离验收后 T1 六树不变，再证明 T2 只改授权 catalog 语义：Agnes 自定义定义/关联/名字与干净 vllm 空槽；没有改其它供应商、密钥、历史或索引 |
| A12 | 真实 Agnes smoke 明确模型、合成输入和 token/request 限额，无默认模型回退；结果区分 success/failed/blocked；无凭据进入报告和归档 |
| A13 | 完整 Python、Node、tsc、Ruff、ESLint、i18n parity、diff 和 MD-R2/MM-R3 浏览器回归通过；保留失败证据，不把历史旧数量当新验证 |

## 必须实际操作的 Chromium 用例

1. 从设置 LLM 下拉框末尾创建学校网关，先取消一次，再创建保存。检查已保存 catalog 的 binding=custom 和稳定引用，目录 fixture 返回模型并导入。设置为当前聊天选择后发送，核对 fixture 捕获的 endpoint/model/header 存在性，不记录 key 值。
2. 重开供应商编辑，改名和内置图标，再改为 emoji；设置、第一层连接列表、聊天触发按钮、题目跟进、默认候选均检查，刷新后仍在。不是只测弹窗输入框。
3. 另外创建 Anthropic 接口的自定义项、另一个同协议但不同 key 的连接。实际捕获各协议请求，证明不会因显示名/模型别名误路由或给未知代理塞入原厂 reasoning 字段。
4. 目录 404 后手动填写 fixture ID，保存并发送；再测试错误/取消/409，既有列表和 dirty 草稿不能丢。普通用户分配授权用 TestClient 完整验证；浏览器没有登录 fixture时不能宣称验过真实账号登录。
5. 至少遍历七个服务的创建入口、协议选项、保存后重开；非 LLM 复用既有运行时函数的协议测试，不要求用真实 Agnes 测嵌入或 ASR。
6. 在本地假 catalog 上运行迁移 dry-run/apply/no-op；新增供应商能在两层选择中出现，vllm 空槽不会发出外网请求或成为默认。

新增 `web/playwright.custom-providers.config.ts` / `web/e2e/custom-providers.spec.ts`，复用已审计的 S15 临时源码、回环模型服务、已安装 Chromium、端口和 cleanup，不新建另一套浏览器基础设施。

## 命令与证据

Python 必须：`.venv/bin/python scripts/run_tests_isolated.py [pytest 参数]`。本阶段目标测试后完整运行一次；不能直接 pytest 或绕过真实数据保护。Node 用 `npm run test:node`，若运行时只打印文件数，另记录实际 case 数而非虚报。

浏览器使用新的 `S15_EVIDENCE_DIR`，分别执行 CP-R1、MM-R3、MD-R2 配置。优先复用当前 Chromium；S15 核心用例若出现相关影响再回归。不要把真实 catalog 复制到 fixture，不对真实用户界面运行自动化创建/删改测试。

统一交付 report.md、report.json、acceptance.json、协议捕获摘要、源码范围与可重建归档、T0/T1/T2 数据收据、去密钥迁移 diff、幂等/409 证据、live_smoke.json、浏览器与 cleanup 记录。状态用 implemented/verified_local，accepted=false 留协调者独立验收；不得修改历史报告签名。

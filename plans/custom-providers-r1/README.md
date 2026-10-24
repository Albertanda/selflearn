# CP-R1：自定义供应商收尾与 Agnes 迁移

日期：2026-10-24（Asia/Shanghai）。状态：已规划，尚未实施。执行者：DeepSeek Harness。

这是一个连续执行的阶段。TASKS.json 的卡是低依赖实施单元，不是逐卡审批点。前置是已补修并验收的 MM-R3：`.phase1-evidence/reviews/MM-R3-20261024/REVIEW.md`、`review.json`。保留其 18 个补修文件及全部历史证据，不从 git HEAD 回退。

## 已确认的现象和原因

- 源码和正在运行的后端 8001、前端 3782 转发的 `/api/v1/settings` 均返回 38 个 LLM 供应商，其中包括 `Custom (OpenAI API)`、`Custom (Anthropic API)`。自定义协议没有被删除。
- 下拉选项按英文标签排序，直接输出 `p.label`，没有中文自定义创建入口，也没有独立命名、图标管理。不能据此宣称“MM-R3 禁止自定义”。现有 profile 虽能重命名，但供应商标签/图标仍来自静态 binding。
- 模型目录查询要求非空 binding，用它选择协议；URL、API Key 不能唯一确定 Chat、Anthropic、嵌入或音频请求格式。此校验应保留。
- 聊天两层选择按 profile_id 分组，未要求模型属于某个大厂；`custom` 已有目录和运行时适配器。
- 真实 Agnes 连接当前为 `binding=vllm`、配置名 `OpenAI`，地址主机 `apihub.agnes-ai.com`、路径 `/v1`，含 `agnes-3.0-flash`。默认 LLM 仍是 DeepSeek。仅确认密钥已存在，未展示、复制或调用密钥。

本轮协调者只读检查和生成任务包，没有改生产代码或真实配置，也没有调用 Agnes。具体证据与片段在 EXPLORATION.md 和 `.phase1-evidence/planning/CP-R1-20261024/`。

## 阶段交付

1. 七个已有模型服务的供应商下拉框末尾固定“自定义供应商配置…”；创建有稳定 ID、名字、可改图标的供应商，复用当前服务已有的兼容协议。
2. 自定义供应商可重新选择、重命名、改图标；设置、默认模型候选、主聊天和题目跟进显示一致。已有普通用户权限和连接分组规则保持正确。
3. 保留旧 custom/custom_anthropic 配置兼容；不实现新协议、任意 Python 插件或按模型别名猜测厂商。
4. 隔离验收通过后，将现有 Agnes 连接迁移为命名自定义供应商，保留其 profile/model ID、连接凭据和参数；恢复干净的 vLLM/Local 配置槽，默认引用不变。
5. 使用 Agnes 做有界、显式选择的真实 smoke，记录未来测试政策；大批量回归继续使用确定性替身。

读 CONTRACTS.md → TASKS.json → ACCEPTANCE.md → EXPLORATION.md。START_CP_R1.txt 可直接粘贴执行。源码修改、真实配置迁移、真实外部 smoke 必须分阶段记录，不能用“六树完全不变”描述最终被明确授权修改的 model_catalog.json。

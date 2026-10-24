# MM-R3 执行记录

运行：`MM-R3-20261024T0811Z`。工作树保持原未提交修改，未 reset/clean，未修改真实配置、密钥、默认项、学习数据或历史基线。前置 MD-R2 协调者结论 `accepted_local`；本阶段完成后再交协调者独立复核。

## 到达与边界

- 源码 HEAD：`9723f953cb6ca56f13603f76c5d07e1e2f1f4473`。
- 到达源码/六树/状态：`.phase1-evidence/model-management/MM-R3-20261024T0811Z/{arrival.json,source_arrival.json,data_before.json}`。
- EXPLORATION 的 37 个唯一源码哈希全部匹配，未重做全仓 orientation。
- 真实六树只计算不透明哈希；所有测试使用 `scripts/run_tests_isolated.py` 或 S15/MD-R2 disposable source、loopback MODEL_SERVER、既有 Chromium。

## 实施单元

| 卡 | 结果 |
|---|---|
| M3-00 | 到达基线、MD-R2 review、hash 核对、唯一证据根、EXECUTION 入口。 |
| M3-01 | 新增 `reasoning_controls.py` 单一策略；DeepSeek `effort.supported_levels/default_level` 从目录解析到 candidate/cache/catalog/options/settings；`provider_metadata.reasoning_controls` sibling，不扩 parameters 任意 JSON；cache schema 4、identity policy schema 2。 |
| M3-02 | DeepSeek/阿里 DeepSeek/Qwen/Claude/Gemini/OpenAI/Azure/Codex 精确 wire 映射；minimal 不再是关闭；官方 host 才套静态策略，未知代理不猜；Anthropic adaptive + `output_config.effort` 与旧 budget 分离，budget 严格低于 max_tokens；Qwen3.8 effort 与 budget 不并存。 |
| M3-03 | 正式 `reasoning_override` 契约（TS/Pydantic/WS/runtime）；省略=inherit；先授权模型后校验强度；scoped config 只影响本 turn；session `reasoning_preferences` 按 `profile:model` 保存；turn snapshot 记录 requested/effective/source；regenerate 复用/显式覆盖；主聊天、题目跟进、core agentic、HTTP/SDK fallback 均传协议。 |
| M3-04 | ModelSelector 两层：第一层 profile_id 连接、第二层模型；按钮常显来源+自定义名；同名 DeepSeek 原厂/阿里可辨；同厂两连接不合并；跨连接搜索保留来源；键盘/触屏/返回/错误/空列表；主聊天与 Followup 同组件。 |
| M3-05 | ChatComposer `ReasoningSelector` 只消费后端能力；native levels、provider default、inherit、none；模型设置页同一后端摘要可设模型默认强度；budget 明确标注；不支持/旧值可见并可清除。 |
| M3-06 | `GET/PATCH /api/v1/settings/default-models`；HMAC opaque revision；锁内读校验写；PATCH 只改 active 引用；revision 409、跨 profile 422、缺失模型 409、hidden 422、普通用户 403；普通 Save/Apply 带 revision 且锁内比较。 |
| M3-07 | 新 `/settings/default-models` 首项页；一个默认 LLM + 现有 embedding/search/STT/TTS/vision/image/video 引用；search 只选 profile；SettingsContext `editing_selections` 与 draft.active 分离；ServiceConfigEditor 的 profile/model tab、诊断、目录添加、参数预览、改名、删除均定位本地编辑选择；默认只由默认页/首次空服务初始化。 |
| M3-08 | 默认页固定第一；中文 LLM 统一“大语言模型（LLM）”；默认页隐藏 draft Save/Apply 工具条并只提供“保存默认设置”；配置页保留 Apply 并说明“保存全部草稿修改，不改变默认模型”。 |
| M3-09 | 完整 Python/Node/tsc/i18n/ESLint/Ruff、MM-R3 浏览器 2 项、MD-R2 浏览器回归、S15 B1-B5 回归、真实六树 compare、源码归档与重建。 |

## 关键设计

- **能力策略唯一入口**：`deeptutor/services/llm/reasoning_controls.py`。前端只渲染后端 `reasoning_controls`，不维护另一套模型名判断。
- **Provider identity vs wire**：`provider_identity` 决定供应来源；wire 决定实际字段。`custom`/代理不因模型名获得原厂档位；静态规则还要求 profile host 属于该厂官方 host，或 catalog 中有该连接返回的明确 `reasoning_controls`。
- **选择语义**：`inherit` 使用模型已保存值（坏值降级为 provider default 且不发送）；`provider_default` 使用内部 sentinel 抑制所有项目默认，sentinel 不出网；`effort` 先授权/校验，再按 aliases 映射 native level。
- **默认引用**：仍只存 `services[service].active_profile_id/active_model_id`，不建第二份 preferences；默认页 PATCH 不提交其它页 draft。
- **编辑选择**：`SettingsContext` 维护按服务的本地 `editingSelections`；浏览/测试/导入/改名不写 active。只有首次空服务初始化首个默认，后续新增模型绝不替换默认；删除当前默认被阻止并提示先换默认。
- **并发**：`ModelCatalogService.update_checked` 在同一 RLock 内重新加载、校验 opaque revision、builder/validator、save；revision 使用进程级 HMAC key，避免把明文哈希暴露成可验证密钥摘要。

## 相邻接缝（记录原因）

- `deeptutor/agents/chat/agentic_pipeline.py`、`question/pipeline.py`、`research/pipeline.py`、`capabilities/explore_context/explorer.py`、`core/agentic/client.py`：为保证 core agentic/题目跟进/SDK 路径与 provider 路径使用同一 wire protocol，增加 `reasoning_protocol` 透传；否则 metadata 的 budget/toggle 覆写只在 services 层生效。
- `web/playwright.phase1.config.ts`：仅在隔离 MODEL_SERVER 增加 `/r3/*` fixtures 与 reasoning 请求日志字段；S15 默认设置路径不变。
- `web/e2e/model-discovery-r2.spec.ts`：两层选择与显式默认页改变后，旧 spec 的“点平铺模型即选中/点编辑模型即改默认”不再成立；已更新为先选连接、用显式默认 API 移动默认，仍断言 MD-R2 参数/名称/预算/凭据/嵌入修复。原 MD-R2 报告和历史证据未改。
- `web/e2e/phase1.spec.ts` 未改；S15 回归使用新的 disposable source。

## 证据索引

- 报告/验收：本目录 `report.md`、`report.json`、`acceptance.json`。
- 协议请求：`protocol_requests.json`；浏览器原始：`browser-10/browser_evidence.md.json`。
- 官方来源：`metadata_sources.json`；38 家策略：`provider_coverage.json`。
- 测试日志：本目录 `logs/`（最终复制）。
- 六树：`data_after.json`、`data_compare.json`。
- 源码：`source_final.json`、`source_archive.tar.gz`、`archive_verification.json`、`source_compare.json`。
- 浏览器：`browser-final-5/`（MM-R3，3/3）、`browser-md-r2-regression-3/`（MD-R2，1/1）、`browser-s15-regression-final/`（S15 B1-B5，5/5）。

## 限制

- 无真实厂商账号/付费推理/学校网关调用；全部 `live_tested=false`。
- DeepSeek/Ali/Claude/Gemini/OpenAI 档位来自本阶段阅读的官方资料与 fixtures；未验证真实账号下每个版本的实时枚举。
- 未知代理、未在规则表中的型号不显示档位；`custom` 即使有任意 JSON 也不猜 wire。
- 浏览器 auth 关闭；普通用户 403 由 FastAPI TestClient 覆盖。
- S15 B3 的一次探索性运行误用了不存在的旧 FFmpeg 路径，失败证据保留在 `browser-s15-regression/` 与 `browser-s15-b3-rerun/`；改用本机真实 WinGet FFmpeg/ffprobe 后，最终 `browser-s15-regression-final/` 为 B1-B5 5/5。
- 最终完整 Python：5149 passed / 20 skipped / 7 warnings（174.07s）；验收子集：792 passed / 2 warnings（50.69s）；Node 559 passed；tsc 0；Ruff pass；ESLint 0 errors / 7 个既有 placeholder warnings；i18n parity OK、23 个既有 audit 文件不变；`git diff --check` 0。

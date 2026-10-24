# CP-R1 执行记录

运行：`CP-R1-20261024T2032Z`。工作树未 reset/clean；未停止或重启用户现有后端 8001 / 前端 3782。真实配置迁移是 CP-07 的显式授权步骤，迁移前后分别建 T0/T1/T2 收据。

## 到达

- HEAD：`9723f953cb6ca56f13603f76c5d07e1e2f1f4473`。
- `SOURCE_INDEX.json` 29 个预探索文件全部 hash 匹配；没有重新全仓 orientation。
- Agnes 到场事实：`llm-profile-1792841570392` / `llm-model-51f6b172-f944-40e7-b251-279b227757c4`，`binding=vllm`、name=OpenAI、URL=`https://apihub.agnes-ai.com/v1`，key 存在、headers 为空；默认 LLM 是 DeepSeek。
- 到达证据：`source_t0.json`、`data_t0.json`、`arrival_facts.json`、`source_index_check.json`。

## 实施

| 卡 | 结果 |
|---|---|
| CP-00 | 新证据根、hash 核对、T0 六树/源码收据；未复制真实 catalog。 |
| CP-01 | 新增 `custom_providers.py`：C1/C2/C4 schema、七服务协议白名单、名称/图标/引用/不可变性/删除约束、presenter；settings GET 暴露协议能力；PUT/Apply 锁内验证；旧 catalog 缺失字段兼容。 |
| CP-02 | 七服务下拉末尾哨兵；`CustomProviderDialog` 创建/编辑名称、协议、内置图标/Emoji；取消不写 draft；编辑协议只读；连接名独立；中英 locale。 |
| CP-03 | presenter 贯通管理员/普通用户 LLM options、hidden、默认候选、设置标签、主聊天/题目跟进、发现弹窗；技术 binding 保持 custom/custom_anthropic。 |
| CP-04 | 自定义 OpenAI/Anthropic 目录和实际请求、404 后手填、缓存/刷新、改名不重查；修复 anthropic SDK 1.5 不接受 temperature 的真实兼容缺陷。 |
| CP-05 | `scripts/migrate_agnes_custom_provider.py` 默认 dry-run、API-only apply、409 有界重读、精确目标拒绝、幂等、vLLM 空槽；`scripts/agnes_llm_smoke.py` 显式有界 smoke；AGENTS 测试偏好。 |
| CP-06 | 完整 Python/Node/tsc/Ruff/ESLint/i18n/diff；CP-R1/MM-R3/MD-R2 Chromium；T1 六树不变；源码范围/归档。 |
| CP-07 | 通过运行中管理 API 执行授权 Agnes 迁移、记录 T2 语义 diff，执行有界 Agnes smoke；最终报告与归档。 |

## 关键边界

- 自定义定义只存 id/service/binding/name/icon；URL、key、headers、模型参数仍只在 profile/model。
- 显示名不成为请求身份、不参与目录查询、不推断 reasoning；`custom`/`custom_anthropic` 的真实协议由 binding 决定。
- 旧匿名 custom 配置照常读取；名称未定义时回退技术 binding。
- 默认页和编辑器隔离保持 MM-R3 行为。
- 迁移不独立 save 文件；只通过 `/api/v1/settings/catalog` PUT，由服务器锁和 revision 决定原子性；不关闭 masked credential 检查。
- 真实服务若不重启，继续运行旧代码；新 UI 需重启加载，最终报告注明。

## 证据

根：`.phase1-evidence/custom-providers/CP-R1-20261024T2032Z/`。最终内容见 `report.md`、`report.json`、`acceptance.json`、`protocol_capture.json`、`migration_diff.json`、`live_smoke.json`、`source_compare_v3.json`、`source_archive_final_v4.tar.gz`。

## 最终结果

- CP-06 完整 Python：`5218 passed / 20 skipped / 13 warnings`（183.22s），记录见 `logs/full-python.log`。
- CP-R1 Chromium：`1 passed`（58.4s），证据 `browser-final/`；MM-R3 Chromium 5/5（`browser-mm-r3-regression/`）；MD-R2 Chromium 1/1（`browser-md-r2-regression/`）。
- Node 568 passed；tsc 0；Ruff pass；ESLint 0 errors / 7 个继承 placeholder warnings；i18n parity OK、23 个继承 audit 文件；diff 0。
- T0→T1 六树完全不变；T2 仅 `data/user/settings/model_catalog.json` 发生 C6 白名单语义变化。
- 实际迁移：`migration_apply.json`、`migration_diff.json`、`migration_noop.json`；默认 DeepSeek 不变；Agnes profile/model ID、URL、key 存在性、headers、模型参数保持；新增 `llm-profile-vllm-local` 空槽。
- 真实 Agnes smoke：`live_smoke.json`，1 次推理成功，`agnes-3.0-flash`，`max_tokens=64`，`default_fallback=false`；未记录内容或凭据。
- 旧 8001/3782 进程未重启，迁移后仍运行旧代码；新源码/界面需要用户重启加载。迁移通过运行中管理 API PUT 完成，未直接写文件。

# MD-R2 执行索引

状态：**`verified_local`**（代码、隔离测试、浏览器与数据不变检查已执行；未自签 accepted，等待独立复核）。执行日期 2026-10-24，Asia/Shanghai。本文件只索引本阶段新增证据，不改写 README 的“尚未实施”历史事实，也不改写 MD-R1 封存结果。

## 证据根

`.phase1-evidence/model-discovery/MD-R2-20261024T0305Z/`

| 文件 | 内容 |
|---|---|
| `source_arrival.json` / `source_final.json` | 到达与最终源码清单、HEAD、dirty/untracked、删除文件 |
| `source_archive.tar.gz` / `.manifest.json` | 最终源码确定性归档（不含真实数据/密钥） |
| `archive_verification.json` | 临时目录逐文件重建核验 |
| `source_compare.json` | 到达→最终变更及白名单范围判定 |
| `data_before.json` / `data_after.json` / `data_compare.json` | 真实六树不透明哈希与比较 |
| `full-python.log` | 最终完整隔离 Python 回归 |
| `acceptance-python.log` | ACCEPTANCE 指定 Python 子集 |
| `node-tests.log` / `tsc.log` / `i18n.log` / `eslint.log` / `ruff.log` / `git-diff-check.log` | Web/静态检查 |
| `s15-browser.log` / `s15/` | S15 B1–B5 回归 |
| `md-r2-browser.log` / `browser/` | MD-R2 真实 Chromium 交互、fixture 请求记录、截图、cleanup |
| `provider_results.json` | 恰好 38 项策略、fixture 测试映射、字段支持、live_tested=false |
| `metadata_sources.json` | 新增官方文档资料条目、URL、核验日期、地域/模式、字段 |
| `acceptance.json` | A01–A18 逐项结果与证据位置 |
| `report.md` / `report.json` | 阶段完成、限制、风险、数据不变、未实测声明 |

## 代码入口

- `deeptutor/services/model_discovery/provider_policy.py`：38 供应商显式目录策略与真实身份/传输族分离。
- `deeptutor/services/model_discovery/metadata.py` + `official_parameters.json`：白名单参数、provenance、有限官方资料。
- `deeptutor/services/model_discovery/adapters.py`：compatible/Anthropic/Gemini/Azure/Aliyun/SF/Ollama 有界目录。
- `deeptutor/services/model_discovery/service.py`：目录 URL、凭据边界、缓存指纹、single-flight。
- `deeptutor/services/config/provider_runtime.py`、`services/llm/{config,factory}.py`、`agents/chat/agentic_pipeline.py`：输出预算与容量接缝。
- `web/lib/model-metadata.ts`、`web/components/settings/*`：自动填入、人工覆盖、更新预览、目录 URL、状态展示。
- `web/components/chat/home/ModelSelector.tsx`、`web/lib/llm-options.ts`：自定义名称、隐藏当前项、保存后局部缓存失效。

## 明确未做

- 未用真实厂商账号目录、未调用付费推理、未实测学校网关。
- 未修改真实模型配置、密钥、学习数据、索引或历史基线；未 commit/push/install/restart。
- 未进入 S16 或其它 Phase 2 功能。

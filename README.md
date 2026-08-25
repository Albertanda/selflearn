# Subject Learning Assistant（分科学习助手）

基于 DeepTutor（HKUDS，Apache-2.0）裁剪扩展的**分科学习助手**——面向大学生的科目级 AI 学习工作区。
本目录是 M0–M8 的完整实现（fork 自 `feat/vision-model`，基线 v1.5.13；上游原版 README 见 `UPSTREAM.md`）。

## 功能概览

| 里程碑 | 功能 | 状态 |
|---|---|---|
| M0 | DeepTutor 裁剪（移除 partners/book/MCP/CLI apps 等） | ✅ |
| M1 | 分科作用域：`/api/v1/subjects` CRUD、会话挂科目 | ✅ |
| M2 | 每科知识库（LlamaIndex）+ 上传类型路由 + 索引/检索 | ✅ |
| M3 | 错题集：AI 批改（`/wrong-book/check`）+ 四档掌握度（反复错/错过/基本掌握/已掌握） | ✅ |
| M4 | 期末考点检测（讲师信号识别，提示词 v3 + few-shot + 负向信号排除） | ✅ |
| M5 | 知识点索引 + 三级上下文注入（知识点/考点/错题/画像）+ 对话摘要压缩 | ✅ |
| M6 | 复习指南 PDF/Word（Typst + python-docx） | ✅ |
| M7 | 图表报告（LLM 生成 matplotlib → ODE 自检 → Typst PDF） | ✅ |
| M8 | 科目工作台 UI、视觉三态策略、备份导出、token-saver 开关 | ✅ |

## 快速启动

```bash
# 后端（8001）
PYTHONPATH=$PWD /home/prompt/DeepTutor/.venv/bin/python -m uvicorn deeptutor.api.main:app --host 127.0.0.1 --port 8001

# 前端（3782，web/proxy.ts 转发 /api 与 /ws）
cd web && node ./scripts/dev.mjs
# 或生产模式：cd web && node ./scripts/build.mjs && npx next start -p 3782
```

浏览器打开 `http://127.0.0.1:3782`（认证默认关闭，单用户模式）。

## 配置（`data/user/settings/`）

| 文件 | 内容 |
|---|---|
| `model_catalog.json` | LLM / Embedding / Search / STT / **Vision** 模型 |
| `document_parsing.json` | MinerU（cloud + token）等解析引擎 |
| `token_budget.json` | 节省 Token 开关 + context_ratio（0.1–0.95） |
| `vision_strategy.json` | 视觉策略：auto / prefer_dedicated / dedicated_only |

## 关键接口

```
POST /api/v1/subjects                                 新建科目
POST /api/v1/subjects/{id}/knowledge/upload           上传材料（类型自动识别）
POST /api/v1/subjects/{id}/knowledge/{kb}/query       RAG 检索
POST /api/v1/subjects/{id}/wrong-book/check           AI 批改（错题自动入库）
POST /api/v1/subjects/{id}/wrong-book/{eid}/attempt   记录作答 → 掌握度更新
POST /api/v1/subjects/{id}/exam-points/detect         考点检测（粘贴转写）
POST /api/v1/subjects/{id}/review-pack                复习指南（format=pdf|docx）
POST /api/v1/subjects/{id}/report                     图表报告（ode_rhs 为图表数值校验基准）
GET  /api/v1/subjects/{id}/export                     科目数据 ZIP 备份
```

## 工具链

- **Typst** v0.15.1（`tools/bin/typst`）：PDF 渲染（`--font-path tools/fonts` 提供 Microsoft YaHei / SimSun-ExtG）
- **matplotlib** 3.11：图表渲染（子进程执行，带 ODE 数值自检：LLM 抄错方程会被拒绝并重试）
- **python-docx** / **tiktoken** / **scipy** / **numpy**

## 数据布局

```
data/user/workspace/subjects/<id>/        # 科目树（M1 扩展）
  knowledge.json / materials/<type>/ / knowledge_bases/<kb>/
  wrong_book.json（含四档掌握度）/ exam_points.json（证据+学期）
  knowledge_points.json（知识点挂链）/ profile.json（偏好/目标/事实）
data/user/subjects/<id>/                  # 产物：复习指南/报告/备份（/api/outputs 下载）
```

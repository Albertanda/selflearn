# SelfLearn · 分科学习助手

**把教材、课堂录音、问答和复习资料组织到同一个科目工作区。**

SelfLearn 面向大学课程学习，在本地管理科目资料与学习记录，连接用户自行配置的 AI 服务，
提供知识库问答、长录音转写、错题批改、考点整理和复习资料生成。

*A subject-based AI study workspace with document RAG, lecture transcription, mistake tracking,
review reports, and configurable model providers.*

基于 [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) 裁剪和扩展，
采用 [Apache-2.0](LICENSE) 许可；保留上游代码归属与许可。
上游原版说明归档在 [UPSTREAM.md](UPSTREAM.md)，不代表本分支当前功能。

[快速启动](#快速启动固定数据根) · [模型配置](#模型与供应商管理) ·
[当前边界](#导出报告与删除) · [更新记录](CHANGELOG.md) · [参与开发](CONTRIBUTING.md)

## 可以做什么

| 场景 | 当前实现 |
|---|---|
| 按科目学习 | 独立科目工作台、知识库、错题、考点、知识点和学习画像；聊天可关联科目 |
| 使用课程资料问答 | 上传文档、构建索引、按科目检索，展示来源与实际索引状态 |
| 整理课堂录音 | 持久化转写任务、长音频自动切片、按序合并、失败片段续跑；支持阿里云千问 ASR |
| 练习和复习 | AI 批改、错题记录、基于作答证据的掌握度、考点检测、PDF / Word 复习资料 |
| 生成图表报告 | matplotlib 图表与 ODE 数值检查，经报告专用隔离执行器生成 PDF |
| 管理多个模型来源 | 查询和缓存可用模型、参数来源与自动填入、供应商/连接分组、每轮思考强度、独立默认模型设置 |
| 接入自有网关 | 具名自定义供应商、可改名称与图标，复用对应服务支持的协议 |

后端使用 Python / FastAPI，前端使用 Next.js / React；主要使用环境为 Ubuntu / WSL。
运行数据保存在本地 `data/`，模型请求会发送到所选服务端；这不是默认离线运行的模型发行包。
当前版本包括第一阶段稳定性修复及后续 ASR、模型发现与模型管理改进，仍处于持续完善中。

## 快速启动（固定数据根）

首次先按下方「环境准备」建好虚拟环境。**推荐使用本 fork 的 wrapper**；它会从脚本真实位置解析
checkout、覆盖继承的 `DEEPTUTOR_HOME`，切到仓库根并用该根自己的 `.venv/bin/deeptutor` 启动：

```bash
# 在仓库根目录使用相对路径；不需要先激活虚拟环境
./scripts/start_selflearn.sh

# 开发模式：--dev 原样转发给 deeptutor start
./scripts/start_selflearn.sh --dev
```

从任意 cwd 调用时，使用脚本的完整路径，例如 `/path/to/selflearn/scripts/start_selflearn.sh`。

wrapper 会拒绝调用者传入 `--home` 或 `--home=...`，因为显式 Typer 参数会覆盖固定数据根；
缺 `.venv`、缺本地 CLI 或 CLI 不可执行时它具名失败，不回退系统 PATH、不自动安装。CLI 退出码原样透传。

等价的直接启动方式（**必须在仓库根执行**，并显式固定 home）：

```bash
# 先进入你克隆的仓库根目录
DEEPTUTOR_HOME="$PWD" ./.venv/bin/deeptutor start --home "$PWD"
```

分开启动时同样要固定 root：

```bash
# 在仓库根目录
DEEPTUTOR_HOME="$PWD" PYTHONPATH="$PWD" ./.venv/bin/python -m uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001

# 另一个终端，从仓库根进入前端目录
cd web
node ./scripts/dev.mjs
# 生产构建：node ./scripts/build.mjs && npx next start -p 3782
```

默认浏览器地址为 `http://localhost:3782`，后端为 `http://localhost:8001`；端口占用时以启动日志为准。
在启动器所在终端按 **Ctrl+C**，启动器会通知并清理它启动的前后端进程；分开启动时在各终端分别停止。
关闭项目不会删除科目、配置或学习记录。

> **数据根规则**：`deeptutor/runtime/home.py` 本身仍按「显式 `--home` → `DEEPTUTOR_HOME` →
> 当前工作目录」解析；S12 没有改变这个全局回退行为。安全性来自上面的固定 wrapper/显式命令。
> 从别的目录直接运行 `deeptutor start` 仍可能静默创建空数据树，看不到已有科目。

环境版本、Typst/字体哈希和未验收项见 [`plans/phase1/ENVIRONMENT.md`](plans/phase1/ENVIRONMENT.md)。

## 当前能力与边界

### 模型与供应商管理

- 在设置中配置大语言模型（LLM）、嵌入、语音识别、视觉等服务；“默认模型”页面集中设置默认引用。
  浏览、编辑某个模型与更改默认模型分开，原“应用”按钮继续保留。
- 配好连接后，可首次自动获取模型并缓存，也可手动刷新和输入模型 ID。
  支持的目录接口包括 OpenAI 兼容接口及部分厂商原生接口；不提供目录的服务仍需手动配置。
- 新增模型时，优先填入接口提供的上下文、最大输出、嵌入维数等参数；有限官方文档补充带来源说明。
  **缺失参数保持未知**，不按模型名猜测；刷新不会静默覆盖人工设置或已有索引维数。
- 聊天按供应商/连接再选模型，显示用户设置的模型名称；思考强度按模型真实能力提供，
  包括厂商原生档位、开关或有说明的预算预设，不把所有模型强制映射为相同档位。
- 供应商下拉框末尾有“自定义供应商配置…”入口，可设置名称与图标。
  学校/组织网关须兼容对应服务已支持的协议；仅填写地址不代表支持任意厂商协议。
- 阿里云百炼已提供 LLM、嵌入和千问 ASR 等相关入口。ASR 的已验证型号与配置方法见
  [阿里云 ASR 说明](plans/aliyun-asr/README.md)。

密钥只在本机设置中保存，本仓库不附带可用凭据或任何个人模型连接。

### 知识库与上传

- **文档上传（index）**：服务端先做批量预检/私有 staging，再在科目 KB 事务内发布；页面展示的
  `documents` 是当前权威索引源文件数，不是本次上传文件数或 chunk 数。排队/执行/重建、
  `materials_in_sync` 和图片覆盖警告按服务端实际字段展示。
- **音频上传（transcribe）**：短音频仍保留旧同步响应；两个科目页面的课堂录音改走
  持久化异步 job（202 后轮询，按 180 秒连续切片、顺序合并、失败续跑）。全部片段完成后才把
  音频与 `.transcript.txt` 发布到该科 `materials/lecture/`，**不会自动建立索引**；转写文本只是
  填入考点检测框。二者不可混说。长录音需要显式配置 ffmpeg/ffprobe；没有工具时返回固定
  `asr_dependency_unavailable`，不会假装转写成功。
- **图片覆盖**：未测量时显示未知，跳过/未验证不能描述为完整；覆盖警告来自服务端固定文案。
- **PageIndex**：本 fork 通过既有 rag 工具提供文档树 **outline**（`retrieval_kind=outline`），
  不是 query-grounded passage，也没有 PageIndex MCP 深度检索传输。MCP SDK 仅保留为兼容依赖。
- **知识点掌握度**：没有有效作答证据的聚合知识点显示为**未评估**（`mastery=null`、
  `evidence_count=0`）；0/untracked 只属于单条错题掌握度语义。没有证据不等于已掌握。
- **事实提取**：只有科目作用域的 chat 历史在触发摘要压缩时，才从摘要中提取 learner facts
  写入该科 `profile.json`；科目页画像编辑维护已有 goals/style，教材上传和科目接口不会自动抽取新事实。
  非科目聊天不会写科目画像。

### 导出、报告与删除

- `GET /api/v1/subjects/{id}/export` 导出**科目资料与学习记录**（C12 ZIP：manifest、科目记录、
  学习材料/KB 原件/已完成索引、completed 报告与复习包）。它**不含聊天历史**，也**不提供导入恢复**；
  settings 密钥、别科产物、旧导出 ZIP 和未完成/失败的 report run 不进入包。ZIP 经 manifest/
  逐文件 hash/CRC 独立复核后才发布。
- 图表报告的模型代码与 ODE 数值检查只能走**报告专用受限执行器**：默认只接受真实 `bwrap`
  逐任务 namespace 证明并通过健康探测的 backend；不满足时固定 503，不回退宿主进程。
  普通共享 sandbox runner 不构成报告隔离证明。ODE 检查是固定五点一致性，不等同于进程树 cgroup。
- 删除科目会清理学习树与公开产物树；两棵树先验证、再删除，registry 最后移除，失败不会报告成功。
  HTTP/WS与浏览器入口已在隔离环境验收，范围见第一阶段验收记录。

### 启动/验收门

- S13/P50 已完成本机真实 bwrap 隔离、PNG/ODE、资源/清理及失败发布验收；S14 HTTP/WS和S15浏览器门也已通过。
- 上述验收使用确定性 fake 模型与隔离数据，运行真实本地应用入口；不代表真实供应商质量、真实凭据有效性或生产部署通过。
- 最近一次模型管理独立复核通过 5,247 项 Python 测试、568 项 Node 用例和 8 项 Chromium 场景；
  20 项 Python 测试跳过。另有一次有界 Agnes 真实请求通过，不代表其他供应商均已实测。
  详见 [更新记录](CHANGELOG.md)；原始本机验收证据不随源码公开。
- 第一阶段已关闭，见 [验收与限制](plans/phase1/PHASE1_ACCEPTANCE.md)。
  S14 配置完整性事故保留[用户批准的单项例外](plans/phase1/data_baseline_exception.json)，不声称原配置已恢复。
- 认证默认关闭时是单用户模式；启用 `auth.json` 后 `/api/*`、`/ws/*` 由 `dt_token` cookie 控制。
  不要把服务暴露到公网后再依赖默认关闭的认证。

## 环境准备

需要 Python 3.11–3.13（本机验收使用 3.12）以及 Node.js / npm（本机验收使用 Node.js 22）。
这是源码安装路径；PyPI 上的 `deeptutor` 不等同于本仓库的定制版本。

```bash
git clone https://github.com/Albertanda/selflearn.git
cd selflearn

# 项目不支持 Python 3.14
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[dev]"

# 安装前端依赖
cd web
npm ci
cd ..

# 启动；生产模式首次会构建前端，源码变化后自动重新构建
./scripts/start_selflearn.sh
```

支持的源码 extras：

```bash
pip install -e ".[server]"          # API/Web 服务依赖
pip install -e ".[cli]"             # CLI-only 依赖
pip install -e ".[parse]"           # 可选文档解析引擎
pip install -e ".[math-animator]"   # Manim 动画（另需系统 LaTeX/ffmpeg）
pip install -e ".[dev]"             # server + 开发/测试工具
pip install -e ".[all]"             # server + math-animator + dev
```

`.[partners]`、`.[tutorbot]`、`.[matrix]`、`.[matrix-e2e]` 已移除；不再有伙伴/Matrix 安装面。

## 工具链

二进制与字体不入库（体积大 + 字体版权），首次运行前准备：

```bash
mkdir -p tools/bin tools/fonts
# Typst v0.15.1（静态 musl 版）
curl -L -o /tmp/typst.tar.xz https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz
tar -xJf /tmp/typst.tar.xz -C /tmp/ && cp /tmp/typst-x86_64-unknown-linux-musl/typst tools/bin/
# 中文字体（Windows 源码或任意 CJK 字体均可；代码默认读取 tools/fonts/SimsunExtG.ttf 与 msyh.ttc）
cp /mnt/c/Windows/Fonts/SimsunExtG.ttf /mnt/c/Windows/Fonts/msyh.ttc tools/fonts/ 2>/dev/null || true
```

- **Typst** v0.15.1（`tools/bin/typst`）：PDF 渲染（`--font-path tools/fonts` 提供 Microsoft YaHei / SimSun-ExtG）
- **ffmpeg / ffprobe**：长录音探测、格式归一化与切片；路径配置见下方
- **bubblewrap (`bwrap`)**：图表报告专用隔离执行；需要系统允许相应 namespace 能力，缺失或探测不通过会拒绝执行
- **matplotlib**：图表渲染（报告专用沙箱内执行，带固定五点 ODE 一致性检查）
- **python-docx** / **tiktoken** / **scipy** / **numpy**

## 配置（`data/user/settings/`）

| 文件 | 内容 |
|---|---|
| `model_catalog.json` | 各服务连接、模型、默认引用和自定义供应商定义 |
| `asr_media.json` | 可选的 ffmpeg / ffprobe 绝对路径 |
| `document_parsing.json` | 可选文档解析引擎配置 |
| `token_budget.json` | 节省 Token 开关 + context_ratio（0.1–0.95） |
| `vision_strategy.json` | 视觉策略：auto / prefer_dedicated / dedicated_only |
| `auth.json` | 认证开关与账号存储（启用后由 cookie 保护 API/WS） |

`data/`、密钥、虚拟环境、工具二进制、字体、构建产物及 `.phase1-evidence/` 原始验收目录均不提交。
从 GitHub 克隆仅获取代码、测试和文档，须自行配置模型和工具；科目导出不是完整机器备份。

## 关键接口

```
POST /api/v1/subjects                                 新建科目
POST /api/v1/subjects/{id}/knowledge/upload           上传材料（文档 index / 音频 transcribe）
POST /api/v1/subjects/{id}/knowledge/{kb}/query       RAG 检索
POST /api/v1/subjects/{id}/wrong-book/check           AI 批改（错题自动入库）
POST /api/v1/subjects/{id}/wrong-book/{eid}/attempt   记录作答 → 掌握度更新
POST /api/v1/subjects/{id}/exam-points/detect         考点检测（粘贴转写）
POST /api/v1/subjects/{id}/review-pack                复习指南（format=pdf|docx）
POST /api/v1/subjects/{id}/report                     图表报告（ode_rhs 为图表数值校验基准）
GET  /api/v1/subjects/{id}/export                     科目资料与学习记录 ZIP 导出（不含聊天/无导入恢复）
```

## 数据布局

```
data/user/workspace/subjects/<id>/        # 科目树（M1 扩展）
  knowledge.json / materials/<type>/ / knowledge_bases/<kb>/
  wrong_book.json（含四档掌握度）/ exam_points.json（证据+学期）
  knowledge_points.json（知识点挂链）/ profile.json（偏好/目标/事实）
data/user/subjects/<id>/                  # 产物：复习指南/报告/备份（/api/outputs 下载）
```

`data/partners` 等历史目录可能仍出现在旧数据或迁移说明中；它们不再有运行时伙伴功能，
但不要为了“清理”删除仍含用户数据的目录。Compose 的数据挂载与迁移步骤见
[`CONTAINERIZATION.md`](CONTAINERIZATION.md)。

## 隔离测试入口

运行 Python 测试使用 `.venv/bin/python scripts/run_tests_isolated.py [pytest参数]`。省略参数运行完整测试；入口会在应用导入前创建临时 HOME/配置并阻断非测试网络。直接 `python -m pytest` 收集会被拒绝，以避免再次修改真实设置或调用真实模型。历史阶段日志中的旧命令只作历史记录。

长录音/浏览器验收需要显式媒体工具；Windows 二进制在 WSL 中可直接用引号包裹的绝对路径：

```bash
SELFLEARN_FFMPEG_BIN="/mnt/c/.../ffmpeg.exe" \
SELFLEARN_FFPROBE_BIN="/mnt/c/.../ffprobe.exe" \
./scripts/start_selflearn.sh
```

原生 ffmpeg/ffprobe 在 PATH 中时可省略两项；启动器不会安装或改写系统 PATH。
后端转写任务支持已适配的 OpenAI-compatible multipart STT 和阿里云千问 chat-audio 协议，
不等于支持所有云厂商的文件转写接口。

## 与上游的关系

本分支从 DeepTutor `feat/vision-model`、v1.5.13 基线发展，围绕科目工作区进行裁剪和修复。
Partner / Book CLI 及伙伴、Matrix 安装 extras 已移除；部分共享框架与依赖继续保留，
不把本分支描述为完全重写或已删除全部上游功能。上游 README 多语言归档保持原样。

本仓库的反馈与贡献请提交至 [Albertanda/selflearn](https://github.com/Albertanda/selflearn/issues)。
阶段任务包位于 `plans/`，记录当时的规划、契约与验收范围；其中“尚未实施”等文字可能是历史状态，
当前功能以本文、实际代码及最新独立验收结论为准。

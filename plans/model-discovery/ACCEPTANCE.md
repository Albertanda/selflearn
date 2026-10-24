# MD-R1 验收矩阵与交付

## 强制行为

| 门 | 必须实际证明 |
| --- | --- |
| 七类入口 | llm/embedding/stt/tts/imagegen/videogen/vision 均能打开统一面板；search 没有入口 |
| 目录适配 | 阿里 native 分页、SF 已知子类、兼容列表、Ollama 已安装目录，各有真实 HTTP 形状 fixture；未适配明确解释 |
| 分类/协议 | 明确错类不混入，unknown 需确认，unsupported 禁直接添加；阿里 qwen3-asr-flash 与 filetrans/实时/其他系列有区分 |
| 凭据 | 含点号完整 key、mask、敏感 headers、空值、跨服务、origin 改动、普通用户越权都有测试；无真实秘密 |
| 缓存 | fake clock 测 TTL/冷却/旧目录，真文件验证重开后可用，错误/损坏/并发/容量/隔离均覆盖 |
| 首次获取 | 当前已保存普通连接首次访问自动查询；输入期间不发请求；重开走缓存，显式刷新可重试，StrictMode 不风暴 |
| 无破坏添加 | 取消面板不改 draft；勾选确认只加入 draft，未保存不进聊天；刷新不删旧模型/别名/参数/默认项 |
| 迟到响应 | A→B、跨服务、同 binding 改地址/密钥、保存前后、删 profile 的旧请求均丢弃 |
| 隐藏/权限 | 隐藏保留配置与授权；当前默认不可隐藏；普通用户仅可见已授权候选；仅获授权隐藏模型不锁死既有会话 |
| 隐藏后重开会话 | 新候选无隐藏项，当前已选隐藏项显示解释并可继续发请求；刷新页面仍成立，不只依靠内存旧 label |
| 回归 | ASR-R1、阿里 ASR、旧同步转写、原 LLM options、CodeBuddy、Codex OAuth、secret-mask 和 grants 无退化 |
| 完整性 | 真实六树及补充秘密目录到达/收尾一致；无真实厂商调用；旧已封存证据保持不变 |

不能只测 helper 后说 UI 已完成。Node 可执行生产 hook/组件接缝，浏览器必须覆盖真实 React 界面及持久化。

## 命令

Python 必须通过隔离 runner。媒体测试在隔离 home 下无法读取真实 asr_media 配置，应通过环境提供已有工具路径：

```bash
SELFLEARN_FFMPEG_BIN="/mnt/c/Users/17261/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin/ffmpeg.exe" \
SELFLEARN_FFPROBE_BIN="/mnt/c/Users/17261/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin/ffprobe.exe" \
.venv/bin/python scripts/run_tests_isolated.py -q \
  tests/services/model_discovery tests/api/test_model_discovery.py \
  tests/api/test_model_visibility.py tests/phase1/test_model_visibility_access.py \
  tests/services/model_selection tests/services/config \
  tests/services/test_model_catalog.py tests/asr tests/services/test_voice.py \
  tests/api/test_voice_routes.py tests/phase1/test_p1_01.py tests/phase1/test_p1_16.py
```

普通用户授权与 OAuth 测试如实际在其他目录，定向加入，不删除既有用例、不对失败集 deselect。

在 `web/`：

```bash
npm run test:node
./node_modules/.bin/tsc --noEmit
npm run i18n:check
```

对本次修改的 TS/TSX 文件运行本地 ESLint；对 Python 修改运行 `.venv/bin/ruff check <changed-python-paths>`；最后 `git diff --check`。
不为了让检查通过升级依赖、改 strict/skip/error 策略或删除失败旧断言。旧警告与新失败区分记录。

## 浏览器

新增 `web/playwright.model-discovery.config.ts`，复用 `playwright.phase1.config.ts` 的临时源码、guard、端口所有权和清理机制。现有 loopback model fixture 定义在后者的 MODEL_SERVER 字符串中；必要时只在该接缝增加本功能目录 fixture，不能解除隔离。

本机已有 Chromium：`/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`。
用新的未使用 evidence 子目录，`workers=1, retries=0, forbidOnly=true`。实际执行：

```bash
S15_EVIDENCE_DIR="/home/albert/selflearn/selflearn/.phase1-evidence/model-discovery/MD-R1-<fresh>/browser" \
./node_modules/.bin/playwright test -c playwright.model-discovery.config.ts
```

`<fresh>` 必须替换为本次真实目录。不得复用 S15、ASR 或阿里 ASR 已封存目录，不设置源码副本为真实 checkout。

至少实际交互：

1. 保存 fixture 连接，打开模型区域触发首次目录；关闭重开不增加上游读取。
2. 查询并搜索、多选添加，未保存不进聊天，保存后可选；已有条目 id/别名/默认保持。
3. 延迟 A 查询后切 B，B 页面、draft、缓存正确；refresh 失败保留旧候选与未保存更改。
4. 隐藏非默认 LLM，新列表不显示；已有会话与页面刷新后的当前隐藏项仍可用。
5. 当前默认隐藏操作被拒绝；普通用户越权目录请求失败；其已授权隐藏模型不造成能力错误撤销。
6. 七个类别入口逐项检查；selected-service 对应不同目录响应，不用一个永远返回 chat 的 fake 冒充全部支持。

做两个坏对照：临时源码副本中分别移除连接 generation 校验、恢复旧覆盖式同步；测试必须在本功能行为断言失败。导入失败/浏览器缺失不算坏对照成功。之后正常源码不受修改。

## 交付格式

`report.json` 至少包含 stage=MD-R1、status、前置阿里验收引用、每卡目标/证据/完成条件、实际变更文件、每个 adapter×service 的 remote/preset/unknown/unsupported 矩阵、测试 passed/failed/skipped、命令日志定位、浏览器与坏对照、完整性和限制。

`execution.log` 追加实际命令、cwd、UTC、原输出和退出码，不写事后伪造的一行“通过”。真实数据保护失败是硬失败；环境门不能执行就写 blocked_environment。

保留原工作区的已修改/未跟踪文件；不要拿 HEAD 当干净前置版本。本次到达快照是 scope 基准；源码归档只做一次，包含前置未跟踪修复和本次文件，排除 data/秘密/依赖/构建产物，解包逐项哈希核验。不要为每张卡做 tar。

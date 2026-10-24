# MM-R3 验收门

每项由生产函数行为/实际请求构造证明，不以源码字符串或HTTP200代替。开发使用隔离配置、本地模型服务与已安装浏览器，不访问真实厂商。

| 门 | 必须证明 |
|---|---|
| B01 | 两层选择：第一层连接、第二层模型，选择第一层不暗切模型；同名原厂/阿里可辨，同厂商两连接独立 |
| B02 | 已选、系统默认、隐藏当前项、跨供应商搜索、刷新失败、空列表、键盘/触屏/返回可用；两个composer一致 |
| B03 | 思考能力同一后端策略贯通目录/cache/catalog/options；DeepSeek effort元数据不丢；未知代理不套原厂 |
| B04 | 原厂Flash/Pro low/high/max，minimal→low、medium/xhigh→high、ultra→max；none/off独立，provider_default无项目注入 |
| B05 | 阿里DeepSeek按版本、Qwen按effort/budget区分；Claude effort+adaptive/旧budget正确；Gemini、OpenAI/托管按真实协议 |
| B06 | 多档支持者不少于其真实三档；binary如实开关，预算预设清楚标注，未知不虚构档位或直接乱发参数 |
| B07 | 请求正式schema：inherit/default/effort、未知字段/非法值/跨profile及权限校验；旧请求兼容 |
| B08 | 不同session/profile并发不串强度；换模型恢复各自值，刷新/重连/regen/分支/题目跟进保留正确snapshot |
| B09 | 默认API只patch引用：保留模型参数/密钥/未知字段；409/422/403/幂等；Save/Apply带revision并发不丢配置 |
| B10 | 默认页首项、中文大语言模型（LLM）、一个默认LLM及现有其它服务；search是profile而非模型 |
| B11 | 浏览/切tab/诊断/添加后续模型/参数预览/重命名不改已有默认；未保存新模型不进入默认候选 |
| B12 | 明确保存默认才改变后续调用；取消/失败保留；与其它页dirty编辑互不丢失，应用仍存在且语义清楚 |
| B13 | 普通用户只看到授权连接和能力；managed不改key/登录，隐藏规则和稳定ID保留 |
| B14 | MD-R2所有参数/名称/缓存/凭据回归及协调者嵌入修复通过；真实六树不变，无真实推理/重建 |

## 浏览器必须实际操作

新增 MM-R3 wrapper，复用现有 disposable source、MODEL_SERVER、本地端口、Chromium 和cleanup。原MD-R2浏览器另跑一次回归；不用只发 API 请求充当 UI。

1. 配置两个本地fixture连接模拟 DeepSeek 原厂与阿里，放相同自定义模型名、不同调用ID/版本。点击两层切换，按钮始终显示来源，捕获实际请求去正确 endpoint。
2. 在聊天选择 low/high/max，至少实际发送两次不同强度，断言wire值随选项变化；选择继承、厂商默认、关闭的请求字段不同。切到仅两档/预算/未知fixture，非法选项不能误发。
3. 题目跟进控件真实发送一轮，不能仅证明已挂载 label。刷新会话、重新生成，捕获仍是对应快照或用户明确修改后的强度。
4. 模型设置浏览不同profile/model、测试连接和导入后续模型，再保存/应用，原默认不变。进入默认页显式选择后保存，新的未指定模型对话才使用新默认。
5. 默认页取消、保存失败、并发409、其他页面未保存参数保留；未保存新增模型不在本页候选。搜索/STT/TTS等至少fixture验证引用合法性；改embedding默认不发推理和索引操作。
6. 键盘导航和窄屏实际走完两层，中文导航顺序/名称与应用说明正确。普通用户权限由API测试覆盖，若浏览器不启用auth须说明限制，不伪造登录验收。

## 检查命令

根目录：`.venv/bin/python scripts/run_tests_isolated.py -q tests/services/model_discovery tests/services/model_selection tests/services/config tests/services/llm tests/services/session tests/api/test_model_discovery.py tests/api/test_model_visibility.py tests/api/test_default_models.py tests/api/test_unified_ws_turn_runtime.py tests/core/test_agentic_client_provider_kwargs.py`。

待新测试创建后运行相应列表。相关通过后完整 `.venv/bin/python scripts/run_tests_isolated.py` 一次；仅因新增变更、失败或未解风险再重跑。需要ASR回归时复用已有 SELFLEARN_FFMPEG_BIN/SELFLEARN_FFPROBE_BIN 和 DATA_GYM_CACHE_DIR，不能安装/下载或读取真实catalog作fixture。

web目录：`npm run test:node`、`npx tsc --noEmit`、`npm run i18n:check`、实际改动ESLint；根目录实际改动Ruff、git diff --check。当前Node22聚合runner可能只报文件数，协调者逐文件直接运行得到540真实用例（MD-R2基线），统计时区分文件数和用例数，不虚报。

浏览器用新的 `.phase1-evidence/model-management/MM-R3-<run>/browser` 和 wrapper，不覆盖封存路径；禁止指向真实运行目录。环境拒绝本地listen时记录原因，不取消项目隔离guard或降级验收定义。

## 统一交付

新证据根包含 report.md/report.json、B01–B14对应测试和路径、实际协议请求脱敏记录、浏览器截图/断言/cleanup、官方能力规则来源、测试命令/退出码/数量、到达及最终源码hash/可重建归档、真实六树前后opaque compare。

明确区分本地mock与真实服务验证；所有硬门通过才报 verified_local，accepted由协调者独立复核。不能自报38厂商真实通过或以UI档位数冒充实际推理区别。整阶段一次交付，不逐卡询问继续，不进入科目/知识库/ASR新功能。

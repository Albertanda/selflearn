# S15 已探索文件清单＋关键片段
配合 START_S15.txt 执行。以下定位已由协调者定向探索并校验；先核对文件SHA，匹配时复用，只补读实际需要的接口，不重做全仓orientation。源码片段带一基行号。浏览器尚未启动/验收，环境仅为只读存在性观察。
机器索引位于 `.phase1-evidence/reviews/S14-final/s15_packet_index.json`（相对项目根）；本文件包含全部清单与片段，无须先浏览其他目录。旧S14探索包保持原样。
用户授权单项catalog例外已写 `plans/phase1/data_baseline_exception.json`。S15须继承新基线且零增量；这不表示原配置恢复，也不准修改其他真实数据。
## 已探索文件清单
| 文件（项目根相对路径） | SHA256 | 用途 |
|---|---|---|
| `plans/phase1/cards/P1-53.md` | `a7dce5109ef17983a8e02c8059adebdc5d8c77e0b8975b65c718bb54dfee569d` | 目标、允许范围、环境与验收条件 |
| `plans/phase1/stages/S15.md` | `9511e5cb76ad4c4ceee25e13a3edb38fb3aca12bc34531477ca7d79b5b6072c4` | 阶段边界、唯一单元和阶段验收 |
| `plans/phase1/DATA_CONTRACTS.md` | `d991c1737e55f6902e1524c1485cb52a23977168dd21c52dfa9d37d37143cdae` | C08 scope语义、C13异步UI/入口和C14真实浏览器要求 |
| `web/playwright.config.ts` | `243bb8fa7f8a6d0d571141de1a7215a209ef3d5a890049f1261bf09051f38e43` | 现有Playwright配置、testDir/project/baseURL |
| `web/package.json` | `bb41eb69e966ea306d3415bde85f006c52ece489c5b1b5cb02f29fd3e0db1991` | 启动/测试脚本及Playwright依赖 |
| `web/next.config.js` | `d2bc969698138761cb7135511f3be6e5e7080bb3b9e282c00bdddc6965dd0d66` | 配置读取、backend port/base与独立distDir |
| `web/scripts/dev.mjs` | `04aeb113689e06808a6c72e0ea4fde8619538de85500deb2312eb5d0d91215d4` | dev启动脚本向Next转发参数和环境 |
| `web/proxy.ts` | `21fdea851cc844821be1734f8a87c2a3b832ff2929791862031b3fc9113c12f0` | runtime API base、HTTP/WS rewrite和matcher |
| `web/lib/api.ts` | `cd93ae4d5180251ef80e158889878638fa70fb0741d7cef7b8094e8b6a834de0` | 前端同源API/WS URL与请求行为 |
| `web/app/(workspace)/page.tsx` | `728dcd712faf023a482626d0d472af191a86daeaaaa7a9d5cb302a6fd3ac288c` | 旧首页重定向到聊天路由 |
| `web/app/(workspace)/home/[[...sessionId]]/page.tsx` | `02c74fb939a35a88bd02e2d6177017c709588ca0390e324be950d1716fd9bb46` | 聊天页provider、会话加载和SubjectSelector接线 |
| `web/components/chat/home/ChatComposer.tsx` | `053fd79b868532629d251151e4453b1950063332fdc1d4d899bb48b5b1a8f491` | 聊天composer里subject选择器调用 |
| `web/components/chat/home/SubjectSelector.tsx` | `38f08ded9dfe097299cc39b61d64837960c789c395852bbd75309bb744211370` | 按钮title、菜单项文本、清空选择行为 |
| `web/context/UnifiedChatContext.tsx` | `cefdc1d5b56e46f36456b2ec5ee0fc585149fce0d4685a059d176c29dc61d81d` | load/revalidate时恢复scope、未hydrated发送闸门接口 |
| `web/lib/subject-scope.ts` | `bb1c00d0aeb3e9b4a46c51c110fc63877870f30f4afabd964aa795beb59cba9a` | 三态scope、explicit null、session revalidation |
| `web/app/(workspace)/subjects/page.tsx` | `5474afefa9957975923200179d3a52caf2dad1b12c57358344cd2c980532b9fe` | 科目列表加载、创建、可见表单与行操作 |
| `web/app/(workspace)/subjects/[id]/page.tsx` | `4b90d2d16585adca77c170f6f293b9e9d054497f73488876d70f980aa27edef7` | 详情加载、导出、ASR上传和可定位UI文本 |
| `web/lib/subject-results.ts` | `a1ef93176e9ad07e1d060305a2ac076fca28fccbf6ea13b98adc11d63675666c` | 导出下载URL校验和ASR转写结果的用户消息 |
| `web/app/(utility)/knowledge/page.tsx` | `54e2d9be856f7ef9f4199e87ae3c3a4f2063e03826d5de7ce91d81be81e63b62` | 知识中心页面入口 |
| `web/components/knowledge/KnowledgePage.tsx` | `08ce3e7b11580a56b71b8b955a89968b771e47e34bfab15bb618ea0e368f3b60` | 知识中心create modal状态和开关接线 |
| `web/components/knowledge/KnowledgeHome.tsx` | `9d2a7803753ce92362f6d5f786247cbf06701cdb75efad10abb6478bfba788aa` | 可用的New knowledge base入口 |
| `web/components/knowledge/CreateKbModal.tsx` | `830f53decb9bd5c7c4d3f9b3628cce000d0a400bb9e5c46e6f62555029fd7788` | 新建知识库modal状态/reset逻辑 |
| `web/lib/knowledge-api.ts` | `4ad38aa993282636eb9d01a370ce82cd51ac5348ecbd0d724a6b64b0d7ceec47` | knowledge create及Obsidian client遗留接口边界 |
| `web/tests/e2e/compliance-and-ux.audit.ts` | `15281c493dec962b26d161ccef583f3603f983fca8640fd9c87b958939a080c3` | 现有Playwright浏览器测试类型与selector风格 |
| `web/tests/phase1-25.test.ts` | `cac674432ac14854bc1378d5a641d19eef420ddb2488b996f882331afdc128c5` | scope行为已有node逻辑测试，不是浏览器验收 |
| `web/tests/phase1-43.test.ts` | `8f02b4e45935f252bf1e90c14ce4e6d6553b06b17970ab7effdf4a3444912b6d` | Obsidian入口裁剪现有node测试，不证明真实页面浏览器行为 |
| `tests/conftest.py` | `5d42c9bea0c5fd45778568822a5ed8043bbdbcfc6740dc9f5d8a6d6e9bb91e9f` | pytest导入前必须有隔离环境变量 |
| `tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | p1_runtime和provider fixture接口 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 临时home/网络guard/同进程provider stub/ASGI TestClient边界 |
| `tests/phase1/test_http_acceptance.py` | `e16fa7e1130bb25c93ef4ad7877ce3126423dd7d08d4a8c97236b5d814cb4c23` | S14 HTTP临时app、CRUD、download/export/delete断言 |
| `tests/phase1/test_ws_acceptance.py` | `a7e9b84d05fdeffd6af368d8af7a7c245b53906eb0efa46775de7ea65d978ab7` | S14 WS in-process测试及临时home子进程formal app探针 |
| `deeptutor/api/main.py` | `a7a360ff67d59ad31f42d25b64a7a06a2cf7f0b9fbb070063463bceefefa042b` | 真实FastAPI导入期副作用、lifespan、subject和WS路由注册 |
| `deeptutor/api/routers/subjects.py` | `adae1fb5bfadd9921adec8765e2432b1d8d3b57347afc5ce845da3face9e7816` | 真实subject路由和current-user scoped list/create/patch |
| `deeptutor/api/routers/unified_ws.py` | `5a6bed835c44b05702bc32b0e0c0a1a2c9843a5fc420a1e0f954c1b55e5e7b60` | 真实/api/v1/ws endpoint与upgrade/auth |
| `web/app/api/v1/knowledge/create/route.ts` | `db05aefb97f7b09c840ea47e5ccf6f49eb661aee65de12bf5510febe9431397a` | Next知识库创建流式route的接线 |
| `web/app/api/v1/knowledge/[kbName]/upload/route.ts` | `db05aefb97f7b09c840ea47e5ccf6f49eb661aee65de12bf5510febe9431397a` | Next知识库上传流式route的接线 |
| `scripts/run_tests_isolated.py` | `36b00721c2f87e87461bb846bb662258a8cca4a560e1045c89e28cc8531495c9` | 临时HOME测试运行器和Python网络guard的继承方式 |
| `scripts/phase1_data_baseline.py` | `90442088f8a6f8731a940b081db2aa430f4518c601a1b0286c5ee8a77e6122ab` | 旧基线验证与单项获批例外校验 |
| `plans/phase1/data_baseline_exception.json` | `a8dd11a3d2551b94b6d51718736af99725949899ec9f71e8b061c0ce0340f0d5` | 用户批准的model_catalog单项新基线例外声明 |

## 环境事实与接线限制
```json
{
  "package_declared_playwright": "@playwright/test ^1.53.2",
  "installed_playwright_test_version": "1.57.0",
  "playwright_cli": {
    "path": "/home/albert/selflearn/selflearn/web/node_modules/.bin/playwright",
    "exists": true,
    "is_file": true,
    "executable": true
  },
  "browser_executables": [
    {
      "path": "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
      "exists": true,
      "is_file": true,
      "executable": true
    },
    {
      "path": "/home/albert/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell",
      "exists": true,
      "is_file": true,
      "executable": true
    },
    {
      "path": "/mnt/c/Users/17261/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe",
      "exists": true,
      "is_file": true,
      "executable": true
    }
  ],
  "existing_dist_dirs": [
    {
      "path": "/home/albert/selflearn/selflearn/web/.next",
      "exists": true
    },
    {
      "path": "/home/albert/selflearn/selflearn/web/.next-deeptutor",
      "exists": true
    }
  ],
  "launched": false,
  "browser_tested": false
}
```

S14 TestClient为进程内ASGI，不是浏览器可连的TCP服务，monkeypatch不会跨子进程。S15必须建立受控临时前后端、确定性provider边界及真实WS升级；正式app导入前固定临时根。Next配置从源码相邻settings读取，因此要临时源码副本；proxy由DEEPTUTOR_API_BASE_URL指向受控后端。stat可执行不等于浏览器已能启动，禁止自动下载。

## 关键原文片段

### `plans/phase1/cards/P1-53.md`

L1–L21：

```text
0001: # P1-53：浏览器验收科目状态与现有工作台
0002: 
0003: 状态：planned；类型：gate；审阅风险：gate。依赖：P1-49, P1-25, P1-42, P1-43, P1-51, P1-52。
0004: 
0005: ## 目标
0006: 
0007: 真实浏览器验证选择/刷新/清空、索引/ASR消息、失败解除busy及死入口消失。
0008: 
0009: ## 已有问题证据
0010: 
0011: node纯逻辑tests不证明实际菜单位置、会话hydration或浏览器async状态。
0012: 
0013: ## 必读输入
0014: 
0015: - 仓库 AGENTS.md、plans/phase1/EXECUTION_GUIDE.md 和 FRAMEWORK.md 的阶段边界。
0016: - DATA_CONTRACTS.md 的 C13, C08, C14；此处不得自行改契约。
0017: - 本卡允许的现有实现和依赖卡 completion.json，核实前置通过后再编辑。
0018: - PROJECT_AUDIT_2026-10-10.md 对应发现；源码行号可能已随前置卡变化，应按符号定位。
0019: 
0020: ## S15执行细化
0021: 
```

L31–L54：

```text
0031: 历史单卡模式的证据目录为 `.phase1-evidence/P1-53/` ；阶段模式改用所属 `.phase1-evidence/stages/<stage_id>/` 写共享证据。允许编辑测试不是允许删除有效断言/添加skip。依赖卡文件可以读取；未列文件不得写。
0032: 
0033: ## 执行步骤
0034: 
0035: 1. 使用现有@playwright/test和临时源码副本，临时home与本机stub，不连接真实六科实例；若浏览器未安装写环境阻塞。
0036: 2. 显式设置 DEEPTUTOR_HOME、BACKEND_PORT、DEEPTUTOR_API_BASE_URL、NEXT_PUBLIC_API_BASE_EXTERNAL、DEEPTUTOR_NEXT_DIST_DIR 指向临时实例/独立dist，不能覆盖生产.next/.next-deeptutor；next.config.js依赖源码副本旁settings，因此副本只能有虚构配置。
0037: 3. 检查菜单可见和选最后一科、刷新session恢复、切会话/quiz保持scope。
0038: 4. HTTP故障/断网/导出失败/ASR成功分别截图或结构断言；不得只检查源码contains。
0039: 5. 最终写stage acceptance汇总，列G0–G4证据；G5签收由主审阅者执行，不伪造accepted。
0040: 
0041: 
0042: ## 证据：如何证明完成
0043: 
0044: 以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：
0045: 
0046: - [ ] 刷新scope、clear及quiz实际请求字段正确
0047: - [ ] 故障busy最终false且无success文案
0048: - [ ] ASR不声称index ready
0049: - [ ] Obsidian不可点、其他KB入口可用
0050: - [ ] 跨科source显示正确、下载URL有效
0051: 
0052: 执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：
0053: 
0054: ```bash
```


### `plans/phase1/stages/S15.md`

L4–L13：

```text
0004: 
0005: 按STAGE_WORKFLOW.md执行。小卡是阶段内编码单元，不是人工交接关口；完成一单元本地验证后继续本阶段下一单元，阶段末一次提交审查。
0006: 
0007: ## 目标与前置
0008: 
0009: 完成 浏览器验收与最终签收准备 的现有修复，契约 C08, C13, C14。
0010: 跨阶段依赖：S07, S11, S13, S14；当前source需与相应review receipt一致。
0011: 
0012: ## 实施顺序与范围
0013: 
```

L15–L34：

```text
0015: 
0016: 允许更改文件为上述单元白名单的并集；不得因为同一文件在并集中，就修改卡目标以外的功能。
0017: 
0018: - `web/e2e/phase1.spec.ts`
0019: - `web/playwright.phase1.config.ts`
0020: 
0021: ## 证据与完成条件
0022: 
0023: - 开始前留阶段source/data基线；阶段内逐单元使用定向测试，不重复读取全部仓库与全部卡。
0024: - 有效负例先从合法正例只改变目标字段/故障点；错误响应不回显输入值；高风险单元用独立坏对照确认断言能拦缺陷。
0025: - 必要命令如下；执行未通过时在本阶段范围内自修再复测。通常node/tsc等共享命令在阶段末合并一次，有新改动或失败才追加复跑。
0026: 
0027: ```bash
0028: cd web && ./node_modules/.bin/playwright test -c playwright.phase1.config.ts
0029: ```
0030: 
0031: - 阶段report.json包含各卡结果、实际命令/退出码/日志定位、scope与data检查、限制；不得为凑文件再生成每卡长报告。
0032: - scope_check按本阶段白名单并集，真实数据/前人修复保持；交付状态verified_local，accepted只由独立审阅者写review.json。
0033: - 真实OS/浏览器不足如实blocked_environment，不以skip或fake backend替代；不得自动安装、升级、使用真实供应商。
0034: - 阶段内无需请求下一张卡批准；阶段末停止，等待阶段review。跨范围/契约/真实数据/环境问题才提交阻塞。
```


### `plans/phase1/DATA_CONTRACTS.md`

L102–L116：

```text
0102: ## C08：聊天科目作用域与知识库标识
0103: 
0104: 输入 subject_id 采用三态：未提供沿用当前 session.preferences.subject_id，null/空字符串明确清空，非空字符串设置。支持顶层字段及旧 config.subject_id；两者同时提供且不相等为 invalid_input。不能用 `a or b` 丢掉清空值。验证发生在创建 turn/写用户消息前。新 session 无值即 null；切换 session 不继承另一 session 的选择。
0105: 
0106: 复用已存在 preferences_json 保存 subject_id，不新增 SQLite 列或配置数据库，不改变 session store API。运行 metadata 带 resolved subject_id，request_snapshot 保存本轮 resolved 值，以便重试/再生成使用原作用域；UI 恢复 preferences 后才允许发送。被删科目的历史会话提示 subject_not_found，用户显式清空后恢复普通聊天，不静默选别科。
0107: 
0108: subject KB wire id：`subject:kb:<subject_id>:<kb_name>`。subject_id/kb_name 均不含冒号；中文按字符串存储，URL 路径各段单独编码。既有 admin:kb:/user:kb: 保留。不修改知识库磁盘名字。
0109: 
0110: 内部 resolved resource 包含 wire id、真实 name、subject_id|null、当前用户 base_dir、read_only；base_dir 不进入模型工具 schema/公开响应。显式 subject ref 必须属于本轮 subject，且该科/KB存在、权限通过；scope mismatch 报 403，缺库报 404，不回退全局。所有构造路径在服务端。
0111: 
0112: 本轮 knowledge_bases = 用户显式挂载的合法全局 ref + 当前科目所有 ready 的 subject refs，稳定去重。未 ready 的当前科库用 warning 表达，不挂载成功检索列表；空科目不附加全局默认库。模型工具参数 enums 使用 wire id。legacy bare name 仅在本轮已挂载资源中唯一匹配时接受；重名为 invalid_input，不能猜 subject/global 任一来源。
0113: 
0114: rag 和 kb_files 使用同一 resolver，ready/权限制约一致。返回来源必须带 kb_ref、subject_id、源文件名/页码（若原 parser提供），不只带重名 kb_name。已有 read_source 仅从 server source_index 读附件 ID，保持此约束，不增加“任意文件路径读取”或新的全文 KB 阅读功能。附件来源和 KB 引用不可混为同一个 id。
0115: 
0116: 不能因科库检索失败悄悄改用全局 KB 回答；WS/工具失败必须可见。全局用户访问规则保持。PageIndex 的概览路径在 C13 单列，不宣称本阶段新增深度 MCP 检索。
```

L175–L195：

```text
0175: ## C13：UI、裁剪与能力说明
0176: 
0177: - 所有修改的 async action 有 try/catch/finally，失败解除 busy，不显示成功计数/生成链接。post 非 2xx 不继续按成功刷新；读取 error.message，兼容旧 detail 文本。界面不展示 traceback/provider密钥/宿主路径。
0178: - subject selector 提供无科目选项；从当前 session 的 preferences 恢复，能力参数与 subject_id 合并不能覆盖彼此。刷新恢复未完成时不能发送旧科目的请求。
0179: - 上传 operation=transcribe 时显示转写完成与文本去向；index 时显示任务/状态；documents从C07，coverage降级可见。不新增“音频自动建库”或全新批改界面。
0180: - 去掉 Obsidian 可点击创建入口及活跃宣传。保留 501 API 和合法历史数据读取拒绝；不删除用户原 vault/旧 KB 目录。
0181: - 删除 partners/tutorbot/matrix 依赖 extras 和 requirements 镜像，root requirements 改 server；修对应打包断言。保留 CLI、scheduler、sandbox runner、office skills、built-in deferred_tools、load_tools、多用户上下文和现有内置 capability。不按词删 runtime/providers。
0182: - PageIndex 可用 REST outline 能力保留且如实标注 retrieval_kind=outline，不宣称有不存在的 MCP 深度检索工具。当前 prompt/挂载应能走既有概览检索，不引入外部 transport。MCP SDK 暂保留但注释标“兼容待审查”，不是“当前自动注入client”；后续若需要移除，另立有完整动态插件/打包证据的卡。
0183: - 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。
0184: 
0185: ## C14：证据与阶段验收（2026-10-11修订）
0186: 
0187: 每张小卡仍需正向和独立反向行为证据；合法负例从已证明有效的base只改一个字段/故障点。高风险用一个针对性坏对照确认断言捕获真实效果，禁止只看源码contains或mock自证。该义务不要求每卡交付一份独立人工报告。
0188: 
0189: 每阶段一个执行会话，阶段内按stages.json既定顺序串行卡。报告/审查为阶段粒度，规则见STAGE_WORKFLOW.md。新阶段使用StageReport schema：stage_id/status/baseline_id/card_results/commands/scope_check/real_data_unchanged/limitations。card_results含卡ID、目标、修改路径、断言、命令定位和限制；commands保存实际命令、cwd、exit、共享execution.log行号，不能只写摘要“通过”。
0190: 
0191: 单元状态verified_local表示本地验证；阶段末由协调者独立复核并写review.json的accepted，执行者不能自签。历史P1-00/completion.json保持原样，协调修补/签收另存reviews/P1-00；旧Completion schema继续兼容明确单卡调用，不强制后续每卡创建文件。
0192: 
0193: 真实数据保护失败立即停止；环境缺失用blocked_environment，不以skip/mock作为真实验收。源码增量按阶段开始前快照和阶段白名单并集检查，不把继承dirty计为新改动。日志仅追加保存失败尝试；原始baseline/归档不可覆写。新v2快照包含批准新增源文件和mode，历史v1只能证明它当时记录的范围。
0194: 
0195: 最终验收仍需完整pytest 0 failed、原403前端测试保留且新增行为测试通过、tsc/相关ruff通过、scope/data不变，以及真实HTTP/WS/OS sandbox/浏览器场景。passed计数可随新增用例增长；合法旧skip保留，不新建skip/xfail逃避本阶段要求。主审阅者可在已授权范围直接修复并复测，披露自己的修改，不能用新的自证代替独立验收。
```


### `web/playwright.config.ts`

L1–L27：

```text
0001: import { defineConfig, devices } from "@playwright/test";
0002: 
0003: const BASE_URL =
0004:   process.env.WEB_BASE_URL ||
0005:   process.env.NEXT_PUBLIC_API_BASE ||
0006:   "http://localhost:3000";
0007: const SERIAL_MODE = process.env.PW_SERIAL === "1";
0008: 
0009: export default defineConfig({
0010:   testDir: "./tests",
0011:   fullyParallel: !SERIAL_MODE,
0012:   forbidOnly: !!process.env.CI,
0013:   retries: process.env.CI ? 2 : 0,
0014:   workers: SERIAL_MODE ? 1 : undefined,
0015:   reporter: [["html", { open: "never" }], ["list"]],
0016:   use: {
0017:     baseURL: BASE_URL,
0018:     trace: "on-first-retry",
0019:   },
0020:   projects: [
0021:     {
0022:       name: "ui-audit",
0023:       testMatch: "**/*.audit.ts",
0024:       use: { ...devices["Desktop Chrome"] },
0025:     },
0026:   ],
0027: });
```


### `web/package.json`

L1–L20：

```text
0001: {
0002:   "name": "opentutor-web",
0003:   "version": "1.0.0",
0004:   "private": true,
0005:   "scripts": {
0006:     "dev": "node ./scripts/dev.mjs",
0007:     "dev:turbo": "node ./scripts/dev.mjs --turbopack",
0008:     "build": "node ./scripts/build.mjs",
0009:     "start": "next start",
0010:     "lint": "eslint .",
0011:     "test:node": "node ./scripts/run-node-tests.mjs",
0012:     "perf:check": "node ./scripts/route_budgets.mjs",
0013:     "build:perf": "npm run build && npm run perf:check",
0014:     "i18n:parity": "node ./scripts/i18n_parity.mjs",
0015:     "i18n:audit": "node ./scripts/i18n_audit.mjs",
0016:     "i18n:audit:strict": "node ./scripts/i18n_audit.mjs --strict",
0017:     "i18n:check": "npm run i18n:parity && npm run i18n:audit",
0018:     "audit": "playwright test --project=ui-audit",
0019:     "audit:ui": "playwright test --ui --project=ui-audit",
0020:     "audit:report": "playwright show-report",
```

L45–L54：

```text
0045:     "remark-math": "^6.0.0",
0046:     "tailwind-merge": "^3.4.0"
0047:   },
0048:   "devDependencies": {
0049:     "@playwright/test": "^1.53.2",
0050:     "@types/node": "^25",
0051:     "@types/react": "^19",
0052:     "@types/react-dom": "^19",
0053:     "@types/react-syntax-highlighter": "^15.5.13",
0054:     "autoprefixer": "^10.4.20",
```


### `web/next.config.js`

L47–L76：

```text
0047: const SETTINGS_DIR = path.resolve(__dirname, "..", "data", "user", "settings");
0048: const SYSTEM_SETTINGS = readJsonFile(path.join(SETTINGS_DIR, "system.json"));
0049: const AUTH_SETTINGS = readJsonFile(path.join(SETTINGS_DIR, "auth.json"));
0050: const BACKEND_PORT = firstNonEmpty(
0051:   process.env.BACKEND_PORT,
0052:   SYSTEM_SETTINGS.backend_port,
0053:   "8001",
0054: );
0055: 
0056: // Use data/user/settings as the frontend source of truth. Environment values
0057: // remain explicit deployment overrides for Docker/CI.
0058: const NEXT_PUBLIC_API_BASE = firstNonEmpty(
0059:   process.env.NEXT_PUBLIC_API_BASE_EXTERNAL,
0060:   SYSTEM_SETTINGS.next_public_api_base_external,
0061:   process.env.NEXT_PUBLIC_API_BASE,
0062:   SYSTEM_SETTINGS.next_public_api_base,
0063:   `http://localhost:${BACKEND_PORT}`,
0064: );
0065: 
0066: const NEXT_PUBLIC_AUTH_ENABLED = normalizeBoolean(
0067:   firstNonEmpty(
0068:     process.env.NEXT_PUBLIC_AUTH_ENABLED,
0069:     process.env.AUTH_ENABLED,
0070:     AUTH_SETTINGS.enabled,
0071:     "false",
0072:   ),
0073: );
0074: 
0075: process.env.NEXT_PUBLIC_API_BASE = NEXT_PUBLIC_API_BASE;
0076: process.env.NEXT_PUBLIC_AUTH_ENABLED = NEXT_PUBLIC_AUTH_ENABLED;
```

L93–L100：

```text
0093: const nextConfig = {
0094:   // Keep the production build used by `deeptutor start` separate from the
0095:   // `.next` development cache used by the explicit `deeptutor start --dev`.
0096:   // Without separate directories either command can invalidate the other
0097:   // process while it is running.
0098:   distDir: process.env.DEEPTUTOR_NEXT_DIST_DIR || ".next",
0099: 
0100:   // Expose the build-time version to the browser so the sidebar badge
```


### `web/scripts/dev.mjs`

L47–L69：

```text
0047: const inherited = process.env.NODE_OPTIONS ?? "";
0048: const nodeOptions = /--max[-_]old[-_]space[-_]size/.test(inherited)
0049:   ? inherited
0050:   : `${inherited} --max-old-space-size=${Math.min(
0051:       HEAP_CEILING_MB,
0052:       Math.floor(memoryBudgetMB() * 0.5),
0053:     )}`.trim();
0054: 
0055: const child = spawn(process.execPath, [NEXT_BIN, "dev", ...process.argv.slice(2)], {
0056:   cwd: WEB_DIR,
0057:   stdio: "inherit",
0058:   env: { ...process.env, NODE_OPTIONS: nodeOptions },
0059: });
0060: 
0061: // Let Next own the terminal: forward the signals it already handles (lock file
0062: // cleanup, worker teardown) instead of dying first and orphaning the worker.
0063: for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
0064:   process.on(signal, () => child.kill(signal));
0065: }
0066: child.on("exit", (code, signal) => {
0067:   if (signal) process.kill(process.pid, signal);
0068:   else process.exit(code ?? 0);
0069: });
```


### `web/proxy.ts`

L13–L24：

```text
0013: // Backend base URL for `/api/*` and `/ws/*` rewrites. The container entrypoint
0014: // exports `DEEPTUTOR_API_BASE_URL` from `data/user/settings/system.json`
0015: // (preferring `next_public_api_base`, then `next_public_api_base_external`,
0016: // then `http://127.0.0.1:${BACKEND_PORT}`). This last-resort default applies
0017: // only when nothing exported the variable at all.
0018: //
0019: // The loopback is spelled as the IPv4 literal, not `localhost`: on a dual-stack
0020: // host that name resolves to ::1 first, while uvicorn binds 0.0.0.0 (IPv4
0021: // only), so every rewrite would fail to connect.
0022: const API_BASE_URL =
0023:   process.env.DEEPTUTOR_API_BASE_URL ?? "http://127.0.0.1:8001";
0024: 
```

L42–L56：

```text
0042: export function proxy(req: NextRequest): NextResponse {
0043:   const { pathname, search } = req.nextUrl;
0044: 
0045:   if (isCodexCallbackPath(pathname)) {
0046:     return NextResponse.rewrite(
0047:       new URL(CODEX_CALLBACK_API_PATH + search, API_BASE_URL),
0048:     );
0049:   }
0050: 
0051:   // 1. Bridge the origin gap: forward backend-relative paths to the API server.
0052:   //    This keeps the URL knowledge in one place (the entrypoint + system.json)
0053:   //    rather than baked into the frontend bundle.
0054:   if (isBackendPath(pathname)) {
0055:     return NextResponse.rewrite(new URL(pathname + search, API_BASE_URL));
0056:   }
```

L74–L85：

```text
0074: export const config = {
0075:   // Run on every request except Next.js internals and the favicon. The /api/*
0076:   // and /ws/* paths are explicitly handled above (rewritten to the backend);
0077:   // large knowledge create/upload requests are handled by dedicated App Router
0078:   // endpoints that stream directly to FastAPI. Excluding them here is crucial:
0079:   // merely entering Proxy makes Next clone and cap the multipart body.
0080:   // the browser's /_next/image optimizer requests are excluded here, while the
0081:   // optimizer's loopback fetch for the source image (e.g. /logo.png) is let
0082:   // through the auth gate by isAuthExempt.
0083:   matcher: [
0084:     "/((?!_next/static|_next/image|favicon.ico|api/v1/knowledge/(?:create|[^/]+/upload)(?:/|$)).*)",
0085:   ],
```


### `web/lib/api.ts`

L1–L38：

```text
0001: // API configuration and utility functions.
0002: //
0003: // The frontend bundle is now URL-agnostic: the browser issues requests against
0004: // the frontend origin (`:3782/api/...` and `:3782/api/.../ws`), and
0005: // `web/proxy.ts` rewrites `/api/*` and `/ws/*` to the configured backend on
0006: // every request. This means there is no build-time or runtime URL substitution
0007: // in the bundle, and no placeholder token to keep alive. `apiUrl` and `wsUrl`
0008: // stay as one-liner pass-throughs so the dozens of existing call sites continue
0009: // to compile and work without modification.
0010: 
0011: /**
0012:  * Construct a full API URL from a path.
0013:  *
0014:  * Pass-through: returns the path unchanged. The actual backend URL is
0015:  * determined at request time by `web/proxy.ts`, which reads
0016:  * `DEEPTUTOR_API_BASE_URL` (exported by the container entrypoint from
0017:  * `data/user/settings/system.json`).
0018:  *
0019:  * @param path - API path (e.g., '/api/v1/knowledge/list')
0020:  * @returns The same path, unchanged
0021:  */
0022: export function apiUrl(path: string): string {
0023:   return path;
0024: }
0025: 
0026: /**
0027:  * Construct a WebSocket URL from a path.
0028:  *
0029:  * Pass-through: returns the path unchanged. `proxy.ts` rewrites `/ws/*` to
0030:  * the configured backend, and the runtime upgrades to `ws://` /
0031:  * `wss://` based on the backend's scheme.
0032:  *
0033:  * @param path - WebSocket path (e.g., '/api/v1/solve')
0034:  * @returns The same path, unchanged
0035:  */
0036: export function wsUrl(path: string): string {
0037:   return path;
0038: }
```

L77–L95：

```text
0077: export async function apiFetch(
0078:   input: RequestInfo | URL,
0079:   init?: RequestInit & { skipAuthRedirect?: boolean },
0080: ): Promise<Response> {
0081:   const { skipAuthRedirect, ...fetchInit } = init ?? {};
0082:   const res = await fetch(input, { credentials: "include", ...fetchInit });
0083: 
0084:   if (
0085:     res.status === 401 &&
0086:     runtimeAuthEnabled &&
0087:     !skipAuthRedirect &&
0088:     typeof window !== "undefined"
0089:   ) {
0090:     const next = encodeURIComponent(window.location.pathname);
0091:     window.location.href = `/login?next=${next}`;
0092:     return new Promise(() => {});
0093:   }
0094: 
0095:   return res;
```


### `web/app/(workspace)/page.tsx`

L1–L30：

```text
0001: "use client";
0002: 
0003: import { useEffect } from "react";
0004: import { useRouter } from "next/navigation";
0005: 
0006: /**
0007:  * Root page now redirects to /home.
0008:  * Handles backward compatibility for /?session=xxx URLs.
0009:  */
0010: export default function HomePage() {
0011:   const router = useRouter();
0012: 
0013:   useEffect(() => {
0014:     const params = new URLSearchParams(window.location.search);
0015:     const sessionId = params.get("session");
0016:     const capability = params.get("capability");
0017:     const tools = params.getAll("tool");
0018: 
0019:     let target = sessionId ? `/home/${sessionId}` : "/home";
0020: 
0021:     const query: string[] = [];
0022:     if (capability) query.push(`capability=${encodeURIComponent(capability)}`);
0023:     tools.forEach((t) => query.push(`tool=${encodeURIComponent(t)}`));
0024:     if (query.length) target += `?${query.join("&")}`;
0025: 
0026:     router.replace(target);
0027:   }, [router]);
0028: 
0029:   return null;
0030: }
```


### `web/app/(workspace)/home/[[...sessionId]]/page.tsx`

L346–L374：

```text
0346: export default function ChatPage() {
0347:   const params = useParams<{ sessionId?: string[] }>();
0348:   const router = useRouter();
0349:   const { t } = useTranslation();
0350:   const sessionIdParam = params.sessionId?.[0] ?? null;
0351:   const { setActiveSessionId, language: appLanguage } = useAppShell();
0352: 
0353:   const {
0354:     state,
0355:     setTools,
0356:     setCapability,
0357:     setKBs,
0358:     setLLMSelection,
0359:     setMasteryPathId,
0360:     setPersonaSelection,
0361:     setSubjectId,
0362:     sendMessage,
0363:     cancelStreamingTurn,
0364:     submitUserReply,
0365:     regenerateLastMessage,
0366:     deleteTurn,
0367:     editMessage,
0368:     switchBranch,
0369:     newSession,
0370:     loadSession,
0371:     showCachedSession,
0372:     renameSessionTitle,
0373:   } = useUnifiedChat();
0374: 
```

L976–L992：

```text
0976:   const startSessionLoad = useCallback(
0977:     (sid: string) => {
0978:       loadAbortRef.current?.abort();
0979:       const ctrl = new AbortController();
0980:       loadAbortRef.current = ctrl;
0981:       const cached = showCachedSession(sid);
0982:       setSessionLoading(!cached);
0983: 
0984:       void loadSession(sid, { signal: ctrl.signal, revalidate: cached })
0985:         .then(() => {
0986:           if (!ctrl.signal.aborted) {
0987:             loadAbortRef.current = null;
0988:             setSessionLoading(false);
0989:             // Settle at the bottom once the transcript is really laid out.
0990:             // The layout-effect pin runs as the messages first render, when
0991:             // lazily-loaded images (ChatMessages `loading="lazy"`) and the
0992:             // `next/dynamic` capability viewers have not contributed their
```

L2085–L2110：

```text
2085:             <ChatComposer
2086:               composerRef={composerRef}
2087:               capMenuRef={capMenuRef}
2088:               capBtnRef={capBtnRef}
2089:               spaceMenuRef={spaceMenuRef}
2090:               spaceBtnRef={spaceBtnRef}
2091:               dragCounter={dragCounter}
2092:               dragging={dragging}
2093:               capMenuOpen={capMenuOpen}
2094:               spaceMenuOpen={spaceMenuOpen}
2095:               hasMessages={hasMessages}
2096:               attachments={attachments}
2097:               attachmentError={attachmentError}
2098:               activeCap={activeCap}
2099:               knowledgeBases={kbOptions}
2100:               llmOptions={llmOptions}
2101:               activeLLMDefault={activeLLMDefault}
2102:               llmSelection={state.llmSelection}
2103:               llmOptionsLoading={llmOptionsLoading}
2104:               llmOptionsError={llmOptionsError}
2105:               subjects={subjectOptions}
2106:               subjectId={subjectId}
2107:               onSubjectChange={(id) => setSubjectId(id)}
2108:               onRefreshLLMOptions={() =>
2109:                 void refreshLLMOptions({ force: true })
2110:               }
```


### `web/components/chat/home/ChatComposer.tsx`

L1060–L1078：

```text
1060:                 {knowledgeBases.length > 0 ? (
1061:                   <KnowledgeSelector
1062:                     knowledgeBases={knowledgeBases}
1063:                     selected={selectedKnowledgeBases}
1064:                     onToggle={onToggleKB}
1065:                   />
1066:                 ) : null}
1067:                 {onSubjectChange ? (
1068:                   <SubjectSelector
1069:                     subjects={subjects ?? []}
1070:                     value={subjectId ?? ""}
1071:                     onChange={onSubjectChange}
1072:                   />
1073:                 ) : null}
1074:                 {onPersonaSelectionChange ? (
1075:                   <PersonaSelector
1076:                     value={personaSelection ?? ""}
1077:                     onChange={onPersonaSelectionChange}
1078:                     open={personaSelectorOpen}
```


### `web/components/chat/home/SubjectSelector.tsx`

L20–L60：

```text
0020: export default function SubjectSelector({
0021:   subjects,
0022:   value,
0023:   onChange,
0024:   placement = "top",
0025: }: {
0026:   subjects: SubjectOption[];
0027:   value: string;
0028:   onChange: (id: string) => void;
0029:   /**
0030:    * Which way the menu opens. The composer toolbar sits at the bottom of the
0031:    * window, so the shared default is "top" (open upward) — the same convention
0032:    * ModelSelector / PersonaSelector / KnowledgeSelector use. Opening downward
0033:    * put this menu past the viewport edge, where it was clipped and the last
0034:    * entries could not be clicked.
0035:    */
0036:   placement?: "top" | "bottom";
0037: }) {
0038:   const { t } = useTranslation();
0039:   const [open, setOpen] = useState(false);
0040:   const ref = useRef<HTMLDivElement>(null);
0041:   const current = subjects.find((s) => s.id === value);
0042: 
0043:   useEffect(() => {
0044:     if (!open) return;
0045:     const close = (e: MouseEvent) => {
0046:       if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
0047:     };
0048:     document.addEventListener("mousedown", close);
0049:     return () => document.removeEventListener("mousedown", close);
0050:   }, [open]);
0051: 
0052:   // With no subjects available the trigger still renders when a value is set:
0053:   // the learner's subject may have just been deleted, and the only way back to a
0054:   // usable session is the explicit "无科目" entry below. Hiding the control made
0055:   // that clear unreachable (the session stayed scoped to a subject that no
0056:   // longer exists).
0057:   if (subjects.length === 0 && !value) return null;
0058: 
0059:   // Same placement + viewport-safe width contract as the other composer
0060:   // selectors, so a long subject name cannot push the menu off-screen either.
```

L64–L103：

```text
0064:   return (
0065:     <div ref={ref} className="relative">
0066:       <button
0067:         onClick={() => setOpen(!open)}
0068:         className={
0069:           "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs " +
0070:           (current
0071:             ? "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400"
0072:             : "border-border/40 text-muted-foreground")
0073:         }
0074:         title={t("Subject context", "科目上下文")}
0075:       >
0076:         <BookOpen size={13} strokeWidth={1.8} />
0077:         <span className="max-w-[9rem] truncate">
0078:           {current ? current.name : t("无科目", "无科目")}
0079:         </span>
0080:         <ChevronDown size={12} />
0081:       </button>
0082:       {open && (
0083:         <div
0084:           className={`absolute left-0 z-50 ${menuPlacementClass} max-h-72 w-[min(240px,calc(100vw-32px))] overflow-y-auto rounded-lg border bg-background p-1 shadow-lg`}
0085:         >
0086:           <button
0087:             onClick={() => {
0088:               onChange("");
0089:               setOpen(false);
0090:             }}
0091:             className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/5"
0092:           >
0093:             <span className="truncate text-muted-foreground">
0094:               {t("无科目", "No subject")}
0095:             </span>
0096:             {!current && <Check size={14} className="text-emerald-600" />}
0097:           </button>
0098:           {subjects.map((s) => (
0099:             <button
0100:               key={s.id}
0101:               onClick={() => {
0102:                 onChange(s.id);
0103:                 setOpen(false);
```


### `web/context/UnifiedChatContext.tsx`

L729–L785：

```text
0729:     case "LOAD_SESSION":
0730:     case "REVALIDATE_SESSION": {
0731:       if (action.type === "REVALIDATE_SESSION") {
0732:         // Second line of defence: ``loadSession`` already drops a revalidate
0733:         // whose session went live, but the check belongs here too so no
0734:         // background snapshot can ever clobber a streaming turn.
0735:         const local = state.sessions[action.key];
0736:         if (!local || local.isStreaming || local.status === "running") {
0737:           return state;
0738:         }
0739:       }
0740:       const existing =
0741:         state.sessions[action.key] ??
0742:         createSessionEntry(action.key, action.sessionId);
0743:       return {
0744:         ...state,
0745:         selectedKey:
0746:           action.type === "LOAD_SESSION" ? action.key : state.selectedKey,
0747:         sessions: {
0748:           ...state.sessions,
0749:           [action.key]: {
0750:             ...existing,
0751:             key: action.key,
0752:             sessionId: action.sessionId,
0753:             sessionTitle:
0754:               action.title !== undefined ? action.title : existing.sessionTitle,
0755:             enabledTools: action.tools ?? existing.enabledTools,
0756:             activeCapability:
0757:               action.capability !== undefined
0758:                 ? action.capability
0759:                 : existing.activeCapability,
0760:             knowledgeBases: action.knowledgeBases ?? existing.knowledgeBases,
0761:             llmSelection:
0762:               action.llmSelection !== undefined
0763:                 ? action.llmSelection
0764:                 : existing.llmSelection,
0765:             masteryPathId:
0766:               action.masteryPathId !== undefined
0767:                 ? action.masteryPathId
0768:                 : existing.masteryPathId,
0769:             personaSelection:
0770:               action.personaSelection !== undefined
0771:                 ? action.personaSelection
0772:                 : existing.personaSelection,
0773:             // The session's own stored scope wins over whatever this tab had:
0774:             // switching sessions must never carry the previous subject along. A
0775:             // background refresh only fills in a scope that is not known yet —
0776:             // it must not wipe a choice the learner made in the composer.
0777:             ...(action.preferences !== undefined
0778:               ? action.type === "LOAD_SESSION"
0779:                 ? applySessionScope(existing, {
0780:                     type: "load",
0781:                     preferences: action.preferences,
0782:                   })
0783:                 : revalidatedScope(existing, action.preferences)
0784:               : {}),
0785:             messages: action.messages,
```

L1531–L1568：

```text
1531:   const loadSession = useCallback(
1532:     async (
1533:       sessionId: string,
1534:       options?: { signal?: AbortSignal; revalidate?: boolean },
1535:     ) => {
1536:       // Entering a session: its stored subject is not known yet, so close the
1537:       // send gate (and drop any scope this tab carried) before the fetch.
1538:       // Every load gets a generation. Comparing session ids alone cannot tell
1539:       // "the same session, loaded twice" apart, and the older response would
1540:       // then win by arriving last.
1541:       const previous = latestLoadKeyRef.current as unknown;
1542:       const previousKey =
1543:         typeof previous === "string"
1544:           ? previous
1545:           : previous && typeof previous === "object"
1546:             ? ((previous as { key?: string }).key ?? null)
1547:             : null;
1548:       const previousGeneration =
1549:         previous && typeof previous === "object"
1550:           ? Number((previous as { generation?: number }).generation || 0)
1551:           : 0;
1552:       const generation =
1553:         (previousKey === sessionId ? previousGeneration : 0) + 1;
1554:       if (!options?.revalidate) {
1555:         latestLoadKeyRef.current = { key: sessionId, generation };
1556:         dispatch({ type: "MARK_SESSION_LOADING", key: sessionId });
1557:       }
1558:       let session;
1559:       try {
1560:         session = await getSession(sessionId, options?.signal);
1561:       } catch (error) {
1562:         // A failed load must not leave the send gate closed forever: the scope
1563:         // falls back to 无科目 for this session and the caller still sees the
1564:         // error (it can retry the navigation).
1565:         if (!options?.revalidate) {
1566:           dispatch({ type: "SESSION_LOAD_FAILED", key: sessionId });
1567:         }
1568:         throw error;
```

L1632–L1642：

```text
1632:         // may have stale persisted preferences, so new turns follow the
1633:         // current response-language setting rather than their original value.
1634:         language: readStoredResponseLanguage(),
1635:         // Raw preferences: the reducer derives the subject scope through the
1636:         // shared three-state helper, so entering a session can never carry the
1637:         // previous session's subject along.
1638:         preferences: session.preferences ?? {},
1639:         selectedBranches: normalizeSelectedBranches(
1640:           session.preferences?.selected_branches,
1641:         ),
1642:       });
```

L2118–L2120：

```text
2118:   const setSubjectId = useCallback((value: SubjectScope) => {
2119:     dispatch({ type: "SET_SUBJECT_ID", value: normalizeSubject(value) });
2120:   }, []);
```


### `web/lib/subject-scope.ts`

L62–L107：

```text
0062: export function normalizeSubject(value: unknown): SubjectScope {
0063:   if (typeof value !== "string") return null;
0064:   const trimmed = value.trim();
0065:   return trimmed ? trimmed : null;
0066: }
0067: 
0068: /** The session scope implied by a session's stored preferences. */
0069: export function scopedFromPreferences(preferences: unknown): SubjectSessionScope {
0070:   const record =
0071:     preferences && typeof preferences === "object"
0072:       ? (preferences as Record<string, unknown>)
0073:       : {};
0074:   // A missing key means "no subject stored" — which for a session is the same
0075:   // observable value as an explicit clear: 无科目. It is *not* "keep whatever
0076:   // this tab had", because the session is the authority.
0077:   return {
0078:     subjectId: normalizeSubject(record.subject_id),
0079:     subjectHydrated: true,
0080:   };
0081: }
0082: 
0083: /** Apply the learner's explicit choice to a hydrated scope. */
0084: export function selectSubject(
0085:   scope: SubjectSessionScope,
0086:   value: SubjectScope,
0087: ): SubjectSessionScope {
0088:   return {
0089:     subjectId: normalizeSubject(value),
0090:     subjectHydrated: scope.subjectHydrated,
0091:   };
0092: }
0093: 
0094: /** May this session send a turn right now? */
0095: export function subjectSendable(scope: SubjectSessionScope | undefined): boolean {
0096:   return Boolean(scope?.subjectHydrated);
0097: }
0098: 
0099: /**
0100:  * The `subject_id` to put on the wire. Always returns a value — including
0101:  * `null` — because the key is what tells the backend "clear it"; the caller
0102:  * must keep the key present.
0103:  */
0104: export function subjectForRequest(scope: SubjectSessionScope): string | null {
0105:   return normalizeSubject(scope.subjectId);
0106: }
0107: 
```

L208–L250：

```text
0208: export function applySessionScope(
0209:   scope: SubjectSessionScope,
0210:   event: SessionScopeEvent,
0211: ): SubjectSessionScope {
0212:   switch (event.type) {
0213:     case "loading":
0214:       return pendingSessionScope();
0215:     case "load":
0216:       return scopedFromPreferences(event.preferences);
0217:     case "select":
0218:       return selectSubject(scope, event.value);
0219:   }
0220: }
0221: 
0222: /**
0223:  * Background refresh: fill in a scope that is not known yet, never overwrite a
0224:  * known one.
0225:  *
0226:  * A revalidate runs on a session that is already on screen, where the learner
0227:  * may have just picked a subject in the composer and not sent it yet. Replacing
0228:  * that choice with the (older) stored value would silently change the scope of
0229:  * the next turn. A superseded initial load is the other case: its entry is still
0230:  * unhydrated, and filling it in is what lets the send gate ever open again.
0231:  */
0232: export function revalidatedScope(
0233:   scope: SubjectSessionScope,
0234:   preferences: unknown,
0235: ): SubjectSessionScope {
0236:   return scope.subjectHydrated
0237:     ? scope
0238:     : applySessionScope(scope, { type: "load", preferences });
0239: }
0240: 
0241: /**
0242:  * One "this attached library is not usable this turn" notice.
0243:  *
0244:  * The server owns the text (the fixed C02 projection) and the identity; the
0245:  * client only bounds and validates it before showing it.
0246:  */
0247: export interface SubjectKbWarning {
0248:   kbRef: string;
0249:   status: string;
0250:   code: string;
```


### `web/app/(workspace)/subjects/page.tsx`

L35–L82：

```text
0035: export default function SubjectsPage() {
0036:   const { t } = useTranslation();
0037:   const [subjects, setSubjects] = useState<Subject[]>([]);
0038:   const [knowledge, setKnowledge] = useState<Record<string, KnowledgeRecord[]>>({});
0039:   const [name, setName] = useState("");
0040:   const [term, setTerm] = useState("");
0041:   const [uploading, setUploading] = useState<Record<string, boolean>>({});
0042:   const [busy, setBusy] = useState(false);
0043:   const [msg, setMsg] = useState("");
0044:   const mounted = useRef(true);
0045:   const loadGeneration = useRef(0);
0046:   const isCurrent = () => mounted.current;
0047: 
0048:   const load = useCallback(async (notify: boolean) => {
0049:     const generation = ++loadGeneration.current;
0050:     const view = await loadSubjectsView({
0051:       request: apiFetch,
0052:       isCurrent: () => mounted.current && generation === loadGeneration.current,
0053:       notify,
0054:       onError: setMsg,
0055:       onLoaded: (loaded) => {
0056:         const rows = loaded.subjects as unknown as Subject[];
0057:         setSubjects(rows);
0058:         setKnowledge((previous) => {
0059:           const next: Record<string, KnowledgeRecord[]> = {};
0060:           for (const subject of rows) {
0061:             next[subject.id] =
0062:               (loaded.knowledge[subject.id] as unknown as
0063:                 | KnowledgeRecord[]
0064:                 | undefined) ?? previous[subject.id] ?? [];
0065:           }
0066:           return next;
0067:         });
0068:       },
0069:     });
0070:     return view?.knowledge ?? {};
0071:   }, []);
0072: 
0073:   useEffect(() => {
0074:     mounted.current = true;
0075:     void load(true);
0076:     const timer = setInterval(() => void load(false), 5000);
0077:     return () => {
0078:       mounted.current = false;
0079:       loadGeneration.current += 1;
0080:       clearInterval(timer);
0081:     };
0082:   }, [load]);
```

L84–L103：

```text
0084:   async function createSubject(e: React.FormEvent) {
0085:     e.preventDefault();
0086:     if (!name.trim()) return;
0087:     await createSubjectAction({
0088:       request: apiFetch,
0089:       isCurrent,
0090:       name,
0091:       term,
0092:       setBusy,
0093:       onError: setMsg,
0094:       onSuccess: () => {
0095:         setMsg("创建成功");
0096:         void load(false);
0097:       },
0098:       clearInputs: () => {
0099:         setName("");
0100:         setTerm("");
0101:       },
0102:     });
0103:   }
```

L140–L167：

```text
0140:       <div className="mx-auto max-w-5xl px-6 py-10">
0141:       <h1 className="text-2xl font-semibold">科目（Subjects）</h1>
0142:       <p className="mt-1 text-sm opacity-70">
0143:         每科独立管理对话、知识库与错题集；模型配置全局共享。
0144:       </p>
0145: 
0146:       <form onSubmit={createSubject} className="mt-6 flex flex-wrap gap-3 rounded-xl border p-4">
0147:         <input
0148:           className="rounded-md border bg-transparent px-3 py-1.5 text-sm outline-none"
0149:           placeholder="科目名称（如：常微分方程）"
0150:           value={name}
0151:           onChange={(e) => setName(e.target.value)}
0152:         />
0153:         <input
0154:           className="rounded-md border bg-transparent px-3 py-1.5 text-sm outline-none"
0155:           placeholder="学期（可选，如 2026秋）"
0156:           value={term}
0157:           onChange={(e) => setTerm(e.target.value)}
0158:         />
0159:         <button
0160:           className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
0161:           type="submit"
0162:           disabled={busy}
0163:         >
0164:           {busy ? "创建中…" : "新建科目"}
0165:         </button>
0166:         {msg && <span className="self-center text-sm text-amber-600">{msg}</span>}
0167:       </form>
```

L169–L205：

```text
0169:       <div className="mt-6 space-y-4">
0170:         {subjects.map((s) => (
0171:           <div key={s.id} className="rounded-xl border p-4">
0172:             <div className="flex items-center justify-between">
0173:               <div>
0174:                 <a href={`/subjects/${s.id}`} className="font-semibold text-blue-600 hover:underline">
0175:                   {s.name}
0176:                 </a>
0177:                 {s.term && <span className="ml-2 text-sm opacity-60">{s.term}</span>}
0178:                 <span className="ml-2 text-xs opacity-40">id: {s.id}</span>
0179:               </div>
0180:               <div className="flex gap-2">
0181:                 <input
0182:                   type="file"
0183:                   multiple
0184:                   disabled={busy || uploading[s.id]}
0185:                   accept=".pdf,.epub,.ppt,.pptx,.png,.jpg,.jpeg,.mp3,.m4a,.docx,.md,.txt"
0186:                   className="hidden"
0187:                   id={`file-${s.id}`}
0188:                   onChange={(e) => uploadFiles(s.id, e.target.files, "auto")}
0189:                 />
0190:                 <label
0191:                   htmlFor={`file-${s.id}`}
0192:                   className={
0193:                     uploading[s.id] || busy
0194:                       ? "cursor-not-allowed rounded-md bg-emerald-600/60 px-3 py-1 text-sm text-white"
0195:                       : "cursor-pointer rounded-md bg-emerald-600 px-3 py-1 text-sm text-white"
0196:                   }
0197:                 >
0198:                   {uploading[s.id] ? "上传中…" : "上传材料"}
0199:                 </label>
0200:                 <button
0201:                   className="rounded-md bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
0202:                   onClick={() => deleteSubject(s.id)}
0203:                   disabled={busy || uploading[s.id]}
0204:                 >
0205:                   {busy ? "处理中…" : "删除"}
```


### `web/app/(workspace)/subjects/[id]/page.tsx`

L97–L126：

```text
0097:   const refresh = useCallback(
0098:     async (notify = false) => {
0099:       if (!isCurrent()) return;
0100:       const generation = ++loadGeneration.current;
0101:       await loadSubjectDetail({
0102:         request: apiFetch,
0103:         isCurrent: () => isCurrent() && generation === loadGeneration.current,
0104:         subjectId,
0105:         notify,
0106:         onLoaded: (view) => {
0107:           if (view.loaded.knowledge) setKnowledge(view.knowledge as unknown as KnowledgeRecord[]);
0108:           if (view.loaded.wrongs) setWrongs(view.wrongs as unknown as WrongEntry[]);
0109:           if (view.loaded.points) setPoints(view.points as unknown as ExamPoint[]);
0110:           if (view.loaded.profile && view.profile) {
0111:             setProfile({
0112:               explanation_style:
0113:                 typeof view.profile.explanation_style === "string"
0114:                   ? view.profile.explanation_style
0115:                   : "balanced",
0116:               goals:
0117:                 typeof view.profile.goals === "string" ? view.profile.goals : "",
0118:             });
0119:           }
0120:         },
0121:         onError: (message) => {
0122:           if (isCurrent()) setMsg(message);
0123:         },
0124:       });
0125:     },
0126:     [subjectId, isCurrent],
```

L215–L225：

```text
0215:   async function exportSubject() {
0216:     await exportSubjectAction({
0217:       request: apiFetch,
0218:       isCurrent,
0219:       subjectId,
0220:       setBusy,
0221:       onError: setMsg,
0222:       onSuccess: () => setMsg("导出已开始下载。"),
0223:       openDownload: (url) => window.open(url, "_blank", "noopener,noreferrer"),
0224:     });
0225:   }
```

L239–L257：

```text
0239:   return (
0240:     <div className="h-full overflow-y-auto [scrollbar-gutter:stable]">
0241:       <div className="mx-auto max-w-5xl px-6 py-10">
0242:       <div className="flex items-center gap-3">
0243:         <Link href="/subjects" className="text-sm text-blue-600 hover:underline">
0244:           ← 科目列表
0245:         </Link>
0246:         <h1 className="text-2xl font-semibold">{subjectId}</h1>
0247:         <div className="ml-auto text-right">
0248:           <button
0249:             onClick={() => void exportSubject()}
0250:             disabled={busy}
0251:             className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
0252:           >
0253:             {busy ? "处理中…" : "导出科目资料"}
0254:           </button>
0255:           <div className="mt-1 max-w-[18rem] text-[11px] opacity-50">
0256:             {EXPORT_SCOPE_NOTE}
0257:           </div>
```

L441–L462：

```text
0441:   async function uploadAudio(files: FileList | null) {
0442:     if (!files || files.length === 0) return;
0443:     setAsrMsg("正在上传录音并转写（ASR）…");
0444:     setAsrError(false);
0445:     await uploadAudioAction({
0446:       request: apiFetch,
0447:       isCurrent,
0448:       subjectId,
0449:       files: Array.from(files),
0450:       setBusy,
0451:       onError: (message) => {
0452:         setAsrError(true);
0453:         setAsrMsg(message);
0454:       },
0455:       onSuccess: (outcome) => {
0456:         setAsrError(false);
0457:         if (outcome.text) {
0458:           setTranscript((prev) => (prev ? prev + "\n\n" + outcome.text : outcome.text));
0459:         }
0460:         setAsrMsg(outcome.message);
0461:       },
0462:     });
```

L482–L503：

```text
0482:   return (
0483:     <div className="rounded-xl border p-4">
0484:       <div className="text-sm font-medium">课堂考点检测</div>
0485:       <div className="mt-2 flex flex-wrap items-center gap-3 text-xs opacity-70">
0486:         <label className={busy ? "cursor-not-allowed rounded-md bg-blue-600/60 px-3 py-1.5 text-xs text-white" : "cursor-pointer rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white"}>
0487:           {busy ? "处理中…" : "上传录音（mp3/m4a/wav）"}
0488:           <input type="file" multiple accept=".mp3,.m4a,.wav,.flac,.ogg,.aac" className="hidden" disabled={busy} onChange={(e) => void uploadAudio(e.target.files)} />
0489:         </label>
0490:         <span>或直接粘贴讲课转写文字：</span>
0491:       </div>
0492:       {asrMsg && <div className={asrError ? "mt-1 text-xs text-red-600" : "mt-1 text-xs text-emerald-600"}>{asrMsg}</div>}
0493:       <textarea
0494:         value={transcript}
0495:         onChange={(e) => setTranscript(e.target.value)}
0496:         rows={4}
0497:         placeholder="粘贴教师讲课转写文本（模拟 ASR 输出）…"
0498:         className="mt-2 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
0499:       />
0500:       <button onClick={run} disabled={busy} className="mt-2 rounded-md bg-amber-600 px-4 py-1.5 text-sm text-white disabled:opacity-50">
0501:         {busy ? "检测中…" : "检测考点"}
0502:       </button>
0503:       {result && <div className="mt-2 text-sm text-amber-600">{result}</div>}
```


### `web/lib/subject-results.ts`

L635–L669：

```text
0635: export function outputDownloadUrl(payload: JsonObject): string | null {
0636:   const url = stringField(payload, "url");
0637:   if (!url) return null;
0638:   if (!url.startsWith("/api/outputs/") || url.startsWith("//")) return null;
0639:   if (url.includes("..") || url.includes("\\") || url.includes("\n")) return null;
0640:   return url;
0641: }
0642: 
0643: export async function exportSubjectAction(options: {
0644:   request: SubjectRequest;
0645:   subjectId: string;
0646:   setBusy?: (busy: boolean) => void;
0647:   isCurrent?: () => boolean;
0648:   onError: (message: string) => void;
0649:   onSuccess: (url: string) => void;
0650:   openDownload: (url: string) => void;
0651: }): Promise<boolean> {
0652:   const result = await runSubjectAction(
0653:     options,
0654:     async () => {
0655:       const payload = await requestSubjectJson(
0656:         options.request,
0657:         `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/export`,
0658:         { method: "GET" },
0659:       );
0660:       const url = outputDownloadUrl(payload);
0661:       if (!url) throw new SubjectActionError(SAFE_BAD_EXPORT_URL, "protocol");
0662:       return url;
0663:     },
0664:   );
0665:   if (!result.ok || options.isCurrent?.() === false) return false;
0666:   options.onSuccess(result.value);
0667:   options.openDownload(result.value);
0668:   return true;
0669: }
```

L713–L751：

```text
0713: export async function uploadAudioAction(options: {
0714:   request: SubjectRequest;
0715:   subjectId: string;
0716:   files: File[];
0717:   setBusy?: (busy: boolean) => void;
0718:   isCurrent?: () => boolean;
0719:   onError: (message: string) => void;
0720:   onSuccess: (outcome: AudioUploadOutcome) => void;
0721: }): Promise<boolean> {
0722:   if (options.files.length === 0) return false;
0723:   const body = buildFormData({ type: "lecture" });
0724:   for (const file of options.files) body.append("files", file);
0725: 
0726:   const result = await runSubjectAction(
0727:     options,
0728:     async () => {
0729:       const payload = await requestSubjectJson(
0730:         options.request,
0731:         `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/knowledge/upload`,
0732:         { method: "POST", body },
0733:       );
0734:       const operation = stringField(payload, "operation");
0735:       if (operation !== "transcribe") {
0736:         throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
0737:       }
0738:       const transcripts = transcriptsFrom(payload);
0739:       const text = transcripts
0740:         .map((item) => stringField(item, "text") ?? "")
0741:         .filter((value) => value.length > 0)
0742:         .join("\n\n");
0743:       const message = text
0744:         ? `转写完成（${transcripts.length} 个文件）；转写文本已保存到该科“课堂录音”材料（materials/lecture），并填入下方检测框，不会自动建立索引。`
0745:         : "转写完成，但没有返回文本内容，请检查录音。";
0746:       return { message, text, count: transcripts.length };
0747:     },
0748:   );
0749:   if (!result.ok || options.isCurrent?.() === false) return false;
0750:   options.onSuccess(result.value);
0751:   return true;
```


### `web/app/(utility)/knowledge/page.tsx`

L1–L19：

```text
0001: "use client";
0002: 
0003: import { Suspense } from "react";
0004: import { Loader2 } from "lucide-react";
0005: import KnowledgePage from "@/components/knowledge/KnowledgePage";
0006: 
0007: export default function Page() {
0008:   return (
0009:     <Suspense
0010:       fallback={
0011:         <div className="flex min-h-[50vh] items-center justify-center text-[13px] text-[var(--muted-foreground)]">
0012:           <Loader2 className="h-5 w-5 animate-spin" />
0013:         </div>
0014:       }
0015:     >
0016:       <KnowledgePage />
0017:     </Suspense>
0018:   );
0019: }
```


### `web/components/knowledge/KnowledgePage.tsx`

L15–L42：

```text
0015: export default function KnowledgePage() {
0016:   const { t } = useTranslation();
0017:   const router = useRouter();
0018:   const searchParams = useSearchParams();
0019:   const initialKb = searchParams.get("kb");
0020:   const initialEngine = searchParams.get("engine");
0021: 
0022:   const {
0023:     kbs: allKbs,
0024:     providers,
0025:     uploadPolicy,
0026:     loading,
0027:     error,
0028:     setError,
0029:     tasksByKb,
0030:     historyByKb,
0031:     clearHistory,
0032:     refresh,
0033:     createKb,
0034:     uploadFiles,
0035:     setDefault,
0036:     reindex,
0037:     retry,
0038:     deleteKb,
0039:     connectLinkedFolder,
0040:     connectLightRagServer,
0041:     connectIma,
0042:   } = useKnowledgeBases();
```

L58–L68：

```text
0058:   const [createOpen, setCreateOpen] = useState(false);
0059:   const [pipelineOpen, setPipelineOpen] = useState(false);
0060: 
0061:   const openCreate = useCallback(() => {
0062:     setCreateOpen(true);
0063:   }, []);
0064:   // Lands on the Overview console unless deep-linked to a KB or an engine.
0065:   const [view, setView] = useState<"home" | "kb" | "engine">(
0066:     initialEngine ? "engine" : initialKb ? "kb" : "home",
0067:   );
0068: 
```

L241–L294：

```text
0241:             <KnowledgeHome
0242:               kbs={kbs}
0243:               providers={providers}
0244:               onOpenKb={openKb}
0245:               onOpenEngine={openEngine}
0246:               onCreate={openCreate}
0247:             />
0248:           ) : view === "engine" && selectedProvider ? (
0249:             <EngineDetail
0250:               provider={selectedProvider}
0251:               kbs={kbs}
0252:               onBack={() => setView("home")}
0253:               onOpenKb={openKb}
0254:               onSelectMode={handleSelectMode}
0255:               onChanged={() => void refresh({ force: true })}
0256:               onError={(message) => setError(message)}
0257:             />
0258:           ) : view === "engine" ? (
0259:             // Selected engine vanished (e.g. provider list changed); bounce home.
0260:             <KnowledgeHome
0261:               kbs={kbs}
0262:               providers={providers}
0263:               onOpenKb={openKb}
0264:               onOpenEngine={openEngine}
0265:               onCreate={openCreate}
0266:             />
0267:           ) : (
0268:             <KnowledgeBaseDetail
0269:               kb={selectedKb}
0270:               uploadPolicy={uploadPolicy}
0271:               task={selectedKb ? tasksByKb[selectedKb.name] : undefined}
0272:               history={selectedKb ? (historyByKb[selectedKb.name] ?? []) : []}
0273:               onCreate={openCreate}
0274:               onUpload={handleUpload}
0275:               onReindex={handleReindex}
0276:               onRetry={handleRetry}
0277:               onSetDefault={handleSetDefault}
0278:               onDelete={handleDelete}
0279:               onClearHistory={clearHistory}
0280:               onBack={() => setView("home")}
0281:             />
0282:           )}
0283:         </div>
0284:       )}
0285: 
0286:       <CreateKbModal
0287:         isOpen={createOpen}
0288:         onClose={() => setCreateOpen(false)}
0289:         providers={providers}
0290:         uploadPolicy={uploadPolicy}
0291:         onCreate={handleCreate}
0292:         onConnectLinkedFolder={connectLinkedFolder}
0293:         onConnectLightRagServer={connectLightRagServer}
0294:         onConnectIma={connectIma}
```


### `web/components/knowledge/KnowledgeHome.tsx`

L114–L135：

```text
0114:   return (
0115:     <div className="flex-1 overflow-y-auto bg-[var(--background)]">
0116:       <div className="mx-auto max-w-4xl px-6 py-8">
0117:         {/* Header */}
0118:         <div className="flex items-start justify-between gap-4">
0119:           <div>
0120:             <h1 className="text-[19px] font-semibold tracking-tight text-[var(--foreground)]">
0121:               {t("Knowledge Center")}
0122:             </h1>
0123:             <p className="mt-1 text-[12.5px] text-[var(--muted-foreground)]">
0124:               {t("Manage your knowledge bases and retrieval engines.")}
0125:             </p>
0126:           </div>
0127:           <button
0128:             type="button"
0129:             onClick={onCreate}
0130:             className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3.5 py-2 text-[12.5px] font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90"
0131:           >
0132:             <Plus size={14} />
0133:             {t("New knowledge base")}
0134:           </button>
0135:         </div>
```

L212–L231：

```text
0212:           {kbs.length === 0 ? (
0213:             <div className="rounded-2xl border border-dashed border-[var(--border)] px-4 py-12 text-center">
0214:               <Database className="mx-auto mb-2 h-6 w-6 text-[var(--muted-foreground)]" />
0215:               <div className="text-[13px] font-medium text-[var(--foreground)]">
0216:                 {t("No knowledge bases yet")}
0217:               </div>
0218:               <p className="mx-auto mt-1 max-w-sm text-[12px] leading-relaxed text-[var(--muted-foreground)]">
0219:                 {t(
0220:                   "Create one to upload documents and retrieve grounded context in chat.",
0221:                 )}
0222:               </p>
0223:               <button
0224:                 type="button"
0225:                 onClick={onCreate}
0226:                 className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3.5 py-2 text-[12.5px] font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90"
0227:               >
0228:                 <Plus size={14} />
0229:                 {t("New knowledge base")}
0230:               </button>
0231:             </div>
```


### `web/components/knowledge/CreateKbModal.tsx`

L91–L123：

```text
0091: export default function CreateKbModal({
0092:   isOpen,
0093:   onClose,
0094:   providers,
0095:   uploadPolicy,
0096:   onCreate,
0097:   onConnectLinkedFolder,
0098:   onConnectLightRagServer,
0099:   onConnectIma,
0100:   onConfigureProvider,
0101:   initialMode = "new",
0102:   initialSource,
0103: }: CreateKbModalProps) {
0104:   const { t } = useTranslation();
0105:   const [mode, setMode] = useState<Mode>(initialMode);
0106:   const [name, setName] = useState("");
0107:   const [provider, setProvider] = useState("llamaindex");
0108:   const [files, setFiles] = useState<File[]>([]);
0109:   // Link mode: the source is a linkable engine id.
0110:   const [linkSource, setLinkSource] = useState(initialSource || "");
0111:   const [folderPath, setFolderPath] = useState("");
0112:   const [probe, setProbe] = useState<LinkedFolderProbe | null>(null);
0113:   const [probing, setProbing] = useState(false);
0114:   // LightRAG Server engine (new mode): a connection instead of an upload.
0115:   const [serverUrl, setServerUrl] = useState("");
0116:   const [apiKey, setApiKey] = useState("");
0117:   const [serverMode, setServerMode] = useState("");
0118:   const [serverProbe, setServerProbe] = useState<LightRagServerProbe | null>(
0119:     null,
0120:   );
0121:   const [serverProbing, setServerProbing] = useState(false);
0122:   const [submitting, setSubmitting] = useState(false);
0123:   const [error, setError] = useState<string | null>(null);
```

L149–L175：

```text
0149:   // Reset the form only on the closed → open transition. While the modal is
0150:   // open, background indexing polls replace `providers` (and friends) every
0151:   // few seconds, and a data refresh must never wipe user input (#691).
0152:   const wasOpenRef = useRef(false);
0153:   useEffect(() => {
0154:     const justOpened = isOpen && !wasOpenRef.current;
0155:     wasOpenRef.current = isOpen;
0156:     if (!justOpened) return;
0157:     setMode(initialMode);
0158:     setName("");
0159:     setFiles([]);
0160:     setError(null);
0161:     const initialProvider = createProviders(providers).find(
0162:       (item) => item.id === initialSource,
0163:     )?.id;
0164:     setProvider(
0165:       initialProvider || createProviders(providers)[0]?.id || "llamaindex",
0166:     );
0167:     setLinkSource(initialSource || firstLinkable || "");
0168:     setFolderPath("");
0169:     setProbe(null);
0170:     setProbing(false);
0171:     setServerUrl("");
0172:     setApiKey("");
0173:     setServerMode("");
0174:     setServerProbe(null);
0175:     setServerProbing(false);
```


### `web/lib/knowledge-api.ts`

L614–L660：

```text
0614: export async function createKnowledgeBase(payload: {
0615:   name: string;
0616:   provider: string;
0617:   files: File[];
0618: }): Promise<KnowledgeTaskResponse> {
0619:   const form = new FormData();
0620:   form.append("name", payload.name);
0621:   form.append("rag_provider", payload.provider);
0622:   appendFilesWithPaths(form, payload.files);
0623: 
0624:   const res = await apiFetch(apiUrl("/api/v1/knowledge/create"), {
0625:     method: "POST",
0626:     body: form,
0627:   });
0628:   if (!res.ok) {
0629:     throw new Error(
0630:       await readErrorDetail(res, "Failed to create knowledge base"),
0631:     );
0632:   }
0633:   invalidateKnowledgeCaches();
0634:   return (await res.json()) as KnowledgeTaskResponse;
0635: }
0636: 
0637: export async function connectObsidianVault(payload: {
0638:   name: string;
0639:   vaultPath: string;
0640: }): Promise<{ status: string; name: string; vault_path: string }> {
0641:   const res = await apiFetch(apiUrl("/api/v1/knowledge/connect-obsidian"), {
0642:     method: "POST",
0643:     headers: { "Content-Type": "application/json" },
0644:     body: JSON.stringify({ name: payload.name, vault_path: payload.vaultPath }),
0645:   });
0646:   if (!res.ok) {
0647:     throw new Error(
0648:       await readErrorDetail(res, "Failed to connect Obsidian vault"),
0649:     );
0650:   }
0651:   invalidateKnowledgeCaches();
0652:   return (await res.json()) as {
0653:     status: string;
0654:     name: string;
0655:     vault_path: string;
0656:   };
0657: }
0658: 
0659: export interface LinkedFolderProbe {
0660:   /** Whether the folder holds a ready index for the chosen engine. */
```


### `web/tests/e2e/compliance-and-ux.audit.ts`

L1–L37：

```text
0001: import { test, expect } from "@playwright/test";
0002: 
0003: // Minimal compliance and UX checks without external deps (axe-core)
0004: // Focus on semantic landmarks, headings, alt text, link names, and basic error messaging.
0005: 
0006: const BASE_URL =
0007:   process.env.WEB_BASE_URL ||
0008:   process.env.NEXT_PUBLIC_API_BASE ||
0009:   "http://localhost:3000";
0010: 
0011: async function expectAnyVisible(
0012:   locators: import("@playwright/test").Locator[],
0013:   message: string,
0014: ) {
0015:   for (const loc of locators) {
0016:     try {
0017:       if (await loc.first().isVisible()) return;
0018:     } catch {}
0019:   }
0020:   expect(false, message).toBe(true);
0021: }
0022: 
0023: test.describe("Compliance :: Accessibility & Semantics", () => {
0024:   test("home page exposes main landmark and H1", async ({ page }) => {
0025:     await page.goto(`${BASE_URL}/`);
0026:     await page.waitForSelector("main", { timeout: 5000 });
0027:     const main = page.locator("main");
0028:     await expect(main, "Missing <main> landmark").toBeVisible();
0029: 
0030:     const h1 = page.locator("h1").first();
0031:     await expect(h1, "Missing top-level <h1>").toBeVisible();
0032:   });
0033: 
0034:   test("images provide alt text", async ({ page }) => {
0035:     await page.goto(`${BASE_URL}/`);
0036:     const missingAltCount = await page.$$eval(
0037:       "img",
```


### `web/tests/phase1-25.test.ts`

L51–L105：

```text
0051: test("a new session starts with no subject and is usable immediately", () => {
0052:   const scope = newSessionScope();
0053:   assert.equal(scope.subjectId, null);
0054:   assert.equal(subjectSendable(scope), true);
0055:   assert.equal(subjectForRequest(scope), null);
0056: });
0057: 
0058: test("entering a session drops the previous scope and closes the send gate", () => {
0059:   const previous = applySessionScope(newSessionScope(), {
0060:     type: "select",
0061:     value: "科目上一轮",
0062:   });
0063:   const entering = applySessionScope(previous, { type: "loading" });
0064: 
0065:   assert.equal(entering.subjectId, null, "旧 scope 被带进了新会话");
0066:   assert.equal(subjectSendable(entering), false, "hydration 完成前不应允许发送");
0067: });
0068: 
0069: test("the session's stored subject is restored on load — and absence means none", () => {
0070:   assert.equal(loaded({ subject_id: SUBJECT_A }).subjectId, SUBJECT_A);
0071:   assert.equal(subjectSendable(loaded({ subject_id: SUBJECT_A })), true);
0072: 
0073:   // 存储里没有这个键 = 这个会话没有科目，不是"沿用上一个会话"。
0074:   const never = loaded({ tools: ["rag"], capability: "chat" });
0075:   assert.equal(never.subjectId, null);
0076:   assert.equal(never.subjectHydrated, true);
0077: 
0078:   // 历史遗留的 "" 视为清空。
0079:   assert.equal(loaded({ subject_id: "" }).subjectId, null);
0080:   assert.equal(loaded({ subject_id: "   " }).subjectId, null);
0081:   // 非字符串不是合法 scope，按"无科目"处理而不是抛错。
0082:   assert.equal(loaded({ subject_id: 42 }).subjectId, null);
0083: });
0084: 
0085: test("clearing keeps an explicit null (never a dropped key)", () => {
0086:   const scope = applySessionScope(loaded({ subject_id: SUBJECT_A }), {
0087:     type: "select",
0088:     value: "",
0089:   });
0090:   assert.equal(scope.subjectId, null);
0091:   assert.equal(subjectSendable(scope), true, "清空不改变 hydration");
0092: 
0093:   const config = mergeSubjectIntoConfig({ depth: "standard" }, subjectForRequest(scope));
0094:   assert.equal("subject_id" in config, true, "清空必须保留属性存在性");
0095:   assert.equal(config.subject_id, null, "清空必须发明确 null");
0096:   assert.deepEqual(subjectFromConfig(config), { hasScope: true, value: null });
0097: });
0098: 
0099: test("choosing a subject keeps the gate closed until hydration finishes", () => {
0100:   const entering = applySessionScope(newSessionScope(), { type: "loading" });
0101:   const picked = applySessionScope(entering, { type: "select", value: SUBJECT_A });
0102:   assert.equal(picked.subjectId, SUBJECT_A);
0103:   assert.equal(subjectSendable(picked), false, "未完成恢复就允许发送了");
0104: });
0105: 
```

L142–L155：

```text
0142: test("a background refresh never overwrites a choice made in the composer", () => {
0143:   const picked = applySessionScope(loaded({ subject_id: SUBJECT_A }), {
0144:     type: "select",
0145:     value: SUBJECT_B,
0146:   });
0147:   const refreshed = revalidatedScope(picked, { subject_id: SUBJECT_A });
0148:   assert.equal(refreshed.subjectId, SUBJECT_B, "后台刷新把用户刚选的科目改回去了");
0149: 
0150:   // 但一个还没 hydrate 的 entry 必须被填充，否则发送门永远不会打开。
0151:   const unhydrated = applySessionScope(newSessionScope(), { type: "loading" });
0152:   const filled = revalidatedScope(unhydrated, { subject_id: SUBJECT_A });
0153:   assert.equal(filled.subjectId, SUBJECT_A);
0154:   assert.equal(subjectSendable(filled), true);
0155: });
```


### `web/tests/phase1-43.test.ts`

L74–L103：

```text
0074: test("the link dialog renders no Obsidian option or vault copy", () => {
0075:   const html = renderModal("link");
0076:   assert.ok(!/obsidian/i.test(html), html);
0077:   assert.ok(!/vault/i.test(html), html);
0078:   assert.ok(!html.includes("Connect vault"), html);
0079:   assert.ok(!html.includes("Vault path"), html);
0080: });
0081: 
0082: test("the still-supported link sources render and keep their affordances", () => {
0083:   const html = renderModal("link");
0084:   assert.match(html, /LlamaIndex/);
0085:   assert.match(html, /PageIndex/);
0086:   assert.match(html, /LightRAG Server/);
0087:   assert.match(html, /IMA/);
0088:   assert.match(html, /Read only/);
0089:   assert.match(html, /Folder path/);
0090:   assert.match(html, /Check folder/);
0091:   assert.match(html, /Source/);
0092: });
0093: 
0094: test("normal document upload still renders in create mode", () => {
0095:   const html = renderModal("new");
0096:   assert.match(html, /Index engine/);
0097:   assert.match(html, /Choose files/);
0098:   assert.match(html, /LlamaIndex/);
0099:   assert.match(html, /PageIndex/);
0100:   assert.ok(!/obsidian/i.test(html), html);
0101: });
0102: 
0103: test("new-mode provider choices keep filtering IMA as before", () => {
```

L124–L155：

```text
0124: test("the home has no Obsidian create card while historical KBs stay readable", () => {
0125:   const html = renderToStaticMarkup(
0126:     createElement(KnowledgeHome, {
0127:       kbs: [
0128:         {
0129:           name: "分析笔记",
0130:           is_default: true,
0131:           metadata: { rag_provider: "llamaindex", type: "obsidian" },
0132:         },
0133:       ],
0134:       providers: PROVIDERS,
0135:       onOpenKb: NOOP,
0136:       onOpenEngine: NOOP,
0137:       onCreate: NOOP,
0138:     }),
0139:   );
0140:   assert.ok(!/connect vault/i.test(html), html);
0141:   assert.ok(!/connect your obsidian vault/i.test(html), html);
0142:   assert.ok(!/\{\{count\}\} connected/i.test(html), html);
0143:   assert.match(html, /LlamaIndex/);
0144:   assert.match(html, /PageIndex/);
0145:   // A historical obsidian KB still appears in the ordinary KB list (and keeps
0146:   // its historical type label); only the clickable create entry is gone.
0147:   assert.match(html, /分析笔记/);
0148:   assert.match(html, /Obsidian/);
0149: });
0150: 
0151: test("the historical 501 Obsidian endpoint and its client stay available read-only", () => {
0152:   const backend = readFileSync(
0153:     path.resolve("../deeptutor/api/routers/knowledge.py"),
0154:     "utf8",
0155:   );
```


### `tests/conftest.py`

L13–L40：

```text
0013: 
0014: def _require_isolated_test_environment() -> None:
0015:     """Refuse collection before application imports can touch owner settings."""
0016:     repo = Path(__file__).resolve().parents[1]
0017:     raw_root = os.environ.get("SELFLEARN_TEST_ROOT", "")
0018:     valid = os.environ.get("SELFLEARN_ISOLATED_TEST_RUN") == "1" and bool(raw_root)
0019:     if valid:
0020:         root = Path(raw_root).resolve()
0021:         valid = root.is_dir() and not root.is_relative_to(repo) and not repo.is_relative_to(root)
0022:         for key in (
0023:             "HOME",
0024:             "XDG_CONFIG_HOME",
0025:             "XDG_DATA_HOME",
0026:             "XDG_CACHE_HOME",
0027:             "TMPDIR",
0028:             "DEEPTUTOR_HOME",
0029:         ):
0030:             value = os.environ.get(key)
0031:             valid = valid and bool(value) and Path(value).resolve().is_relative_to(root)
0032:     if not valid:
0033:         raise pytest.UsageError(
0034:             "Unisolated pytest collection refused before application imports. "
0035:             "Use: .venv/bin/python scripts/run_tests_isolated.py [pytest arguments]"
0036:         )
0037: 
0038: 
0039: _require_isolated_test_environment()
0040: 
```


### `tests/phase1/conftest.py`

L27–L76：

```text
0027: @pytest.fixture
0028: def p1_runtime(tmp_path: Path) -> Iterator[Path]:
0029:     """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
0030:     with helpers.isolated_runtime(tmp_path) as admin_root:
0031:         yield admin_root
0032: 
0033: 
0034: @pytest.fixture
0035: def p1_subjects(p1_runtime: Path) -> dict:
0036:     """在隔离根下建 A / B / global 三处**同名**知识库，各带独立标记。"""
0037:     subjects = helpers.make_same_name_kbs(p1_runtime)
0038:     subjects["_admin_root"] = p1_runtime
0039:     return subjects
0040: 
0041: 
0042: @pytest.fixture
0043: def p1_llm() -> helpers.FakeLLMClient:
0044:     """可 await 的 LLM 替身（未安装；见 :func:`p1_providers`）。"""
0045:     return helpers.FakeLLMClient()
0046: 
0047: 
0048: @pytest.fixture
0049: def p1_embedding() -> helpers.FakeEmbeddingClient:
0050:     return helpers.FakeEmbeddingClient()
0051: 
0052: 
0053: @pytest.fixture
0054: def p1_stt() -> helpers.FakeSTT:
0055:     return helpers.FakeSTT()
0056: 
0057: 
0058: @pytest.fixture
0059: def p1_providers(
0060:     monkeypatch: pytest.MonkeyPatch,
0061:     p1_runtime: Path,
0062:     p1_llm: helpers.FakeLLMClient,
0063:     p1_embedding: helpers.FakeEmbeddingClient,
0064:     p1_stt: helpers.FakeSTT,
0065: ) -> dict:
0066:     """把三个替身装到真实被调用的模块上，避免任何真实供应商调用。"""
0067:     return helpers.install_provider_stubs(
0068:         monkeypatch, llm=p1_llm, embedding=p1_embedding, stt=p1_stt
0069:     )
0070: 
0071: 
0072: @pytest.fixture
0073: def p1_route_client(p1_runtime: Path) -> Iterator[object]:
0074:     """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
0075:     with helpers.route_client() as client:
0076:         yield client
```


### `tests/phase1/helpers.py`

L508–L532：

```text
0508: @contextlib.contextmanager
0509: def isolated_runtime(
0510:     tmp_path: Path,
0511:     *,
0512:     guard_network: bool = True,
0513:     allow_endpoints: Iterable[tuple[str, int]] = (),
0514:     allow_unix_paths: Iterable[str] = (),
0515:     **kwargs: Any,
0516: ) -> Iterator[Path]:
0517:     """重定向到 tmp 并在退出时无条件恢复；默认同时启用网络 guard。"""
0518:     snap, admin_root = redirect_runtime(tmp_path, **kwargs)
0519:     active_token = _ACTIVE_ROOT.set(admin_root)
0520:     try:
0521:         if guard_network:
0522:             with block_external_network(
0523:                 allow_endpoints=allow_endpoints, allow_unix_paths=allow_unix_paths
0524:             ):
0525:                 yield admin_root
0526:         else:
0527:             yield admin_root
0528:     finally:
0529:         try:
0530:             restore_runtime(snap)
0531:         finally:
0532:             _ACTIVE_ROOT.reset(active_token)
```

L828–L858：

```text
0828: def install_provider_stubs(
0829:     monkeypatch,
0830:     *,
0831:     llm: "FakeLLMClient | None" = None,
0832:     embedding: "FakeEmbeddingClient | None" = None,
0833:     stt: "FakeSTT | None" = None,
0834: ) -> dict[str, Any]:
0835:     """把替身装到真实被调用的模块上；返回已安装的替身。"""
0836:     ensure_bootstrap_home()
0837:     installed: dict[str, Any] = {}
0838: 
0839:     def replace_callable(module_name: str, name: str, replacement: Any) -> None:
0840:         original = getattr(_module(module_name), name)
0841:         # Packages re-export these functions; loaded consumers may already have
0842:         # imported the same function. Patch those identities as well.
0843:         for loaded_name, module in tuple(sys.modules.items()):
0844:             if (loaded_name.startswith("deeptutor.")
0845:                     and getattr(module, "__dict__", {}).get(name) is original):
0846:                 monkeypatch.setattr(module, name, replacement)
0847:     if llm is not None:
0848:         replace_callable("deeptutor.services.llm.client", "get_llm_client", lambda *a, **k: llm)
0849:         replace_callable("deeptutor.services.llm.factory", "complete_response", llm.complete_response)
0850:         installed["llm"] = llm
0851:     if embedding is not None:
0852:         replace_callable("deeptutor.services.embedding.client", "get_embedding_client",
0853:                          lambda *a, **k: embedding)
0854:         installed["embedding"] = embedding
0855:     if stt is not None:
0856:         replace_callable("deeptutor.services.asr.transcribe", "transcribe", stt.transcribe)
0857:         installed["stt"] = stt
0858:     return installed
```

L888–L919：

```text
0888: @contextlib.contextmanager
0889: def block_external_network(
0890:     *,
0891:     allow_endpoints: Iterable[tuple[str, int]] = (),
0892:     allow_unix_paths: Iterable[str] = (),
0893: ) -> Iterator[frozenset[tuple[str, int]]]:
0894:     """拦截未声明的 TCP/UDP/DNS 出口。
0895: 
0896:     覆盖 ``connect`` / ``connect_ex`` / ``sendto`` / ``sendmsg`` /
0897:     ``create_connection`` 与 DNS 解析。只有白名单里的 ``(host, port)`` 与显式
0898:     ``allow_unix_paths`` 可用；``0.0.0.0``、空 host、任意回环端口默认拒绝。
0899:     """
0900:     endpoints = list(allow_endpoints)
0901:     for host, port in endpoints:
0902:         if host not in LOOPBACK_HOSTS or type(port) is not int or not 1 <= port <= 65535:
0903:             raise IsolationError("only explicit localhost endpoints with valid ports are allowed")
0904:     allowed = frozenset((_normalize_host(h), p) for h, p in endpoints)
0905:     allowed_hosts = frozenset(host for host, _port in allowed)
0906:     allowed_unix = frozenset(str(p) for p in allow_unix_paths)
0907: 
0908:     previous = {
0909:         "connect": socket.socket.connect,
0910:         "connect_ex": socket.socket.connect_ex,
0911:         "sendto": socket.socket.sendto,
0912:         "sendmsg": socket.socket.sendmsg,
0913:         "create_connection": socket.create_connection,
0914:         "getaddrinfo": socket.getaddrinfo,
0915:         "gethostbyname": socket.gethostbyname,
0916:         "gethostbyname_ex": socket.gethostbyname_ex,
0917:     }
0918:     # Nested explicit localhost stubs must work under p1_runtime's default
0919:     # guard. Delegate to the underlying transport, then restore the outer guard.
```

L1131–L1155：

```text
1131: def build_route_app():
1132:     """构造只含真实科目路由的轻量 app，**不挂**后台 lifespan。
1133: 
1134:     用带完整 lifespan 的 ``deeptutor.api.main.app`` 做普通路由测试，会把 EventBus/cron/
1135:     LLM 锚定在启动时的根上并跨隔离作用域存活。完整 lifespan 的验收放在独立子进程里
1136:     （:func:`full_lifespan_probe`）。
1137:     """
1138:     from fastapi import FastAPI
1139: 
1140:     from deeptutor.api.routers import subjects
1141: 
1142:     app = FastAPI()
1143:     app.include_router(subjects.router, prefix=ROUTE_PREFIX)
1144:     return app
1145: 
1146: 
1147: @contextlib.contextmanager
1148: def route_client() -> Iterator[Any]:
1149:     """在当前隔离作用域内创建并**关闭**一个真实路由客户端。"""
1150:     if _ACTIVE_ROOT.get() is None:
1151:         raise IsolationError("route_client requires an active isolated_runtime scope")
1152:     from fastapi.testclient import TestClient
1153: 
1154:     with TestClient(build_route_app()) as client:
1155:         yield client
```


### `tests/phase1/test_http_acceptance.py`

L97–L145：

```text
0097: def _app() -> FastAPI:
0098:     app = FastAPI()
0099:     app.include_router(subjects_router.router, prefix=ROUTE)
0100:     app.include_router(outputs.router, prefix=OUTPUTS)
0101:     return app
0102: 
0103: 
0104: @pytest.fixture
0105: def http_client(p1_runtime: Path, p1_providers) -> TestClient:
0106:     _seed_catalog(p1_runtime)
0107:     with TestClient(_app()) as client:
0108:         yield client
0109: 
0110: 
0111: def _create(client: TestClient, name: str, *, description: str = "", term: str = "2026春"):
0112:     response = client.post(
0113:         ROUTE, data={"name": name, "description": description, "term": term}
0114:     )
0115:     assert response.status_code == 200, response.text
0116:     return response.json()["subject"]
0117: 
0118: 
0119: def _upload(
0120:     client: TestClient,
0121:     subject_id: str,
0122:     *,
0123:     filename: str,
0124:     content: bytes,
0125:     type_: str = "assignment",
0126: ):
0127:     return client.post(
0128:         f"{ROUTE}/{subject_id}/knowledge/upload",
0129:         files=[("files", (filename, content, "text/plain"))],
0130:         data={"type": type_},
0131:     )
0132: 
0133: 
0134: def _wait_ready(client: TestClient, subject_id: str, kb_name: str = KB_NAME) -> dict:
0135:     deadline = time.monotonic() + 20
0136:     last: dict = {}
0137:     while time.monotonic() < deadline:
0138:         response = client.get(f"{ROUTE}/{subject_id}/knowledge/{kb_name}/status")
0139:         assert response.status_code == 200, response.text
0140:         last = response.json()
0141:         if last.get("status") == "ready":
0142:             return last
0143:         if last.get("status") == "error":
0144:             raise AssertionError(last)
0145:         time.sleep(0.05)
```

L177–L216：

```text
0177: def test_h1_http_crud_and_patch_three_state(http_client: TestClient) -> None:
0178:     a = _create(http_client, "科目 A", description="原描述", term="2026春")
0179:     b = _create(http_client, "科目 B", description="B 描述", term="2025秋")
0180:     assert a["id"] and b["id"] and a["id"] != b["id"]
0181:     assert a["id"].islower() and " " not in a["id"]
0182:     assert a["name"] == "科目 A" and a["term"] == "2026春"
0183: 
0184:     listing = http_client.get(ROUTE)
0185:     assert listing.status_code == 200
0186:     ids = {item["id"] for item in listing.json()["subjects"]}
0187:     assert {a["id"], b["id"]} <= ids
0188: 
0189:     # 只提交 description：term 必须保留。
0190:     patched = http_client.patch(f"{ROUTE}/{a['id']}", data={"description": "新描述"})
0191:     assert patched.status_code == 200, patched.text
0192:     assert patched.json()["subject"]["description"] == "新描述"
0193:     assert patched.json()["subject"]["term"] == "2026春"
0194: 
0195:     # 显式空字符串：只清空 term，description 保留。
0196:     cleared = http_client.patch(f"{ROUTE}/{a['id']}", data={"term": ""})
0197:     assert cleared.status_code == 200, cleared.text
0198:     assert cleared.json()["subject"]["term"] == ""
0199:     assert cleared.json()["subject"]["description"] == "新描述"
0200: 
0201:     # 空 PATCH 不写注册表（字节不变）。
0202:     registry = store.subjects_root() / "index.json"
0203:     before = registry.read_bytes()
0204:     noop = http_client.patch(f"{ROUTE}/{a['id']}", data={})
0205:     assert noop.status_code == 200, noop.text
0206:     assert noop.json()["subject"]["description"] == "新描述"
0207:     assert registry.read_bytes() == before
0208: 
0209:     # 不存在的科目是具名 C02，而不是半写或 500。
0210:     missing = http_client.patch(f"{ROUTE}/not-registered", data={"description": "x"})
0211:     assert missing.status_code == 404, missing.text
0212:     body = missing.json()
0213:     assert body["detail"] == body["error"]["message"]
0214:     assert body["error"]["code"] == "subject_not_found"
0215:     assert registry.read_bytes() == before
0216:     assert b["id"] in {item["id"] for item in http_client.get(ROUTE).json()["subjects"]}
```

L810–L849：

```text
0810: def test_h6_export_downloads_verified_zip_and_excludes_private_or_transient(
0811:     http_client: TestClient, p1_llm
0812: ) -> None:
0813:     a = _create(http_client, "导出科目 A")
0814:     b = _create(http_client, "导出科目 B")
0815:     sid = a["id"]
0816:     # 真实复习包产物是 artifacts/ 的可核对输入。
0817:     pdf = _review_pack(http_client, sid, "pdf", p1_llm, "S14-EXPORT-ARTIFACT-44d0")
0818:     assert http_client.get(pdf["url"]).status_code == 200
0819: 
0820:     root = store.subject_dir(sid)
0821:     (root / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
0822:     (root / "chat_history.json").write_text('{"private": "chat"}', encoding="utf-8")
0823:     (root / "settings.json").write_text('{"api_key": "sk-never-export"}', encoding="utf-8")
0824:     (root / "_report_runs" / "run-private").mkdir(parents=True, exist_ok=True)
0825:     (root / "_report_runs" / "run-private" / "diagnostic.log").write_text(
0826:         "private", encoding="utf-8"
0827:     )
0828:     (root / "materials" / "lecture" / ".hidden").write_text("hidden", encoding="utf-8")
0829:     (root / "materials" / "lecture" / "scratch.tmp").write_text("tmp", encoding="utf-8")
0830:     (root / "materials" / "lecture" / "old.lock").write_text("lock", encoding="utf-8")
0831:     (root / "materials" / "lecture" / "export-note.txt").write_text(
0832:         "exported material", encoding="utf-8"
0833:     )
0834:     public = store.current_subject_paths().get_public_outputs_root() / "subjects" / sid
0835:     public.mkdir(parents=True, exist_ok=True)
0836:     (public / "subject-export-deadbeef.zip").write_bytes(b"PK-old")
0837:     (public / "subject-backup-123.zip").write_bytes(b"PK-backup")
0838: 
0839:     response = http_client.get(f"{ROUTE}/{sid}/export")
0840:     assert response.status_code == 200, response.text
0841:     body = response.json()
0842:     assert body["schema_version"] == 1
0843:     assert re.fullmatch(r"[a-f0-9]{32}", body["export_id"])
0844:     assert body["url"].startswith(f"{OUTPUTS}/subjects/{sid}/subject-export-")
0845:     assert body["path"] == f"subjects/{sid}/{Path(body['url']).name}"
0846: 
0847:     download = http_client.get(body["url"])
0848:     assert download.status_code == 200, download.text
0849:     assert download.content[:2] == b"PK" and len(download.content) == body["size"]
```

L918–L951：

```text
0918: def test_h6_delete_a_removes_only_a_and_preserves_b_and_global(http_client: TestClient) -> None:
0919:     a = _create(http_client, "删除科目 A")
0920:     b = _create(http_client, "删除科目 B")
0921:     sid_a, sid_b = a["id"], b["id"]
0922:     (store.subject_dir(sid_a) / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
0923:     (store.subject_dir(sid_b) / "materials" / "lecture").mkdir(parents=True, exist_ok=True)
0924:     (store.subject_dir(sid_a) / "materials" / "lecture" / "a.txt").write_text(
0925:         "A unique", encoding="utf-8"
0926:     )
0927:     (store.subject_dir(sid_b) / "materials" / "lecture" / "b.txt").write_text(
0928:         "B unique", encoding="utf-8"
0929:     )
0930:     outputs_a = store.current_subject_paths().get_public_outputs_root() / "subjects" / sid_a
0931:     outputs_a.mkdir(parents=True, exist_ok=True)
0932:     (outputs_a / "artifact.txt").write_text("A artifact", encoding="utf-8")
0933:     global_dir = store.current_subject_paths().get_knowledge_bases_root()
0934:     global_dir.mkdir(parents=True, exist_ok=True)
0935:     (global_dir / "global-marker.txt").write_text("global", encoding="utf-8")
0936: 
0937:     subject_a_root = store.subject_dir(sid_a)
0938:     before_b = _tree(store.subject_dir(sid_b))
0939:     before_global = _tree(global_dir)
0940: 
0941:     deleted = http_client.delete(f"{ROUTE}/{sid_a}")
0942:     assert deleted.status_code == 200, deleted.text
0943:     assert deleted.json() == {"status": "deleted", "subject_id": sid_a}
0944:     after = http_client.get(f"{ROUTE}/{sid_a}/knowledge")
0945:     assert after.status_code == 404, after.text
0946:     assert after.json()["error"]["code"] == "subject_not_found"
0947:     assert not subject_a_root.exists()
0948:     assert not outputs_a.exists()
0949:     assert _tree(store.subject_dir(sid_b)) == before_b
0950:     assert _tree(global_dir) == before_global
0951:     assert sid_b in {item["id"] for item in http_client.get(ROUTE).json()["subjects"]}
```


### `tests/phase1/test_ws_acceptance.py`

L124–L155：

```text
0124: @pytest.fixture
0125: def ws_env(p1_runtime: Path, p1_providers, monkeypatch: pytest.MonkeyPatch):
0126:     _seed_catalog(p1_runtime)
0127:     monkeypatch.setattr(llamaindex_pipeline.LlamaIndexPipeline, "_configure_settings", _configure_llamaindex)
0128:     monkeypatch.setattr(llamaindex_pipeline.LlamaIndexPipeline, "_current_signature", lambda self: None)
0129:     monkeypatch.setattr(
0130:         llamaindex_pipeline.LlamaIndexPipeline, "_verify_embedding_connectivity", _noop_verify
0131:     )
0132:     # 本验收手工建立无签名版本的 fixture index；这个不适用于 fixture 的
0133:     # "indexed with unknown" 提示不应变成 raw-log 回调泄漏，业务检索仍然真实。
0134:     monkeypatch.setattr(
0135:         llamaindex_pipeline.LlamaIndexPipeline,
0136:         "_embedding_mismatch_warning",
0137:         lambda self, kb_name: "",
0138:     )
0139: 
0140:     async def no_title(self, **_kwargs):
0141:         return None
0142: 
0143:     monkeypatch.setattr(TurnRuntimeManager, "_maybe_generate_session_title", no_title)
0144:     return SimpleNamespace(
0145:         root=p1_runtime,
0146:         embedding=p1_providers["embedding"],
0147:         llm=p1_providers["llm"],
0148:     )
0149: 
0150: 
0151: def _app() -> FastAPI:
0152:     app = FastAPI()
0153:     app.include_router(unified_ws.router, prefix="/api/v1")
0154:     return app
0155: 
```

L451–L490：

```text
0451: def test_w2_ws_subject_three_state_and_session_isolation(
0452:     ws_env, monkeypatch: pytest.MonkeyPatch
0453: ) -> None:
0454:     a = helpers.make_subject(ws_env.root, "三态A")
0455:     b = helpers.make_subject(ws_env.root, "三态B")
0456:     _install_client(
0457:         monkeypatch,
0458:         [_final(f"W2-{index}") for index in range(8)],
0459:     )
0460: 
0461:     with TestClient(_app()) as test_client:
0462:         with test_client.websocket_connect(ROUTE) as websocket:
0463:             first = _turn(
0464:                 websocket,
0465:                 {
0466:                     "content": "explicit A",
0467:                     "session_id": None,
0468:                     "subject_id": a.subject_id,
0469:                     "tools": [],
0470:                     "config": {},
0471:                 },
0472:             )
0473:             session_id = _session_id(first)
0474:             turns = [first]
0475:             for content, subject in (
0476:                 ("omitted keeps A", "__omit__"),
0477:                 ("switch B", b.subject_id),
0478:                 ("null clears", None),
0479:                 ("omitted keeps clear", "__omit__"),
0480:                 ("empty clears", ""),
0481:             ):
0482:                 payload: dict[str, Any] = {
0483:                     "content": content,
0484:                     "session_id": session_id,
0485:                     "tools": [],
0486:                     "config": {},
0487:                 }
0488:                 if subject != "__omit__":
0489:                     payload["subject_id"] = subject
0490:                 turns.append(_turn(websocket, payload))
```

L1387–L1404：

```text
1387: def test_formal_app_registers_http_and_ws_with_real_lifespan() -> None:
1388:     repo = Path(__file__).resolve().parents[2]
1389:     proc = subprocess.run(
1390:         [sys.executable, "-c", FORMAL_APP_PROBE, str(repo)],
1391:         capture_output=True,
1392:         text=True,
1393:         timeout=120,
1394:         cwd=str(repo),
1395:     )
1396:     lines = [line for line in proc.stdout.splitlines() if line.strip()]
1397:     payload = json.loads(lines[-1]) if lines else {}
1398:     assert proc.returncode == 0, proc.stderr[-3000:]
1399:     assert payload.get("ok") is True, payload
1400:     assert payload.get("subjects_status") == 200
1401:     assert payload.get("pong") is True
1402:     assert payload.get("cron_under_tmp") is True
1403:     assert payload.get("shutdown_ok") is True
1404:     assert payload.get("home_removed") is True
```


### `deeptutor/api/main.py`

L18–L21：

```text
0018: ensure_runtime_settings_files()
0019: export_runtime_settings_to_env(overwrite=True)
0020: configure_logging()
0021: logger = logging.getLogger(__name__)
```

L102–L151：

```text
0102: @asynccontextmanager
0103: async def lifespan(app: FastAPI):
0104:     """
0105:     Application lifecycle management
0106:     Gracefully handle startup and shutdown events, avoid CancelledError
0107:     """
0108:     # Execute on startup
0109:     logger.info("Application startup")
0110: 
0111:     # Validate configuration consistency
0112:     validate_tool_consistency()
0113: 
0114:     # Initialize LLM client early so OPENAI_* env vars are available before
0115:     # any downstream provider integrations start.
0116:     try:
0117:         from deeptutor.services.llm import get_llm_client
0118: 
0119:         llm_client = get_llm_client()
0120:         logger.info(f"LLM client initialized: model={llm_client.config.model}")
0121:     except Exception as e:
0122:         logger.warning(f"Failed to initialize LLM client at startup: {e}")
0123: 
0124:     try:
0125:         from deeptutor.events.event_bus import get_event_bus
0126: 
0127:         event_bus = get_event_bus()
0128:         await event_bus.start()
0129:         logger.info("EventBus started")
0130:     except Exception as e:
0131:         logger.warning(f"Failed to start EventBus: {e}")
0132: 
0133:     try:
0134:         from deeptutor.services.cron import get_cron_service
0135: 
0136:         await get_cron_service().start()
0137:     except Exception as e:
0138:         logger.warning(f"Failed to start cron service: {e}")
0139: 
0140:     # Migrate any v1 memory files (PROFILE.md / SUMMARY.md) into a
0141:     # backup folder so the v2 three-layer subsystem starts clean.
0142:     try:
0143:         from deeptutor.services.memory import migrate_v1_if_needed
0144: 
0145:         backup = migrate_v1_if_needed()
0146:         if backup is not None:
0147:             logger.info("v1 memory archived to %s", backup)
0148:     except Exception as e:
0149:         logger.warning(f"v1 memory migration failed: {e}")
0150: 
0151:     yield
```

L193–L193：

```text
0193: app = FastAPI(
```

L391–L401：

```text
0391: app.include_router(
0392:     attachments.router,
0393:     prefix="/api/attachments",
0394:     tags=["attachments"],
0395:     dependencies=_auth,
0396: )
0397: 
0398: # Unified WebSocket endpoint — auth is checked inside the handler (WebSockets
0399: # cannot use FastAPI dependencies in the standard way)
0400: app.include_router(unified_ws.router, prefix="/api/v1", tags=["unified-ws"])
0401: 
```


### `deeptutor/api/routers/subjects.py`

L1–L83：

```text
0001: """Subjects — subject-scoped learning data (M1).
0002: 
0003: Routes: subject CRUD, per-subject knowledge bases (upload → index → query).
0004: Knowledge indexing reuses the LlamaIndex pipeline through the same
0005: ``KnowledgeBaseInitializer`` / ``run_initialization_task`` machinery as the
0006: global knowledge center, but bound to ``data/subjects/<id>/knowledge_bases``.
0007: """
0008: 
0009: from __future__ import annotations
0010: 
0011: import asyncio
0012: import logging
0013: from pathlib import Path
0014: 
0015: from fastapi import (
0016:     APIRouter,
0017:     BackgroundTasks,
0018:     Depends,
0019:     File,
0020:     Form,
0021:     HTTPException,
0022:     Request,
0023:     UploadFile,
0024: )
0025: 
0026: from deeptutor.api.routers.auth import require_auth
0027: from deeptutor.api.routers.knowledge import (
0028:     KnowledgeBaseInitializer,
0029:     ProgressTracker,
0030:     _build_unique_task_id,
0031:     get_task_stream_manager,
0032:     run_initialization_task,
0033: )
0034: from deeptutor.api.subject_route import SubjectRoute
0035: from deeptutor.knowledge.manager import KnowledgeBaseManager
0036: from deeptutor.services.rag.service import RAGService
0037: from deeptutor.subjects import (
0038:     exam_points,
0039:     grading,
0040:     json_store,
0041:     knowledge_points,
0042:     store,
0043:     subject_operations,
0044:     uploads,
0045:     wrong_book,
0046: )
0047: from deeptutor.subjects.errors import ErrorCode, SubjectOperationError, subject_error
0048: 
0049: logger = logging.getLogger(__name__)
0050: 
0051: #: 科目路由专用错误出口：只影响本 router，其他上游 router 的异常机制不变（C02/P1-56）。
0052: router = APIRouter(route_class=SubjectRoute)
0053: 
0054: #: Extension → knowledge type for ``type=auto`` uploads. The single source of
0055: #: truth lives with the upload preflight (``subjects/uploads.py``); the name is
0056: #: re-exported here because it is part of this router's historical surface.
0057: TYPE_BY_EXTENSION = uploads.TYPE_BY_EXTENSION
0058: ALLOWED_TYPES = uploads.ALLOWED_TYPES
0059: 
0060: 
0061: def _require_subject(subject_id: str) -> dict:
0062:     """Resolve one subject in the **current user's** registry (C01/C02).
0063: 
0064:     The id is validated as a plain slug before anything is resolved: an id that
0065:     cannot be a single path segment is ``invalid_subject_id`` (400) rather than a
0066:     lookup miss, and no "clean-up" or admin fallback is attempted. A well-formed
0067:     but unregistered id raises the named ``subject_not_found`` (404) instead of an
0068:     ``HTTPException`` whose detail echoed the caller's input.
0069:     """
0070:     if not store.is_valid_subject_id(subject_id):
0071:         raise store.InvalidSubjectIdError(subject_id)
0072:     subject = store.get_subject(subject_id)
0073:     if subject is None:
0074:         raise store.SubjectNotFoundError(subject_id)
0075:     return subject
0076: 
0077: 
0078: def _kb_manager(subject_id: str) -> KnowledgeBaseManager:
0079:     return KnowledgeBaseManager(base_dir=str(store.subject_kb_base_dir(subject_id)))
0080: 
0081: 
0082: @router.get("")
0083: async def list_subjects(_: None = Depends(require_auth)):
```


### `deeptutor/api/routers/unified_ws.py`

L1–L60：

```text
0001: """
0002: Unified WebSocket Endpoint
0003: ==========================
0004: 
0005: Single ``/api/v1/ws`` endpoint for turn-based execution and replayable streaming.
0006: 
0007: Supported client message ``type`` values:
0008: 
0009: - ``message`` / ``start_turn`` — start a new turn from a payload.
0010: - ``subscribe_turn`` — stream events of an existing turn (with ``after_seq``).
0011: - ``subscribe_session`` — stream events of the active turn for a session.
0012: - ``resume_from`` — resume an in-flight turn after reconnection.
0013: - ``unsubscribe`` — stop a previously created subscription.
0014: - ``cancel_turn`` — cancel a running turn.
0015: - ``submit_user_reply`` — deliver the user's reply for an ``ask_user``
0016:   paused turn so the agentic loop can resume on the same turn.
0017: - ``regenerate`` — re-run the last user message in the given session as a
0018:   brand-new turn. Replaces the trailing assistant message (if any) and
0019:   reuses the session's stored capability/tools/preferences. Optional
0020:   ``overrides`` field accepts ``capability``, ``tools``, ``knowledge_bases``,
0021:   ``language``, ``config``, ``notebook_references``, ``history_references``,
0022:   ``mastery_path_id``.
0023:   Errors: ``regenerate_busy`` (another turn is running) and
0024:   ``nothing_to_regenerate`` (no prior user message).
0025: - ``check_active_turn`` — report whether the session has a live running turn;
0026:   replies with ``active_turn_info`` (``turn_id``/``status``), marking stale
0027:   persisted "running" rows as cancelled when no live execution exists.
0028: - ``user_input`` — deliver a learner answer to the turn's StreamBus
0029:   (resolves a pending ``wait_for_input``, e.g. an ``ask_user`` pause).
0030: """
0031: 
0032: from __future__ import annotations
0033: 
0034: import asyncio
0035: import json
0036: import logging
0037: from typing import Any
0038: 
0039: from fastapi import APIRouter, WebSocket, WebSocketDisconnect
0040: 
0041: from deeptutor.subjects.errors import SubjectOperationError, SubjectStorageError
0042: 
0043: router = APIRouter()
0044: logger = logging.getLogger(__name__)
0045: 
0046: 
0047: @router.websocket("/ws")
0048: async def unified_websocket(ws: WebSocket) -> None:
0049:     from deeptutor.api.routers.auth import ws_auth_failed, ws_require_auth
0050:     from deeptutor.multi_user.context import reset_current_user
0051: 
0052:     user_token = await ws_require_auth(ws)
0053:     if user_token is ws_auth_failed:
0054:         return
0055: 
0056:     await ws.accept()
0057:     closed = False
0058:     subscription_tasks: dict[str, asyncio.Task[None]] = {}
0059: 
0060:     async def safe_send(data: dict[str, Any]) -> None:
```


### `web/app/api/v1/knowledge/create/route.ts`

L1–L8：

```text
0001: import { forwardBackendUpload } from "@/lib/streaming-upload-proxy";
0002: 
0003: export const runtime = "nodejs";
0004: export const dynamic = "force-dynamic";
0005: 
0006: export function POST(request: Request): Promise<Response> {
0007:   return forwardBackendUpload(request);
0008: }
```


### `web/app/api/v1/knowledge/[kbName]/upload/route.ts`

L1–L8：

```text
0001: import { forwardBackendUpload } from "@/lib/streaming-upload-proxy";
0002: 
0003: export const runtime = "nodejs";
0004: export const dynamic = "force-dynamic";
0005: 
0006: export function POST(request: Request): Promise<Response> {
0007:   return forwardBackendUpload(request);
0008: }
```


### `scripts/run_tests_isolated.py`

L1–L7：

```text
0001: #!/usr/bin/env python3
0002: """Run pytest with disposable settings, credentials and a Python network guard.
0003: 
0004: Usage: .venv/bin/python scripts/run_tests_isolated.py -q tests/phase1
0005: Without arguments, pytest uses both configured testpaths. No real model/config
0006: is copied into the disposable home. This does not claim OS sandbox isolation.
0007: """
```

L24–L49：

```text
0024: def main(args: list[str]) -> int:
0025:     with tempfile.TemporaryDirectory(prefix="selflearn-tests-") as root_value:
0026:         root = Path(root_value)
0027:         env = clean_env(root)
0028:         env["DEEPTUTOR_HOME"] = str(root / "runtime")
0029:         Path(env["DEEPTUTOR_HOME"]).mkdir()
0030:         guard = root / "guard"
0031:         guard.mkdir()
0032:         (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
0033:         env["S13_ENDPOINT_REGISTRY"] = str(guard / "endpoints.json")
0034:         env["PYTHONPATH"] = str(guard) + os.pathsep + str(REPO)
0035:         bootstrap = subprocess.run(
0036:             [sys.executable, "-c", BOOTSTRAP_CODE],
0037:             cwd=REPO,
0038:             env=env,
0039:             timeout=120,
0040:             check=False,
0041:         )
0042:         if bootstrap.returncode:
0043:             return bootstrap.returncode
0044:         process = subprocess.Popen(
0045:             [sys.executable, "-m", "pytest", *(args or ["-q"])],
0046:             cwd=REPO,
0047:             env=env,
0048:             start_new_session=True,
0049:         )
```


### `scripts/phase1_data_baseline.py`

L22–L49：

```text
0022: MANIFEST = "plans/phase1/data_baseline_exception.json"
0023: ORIGINAL_SHA = "630dbac8a405233f2b946e3a60e42d6f9a5ebe43aedb81a3b702109e3f51110e"
0024: APPROVED_SHA = "65db48a600816207a3b6f366fbb227ef06960d3eacd519b2e281e8978a23d5a0"
0025: 
0026: 
0027: def load_data_baseline(root: Path, original: Path) -> dict:
0028:     """Use the historical baseline unless the exact approved exception validates.
0029: 
0030:     A malformed/stale manifest fails closed; it never selects today's data as a
0031:     new baseline. All six root inventories must match S13 except this one file's
0032:     approved size/hash, including modes, directories and supplementary trees.
0033:     """
0034:     root = root.resolve()
0035:     historical = json.loads(original.read_text(encoding="utf-8"))
0036:     path = root / MANIFEST
0037:     if not path.exists():
0038:         return historical
0039:     record = json.loads(path.read_text(encoding="utf-8"))
0040:     if (
0041:         record.get("schema_version") != 1
0042:         or record.get("exception_id") != "S14-model-catalog-20261020"
0043:         or record.get("status") != "user_authorized"
0044:         or record.get("authorization", {}).get("actor") != "user"
0045:         or record.get("authorization", {}).get("text")
0046:         != "接受单项例外，允许建立新配置基线"
0047:         or record.get("allowed_path") != "data/user/settings/model_catalog.json"
0048:     ):
0049:         raise ValueError("Invalid S14 data-baseline exception authorization")
```

L62–L83：

```text
0062:     if record["historical"]["path"] != original.relative_to(root).as_posix():
0063:         raise ValueError("Exception references a different historical baseline")
0064:     if snapshot("historical") != historical:
0065:         raise ValueError("Historical baseline mismatch")
0066:     prior, approved = snapshot("previous"), snapshot("baseline")
0067:     if not compare_data(historical, prior)["ok"]:
0068:         raise ValueError("S13 baseline does not preserve historical data")
0069:     for value in (prior, approved):
0070:         if value["root"] != str(root):
0071:             raise ValueError("Data baseline belongs to another repository")
0072:         if set(value["roots"]) != {"learning_tree", "public_outputs", "settings"}:
0073:             raise ValueError("Incomplete primary data inventory")
0074:         if set(value["supplementary_roots"]) != {"global_knowledge_bases", "memory", "system"}:
0075:             raise ValueError("Incomplete supplementary data inventory")
0076:     old = prior["roots"]["settings"]["files"]["model_catalog.json"]
0077:     new = approved["roots"]["settings"]["files"]["model_catalog.json"]
0078:     if old.get("sha256") != ORIGINAL_SHA or old.get("size") != 3608:
0079:         raise ValueError("Unexpected original catalog identity")
0080:     if new != {**old, "sha256": APPROVED_SHA, "size": 3117}:
0081:         raise ValueError("Exception authorizes only the specified catalog bytes")
0082:     projected = deepcopy(approved)
0083:     projected["roots"]["settings"]["files"]["model_catalog.json"] = old
```


### `plans/phase1/data_baseline_exception.json`

L1–L38：

```text
0001: {
0002:   "schema_version": 1,
0003:   "exception_id": "S14-model-catalog-20261020",
0004:   "status": "user_authorized",
0005:   "recorded_at_utc": "2026-10-20T11:14:34.258088+00:00",
0006:   "authorization": {
0007:     "actor": "user",
0008:     "text": "接受单项例外，允许建立新配置基线"
0009:   },
0010:   "allowed_path": "data/user/settings/model_catalog.json",
0011:   "historical": {
0012:     "path": ".phase1-evidence/P1-00/real_data_protection_baseline.json",
0013:     "sha256": "fd4fe5d4079712d0f587efbedeeaf54583fe9c9e1e4ce34e691b956245c8f461"
0014:   },
0015:   "previous": {
0016:     "path": ".phase1-evidence/reviews/S13-final/data_after.json",
0017:     "sha256": "3349b624094145a4cba7b240d300b54f7a8766235caa037c5621ed2ca7222ce2"
0018:   },
0019:   "baseline": {
0020:     "path": ".phase1-evidence/reviews/S14-final/data_exception_baseline.json",
0021:     "sha256": "1d231082f8bc3c35bda8728491710c18fa4c8259d89d7b34878b7c8eaa0c3d9b"
0022:   },
0023:   "before": {
0024:     "sha256": "630dbac8a405233f2b946e3a60e42d6f9a5ebe43aedb81a3b702109e3f51110e",
0025:     "size": 3608
0026:   },
0027:   "after": {
0028:     "sha256": "65db48a600816207a3b6f366fbb227ef06960d3eacd519b2e281e8978a23d5a0",
0029:     "size": 3117
0030:   },
0031:   "incident": {
0032:     "path": ".phase1-evidence/stages/S14/incident.json",
0033:     "sha256": "24102afcacc3ba06123ebc8c6db3a59b74775b278994ba4c8b1d44aab253b4e7"
0034:   },
0035:   "original_restored": false,
0036:   "live_provider_validation": false,
0037:   "meaning": "User accepts the single lost configuration baseline. All other inventories, metadata and old evidence remain protected. This is not restoration or provider verification."
0038: }
```

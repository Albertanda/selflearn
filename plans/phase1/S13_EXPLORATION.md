# S13 已探索文件与关键片段

本包由 `.phase1-evidence/reviews/S12-final/build_s13_packet.py` 生成。SHA-256 对应生成时完整文件字节；片段保留原文，行号为一基。只读参考不获得写权限；阶段范围以 stages.json 为准。

## 阶段与任务

S13：全量回归及真实沙箱验收。顺序 P1-49 → P1-50；契约 C11, C14。当前允许路径动态展开：2 项模式，0 个现存文件，2 个缺失项。缺失：scripts/phase1_sandbox_acceptance.py, scripts/phase1_verify.py。两项新增脚本目前都不存在。

P1-49 通过新脚本实际运行等价完整 `./.venv/bin/python -m pytest -q` 的测试；应用导入/收集之前设临时运行根并清凭证。pyproject 的 testpaths 同时包含 `tests` 和 `deeptutor/learning/tests`，临时 bootstrap helper 也须显式传两个路径。还要分别运行 web Node 测试脚本、整站 tsc、ruff 与 diff 检查。使用 phase1 snapshot 工具核验源代码范围、可重建归档和六棵受保护数据树；数据仅允许不透明 hash 比较，禁止读取 settings/memory 内容。执行失败返回对应卡修复，不删测试或扩大脚本权限。

P1-50 需要实际 bwrap 路径证明，而不是 SYSTEM 字样、mock backend 或已有条件测试的 skip。以临时数据构造合法正例和只改变单一边界的反例，验证宿主/别 run 读取、外写和 localhost 网络均被拒绝，timeout 清理整个进程组，真实 matplotlib 中文 PNG 通过验证，ODE 数值样本由可信父进程重算。缺 bwrap/字体/环境时记录 blocked_environment，不安装或改系统。

## 复用接缝与限制

- pytest 全量保护由根 `tests/conftest.py` 的真实 owner secret 写入守卫提供；phase1 `p1_runtime` 通过 `isolated_runtime` 使用临时运行根，默认网络隔离由 `block_external_network` 提供。`full_lifespan_probe` 可启动一个临时 HOME 子进程。注意 phase1 fixtures 是显式引用，不应假设全部自动生效。
- `scripts/phase1_snapshot.py` 已提供源码捕获、允许范围比较、归档重建和真实数据哈希；将它作为验证器的底层，不重复实现会读数据内容的扫描器。归档源排除 data，输出限于证据目录。
- `web/scripts/run-node-tests.mjs` 编译并递归发现 Node 测试，然后运行 Node test runner；它清理生成的 `web/dist/node-tests`。这与独立整站 `tsc --noEmit -p .` 是不同检查。
- `chart_executor` 默认选择真实合格 bwrap 后端；测试专用 backend 注入不能作为本次证明。请求挂载只将当前 run workdir 映射为宿主可写目录，独立 /tmp tmpfs 可写正常；运行环境有独立 HOME/MPL cache。健康检查和 proof 要以运行行为为依据。
- worker 在执行模型脚本前对进程设 hard limits，并让父进程控制墙钟和进程组；现契约说明 CPU/内存 RLIMIT 是进程级，不能写成整棵进程树累计限额。PNG 由 Pillow 严格解码、像素限制并绑定当前 attempt；ODE 只校验固定样本，不是形式化数学证明。
- `report_store` 的 report run 先注册活动状态并建私有目录，失败不会公开 URL，成功时校验后发布并释放活动锁。验收应把执行、产物校验和发布生命周期分开观察。
- P33 有真实 bwrap boundary、matplotlib PNG 和 ODE 示例，同时包含 fake backend 测试；P34 覆盖跨 run PNG 拒绝及五点 ODE；P35 多数编排案例使用 fake executor，另有 Typst 产物例子。不能把这些历史单测或 mock 结果冒充本阶段真实 OS 验收。

## 文件 SHA-256

### 阶段范围现存文件

| 文件 | SHA-256 | 字节 |
|---|---|---:|

### 只读参考

| 文件 | SHA-256 | 字节 |
|---|---|---:|
| `plans/phase1/stages/S13.md` | `c027fb8c2843a0590446449373690b1aa7c5468a7aad2fafe0d32099117ced88` | 3218 |
| `plans/phase1/cards/P1-49.md` | `ff435d578de3d18ed174c54932de6d3d611fb9c8db306bf82cbc0cc1ba843c30` | 4801 |
| `plans/phase1/cards/P1-50.md` | `6c37464e67bec1ce2a598ac005f0a96fcac7b937927c9fb476ff0de729eefbd6` | 4197 |
| `plans/phase1/FRAMEWORK.md` | `9190d8ad2f513a1fef09020c98d6bd8816274834cf9a2d8c75abae6397cc77f1` | 10573 |
| `plans/phase1/EXECUTION_GUIDE.md` | `eb688596ef5409a2b1c6dcbc92d4f30304102bb0a176df21d0ea375b30acb03e` | 2575 |
| `plans/phase1/STAGE_WORKFLOW.md` | `34f378797cde73adbcebd856ad37a7c6bd3b408aba68903a22997d2ac88745b0` | 9143 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | 31470 |
| `pyproject.toml` | `25e77bb50f30ee18891f1d186d3551cd1ad684c8aab1eb47060c4ee4ffd35337` | 16482 |
| `tests/conftest.py` | `511bfdafa2e19026ef5a85d4d3ee9cc611a4963f737b504a96ba5167a16fa4bd` | 7649 |
| `tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | 2376 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 49819 |
| `tests/phase1/test_p1_00.py` | `2e018fb0d756bb061ec29c0203321801b713f767812190d70562909a26e70e63` | 29538 |
| `tests/phase1/test_p1_33.py` | `164584aeff514b1319b941cacd5048e86e454a39b6c705613b4e79952cad8871` | 53760 |
| `tests/phase1/test_p1_34.py` | `994d06bd55d95701f06340f4f0c29f6924440622d866efb750d9d3e658b73d88` | 31535 |
| `tests/phase1/test_p1_35.py` | `862ac3606061d130cf0e5c712ab41508d323c8753158889663edadaa135ecff3` | 22331 |
| `tests/runtime/test_launcher.py` | `3730f1de6ed3d9c848635749348670ca530e3ca90b4c2ffae7f59eb1b49f961a` | 17560 |
| `deeptutor/learning/tests/test_policy.py` | `712f2300b76ef140186176d0ebbdd13c3549b001ebb9be6eebae055cda812be0` | 10621 |
| `scripts/phase1_snapshot.py` | `7dcaf3d0228a12f057698205f7b8152eaaa84c489ed8ce36508ed794c3ed7c7c` | 40898 |
| `web/scripts/run-node-tests.mjs` | `f67c84ce249ae9cfa6607038f6be0cad0a8428aa90186df0dcc69f8870681f74` | 1496 |
| `web/tsconfig.node-tests.json` | `b9ceadd1d99e85ff0652717f4d4635437da15cbc51dc27864ced18ba0d06ebec` | 317 |
| `web/tsconfig.json` | `f674863c7ab4895c97210a22291ee0adfb373014f39134aa4f15bcffa2745a25` | 715 |
| `deeptutor/services/pdf/chart_executor.py` | `3431a2d98c269d844ecbd142e2f6396f44207c007cd301c7e5bbcb55dcf75a63` | 57711 |
| `deeptutor/services/pdf/chart_worker.py` | `b8c9e8b0606379664e4c4127356dfb41829ccb096558fb4d2ad4cc908bd6fea4` | 20674 |
| `deeptutor/services/pdf/chart_validation.py` | `3d71c01ef23fa803c2e4a8a0b6a2d42004531ce60f37dd33e0adaa67ffd2f20a` | 11377 |
| `deeptutor/services/pdf/report_store.py` | `585978c06d9746295f7a90b93ffd5e44dd33aeb337b9fa98eae313e37b22a348` | 49515 |
| `deeptutor/services/pdf/report.py` | `e8a9cfe54b34602e0dc279fcc357b813e2a188551343bd0b0c256f3d7dedcebf` | 32557 |
| `tests/phase1/test_p1_47.py` | `5afb61371cb6068cd6d2c9fcee393e208a6ff4453d7f45e15894be6408c71431` | 12923 |
| `plans/phase1/ENVIRONMENT.md` | `582d9d3faa36eafd22910934390bf6e8a645b9334ed34d118e4e2603867ddd38` | 3617 |

## 定位片段

### 1. `plans/phase1/stages/S13.md:1-1`（定位词 `# S13`）

```text
# S13：全量回归及真实沙箱验收
```

### 2. `plans/phase1/stages/S13.md:9-9`（定位词 `P1-49`）

```text
完成 全量回归及真实沙箱验收 的现有修复，契约 C11, C14。P1-49覆盖完整testpaths与所有离线门；P1-50覆盖真实bwrap及报告失败发布链。历史Node403/459只属旧基线，最新S11-final为477，必须实际收集。
```

### 3. `plans/phase1/stages/S13.md:9-9`（定位词 `P1-50`）

```text
完成 全量回归及真实沙箱验收 的现有修复，契约 C11, C14。P1-49覆盖完整testpaths与所有离线门；P1-50覆盖真实bwrap及报告失败发布链。历史Node403/459只属旧基线，最新S11-final为477，必须实际收集。
```

### 4. `plans/phase1/stages/S13.md:36-39`（定位词 `blocked_environment`）

```text
- 阶段report.json包含各卡结果、实际命令/退出码/日志定位、scope与data检查、限制；不得为凑文件再生成每卡长报告。
- scope_check按本阶段白名单并集，真实数据/前人修复保持；交付状态verified_local，accepted只由独立审阅者写review.json。
- 真实OS/浏览器不足如实blocked_environment，不以skip或fake backend替代；不得自动安装、升级、使用真实供应商。
- 阶段内无需请求下一张卡批准；阶段末停止，等待阶段review。跨范围/契约/真实数据/环境问题才提交阻塞。
```

### 5. `plans/phase1/cards/P1-49.md:1-7`（定位词 `# P1-49`）

```text
# P1-49：运行第一阶段离线全量与差异验收

状态：planned；类型：gate；审阅风险：gate。依赖：P1-00, P1-01, P1-02, P1-03, P1-04, P1-05, P1-06, P1-07, P1-08, P1-09, P1-10, P1-11, P1-12, P1-13, P1-14, P1-15, P1-16, P1-17, P1-18, P1-19, P1-20, P1-21, P1-22, P1-23, P1-24, P1-25, P1-26, P1-27, P1-28, P1-29, P1-30, P1-31, P1-32, P1-33, P1-34, P1-35, P1-36, P1-37, P1-38, P1-39, P1-40, P1-41, P1-42, P1-43, P1-44, P1-45, P1-46, P1-47, P1-48, P1-54, P1-55, P1-56。

## 目标

从完整testpaths、前端、类型、lint、允许范围和真实数据保护证明单元修复可集成。
```

### 6. `plans/phase1/cards/P1-49.md:32-40`（定位词 `完整pytest`）

```text
## 执行步骤

1. 可直接执行 `./.venv/bin/python scripts/phase1_verify.py`；内部运行完整pytest（tests和deeptutor/learning/tests）、node/整站tsc/业务及新增脚本ruff、diff与历史evidence/最新receipt合法性检查，记录真实argv/cwd/UTC/exit/输出。应用导入前临时home与可信默认配置，清真实凭证，限定网络；不使用相关目录默认参数冒充全量。
2. 核验baseline增量只包含各卡allowed范围；删除/skip测试仅限定44/45的removed-feature断言。
3. 复核六真实树hash/权限/锁不变，秘密未进source/evidence；145前置源码只读，capture147；精确路径escape避免glob漏检。验证源码恢复归档，历史源码哈希按后续授权覆盖解释，不改旧receipt。不自动fix业务失败。必要子命令失败、越界变化、缺OS必需证据均有安全坏对照证明门禁拒绝伪绿。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：
```

### 7. `plans/phase1/cards/P1-49.md:44-52`（定位词 `六科学习/产物/settings hash保持`）

```text
- [ ] tsc/ruff/diffcheck通过
- [ ] 越界修改能被scope检查拒绝
- [ ] 六科学习/产物/settings hash保持

执行命令（从项目根开始；带 cd web 的条目为独立命令，不延续前一条 cwd）：

```bash
./.venv/bin/python -m pytest -q
cd web && node ./scripts/run-node-tests.mjs
```

### 8. `plans/phase1/cards/P1-50.md:1-7`（定位词 `# P1-50`）

```text
# P1-50：真实OS沙箱与图表安全验收

状态：planned；类型：gate；审阅风险：gate。依赖：P1-33, P1-34, P1-35。

## 目标

以真实正常PNG与恶意边界用例证明隔离，不以fake backend替代。
```

### 9. `plans/phase1/cards/P1-50.md:5-13`（定位词 `以真实正常PNG与恶意边界用例证明隔离`）

```text
## 目标

以真实正常PNG与恶意边界用例证明隔离，不以fake backend替代。

## 已有问题证据

SYSTEM等级不等于逐任务目录隔离；原subprocess已可写出报告目录。

## 必读输入
```

### 10. `plans/phase1/cards/P1-50.md:35-43`（定位词 `blocked_environment`）

```text
2. 验证读另一科/另一run/宿主fake配置、写越界、联网到localhost探针均失败；不使用真实密钥。
3. 验证有限子/孙进程的短超时清理、真实CPU/AS/FSIZE/CORE进程级硬限制、安全小上限超限、输出截断、中文字体与可信五点ODE；禁止fork bomb/宿主OOM，不宣称进程树累计cgroup配额。沙箱内部/tmp可写不等于宿主越界；canary和listener必须先有合法正例且探针确实执行。
4. 执行失败须进入真实report.generate_report编排/发布链验证无正式PDF/公开URL、旧产物不变和活动状态释放；仅LLM可用确定性fake，执行/PNG/发布不可fake。bwrap/字体等不足写blocked_environment并非零退出，不把pytest.skip当通过。

## 证据：如何证明完成

以下必须成为独立的行为断言/场景；至少记录输入、预期、实际和对应测试名，不能只断言源码字符串或helper被调用：

- [ ] 真实有效PNG/中文正常
```

### 11. `plans/phase1/FRAMEWORK.md:41-49`（定位词 `阶段内串行完成`）

```text
任务卡通常只有一个行为目标，修改 1–3 个生产文件、1 个主要测试文件。存储、响应契约等共同依赖先独立实现，业务卡只接入；相互共享大文件的卡必须串行。单元的确定性来自精确输入/输出与反例，而不是“改了几行”。

每张卡独立列目标、已有证据、读取入口、允许文件与符号范围、执行步骤、测试命令、完成条件和禁止事项。卡上的依赖是必需前置，不允许为了省事跨卡实施。一个会话执行一个已授权阶段（2–6张卡）；阶段内串行完成，阶段结束一次独立审查。小卡保持编码粒度，禁止自由选阶段外任务。批改与模型解析、数据写入分开；科目作用域编码与聊天接线、检索接入分开；报告目录、沙箱、图像验证、编排、接口、核查分开。

约250行现作为阶段复杂度提醒，不机械触发人工补卡；文件范围/目标或契约确需扩大时才blocked_scope。阶段内已授权单元为集成需要作小修可以直接实现并复测。禁止顺手重构、全仓格式化、机械删所有 MCP/book/partner 字符串。

## 5. 执行与验收顺序

所有单元和依赖在tasks.json；stages.json定义阶段顺序与阶段内单元顺序，dispatch_order已同步展开。默认一名执行者串行按阶段工作，阶段边界才人工交接，不能按卡编号盲跑。若调度者以后使用并行执行，必须同时满足依赖已验收和 allowed_files/符号范围不重叠；不要让多个 agent 同时改 subjects.py、agentic_pipeline.py、builtin/__init__.py 或同一测试文件。
```

### 12. `plans/phase1/FRAMEWORK.md:54-62`（定位词 `G3：离线全量`）

```text
| G1：共同契约 | 错误、生成、存储、KB 标识基础卡通过；C01–C08 的反例测试通过 | 对应基础未通过时阻塞其消费者；无关工作流可继续 |
| G2：功能单元 | 00–48 及 54–56 的适用卡完成；批改、考点、上传、检索、报告、导出均有行为证据 | 不进入最终集成 |
| G3：离线全量 | P1-49/51/52/53 通过；Python/frontend/tsc/范围检查和跨入口用例通过 | 不宣称阶段完成 |
| G4：报告执行边界 | P1-50 使用真实 OS 沙箱验证正常出图、路径/网络/环境拒绝、超时和跨任务隔离 | 状态 blocked_environment；mock 通过不能替代 |
| G5：阶段签收 | 高风险卡由主审阅者检查实际 diff 和 G3/G4 证据，真实数据哈希未变化，交接记录完整 | 仅可标“已实现待验收” |

阶段总体完成要 G0–G5 全部通过。高风险审阅集中在跨科作用域、原子/并发存储、材料一致性、报告隔离/路径、导出排除范围；任务卡可由暂定 DeepSeek v4.1 flash 完成实现，阶段主审阅使用用户认可的审阅者。执行器不得自行更换模型/派遣其他 agent。

真实供应商 LLM/embedding/STT 可做额外抽样，但默认验收不消耗供应商额度。Stub 与真实调用必须在证据中区分。真实 provider 未验证应在最终报告列出，不声称在线性能/识图精度已保证；如果要签收真实 provider 兼容性，需另附真实调用验收证据。
```

### 13. `plans/phase1/FRAMEWORK.md:55-63`（定位词 `G4：报告执行边界`）

```text
| G2：功能单元 | 00–48 及 54–56 的适用卡完成；批改、考点、上传、检索、报告、导出均有行为证据 | 不进入最终集成 |
| G3：离线全量 | P1-49/51/52/53 通过；Python/frontend/tsc/范围检查和跨入口用例通过 | 不宣称阶段完成 |
| G4：报告执行边界 | P1-50 使用真实 OS 沙箱验证正常出图、路径/网络/环境拒绝、超时和跨任务隔离 | 状态 blocked_environment；mock 通过不能替代 |
| G5：阶段签收 | 高风险卡由主审阅者检查实际 diff 和 G3/G4 证据，真实数据哈希未变化，交接记录完整 | 仅可标“已实现待验收” |

阶段总体完成要 G0–G5 全部通过。高风险审阅集中在跨科作用域、原子/并发存储、材料一致性、报告隔离/路径、导出排除范围；任务卡可由暂定 DeepSeek v4.1 flash 完成实现，阶段主审阅使用用户认可的审阅者。执行器不得自行更换模型/派遣其他 agent。

真实供应商 LLM/embedding/STT 可做额外抽样，但默认验收不消耗供应商额度。Stub 与真实调用必须在证据中区分。真实 provider 未验证应在最终报告列出，不声称在线性能/识图精度已保证；如果要签收真实 provider 兼容性，需另附真实调用验收证据。

```

### 14. `plans/phase1/EXECUTION_GUIDE.md:10-18`（定位词 `阶段report.json`）

```text
阶段内按指定卡顺序实现、定向测试和自修，完成一单元不询问下一卡，不重新阅读57卡或另写全项目计划。
限定阶段白名单并集和卡目标；不提交、不调用真实供应商、不动真实配置/数据、不做第二阶段功能。
只保留阶段report.json和共享追加日志，按C14和StageReport schema记录各单元结果与实际命令。
阶段结束停止，由协调者一次独立复核；不自行执行下阶段或标accepted。
```

当前待执行阶段以stages.json的next_stage与最新签收receipt为准，具体指令见对应START_Sxx.txt；原START_P1_00.txt/旧审查报告是历史记录。

## 必须保持的约束
```

### 15. `plans/phase1/EXECUTION_GUIDE.md:22-29`（定位词 `数据读取允许保护程序不透明二进制流哈希`）

```text
- tests/phase1夹具须隔离PathService、用户roots、manager/catalog缓存，并恢复；外网stub，不能使用真实密钥。
- 测试缓存可产生，但不覆盖生产.next/.next-deeptutor，浏览器用临时源码副本及独立dist。
- 数据读取允许保护程序不透明二进制流哈希；不解析/展示/复制settings中的密钥，不用真实供应商。
- 有效反例先证明其他字段合法；安全诊断不回显输入；类型边界、权限和失败bytes必须真正观察。
- 普通实现选择自主做，不重复要开始/继续批准；范围/契约/真实数据/环境阻塞才报告准确缺项。
- 阶段默认3个主要证据文件，日志仅追加。旧单卡completion和失败日志不删不改，历史合法skip保留。

命令行已有dsh --profile headless的基本形式，但本包不猜model id或设置Harness profile；可在用户已有Web界面按当前项目目录粘贴START_S01。项目AGENTS.md适用于selflearn，不把Harness仓库的pnpm规则移植进来。
```

### 16. `plans/phase1/STAGE_WORKFLOW.md:34-42`（定位词 `StageReport`）

```text
另加必要的source/data基线和一个阶段完成source归档；不为每条断言、每次检查、每卡反复建目录。先前P1-00的原始证据保持不变，新的协调者修补在reviews/P1-00，不覆盖原completion或失败日志。

report.json内card_results记录卡ID、verified_local/blocked、目标是否达成、修改文件、满足的完成条件、测试名和日志定位；直接复用命令记录，不强制每卡completion.json。历史Completion schema和单卡证据仍可读；新阶段使用StageReport schema。

日志是原命令输出，不是事后写一行“pytest→0”。去掉真实密钥，不删除失败尝试；返修只追加修订记录和复测。大二进制只存一次，其hash列入report，不把同一snapshot复制成多份证明。协调用review.json完成签收，不再同时写开工说明/补修说明/最终验收四份重复文件。

## 4. 反馈必须成为可执行检查

| 已重复出现的缺陷 | 执行者必须做的检查 | 协调者复核 |
```

### 17. `plans/phase1/STAGE_WORKFLOW.md:28-36`（定位词 `execution.log`）

```text
```text
.phase1-evidence/stages/Sxx/report.json      阶段汇总与各单元结果
.phase1-evidence/stages/Sxx/execution.log    命令、时间、原始输出、实际exit code；仅追加
.phase1-evidence/stages/Sxx/review.json      协调者审查、补修、当前源码hash和签收
```

另加必要的source/data基线和一个阶段完成source归档；不为每条断言、每次检查、每卡反复建目录。先前P1-00的原始证据保持不变，新的协调者修补在reviews/P1-00，不覆盖原completion或失败日志。

report.json内card_results记录卡ID、verified_local/blocked、目标是否达成、修改文件、满足的完成条件、测试名和日志定位；直接复用命令记录，不强制每卡completion.json。历史Completion schema和单卡证据仍可读；新阶段使用StageReport schema。
```

### 18. `plans/phase1/STAGE_WORKFLOW.md:19-27`（定位词 `blocked_environment`）

```text
5. 相同阶段内的已通过单元可以为真实集成失败作必要修正，记录返修原因和关联回归；不把它标成跨范围阻塞。需要改不在阶段并集内的生产文件或改变数据契约时，才blocked_scope。
6. 250行是最初拆卡评估提醒，现改为阶段复杂度预警，不能机械截断、压缩长行或新造补卡税。预计一个阶段变成架构重写或无法独立验证，应给协调者一个最小拆分建议；范围和验收不能被行数替代。
7. 缺真实沙箱/浏览器时记录blocked_environment；不能通过skip/fake结果声称验收完成。无环境依赖的实现单元仍可在本阶段内完成并如实报告。
8. 阶段内安全/真实数据保护失败立即停；普通失败先自修。阶段末只有一次对外汇报，等待协调者复核。不提交/推送/升级、不启动真实服务、不调用真实供应商，不处理第二阶段新功能。

## 3. 最少证据文件

每阶段默认只保留三个主要文件：

```

### 19. `plans/phase1/DATA_CONTRACTS.md:132-140`（定位词 `## C11：报告、执行与产物`）

```text
知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
```

### 20. `plans/phase1/DATA_CONTRACTS.md:183-191`（定位词 `## C14：证据与阶段验收`）

```text
- 新部署文档不建议安装已删伙伴功能；历史迁移说明和 UPSTREAM.md/assets/README 上游存档保持原样。AGENTS.md 标当前 fork 差异或同步最小命令表，不把源上游全文视为本项目运行清单。

## C14：证据与阶段验收（2026-10-11修订）

每张小卡仍需正向和独立反向行为证据；合法负例从已证明有效的base只改一个字段/故障点。高风险用一个针对性坏对照确认断言捕获真实效果，禁止只看源码contains或mock自证。该义务不要求每卡交付一份独立人工报告。

每阶段一个执行会话，阶段内按stages.json既定顺序串行卡。报告/审查为阶段粒度，规则见STAGE_WORKFLOW.md。新阶段使用StageReport schema：stage_id/status/baseline_id/card_results/commands/scope_check/real_data_unchanged/limitations。card_results含卡ID、目标、修改路径、断言、命令定位和限制；commands保存实际命令、cwd、exit、共享execution.log行号，不能只写摘要“通过”。

单元状态verified_local表示本地验证；阶段末由协调者独立复核并写review.json的accepted，执行者不能自签。历史P1-00/completion.json保持原样，协调修补/签收另存reviews/P1-00；旧Completion schema继续兼容明确单卡调用，不强制后续每卡创建文件。
```

### 21. `pyproject.toml:397-405`（定位词 `testpaths = ["tests", "deeptutor/learning/tests"]`）

```text
# ============================================
[tool.pytest.ini_options]
testpaths = ["tests", "deeptutor/learning/tests"]
pythonpath = ["."]
markers = [
    "asyncio: mark async tests that require pytest-asyncio",
]
asyncio_default_fixture_loop_scope = "function"
addopts = [
```

### 22. `pyproject.toml:402-410`（定位词 `asyncio_default_fixture_loop_scope`）

```text
    "asyncio: mark async tests that require pytest-asyncio",
]
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "--strict-markers",
    "--strict-config",
    "--disable-warnings",
    "--tb=short",
    "--import-mode=importlib",
```

### 23. `tests/conftest.py:19-27`（定位词 `def _tree_snapshot`）

```text


def _tree_snapshot(root: Path) -> frozenset[str]:
    if not root.is_dir():
        return frozenset()
    return frozenset(str(path) for path in root.rglob("*") if path.is_file())


#: Captured at import time — before any test can monkeypatch the roots — so the
```

### 24. `tests/conftest.py:46-54`（定位词 `def _guard_real_owner_secrets`）

```text

@pytest.fixture(autouse=True)
def _guard_real_owner_secrets():
    """A test must never write into the real per-account state trees.

    These hold OAuth refresh tokens, MCP credentials, and which CLI apps are
    installed. A test that redirects ``ADMIN_WORKSPACE_ROOT`` but forgets
    ``SYSTEM_ROOT`` — or that calls ``monkeypatch.undo()`` and so reverts a
    fixture's redirection — lands here, and without this guard the failure is
```

### 25. `tests/conftest.py:72-80`（定位词 `def _guard_legacy_multi_user_migration`）

```text

@pytest.fixture(autouse=True)
def _guard_legacy_multi_user_migration(monkeypatch):
    """Tests must never migrate the developer's real ``multi-user/`` tree.

    ``migrate_legacy_multi_user_tree`` runs on the auth/grants/workspace read
    paths, so any test that exercises those without full path isolation would
    otherwise move a real sibling ``multi-user/`` into ``data/``. Point the
    legacy root at a path that cannot exist and reset the once-flag;
```

### 26. `tests/phase1/conftest.py:26-34`（定位词 `def p1_runtime`）

```text

@pytest.fixture
def p1_runtime(tmp_path: Path) -> Iterator[Path]:
    """重定向运行数据根到 tmp 的 admin root，并默认启用外网拦截。"""
    with helpers.isolated_runtime(tmp_path) as admin_root:
        yield admin_root


@pytest.fixture
```

### 27. `tests/phase1/conftest.py:71-76`（定位词 `def p1_route_client`）

```text

@pytest.fixture
def p1_route_client(p1_runtime: Path) -> Iterator[object]:
    """在当前隔离作用域内创建的真实科目路由客户端；退出即关闭。"""
    with helpers.route_client() as client:
        yield client
```

### 28. `tests/phase1/helpers.py:507-515`（定位词 `def isolated_runtime`）

```text

@contextlib.contextmanager
def isolated_runtime(
    tmp_path: Path,
    *,
    guard_network: bool = True,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
    **kwargs: Any,
```

### 29. `tests/phase1/helpers.py:887-895`（定位词 `def block_external_network`）

```text

@contextlib.contextmanager
def block_external_network(
    *,
    allow_endpoints: Iterable[tuple[str, int]] = (),
    allow_unix_paths: Iterable[str] = (),
) -> Iterator[frozenset[tuple[str, int]]]:
    """拦截未声明的 TCP/UDP/DNS 出口。

```

### 30. `tests/phase1/helpers.py:1219-1227`（定位词 `def full_lifespan_probe`）

```text


def full_lifespan_probe(timeout: float = 60.0) -> dict[str, Any]:
    """在独立子进程中用 tmp home 启停真实 lifespan，返回诊断字典。

    子进程在 import/startup **之前**就设定 ``DEEPTUTOR_HOME`` 与假配置；不写
    ``HOME``/``CODEX_HOME``，不读取真实凭证。
    """
    proc = subprocess.run(
```

### 31. `tests/phase1/test_p1_00.py:123-131`（定位词 `def test_dirty_untracked_and_deleted_sources_rebuild_exactly`）

```text
# 1. 可准确重建
# ---------------------------------------------------------------------------
def test_dirty_untracked_and_deleted_sources_rebuild_exactly(synth_repo, tmp_path):
    root = synth_repo
    before = SNAP.capture(root, "synthetic-before")
    archived = before["archived_files"]

    # dirty 文件按工作树内容归档，而不是 HEAD 内容
    head_sha = hashlib.sha256(SNAP.git(root, "show", "HEAD:src/app.py")).hexdigest()
```

### 32. `tests/phase1/test_p1_00.py:479-487`（定位词 `def test_scope_glob_only_allows_matching_direct_files`）

```text


def test_scope_glob_only_allows_matching_direct_files():
    assert SNAP.allowed_hit("deeptutor/subjects/store.py", ["deeptutor/subjects/*.py"])
    assert not SNAP.allowed_hit("deeptutor/subjects/nested/rogue.py", ["deeptutor/subjects/*.py"])
    assert not SNAP.allowed_hit("other/deeptutor/subjects/store.py", ["deeptutor/subjects/*.py"])


def test_scope_detects_git_head_change(synth_repo):
```

### 33. `tests/phase1/test_p1_33.py:139-147`（定位词 `def test_only_the_current_run_workdir_is_a_writable_mount`）

```text
# 策略向量：mounts / env / argv / limits
# ---------------------------------------------------------------------------
def test_only_the_current_run_workdir_is_a_writable_mount(p1_run: rs.ReportRun) -> None:
    request = ce.plan_chart_request(p1_run, "chart_1.png")

    writable = [mount for mount in request.mounts if not mount.read_only]
    assert len(writable) == 1
    assert writable[0].host_path == str(p1_run.workdir)
    assert writable[0].sandbox_path == str(p1_run.workdir)
```

### 34. `tests/phase1/test_p1_33.py:561-569`（定位词 `def test_real_sandbox_boundary_probe`）

```text


def test_real_sandbox_boundary_probe(p1_run: rs.ReportRun) -> None:
    """真实 bwrap：在沙箱内探测挂载/环境/网络（受控边界，不是 OS 验收）。"""
    worker = Path(ce.__file__).resolve().with_name(ce.WORKER_FILENAME)
    repo_file = Path(ce.__file__).resolve()
    worker_before = _sha256(worker)
    probe = f"""
import json, os, socket, sys
```

### 35. `tests/phase1/test_p1_33.py:642-650`（定位词 `def test_real_sandbox_runs_matplotlib_and_reports_the_artifact`）

```text


def test_real_sandbox_runs_matplotlib_and_reports_the_artifact(p1_run: rs.ReportRun) -> None:
    code = (
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [3, 2, 1])\n"
        "plt.title('P1-33')\n"
```

### 36. `tests/phase1/test_p1_33.py:666-674`（定位词 `def test_real_sandbox_ode_check_uses_the_same_executor`）

```text


def test_real_sandbox_ode_check_uses_the_same_executor(p1_run: rs.ReportRun) -> None:
    script = (
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "def f(x, y):\n    return x**2 - y\n"
        "open('chart_1.png', 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n')\n"
    )
    _run(ce.execute_chart_code(script, run=p1_run, expected_png="chart_1.png"))
```

### 37. `tests/phase1/test_p1_34.py:131-139`（定位词 `def test_valid_current_png_passes`）

```text
# 正例与基本属性
# ---------------------------------------------------------------------------
def test_valid_current_png_passes(p1_run: rs.ReportRun) -> None:
    result = _execute(p1_run, _chart_code())
    assert result.ok is True

    entry = cv.validate_chart_output(p1_run, "chart_1.png")

    target = p1_run.workdir / "chart_1.png"
```

### 38. `tests/phase1/test_p1_34.py:171-179`（定位词 `def test_another_runs_image_is_not_this_runs_output`）

```text


def test_another_runs_image_is_not_this_runs_output(p1_subject) -> None:
    first = rs.create_report_run(p1_subject.subject_id)
    second = rs.create_report_run(p1_subject.subject_id)
    _write_artifact(first, _png_bytes())

    with pytest.raises(SubjectOperationError) as info:
        cv.validate_chart_output(second, "chart_1.png")
```

### 39. `tests/phase1/test_p1_34.py:348-356`（定位词 `def test_ode_five_points_pass_and_status_is_numeric_only`）

```text
# ODE：走 P33 的执行器 + 真实 validation
# ---------------------------------------------------------------------------
def test_ode_five_points_pass_and_status_is_numeric_only(p1_run: rs.ReportRun) -> None:
    _execute(p1_run, _chart_code(expression="x**2 - y"))

    outcome = _run(cv.check_ode_numeric(p1_run, "x**2 - y"))

    assert outcome["status"] == rs.VERIFICATION_PASSED
    assert outcome["points"] == 5
```

### 40. `tests/phase1/test_p1_35.py:309-317`（定位词 `def test_any_declared_chart_failure_fails_the_whole_report`）

```text
# 失败：整体失败、无 URL、旧报告不变
# ---------------------------------------------------------------------------
def test_any_declared_chart_failure_fails_the_whole_report(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:柱状图}\n"
    stub.chart_response = '{"code": [1, 2]}'
    stub.install(monkeypatch)
```

### 41. `tests/phase1/test_p1_35.py:401-409`（定位词 `def test_sandbox_unavailable_is_reported_without_retry_or_host_fallback`）

```text


def test_sandbox_unavailable_is_reported_without_retry_or_host_fallback(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    stub.default_body = "# 报告\n{CHART:图}\n"
    stub.execute_error = "sandbox_unavailable"
    stub.install(monkeypatch)
```

### 42. `tests/phase1/test_p1_35.py:542-550`（定位词 `def test_real_typst_chinese_with_image_is_openable`）

```text


def test_real_typst_chinese_with_image_is_openable(
    subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image, ImageDraw, ImageFont
    import pymupdf

    font = Path(report_mod.__file__).resolve().parents[3] / "tools" / "fonts" / "msyh.ttc"
```

### 43. `tests/runtime/test_launcher.py:50-58`（定位词 `def test_start_does_not_create_nested_data_tree`）

```text


def test_start_does_not_create_nested_data_tree(monkeypatch, tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    bad_home = package_root / "data" / "user"
    monkeypatch.setattr("deeptutor.runtime.home.PACKAGE_ROOT", package_root)
    monkeypatch.setattr(launcher, "get_runtime_home", lambda _home=None: bad_home)

    with pytest.raises(SystemExit, match="Invalid DeepTutor runtime home"):
```

### 44. `tests/runtime/test_launcher.py:428-436`（定位词 `def test_start_uses_ipv4_loopback_for_frontend_proxy`）

```text

@pytest.mark.parametrize("resolved_backend_port", [8001, 8123])
def test_start_uses_ipv4_loopback_for_frontend_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolved_backend_port: int,
) -> None:
    from deeptutor.services import config as config_module
    from deeptutor.services import setup as setup_module
```

### 45. `deeptutor/learning/tests/test_policy.py:44-52`（定位词 `def test_`）

```text


def test_memory_gate_requires_high_quantitative_mastery():
    kp = _kp("kp1", KnowledgeType.MEMORY)
    progress = _progress(kp)
    progress.mastery_levels["kp1"] = 0.8
    assert policy.is_mastered(progress, kp) is False
    progress.mastery_levels["kp1"] = 0.9
    assert policy.is_mastered(progress, kp) is True
```

### 46. `scripts/phase1_snapshot.py:172-180`（定位词 `def scan_tree`）

```text


def scan_tree(root: Path, *, exclude: bool = True) -> tuple[dict[str, dict], list[str]]:
    """返回 (文件条目, 目录列表)，覆盖 root 下所有未被排除的路径。

    符号链接按目标记录且不下钻；不可读文件直接抛错而不是跳过。
    """
    files: dict[str, dict] = {}
    dirs: list[str] = []
```

### 47. `scripts/phase1_snapshot.py:344-352`（定位词 `def capture`）

```text


def capture(root: Path, label: str, *, include_paths=()) -> dict:
    """记录完整基线：归档清单 + 更宽的监控清单 + 删除清单。"""
    if not (root / ".git").exists():
        raise RuntimeError(f"not a git worktree: {root}")
    head = git_head(root)
    tracked = git_tracked(root)
    tracked_set = set(tracked)
```

### 48. `scripts/phase1_snapshot.py:439-447`（定位词 `def build_archive`）

```text
# archive / verify-rebuild
# --------------------------------------------------------------------------
def build_archive(root: Path, baseline: dict, out: Path) -> dict:
    """写出确定性 tar.gz。

    归档内容取自**当前工作树**，因此每个条目都会先与 capture 时记录的
    sha256/size 比对：如果文件在 capture 之后被改动过，这里直接失败，
    而不是产出一个与 manifest 不符的归档。失败时不留下半成品，也不改动原树。
    """
```

### 49. `scripts/phase1_snapshot.py:666-674`（定位词 `def protect_data`）

```text


def protect_data(root: Path) -> dict:
    roots = {name: protect_one(root, rel) for name, rel in PROTECTED_DATA_ROOTS.items()}
    supplementary = {
        name: protect_one(root, rel) for name, rel in SUPPLEMENTARY_DATA_ROOTS.items()
    }
    core = json.dumps(roots, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
```

### 50. `scripts/phase1_snapshot.py:792-800`（定位词 `def compare(`）

```text
# compare
# --------------------------------------------------------------------------
def compare(before: dict, after: dict, allowed: list[str]) -> dict:
    if before.get("root") != after.get("root"):
        raise ValueError("cannot compare different repository roots")
    b_files = {p: v for p, v in before["monitored_files"].items() if not is_excluded(p)}
    a_files = {p: v for p, v in after["monitored_files"].items() if not is_excluded(p)}
    _validate_entries(b_files)
    _validate_entries(a_files)
```

### 51. `web/scripts/run-node-tests.mjs:21-29`（定位词 `function collectTests`）

```text
}

function collectTests(dir) {
  const entries = readdirSync(dir)
    .map((name) => path.join(dir, name))
    .sort((a, b) => a.localeCompare(b));
  const files = [];
  for (const entry of entries) {
    const stats = statSync(entry);
```

### 52. `web/scripts/run-node-tests.mjs:56-60`（定位词 `"--test"`）

```text
  "-r",
  "./scripts/register-node-test-aliases.cjs",
  "--test",
  ...testFiles,
]);
```

### 53. `web/scripts/run-node-tests.mjs:44-52`（定位词 `"tsconfig.node-tests.json"`）

```text
  path.join(webRoot, "node_modules", "typescript", "bin", "tsc"),
  "-p",
  "tsconfig.node-tests.json",
]);

const testFiles = collectTests(testRoot);
if (testFiles.length === 0) {
  console.error("No compiled node tests found.");
  process.exit(1);
```

### 54. `web/tsconfig.node-tests.json:3-11`（定位词 `"outDir": "./dist/node-tests"`）

```text
  "compilerOptions": {
    "noEmit": false,
    "outDir": "./dist/node-tests",
    "rootDir": ".",
    "baseUrl": ".",
    "module": "commonjs",
    "moduleResolution": "node",
    "incremental": false,
    "paths": {
```

### 55. `web/tsconfig.node-tests.json:13-16`（定位词 `"include": ["tests/**/*.ts"]`）

```text
    }
  },
  "include": ["tests/**/*.ts"]
}
```

### 56. `web/tsconfig.json:5-13`（定位词 `"strict": true`）

```text
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
```

### 57. `web/tsconfig.json:6-14`（定位词 `"noEmit": true`）

```text
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
```

### 58. `deeptutor/services/pdf/chart_executor.py:223-231`（定位词 `class ReportExecutionPolicy`）

```text

@dataclass(frozen=True)
class ReportExecutionPolicy:
    """报告执行的固定策略（服务端构造；模型/工具参数都进不来）。"""

    wall_clock_s: int = 60
    ode_wall_clock_s: int = 30
    cpu_seconds: int = 30
    memory_mb: int = 1536
```

### 59. `deeptutor/services/pdf/chart_executor.py:301-309`（定位词 `class BwrapReportBackend`）

```text


class BwrapReportBackend:
    """报告专用 bubblewrap 后端（窄派生，不修改共享 ``BwrapBackend``）。"""

    name = "bwrap-report"

    def __init__(self, bwrap_path: str | Path | None = None) -> None:
        self._bwrap = str(bwrap_path or shutil.which("bwrap") or "bwrap")
```

### 60. `deeptutor/services/pdf/chart_executor.py:410-418`（定位词 `def select_report_backend`）

```text


def select_report_backend(policy: ReportExecutionPolicy = DEFAULT_POLICY) -> ReportSandboxBackend:
    """报告路径的 backend 选择：显式注入优先，否则只接受真实 bwrap 后端。

    这里**不看**共享 sandbox settings：``RunnerSidecarBackend``/``APPLICATION``/
    ``OFF`` 都不满足逐任务隔离要求，绝不能因为"配置里有别的 backend"就降级执行。
    """
    if policy.backend is not None:
```

### 61. `deeptutor/services/pdf/chart_executor.py:509-517`（定位词 `def _report_mounts`）

```text


def _report_mounts(run: report_store.ReportRun) -> tuple[ReportMount, ...]:
    """唯一可写挂载 = 本次 run 的 workdir；其余全部只读。"""
    workdir = run.workdir
    mounts = [ReportMount(str(workdir), str(workdir), False)]
    mounts.extend(_runtime_read_only_mounts())
    return tuple(mounts)

```

### 62. `deeptutor/services/pdf/chart_executor.py:1049-1057`（定位词 `async def _qualified_backend`）

```text
# 执行入口
# ---------------------------------------------------------------------------
async def _qualified_backend(
    policy: ReportExecutionPolicy,
) -> ReportSandboxBackend:
    """取 backend 并完成证明 + 健康检查；不合格一律 503，不做宿主回退。"""
    backend = select_report_backend(policy)
    proof = _backend_proof(backend)
    if proof is None or not proof.is_qualified():
```

### 63. `deeptutor/services/pdf/chart_executor.py:1332-1340`（定位词 `async def execute_chart_code`）

```text


async def execute_chart_code(
    code: str,
    *,
    run: report_store.ReportRun,
    expected_png: str,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
```

### 64. `deeptutor/services/pdf/chart_executor.py:1385-1393`（定位词 `async def execute_ode_check`）

```text


async def execute_ode_check(
    run: report_store.ReportRun,
    expression: object,
    *,
    points: object,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
```

### 65. `deeptutor/services/pdf/chart_worker.py:160-168`（定位词 `def _set_hard_limits`）

```text
# 资源上限（必须在运行模型脚本之前设置）
# ---------------------------------------------------------------------------
def _set_hard_limits(spec: dict) -> dict:
    cpu_seconds = _require_int(spec, "cpu_seconds", minimum=1, maximum=600)
    memory_mb = _require_int(spec, "memory_mb", minimum=64, maximum=65536)
    max_file_bytes = _require_int(spec, "max_file_bytes", minimum=1024, maximum=1 << 32)
    address_space = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
```

### 66. `deeptutor/services/pdf/chart_worker.py:203-211`（定位词 `def _run_bounded_child`）

```text
# 运行子进程：读取期间即有界
# ---------------------------------------------------------------------------
def _run_bounded_child(
    argv: list[str],
    workdir: str,
    *,
    timeout_s: int,
    tail_chars: int = MAX_TAIL_CHARS,
) -> dict:
```

### 67. `deeptutor/services/pdf/chart_worker.py:427-435`（定位词 `def _ode_mode`）

```text


def _ode_mode(spec: dict, workdir: str) -> int:
    """**可信**父 worker：起不可信子进程取采样，自己算参考值/误差/有限性。"""
    script = _safe_basename(spec.get("script"), "script")
    expression = spec.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise WorkerError("expression 不能为空")
    points = _validate_points(spec.get("points"))
```

### 68. `deeptutor/services/pdf/chart_worker.py:490-498`（定位词 `def main(`）

```text
# 入口
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    started = time.time()
    if len(argv) != 2 or argv[0] not in _MODES:
        _emit(
            {
                "schema": 1,
                "mode": "worker",
```

### 69. `deeptutor/services/pdf/chart_validation.py:135-143`（定位词 `def _decode_png_strict`）

```text


def _decode_png_strict(path: Path, *, max_pixels: int) -> tuple[int, int, str]:
    """Pillow 严格解码：verify + 真实 load；任何警告/炸弹/格式不符都算失败。

    返回 ``(width, height, mode)``。读取有界：先看头部尺寸，超限直接拒绝，不做解码。
    警告处理是**局部**的（``catch_warnings`` + ``error``），不改变进程级过滤状态：
    解码期间的任何警告都说明这张图"有问题"，不能当作合法成功。
    """
```

### 70. `deeptutor/services/pdf/chart_validation.py:167-175`（定位词 `def validate_chart_output`）

```text


def validate_chart_output(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """验证本次 attempt 的 ``expected_png``，返回 ``ReportFile`` 形状的字典。
```

### 71. `deeptutor/services/pdf/chart_validation.py:230-238`（定位词 `async def check_ode_numeric`）

```text


async def check_ode_numeric(
    run: report_store.ReportRun,
    ode_rhs: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """在隔离环境里用固定 5 点检查 ``f`` 与声明表达式的数值一致性。
```

### 72. `deeptutor/services/pdf/report_store.py:242-250`（定位词 `def _register_active`）

```text


def _register_active(
    run: ReportRun, lease: subject_operations.ActivityLease | None = None
) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_RUNS[run.report_id] = (os.getpid(), str(run.staging_dir))
        if lease is not None:
            _ACTIVE_LEASES[run.report_id] = lease
```

### 73. `deeptutor/services/pdf/report_store.py:638-646`（定位词 `def create_report_run`）

```text
# create
# ---------------------------------------------------------------------------
def create_report_run(
    subject_id: str,
    *,
    reviewed_from: str | None = None,
    lease: subject_operations.ActivityLease | None = None,
) -> ReportRun:
    """Every caller, including the synchronous API, owns a validated lease."""
```

### 74. `deeptutor/services/pdf/report_store.py:751-759`（定位词 `def fail_report_run`）

```text


def fail_report_run(run: ReportRun, *, detail: str = "") -> ReportManifest:
    """把本次运行标成 ``failed``（无 URL、无文件）并释放活跃登记。

    已经 ``completed`` 的运行不会被降级覆盖——失败不能抹掉已发布的旧结果。
    """
    run = _require_run(run)
    try:
```

### 75. `deeptutor/services/pdf/report_store.py:949-957`（定位词 `def publish_report_run`）

```text


def publish_report_run(
    run: ReportRun, *, files: Sequence[ReportFile | Mapping[str, Any]], verification_status: str
) -> ReportManifest:
    """Synchronous compatibility API; same validation, copy, and atomic commit.

    Async orchestration uses the internal prepare/commit split so cancellation
    can discard an off-loop copy before any completed metadata/URL is published.
```

### 76. `deeptutor/services/pdf/report_store.py:961-969`（定位词 `def report_url`）

```text


def report_url(manifest: ReportManifest) -> str | None:
    """完成态 manifest 的正式 PDF URL；其它状态一律没有 URL。"""
    if manifest.status != STATUS_COMPLETED:
        return None
    pdf = manifest.file_for_role(ROLE_PDF)
    if pdf is None:
        return None
```

### 77. `deeptutor/services/pdf/report.py:332-340`（定位词 `async def _produce_chart`）

```text
# Chart + ODE execution for one declared figure
# ---------------------------------------------------------------------------
async def _produce_chart(
    run: report_store.ReportRun,
    name: str,
    spec: str,
    ode_expression: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Produce one declared chart; only a complete verified attempt returns.
```

### 78. `deeptutor/services/pdf/report.py:618-626`（定位词 `async def generate_report`）

```text
# Public pipeline
# ---------------------------------------------------------------------------
async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path | None = None,
    ode_rhs: str = "",
```

### 79. `deeptutor/services/pdf/report.py:191-199`（定位词 `def _verify_report_pdf`）

```text


def _verify_report_pdf(path: Path, expected_images: int = 0) -> tuple[int, int]:
    """Require an actually opened PDF with at least one page/image.

    ``typst_compile`` returning ``True`` or a file merely existing is not
    enough: the emitted document must parse, have a page, and (when charts were
    declared) actually embed them.
    """
```

### 80. `tests/phase1/test_p1_47.py:158-166`（定位词 `def test_inherited_cdpath_cannot_redirect_relative_launcher_resolution`）

```text

@pytest.mark.parametrize("via_link", [False, True])
def test_inherited_cdpath_cannot_redirect_relative_launcher_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_link: bool
) -> None:
    repo = make_repo(tmp_path)
    decoy = make_repo(tmp_path, name="decoy-checkout")
    monkeypatch.setenv("CDPATH", str(decoy))
    wrapper = Path("scripts/start_selflearn.sh")
```

### 81. `tests/phase1/test_p1_47.py:317-325`（定位词 `def test_environment_document_records_actual_versions_and_unverified_gaps`）

```text


def test_environment_document_records_actual_versions_and_unverified_gaps() -> None:
    text = (ROOT / "plans" / "phase1" / "ENVIRONMENT.md").read_text(encoding="utf-8")

    assert "3.12.14" in text
    assert re.search(r"\| Node\.js \| `v\d+\.\d+\.\d+`", text)
    assert "environment_observation.json" in text
    assert "environment-observation" in text
```

### 82. `plans/phase1/ENVIRONMENT.md:5-13`（定位词 `## Reproducible observation and provenance`）

```text
the full Python/Node dependency graph.

## Reproducible observation and provenance

The saved observation is
`.phase1-evidence/reviews/S12-final/environment_observation.json`.
Its exact command, output and exit code are recorded under command ID
`environment-observation` in that directory's `execution.log` and `commands.jsonl`.
Run the following from the checkout root to reproduce the observation without
```

### 83. `plans/phase1/ENVIRONMENT.md:25-33`（定位词 `| Node.js |`）

```text
| Interpreter | `/home/albert/selflearn/selflearn/.venv/bin/python` |
| Platform | `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.43` |
| Node.js | `v22.22.1`, executable `/usr/bin/node` |
| Git HEAD | `9723f953cb6ca56f13603f76c5d07e1e2f1f4473` |

The original S12 reply/document claimed Node `v24.22.0`, but its saved command
log contains no Node version observation to substantiate that claim. The
coordinator independently observed `v22.22.1` above; the original worker report
and evidence remain unchanged. This does not establish which executable the
```

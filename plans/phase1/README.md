# 第一阶段修复入口：阶段模式2.1

2026-10-21：S00–S15共16阶段/57张卡已签收，第一阶段关闭。最新结论见 [验收与限制](PHASE1_ACCEPTANCE.md)，后续仅 [只读交接（含已探索文件清单+关键片段）](PHASE1_HANDOFF.txt)。没有S16；第二阶段需用户另行给出需求。S14单项catalog例外继续保留，旧配置未恢复；以下阶段日志为历史。

2026-10-11起按阶段授权与审查。57张小卡作为编码单元保留，合并为16个阶段（S00为已审查的P1-00，后续15个执行阶段），阶段内无需人工逐卡转发。

- [阶段流程与证据规则](STAGE_WORKFLOW.md)
- [阶段机器索引](stages.json) 与 [单元依赖索引](tasks.json)
- [修复框架](FRAMEWORK.md) 与 [数据契约1.1](DATA_CONTRACTS.md)
- [字段Schema](schemas.json) 与 [正/反例](examples.json)
- [执行指南](EXECUTION_GUIDE.md)、[历史S15开工指令](START_S15.txt)及[已探索文件清单+关键片段](S15_EXPLORATION.md)；[历史S14指令](START_S14.txt)及[探索包](S14_EXPLORATION.md)；[历史S13指令](START_S13.txt)及[探索包](S13_EXPLORATION.md)；[历史S12指令](START_S12.txt)及[探索包](S12_EXPLORATION.md)；[历史S11指令](START_S11.txt)及[探索包](S11_EXPLORATION.md)；[历史S10指令](START_S10.txt)及[探索包](S10_EXPLORATION.md)；[历史S09指令](START_S09.txt)及[探索包](S09_EXPLORATION.md)；[历史S08合并返修](REWORK_S08.txt)及[19文件77片段探索包](S08_REWORK_EXPLORATION.md)；[首次S08开工指令](START_S08.txt)及[首次探索包](S08_EXPLORATION.md)；[历史S07合并返修](REWORK_S07.txt)及[返修探索包](S07_REWORK_EXPLORATION.md)；[首次S07开工指令](START_S07.txt)及[S07已探索文件清单+关键片段](S07_EXPLORATION.md)；[历史S06合并返修](REWORK_S06.txt)及[已探索文件清单+关键片段](S06_REWORK_EXPLORATION.md)；[首次S06指令](START_S06.txt)及[首次S06探索包](S06_EXPLORATION.md)；[S05返修指令](REWORK_S05.txt)及[S05返修探索包](S05_REWORK_EXPLORATION.md)；[首次S05指令](START_S05.txt)、[首次S05探索包](S05_EXPLORATION.md)、[S04返修指令](REWORK_S04.txt)、[S04返修探索包](S04_REWORK_EXPLORATION.md)、[首次S04指令](START_S04.txt)、[首次S04探索包](S04_EXPLORATION.md)、[S03返修指令](REWORK_S03.txt)、[S03首次指令](START_S03.txt)、[S02返修指令](REWORK_S02.txt)、[S02首次指令](START_S02.txt)、[S01返修指令](REWORK_S01.txt)和[首次S01指令](START_S01.txt)保留作历史输入
- [当前核查与模式优化结论](REVIEW_AND_WORKFLOW_2026-10-11.md)
- [计划包校验记录](PACKAGE_VALIDATION.json)

## 阶段表

| 阶段 | 工作 | 内部顺序 | 状态 |
|---|---|---|---|
| [S00](stages/S00.md) | 已完成的基线修补审查 | P1-00 | accepted |
| [S01](stages/S01.md) | 测试隔离与可信测试基线 | P1-01 → P1-02 | accepted |
| [S02](stages/S02.md) | 错误、原子写与模型输出基础 | P1-03 → P1-09 → P1-55 → P1-04 | accepted |
| [S03](stages/S03.md) | 科目存储与持久化接入 | P1-10 → P1-11 → P1-12 → P1-13 → P1-14 | accepted |
| [S04](stages/S04.md) | 批改、考点和接口失败闭环 | P1-05 → P1-06 → P1-07 → P1-08 → P1-15 → P1-56 | accepted |
| [S05](stages/S05.md) | 安全上传、索引源与任务状态 | P1-16 → P1-17 → P1-18 → P1-29 → P1-19 → P1-30 | accepted |
| [S06](stages/S06.md) | 文档图像索引与覆盖 | P1-26 → P1-27 → P1-28 | accepted |
| [S07](stages/S07.md) | 科目聊天与知识库作用域 | P1-20 → P1-21 → P1-22 → P1-23 → P1-24 → P1-25 | accepted |
| [S08](stages/S08.md) | 报告输入、目录和执行边界 | P1-31 → P1-32 → P1-33 → P1-34 | accepted |
| [S09](stages/S09.md) | 报告生成、核查及入口一致性 | P1-35 → P1-36 → P1-37 → P1-38 | accepted |
| [S10](stages/S10.md) | 学情派生、导出与删除一致性 | P1-39 → P1-40 → P1-41 → P1-54 | accepted |
| [S11](stages/S11.md) | 现有UI与裁剪残留收敛 | P1-42 → P1-43 → P1-44 → P1-45 → P1-46 | accepted |
| [S12](stages/S12.md) | 启动、文档和lint收尾 | P1-47 → P1-48 | accepted |
| [S13](stages/S13.md) | 全量回归及真实沙箱验收 | P1-49 → P1-50 | accepted |
| [S14](stages/S14.md) | HTTP与WebSocket集成验收 | P1-51 → P1-52 | accepted（用户批准单项配置例外） |
| [S15](stages/S15.md) | 浏览器验收与最终签收准备 | P1-53 | accepted |

单元文件仍在cards目录，阶段入口链接其目标/范围/行为条件；阶段的文件范围为单元白名单并集。默认一名执行者串行，阶段末一次独立审阅；不自动进入未授权的下一阶段。

阶段末一份report.json和共享execution.log，review.json由协调者给；不再每卡新建长报告/补修/验收四份文档。旧P1-00completion与归档保持不变，本次修补和签收存于.phase1-evidence/reviews/P1-00。

本包校验只证明计划/schema/顺序完整；业务完成另由S00–S15独立receipt证明。S13–S15已通过本机回归、OS隔离、HTTP/WS及浏览器门，真实供应商与部署仍不在验收结论内。

2026-10-13：S03-final已验收；当前下一阶段为[S04开工指令](START_S04.txt)，随附[已探索文件清单+关键片段](S04_EXPLORATION.md)。按流程2.1复用源码片段和hash，只定向补读，不重新做全仓库orientation。

2026-10-13 S04初次审查：状态changes_requested，按[合并返修](REWORK_S04.txt)与[更新探索包](S04_REWORK_EXPLORATION.md)修严格候选边界、批内确认、复用元数据及HTTP cause出口；不进入S05。上条是首次授权历史。

2026-10-14 S04最终签收：R1–R5及协调者Unicode补修通过，369项定向、2631项相关目录/18历史skip、18方法扩展探针、Ruff和恢复归档核验通过。最新receipt为`.phase1-evidence/reviews/S04-final/review.json`，合并37条源码hash；真实六树不变。当前下一阶段为[S05开工指令](START_S05.txt)，附[S05探索包](S05_EXPLORATION.md)。上方S04初次审查为历史记录，现不再阻止S05开工；S05代码尚未实施。

2026-10-14 S05初次审查：源码/命令证据一致，126项与Ruff通过，但独立23方法复现24处失败；相关目录2739 passed / 1 failed / 18历史skip，P30测试仍依赖调度时序。当前按[S05合并返修](REWORK_S05.txt)及[更新探索包](S05_REWORK_EXPLORATION.md)处理，不进入S06。阶段指针`.phase1-evidence/stages/S05/review.json`记录当前48条源码hash；真实六树本轮不变，协调者未改生产/测试。

2026-10-14 S05最终签收：返修R1–R7通过，协调者补修五个生产文件并新增13项永久回归，197项定向、2811项相关目录/18历史skip、33方法独立探针、Ruff、六树保护及恢复归档核验通过。最新receipt为`.phase1-evidence/reviews/S05-final/review.json`，合并48条当前源码hash。当前下一阶段是[S06开工指令](START_S06.txt)和[S06探索包](S06_EXPLORATION.md)；P26→P27→P28一次授权执行，不重做orientation。上方S05初次changes_requested为历史。P27范围补齐两个coverage投影接缝和旧loader测试适配，共11路径；尚未实施S06或第二阶段功能。

2026-10-16 S06初次审查：137项合并、2940项相关目录/18历史skip、Ruff、源码/命令证据和1853成员归档均核验通过，但18方法独立探针含子场景复现18处失败：资产/旧分支门禁、识别额度/factory去图重试、普通失败发布、旧coverage/ready公开投影和PDF跳过统计。按[S06合并返修](REWORK_S06.txt)与[本轮探索包](S06_REWORK_EXPLORATION.md)完成R1–R6，不进入S07；最新基准为59条源码、返修14路径，其余45只读。原S06开工授权已由本轮窄范围指令细化，协调者未改生产/既有测试，真实六树本轮无新变化。

2026-10-16 S06-final签收：返修旧探针已通过，协调者仍复现9类/11断言遗漏并直接修复六生产/两测试文件，新增11项回归。最终168项合并、2971项相关目录/18历史skip、27方法探针及Ruff通过，六树本轮无变化，最新59条源码hash见S06-final receipt。返修报告38条哈希有1条派生readonly_check漂移，原件保留，独立复核已说明并取代其过期摘要。下一阶段为[START_S07](START_S07.txt)，附[24文件68片段探索包](S07_EXPLORATION.md)；六卡一次阶段交付，P21补齐统一WS错误投影两路径，18路径/77项capture并集。S07尚未实施，历史“不进入S07”已被本次签收取代。

2026-10-16 S07初审：原127项定向/2旧环境skip、420项Node、Ruff/tsc通过，相关回归3264 passed/21 skipped/2历史模型配置失败；两失败已从S06归档独立重建复现。46产物hash与42所列命令匹配，最终另2条收尾命令未列入报告。独立后端26场景25失败/1正例，前端7场景5失败/2正例，确认挂载身份/空集合、缺库与provider读取、三态/重放、前端接线/生命周期/清空、warning不可见、公开结果泄漏、PageIndex缺标记与非chat端作用域遗漏。当前changes_requested，不进入S08；[R1–R8合并返修](REWORK_S07.txt)一次交付，23路径/82源码基准，协调者未改生产/既有测试，真实六树本轮不变。

2026-10-16 S07-final签收：原返修26后端/7前端探针通过，协调者新增11项探针先复现后直接修复构造异常、显式失败结果、嵌套来源字段、explicit unknown及legacy/config重生成预校验。四生产/五测试文件补修，新增11项永久回归；17项Question环境失败以显式fake配置消除。最终244项定向/独立后端、3391项相关目录/19历史条件skip、429项Node、7前端探针、tsc/Ruff及计划包通过；六树本轮零变化，最新84条源码hash见S07-final receipt。原54产物/37所列+收尾共39条唯一命令/前缀hash核验通过，保留并解释07.1中的两处closing措辞/旧hash笔误，未改原证据。下一阶段[START_S08](START_S08.txt)附[24文件65片段探索包](S08_EXPLORATION.md)，四卡一次交付，10路径/94项capture并集；S08尚未实施，S09入口接入及S15真实OS门按原进度处理。

2026-10-17 S08初审：165项定向、3556项相关目录/19历史skip和Ruff通过，24产物/42条含收尾命令及814行79222字节冻结前缀核验一致；原最早related日志范围穿插ruff/bad-control输出，历史保留，新返修要求串行。独立32场景复现28失败/4通过，包括固定输入名/源码编码、run路径与坏metadata/保留名、UUID竞争删除成功者/失败active泄漏/误弃存活进程、EOF越时/leader先退组清理/worker全量日志OOM、坏控制协议、失败或旧attempt/产物替换，以及真实bwrap中ODE脚本stdout自签。当前changes_requested，不进入S09；按[合并返修](REWORK_S08.txt)和[19文件77片段探索包](S08_REWORK_EXPLORATION.md)在原十路径完成R1–R8，94源码/84前置只读。协调者未改生产/既有测试，六真实树本轮零变化；旧host helper/入口集成仍S09、最终OS门仍S15，不能将本轮真实边界缺陷留到后续。

2026-10-17 S08-final签收：Harness原32探针全通过，协调者追加13场景仍复现11失败，已补修四生产/三测试并新增11项永久回归：路径链接、缺metadata active收尾、不可读出生标识、重复/矛盾协议、无artifact成功、采样输出截断、同run脚本竞争、PNG IO及坏摘要类型映射。最终309项定向/独立检查、3655项相关目录/19历史skip及Ruff通过，六真实树本轮零变化；94条源码见S08-final receipt。40报告+5收尾命令及24产物核验一致；1880对1880只是相等超集的表述笔误保留说明。下一阶段[START_S09](START_S09.txt)附[已探索文件清单+关键片段](S09_EXPLORATION.md)，四卡一次交付。P35额外窄授权P31旧流水线接缝测试跟随安全契约更新，已同步卡/tasks/stages，9路径/99项capture、90前置只读；S09尚未实施，最终OS/浏览器门仍S15。

2026-10-19 S09-final签收：348项定向、3739项相关目录/19历史skip及Ruff通过；协调者补修5生产/4测试，新增18项永久回归，解决附件review遗漏、复制PNG校验不足、发布路径/临时文件、重IO及取消提交边界，六真实树零变化。下一阶段为[START_S10](START_S10.txt)及[已探索文件清单+关键片段](S10_EXPLORATION.md)，四单元一次交付；共享活动协议必要接入已同步卡/tasks/stages，14路径/107 capture，S10尚未实施。最终真实OS门为S13/P1-50，HTTP/WebSocket为S14，浏览器为S15；旧文档将P50写成S15的说法按此更正。

2026-10-19 S10-final签收：原42项定向通过但独立25项边界均复现缺陷，协调者补修11生产/5测试，最终121项S10/执行器定向和3806项相关目录/19历史skip通过。修复租约能力/身份/继承/直接调用、取消线程生命周期、导出排除/metadata/格式/内存/清理、跨用户准备对象及短JSON写入删除竞态；六树零变化。下一阶段[START_S11](START_S11.txt)附[探索包](S11_EXPLORATION.md)，五单元一次交付；29路径/134 capture，S11未实施。真实最终门仍S13–S15。

2026-10-19 S11-final签收：协调者补修页面协议/状态投影/同名库作用域/请求代次及画像清空、provider catalog描述和CLI文档验证假阴性；4生产/3测试，新增19项永久回归。最终49定向、3843相关目录/19既有skip、477 Node及全CLI66/1终端skip、tsc/限定Ruff通过。六树不变，133条当前源码、1902成员恢复归档见receipt；历史S10 supplementary误覆已逐字节恢复并核验，mtime例外如实保留。下一阶段S12两单元一次交付，capture145；S12未实施。

2026-10-20 S12-final签收：CDPATH相对启动/链接补修及两项永久回归，361定向/1既有skip、4022相关/20条件skip、完整业务Ruff通过；145源码、1907成员恢复归档、六真实树无变化。环境证据更正为Node v22.22.1，复用S11-final Node数477。下一阶段 [START_S13](START_S13.txt) 附 [已探索文件清单+关键片段](S13_EXPLORATION.md)，两项新增门禁脚本/147 capture/145只读；S13未实施，第一阶段尚未整体完成。

2026-10-20 S13-final签收：4757完整Python/20既有skip、4777收集、477 Node/tsc/Ruff、真实bwrap七组及16项独立门禁回归通过，六树不变；147源码/1911成员最终归档。已修复计数、独立新证据目录、秘密清除、网络出口、六树保护与结果/OS断言缺口。下一阶段 [START_S14](START_S14.txt) 附 [已探索文件清单+关键片段](S14_EXPLORATION.md)，147只读/149 capture；HTTP/WS及浏览器仍未完成。

2026-10-20 S14：协调者补修并独立验收；结果以S14-final receipt为准。唯一旧catalog损失已由用户明确接受并建立受限新基线，事故/原始基线保留，其他树不放宽。后续只用隔离Python runner。下一阶段按 [START_S15](START_S15.txt) 和 [已探索文件清单+关键片段](S15_EXPLORATION.md) 执行浏览器门，不进入第二阶段。

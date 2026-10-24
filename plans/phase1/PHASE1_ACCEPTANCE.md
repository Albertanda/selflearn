# 第一阶段最终验收（2026-10-21）

S00–S15共16阶段/57张卡全部完成独立签收，第一阶段关闭。以 `.phase1-evidence/stages/S15/review.json` 指向的 `.phase1-evidence/reviews/S15-final/review.json` 为当前完整证据入口。当前源码、范围、归档、全部命令和数据比对均绑定该receipt；旧阶段的源码摘要只表示当时状态。没有S16，第二阶段未授权。

## 最终验证与直接补修

- S13/P50：真实bwrap沙箱、PNG/ODE、资源边界、失败发布及清理已验收；S14：真实HTTP/WS入口与线程/取消终态已验收。既有证据不覆写。
- S15：真实Chromium驱动真实Next/FastAPI、隔离源副本及确定性model/STT/embedding，B1–B5全部通过；包括三题成功Quiz、跨科与全局RAG、展开可见的各科来源文件名、切科、坏响应/断网、按钮释放和重试、实际ZIP下载与成员CRC/manifest哈希。
- 协调者修复：无call_id的轮次SOURCES原被UI丢弃；导出/复习包异步下载原不在busy/error边界内，传输失败会先报成功。现在来源在当前轮次现有trace内可见，下载等待实际响应并检查格式前缀，失败不会提示成功或触发下载；保留切科/卸载抑制旧结果。
- 新增12项永久Node回归，最终489项通过；整站tsc通过。8个改动TS/TSX文件ESLint无错误，科目详情页22条既有中文i18n警告保留。前端格式前缀校验不是通用ZIP深度验证；实际下载ZIP另由浏览器验收校验成员与CRC。
- 浏览器设施补修：拒绝真实repo/祖先/已有数据/伪造bootstrap/已封存证据；源输入只读复制，过滤.env与symlink；父子进程清理凭据、Python/Node/浏览器出口约束，覆盖DNS resolver及WebSocket；自动清理只认本次PID出生身份和临时根。7项配置VM探针及18项Node网络VM探针通过，红对照保留。最后浏览器后仅增加临时基目录拒绝检查及等效JSX引号转义，另以最终VM、Node、tsc和lint复核。
- 完整隔离Python回归4806通过、20项条件skip、6条非RuntimeWarning/Unraisable警告；Ruff与计划包通过。范围/数据/归档的计数与退出码见签收receipt及追加式execution.log。skip来自既有终端条件、未安装可选解析/RAG依赖及显式禁用的集成/公网测试，不等同于该路径已通过。

## 数据完整性与结论边界

S14原model_catalog.json已丢失，未找到精确备份，原配置没有恢复。用户已明确接受单项例外并允许新基线；授权与摘要见 [例外记录](data_baseline_exception.json)。相对S13原基线，`real_data_unchanged=false`；相对获准新基线及协调者本轮到达时，六真实树无新增变化，`real_data_unchanged_from_approved_baseline=true`。其他五树和settings其余文件不放宽；原基线、事故与原报告保留。未读取/展示密钥、未验证真实配置有效性、未自动调用真实模型或轮换凭据。

Fake模型用于验证真实入口的协议、作用域、成功/失败与持久化闭环，不是对真实模型生成质量的评价。RAG来源显示文件身份，未凭空生成原文下载URL；科目导出不含聊天、不支持导入恢复；知识点没有attempt证据时mastery=null。真实供应商、互联网检索/模型质量、部署及生产负载均未获验收，不应从本机门推导它们已经通过。

原START_S15/B2要求“来源中的下载URL实际GET”，但现有KB来源投影没有URL；C08明确保持来源身份约束，不新增全文KB阅读能力。协调者据C08将该不可适用子项限定为当前轮次可展开来源身份、真实raw内容标记与跨科隔离；未宣称来源下载已经通过，也未以B4 ZIP下载替代它。若将来要求原文下载，应另立功能需求和访问契约。Next的一次npm版本检查被Node出口守卫阻断，记录保留；浏览器console中的故障请求错误来自注入场景，不是未捕获page error。

## 后续操作

只读交接见 [交接指令及探索片段](PHASE1_HANDOFF.txt)。不要重新执行历史START/REWORK指令、不要把旧计划文件的planned字段解释为待补做业务。当前阶段状态以stages.json与canonical receipt为准。

Python测试必须通过 `.venv/bin/python scripts/run_tests_isolated.py [pytest参数]`；不得直接pytest或绕过guard。浏览器如经另行要求重跑，必须显式选择repo `.phase1-evidence/` 下全新 `S15_EVIDENCE_DIR`，使用已安装浏览器及当前隔离runner。默认原S15目录已封存，拒绝覆写属于正确行为。历史S13固定基线门会拒绝后来已授权的源码变化，不能借其过期source断言覆盖当前签收。

# DeepSeek Harness 阶段执行指南 2.1

用户于2026-10-11明确要求按阶段推进。读取STAGE_WORKFLOW.md和stages.json，再读当前阶段入口及其中小卡；小卡目标/文件/符号/行为测试保留，历史“一卡一会话、每卡完成停止”不再适用于阶段授权。

## 可粘贴入口

```text
工作目录 /home/albert/selflearn/selflearn。
只执行已授权阶段Sxx，先读START_Sxx及附带探索包，核验前置review和片段hash，再按STAGE_WORKFLOW.md和stages/Sxx.md定向执行。
阶段内按指定卡顺序实现、定向测试和自修，完成一单元不询问下一卡，不重新阅读57卡或另写全项目计划。
限定阶段白名单并集和卡目标；不提交、不调用真实供应商、不动真实配置/数据、不做第二阶段功能。
只保留阶段report.json和共享追加日志，按C14和StageReport schema记录各单元结果与实际命令。
阶段结束停止，由协调者一次独立复核；不自行执行下阶段或标accepted。
```

当前待执行阶段以stages.json的next_stage与最新签收receipt为准，具体指令见对应START_Sxx.txt；原START_P1_00.txt/旧审查报告是历史记录。

## 必须保持的约束

- 生产依赖/数据模型不自行扩展，不改冻结契约来让代码通过；共同契约缺陷由协调者修订并注明影响面。
- 范围按阶段开始前实际source diff，不按HEAD所有dirty。本阶段单元内的真实集成返修可直接完成，不把每个helper调整变成人工交接。
- tests/phase1夹具须隔离PathService、用户roots、manager/catalog缓存，并恢复；外网stub，不能使用真实密钥。
- 测试缓存可产生，但不覆盖生产.next/.next-deeptutor，浏览器用临时源码副本及独立dist。
- 数据读取允许保护程序不透明二进制流哈希；不解析/展示/复制settings中的密钥，不用真实供应商。
- 有效反例先证明其他字段合法；安全诊断不回显输入；类型边界、权限和失败bytes必须真正观察。
- 普通实现选择自主做，不重复要开始/继续批准；范围/契约/真实数据/环境阻塞才报告准确缺项。
- 阶段默认3个主要证据文件，日志仅追加。旧单卡completion和失败日志不删不改，历史合法skip保留。

命令行已有dsh --profile headless的基本形式，但本包不猜model id或设置Harness profile；可在用户已有Web界面按当前项目目录粘贴START_S01。项目AGENTS.md适用于selflearn，不把Harness仓库的pnpm规则移植进来。

# ASR-R1 长录音修复执行包

2026-10-22：已准备派发，尚未实施。用户要求针对真实课堂录音问题执行专项修复；不是S16，也不是泛化的第二阶段功能开发。

一次执行、一次交付，入口为 [开工指令](START_ASR_R1.txt)、[冻结数据与状态契约](CONTRACTS.md)、[六单元任务卡](TASKS.json)、[已探索文件清单+关键片段](EXPLORATION.md)。[历史只读调查](DIAGNOSIS.md)提供事实与备选方案，实际实施以本包冻结范围为准。

主因：45分钟原件直连SF63.551秒成功，Next默认30秒500；真实目录早已存有转写。修复交付应为异步任务+切片+顺序合并+恢复，而非仅提高超时。暂不增加阿里适配器，所给阿里凭据测试未通过。

证据目录：`.phase1-evidence/reviews/ASR-R1-dispatch/`保存本包摘要、当前源码/数据基线及脱敏调查结果；worker用全新`.phase1-evidence/repairs/ASR-R1/`，不得写旧S15目录。原件、真实settings与当前服务保持；正常用户使用产生的数据变化与worker写入必须分开说明。

Worker仅可在本README追加实施状态、最终验证引用与运行说明；本包其余文件保持冻结。S00–S15签收始终是历史状态，后续合法源码变更由ASR-R1新receipt绑定，不修改旧receipt。

## 实施状态（ASR-R1，2026-10-22）

已按 A1–A6 合并实施（待协调者独立验收）：

- 新增持久化 job API（POST/GET/result/cancel/retry）与 `.asr_jobs` 私有树；上传 202 后由后台
  探测、按 sample 连续切片（180 秒上限、前 10 秒静音中点、无静音硬切）、逐片 checkpoint、
  按 file/chunk 顺序合并，全部片段成功后才事务发布到 `materials/lecture`。
- 两个科目页面（列表页“课堂录音”和详情页课堂考点）使用同一个 typed client/panel；刷新可找回
  最近任务，202 不显示成功，取消/重试为显式操作，完成结果只填入当前科目一次。
- provider 仅支持 OpenAI-compatible multipart；SF 按 50,000,000 字节/3600 秒保守规划，未知端点
  按 8,000,000 字节/180 秒。401/402/403 不重试，413 只细分失败范围，429 尊重 Retry-After。
- 65 秒确定性 provider 延迟的真实 Chromium/Next/FastAPI job 通过（POST 202 后约 65 秒完成，
  中途刷新找回同一 job）；S15 B1–B5 保留并 5/5 通过。完整 45 分钟真实录音经临时科目/job/API/
  发布流程与 loopback fake provider 跑通 16/16 片。
- 真实 45 分钟 SiliconFlow job smoke 被外部 `HTTP 402` 拒绝并记录为阻塞；未伪造 live 通过，
  未修改用户 catalog/key，未读取 Qwen key 文件。
- 证据：`.phase1-evidence/repairs/ASR-R1/report.json`；运行命令与失败历史见同目录
  `commands.jsonl` / `execution.log`。

启动时显式提供媒体工具（Windows 二进制在 WSL 中）：

```bash
SELFLEARN_FFMPEG_BIN="/mnt/c/.../ffmpeg.exe" \
SELFLEARN_FFPROBE_BIN="/mnt/c/.../ffprobe.exe" \
./scripts/start_selflearn.sh
```

## 协调者复核

已独立审查并直接补修 Harness 交付，详见 [复核、修复、服务阻塞与启动说明](REVIEW.md)。最终签收以 `.phase1-evidence/reviews/ASR-R1-final/review.json` 为准。HTTP 402 已实测确认为当前账户余额不足并独立分类，未恢复真实模型转写成功。历史 worker 报告保留原样；本次数据保护使用测试前固定快照与结束后六树校验，不再排除原测试。

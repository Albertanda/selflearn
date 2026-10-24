# ASR-R1 独立复核与补修

本次用户授权：复核 ASR-R1.txt、实际实现与验收结果，直接修复问题并调查服务阻塞。范围是长录音专项，不开启 S16 或第二阶段。

## 交付审查

Harness 的整体方向正确：录音上传返回 202，后台持久化 job，按连续采样范围切片，按原文件与片段顺序合并，最后发布。原 45 分钟请求曾直连成功，前端旧 30 秒代理边界才是最初故障的实测原因。切片与异步任务分别解决供应商输入限制和请求长时间占用问题。

其报告不能直接作为最终验收：严格 Python 全量仍有 1 项失败；402 被归为认证错误；检查点完整性、媒体资源约束、取消和发布路径也有独立复现的缺口。Worker 原报告、失败日志、归档均保持原样。复核确认其 1956 个源码归档成员摘要一致；45 文件范围内的 47 项变更经字面路径和父目录重新计算，范围外为零。S15 回执、派发索引、S14 单项配置例外及冻结合同均未改写。

## 本轮直接补修

| 问题 | 修复与验证 |
|---|---|
| HTTP 402 误导为密钥或权限错误 | 新增 `asr_provider_billing`，HTTP 502、禁止自动重试；提示在供应商平台处理余额/计费状态后手动继续。401/403 仍保持认证/权限类别。记录 SF 的响应 trace-id。 |
| endpoint 带 query 时路径拼接错误；恢复配置身份不完整 | 分别拼接 URL path/query；保留非敏感 query 的身份，排除凭据参数；配置指纹包含 profile_id，允许只轮换密钥。SF 能力策略绑定实际 API 域名。 |
| 只声明单片预算，没有校验真实产物 | 发送前校验实际 WAV 字节数、时长、16kHz/单声道/PCM16 编码，限制尝试次数。 |
| 413 子片还能继续递归细分 | 每个初始范围至多细分一次；子片携带 split_depth，成功片保持稳定身份和检查点。 |
| 批次限制只在全部 stage 后检查 | 在流式写入期间累计 batch 字节，写入溢出块前拒绝，旧同步入口默认行为保持。 |
| 媒体协议未限制；日志限额只在结束后生效 | ffmpeg/ffprobe 输入限定 file,pipe；运行中限额读取 stdout/stderr，超限终止并回收自有进程。 |
| 媒体超时不是整项累计预算；磁盘限制仅事后检查 | 按 job 累计媒体子进程用时；运行中检查私有工作集，探测后在继续解码前检查批次时长和预计资源。 |
| 中断输出可能被当作完整 WAV 重用 | WAV 写入内部 partial 文件，验证后 rename；异常删除自有 partial，重试重新生成未完成产物。 |
| 恢复时未验证成功文本、规范化音频等摘要 | 保留并核验原件、规范化 WAV、成功片和文本摘要；合并前校验采样范围连续且覆盖末尾，篡改不发布。 |
| 用户取消不能及时终止进行中的网络/媒体操作 | worker 内监视持久化取消请求，终止进行中的等待；清理失败不会假称 cancelled。发布开始后仍拒绝取消。 |
| 取消等待门闩可能遗留后台取锁线程；发布占用事件循环 | 以非阻塞取锁循环替代可遗弃的取锁线程；发布放到线程并 shield/join。shutdown 等待实际线程退出后才释放租约和 claim。 |
| 正常发布缺少最后摘要核验，预条件存在取锁窗口 | 门闩内准备发布计划，发布后逐目标核验；恢复的全部已发布/部分已发布/第三者改动分支均实测，第三者内容不覆盖。 |
| 失败状态与释放 claim 之间，显式 retry 可能被丢弃 | 有界等待旧 claim 释放，重新核对完成/取消状态，禁止多 worker。 |
| 内存任务表未区分同名科目的用户空间 | key 纳入科目绝对 workspace 身份；完成回调也释放尚未开始就被 shutdown 取消的任务资源。 |
| 迟到 cancel/retry、旧结果或刷新可能覆盖新科目/任务 | action 捕获 generation；新上传使旧请求失效；结果交付也校验当前 job_id；新增执行真实 hook 的延迟响应测试。 |
| job_id 只验证 32 位 hex | 同时验证 UUID4 与 RFC4122 variant；匹配已有请求时按真实 owner 状态投影，不假称仍在运行。 |
| 存储摘要读取可能跟随 symlink 或阻塞于非常规文件 | O_NOFOLLOW/O_NONBLOCK 并 fstat 验证普通文件；文本读取限定本 job 的 text 子目录。 |
| 全量测试拿 S15 旧业务数据与用户新使用结果作等值比较 | 保留历史记录与精确 S14 例外验证；runner 在 bootstrap 前固定本次不透明数据快照，测试期间与结束后校验全部六树。新增“pytest 成功但数据变化仍失败”的测试，不排除原保护测试。 |

新增独立 Python 回归共 22 个场景，其中首轮 10 个及后续资源清理/链接场景 3 个在补修前确实失败；另有 2 个测试运行器数据保护场景。新增 3 个前端测试执行生产 hook，覆盖切科后迟到取消/继续响应与阻止同一面板在活动任务期间重复上传；活动任务保留轮询归属。暂停过一次未完成的全量测试，以纳入最后发现的异常半成品清理修复；该次 exit=2 不作为通过证据。随后完整运行还暴露了新增数据保护测试与 tests/scripts 的导入命名冲突（其余 4888 项通过），已改为显式加载 CLI 模块并增加混合收集复核；最终串行验收另行完整运行，原失败记录保留。

## 外部服务阻塞

协调者独立用当前 active STT profile 的密钥在内存中发送 **1 次、1 秒 WAV**，直达官方 `api.siliconflow.cn`：HTTP **402**，业务码 **30001**，响应命中余额不足分类，耗时 0.402 秒，trace-id `ti_ahufbw0oaaycxfnk35`。只记录固定分类、状态和追踪信息，不保存密钥或上游原文。

这条请求说明当前账户计费阻塞已经发生在极短输入上。增加切片不能解除账户余额限制。需要用户在硅基流动控制台处理可用余额/计费状态；处理后可显式继续失败任务。没有自动充值、换供应商、改真实配置或重复计费重试。未在余额阻塞后再发送完整课堂录音；完整真实模型转写仍未重新验证。

参考官方[财务说明](https://docs.siliconflow.cn/docs/userguide/faqs/misc_finance)与[转写接口说明](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post)。402/30001/余额不足结论来自本次真实请求，不能伪装为官方页面已列出该错误码。官方[更新公告](https://docs.siliconflow.cn/docs/release-notes/overview)已说明旧 `/user/info` 于 2026-08-14 停用，本次未使用该过时余额查询接口。

## 验收与运行

最终验收计数、源文件摘要、数据比对和证据索引见 `.phase1-evidence/reviews/ASR-R1-final/review.json`。完整命令与实输出在同目录 `execution.log`、`commands.jsonl`，所有最终检查按顺序运行。真实模型验证与本地 fixture 验收分开报告。

运行中旧服务未重启。新代码需重新启动项目后生效；本机 Ubuntu PATH 没有原生 ffmpeg/ffprobe，启动前必须提供已经验证的 Windows 可执行文件：

```bash
cd /home/albert/selflearn/selflearn
SELFLEARN_FFMPEG_BIN="/mnt/c/Users/17261/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin/ffmpeg.exe" \
SELFLEARN_FFPROBE_BIN="/mnt/c/Users/17261/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin/ffprobe.exe" \
./scripts/start_selflearn.sh
```

先在原启动终端按 Ctrl+C 关闭旧实例，再执行上述命令。处理中正常关闭会保留可恢复状态；不要用强制结束代替正常退出作为日常操作。

本轮测试从临时科目/临时数据根运行，不向真实科目写测试产物。相对于 S15/S13 的历史差异与 S14 配置事故仍如实保留，不能将“本轮前后未变”写成“历史原配置已恢复”。

最终本地结果：Python **4890 passed / 20 skipped / 0 failed / 0 deselected**（RuntimeWarning 与 Unraisable 作为错误），Node **503 passed**，浏览器 **6 passed**，TypeScript/Ruff/diff 检查通过。ESLint 为 0 errors / 4 条中文 JSX 文案警告；Python 保留 6 条非上述严格类别警告。45 分钟录音模拟供应商全链路 **16/16** 完成；四份原录音未变；临时服务端口均关闭、临时实例已清理。本地代码签收为 `accepted_local_with_external_blocker`；真实账户复通仍未完成，`live_provider_verified=false`，不宣称真实模型质量或已部署成功。

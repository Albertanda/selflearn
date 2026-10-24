# ASR-R1 实施契约（冻结版）

本合同由当前用户下发授权生效。仅长录音专项，不修改第一阶段C01–C14历史原文。保留其路径、原子写、错误投影、归属、ASR不自动索引约束。本合同与START_ASR_R1.txt共同定义本轮验收。

## D1 范围与兼容

新增job API；旧POST /subjects/{id}/knowledge/upload的文档与同步音频响应保持200及既有fields，聊天麦克风不迁移。两个现有科目页面全部音频走job，mixed auto上传继续在创建任务前拒绝，不拆成隐式部分成功。录音job只支持本轮已验证的OpenAI-compatible multipart，沿用配置resolver的auth_style、extra_headers、api_version和language；其他协议明确不支持，不伪装阿里适配已完成。

设置STT测试与课堂调用共用现有resolve_stt_runtime_config的选择语义；保持文件句柄流式上传，不能复用一个会把200MiB全读成bytes的接口。STTConfig/现有voice公共契约不做大重构，test_runner只将结果描述明确为1秒连接/协议测试。

## D2 限制与媒体

- MAX_FILES=16；MAX_FILE_BYTES=200*1024*1024（沿用既有）；新增job的batch总输入上限也为200MiB；总音频时长上限4小时，实际探测后超过则job失败；私有工作集上限1GiB。以上命名常量、测试与错误文案一致，不改变旧API上限。
- MAX_CHUNK_SECONDS=180；输出16kHz/单声道/PCM16 WAV；按sample连续规划，首版不重叠。优先选择上限前10秒内最后一个可用静音中点，静音检测用固定有界参数（建议noise=-35dB,d=0.3s），没有静音硬切；不得跳过静音时间形成覆盖空洞。
- 能力表以provider/protocol及已验证endpoint/model绑定，不以显示名称或Qwen字样判断。SF规范快照为50MB/3600秒；MB确切边界未由文档澄清，设保守50000000字节用于规划，不声称此次50786002字节被拒。未知multipart保守单片8,000,000字节/180秒。总是额外核对实际产物size与编码预算。
- 子进程固定argv、无shell，probe20秒、媒体操作总600秒上限；取消终止自己创建的进程/组并wait，无宽泛pkill。Windows.exe仅显式配置且WSL时转换受控文件路径；不把/proc、URL或任意用户传入选项作为媒体输入。协议限制file/pipe，避免媒体内容主动访问网络。
- 静音检测/分片大日志须流式限额，输出工作集超预算即停止并清理；探测/转码不得阻塞FastAPI事件循环。输出路径按内部数字生成，不使用原文件名构造shell。

## D3 HTTP契约

所有接口在当前用户上下文解析registered subject，使用require_auth与SubjectRoute。request_id与job_id必须是UUID4，磁盘与响应job_id为32位小写hex。非法ID400，科目/任务不在本用户本科目404，不回显路径。所有GET只读，不创建树、不迁移/改manifest。

| 方法/路径（前缀/api/v1/subjects/{sid}） | 输入与输出 |
|---|---|
| POST /asr/jobs | multipart重复字段`files`（不是字面`files[]`）、request_id；可选language默认zh。流式stage并校验后202，返回`{operation:"transcribe",job:JobView}`；不得等待probe/ASR |
| GET /asr/jobs?limit=20 | limit整数1..50；`{jobs:JobView[]}`，created_at倒序，缺任务目录返回空且不创建 |
| GET /asr/jobs/{jid} | `{job:JobView}`；不可含凭据、绝对磁盘路径或全文 |
| GET /asr/jobs/{jid}/result | 仅completed，返回`{operation:"transcribe",job_id,files:[...],transcripts:[{file,text,model}],message}`；其他状态409；保留旧结果字段形状 |
| POST /asr/jobs/{jid}/cancel | queued/running→202（可能cancelling）；cancelled重复200；已completed或已经进入不可取消发布段409，禁止返回cancelled但实际上完成 |
| POST /asr/jobs/{jid}/retry | failed/interrupted→202同job继续；queued/running/cancelling不启动第二worker（运行中重复202同job）；completed/cancelled409 |

POST创建幂等：job_id=UUID(request_id).hex。该ID已有记录时，必须验证同一批文件顺序/名称/sha、语言及配置指纹；相同返回202同job不再转写，不同409 asr_request_conflict，不覆盖旧任务。先用自有临时stage流式hash，再判断；并发同ID以OS锁+原子落盘保证唯一。202丢失时前端可用已知job_id或列表找回，不能生成新ID自动重传。

Next新route.ts的POST和GET都必须转发，因为matcher对精确/asr/jobs路径的排除同时影响两者；/asr/jobs/{jid}等短请求可沿用rewrite。继承cookie/auth头，不能新开未鉴权上传路径。禁用全局增大/关闭所有API超时作为最终修复。

JobView schema：

```json
{
  "job_id": "uuid4hex", "subject_id": "registered-id",
  "status": "queued", "phase": "queued",
  "revision": 1, "created_at": "UTC ISO8601", "updated_at": "UTC ISO8601",
  "files": [{"file_index": 0, "name": "lecture.m4a", "size_bytes": 123}],
  "progress": {"files_total": 1, "chunks_total": 0, "chunks_completed": 0,
               "audio_total_ms": 0, "audio_completed_ms": 0},
  "error": null, "can_retry": false, "can_cancel": true, "result_available": false
}
```

status枚举queued/running/cancelling/completed/failed/cancelled/interrupted。phase为queued/probing/segmenting/transcribing/merging/publishing/finished；queued不假称已转写；total未知时为0且UI显示准备中。progress不以网络字节冒充识别进度。error为null或`{code,message,retryable,failed_file_index?,failed_chunk_index?}`，不输出完整内部错误。revision单调，UI不以过期poll覆盖新状态。

## D4 私有持久化、身份与claim

`store.subject_dir(sid)/.asr_jobs/<jid>/`保存manifest、私有输入、chunk checkpoint与result.json。使用现有confined/安全段/拒绝symlink和非常规文件规则；根、父、叶均验证。数据库/Redis非本轮依赖。manifest额外保存schema_version、输入sha与采样信息、配置指纹、每段状态/摘要、worker进程出生身份及attempt。使用原子JSON写与短文件锁；不得持有JSON写锁跨网络/媒体任务。

配置指纹不含API key/header secret：记录profile/model、协议、语言、规范化无凭据endpoint身份及策略版本。运行时凭据只在内存；重试允许同profile换有效凭据，但其他语义改变必须409 asr_config_changed，不与旧checkpoint混合。HTTP客户端传入的endpoint/model/文件路径不能替换server已解析配置。

持有主subject共享活动租约到实际worker终止；加跨进程音频writer门闩覆盖新/旧两种音频入口。锁资源在已验证用户workspace下，带owner-PID语义，fork子进程不能unlock父租约。相同sid在不同用户不可共用claim；导出/删除不能越过活动，普通读与无冲突功能保持原行为。manifest中的PID不是唯一claim依据；必须有OS层worker唯一性保护，拒绝双retry/双进程重做。

queued/running的owner不存在或出生身份不符：GET只读投影interrupted/can_retry，不写盘；retry在取得claim后检查并持久化恢复。应用shutdown在yield后关闭本进程持有的ASR任务、HTTP和媒体进程，将未完成工作留为可恢复中断，不能操作别的用户/进程任务。不做启动时跨用户扫描和自动真实模型恢复。

## D5 顺序、checkpoint、重试与发布

chunk=(chunk_id,file_index,chunk_index,start_sample,end_sample,sample_rate,sha256,status,text_path,attempt)。chunk_id使用文件号+采样范围形成稳定身份（如f0-0-2880000），chunk_index仅为当前规划的顺序显示。413触发细分时只替换失败范围，保留其他成功范围及checkpoint；revision增加后可重编号，但成功结果不能因显示index变化而错配或重调。每原文件首段0、相邻端点相等、末段等于规范化总samples，段号唯一递增；毫秒显示不作为累计计算依据。合并显式按file_index与chunk_index排序，未来并行完成顺序不影响文本。重复讲授句子必须保留。

每段成功原子落盘再计数。对中途失败只重试未成功片，验证原输入/切片摘要不变；不能重发成功片或盲目append。每份原录音独立输出一份transcript，多个输入按选择顺序出现在result里。

供应商401/403不自动重试；413或已识别长度超限重新细分一次（总片数与work预算仍有界）；429尊重Retry-After且单次等待最多60秒；5xx/Timeout指数退避+抖动，每片含首次最多3次/总墙钟240秒。connect≤15秒、单次read≤180秒、write≤60秒，客户端timeout与total deadline分开。无效输出不自动作为空成功；合法静音空text仍按既有契约成功但UI不声称有正文。日志只保留归一化原因/status/trace-id/耗时。

先准备私有完整result和预期正式源/文本摘要，再persist publishing，再调用既有commit_transcripts对整个batch发布。正常异常按旧事务回滚；已存在完成文件失败不变。只有所有正式hash吻合且completed元数据持久化后才能报告完成。准备/发布前取消可生效，开始正式commit后的cancel明确409，不在提交线程还活着时释放活动或删除输入。

硬崩溃发生publishing：必须interrupted并按可验证的preconditions恢复，不假称跨文件rename具备断电原子性。若全部预期正式文件已匹配则retry只补completed元数据，不再转写；部分提交可在对旧/本次预期hash进行检查后重做发布；第三者已改成其他内容则409 asr_publish_conflict，不能覆写。至少用故障注入覆盖这三个分支。

completed保留manifest/result与摘要，释放/删除本job占用的输入/大切片副本；failed/interrupted保留恢复所需输入/checkpoint；cancelled清理本job媒体但保留状态，需重新上传才能再做。私有.asr_jobs从科目导出递归排除，但科目合法删除仍删除它，不能留下孤儿任务。对所有清理不使用忽略IO错误来伪称成功。

## D6 错误契约

新ASR代码进入现有固定error envelope，保留原code行为，不修改无关HTTP语义：

| code | HTTP | retryable | 固定message用途 |
|---|---|---|---|
| asr_input_too_large | 400 | false | 输入文件/批次超过项目限额 |
| asr_job_not_found | 404 | false | 当前科目的转写任务不存在 |
| asr_protocol_unsupported | 400 | false | 当前供应商协议暂不支持课堂长录音 |
| asr_resource_limit | 400 | false | 媒体处理超过本任务资源预算 |
| asr_duration_limit | 400 | false | 超过本功能总时长限额 |
| asr_invalid_audio | 400 | false | 音频损坏/格式不支持 |
| asr_dependency_unavailable | 503 | false | 缺经过配置的ffmpeg/ffprobe |
| asr_provider_auth | 502 | false | 供应商凭据/权限无效，不冒充本站登录失效 |
| asr_provider_limit | 502 | false | 供应商输入限制且细分后仍失败 |
| asr_rate_limited | 429 | true | 有界退避耗尽 |
| asr_config_changed | 409 | false | 恢复模型/策略不兼容 |
| asr_request_conflict | 409 | false | 同request_id内容冲突 |
| asr_invalid_state | 409 | false | completed/cancelled等不允许的动作 |
| asr_publish_conflict | 409 | false | 正式目标已被后来修改 |

其余沿用provider_timeout504、provider_unavailable502、invalid_model_output502、storage_io500、storage_corrupt500、kb_busy409。为新码编写固定中文文案，不包含文件路径、输入值、上游原文或密钥。接收任务后后台失败通过GET的job.error表达，不能把查询正常返回误判为成功完成。

## D7 页面行为

共享typed客户端+可取消轮询/组件；列表页auto全音频与详情页lecture都走新job，文档路径不变。上传中、已接收、转写中、失败/可恢复、取消中、完成文案分开；仅completed获取result并触发一次当前job的onSuccess/填入考点框。刷新用GET列表找回最近任务，不自动重复提交/重试；切科/卸载后旧poll与迟到result不能更新新科，AbortController取消本地poll不等于取消服务器job。失败、完成或取消后操作按钮有一致恢复，支持显式继续和取消，不把job.error隐藏在通用服务不可用提示中。

## D8 最终验收必须实际证明

65秒provider延迟的真Next/FastAPI/浏览器job成功；断网/刷新后可找回；幂等请求与重复retry只有一worker；跨用户/跨科无互读；片段乱序完成和同句重复仍正确；坏片重试不重调成功片；发布中断三分支；cancel/shutdown与fork锁；ZIP无.asr_jobs；旧文档/短音频/API语义不回退；真实媒体四录音规划与完整45分钟fake-provider job；一次独立真实SF smoke（或精确的外部阻塞记录）。禁止删除断言/skip必要场景/用fake的速度证明真实长调用不会超时。

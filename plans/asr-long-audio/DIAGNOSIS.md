> 历史调查原文：当时只读、未授权编码；当前新增授权由START_ASR_R1.txt与CONTRACTS.md定义。测试事实仍有效。

# 课堂长录音 ASR：只读调查与实施建议

日期：2026-10-22（Asia/Shanghai）。本文件为方案，不是编码授权。本次未修改项目现有源码、配置、真实学习材料或录音原件；未重启服务。只在本临时目录创建测试脚本、音频切片和无密钥结果。临时阿里请求没有持久化供应商配置。

## 1. 结论与证据等级

本次首要缺陷是长时间同步 ASR 经前端代理等待响应，而 Next rewrite 默认约30秒超时。45分钟原录音在硅基流动实际成功，不是此次被其文件大小门槛拒绝。切片仍值得实现，但必须与后台任务、进度和结果查询一起设计；仅切片后在原HTTP请求里串行等所有结果，仍会超时。

尚未取得用户当时的浏览器Network记录和完整终端历史日志，因此不声称追溯证明了每一次报错；以下独立复现、现有转写文件、实际供应商耗时共同支持代理超时为本次首要原因。

### 实际测量

| 测试 | 结果 |
|---|---|
| 当前配置 | SiliconFlow，Qwen/Qwen3-ASR-1.7B，https://api.siliconflow.cn/v1 |
| 原录音 | 10月22日.m4a，50,786,002字节，2715.755秒（45分15.755秒），AAC，48kHz，双声道 |
| 同编码20秒片段直连供应商 | HTTP200，1.216秒，103字 |
| 45分钟原录音，保持项目相同请求字段直连 | HTTP200，63.551秒，14039字 |
| 安装版Next真实proxyRequest转发33秒延迟本机fixture | 30.069秒返回HTTP500 / Internal Server Error |
| 同fixture直接后端对照 | 33.014秒返回HTTP200 |
| 项目真实readSubjectFailure处理上述500 | 服务暂时不可用，请稍后重试。 |
| 当前生产构建配置 | experimental.proxyTimeout未配置，默认30秒 |
| 原录音临时分片 | 16片，16kHz/单声道/16bit WAV，连续覆盖2715.755秒 |
| 切片最大实际文件 / Base64大小 | 5,760,420 / 7,680,560字节 |
| 第0/7/15片直连硅基流动 | 全部HTTP200；约6.151/6.113/1.222秒 |

只抽测首、中、末三片，不宣称16片全部转写完成，也未对完整识别准确率进行人工逐字评估。测试固定180秒切片为可行性原型，不包含下面建议的静音择点。

### 后台已有成果

调查开始前，以下文件已经存在：

- `/home/albert/selflearn/selflearn/data/user/workspace/subjects/偏微分方程/materials/lecture/10月22日.m4a.transcript.txt`：41017字节、14037字符。
- 同目录 `10月22日 2.m4a.transcript.txt`：29201字节、10401字符。

对应原音频摘要与Windows录音原件一致，保存时间早于本轮调查。说明网页报错不等于后台转写未完成；不要用同名反复重传推断转写功能是否成功。

### 为什么“模型测试通过”没有提前发现

`deeptutor/services/config/test_runner.py:480`的STT测试只上传1秒静音，验证连接/鉴权/协议。这不能验证45分钟录音的处理耗时、完整链路超时或长音频限制。设置测试走voice适配器，科目录音走`services/asr/transcribe.py`独立实现，两处配置与协议行为也存在分叉。

## 2. 现有代码对应关系

- `web/proxy.ts`：科目上传进入rewrite，只有全局knowledge的create/upload使用专用流式路由。
- `web/next.config.js`：设置了210MiB请求体克隆限制，但未设置proxyTimeout；体积上限与等待超时是不同问题。
- `web/node_modules/next/dist/server/lib/router-utils/proxy-request.js:33`：默认proxyTimeout=30000。router-server调用该函数时读取experimental.proxyTimeout。
- `web/lib/subject-results.ts:95`：非结构化5xx转换成用户看到的固定提示。
- `deeptutor/services/asr/transcribe.py:155`：整文件multipart请求；不探测时长、不分段、不重试；默认httpx timeout为300秒。该值不等于整条前端链路可等待300秒，也不是严格总墙钟deadline。
- `deeptutor/api/routers/subjects.py:245`：一个HTTP请求内逐文件等待所有ASR，完成后才返回。
- `deeptutor/api/routers/subjects.py:293`：供应商非200统一投影为provider_unavailable，丢失可供安全分类的尺寸/鉴权/限流原因。
- `deeptutor/subjects/uploads.py:1030`：成功后以既有事务发布原音频和同名`.transcript.txt`。这个保护应保留。
- `deeptutor/utils/document_validator.py`：项目原始文件上限200MiB，大于部分供应商单请求限制。

## 3. 官方限制调研

这是供应商、接口和模型服务的限制组合，不是“参数规模1.7B决定只能上传10MB”。SiliconFlow的Qwen/Qwen3-ASR-1.7B与百炼qwen3-asr-flash也不是同一个API产品。

| 平台/接口 | 官方限制与接口差异 |
|---|---|
| SiliconFlow /audio/transcriptions | 文档写50MB、1小时。文档MB单位未精确定义字节；本次50,786,002字节实际被接受，不能武断按50,000,000字节判定此次失败 |
| 百炼 qwen3-asr-flash | 10MB、5分钟；兼容模式走/chat/completions，input_audio为URL/Base64；响应在choices/message/content，不是multipart /audio/transcriptions |
| 百炼 qwen3-asr-flash-filetrans | 2GB、12小时；DashScope异步提交、轮询和结果下载，需要可访问音频URL；不能仅换model字符串 |
| Groq文件转写 | 文档标账户25MB免费档/100MB开发档，同时直接附件限25MB，较大文件需URL；需要区分传输方式 |
| Google Speech-to-Text v1 | 本地内容请求10MB，同步约1分钟；长任务通常使用Cloud Storage URI，异步可到480分钟 |

官方来源：

- [SiliconFlow文件转写](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post)
- [百炼ASR模型与规格](https://help.aliyun.com/zh/model-studio/asr-model/)
- [百炼Qwen-ASR协议](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)
- [百炼非实时语音识别](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)
- [Groq语音转写](https://console.groq.com/docs/speech-to-text)
- [Google v1配额与限制](https://docs.cloud.google.com/speech-to-text/docs/v1/quotas)

阿里测试：现有项目的multipart路径返回404；按官方chat音频协议测试，北京与新加坡均返回401 invalid_api_key。本轮不能确认所给密钥在百炼ASR上的有效性，不应据此判断阿里模型不可用。没有将密钥写入项目、报告或命令行。

## 4. 推荐解决方案

### 4.1 优先修正等待链路

推荐直接做“上传入队→后台转写→轮询查询→完成发布”，消除浏览器连接寿命与录音总处理时长的耦合。

建议新增、与旧接口共存：

- POST `/api/v1/subjects/{subject_id}/asr/jobs`：流式接收文件，完成大小/归属/名称检查并保存临时输入后，返回202及job_id，不等待模型。
- GET `/api/v1/subjects/{subject_id}/asr/jobs/{job_id}`：返回状态、阶段、已完成片数/总片数、已完成音频时长及安全错误。
- POST 同job的`/cancel`：请求取消；待实际在途请求/媒体子进程清理完成，再进入cancelled。
- POST 同job的`/retry`：验证输入摘要、参数和模型身份后续跑失败片段，复用已完成片段。

新上传需要Next专用流式路由，复用现有forwardBackendUpload的传输原则，并从rewrite matcher中精确排除该路径；保留认证Cookie/headers传递及后端require_auth。不能因绕过Proxy而绕过后端授权。

若先做极小止血，可先给现有科目上传增加专用流式转发并设置明确的有界等待预算；或临时提高proxyTimeout（如600秒）验证链路。后者需要重新构建/重启、会影响其他代理路由，且不能稳定覆盖多文件累计耗时，不作为最终架构。

### 4.2 探测并按供应商能力切分

单次请求同时满足：实际上传字节、音频时长、格式、采样要求、协议编码后的大小及请求预算。

- 输入原件不覆盖；工作区保留原始文件名、实际size、sha256和ffprobe媒体信息。
- 根据provider+protocol+model的能力表选择规则，不按模型名中的Qwen盲猜，不对全部供应商硬编码10MB。
- 首版通用默认目标片长180秒。优先在上限前约10秒的静音区找切点，无静音时按最大采样数切分。
- 采用16kHz单声道PCM16 WAV作为已验证的通用基线；本次180秒片约5.76MB，Base64约7.68MB，为阿里10MB编码后预算留出余量。不要把4分钟WAV当然视为满足10MB Base64限制。
- 已是有损AAC的原录音，转换不等于恢复无损音质；测试确认声道混合和课程术语识别效果。
- 有明确格式能力的供应商可用FLAC等减少上传，但不能只重命名扩展名；最终文件必须重新探测并检查实际size/duration。
- 单片任一维度超限就继续细分。对未知自定义供应商使用明确的保守限制/用户配置，不把一次短音频测试当成无限上传能力。
- ffmpeg/ffprobe使用可配置的可信绝对路径、固定参数列表、不经shell；媒体处理需有超时、并发和输出大小限制。当前Ubuntu没有PATH中的原生ffmpeg/ffprobe；本次借用已有Windows二进制，仅写临时目录。正式实现需显式声明依赖，不能静默下载安装。

### 4.3 顺序与边界：独立于完成先后

每份原录音建一个manifest，至少保存：

```json
{
  "manifest_version": 1,
  "job_id": "uuid",
  "subject_id": "原有科目标识",
  "file_order": 0,
  "source_name": "10月22日.m4a",
  "source_sha256": "...",
  "duration_ms": 2715755,
  "profile_id": "...",
  "model": "Qwen/Qwen3-ASR-1.7B",
  "protocol": "openai_audio_multipart",
  "config_fingerprint": "不含密钥的配置摘要",
  "chunks": [
    {"index": 0, "start_sample": 0, "end_sample": 2880000,
     "sample_rate": 16000, "status": "completed", "text_path": "chunk-0000.txt"}
  ]
}
```

例中2880000为恰好180秒的设计示意；本次ffmpeg原型的实际边界来自wav采样数，见chunk_manifest.json，不把示意值伪称实测值。

- 首版逐片串行，默认供应商并发1；即使将来并行，也只按file_order、时间范围和数字index合并，不按HTTP完成顺序，不按未补零文件名排序。
- 以采样数校验首片从0开始、相邻区间连续、末片覆盖末尾、没有缺片或重复提交；毫秒只用于显示，避免逐段舍入累计误差。
- 每段结果写入独立checkpoint。重试不向总文本盲目追加，同一index只取一份成功结果。
- 每个原录音生成一份最终完整transcript；多份不同录音按用户选择顺序保留独立成果，不把它们混成同一个文件。
- 首版默认静音择点、无重叠，便于证明完整覆盖和避免重复。若加入重叠，必须另存请求区间/核心区间；有时间戳时按核心区间裁剪，无时间戳时只能保守处理接缝。不能全局删除相似句，课堂本来就可能重复强调。
- 合并是确定性的文本拼接，不让LLM润色重排原文；任何可选整理应另存为派生成果。

### 4.4 状态、恢复和发布

状态为queued/running/completed/failed/cancelled；运行阶段为probing/segmenting/transcribing/merging/publishing。

- 进度表示完成片数及已完成音频时长；不伪造供应商内部识别百分比。
- job输入/切片/manifest存在私有任务目录，不放公开outputs，且不混入科目导出。
- 配置选定后固定provider/model/协议/语言/切分策略。恢复时配置不兼容应明确拒绝，不能悄悄换成当前全局模型拼接。
- 所有片段及覆盖校验通过后，调用既有commit_transcripts保护，事务发布原音频与原文件名.transcript.txt。失败保留原有完成文件，不以半篇文本覆盖它们。
- 202仅表示已接收任务，不显示“转写完成”；completed必须意味着正式文件已提交，且这仍不代表索引ready。
- 跨请求的活动所有权应与现有subject_operations衔接；HTTP返回后活动不能提前释放。科目删除、重复上传、导出与任务仍应遵守互斥/一致性要求。
- 不能只依赖FastAPI进程内BackgroundTasks并声称可恢复；任务状态与checkpoint要持久化。重启后running需识别为interrupted/recoverable，不冒充完成。

### 4.5 分类错误与有界重试

在保留C02固定安全消息的前提下，区分：文件/时长超限、格式无效、鉴权/权限、限流、超时、供应商不可用和本地IO。不把所有400/401/413都变成“稍后重试”。

- 401/403：停止，提示检查该ASR配置，不自动重试。
- 已确认尺寸/时长超限：重新规划更小片段，次数有界；不原样重发同一超限文件。
- 429：尊重Retry-After，指数退避+抖动，限定次数和总时间。
- 短暂5xx/超时：有限重试，只重试失败片段；已成功checkpoint不重转。供应商POST超时可能已计费，不能承诺外部调用恰好一次。
- 日志保存job_id、片号、状态码、耗时、供应商trace_id和经白名单归一化的错误码；不记录Authorization、密钥、整个原始错误体或完整转写正文。

### 4.6 阿里接入作为可选独立单元

先解决当前已可用的SiliconFlow长录音链路。若继续支持阿里，新增明确的dashscope_chat_audio适配器，构造input_audio并解析choices；不能仅改base_url或把录音模块直接换成读取整文件bytes的voice实现。

设置测试与课堂上传应共用配置解析及协议适配，但保留大文件流式处理。长录音Filetrans另需异步服务适配及可访问URL/对象存储，不能只改model_id，本轮不建议作为必需前置。

## 5. 建议按一个合并阶段实施，内部拆成六个单元

| 单元 | 目标及允许范围（建议） | 完成证据 |
|---|---|---|
| A1 诊断与能力契约 | asr模块、voice/config解析的必要接缝、专用测试；先固定错误/限制/协议定义 | 设置测试与真实转写选择同一profile；尺寸/时长/编码预算正反例；不泄漏凭据 |
| A2 媒体与切片 | 新asr媒体探测/切片模块及测试；不改科目存储通用规则 | 四个真实原录音均能规划；连续采样覆盖、大小限制、坏媒体/超时/取消；原件不变 |
| A3 持久任务执行 | 新asr任务模块、subject_operations必要接缝、专用测试 | 分片失败、重试、乱序完成、重复请求、重启恢复、模型切换全部有行为测试 |
| A4 API与上传转发 | 新ASR job路由、Next精确流式上传路由及matcher、相关测试 | 202立即返回；60秒以上任务不因30秒断开；认证、跨科、上传断开和取消测试 |
| A5 页面与最终发布 | 既有科目上传UI、subject-results及commit_transcripts必要接缝 | 进度/失败/继续/取消准确；所有片完成才发布；旧完成文本失败不变；ASR不假称索引ready |
| A6 独立验收 | 新长音频真实入口/浏览器测试及方案文档；不重写历史receipt | 本次45分钟录音成功闭环、刷新恢复、不串科、故障片断点恢复、来源原件不变 |

上述是建议授权范围，尚未授权编码。不要把“必要接缝”解释成无限重构；实际开工前再固化具体文件白名单、响应schema和新增测试清单。

## 6. 验收标准

1. 离线真实Next延迟fixture证明超过30秒的后台工作不会造成前端误报；不能只提高供应商timeout。
2. 同一45分钟录音经任务接口完成，UI显示真实进度，正式转写文件可读；浏览器刷新/断线后仍可按job_id找回状态。
3. 16片或静音策略实际规划出的全部片段连续覆盖原音频；乱序完成也按数字片号/时间顺序合并。
4. 注入中段失败，只重试该段；没有“少一段却已完成”或重复拼接。
5. 在上传、分片、请求及发布各阶段取消，均最终释放活动和临时进程，不删除旧成功文件。
6. 明确覆盖供应商超限、401、429、5xx、网络超时、坏响应、ffmpeg缺失/失败，以及同名原件替换。
7. 人工听查片段接缝、课程专业词和首尾，不能把HTTP200当作识别准确率已验证。
8. 项目测试继续使用隔离runner；真实供应商抽样单独记录，不改历史第一阶段签收，不使用真实学习目录当自动化fixture。

## 7. 本轮证据文件

- silicon_results.json：短样本及原45分钟直连实际状态/耗时/文本摘要。
- proxy_results.json：默认代理30秒500及直接后端成功对照。
- chunk_manifest.json：16片采样范围、size、编码后size及摘要。
- chunk_probe_results.json：首、中、末片实测结果。
- aliyun_results.json、aliyun_singapore_results.json：阿里协议/鉴权测试，未含密钥。
- readonly_verification.json：189项源码无漂移、settings内容无新增变化。

临时目录不具备长期归档承诺；如需正式执行包，再由用户授权后写入项目计划目录。当前没有实施修复。

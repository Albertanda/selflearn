# 阿里云百炼 ASR

本轮在 ASR-R1 已验收的切片、恢复、顺序合并和发布机制上增加供应商协议支持，
不改写历史验收、数据基线或配置事故记录。不包含统一模型发现功能。

## 配置和协议

- STT 供应商：`aliyun`，界面名“阿里云百炼 (DashScope)”。
- 首个支持并验证的模型：`qwen3-asr-flash`。
- 北京 API base：`https://dashscope.aliyuncs.com/compatible-mode/v1`。
  也支持控制台提供的业务空间专属 base；地域必须与密钥一致。
- 适配器：`qwen_asr`；请求样式：`qwen_chat_audio`。
- POST `chat/completions`，使用 `messages[].content[].input_audio.data`
  的 WAV Data URI，解析 `choices[0].message.content`；合法空字符串是静音成功。
- 不把 OpenRouter 的 `base64_json` 或 multipart 请求误发给该接口。
- 密钥作为不透明字符串完整保存，不能用只允许字母数字的正则截取；可能包含点号。

官方参考：
<https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference>

## 输入边界

厂商上限 300 秒 / Base64 后 10MB。原音频单请求保守限 7,490,000 字节，
序列化 JSON 再检查 10,000,000 字节。课程任务继续采用不超过 180 秒的
16kHz 单声道 PCM16 WAV；只编码当前片段，不把完整课程放入 Base64。
401/403 不重试；限流、超时和 5xx 沿用现有有界重试；413 交由任务层细分。

设置页测试和麦克风复用同一协议；短音频 WebM/MP3 等先转为 WAV。
短音频入口超限时返回清晰错误，课程长录音应走已有异步任务入口。
旧同步转写入口也按当前 STT 协议派发，不会静默回到 multipart。

## 媒体依赖

依次使用环境变量、`data/user/settings/asr_media.json`、原生 PATH。
本机配置仅保存可执行文件路径，不把用户 Windows 路径硬编码到产品源码。

```json
{
  "version": 1,
  "ffmpeg_bin": "/absolute/path/to/ffmpeg",
  "ffprobe_bin": "/absolute/path/to/ffprobe"
}
```

`SELFLEARN_FFMPEG_BIN` / `SELFLEARN_FFPROBE_BIN` 优先。
显式路径失效时返回依赖不可用，不偷偷切换另一套工具。
已有 Windows `.exe` 工具按现有 WSL 路径转换逻辑使用。

## 验证

通过 `scripts/run_tests_isolated.py` 运行 ASR、voice、配置及旧同步转写回归。
新增 `tests/asr/test_qwen.py` 验证实际请求格式、大小边界、错误/重试、WebM
转换、持久媒体路径及逆序请求后的有序发布。

显式真实验收脚本（会调用模型并产生费用）：

```bash
.venv/bin/python scripts/aliyun_asr_acceptance.py \
  --key-file /absolute/path/to/key.txt \
  --recording /absolute/path/to/lecture.m4a \
  --output-dir .phase1-evidence/reviews/a-new-unused-name
```

密钥文件只放完整密钥，脚本不输出密钥、上游错误原文。
脚本使用临时学习空间、复制录音、核对原文件摘要，并保留转写文本与安全统计。
成功转写不是字词准确率评测，也不表示所有阿里云 ASR 型号已受支持。

本轮实际结果与配置变更凭据见
`.phase1-evidence/reviews/aliyun-asr-20261023/`；旧 ASR-R1 验收保持原样。

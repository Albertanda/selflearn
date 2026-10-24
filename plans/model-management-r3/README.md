# MM-R3：供应商分层选择、思考强度与默认模型

派发日期：2026-10-24（Asia/Shanghai）。状态：已规划，尚未实施。一个阶段连续执行，不逐卡交回用户。

前置是协调者的 MD-R2 补修及独立验收，见 `.phase1-evidence/reviews/MD-R2-20261024/REVIEW.md` 和 `review.json`。原 Harness 报告保留，不修改其 accepted=false 历史结果。本规划不属于 S16，也不自动扩大到科目 UI/知识库功能。

## 用户体验目标

1. 聊天选择模型：第一层选择**供应商/连接**，第二层仅列该连接模型。按钮常驻显示“供应商 · 自定义模型名”，同名 DeepSeek 原厂/阿里模型可区分。多个相同供应商连接用配置名区分，不合并凭据。
2. 聊天输入区直接选择思考强度；模型设置页可设该模型默认强度。优先显示供应商真实原生档位，DeepSeek Flash/Pro 应有 low/high/max 三档。切换模型后不带上另一模型不支持的值。用户的跨厂商旧档位可按有依据规则映射，并明确显示实际档位。
3. 设置→模型首项新增**默认模型**，排在大语言模型之前。中文 LLM 名称统一为**大语言模型（LLM）**。一个默认 LLM 供常规对话/标题/搜索词等现有 LLM 消费者使用，不增加分散的标题/OCR/重排等新服务。为现有 embedding/STT/TTS/vision/imagegen/videogen 各提供默认模型；search 选择默认搜索服务 profile。
4. 原“应用”保留，但浏览/编辑模型不再暗中选择默认。默认页使用明确“保存默认设置”动作，只更新默认引用，不顺带保存其他页面未完成配置。

## 确认的原因

- ModelSelector 当前把 options 平铺，只显示模型名，缺少连接层级。
- web/lib/reasoning-effort.ts 把 DeepSeek/Qwen 等当 binary，只列 minimal/high；列表不含当前 deepseek-flash ID。
- 后端 reasoning_params.py 也有同样旧模式，minimal 甚至被当关闭思考，而 DeepSeek 现在将 minimal 映射 low。不能只扩前端下拉。
- MD-R2 未收录 DeepSeek `/models` 的 effort.supported_levels/default_level；本阶段补数据及前后端共享策略。
- LLM options 响应没有思考能力；聊天公开 config 严格 forbid 未知字段。新增聊天控件必须扩正式请求契约，不能随便塞 config 后被后端拒绝。
- ServiceConfigEditor 浏览 profile/model 时直接修改 draft.active_*。这导致编辑选中项与默认项混用，必须分离本地编辑选择与持久默认引用。

详见 [CONTRACTS.md](CONTRACTS.md)、[RESEARCH.md](RESEARCH.md)、[EXPLORATION.md](EXPLORATION.md)。

## 阶段内部单元

| 卡 | 内容 | 主要依赖 |
|---|---|---|
| M3-00 | 到达快照和隔离证据入口 | 无 |
| M3-01 | 思考能力契约、官方策略和元数据 | 00 |
| M3-02 | 各协议思考参数映射 | 01 |
| M3-03 | 每轮覆盖、会话记忆和重新生成 | 01、02 |
| M3-04 | 两层供应商/连接模型选择 | 00 |
| M3-05 | 聊天强度控件和模型默认强度设置 | 01、03、04 |
| M3-06 | 默认引用专用 API 与并发保护 | 00 |
| M3-07 | 默认页与编辑选择分离 | 06 |
| M3-08 | 导航、中文名称与应用说明 | 07 |
| M3-09 | 全阶段行为/浏览器/回归交付 | 02–08 |

每卡的目标、证据、范围和完成条件见 [TASKS.json](TASKS.json)。[START_MM_R3.txt](START_MM_R3.txt) 是直接粘贴的开工指令。

真正只有开关的模型不能凭界面造出三档推理能力；支持 thinking budget 的模型可以提供注明“预算预设”的低/中/高。主流枚举多档模型必须完整提供其真实档位，不能继续只用 minimal/high。无信息的学校网关保留未知/继承，不从模型别名猜能力。

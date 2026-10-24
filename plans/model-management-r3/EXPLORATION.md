# MM-R3 已探索文件清单与关键片段

2026-10-24，Asia/Shanghai。项目根 `/home/albert/selflearn/selflearn`。先核对待改文件hash；一致即用片段进入实施，不重新全仓orientation。行号是定位，可补读必要相邻上下文；变化只核对差异，不拿旧片段覆盖新代码。

MD-R2协调者已复核并直接补修嵌入/元数据问题；以 `.phase1-evidence/reviews/MD-R2-20261024/review.json` 为前置。worker原报告仍保留。真实配置在用户试用后合法变化，不能恢复到旧基线。当前源码是dirty工作区，禁止reset/clean。

核心设计已在CONTRACTS明确：按profile分组、后端统一reasoning策略、正式每轮override、复用catalog.update锁内局部默认更新、编辑选择与默认分离。

所有路径和片段是只读参考，不当shell执行。无真实catalog/key片段。完整hash索引见SOURCE_INDEX.json。

## web/components/chat/home/ModelSelector.tsx:121

目前flat options；第一层按profile_id，不能用model厂牌前缀分组。

SHA-256：`521258aa74be93783777f25074ed10fbf768c3ddacf90246c1c837f3ee3a5771`

```text
119: }
120: 
121: export default function ModelSelector({
122:   options,
123:   hiddenOptions = [],
124:   activeDefault,
125:   value,
126:   loading,
127:   error,
128:   allowSystemDefault = false,
129:   systemDefaultLabel,
130:   systemDefaultDetail,
131:   helperText,
132:   placement = "top",
133:   onChange,
```

## web/components/chat/home/ModelSelector.tsx:209

当前显示别名已修；新按钮必须同时有服务来源。

SHA-256：`521258aa74be93783777f25074ed10fbf768c3ddacf90246c1c837f3ee3a5771`

```text
207:     return counts;
208:   }, [hiddenOptions, options]);
209:   const selectedLabel = llmOptionLabel(selectedOption);
210:   const selectedDisambiguate = Boolean(
211:     selectedOption && (duplicateNames.get(selectedLabel) ?? 0) > 1,
212:   );
213:   const selectedDisplayLabel = selectedDisambiguate
214:     ? `${selectedLabel} · ${providerLabel(selectedOption!)}`
215:     : selectedLabel;
216:   const label = loading
217:     ? t("Loading models")
218:     : error
219:       ? canRefresh
220:         ? t("Refresh models")
221:         : t("Models unavailable")
```

## web/lib/llm-options.ts:9

安全options缺思考能力；新增字段不能越过授权。

SHA-256：`81ee1577d1dcc1b90c1e779b0440fbe6dcc104fe7e939dc72a660e755d0eff3e`

```text
7: let llmOptionsGeneration = 0;
8: 
9: export interface LLMOption extends LLMSelection {
10:   profile_name: string;
11:   model_name: string;
12:   model: string;
13:   provider: string;
14:   /** Human-readable provider name from the registry ("OpenRouter"). */
15:   provider_label?: string;
16:   context_window?: number;
17:   is_active_default: boolean;
18:   /** Presentation metadata; omitted means visible. */
19:   visible_in_picker?: boolean;
20:   /** Set only on entries returned through hidden_options. */
21:   hidden?: boolean;
```

## web/hooks/useLLMOptions.ts:19

single-flight和迟到响应防护应保留。

SHA-256：`dbebf2f954e9ae99d59905447d87d0623a355a5c3e5ed9978f3acf2a26ba3a23`

```text
17: 
18: /** Owns model-catalog loading independently from the chat page lifecycle. */
19: export function useLLMOptions() {
20:   const [state, dispatch] = useReducer(
21:     reduceLLMOptionsState,
22:     INITIAL_LLM_OPTIONS_STATE,
23:   );
24:   const latestRequestRef = useRef(0);
25:   const [loadOptions] = useState(() => createSingleFlight(listLLMOptions));
26:   const mountedRef = useRef(true);
27: 
28:   useEffect(() => {
29:     mountedRef.current = true;
30:     return () => {
31:       mountedRef.current = false;
```

## web/lib/reasoning-effort.ts:37

现有静态表是binary且漏Flash；应改消费后端统一能力。

SHA-256：`d40ebf1f5243b674aee499c47dbbd12d1d211eac566c892fd628fe1864073222`

```text
35:   "github_copilot",
36: ]);
37: const BINARY_THINKING_PROVIDERS = new Set([
38:   "deepseek",
39:   "volcengine",
40:   "volcengine_coding_plan",
41:   "byteplus",
42:   "byteplus_coding_plan",
43:   "dashscope",
44:   "minimax",
45: ]);
46: 
47: function includesAny(value: string, patterns: string[]): boolean {
48:   return patterns.some((pattern) => value.includes(pattern));
49: }
```

## web/lib/reasoning-effort.ts:144

确认的旧二档入口，不止改下拉文案。

SHA-256：`d40ebf1f5243b674aee499c47dbbd12d1d211eac566c892fd628fe1864073222`

```text
142:       ]);
143:     if (supported) {
144:       return options(["minimal", "high"], current);
145:     }
146:     if (BINARY_THINKING_PROVIDERS.has(provider)) {
147:       // Deliberately no selector for the rest — VolcEngine/BytePlus thinking
148:       // models are switched on by the backend from the spec's
149:       // reasoning_model_patterns, so an explicit per-model choice here would
150:       // duplicate a decision the registry already owns.
151:       return options([], current);
152:     }
153:   }
154: 
155:   if (OPENAI_PROVIDERS.has(provider) || provider === "custom") {
156:     const isGpt5OrCodex = includesAny(modelName, ["gpt-5", "codex"]);
```

## deeptutor/services/llm/reasoning_params.py:141

现有minimal误当关闭；映射和开关分开。

SHA-256：`2d50bdb359a34906320c903aec576c3e0e5e0abe95dd3c8b3a9c1988c2f36846`

```text
139: 
140:     if thinking_style and resolved_effort is not None:
141:         thinking_enabled = semantic_effort != "minimal"
142:         extra = _THINKING_STYLE_MAP.get(thinking_style, lambda _enabled: None)(thinking_enabled)
143:         if extra:
144:             kwargs.setdefault("extra_body", {}).update(extra)
145:     elif thinking_style and _disable_thinking_by_default(provider_name, model_name):
146:         extra = _THINKING_STYLE_MAP.get(thinking_style, lambda _enabled: None)(False)
147:         if extra:
148:             kwargs.setdefault("extra_body", {}).update(extra)
149: 
150:     return kwargs
151: 
152: 
153: __all__ = [
```

## deeptutor/services/provider_registry.py:322

reasoning pattern也漏deepseek-flash；不要新增另一套歧义判定。

SHA-256：`403d54a602c4cbff47e5caec34e0e7d2b216183a1517ba178eb8590d84964d7a`

```text
320:     ),
321:     ProviderSpec(
322:         name="deepseek",
323:         keywords=("deepseek",),
324:         env_key="DEEPSEEK_API_KEY",
325:         display_name="DeepSeek",
326:         backend="openai_compat",
327:         default_api_base="https://api.deepseek.com",
328:         thinking_style="thinking_type",
329:         reasoning_model_patterns=("deepseek-v4-pro", "deepseek-reasoner"),
330:     ),
331:     ProviderSpec(
332:         name="gemini",
333:         keywords=("gemini",),
334:         env_key="GEMINI_API_KEY",
```

## deeptutor/services/model_discovery/metadata.py:316

候选目前只解析限制/模态，未取effort对象。

SHA-256：`ccdc4f6997efaae7ae6d9b089b28317fc432a27da658e76ddfa6082069f2c190`

```text
314: 
315: 
316: def deepseek_parameters(
317:     raw: Mapping[str, Any],
318:     *,
319:     source_url: str,
320:     checked_at: datetime | str,
321:     kind: str = "provider_api",
322: ) -> ModelParameters | None:
323:     values = {
324:         "context_window": raw.get("context_window"),
325:         "max_output_tokens": raw.get("max_output_tokens"),
326:         "input_modalities": raw.get("input_modalities"),
327:         "output_modalities": raw.get("output_modalities"),
328:     }
```

## deeptutor/services/model_discovery/types.py:369

增加能力摘要需要to_dict/cache/parser同改。

SHA-256：`a96919d82afff7fce7d6a39910bf39c0da5fb35a8f8a102b6a69357e2b4e43f9`

```text
367: 
368: @dataclass(frozen=True, slots=True)
369: class DiscoveredModel:
370:     id: str
371:     name: str
372:     services: tuple[str, ...] = field(default_factory=tuple)
373:     classification: Classification = Classification.UNKNOWN
374:     runtime_compatibility: RuntimeCompatibility = RuntimeCompatibility.UNKNOWN
375:     reason_code: str | None = None
376:     source: ModelSource = ModelSource.REMOTE
377:     callability: str = "not_tested"
378:     context_window: int | None = None
379:     parameters: Any | None = None
380:     resource_name: str | None = None
381:     deployment_mapping_required: bool = False
```

## deeptutor/services/model_discovery/cache.py:35

协调者已升3以刷新嵌入资料；新字段需考虑cache升级。

SHA-256：`392f91a76564c515af4fc65f07f93e2132423eecdcdc43fd781be6cd60ff6f40`

```text
33: )
34: 
35: CACHE_SCHEMA_VERSION = 3
36: MAX_CACHE_ENTRIES = 128
37: FRESH_SUCCESS_TTL = timedelta(hours=1)
38: EMPTY_SUCCESS_TTL = timedelta(minutes=5)
39: FAILURE_COOLDOWN = timedelta(seconds=60)
40: STALE_RETENTION = timedelta(days=7)
41: 
42: 
43: class CacheIOError(RuntimeError):
44:     pass
45: 
46: 
47: @dataclass(slots=True)
```

## deeptutor/services/model_selection/llm.py:92

后端显示名称已经正确；添加reasoning_controls必须脱敏。

SHA-256：`f60ff82ec24da6a9240d1774c91c0b0f3148f5d15e8855d19b40e538752bd26d`

```text
90:                 "model_id": model_id,
91:                 "profile_name": profile_name,
92:                 "model_name": str(model.get("name") or model_value).strip(),
93:                 "model": model_value,
94:                 "provider": provider,
95:                 "provider_label": provider_label,
96:                 "is_active_default": (
97:                     profile_id == active_profile_id and model_id == active_model_id
98:                 ),
99:                 # Presentation metadata only. Authorisation and runtime
100:                 # resolution never consult this field.
101:                 "visible_in_picker": model_visible(model),
102:             }
103:             context_window = _coerce_int(model.get("context_window"))
104:             if context_window is None:
```

## deeptutor/multi_user/model_access.py:121

普通用户授权路径独立，不能只修admin。

SHA-256：`88d13a223317c4703d397b952cede28119dbc9f3b3bf6c5150472e205f594575`

```text
119: 
120: 
121: def allowed_llm_options() -> dict[str, Any]:
122:     user = get_current_user()
123:     if user.is_admin:
124:         from deeptutor.services.model_selection.llm import present_llm_options
125: 
126:         return present_llm_options(admin_catalog())
127:     options = [
128:         {
129:             "profile_id": item.get("profile_id"),
130:             "model_id": item.get("model_id"),
131:             "profile_name": item.get("name") or item.get("profile_id") or "LLM",
132:             "model_name": item.get("name") or item.get("model") or item.get("model_id"),
133:             "label": item.get("name") or item.get("model") or item.get("model_id"),
```

## deeptutor/services/llm/provider_core/anthropic_provider.py:390

新旧thinking模式已区分但强度未完整透传；修改限reasoning接缝。

SHA-256：`e8b966cb167e1e7da63505e374044174787282830fdf7960726f3b0026461d94`

```text
388:         # turned `none` into thinking ON with 4096 tokens.
389:         thinking_enabled = bool(effort) and effort not in _THINKING_OFF_EFFORTS
390:         effort_based = any(family in model_name for family in _EFFORT_BASED_FAMILIES)
391: 
392:         kwargs: dict[str, Any] = {
393:             "model": model_name,
394:             "messages": anthropic_msgs,
395:             "max_tokens": max_tokens,
396:         }
397: 
398:         if system:
399:             kwargs["system"] = system
400: 
401:         if thinking_enabled and effort_based:
402:             # These families reject enabled+budget_tokens with a 400 —
```

## deeptutor/services/llm/provider_core/openai_compat_provider.py:107

按现有wire扩参数，不引入新的全局HTTP客户端。

SHA-256：`f621b2459a5833e3b7592a62bdc8b2a6a8028e9ef5cf8100dca4624d97c806df`

```text
105: 
106: 
107: class OpenAICompatProvider(LLMProvider):
108:     """Unified provider for all OpenAI-compatible APIs.
109: 
110:     Receives a resolved ``ProviderSpec`` from the caller — no internal
111:     registry lookups needed.
112:     """
113: 
114:     def __init__(
115:         self,
116:         api_key: str | None = None,
117:         api_base: str | None = None,
118:         default_model: str = "gpt-4o",
119:         extra_headers: dict[str, str] | None = None,
```

## deeptutor/services/llm/provider_core/openai_codex_provider.py:68

专用Responses字段和validate边界保留。

SHA-256：`18627b7a40238f78f159bc7ad649a3cb26f07767a6abd33f95771217e4e1e74e`

```text
66:             "parallel_tool_calls": True,
67:         }
68:         if reasoning_effort:
69:             body["reasoning"] = {"effort": reasoning_effort}
70:         if tools:
71:             body["tools"] = convert_tools(tools)
72: 
73:         service = get_codex_oauth_service()
74:         async with service.inference_guard():
75:             try:
76:                 token = await self._load_token()
77:                 service.validate_runtime_profile(token, model_slug, reasoning_effort)
78:                 headers = _build_headers(token.account_id, token.access_token)
79:                 try:
80:                     content, tool_calls, finish_reason = await _request_codex(
```

## deeptutor/services/llm/config.py:96

单turn配置需保留MD-R2输出/输入容量，不修改全局catalog。

SHA-256：`e21bb72530c32f5e0ecf7cac2bbe77fc686652b735cb0d14d2cd59eab185b644`

```text
94: 
95: @dataclass
96: class LLMConfig:
97:     """LLM configuration dataclass."""
98: 
99:     model: str
100:     api_key: str
101:     base_url: str | None = None
102:     effective_url: str | None = None
103:     binding: str = "openai"
104:     provider_name: str = "routing"
105:     provider_mode: str = "standard"
106:     api_version: str | None = None
107:     extra_headers: dict[str, str] | None = None
108:     reasoning_effort: str | None = None
```

## deeptutor/services/model_selection/runtime.py:37

授权模型解析后设置scoped配置的明确接缝。

SHA-256：`6e136431769a53633270ae106e04b7d42e44d17b68c5c2819a3923869ec3314c`

```text
35: 
36: 
37: def activate_llm_selection(selection: Any) -> tuple[LLMConfig, Token[LLMConfig | None]]:
38:     """Resolve and install a scoped LLM config for the current async context."""
39:     config = resolve_llm_config_for_selection(selection)
40:     token = llm_config_module.set_scoped_llm_config(config)
41:     return config, token
42: 
43: 
44: def reset_llm_selection(token: Token[LLMConfig | None] | None) -> None:
45:     if token is not None:
46:         llm_config_module.reset_scoped_llm_config(token)
47: 
48: 
49: __all__ = [
```

## deeptutor/services/session/turn_runtime.py:1859

增加每轮覆盖应在解析所选模型后，finally仍reset。

SHA-256：`bb39d968989c0f3b791503173523de75f0d066309d1ee4fc78a31cb8e053c27c`

```text
1857:                     )
1858: 
1859:             llm_config, llm_scope_token = activate_llm_selection(payload.get("llm_selection"))
1860:             _history_ratio = 0.35
1861:             try:
1862:                 from deeptutor.services.settings.token_budget import (
1863:                     get_token_budget_settings,
1864:                 )
1865: 
1866:                 _budget = get_token_budget_settings()
1867:                 _history_ratio = (
1868:                     float(_budget.get("context_ratio", 0.7))
1869:                     if not _budget.get("enabled", True)
1870:                     else 0.35
1871:                 )
```

## deeptutor/services/session/turn_runtime.py:503

请求快照/regen要补强度，而非只UI记住。

SHA-256：`bb39d968989c0f3b791503173523de75f0d066309d1ee4fc78a31cb8e053c27c`

```text
501:         snapshot["memoryReferences"] = memory_references
502:     if llm_selection:
503:         snapshot["llmSelection"] = llm_selection
504:     return {"request_snapshot": snapshot}
505: 
506: 
507: def _format_question_bank_entry(entry: dict[str, Any]) -> str:
508:     """Render a single Question Bank entry as a structured Markdown block."""
509:     lines: list[str] = []
510:     title = str(entry.get("session_title", "") or "Untitled session")
511:     difficulty = str(entry.get("difficulty", "") or "").strip()
512:     qtype = str(entry.get("question_type", "") or "").strip()
513:     is_correct = bool(entry.get("is_correct"))
514: 
515:     badges: list[str] = []
```

## deeptutor/runtime/request_contracts.py:35

extra=forbid：不能随便塞一个config字段指望后端使用。

SHA-256：`ea011e49f57b6b1fb157cbb2821d6bf04c605f5d755a6a7580142a5eff37986a`

```text
33: 
34: 
35: class ChatRequestConfig(BaseModel):
36:     model_config = ConfigDict(extra="forbid")
37: 
38: 
39: class DeepSolveRequestConfig(BaseModel):
40:     model_config = ConfigDict(extra="forbid")
41: 
42: 
43: class DeepQuestionRequestConfig(BaseModel):
44:     model_config = ConfigDict(extra="forbid")
45: 
46:     mode: Literal["custom", "mimic"] = "custom"
47:     topic: str = ""
```

## web/lib/unified-ws.ts:81

扩正式TS request contract和regen payload。

SHA-256：`c698bfd5bfceca8ab600c613b61f801fcc5c5b8dfb824a6a1e03533aad9dbacd`

```text
79:   mastery_path_id?: string;
80:   persona?: string;
81:   llm_selection?: LLMSelection | null;
82:   /** Edit-branching: when present (even as ``null``) the new user message
83:    *  attaches at this exact parent — creating a sibling rather than
84:    *  appending to the session tail. */
85:   parent_message_id?: number | null;
86: }
87: 
88: export interface SubscribeTurnMessage {
89:   type: "subscribe_turn";
90:   turn_id: string;
91:   after_seq?: number;
92: }
93: 
```

## web/context/UnifiedChatContext.tsx:90

会话选择、发送和快照的共同接缝。

SHA-256：`cefdc1d5b56e46f36456b2ec5ee0fc585149fce0d4685a059d176c29dc61d81d`

```text
88: } from "@/lib/subject-scope";
89: 
90: export interface SendMessageOptions {
91:   displayUserMessage?: boolean;
92:   persistUserMessage?: boolean;
93:   requestSnapshotOverride?: MessageRequestSnapshot;
94:   bookReferences?: BookReferencePayload[];
95:   /** Edit-branching: when set, the new user message is inserted as a
96:    *  sibling under this parent rather than appended to the session tail.
97:    *  ``null`` means "explicitly attach to the session root". */
98:   parentMessageId?: number | null;
99: }
100: 
101: export interface ChatState {
102:   sessionId: string | null;
```

## web/components/chat/home/ChatComposer.tsx:1084

共享picker及新强度组件插入附近，不重构整composer。

SHA-256：`86751e5ff759fb0fb629dfb987ad87f15e54c26191a072bd891b4d60e9e321ea`

```text
1082:                   />
1083:                 ) : null}
1084:                 <ModelSelector
1085:                   options={llmOptions}
1086:                   hiddenOptions={hiddenLLMOptions}
1087:                   activeDefault={activeLLMDefault}
1088:                   value={llmSelection}
1089:                   loading={llmOptionsLoading}
1090:                   error={llmOptionsError}
1091:                   onChange={onSelectLLM}
1092:                   onRefresh={onRefreshLLMOptions}
1093:                 />
1094:                 {contextBudget ? (
1095:                   <ContextBudgetChip budget={contextBudget} />
1096:                 ) : null}
```

## web/components/quiz/FollowupChatComposer.tsx:1

题目跟进必须实际发送一轮验收。

SHA-256：`b75a8ed093a3b9f06b642714ab6cb07b7e8b67e34a93518deb3a317ccef4a7f5`

```text
1: "use client";
2: 
3: /**
4:  * FollowupChatComposer — renders the SAME ``ChatComposer`` used on the
5:  * main chat page, but with its own local state pool and a send handler
6:  * that routes through ``QuizFollowupController`` instead of the unified
7:  * chat context. The follow-up tab uses this so the composer surface
8:  * (look, controls, @space popup, KB picker, attachments, LLM selector,
9:  * picker dialogs) matches the main chat composer exactly.
10:  *
11:  * Self-contained: loads its own KB / LLM lists, owns drag-and-drop +
12:  * attachment state, mounts the @space pickers internally.
13:  */
```

## web/components/quiz/QuizFollowupTabBody.tsx:9

跟进composer外层的状态/发送透传；避免只渲染控件。

SHA-256：`48e670d8efac393fb1b6da0b14906c3372dee80391a381e6f44cd9be727788df`

```text
7:  *
8:  * Layout: pinned context cards (question / your answer / AI judgment) →
9:  * scrollable chat thread → ``FollowupChatComposer`` (same chrome as the
10:  * main chat composer).
11:  *
12:  * State is owned by ``QuizFollowupProvider`` so closing/reopening the
13:  * tab — or toggling questions inside QuizViewer — keeps the thread
14:  * intact and is reflected in the QuizViewer follow-up badge.
15:  */
16: 
17: import {
18:   useCallback,
19:   useEffect,
20:   useLayoutEffect,
21:   useMemo,
```

## web/components/settings/SettingsContext.tsx:810

当前添加/浏览与active引用耦合，需local editing_selection。

SHA-256：`63dd057a7053652356aabbf0a8b1c5b4c5ab320b45d0eb210bf3a107988291b1`

```text
808:   );
809: 
810:   const addProfile = useCallback(
811:     (service: ServiceName) => {
812:       mutateCatalog((next) => {
813:         const target = next.services[service];
814:         const profileId = `${service}-profile-${Date.now()}`;
815:         const defaultBinding = service === "search" ? undefined : "openai";
816:         const defaultProvider = service === "search" ? "brave" : undefined;
817:         const providerKey =
818:           service === "search" ? defaultProvider : defaultBinding;
819:         const providerOption = (providers[service] || []).find(
820:           (p) => p.value === providerKey,
821:         );
822:         const providerLabel =
```

## web/components/settings/SettingsContext.tsx:1127

应用保留；Save/Apply需要正确revision与默认引用语义。

SHA-256：`63dd057a7053652356aabbf0a8b1c5b4c5ab320b45d0eb210bf3a107988291b1`

```text
1125:   }, [catalogEditable, draft, t]);
1126: 
1127:   const applyCatalog = useCallback(async () => {
1128:     setApplying(true);
1129:     try {
1130:       // Flush extensions (e.g. /settings/memory) first so their saved
1131:       // state is visible to any backend side-effects in /apply below.
1132:       const exts = Array.from(extensionsRef.current.values()).filter(
1133:         (e) => e.dirty,
1134:       );
1135:       await Promise.all(exts.map((e) => e.save()));
1136: 
1137:       // The catalog apply is only meaningful when editable; an extension-
1138:       // only flush should still produce a success toast.
1139:       if (catalogEditable) {
```

## web/components/settings/ServiceConfigEditor.tsx:418

证实浏览tab会改draft默认；所有诊断/重命名/预览定位要随之改。

SHA-256：`3541d9f183bff08ec91ba33f5a0b80cd44cbeeef29e901c13125e5e8d4c074dc`

```text
416:                       if (isEditing) return;
417:                       mutateCatalog((next) => {
418:                         next.services[service].active_profile_id = profile.id;
419:                         if (service !== "search") {
420:                           next.services[service].active_model_id =
421:                             profile.models[0]?.id ?? null;
422:                         }
423:                       });
424:                     }}
425:                     onDoubleClick={() => {
426:                       if (!isManagedProfile) startProfileRename(profile);
427:                     }}
428:                     onKeyDown={(e) => {
429:                       if (isEditing) return;
430:                       if (e.key === "Enter" || e.key === " ") {
```

## web/components/settings/ServiceConfigEditor.tsx:241

设置页与聊天不能维持两套不同档位表。

SHA-256：`3541d9f183bff08ec91ba33f5a0b80cd44cbeeef29e901c13125e5e8d4c074dc`

```text
239:             )
240:           : []
241:         : reasoningEffortOptions(
242:             activeProfile?.binding,
243:             activeModel.model,
244:             activeModel.reasoning_effort,
245:           )
246:       : [];
247: 
248:   const syncProviderModels = async (
249:     connection?: Pick<CatalogProfile, "binding" | "base_url" | "api_key">,
250:   ) => {
251:     if (service !== "llm" || !activeProfile || modelsSyncing) return;
252:     const binding = connection?.binding ?? activeProfile.binding ?? "";
253:     const baseUrl = connection?.base_url ?? activeProfile.base_url ?? "";
```

## web/lib/settings-nav.ts:80

新默认页置第一；中文LLM目前原样显示。

SHA-256：`f7db76cf1ea716472ce38d34f14a030bc3fb270fbe82af0d2a21d9848ee930fd`

```text
78: }
79: 
80: const MODEL_CHILDREN: SettingsLeaf[] = [
81:   {
82:     key: "llm",
83:     href: "/settings/llm",
84:     label: { zh: "LLM", en: "LLM" },
85:     blurb: {
86:       zh: "语言模型供应商与当前档位。",
87:       en: "Language model providers and active profile.",
88:     },
89:     icon: Brain,
90:     tile: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
91:     service: "llm",
92:   },
```

## web/components/settings/SettingsMain.tsx:13

导航和工具栏说明的接缝；不要移除应用。

SHA-256：`1a1a7f4f39da673e84ad8f35413dfa15da778afd5dd676b02dbb577dd6e3a001`

```text
11: // several settings open a sub-hub, the rest go straight to a leaf. Every page
12: // below the hub carries a breadcrumb top-left so the user knows where they
13: // are. The sticky Save Draft / Apply toolbar rides above the scroll area on
14: // leaf pages only — nav-only pages (hub, sub-hubs) have nothing to save.
15: 
16: export default function SettingsMain({
17:   children,
18: }: Readonly<{ children: React.ReactNode }>) {
19:   const pathname = usePathname() ?? "";
20:   const isHub = pathname === SETTINGS_HUB_HREF;
21: 
22:   if (isHub) {
23:     return (
24:       <div className="h-full overflow-y-auto bg-[var(--background)] [scrollbar-gutter:stable]">
25:         <div className="mx-auto w-full max-w-5xl px-8 py-8 pb-12">
```

## web/components/settings/SettingsSectionGrid.tsx:25

模型hub排序应来自统一nav，不能独立排序把默认项移后。

SHA-256：`a46876aeeb4caaa86cec6e4994d0ee1f5e8646e15b1f90cace67962611320de7`

```text
23:  * hub block.
24:  */
25: export default function SettingsSectionGrid({
26:   categoryKey,
27: }: {
28:   categoryKey: string;
29: }) {
30:   const { i18n } = useTranslation();
31:   const zh = i18n.language?.toLowerCase().startsWith("zh");
32:   const tr = useCallback((l: Lang) => (zh ? l.zh : l.en), [zh]);
33: 
34:   const { catalog, catalogEditable, diagnosticsResults } = useSettings();
35: 
36:   const category = SETTINGS_CATEGORIES.find((c) => c.key === categoryKey);
37: 
```

## deeptutor/api/routers/settings.py:1452

现有Save恢复secret、校验、invalidate边界保留。

SHA-256：`e78534ff101dfeb815d76f6327e9ea18b87d1bfb5cd24eeccb9843331098e88c`

```text
1450: 
1451: @router.put("/catalog")
1452: async def update_catalog(payload: CatalogPayload):
1453:     _require_settings_admin()
1454:     service = get_model_catalog_service()
1455:     current = service.load()
1456:     _reject_masked_identity_change(current, payload.catalog)
1457:     restored = restore_catalog_secrets(payload.catalog, current)
1458:     proposed = reconcile_codex_catalog_update(current, restored)
1459:     _validate_visibility_field(proposed)
1460:     _validate_model_metadata(proposed)
1461:     _reject_hidden_default(current, proposed)
1462:     catalog = service.save(proposed)
1463:     _invalidate_runtime_caches()
1464:     return {"catalog": redact_catalog_secrets(catalog)}
```

## deeptutor/services/config/model_catalog.py:206

已有锁内mutator：用于默认patch的revision比较和局部更新。

SHA-256：`abd66bea1bcc54213299e63f2216b136a97e9365996802e93a65df0b24bc0fea`

```text
204:             return normalized
205: 
206:     def update(self, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
207:         with self._lock:
208:             catalog = self.load()
209:             mutator(catalog)
210:             return self.save(catalog)
211: 
212:     def apply(self, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
213:         current = self.save(catalog or self.load())
214:         return {"catalog_path": str(self.path), "services": list(current.get("services", {}))}
215: 
216:     def _normalize(self, catalog: dict[str, Any]) -> bool:
217:         services = catalog.setdefault("services", {})
218:         changed = False
```

## deeptutor/services/config/provider_runtime.py:750

选中模型default配置解析，chat override不能写这里全局对象。

SHA-256：`2be78f791e09d32eb2f2f30686fb9116cd887a6f20fbb668735d8e3a63279c00`

```text
748:     active_api_base = _as_str((profile or {}).get("base_url"))
749:     active_api_version = _as_str((profile or {}).get("api_version"))
750:     reasoning_effort = _as_str((model or {}).get("reasoning_effort")) or None
751:     active_extra_headers = _to_headers((profile or {}).get("extra_headers"))
752:     context_window = _coerce_optional_int((model or {}).get("context_window"))
753:     if context_window is None:
754:         context_window = _coerce_optional_int((model or {}).get("context_window_tokens"))
755:     metadata = (model or {}).get("provider_metadata")
756:     metadata_parameters = (
757:         metadata.get("parameters") if isinstance(metadata, dict) else None
758:     )
759:     if isinstance(metadata_parameters, dict):
760:         if context_window is None:
761:             context_window = _coerce_optional_int(metadata_parameters.get("context_window"))
762:         metadata_context = _coerce_optional_int(metadata_parameters.get("context_window"))
```

## deeptutor/services/model_discovery/official_parameters.json:188

协调者已补现用嵌入资料，不重做归因或重写真实维度。

SHA-256：`28fd7a1bf243c02f095416928988c26daa5c28cf708b2e5854e60514f85b7655`

```text
186:       "provider": "dashscope",
187:       "models": [
188:         "qwen3.7-text-embedding"
189:       ],
190:       "regions": [
191:         "any"
192:       ],
193:       "modes": [
194:         "any"
195:       ],
196:       "source_url": "https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api",
197:       "checked_at": "2026-10-24T00:00:00Z",
198:       "parameters": {
199:         "default_dimensions": 1024,
200:         "supported_dimensions": [
```

## tests/services/model_discovery/test_coordinator_regressions.py:23

23项独立Python回归保持；SDK/通义视觉真实路由已修复。

SHA-256：`08af6b23e9de3716319f80ce4cc97650907e9ecd3a1eb095db00b0fe7198bd80`

```text
21: 
22: 
23: def test_embedding_metadata_keeps_limits_and_dimensions_in_one_record():
24:     value = generic_parameters(
25:         {"context_window": 8192, "dimension": 1024, "supported_dimensions": [1024, 512]},
26:         kind="endpoint_api", source_url="https://school.example/models", checked_at=CHECKED,
27:     )
28:     assert value.values["context_window"] == 8192
29:     assert value.values["default_dimensions"] == 1024
30:     assert value.values["supported_dimensions"] == [1024, 512]
31:     assert value.provenance["default_dimensions"].json_path == "data[].dimension"
32: 
33: 
34: @pytest.mark.parametrize("provider", ["deepseek", "openrouter", "mistral", "groq"])
35: def test_provider_specific_shape_on_proxy_does_not_claim_official_provenance(provider):
```

## web/tests/model-metadata-coordinator.test.ts:5

4项独立Node回归保持；preview可更新元数据而不改手工维度。

SHA-256：`62b3c42137a9b1b19c307ee43e704245437571a79269b2633a8133bb8f19779c`

```text
3: import { initialCatalogParameters, previewParameterUpdate } from "../lib/model-metadata";
4: 
5: test("LLM import keeps simultaneous input and output limits", () => {
6:   const value = initialCatalogParameters("llm", { max_input_tokens: 200000, max_output_tokens: 32768 });
7:   assert.equal(value.max_input_tokens, "200000");
8:   assert.equal(value.max_tokens, "32768");
9:   assert.equal(value.context_window, undefined);
10: });
11: 
12: test("embedding metadata refresh applies choices and automatic request options without dimension change", () => {
13:   const result = previewParameterUpdate({
14:     existing: { id: "m", name: "M", model: "e", dimension: "1024", send_dimensions: true,
15:       parameter_overrides: { dimension: false, send_dimensions: false } },
16:     service: "embedding", parameters: { default_dimensions: 1024,
17:       supported_dimensions: [1024, 512], supports_dimensions_parameter: false },
```

## web/e2e/model-discovery-r2.spec.ts:206

MD-R2既有真实交互测试，新增R3后保留回归。

SHA-256：`3f81ddaf6482b305a65dfc1565ed6cf648dec92a55f73e74ba14632bb0c8af53`

```text
204: }
205: 
206: test("MD-R2 provider policies, parameters, runtime budget and custom names", async ({
207:   page,
208:   request,
209: }) => {
210:   test.setTimeout(600_000);
211:   guardBrowser(page);
212:   checks.run_id = state.run_id;
213:   checks.evidence_dir = STAGE;
214:   await control(request, { reset: 1, fail: 0, delayA: 0 });
215: 
216:   // ── 1. DeepSeek: native-compatible structured fields, add Pro ─────────────
217:   await page.goto("/settings/llm");
218:   await expect(page.getByText("Provider connection")).toBeVisible();
```

## web/playwright.phase1.config.ts:369

只在隔离服务扩fixtures，复用临时source和cleanup。

SHA-256：`b355c23cd781e7f8a2648f05776f1fe682ea3bd7671152b5c37adf082c1dd0fa`

```text
367: }
368: 
369: const MODEL_SERVER = String.raw`
370: import crypto from "node:crypto";
371: import fs from "node:fs";
372: import http from "node:http";
373: 
374: const port = Number(process.argv[2]);
375: const logPath = process.argv[3];
376: const asrDelayMs = ${ASR_DELAY_MS};
377: const log = (row) => fs.appendFileSync(logPath, JSON.stringify(row) + "\n");
378: 
379: function vector(text) {
380:   const dims = Array(32).fill(0);
381:   const tokens = String(text).toLowerCase().match(/[a-z0-9]+/g) || [];
```

## scripts/run_tests_isolated.py:34

Python不得直跑pytest，六树基线保护必须继续。

SHA-256：`9e9827fd9ea911e6072993d04d02c845b66d8990407b2c58b37f99aad85cc2a6`

```text
32: 
33: 
34: def main(args: list[str]) -> int:
35:     with tempfile.TemporaryDirectory(prefix="selflearn-tests-") as root_value:
36:         root = Path(root_value)
37:         env = clean_env(root)
38:         # User use after phase closure is legitimate. Preserve historical
39:         # receipts separately; guard this entire test run against its own
40:         # pre-bootstrap opaque snapshot, never a post-test replacement.
41:         before = protect_data(REPO)
42:         baseline = root / "data_before_tests.json"
43:         raw = json.dumps(before, sort_keys=True).encode()
44:         baseline.write_bytes(raw)
45:         env["SELFLEARN_TEST_DATA_BASELINE"] = str(baseline)
46:         env["SELFLEARN_TEST_DATA_BASELINE_SHA256"] = hashlib.sha256(raw).hexdigest()
```

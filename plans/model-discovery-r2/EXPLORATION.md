# MD-R2 已探索文件清单与关键片段

生成于2026-10-24（Asia/Shanghai）。这是派发时源码事实，不是执行结果。
先核对待改文件SHA-256；一致则使用下面定位进入实施，免去全仓orientation重读。只补读真正依赖的邻近上下文。行号用于定位，不把片段当shell命令。文件已变化则核对差异，不用旧片段覆盖新源码。

所有项目路径相对 `/home/albert/selflearn/selflearn`。本清单仅生产源码/测试入口，不含真实catalog/密钥。完整清单见SOURCE_INDEX.json。

前置：MD-R1协调者最终复核证据位于`.phase1-evidence/reviews/MD-R1-20261023/`，有5000 Python通过、521 Node通过及隔离浏览器结果；这是历史事实，不算MD-R2验收。真实用户设置此后合法变化，不可恢复旧baseline。

关键接缝：

- registry当前38项，策略只有7名字可进入；见矩阵，不重做供应商名单探索。
- 一个新字段要贯通 Connection→指纹→revision→cache→TS parser→merge→catalog Save→runtime，不能只改一端。
- C7需要修复两条LLM请求构造通路，保留业务已有较小预算；无字段旧配置不变。
- 只读参考：本机Chatbox/Hermes通用实现的路径和机制已在RESEARCH给出，无需审读其全仓或任何auth配置。

## deeptutor/services/provider_registry.py:346

LLM供应商单一入口；阿里已有项，避免重复新增。

SHA-256：`a9cbafa46726d941d22ec8150145a64b1c283ecb22da88f5319bfe1265b6e347`

```text
344:     ),
345:     ProviderSpec(
346:         name="dashscope",
347:         keywords=("qwen", "dashscope"),
348:         env_key="DASHSCOPE_API_KEY",
349:         display_name="DashScope",
350:         backend="openai_compat",
351:         default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
352:         thinking_style="enable_thinking",
353:     ),
354:     ProviderSpec(
355:         name="moonshot",
356:         keywords=("moonshot", "kimi"),
357:         env_key="MOONSHOT_API_KEY",
```

## deeptutor/services/model_discovery/types.py:442

当前混合身份与协议；需要独立provider identity，不靠扩alias列表绕过。

SHA-256：`c73cc0b6b8760daab9590d98cc8bcaae9d5576187d0a92e558cafda580d453b4`

```text
440: 
441: 
442: def canonicalize_binding(binding: str | None) -> str:
443:     key = (binding or "").strip().lower().replace("-", "_")
444:     if key in {"dashscope", "aliyun", "alibaba", "bailian"}:
445:         return "aliyun"
446:     if key in {"siliconflow", "silicon_flow"}:
447:         return "siliconflow"
448:     if key in {
449:         "openai",
450:         "custom",
451:         "openai_compatible",
452:         "openai_compat",
453:         "custom_openai",
```

## deeptutor/services/model_discovery/types.py:540

只覆盖四个协议分支，普通供应商名字被本地拦截。

SHA-256：`c73cc0b6b8760daab9590d98cc8bcaae9d5576187d0a92e558cafda580d453b4`

```text
538: 
539: 
540: def adapter_kind(service: str, connection: Connection) -> str:
541:     """Select the directory adapter without ever trusting an arbitrary host."""
542: 
543:     validate_service(service)
544:     binding = connection.canonical_binding
545:     if binding == "aliyun" and is_aliyun_official_host(connection.base_url):
546:         return "aliyun"
547:     if binding == "siliconflow" and is_siliconflow_official_host(connection.base_url):
548:         return "siliconflow"
549:     if binding == "ollama":
550:         return "ollama"
551:     if binding == "openai_compatible":
```

## deeptutor/services/model_discovery/types.py:349

目前只有可选context_window，新增参数、来源需序列化一致。

SHA-256：`c73cc0b6b8760daab9590d98cc8bcaae9d5576187d0a92e558cafda580d453b4`

```text
347: 
348: @dataclass(frozen=True, slots=True)
349: class DiscoveredModel:
350:     id: str
351:     name: str
352:     services: tuple[str, ...] = field(default_factory=tuple)
353:     classification: Classification = Classification.UNKNOWN
354:     runtime_compatibility: RuntimeCompatibility = RuntimeCompatibility.UNKNOWN
355:     reason_code: str | None = None
356:     source: ModelSource = ModelSource.REMOTE
357:     callability: str = "not_tested"
358:     context_window: int | None = None
359: 
360:     def to_dict(self) -> dict[str, Any]:
```

## deeptutor/services/model_discovery/service.py:376

unsupported在真实目录请求之前返回；不属于上游失败。

SHA-256：`707c74a96a162e5555909ed226ecb12c16da7f0c2aec970d0c4a5a63dfa09593`

```text
374:         from .types import adapter_kind
375: 
376:         adapter = adapter_kind(service, resolved)
377:         if adapter == "unsupported":
378:             return DiscoveryResult(
379:                 service=service,
380:                 profile_id=profile_id,
381:                 status=DiscoveryStatus.UNSUPPORTED,
382:                 models=(),
383:                 cache=CacheInfo(state=CacheState.NONE),
384:                 complete=False,
385:                 error=DiscoveryError(
386:                     DiscoveryErrorCode.UNSUPPORTED,
387:                     "This provider does not have an online model directory adapter in this build. Configure models manually; the saved connection is unchanged.",
```

## deeptutor/services/model_discovery/adapters.py:532

默认按base拼models，使用有界请求；新协议复用预算。

SHA-256：`4042d821d7d1aee182e13c61cf9fb0d69525240b876dfc9dd9024d2b1a0e959b`

```text
530: 
531: 
532: async def fetch_openai_compatible(
533:     connection: Connection,
534:     service: str,
535:     *,
536:     client_factory: ClientFactory,
537:     budget: _Budget | None = None,
538: ) -> FetchOutcome:
539:     budget = budget or _Budget(time.monotonic() + REFRESH_DEADLINE_SECONDS)
540:     url = append_url_path(connection.base_url, "models")
541:     if connection.api_version:
542:         url = with_query_params(url, {"api-version": connection.api_version})
543:     headers = _auth_headers(connection)
```

## deeptutor/services/model_discovery/adapters.py:631

总30秒和全局并发gate，已有修复不能退化。

SHA-256：`4042d821d7d1aee182e13c61cf9fb0d69525240b876dfc9dd9024d2b1a0e959b`

```text
629: 
630: 
631: async def fetch_catalog(connection, service, adapter, *, client_factory=None, now=None):
632:     """Bound queueing, transport and pagination by one cancellable deadline."""
633:     try:
634:         async with asyncio.timeout(REFRESH_DEADLINE_SECONDS):
635:             async with _remote_gate():
636:                 return await _fetch_catalog(
637:                     connection, service, adapter, client_factory=client_factory, now=now
638:                 )
639:     except TimeoutError as exc:
640:         raise DiscoveryUpstreamError(
641:             DiscoveryErrorCode.TIMEOUT, "目录查询超过总时限，请稍后重试。", retryable=True
642:         ) from exc
```

## deeptutor/services/model_discovery/compatibility.py:392

不能仅让DeepSeek走generic后仍把所有类别丢到unknown。

SHA-256：`eee266f21d93bc9e86eca5ef22b1d33387e2e0dd94063dcc7f4b6b9c332908f2`

```text
390: 
391: 
392: def generic_services_for_model(model_id: str, binding: str) -> tuple[str, ...]:
393:     """Return only categories with provider-specific evidence.
394: 
395:     The OpenAI binding has a small, well-known model family map.  A custom
396:     OpenAI-compatible endpoint has no such evidence, so it stays unknown.
397:     """
398: 
399:     canonical = binding.strip().lower().replace("-", "_")
400:     if canonical not in {"openai", "azure_openai", "openai_compatible"}:
401:         return ()
402:     if _OPENAI_EMBEDDING.search(model_id):
403:         return ("embedding",)
```

## deeptutor/services/model_discovery/compatibility.py:283

阿里目前只取context，未贯通max_output等。

SHA-256：`eee266f21d93bc9e86eca5ef22b1d33387e2e0dd94063dcc7f4b6b9c332908f2`

```text
281:         inference_provider=str(raw.get("inference_provider") or ""),
282:     )
283:     model_info = raw.get("model_info")
284:     context_window = (
285:         coerce_context_window(model_info.get("context_window"))
286:         if isinstance(model_info, Mapping)
287:         else None
288:     )
289:     return DiscoveredModel(
290:         id=model_id,
291:         name=name,
292:         services=services,
293:         classification=Classification.PROVIDER,
294:         runtime_compatibility=compatibility,
```

## deeptutor/services/model_discovery/cache.py:116

新参数必须round-trip，不可只修改网络响应。

SHA-256：`5dd45106adbf40b1b9c7d11b6fd7818a465781707e96e10100debe7d5634c049`

```text
114:             )
115:             source = ModelSource(str(item.get("source") or "remote"))
116:             context_window = item.get("context_window")
117:             if context_window is not None and not (
118:                 isinstance(context_window, int) and context_window > 0
119:             ):
120:                 context_window = None
121:             models.append(
122:                 DiscoveredModel(
123:                     id=model_id,
124:                     name=str(item.get("name") or model_id)[:256],
125:                     services=services,
126:                     classification=classification,
127:                     runtime_compatibility=compatibility,
```

## deeptutor/api/routers/settings.py:440

从registry派生LLM选项；label修正在共同接缝。

SHA-256：`9a62b5306eeb2b48d0cd06f7d78c1053cf2880dc3ac0ff7b35b086d38abf92e4`

```text
438: 
439: 
440: def _provider_choices() -> dict[str, list[dict[str, Any]]]:
441:     """Build dropdown options for provider selection, keyed by service type."""
442:     from deeptutor.services.config.provider_runtime import (
443:         DEPRECATED_SEARCH_PROVIDERS,
444:         EMBEDDING_PROVIDERS,
445:         IMAGEGEN_PROVIDERS,
446:         SEARCH_PROVIDERS,
447:         STT_PROVIDERS,
448:         TTS_PROVIDERS,
449:         VIDEOGEN_PROVIDERS,
450:     )
451:     from deeptutor.services.provider_registry import PROVIDERS
```

## deeptutor/services/config/provider_runtime.py:533

目前没有选中模型max_tokens/max_output容量通路。

SHA-256：`f196875c80ca268a26b52a927189d0db0fce7a6ed07a164a6e3049fa95711b4c`

```text
531: 
532: @dataclass(slots=True)
533: class ResolvedLLMConfig:
534:     """Resolved runtime LLM config used by get_llm_config/factory."""
535: 
536:     model: str
537:     provider_name: str
538:     provider_mode: str
539:     binding_hint: str | None = None
540:     binding: str = "openai"
541:     api_key: str = ""
542:     base_url: str | None = None
543:     effective_url: str | None = None
544:     api_version: str | None = None
```

## deeptutor/services/config/provider_runtime.py:750

目标模型上下文读取接缝；增加预算不得串model。

SHA-256：`f196875c80ca268a26b52a927189d0db0fce7a6ed07a164a6e3049fa95711b4c`

```text
748:     reasoning_effort = _as_str((model or {}).get("reasoning_effort")) or None
749:     active_extra_headers = _to_headers((profile or {}).get("extra_headers"))
750:     context_window = _coerce_optional_int((model or {}).get("context_window"))
751:     if context_window is None:
752:         context_window = _coerce_optional_int((model or {}).get("context_window_tokens"))
753: 
754:     provider_pool = _collect_provider_pool(loaded)
755:     spec = _choose_resolved_provider(
756:         hint=binding_hint,
757:         model=resolved_model,
758:         api_key=active_api_key,
759:         api_base=active_api_base or None,
760:         provider_pool=provider_pool,
761:     )
```

## deeptutor/services/llm/config.py:96

全局旧默认4096；添加选中模型字段要贯通resolver与Update。

SHA-256：`661450b3a8446c58086098d3278928f9fb1155620880f13a5773043539e57bef`

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
```

## deeptutor/services/llm/factory.py:154

显式字段重建config可能丢容量/预算；需匹配同一模型才继承。

SHA-256：`50a92d249593bbaeccd2e41483cad1896dc48d9c90ef0f6bbb63dfe08a6d0af8`

```text
152: 
153: 
154: def _resolve_call_config(
155:     *,
156:     model: str | None,
157:     api_key: str | None,
158:     base_url: str | None,
159:     api_version: str | None,
160:     binding: str | None,
161:     extra_headers: dict[str, str] | None,
162:     reasoning_effort: str | None,
163: ) -> tuple[LLMConfig, Any]:
164:     if model and api_key is not None and (base_url is not None or binding is not None):
165:         current = _matching_current_config(
```

## deeptutor/core/agentic/client.py:286

主agentic调用的独立硬编码回退，不能仅修services factory。

SHA-256：`26dce5d4e48eea32e4d796d53fc289e0952cac45a3878db944993513891be069`

```text
284:         tool_choice = kwargs.pop("tool_choice", None)
285:         temperature = kwargs.pop("temperature", 0.7)
286:         max_tokens = kwargs.pop("max_completion_tokens", None)
287:         if max_tokens is None:
288:             max_tokens = kwargs.pop("max_tokens", 4096)
289:         reasoning_effort = kwargs.pop("reasoning_effort", None)
290:         kwargs.pop("stream_options", None)
291: 
292:         if stream:
293:             return _ProviderOpenAIStream(
294:                 provider=self._provider,
295:                 messages=messages,
296:                 tools=tools,
297:                 model=model,
```

## deeptutor/services/llm/context_window.py:7

项目安全cap不借机扩大；厂商原容量另保存。

SHA-256：`ed219e4a4a23d96518bc4cfc087eccd2133a974d7db7367fcc0b616c12a817b8`

```text
5: from typing import Any
6: 
7: DEFAULT_CONTEXT_WINDOW_FALLBACK = 16_384
8: MAX_EFFECTIVE_CONTEXT_WINDOW = 1_000_000
9: LARGE_CONTEXT_MODEL_DEFAULT = 65_536
10: KNOWN_LARGE_CONTEXT_MARKERS = (
11:     "gpt-4.1",
12:     "gpt-4o",
13:     "gpt-5",
14:     "o1",
15:     "o3",
16:     "o4",
17:     "claude",
18:     "gemini",
```

## deeptutor/agents/chat/context_budget.py:74

预算展示接缝，核对输入上限/总窗语义。

SHA-256：`79ceabf8d0eb46bd6a98c686700d88bfce1fe7ce9bbb3baa11e9e8a2e79b4bad`

```text
72: 
73: 
74: def resolve_window_info(
75:     *,
76:     context_window: Any = None,
77:     model: str = "",
78:     max_tokens: Any = None,
79: ) -> ContextWindowInfo:
80:     """Resolve the turn's window and report how it was obtained.
81: 
82:     A configured window is used verbatim, deliberately NOT routed through
83:     :func:`resolve_effective_context_window`: that helper clamps to
84:     ``MAX_EFFECTIVE_CONTEXT_WINDOW`` because it sizes the *history planning*
85:     budget, where an over-large window is a liability. The readout has the
```

## deeptutor/services/config/context_window_detection.py:23

旧检测把不同上限视近似值；本阶段新元数据不能沿用递归猜第一个值。

SHA-256：`08e0006436c629240f5dc462a114ab7e45cdc00a6da2ec40b130ac5732debead`

```text
21: logger = logging.getLogger(__name__)
22: 
23: _CONTEXT_WINDOW_KEYS = (
24:     "context_window",
25:     "context_window_tokens",
26:     "context_length",
27:     "context_size",
28:     "max_context_tokens",
29:     "max_input_tokens",
30:     "input_token_limit",
31:     "max_prompt_tokens",
32:     "max_model_len",
33:     "max_sequence_length",
34: )
```

## deeptutor/services/config/model_catalog.py:277

旧数据normalizer；不要增加读取即写入迁移。

SHA-256：`abd66bea1bcc54213299e63f2216b136a97e9365996802e93a65df0b24bc0fea`

```text
275:                             # Empty default → test_runner auto-fills from the
276:                             # actual API response on first connection test.
277:                             model.setdefault("dimension", "")
278:                             # CSV of supported dims discovered during the last
279:                             # successful "Test connection" — drives the UI
280:                             # dropdown. Empty when the model is not in any
281:                             # adapter's MODELS_INFO map.
282:                             model.setdefault("supported_dimensions", "")
283:                         elif service_name == "tts":
284:                             # Provider/model-specific free-form voice string
285:                             # (e.g. "alloy", "autumn", "model:voice").
286:                             model.setdefault("voice", "")
287:                             model.setdefault("response_format", "mp3")
288:                         elif service_name == "imagegen":
```

## deeptutor/services/embedding/adapters/openai_compatible.py:364

已有维度映射但不代表实时官方参数；只读参照，勿擅改embedding推理。

SHA-256：`6004b1dfeab4c0e6a41eb8db0c3dee7028effaa32221e9f12509f5fafa3e233d`

```text
362:         )
363: 
364:     def get_model_info(self) -> Dict[str, Any]:
365:         model_info = self.MODELS_INFO.get(self.model, self.dimensions)
366: 
367:         if isinstance(model_info, dict):
368:             return {
369:                 "model": self.model,
370:                 "dimensions": model_info.get("default", self.dimensions),
371:                 "supported_dimensions": model_info.get("dimensions", []),
372:                 "supports_variable_dimensions": len(model_info.get("dimensions", [])) > 1,
373:                 "multimodal": looks_like_multimodal_embedding_model(self.model),
374:                 "provider": "openai_compatible",
375:             }
```

## web/lib/model-discovery.ts:35

目前TS候选只有context；扩可选parameters兼容旧schema。

SHA-256：`0b314543e4ed42719d7846bc1fc1869d8447bb03ad9bcc1185661410b9c3b0bd`

```text
33: }
34: 
35: export interface DiscoveryModel {
36:   id: string;
37:   name: string;
38:   services: DiscoveryService[];
39:   classification: DiscoveryClassification;
40:   runtime_compatibility: DiscoveryCompatibility;
41:   reason_code: string | null;
42:   source: DiscoverySource;
43:   callability: "not_tested";
44:   context_window?: number;
45: }
46: 
```

## web/lib/model-discovery.ts:354

已确认导入只复制id/name/model，丢弃其他值。

SHA-256：`0b314543e4ed42719d7846bc1fc1869d8447bb03ad9bcc1185661410b9c3b0bd`

```text
352:     usedIds.add(internalId);
353:     byModel.set(candidate.id, internalId);
354:     models.push({ id: internalId, name: candidate.name, model: candidate.id });
355:     addedIds.push(internalId);
356:   }
357:   return { models, addedIds, reusedIds };
358: }
359: 
360: export function modelVisibleInPicker(
361:   model: Pick<CatalogModel, "visible_in_picker"> | null | undefined,
362: ): boolean {
363:   return model?.visible_in_picker !== false;
364: }
```

## web/components/settings/SettingsContext.tsx:43

类型需要max_tokens/provider_metadata/overrides等。

SHA-256：`db2e516988a1a2b2dd843beedcb2e1b061f7e153e3a3a1dc1fed7e12986ecd40`

```text
41:   | "vision";
42: 
43: export type CatalogModel = {
44:   id: string;
45:   name: string;
46:   model: string;
47:   managed_by?: string;
48:   dimension?: string;
49:   send_dimensions?: boolean;
50:   supported_dimensions?: string;
51:   context_window?: string;
52:   context_window_source?: string;
53:   context_window_detected_at?: string;
54:   // Display preference only; missing means visible and is never migrated.
```

## web/components/settings/SettingsContext.tsx:1038

保存成功已有缓存失效；仍需处理旧pending写回和picker激活。

SHA-256：`db2e516988a1a2b2dd843beedcb2e1b061f7e153e3a3a1dc1fed7e12986ecd40`

```text
1036:       setDraft(cloneCatalog(payload.catalog));
1037:       // The model list the chat composer shows is derived from this catalog.
1038:       invalidateLLMOptionsCache();
1039:       setToast(t("Draft saved"));
1040:     } catch (error) {
1041:       // Keep the dirty draft and the catalog visible so the user can fix the
1042:       // error without losing unsaved candidate selections.
1043:       setToast(
1044:         error instanceof Error
1045:           ? error.message
1046:           : t("Could not save the draft."),
1047:       );
1048:     } finally {
1049:       setSaving(false);
```

## web/components/settings/ServiceConfigEditor.tsx:286

名称保存正确；不要修改model调用ID来实现重命名。

SHA-256：`193970f1f160d986d2c039ca08cacf9a11a058a521f54f168cb1fb1d529ed8dc`

```text
284:   };
285: 
286:   const commitModelRename = (modelId: string) => {
287:     const fallbackIndex =
288:       activeProfile?.models.findIndex((model) => model.id === modelId) ?? -1;
289:     const fallbackName = defaultModelLabel(language, fallbackIndex + 1);
290:     const nextName = editingModelName.trim() || fallbackName;
291:     mutateCatalog((next) => {
292:       const profile = getActiveProfile(next, service);
293:       const model = profile?.models.find((item) => item.id === modelId);
294:       if (model) model.name = nextName;
295:     });
296:     setEditingModelId(null);
297:     setEditingModelName("");
```

## web/components/settings/ServiceConfigEditor.tsx:741

新增官方参数/自动来源UI的位置参照。

SHA-256：`193970f1f160d986d2c039ca08cacf9a11a058a521f54f168cb1fb1d529ed8dc`

```text
739:                                 className={inputClass}
740:                                 inputMode="numeric"
741:                                 value={activeModel.context_window || ""}
742:                                 onChange={(e) =>
743:                                   updateContextWindowField(e.target.value)
744:                                 }
745:                                 placeholder="65536"
746:                               />
747:                               <ContextWindowMeta model={activeModel} />
748:                             </div>
749:                             <ContextWindowDetectionBanner
750:                               model={activeModel}
751:                               detection={activeLlmDetection}
752:                               onApply={applyDetectedContextWindow}
```

## web/components/settings/ModelDiscoveryDialog.tsx:80

候选选择与draft导入界面；更新预览避免直接写saved。

SHA-256：`78616df2b06fbffc5b5497d8ef1dccca15a4ba29c4c6651ea4507def539eb4cc`

```text
78: }
79: 
80: export function ModelDiscoveryDialog({
81:   open,
82:   onClose,
83:   service,
84:   profile,
85:   state,
86:   onQuery,
87:   onRefresh,
88:   onRetry,
89:   onAddSelected,
90: }: {
91:   open: boolean;
```

## web/components/settings/useModelDiscovery.ts:12

已修mask凭据revision竞态；目录URL必须加入同一身份判定。

SHA-256：`3db7cba967b1503202cb1b3e9e5f945e6ca4ef1a00cc81f1164467c27a6b31d0`

```text
10:   isDiscoveryService,
11:   parseDiscoveryResponse,
12:   savedConnectionRevision,
13:   type DiscoveryConnection,
14:   type DiscoveryMode,
15:   type DiscoveryResponse,
16: } from "@/lib/model-discovery";
17: import {
18:   INITIAL_MODEL_DISCOVERY_STATE,
19:   reduceModelDiscoveryState,
20: } from "@/lib/model-discovery-state";
21: 
22: const AUTO_REQUESTS = new Map<string, Promise<DiscoveryResponse>>();
23: 
```

## web/components/chat/home/ModelSelector.tsx:42

两个显示优先级都要改，第二处selectedLabel见相邻定位。

SHA-256：`186d4697e14c50a60411b04c18e4ee83e0fcd2fc765c2ce55527c14bd510b998`

```text
40:   // Official model ID as the primary label (what gets sent to the API),
41:   // per design. The user-given nickname and profile live in the tooltip.
42:   const modelLabel = option.model || option.model_name;
43:   const contextWindow = formatContextWindow(option.context_window);
44:   // Long model ids ("google/gemini-3-flash-preview") get ellipsized by the
45:   // inline layout; hovering the row reveals the full id as an overlay. The
46:   // scrollWidth check at mouseenter time keeps the overlay away from rows
47:   // that aren't actually truncated.
48:   const nameRef = useRef<HTMLSpanElement>(null);
49:   const [revealFull, setRevealFull] = useState(false);
50:   return (
51:     <button
52:       type="button"
53:       title={`${option.model_name} | ${option.profile_name}`}
```

## web/lib/llm-options.ts:60

LLM options资源缓存；局部处理保存后旧请求回写。

SHA-256：`6059160b95a75001b8060cabfd67db295a7e80ecc6675aeb5c0783e051bfba08`

```text
58:  *  each firing their own on mount. Editing a profile calls
59:  *  ``invalidateLLMOptionsCache``; pass ``force`` to bypass the cache. */
60: export async function listLLMOptions(options?: {
61:   force?: boolean;
62:   timeoutMs?: number;
63: }): Promise<LLMOptionsResponse> {
64:   return withClientCache<LLMOptionsResponse>(
65:     LLM_OPTIONS_CACHE_KEY,
66:     async () => {
67:       const controller = new AbortController();
68:       const timeout = setTimeout(
69:         () => controller.abort(),
70:         options?.timeoutMs ?? DEFAULT_LLM_OPTIONS_TIMEOUT_MS,
71:       );
```

## web/hooks/useLLMOptions.ts:19

single-flight与late response保护应保留。

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
```

## deeptutor/services/model_selection/llm.py:92

后端已返回别名；无须改授权/内部引用。

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
```

## deeptutor/multi_user/model_access.py:121

普通用户沿用已有授权alias；不要显示其他模型。

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
```

## web/playwright.model-discovery.config.ts:11

参考wrapper；R2用新路径和test match，不覆盖MD-R1。

SHA-256：`dfca3a291c0e894ed7a510bb5fdb85fbd391aadc6d1f796eaad3f59ba0989b54`

```text
9: 
10: const repo = path.resolve(__dirname, "..");
11: process.env.S15_EVIDENCE_DIR ||= path.join(
12:   repo,
13:   ".phase1-evidence",
14:   "model-discovery",
15:   "MD-R1-browser",
16: );
17: process.env.S15_RUN_LABEL ||= "md";
18: process.env.S15_TEST_MATCH = "model-discovery.spec.ts";
19: process.env.S15_CHROMIUM ||=
20:   "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
21: 
22: // Playwright evaluates this wrapper with its TS loader; the base config must
```

## web/playwright.phase1.config.ts:369

仅隔离model server可扩fixture；生产服务禁加后门。

SHA-256：`a3ce4099db498efe00867fa03c3c49f4f1f677a9c77fa428213936c1b495ad68`

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
```

## scripts/run_tests_isolated.py:34

必须使用runner；保护六树，不直接pytest或绕guard。

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
```

## scripts/phase1_snapshot.py:90

只哈希真实数据，capture include_paths覆盖本阶段新源码。

SHA-256：`7dcaf3d0228a12f057698205f7b8152eaaa84c489ed8ce36508ed794c3ed7c7c`

```text
88: 
89: # 必须保持字节一致的真实数据根（只哈希，不复制）。
90: PROTECTED_DATA_ROOTS = {
91:     "learning_tree": "data/user/workspace/subjects",
92:     "public_outputs": "data/user/subjects",
93:     "settings": "data/user/settings",
94: }
95: 
96: # 额外观察根：只记录，不纳入 real_data_unchanged 的合同判定。
97: SUPPLEMENTARY_DATA_ROOTS = {
98:     "global_knowledge_bases": "data/knowledge_bases",
99:     "memory": "data/memory",
100:     "system": "data/system",
101: }
```

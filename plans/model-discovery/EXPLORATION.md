# MD-R1 已探索文件清单与关键片段

生成于 2026-10-23（Asia/Shanghai）；下面 SHA-256 是本次派发时的整文件摘要。
先核对待修改文件；一致则直接使用片段定位，只读实现所需上下文。行号是定位，不是禁止补读。
不要将下述代码当作待执行 shell；含 $providerId 的 Chatbox 路径需按字面处理。

## 当前前置结果

- 阿里云 ASR 已签收，模型 qwen3-asr-flash，45分15.755秒原录音真实转写 16/16；423 项相关回归通过。
- 前置证明：`/home/albert/selflearn/selflearn/.phase1-evidence/reviews/aliyun-asr-20261023/review.json`。只读，不运行其真实调用脚本。
- model_catalog/asr_media 是用户当前有效配置，本次开发只做 opaque hash，不用于 fixture，不恢复旧数据。
- 工作区已有大量历史已修改/未跟踪内容；保留到达状态，不 reset/clean。

## 文件索引

| 文件（均为项目根下） | SHA-256 | 定位与风险 |
| --- | --- | --- |
| `web/components/settings/SettingsContext.tsx` | `366cd93c0b465fcd38f649d8959ec0c301d11c9afcd2cded676a787cc459f100` | 类型与 draft/Save；Save 目前未检查 response.ok，新增功能需保留保存失败时的 draft。 |
| `web/components/settings/ServiceConfigEditor.tsx` | `a5333685381c446e8c3bbdfc7a3809efa9fe46d3c020e36258ff1cdb126e7bba` | 现有查询仅 llm；替换 profile.models/active 的旧逻辑禁止推广。 |
| `deeptutor/api/routers/settings.py` | `7c8db8a5664d07b055838296c62d1173305ee669c74b02c027d944888b5cdd81` | 现有权限、catalog 保存与 llm-only mask 恢复；新增 API 另建边界。 |
| `deeptutor/services/config/model_catalog.py` | `abd66bea1bcc54213299e63f2216b136a97e9365996802e93a65df0b24bc0fea` | mask 可递归恢复 headers；normalizer 使用 setdefault，勿添加读取即迁移。 |
| `deeptutor/services/llm/factory.py` | `50a92d249593bbaeccd2e41483cad1896dc48d9c90ef0f6bbb63dfe08a6d0af8` | 原 factory 返回 list[str]，无法表达错误/类别；保持老消费者兼容。 |
| `deeptutor/services/llm/cloud_provider.py` | `a50331ba13357446f0515d4633afaf98c9677e5cbc329837b0ee3e9b3e71d394` | 旧实现吞异常并返回空数组，新发现层必须区分错误/空目录。 |
| `deeptutor/services/llm/local_provider.py` | `67176265f643c4b561249dd1ce3ffa94ed5fe65b43dc5407f6d1592111ced78e` | 旧本地目录入口，只作参照，勿重写推理。 |
| `deeptutor/services/model_selection/llm.py` | `f05a472846699de2111aae848c4eefd6c6049b50c5494bcc83a6b86a83994885` | all configured models 与运行按 id 查找是不同接缝。 |
| `deeptutor/multi_user/model_access.py` | `3df602279cf0d1a2c426180009fa68101823655b9770f31618b1e81f1f899020` | 显示不能改 redacted_model_access/has_capability_access 的授权事实。 |
| `web/components/access/CapabilityAccessContext.tsx` | `2e8a882b55dc29a311966f7edc7411eed94b56aee5dc4410d24df6bfb427f6e6` | 关键风险：直接使用 options.length 作为普通用户能力门。 |
| `web/lib/llm-options.ts` | `3c706af8ca71cd8f2176607b2c884c45c0aa43fc4c592943ec3033e705e14dce` | 共享 LLM options 响应与缓存；扩展字段需向后兼容。 |
| `web/lib/llm-options-state.ts` | `abe054bfa3771325c8abdf1bc9a1492db1e1ecd6bad624a34a5d102b71d7e219` | 状态 reducer 要保留新增展示元数据，不丢失败旧列表。 |
| `web/hooks/useLLMOptions.ts` | `1b5beec992b10a0fd3a1561d93e3c4d57ce12bec9eaa2f5fd516c52a3a501d84` | 已有 single-flight 与迟到响应处理，新增字段透传。 |
| `web/components/chat/home/ModelSelector.tsx` | `61951d29764af80838dae63e6689997019d44ef2fca6164703d172d104d99102` | 当前项只在 options 查找，隐藏后需要按 hidden_options 单独解析。 |
| `web/components/chat/home/ChatComposer.tsx` | `053fd79b868532629d251151e4453b1950063332fdc1d4d899bb48b5b1a8f491` | LLM 选择器传参位置；不改整个聊天组件。 |
| `web/app/(workspace)/home/[[...sessionId]]/page.tsx` | `02c74fb939a35a88bd02e2d6177017c709588ca0390e324be950d1716fd9bb46` | 首页 useLLMOptions 与当前选择，不因目录刷新重设。 |
| `web/components/quiz/FollowupChatComposer.tsx` | `af2c53031a1327c127f5f2ef9d827a9834d478f60c1472dfb428511bdfc48638` | 题目跟进聊天也用共享选择器，保证展示元数据兼容。 |
| `deeptutor/services/path_service.py` | `01505ea0a473ba16b09bd27a9afd1a6795f4ddff1eef4a7b34f89ee7c748bd3d` | 缓存根可从 get_user_root 得到，不发明 HOME 或全局路径。 |
| `deeptutor/services/config/provider_runtime.py` | `f196875c80ca268a26b52a927189d0db0fce7a6ed07a164a6e3049fa95711b4c` | Aliyun STT 已实现 qwen_asr/qwen_chat_audio；新目录不等于新增推理。 |
| `deeptutor/services/voice/adapters/qwen_asr.py` | `6f78538ea1eafdfba73e790bc4d16589a195c8807c7f0019e3bdb55cfd9fcf9d` | 只读参考：已验收 ASR 输入边界；此文件不在修改白名单。 |
| `scripts/run_tests_isolated.py` | `9e9827fd9ea911e6072993d04d02c845b66d8990407b2c58b37f99aad85cc2a6` | 必须使用隔离 runner，保护真实数据。 |
| `scripts/phase1_snapshot.py` | `7dcaf3d0228a12f057698205f7b8152eaaa84c489ed8ce36508ed794c3ed7c7c` | capture(..., include_paths=...) 可纳入新未跟踪源码，不用改保护规则。 |
| `web/playwright.phase1.config.ts` | `f51b889ca6f5c2461d888cb101552f66c08d7624e2755a7f0be5d22f4dc543d6` | 已有隔离浏览器 copySource 和 MODEL_SERVER；必要新增目录 fixture 仅在后者。 |
| `web/playwright.asr.config.ts` | `e8be9e59b05df723c1e5b0442bb89ec8ce8efef4362694db0faa0c165d9695f7` | 新功能浏览器 wrapper 的参考；使用新 evidence root 和 test match。 |

## web/components/settings/SettingsContext.tsx

类型与 draft/Save；Save 目前未检查 response.ok，新增功能需保留保存失败时的 draft。

位置 `/home/albert/selflearn/selflearn/web/components/settings/SettingsContext.tsx:43` 至 56：

```text
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
54:   reasoning_effort?: string;
55:   codex_supported_reasoning_levels?: string[];
56:   // Voice (TTS): free-form provider/model-specific voice string, e.g.
```

位置 `/home/albert/selflearn/selflearn/web/components/settings/SettingsContext.tsx:82` 至 98：

```text
82: export type CatalogProfile = {
83:   id: string;
84:   name: string;
85:   managed_by?: string;
86:   codex_account_binding?: string;
87:   read_only?: boolean;
88:   binding?: string;
89:   provider?: string;
90:   base_url: string;
91:   api_key: string;
92:   api_version: string;
93:   extra_headers?: Record<string, string> | string;
94:   proxy?: string;
95:   max_results?: number;
96:   models: CatalogModel[];
97: };
98: 
```

位置 `/home/albert/selflearn/selflearn/web/components/settings/SettingsContext.tsx:1013` 至 1030：

```text
1013:     if (!catalogEditable) return;
1014:     setSaving(true);
1015:     try {
1016:       const response = await apiFetch(apiUrl("/api/v1/settings/catalog"), {
1017:         method: "PUT",
1018:         headers: { "Content-Type": "application/json" },
1019:         body: JSON.stringify({ catalog: draft }),
1020:       });
1021:       const payload = await response.json();
1022:       setCatalog(payload.catalog);
1023:       setDraft(cloneCatalog(payload.catalog));
1024:       // The model list the chat composer shows is derived from this catalog.
1025:       invalidateLLMOptionsCache();
1026:       setToast(t("Draft saved"));
1027:     } finally {
1028:       setSaving(false);
1029:     }
1030:   }, [catalogEditable, draft, t]);
```

## web/components/settings/ServiceConfigEditor.tsx

现有查询仅 llm；替换 profile.models/active 的旧逻辑禁止推广。

位置 `/home/albert/selflearn/selflearn/web/components/settings/ServiceConfigEditor.tsx:180` 至 195：

```text
180:   const syncProviderModels = async (
181:     connection?: Pick<CatalogProfile, "binding" | "base_url" | "api_key">,
182:   ) => {
183:     if (service !== "llm" || !activeProfile || modelsSyncing) return;
184:     const binding = connection?.binding ?? activeProfile.binding ?? "";
185:     const baseUrl = connection?.base_url ?? activeProfile.base_url ?? "";
186:     const apiKey = connection?.api_key ?? activeProfile.api_key ?? "";
187:     if (!binding || (binding !== "codebuddy" && !baseUrl.trim())) return;
188: 
189:     const profileId = activeProfile.id;
190:     setModelsSyncing(true);
191:     try {
192:       const response = await apiFetch(apiUrl("/api/v1/settings/fetch-models"), {
193:         method: "POST",
194:         headers: { "Content-Type": "application/json" },
195:         body: JSON.stringify({
```

位置 `/home/albert/selflearn/selflearn/web/components/settings/ServiceConfigEditor.tsx:221` 至 241：

```text
221:         profile.models = fetched.map((item, index) => {
222:           const previous = existing.get(item.id);
223:           return previous
224:             ? { ...previous, name: item.name || previous.name, model: item.id }
225:             : {
226:                 id: `llm-model-${Date.now()}-${index}`,
227:                 name: item.name || item.id,
228:                 model: item.id,
229:               };
230:         });
231:         if (
232:           !profile.models.some((model) => model.id === target.active_model_id)
233:         ) {
234:           target.active_model_id = profile.models[0]?.id ?? null;
235:         }
236:       });
237:       setToast(t("Synced {{count}} models", { count: fetched.length }));
238:     } catch (error) {
239:       setToast(error instanceof Error ? error.message : String(error));
240:     } finally {
241:       setModelsSyncing(false);
```

位置 `/home/albert/selflearn/selflearn/web/components/settings/ServiceConfigEditor.tsx:537` 至 553：

```text
537:                   </div>
538:                   {!isCodexOAuth && (
539:                     <div className="flex items-center gap-2">
540:                       {service === "llm" &&
541:                         activeProfile.binding === "codebuddy" && (
542:                           <button
543:                             type="button"
544:                             onClick={() => void syncProviderModels()}
545:                             disabled={modelsSyncing}
546:                             className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
547:                           >
548:                             <RefreshCw
549:                               className={`h-3 w-3 ${modelsSyncing ? "animate-spin" : ""}`}
550:                             />
551:                             {t("Sync models")}
552:                           </button>
553:                         )}
```

## deeptutor/api/routers/settings.py

现有权限、catalog 保存与 llm-only mask 恢复；新增 API 另建边界。

位置 `/home/albert/selflearn/selflearn/deeptutor/api/routers/settings.py:190` 至 195：

```text
190: class FetchModelsPayload(BaseModel):
191:     binding: str = ""
192:     base_url: str = ""
193:     api_key: Optional[str] = None
194:     profile_id: Optional[str] = None
195: 
```

位置 `/home/albert/selflearn/selflearn/deeptutor/api/routers/settings.py:1275` 至 1292：

```text
1275: @router.get("/llm-options")
1276: async def get_llm_options():
1277:     if not get_current_user().is_admin:
1278:         return allowed_llm_options()
1279:     return list_llm_options(get_model_catalog_service().load())
1280: 
1281: 
1282: @router.put("/catalog")
1283: async def update_catalog(payload: CatalogPayload):
1284:     _require_settings_admin()
1285:     service = get_model_catalog_service()
1286:     current = service.load()
1287:     restored = restore_catalog_secrets(payload.catalog, current)
1288:     proposed = reconcile_codex_catalog_update(current, restored)
1289:     catalog = service.save(proposed)
1290:     _invalidate_runtime_caches()
1291:     return {"catalog": redact_catalog_secrets(catalog)}
1292: 
```

位置 `/home/albert/selflearn/selflearn/deeptutor/api/routers/settings.py:1336` 至 1350：

```text
1336:     if api_key == CATALOG_SECRET_MASK and payload.profile_id:
1337:         llm_service = get_model_catalog_service().load().get("services", {}).get("llm", {})
1338:         profile = next(
1339:             (
1340:                 item
1341:                 for item in llm_service.get("profiles", [])
1342:                 if item.get("id") == payload.profile_id
1343:             ),
1344:             None,
1345:         )
1346:         api_key = profile.get("api_key") if profile else None
1347: 
1348:     try:
1349:         model_ids = await fetch_llm_models(binding, base_url, api_key)
1350:     except Exception as exc:  # noqa: BLE001 — surface any provider error as 502
```

## deeptutor/services/config/model_catalog.py

mask 可递归恢复 headers；normalizer 使用 setdefault，勿添加读取即迁移。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/config/model_catalog.py:25` 至 51：

```text
25: CATALOG_SECRET_MASK = "***"
26: _SECRET_FIELD_HINTS = ("api_key", "apikey", "token", "secret", "password")
27: 
28: 
29: def _is_secret_field(name: str) -> bool:
30:     normalized = name.lower()
31:     return any(hint in normalized for hint in _SECRET_FIELD_HINTS)
32: 
33: 
34: def _redact_secret_value(value: Any) -> Any:
35:     if isinstance(value, str):
36:         return CATALOG_SECRET_MASK if value else value
37:     if isinstance(value, dict):
38:         return {key: _redact_secret_value(item) for key, item in value.items()}
39:     if isinstance(value, list):
40:         return [_redact_secret_value(item) for item in value]
41:     return value
42: 
43: 
44: def _redact_profile(profile: dict[str, Any]) -> None:
45:     for key, value in list(profile.items()):
46:         # Header values are credentials often enough that none of them should
47:         # cross the API boundary. This also covers JSON-string header maps.
48:         if key == "extra_headers" or _is_secret_field(key):
49:             profile[key] = _redact_secret_value(value)
50: 
51: 
```

位置 `/home/albert/selflearn/selflearn/deeptutor/services/config/model_catalog.py:64` 至 84：

```text
64: 
65: def _restore_secret_value(proposed: Any, current: Any) -> Any:
66:     if proposed == CATALOG_SECRET_MASK:
67:         return deepcopy(current)
68:     if isinstance(proposed, dict) and isinstance(current, dict):
69:         return {
70:             key: _restore_secret_value(value, current.get(key)) for key, value in proposed.items()
71:         }
72:     if isinstance(proposed, list) and isinstance(current, list):
73:         return [
74:             _restore_secret_value(value, current[index] if index < len(current) else None)
75:             for index, value in enumerate(proposed)
76:         ]
77:     return proposed
78: 
79: 
80: def _restore_profile_secrets(proposed: dict[str, Any], current: dict[str, Any]) -> None:
81:     for key, value in list(proposed.items()):
82:         if key == "extra_headers" or _is_secret_field(key):
83:             proposed[key] = _restore_secret_value(value, current.get(key))
84: 
```

位置 `/home/albert/selflearn/selflearn/deeptutor/services/config/model_catalog.py:233` 至 252：

```text
233:             "imagegen",
234:             "videogen",
235:             "vision",
236:         ):
237:             service = services[service_name]
238:             profiles = service.setdefault("profiles", [])
239:             for profile in profiles:
240:                 profile.setdefault("id", f"{service_name}-profile-{uuid4().hex[:8]}")
241:                 profile.setdefault("name", "Untitled Profile")
242:                 profile.setdefault("api_version", "")
243:                 profile.setdefault("base_url", "")
244:                 profile.setdefault("api_key", "")
245:                 if service_name == "search":
246:                     profile.setdefault("provider", "brave")
247:                     profile.setdefault("proxy", "")
248:                     profile["models"] = []
249:                 else:
250:                     profile.setdefault("binding", "openai")
251:                     profile.setdefault("extra_headers", {})
252:                     if service_name == "embedding":
```

## deeptutor/services/llm/factory.py

原 factory 返回 list[str]，无法表达错误/类别；保持老消费者兼容。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/llm/factory.py:649` 至 669：

```text
649: async def fetch_models(
650:     binding: str,
651:     base_url: str = "",
652:     api_key: str | None = None,
653: ) -> list[str]:
654:     if canonical_provider_name(binding) == "codebuddy":
655:         from .provider_core.codebuddy_models import fetch_codebuddy_models
656: 
657:         return await fetch_codebuddy_models(api_key)
658: 
659:     if is_local_llm_server(base_url):
660:         from . import local_provider
661: 
662:         return await local_provider.fetch_models(base_url, api_key)
663: 
664:     from . import cloud_provider
665: 
666:     return await cloud_provider.fetch_models(base_url, api_key, binding)
667: 
668: 
669: def _build_api_provider_presets() -> dict[str, ApiProviderPreset]:
```

## deeptutor/services/llm/cloud_provider.py

旧实现吞异常并返回空数组，新发现层必须区分错误/空目录。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/llm/cloud_provider.py:901` 至 923：

```text
901:         try:
902:             url = f"{base_url}/models"
903:             async with session.get(url, headers=headers) as resp:
904:                 if resp.status == 200:
905:                     payload = await resp.json()
906:                     if isinstance(payload, Mapping):
907:                         mapping = cast(Mapping[str, object], payload)
908:                         items = mapping.get("data")
909:                         if isinstance(items, list):
910:                             return collect_model_names(cast(list[object], items))
911:                     elif isinstance(payload, list):
912:                         return collect_model_names(cast(list[object], payload))
913:             return []
914:         except Exception as e:
915:             logger.error("Error fetching models from %s: %s", base_url, e)
916:             return []
917: 
918: 
919: __all__ = [
920:     "complete",
921:     "stream",
922:     "fetch_models",
923: ]
```

## deeptutor/services/llm/local_provider.py

旧本地目录入口，只作参照，勿重写推理。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/llm/local_provider.py:321` 至 340：

```text
321: async def fetch_models(
322:     base_url: str,
323:     api_key: str | None = None,
324: ) -> list[str]:
325:     """
326:     Fetch available models from local LLM server.
327: 
328:     Supports:
329:     - Ollama (/api/tags)
330:     - OpenAI-compatible (/models)
331: 
332:     Args:
333:         base_url: Base URL for the local server
334:         api_key: API key (optional)
335: 
336:     Returns:
337:         List of available model names
338:     """
339:     base_url = base_url.rstrip("/")
340: 
```

## deeptutor/services/model_selection/llm.py

all configured models 与运行按 id 查找是不同接缝。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/model_selection/llm.py:59` 至 73：

```text
59: def list_llm_options(catalog: dict[str, Any]) -> dict[str, Any]:
60:     """Return a redacted list of configured chat-selectable LLM models."""
61:     service = _llm_service(catalog)
62:     active_profile_id = str(service.get("active_profile_id") or "")
63:     active_model_id = str(service.get("active_model_id") or "")
64: 
65:     options: list[dict[str, Any]] = []
66:     for profile in service.get("profiles", []) or []:
67:         if not isinstance(profile, dict):
68:             continue
69:         profile_id = str(profile.get("id") or "").strip()
70:         if not profile_id:
71:             continue
72:         provider = str(profile.get("binding") or "").strip()
73:         profile_name = str(profile.get("name") or provider or "LLM").strip()
```

位置 `/home/albert/selflearn/selflearn/deeptutor/services/model_selection/llm.py:84` 至 102：

```text
84:             if not model_id or not model_value:
85:                 continue
86: 
87:             option: dict[str, Any] = {
88:                 "profile_id": profile_id,
89:                 "model_id": model_id,
90:                 "profile_name": profile_name,
91:                 "model_name": str(model.get("name") or model_value).strip(),
92:                 "model": model_value,
93:                 "provider": provider,
94:                 "provider_label": provider_label,
95:                 "is_active_default": (
96:                     profile_id == active_profile_id and model_id == active_model_id
97:                 ),
98:             }
99:             context_window = _coerce_int(model.get("context_window"))
100:             if context_window is None:
101:                 context_window = _coerce_int(model.get("context_window_tokens"))
102:             if context_window is not None:
```

## deeptutor/multi_user/model_access.py

显示不能改 redacted_model_access/has_capability_access 的授权事实。

位置 `/home/albert/selflearn/selflearn/deeptutor/multi_user/model_access.py:119` 至 145：

```text
119: def allowed_llm_options() -> dict[str, Any]:
120:     user = get_current_user()
121:     if user.is_admin:
122:         return list_llm_options(admin_catalog())
123:     options = [
124:         {
125:             "profile_id": item.get("profile_id"),
126:             "model_id": item.get("model_id"),
127:             "profile_name": item.get("name") or item.get("profile_id") or "LLM",
128:             "model_name": item.get("name") or item.get("model") or item.get("model_id"),
129:             "label": item.get("name") or item.get("model") or item.get("model_id"),
130:             "model": item.get("model") or "",
131:             "provider": "",
132:             "source": item.get("source") or "admin",
133:             "is_active_default": False,
134:         }
135:         for item in redacted_model_access(user.id).get("llm", [])
136:         if item.get("available")
137:     ]
138:     return {"active": None, "options": options}
139: 
140: 
141: def has_capability_access(capability: str, user_id: str | None = None) -> bool:
142:     """Whether the user has at least one usable model for ``capability``.
143: 
144:     Admins are never gated — they manage the catalog directly. For ordinary
145:     users this mirrors exactly what ``redacted_model_access`` exposes to the
```

位置 `/home/albert/selflearn/selflearn/deeptutor/multi_user/model_access.py:150` 至 167：

```text
150:         return True
151:     if user_id is None:
152:         user_id = user.id
153:     items = redacted_model_access(user_id).get(capability, []) or []
154:     return any(item.get("available") for item in items)
155: 
156: 
157: def apply_allowed_llm_selection(selection: dict[str, Any] | None) -> dict[str, Any] | None:
158:     """Allow only admin-granted LLM profile/model selections for ordinary users."""
159:     user = get_current_user()
160:     if user.is_admin or not selection:
161:         return selection
162:     profile_id = str(selection.get("profile_id") or "")
163:     model_id = str(selection.get("model_id") or "")
164:     for item in redacted_model_access(user.id).get("llm", []):
165:         if item.get("profile_id") == profile_id and item.get("model_id") == model_id:
166:             return selection
167:     raise PermissionError("This model is not assigned to your account.")
```

## web/components/access/CapabilityAccessContext.tsx

关键风险：直接使用 options.length 作为普通用户能力门。

位置 `/home/albert/selflearn/selflearn/web/components/access/CapabilityAccessContext.tsx:61` 至 75：

```text
61:       // presence is our admin signal — admins are never gated.
62:       const res = await apiFetch(apiUrl("/api/v1/settings"));
63:       if (!res.ok) return;
64:       const payload = (await res.json()) as { catalog?: unknown };
65:       if (payload.catalog) {
66:         setIsAdmin(true);
67:         setHasLlm(true);
68:         return;
69:       }
70:       setIsAdmin(false);
71:       // Non-admins: their grant-filtered LLM options decide access.
72:       const { options } = await listLLMOptions();
73:       setHasLlm(options.length > 0);
74:     } catch {
75:       // Keep last known state; the backend still enforces access on every call.
```

## web/lib/llm-options.ts

共享 LLM options 响应与缓存；扩展字段需向后兼容。

位置 `/home/albert/selflearn/selflearn/web/lib/llm-options.ts:8` 至 27：

```text
8: export interface LLMOption extends LLMSelection {
9:   profile_name: string;
10:   model_name: string;
11:   model: string;
12:   provider: string;
13:   /** Human-readable provider name from the registry ("OpenRouter"). */
14:   provider_label?: string;
15:   context_window?: number;
16:   is_active_default: boolean;
17: }
18: 
19: export interface LLMOptionsResponse {
20:   active: LLMSelection | null;
21:   options: LLMOption[];
22: }
23: 
24: export function llmSelectionKey(selection: LLMSelection | null | undefined) {
25:   if (!selection?.profile_id || !selection.model_id) return "";
26:   return `${selection.profile_id}:${selection.model_id}`;
27: }
```

位置 `/home/albert/selflearn/selflearn/web/lib/llm-options.ts:46` 至 68：

```text
46:   return withClientCache<LLMOptionsResponse>(
47:     LLM_OPTIONS_CACHE_KEY,
48:     async () => {
49:       const controller = new AbortController();
50:       const timeout = setTimeout(
51:         () => controller.abort(),
52:         options?.timeoutMs ?? DEFAULT_LLM_OPTIONS_TIMEOUT_MS,
53:       );
54:       try {
55:         const response = await apiFetch(
56:           apiUrl("/api/v1/settings/llm-options"),
57:           {
58:             cache: "no-store",
59:             signal: controller.signal,
60:           },
61:         );
62:         if (!response.ok) {
63:           throw new Error(`Failed to load LLM options: ${response.status}`);
64:         }
65:         const data = (await response.json()) as LLMOptionsResponse;
66:         return {
67:           active: data.active ?? null,
68:           options: Array.isArray(data.options) ? data.options : [],
```

## web/lib/llm-options-state.ts

状态 reducer 要保留新增展示元数据，不丢失败旧列表。

位置 `/home/albert/selflearn/selflearn/web/lib/llm-options-state.ts:5` 至 18：

```text
5: 
6: export interface LLMOptionsState {
7:   options: LLMOption[];
8:   activeDefault: LLMSelection | null;
9:   status: LLMOptionsStatus;
10: }
11: 
12: export type LLMOptionsAction =
13:   | { type: "refresh-started"; background: boolean }
14:   | { type: "refresh-succeeded"; payload: LLMOptionsResponse }
15:   | { type: "refresh-failed" };
16: 
17: export const INITIAL_LLM_OPTIONS_STATE: LLMOptionsState = {
18:   options: [],
```

位置 `/home/albert/selflearn/selflearn/web/lib/llm-options-state.ts:38` 至 47：

```text
38:     case "refresh-succeeded":
39:       return {
40:         options: action.payload.options,
41:         activeDefault: action.payload.active,
42:         status: "ready",
43:       };
44:     case "refresh-failed":
45:       return state.options.length > 0
46:         ? { ...state, status: "ready" }
47:         : { ...state, status: "error" };
```

## web/hooks/useLLMOptions.ts

已有 single-flight 与迟到响应处理，新增字段透传。

位置 `/home/albert/selflearn/selflearn/web/hooks/useLLMOptions.ts:19` 至 34：

```text
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
32:     };
33:   }, []);
34: 
```

位置 `/home/albert/selflearn/selflearn/web/hooks/useLLMOptions.ts:59` 至 71：

```text
59: 
60:   useEffect(() => {
61:     void refresh();
62:   }, [refresh]);
63: 
64:   return {
65:     options: state.options,
66:     activeDefault: state.activeDefault,
67:     loading: state.status === "loading",
68:     error: state.status === "error",
69:     refresh,
70:   };
71: }
```

## web/components/chat/home/ModelSelector.tsx

当前项只在 options 查找，隐藏后需要按 hidden_options 单独解析。

位置 `/home/albert/selflearn/selflearn/web/components/chat/home/ModelSelector.tsx:117` 至 144：

```text
117: }: {
118:   options: LLMOption[];
119:   activeDefault: LLMSelection | null;
120:   value: LLMSelection | null;
121:   loading: boolean;
122:   error: boolean;
123:   allowSystemDefault?: boolean;
124:   systemDefaultLabel?: string;
125:   systemDefaultDetail?: string;
126:   helperText?: string;
127:   placement?: "top" | "bottom";
128:   onChange: (selection: LLMSelection | null) => void;
129:   onRefresh?: () => void;
130: }) {
131:   const { t } = useTranslation();
132:   const [open, setOpen] = useState(false);
133:   const rootRef = useRef<HTMLDivElement>(null);
134:   const { expanded, linger, triggerProps: lingerProps } = useLingerExpand(open);
135: 
136:   const selectedSelection = allowSystemDefault
137:     ? value
138:     : (value ?? activeDefault);
139:   const selectedKey = llmSelectionKey(selectedSelection);
140:   const selectedOption = useMemo(
141:     () =>
142:       options.find((option) => sameLLMSelection(option, selectedSelection)) ??
143:       null,
144:     [options, selectedSelection],
```

## web/components/chat/home/ChatComposer.tsx

LLM 选择器传参位置；不改整个聊天组件。

位置 `/home/albert/selflearn/selflearn/web/components/chat/home/ChatComposer.tsx:277` 至 286：

```text
277:   subagentBudget?: number | null;
278:   onSubagentBudgetChange?: (budget: number) => void;
279:   llmOptions: LLMOption[];
280:   activeLLMDefault: LLMSelection | null;
281:   llmSelection: LLMSelection | null;
282:   llmOptionsLoading: boolean;
283:   llmOptionsError: boolean;
284:   onRefreshLLMOptions?: () => void;
285:   /**
286:    * Context-window breakdown measured on the last turn that reported one.
```

位置 `/home/albert/selflearn/selflearn/web/components/chat/home/ChatComposer.tsx:1080` 至 1093：

```text
1080:                   />
1081:                 ) : null}
1082:                 <ModelSelector
1083:                   options={llmOptions}
1084:                   activeDefault={activeLLMDefault}
1085:                   value={llmSelection}
1086:                   loading={llmOptionsLoading}
1087:                   error={llmOptionsError}
1088:                   onChange={onSelectLLM}
1089:                   onRefresh={onRefreshLLMOptions}
1090:                 />
1091:                 {contextBudget ? (
1092:                   <ContextBudgetChip budget={contextBudget} />
1093:                 ) : null}
```

## web/app/(workspace)/home/[[...sessionId]]/page.tsx

首页 useLLMOptions 与当前选择，不因目录刷新重设。

位置 `/home/albert/selflearn/selflearn/web/app/(workspace)/home/[[...sessionId]]/page.tsx:389` 至 397：

```text
389:   const {
390:     options: llmOptions,
391:     activeDefault: activeLLMDefault,
392:     loading: llmOptionsLoading,
393:     error: llmOptionsError,
394:     refresh: refreshLLMOptions,
395:   } = useLLMOptions();
396:   const [capabilityConfigs, setCapabilityConfigs] =
397:     useState<CapabilityPlaygroundConfigMap>({});
```

位置 `/home/albert/selflearn/selflearn/web/app/(workspace)/home/[[...sessionId]]/page.tsx:1121` 至 1127：

```text
1121:   }, [refreshUserEnabledTools]);
1122: 
1123:   useEffect(() => {
1124:     if (state.llmSelection || !activeLLMDefault) return;
1125:     setLLMSelection(activeLLMDefault);
1126:   }, [activeLLMDefault, setLLMSelection, state.llmSelection]);
1127: 
```

位置 `/home/albert/selflearn/selflearn/web/app/(workspace)/home/[[...sessionId]]/page.tsx:2098` 至 2108：

```text
2098:               activeCap={activeCap}
2099:               knowledgeBases={kbOptions}
2100:               llmOptions={llmOptions}
2101:               activeLLMDefault={activeLLMDefault}
2102:               llmSelection={state.llmSelection}
2103:               llmOptionsLoading={llmOptionsLoading}
2104:               llmOptionsError={llmOptionsError}
2105:               subjects={subjectOptions}
2106:               subjectId={subjectId}
2107:               onSubjectChange={(id) => setSubjectId(id)}
2108:               onRefreshLLMOptions={() =>
```

## web/components/quiz/FollowupChatComposer.tsx

题目跟进聊天也用共享选择器，保证展示元数据兼容。

位置 `/home/albert/selflearn/selflearn/web/components/quiz/FollowupChatComposer.tsx:176` 至 188：

```text
176:       setLLMOptionsLoading(true);
177:       try {
178:         const payload = await listLLMOptions();
179:         if (cancelled) return;
180:         setLLMOptions(payload.options);
181:         setActiveLLMDefault(payload.active);
182:         setLLMOptionsError(false);
183:       } catch {
184:         if (cancelled) return;
185:         setLLMOptionsError(true);
186:         setLLMOptions([]);
187:         setActiveLLMDefault(null);
188:       } finally {
```

位置 `/home/albert/selflearn/selflearn/web/components/quiz/FollowupChatComposer.tsx:622` 至 633：

```text
622:         attachmentError={attachmentError}
623:         activeCap={activeCap}
624:         knowledgeBases={knowledgeBases}
625:         llmOptions={llmOptions}
626:         activeLLMDefault={activeLLMDefault}
627:         llmSelection={llmSelection}
628:         llmOptionsLoading={llmOptionsLoading}
629:         llmOptionsError={llmOptionsError}
630:         selectedBookReferences={selectedBookReferences}
631:         selectedNotebookRecords={selectedNotebookRecords}
632:         selectedHistorySessions={selectedHistorySessions}
633:         selectedAgentSessions={[]}
```

## deeptutor/services/path_service.py

缓存根可从 get_user_root 得到，不发明 HOME 或全局路径。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/path_service.py:99` 至 113：

```text
99:         return self._project_root
100: 
101:     @property
102:     def user_data_dir(self) -> Path:
103:         return self._user_data_dir
104: 
105:     @property
106:     def workspace_root(self) -> Path:
107:         return self._workspace_root
108: 
109:     @property
110:     def package_root(self) -> Path:
111:         return self._package_root
112: 
113:     def get_user_root(self) -> Path:
```

## deeptutor/services/config/provider_runtime.py

Aliyun STT 已实现 qwen_asr/qwen_chat_audio；新目录不等于新增推理。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/config/provider_runtime.py:351` 至 364：

```text
351: 
352: STT_PROVIDERS: dict[str, VoiceProviderSpec] = {
353:     "aliyun": VoiceProviderSpec(
354:         label="阿里云百炼 (DashScope)",
355:         default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
356:         default_model="qwen3-asr-flash",
357:         adapter="qwen_asr",
358:         request_style=STT_QWEN_CHAT,
359:     ),
360:     "openai": VoiceProviderSpec(
361:         label="OpenAI",
362:         default_api_base="https://api.openai.com/v1",
363:         default_model="gpt-4o-mini-transcribe",
364:     ),
```

## deeptutor/services/voice/adapters/qwen_asr.py

只读参考：已验收 ASR 输入边界；此文件不在修改白名单。

位置 `/home/albert/selflearn/selflearn/deeptutor/services/voice/adapters/qwen_asr.py:21` 至 41：

```text
21:     BaseSTTAdapter,
22:     VoiceProviderError,
23:     VoiceProviderHTTPError,
24:     build_auth_headers,
25: )
26: from deeptutor.services.voice.config import STTConfig
27: 
28: QWEN_MAX_REQUEST_BYTES = 10_000_000
29: # Reserve room for the data URI and JSON envelope after 4/3 base64 expansion.
30: QWEN_MAX_AUDIO_BYTES = 7_490_000
31: QWEN_MAX_AUDIO_SECONDS = 300
32: QWEN_MAX_SOURCE_BYTES = 25 * 1024 * 1024
33: _LIMIT_MESSAGE = "千问单次音频超过大小或时长限制，请使用课程录音上传，由系统自动切片。"
34: 
35: 
36: class QwenAudioLimitError(VoiceProviderError):
37:     """The bounded audio/request budget would be exceeded."""
38: 
39: 
40: class QwenInvalidOutputError(VoiceProviderError):
41:     """The upstream success body was not a Qwen transcript."""
```

## scripts/run_tests_isolated.py

必须使用隔离 runner，保护真实数据。

位置 `/home/albert/selflearn/selflearn/scripts/run_tests_isolated.py:38` 至 54：

```text
38:         # User use after phase closure is legitimate. Preserve historical
39:         # receipts separately; guard this entire test run against its own
40:         # pre-bootstrap opaque snapshot, never a post-test replacement.
41:         before = protect_data(REPO)
42:         baseline = root / "data_before_tests.json"
43:         raw = json.dumps(before, sort_keys=True).encode()
44:         baseline.write_bytes(raw)
45:         env["SELFLEARN_TEST_DATA_BASELINE"] = str(baseline)
46:         env["SELFLEARN_TEST_DATA_BASELINE_SHA256"] = hashlib.sha256(raw).hexdigest()
47:         env["DEEPTUTOR_HOME"] = str(root / "runtime")
48:         Path(env["DEEPTUTOR_HOME"]).mkdir()
49:         guard = root / "guard"
50:         guard.mkdir()
51:         (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
52:         env["S13_ENDPOINT_REGISTRY"] = str(guard / "endpoints.json")
53:         env["PYTHONPATH"] = str(guard) + os.pathsep + str(REPO)
54:         try:
```

## scripts/phase1_snapshot.py

capture(..., include_paths=...) 可纳入新未跟踪源码，不用改保护规则。

位置 `/home/albert/selflearn/selflearn/scripts/phase1_snapshot.py:315` 至 322：

```text
315: def whitelisted_untracked(root: Path, tracked: set[str], include_paths=()) -> list[str]:
316:     found: set[str] = set()
317:     for rel in UNTRACKED_WHITELIST:
318:         if (root / rel).is_file() or (root / rel).is_symlink():
319:             found.add(rel)
320:     for prefix in UNTRACKED_WHITELIST_PREFIXES:
321:         base = root / prefix
322:         if base.is_symlink():
```

位置 `/home/albert/selflearn/selflearn/scripts/phase1_snapshot.py:346` 至 352：

```text
346: def capture(root: Path, label: str, *, include_paths=()) -> dict:
347:     """记录完整基线：归档清单 + 更宽的监控清单 + 删除清单。"""
348:     if not (root / ".git").exists():
349:         raise RuntimeError(f"not a git worktree: {root}")
350:     head = git_head(root)
351:     tracked = git_tracked(root)
352:     tracked_set = set(tracked)
```

## web/playwright.phase1.config.ts

已有隔离浏览器 copySource 和 MODEL_SERVER；必要新增目录 fixture 仅在后者。

位置 `/home/albert/selflearn/selflearn/web/playwright.phase1.config.ts:36` 至 43：

```text
36: }
37: const STAGE = canonical(process.env.S15_EVIDENCE_DIR || path.join(REPO, ".phase1-evidence", "stages", "S15"));
38: if (!inside(path.join(REPO, ".phase1-evidence"), STAGE)) throw new Error("S15 evidence must stay under .phase1-evidence");
39: if (fs.existsSync(path.join(STAGE, "report.json")) || fs.existsSync(path.join(STAGE, "closing_manifest.json"))) {
40:   throw new Error("Sealed S15 evidence: set S15_EVIDENCE_DIR to a fresh directory");
41: }
42: const RUN_LABEL = process.env.S15_RUN_LABEL || "good";
43: if (!/^[a-zA-Z0-9_-]{1,48}$/.test(RUN_LABEL)) throw new Error("Invalid S15_RUN_LABEL");
```

位置 `/home/albert/selflearn/selflearn/web/playwright.phase1.config.ts:207` 至 223：

```text
207: function copySource(): void {
208:   const allowed = ["deeptutor", "web", "pyproject.toml", "requirements.txt", "requirements", "scripts"];
209:   fs.mkdirSync(SOURCE_ROOT, { recursive: true });
210:   for (const name of allowed) {
211:     const from = path.join(PROVIDED_SOURCE || REPO, name);
212:     if (!fs.existsSync(from)) continue;
213:     fs.cpSync(from, path.join(SOURCE_ROOT, name), {
214:       recursive: true,
215:       dereference: false,
216:       filter: (src) => {
217:         const rel = path.relative(PROVIDED_SOURCE || REPO, src).split(path.sep).join("/");
218:         if (rel.split("/").some((part) => [".git", "node_modules", "__pycache__", ".pytest_cache"].includes(part))) return false;
219:         if (rel.split("/").some((part) => part === ".env" || part.startsWith(".env."))) return false;
220:         if (fs.lstatSync(src).isSymbolicLink()) return false;
221:         if (rel.startsWith("web/.next") || rel.startsWith("web/.next-deeptutor")) return false;
222:         if (rel === "web/dist" || rel.startsWith("web/dist/")) return false;
223:         if (rel.startsWith("web/test-results") || rel.startsWith("web/playwright-report")) return false;
```

位置 `/home/albert/selflearn/selflearn/web/playwright.phase1.config.ts:364` 至 375：

```text
364: }
365: 
366: http.createServer((req, res) => {
367:   const chunks = [];
368:   req.on("data", (c) => chunks.push(c));
369:   req.on("end", () => {
370:     const raw = Buffer.concat(chunks);
371:     const url = req.url || "";
372:     log({ method: req.method, url, bytes: raw.length, at: new Date().toISOString() });
373:     if (req.method === "POST" && url.endsWith("/embeddings")) {
374:       let body = {};
375:       try { body = JSON.parse(raw.toString("utf8")); } catch {}
```

## web/playwright.asr.config.ts

新功能浏览器 wrapper 的参考；使用新 evidence root 和 test match。

位置 `/home/albert/selflearn/selflearn/web/playwright.asr.config.ts:7` 至 22：

```text
7:  * environment assignments happen before the base config is evaluated, so the
8:  * base config's sealed-evidence and bootstrap ownership checks still apply.
9:  */
10: import path from "node:path";
11: 
12: const repo = path.resolve(__dirname, "..");
13: process.env.S15_EVIDENCE_DIR ||= path.join(repo, ".phase1-evidence", "repairs", "ASR-R1", "browser-asr");
14: process.env.S15_RUN_LABEL ||= "asr";
15: process.env.S15_TEST_MATCH = "asr-long-audio.spec.ts";
16: process.env.S15_ASR_DELAY_MS ||= "65000";
17: process.env.S15_CHROMIUM ||= "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
18: 
19: // Playwright loads this file with its TypeScript config loader; `require` is
20: // evaluated after the assignments above (a static re-export would not be).
21: const base = require("./playwright.phase1.config");
22: export default base.default || base;
```

## 其他已确认路径（按需定向读）

- 文案：`web/locales/zh/app.json`、`web/locales/en/app.json`、`web/locales/zh/common.json`、`web/locales/en/common.json`。只新增本功能需要的 key。
- 测试：`tests/services/model_selection/test_llm_selection.py`、`tests/services/config/test_model_catalog_secrets.py`、`tests/asr/test_qwen.py`、`tests/phase1/test_p1_16.py`。
- Node 组件测试接缝：`web/tests/asr-jobs.test.ts`、`web/tests/settings-context-ui-sync.test.ts`；不要只用源码字符串断言证明新行为。
- 本机 Chatbox 源码（只读参考，非必须重读）：`/home/albert/chatbox/work/cb/src/renderer/routes/settings/provider/$providerId.tsx:370`、`:1016`，以及 `src/renderer/packages/model-setting-utils/base-config.ts:43`。它把候选目录与已添加模型分开，合并多来源，不代表逐个调用验证。
- 本机 Hermes（只读参考，无需本阶段抄入）：`/mnt/c/Users/17261/AppData/Local/hermes/hermes-agent/hermes_cli/models.py:1860` 与 `apps/desktop/src/store/model-visibility.ts:192`。本阶段不做其全局后台发现。

## 允许改动的精确附加接缝

TASKS 中 MD-06 的聊天入口、选择器、能力上下文及 hooks 已逐文件授权，均只限新增展示元数据和保留当前隐藏模型。
MD-07 可修改 `web/playwright.phase1.config.ts` 的 MODEL_SERVER/专用 fixture 开关；禁止改 browser guard、真实数据隔离、源码副本安全检查和清理策略。
`scripts/phase1_snapshot.py`、`scripts/run_tests_isolated.py`、所有已验收 ASR 推理/媒体代码只读，不是改动白名单。
本探索包自身不由 worker 重写；若文件发生并发变化，在 RESULT/report 中记录新定位与原因。

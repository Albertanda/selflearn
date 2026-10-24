# 已探索文件清单 + 关键片段

目的：worker 直接在接缝实施，免去全仓 orientation。完整 SHA256 见 SOURCE_INDEX.json；若一致，不必重读全文；若变动仅补读相应函数。代码片段均为本次只读检查所得，不是执行命令。

## 已完成的只读验证

- 本地后端 8001 与前端 3782 的 GET /api/v1/settings 均返回 38 个 LLM 供应商，含 Custom (OpenAI API)、Custom (Anthropic API)、vLLM/Local。只保留供应商 label/value，没有输出整个响应。
- 当前预设列表没有过滤 custom；ServiceConfigEditor 原样显示英文标签，按服务列表顺序渲染。真实浏览器用户没有找到“自定义供应商”中文入口的确切点击路径未录屏；不能把源码上不存在的“已封死”当事实。
- 当前自定义协议支持测试独立运行：13 passed（0.39s）；命令 `.venv/bin/python scripts/run_tests_isolated.py tests/services/model_discovery/test_provider_policy.py tests/services/model_selection/test_llm_selection.py -q`。
- 真实 Agnes profile/model 定位见 C6；只检查模型/连接身份和凭据是否存在，没有外部推理。
- 当前真实默认是 DeepSeek，不能因新增测试供应商自动更改默认。

## 接缝

### AGENTS.md

项目测试/数据约束

位置：170–177。
```text
170: 
171: ## Isolated Python tests
172: 
173: Use `.venv/bin/python scripts/run_tests_isolated.py [pytest arguments]`. With no arguments it runs the configured full suite. Direct unisolated collection fails before application imports; do not bypass the guard. Preserve both historical data evidence and the explicitly approved S14 catalog exception baseline. The runner separately pins current opaque inventories before bootstrap and checks all six trees after tests; any change during the run fails. Legitimate user activity after phase closure is not a reason to restore old data or rewrite historical receipts.
174: 
175: ## Browser evidence preservation
176: 
177: The S15 Playwright configuration refuses sealed evidence directories. An explicitly requested rerun must set `S15_EVIDENCE_DIR` to a fresh directory under this checkout’s `.phase1-evidence/`; reuse the installed browser and isolated source runner. Never point `S15_SOURCE_COPY` at this checkout, its ancestors, or existing data. Read-only handoff instructions and verified source excerpts are in `plans/phase1/PHASE1_HANDOFF.txt`.
```

### deeptutor/services/provider_registry.py

custom/custom_anthropic 与本地 vllm 早已存在；无需新增 Agnes 静态 provider

位置：128–141。
```python
128:     ProviderSpec(
129:         name="custom",
130:         keywords=(),
131:         env_key="",
132:         display_name="Custom",
133:         backend="openai_compat",
134:         is_direct=True,
135:     ),
136:     ProviderSpec(
137:         name="custom_anthropic",
138:         keywords=(),
139:         env_key="",
140:         display_name="Custom (Anthropic API)",
141:         backend="anthropic",
```

位置：421–428。
```python
421:     ProviderSpec(
422:         name="vllm",
423:         keywords=("vllm",),
424:         env_key="HOSTED_VLLM_API_KEY",
425:         display_name="vLLM/Local",
426:         backend="openai_compat",
427:         is_local=True,
428:     ),
```

### deeptutor/services/config/provider_runtime.py

各服务已有 custom 协议与真实运行时解析

位置：242–250。
```python
242:     ),
243:     "custom": EmbeddingProviderSpec(
244:         label="OpenAI Compatible",
245:         mode="direct",
246:         default_api_base="",
247:         keywords=(),
248:         is_local=False,
249:     ),
250:     # Retained for legacy configs only. Public Settings providers use exact
```

位置：474–481。
```python
474:     # Generic chat-completions image output (any OpenRouter-style gateway).
475:     "custom_chat": GenerationProviderSpec(
476:         label="Chat Completions (Custom)",
477:         default_api_base="",
478:         adapter="chat_completions",
479:         default_model="",
480:     ),
481: }
```

位置：484–501。
```python
484: # all use the async-task adapter (submit → poll → download).
485: VIDEOGEN_PROVIDERS: dict[str, GenerationProviderSpec] = {
486:     "volcengine": GenerationProviderSpec(
487:         label="Volcengine Ark (Seedance)",
488:         default_api_base="https://ark.cn-beijing.volces.com/api/v3",
489:         adapter="async_task",
490:         default_model="doubao-seedance-1-0-pro-250528",
491:     ),
492:     "custom": GenerationProviderSpec(
493:         label="Async Task (Custom)",
494:         default_api_base="",
495:         adapter="async_task",
496:         default_model="",
497:     ),
498: }
499: 
500: # Provider-name aliases accepted from older/loose catalog values.
501: GENERATION_PROVIDER_ALIASES = {
```

### deeptutor/api/routers/settings.py

设置供应商列表、默认候选、revision 和遮罩保护

位置：647–679。
```python
647: 
648: def _provider_choices() -> dict[str, list[dict[str, Any]]]:
649:     """Build dropdown options for provider selection, keyed by service type."""
650:     from deeptutor.services.config.provider_runtime import (
651:         DEPRECATED_SEARCH_PROVIDERS,
652:         EMBEDDING_PROVIDERS,
653:         IMAGEGEN_PROVIDERS,
654:         SEARCH_PROVIDERS,
655:         STT_PROVIDERS,
656:         TTS_PROVIDERS,
657:         VIDEOGEN_PROVIDERS,
658:     )
659:     from deeptutor.services.provider_registry import PROVIDERS
660: 
661:     llm = sorted(
662:         [
663:             {
664:                 "value": s.name,
665:                 "label": (
666:                     "Custom (OpenAI API)"
667:                     if s.name == "custom"
668:                     else "Custom (Anthropic API)"
669:                     if s.name == "custom_anthropic"
670:                     else s.label
671:                 ),
672:                 "base_url": s.default_api_base,
673:                 "auth_mode": s.auth_mode,
674:             }
675:             for s in PROVIDERS
676:         ],
677:         key=lambda p: p["label"].lower(),
678:     )
679:     embedding = sorted(
```

位置：470–489。
```python
470: 
471: def _safe_default_options(catalog: dict[str, Any]) -> dict[str, Any]:
472:     services = catalog.get("services") if isinstance(catalog.get("services"), dict) else {}
473:     result: dict[str, Any] = {}
474:     for name in _DEFAULT_MODEL_SERVICES:
475:         service = services.get(name) if isinstance(services.get(name), dict) else {}
476:         profiles: list[dict[str, Any]] = []
477:         for profile in service.get("profiles", []) or []:
478:             if not isinstance(profile, dict) or not profile.get("id"):
479:                 continue
480:             provider = str(
481:                 (
482:                     profile.get("provider")
483:                     if name == "search"
484:                     else profile.get("binding")
485:                 )
486:                 or ""
487:             )
488:             spec = find_by_name(provider) if name != "search" else None
489:             provider_label = spec.label if spec is not None else (provider or str(profile.get("name") or ""))
```

位置：1587–1607。
```python
1587: 
1588: def _reject_masked_identity_change(
1589:     current: dict[str, Any], proposed: dict[str, Any]
1590: ) -> None:
1591:     """A masked credential cannot silently move to another identity/origin."""
1592: 
1593:     before = _all_profiles(current)
1594:     after = _all_profiles(proposed)
1595:     for key, profile in after.items():
1596:         old = before.get(key)
1597:         if old is None:
1598:             continue
1599:         service_name = key.split(":", 1)[0]
1600:         if profile.get("managed_by") or profile.get("read_only"):
1601:             continue
1602:         old_binding = str(old.get("binding") or old.get("provider") or "")
1603:         new_binding = str(profile.get("binding") or profile.get("provider") or "")
1604:         old_base = str(old.get("base_url") or "")
1605:         new_base = str(profile.get("base_url") or "")
1606:         old_dir = str(old.get("model_directory_url") or "")
1607:         new_dir = str(profile.get("model_directory_url") or "")
```

位置：1682–1702。
```python
1682: 
1683: @router.put("/catalog")
1684: async def update_catalog(payload: CatalogPayload):
1685:     _require_settings_admin()
1686:     service = get_model_catalog_service()
1687: 
1688:     def build(current: dict[str, Any]) -> dict[str, Any]:
1689:         _reject_masked_identity_change(current, payload.catalog)
1690:         restored = restore_catalog_secrets(payload.catalog, current)
1691:         return reconcile_codex_catalog_update(current, restored)
1692: 
1693:     def validate(current: dict[str, Any], proposed: dict[str, Any]) -> None:
1694:         _validate_visibility_field(proposed)
1695:         _validate_model_metadata(proposed)
1696:         _reject_hidden_default(current, proposed)
1697: 
1698:     try:
1699:         catalog = service.update_checked(
1700:             payload.expected_revision,
1701:             build,
1702:             validate=validate,
```

### deeptutor/services/config/model_catalog.py

现有保存事务/未知字段兼容；独立进程线程锁不等于服务器锁

位置：239–267。
```python
239: 
240:     def update_checked(
241:         self,
242:         expected_revision: str | None,
243:         builder: Callable[[dict[str, Any]], dict[str, Any] | None],
244:         *,
245:         validate: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
246:     ) -> dict[str, Any]:
247:         """Read, compare, build, validate and save under one lock.
248: 
249:         ``builder`` receives the current catalog and returns the proposed one
250:         (or mutates and returns ``None``).  ``validate`` runs while the same
251:         lock is held, so a normal catalog save and a default-reference patch
252:         can never validate one snapshot and overwrite another.
253:         """
254: 
255:         with self._lock:
256:             current = self.load()
257:             if expected_revision is not None:
258:                 current_revision = catalog_revision(current)
259:                 if not hmac.compare_digest(expected_revision, current_revision):
260:                     raise CatalogRevisionConflict(current_revision)
261:             working = deepcopy(current)
262:             proposed = builder(working)
263:             if proposed is None:
264:                 proposed = working
265:             if validate is not None:
266:                 validate(current, proposed)
267:             return self.save(proposed)
```

### deeptutor/services/model_discovery/provider_policy.py

已有 custom 的目录协议路由

位置：49–56。
```python
49: 
50: PROVIDER_POLICIES: dict[str, ProviderPolicy] = {
51:     "custom": _p("custom"),
52:     "custom_anthropic": _p("custom_anthropic", ADAPTER_ANTHROPIC),
53:     "azure_openai": _p("azure_openai", ADAPTER_AZURE),
54:     "openrouter": _p("openrouter", structured="openrouter"),
55:     "orcarouter": _p("orcarouter"),
56:     "edenai": _p("edenai"),
```

### deeptutor/services/model_discovery/service.py

binding 验证及凭据校验不能删

位置：325–332。
```python
325:             validate_directory_url(resolved.model_directory_url)
326:         if not resolved.binding:
327:             raise DiscoveryRequestError("A provider binding is required.", status_code=400)
328:         if resolved.provider_identity(service) in {"openai_codex", "codebuddy"}:
329:             raise DiscoveryRequestError(
330:                 "Managed OAuth profiles are configured through their dedicated card, not model discovery.",
331:                 status_code=400,
332:             )
```

### deeptutor/services/model_discovery/types.py

连接 identity/fingerprint 的技术字段，名字和图标不应混入

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### deeptutor/services/model_discovery/cache.py

持久目录缓存与去密钥边界

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### deeptutor/services/model_discovery/adapters.py

已有 OpenAI/Anthropic 目录、禁止带密钥跨源重定向

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### deeptutor/services/model_selection/llm.py

管理员模型摘要目前 label 来自静态 binding

位置：78–97。
```python
78:         # "VolcEngine Coding Plan", ...) so the UI never shows binding keys.
79:         provider_spec = find_by_name(provider)
80:         provider_label = provider_spec.label if provider_spec else provider
81: 
82:         for model in profile.get("models", []) or []:
83:             if not isinstance(model, dict):
84:                 continue
85:             model_id = str(model.get("id") or "").strip()
86:             model_value = str(model.get("model") or "").strip()
87:             if not model_id or not model_value:
88:                 continue
89: 
90:             option: dict[str, Any] = {
91:                 "profile_id": profile_id,
92:                 "model_id": model_id,
93:                 "profile_name": profile_name,
94:                 "model_name": str(model.get("name") or model_value).strip(),
95:                 "model": model_value,
96:                 "provider": provider,
97:                 "provider_label": provider_label,
```

### deeptutor/multi_user/model_access.py

普通用户已授权模型摘要也要接 presenter，不能只改管理员

位置：160–177。
```python
160:             spec = find_by_name(provider)
161:             provider_label = spec.label if spec is not None else provider
162:             option = {
163:                 "profile_id": profile_id,
164:                 "model_id": model_id,
165:                 "profile_name": str(
166:                     profile.get("name") or item.get("name") or profile_id
167:                 ),
168:                 "model_name": str(model.get("name") or model.get("model") or model_id),
169:                 "label": str(model.get("name") or model.get("model") or model_id),
170:                 "model": str(model.get("model") or ""),
171:                 "provider": provider,
172:                 "provider_label": provider_label,
173:                 "source": item.get("source") or "admin",
174:                 "is_active_default": False,
175:                 "visible_in_picker": item.get("visible_in_picker") is not False,
176:             }
177:             controls = controls_for(
```

### deeptutor/multi_user/personal_models.py

个人托管 profile 合并边界，避免新增定义污染 OAuth

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### deeptutor/services/llm/reasoning_controls.py

MM-R3 核心能力策略，不用自定义名字猜原厂档位

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/components/settings/SettingsContext.tsx

Catalog 类型/草稿/编辑选择/保存版本号接缝

位置：101–119。
```tsx
101: 
102: export type CatalogProfile = {
103:   id: string;
104:   name: string;
105:   managed_by?: string;
106:   codex_account_binding?: string;
107:   read_only?: boolean;
108:   binding?: string;
109:   provider?: string;
110:   base_url: string;
111:   api_key: string;
112:   api_version: string;
113:   extra_headers?: Record<string, string> | string;
114:   /** Optional complete directory URL; never a chat URL and never persisted as base_url. */
115:   model_directory_url?: string;
116:   proxy?: string;
117:   max_results?: number;
118:   models: CatalogModel[];
119: };
```

位置：140–155。
```tsx
140: 
141: export type Catalog = {
142:   version: number;
143:   services: {
144:     llm: CatalogService;
145:     embedding: CatalogService;
146:     search: CatalogService;
147:     tts: CatalogService;
148:     stt: CatalogService;
149:     imagegen: CatalogService;
150:     videogen: CatalogService;
151:     vision: CatalogService;
152:   };
153: };
154: 
155: export type UiSettings = {
```

位置：1423–1448。
```tsx
1423: 
1424:   const applySavedDefaultReferences = useCallback(
1425:     (defaults: DefaultModelReferenceMap, revision: string, baseRevision: string) => {
1426:       const mergeReferences = (catalogValue: Catalog): Catalog => {
1427:         const next = cloneCatalog(catalogValue);
1428:         for (const service of Object.keys(defaults) as ServiceName[]) {
1429:           const reference = defaults[service];
1430:           if (!reference) continue;
1431:           next.services[service].active_profile_id = reference.profile_id;
1432:           if (service !== "search") {
1433:             next.services[service].active_model_id =
1434:               reference.model_id ?? null;
1435:           }
1436:         }
1437:         return next;
1438:       };
1439:       setCatalog((current) => mergeReferences(current));
1440:       setDraft((current) => mergeReferences(current));
1441:       setCatalogRevision((current) =>
1442:         revisionAfterDefaultPatch(current, baseRevision, revision),
1443:       );
1444:       invalidateLLMOptionsCache();
1445:     },
1446:     [],
1447:   );
1448: 
```

### web/components/settings/ServiceConfigEditor.tsx

当前供选择的 label 原样显示；新入口与 UI action 接这里

位置：1633–1641。
```tsx
1633: 
1634:   const providerValue =
1635:     service === "search" ? profile.provider || "" : profile.binding || "";
1636:   const providerOption = (providers[service] || []).find(
1637:     (option) => option.value === providerValue,
1638:   );
1639:   const isManagedCodex = isManagedCodexProfile(profile);
1640:   const isCodexOAuth = isCodexOAuthProfile(
1641:     service,
```

位置：1720–1737。
```tsx
1720:             </option>
1721:             {(providers[service] || [])
1722:               .filter((p) => p.status !== "deprecated")
1723:               .map((p) => (
1724:                 <option
1725:                   className={selectOptionClass}
1726:                   key={p.value}
1727:                   value={p.value}
1728:                 >
1729:                   {p.label}
1730:                 </option>
1731:               ))}
1732:           </select>
1733:           <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
1734:         </div>
1735:         {showSearchProviderWarning && (
1736:           <p
1737:             className={`mt-1.5 text-[11px] ${
```

### web/components/settings/useModelDiscovery.ts

向目录发的是技术连接白名单，不要转发名称图标

位置：57–69。
```tsx
57: 
58: function connectionBody(profile: CatalogProfile): DiscoveryConnection {
59:   return {
60:     binding: profile.binding ?? "",
61:     base_url: profile.base_url ?? "",
62:     api_key: profile.api_key ?? "",
63:     api_version: profile.api_version ?? "",
64:     extra_headers: parseHeaders(profile),
65:     model_directory_url: profile.model_directory_url ?? "",
66:   };
67: }
68: 
69: function postDiscovery(
```

### web/components/common/ProviderIcon.tsx

现有静态 binding 到 SVG，未知为 Bot；新增可选 display icon

位置：63–86。
```tsx
63: 
64: export default function ProviderIcon({
65:   provider,
66:   size = 13,
67:   className = "",
68: }: {
69:   provider?: string | null;
70:   size?: number;
71:   className?: string;
72: }) {
73:   const spec = provider
74:     ? PROVIDER_ICONS[provider.trim().toLowerCase()]
75:     : undefined;
76:   if (!spec) {
77:     return (
78:       <Bot
79:         size={size}
80:         strokeWidth={1.7}
81:         className={`shrink-0 ${className}`.trim()}
82:       />
83:     );
84:   }
85:   return (
86:     // eslint-disable-next-line @next/next/no-img-element
```

### web/lib/model-picker-groups.ts

两层按 profile_id，不是大厂强制绑定

位置：27–44。
```tsx
27: 
28: export function modelOptionSource(option: LLMOption): string {
29:   return (
30:     option.provider_label ||
31:     option.provider ||
32:     option.profile_name ||
33:     "LLM"
34:   );
35: }
36: 
37: function connectionLabel(option: LLMOption, _duplicateVendor: boolean): string {
38:   const vendor = modelOptionSource(option);
39:   const profile = (option.profile_name || "").trim();
40:   if (!profile || profile === vendor) return vendor;
41:   return `${vendor} · ${profile}`;
42: }
43: 
44: export function groupLLMOptions(
```

### web/components/chat/home/ModelSelector.tsx

四处 ProviderIcon 与选中隐藏项过滤均要保持

位置：164–176。
```tsx
164:     : (value ?? activeDefault);
165:   const selectedProfileId = selectedSelection?.profile_id;
166:   const selectedModelId = selectedSelection?.model_id;
167:   const groups = useMemo(
168:     () => groupLLMOptions(options, hiddenOptions.filter((option) =>
169:       option.profile_id === selectedProfileId && option.model_id === selectedModelId,
170:     )),
171:     [hiddenOptions, options, selectedProfileId, selectedModelId],
172:   );
173:   const selectedKey = llmSelectionKey(selectedSelection);
174:   const selectedVisibleOption = useMemo(
175:     () =>
176:       options.find((option) => sameLLMSelection(option, selectedSelection)) ??
```

### web/lib/llm-options.ts

模型摘要新增 optional icon，自定义名不改 selection key

位置：9–28。
```tsx
9: 
10: export interface LLMOption extends LLMSelection {
11:   profile_name: string;
12:   model_name: string;
13:   model: string;
14:   provider: string;
15:   /** Human-readable provider name from the registry ("OpenRouter"). */
16:   provider_label?: string;
17:   context_window?: number;
18:   is_active_default: boolean;
19:   /** Presentation metadata; omitted means visible. */
20:   visible_in_picker?: boolean;
21:   /** Set only on entries returned through hidden_options. */
22:   hidden?: boolean;
23:   /** Safe backend policy; omitted/unknown means no invented levels. */
24:   reasoning_controls?: ReasoningControls;
25: }
26: 
27: export interface LLMOptionsResponse {
28:   active: LLMSelection | null;
```

### web/lib/default-models.ts

默认候选 optional icon/type；保留 revisionAfterDefaultPatch

位置：26–35。
```tsx
26: 
27: export interface DefaultProfileOption {
28:   profile_id: string;
29:   profile_name: string;
30:   provider: string;
31:   provider_label: string;
32:   models: DefaultOptionModel[];
33: }
34: 
35: export interface DefaultServiceOptions {
```

位置：134–141。
```tsx
134:  * another window's edits that this SettingsProvider has never loaded. */
135: export function revisionAfterDefaultPatch(
136:   localRevision: string | null,
137:   patchBaseRevision: string,
138:   savedRevision: string,
139: ): string | null {
140:   return localRevision === patchBaseRevision ? savedRevision : localRevision;
141: }
```

### web/components/settings/DefaultModelsEditor.tsx

默认候选 label 与选择后的图标展示；不改默认写入语义

位置：40–46。
```tsx
40: 
41: function profileLabel(profile: DefaultProfileOption): string {
42:   const vendor = profile.provider_label || profile.provider;
43:   if (!vendor || vendor === profile.profile_name) return profile.profile_name;
44:   return `${vendor} · ${profile.profile_name}`;
45: }
46: 
```

### web/components/quiz/FollowupChatComposer.tsx

已补修的线程选择与强度恢复；共享 ChatComposer

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/components/quiz/QuizFollowupTabBody.tsx

历史恢复失败可重试，不能回归

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/context/QuizFollowupContext.tsx

线程级模型和 per-model reasoning prefs，刷新可恢复

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/playwright.phase1.config.ts

复用 disposable source/model fixture/网络白名单/cleanup

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/playwright.model-management-r3.config.ts

新增 wrapper 可参照此文件，不另搭工具链

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/e2e/model-management-r3.spec.ts

现有默认/权限/跟进刷新/隐藏搜索/409 浏览器回归

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### web/e2e/model-discovery-r2.spec.ts

现有供应商目录和参数行为回归

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### tests/services/model_discovery/test_provider_policy.py

现有 custom 两协议等策略行为测试

位置：22–29。
```python
22: 
23: EXPECTED_ADAPTERS = {
24:     "custom": ADAPTER_OPENAI,
25:     "custom_anthropic": ADAPTER_ANTHROPIC,
26:     "azure_openai": ADAPTER_AZURE,
27:     "openrouter": ADAPTER_OPENAI,
28:     "orcarouter": ADAPTER_OPENAI,
29:     "edenai": ADAPTER_OPENAI,
```

### tests/services/model_selection/test_llm_selection.py

现有 custom binding 支持用例

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### scripts/start_selflearn.sh

固定 home 启动器，不用停止真实服务做自动化

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。

### deeptutor/runtime/launcher.py

生产前端按源指纹重建，交付用户重启后生效

本文件用途已定位；任务需要时只读相应接缝，不要求重新全文探索。


# S07 返修：已探索的文件清单 + 关键片段

本包定位当前实际代码，配合 REWORK_S07.txt 执行。不是新的业务契约，不重做全仓orientation。旧 START_S07/探索包/原报告/审查探针均只读。

本轮独立结果：后端26场景，25目标失败/1正例；前端7场景，5目标失败/2正例。目标不是让helper自测通过，而是让实际hydration、调用端、public metadata和最终上下文遵守C08。

关键判断：global资源不是“去掉前缀的库名”；普通user的自有库与授予admin库可同名而不同。CLI可信direct resolver的None兼容与模型调用[]必须分开。
缺目录与legacy空目录不同；原config-only正例必须真实建目录。provider fallback旧读取器吞异常/跟链接，subject边界应改用strict/confined，不修改只读provider_binding。
后端快照已有top-level subject_id；前端hydrate不复制，乐观snapshot只有config，readSnapshotScope两者均没贯通。latestLoadKey只比ID且newSession不失效，纯helper测试无法证明这些接线。
两个非chat _augment_tool_kwargs仍是setdefault，没有server scope；不能把合法请求403和模型伪造路径接受称作“同一执行端已处理”。只补既有调用端，不做新的研究/题目生成模式。
warning目前存在metadata但真实chat prompt和frontend均未消费；PageIndex prompt自称outline不代表真实search结果含retrieval_kind。
RAG顶层deny-list/posix isabs不能保证嵌套metadata和Windows来源安全；真实引擎异常还经core调度原样公开，应在RAG窄边界先映射固定错误，不改所有core工具。

## 可直接运行的审查证据

后端：`.phase1-evidence/reviews/S07/probe_s07.py`（pytest，复用显式临时fixture，只fake服务授权/供应商边界）。
前端：`.phase1-evidence/reviews/S07/probe_frontend.cjs`（TypeScript内存转译并执行实际hydrator/callback/component；非浏览器测试）。
日志：`.phase1-evidence/reviews/S07/execution.log`；机械核对：`submission_integrity.json`；源码恢复/环境归因见同目录归档验证。
原件不可修改；新实现若新增闭包依赖，前端适配仅在rework新证据中补绑定、保留原目标断言，且转永久实际行为测试。

## 当前文件与片段

### `deeptutor/subjects/kb_scope.py`

SHA256 `674b515b016c4b74fba94f22f6522a503f5573532fd0ef37666c817755300dd3`。

L329–L359：
```text
329: 
330: 
331: def _allowed_by_mount(ref: str, mounted: Sequence[str]) -> bool:
332:     """Whether *ref* denotes a resource this turn actually mounted.
333: 
334:     The comparison is by reference identity, or by name segment when both sides
335:     are the same kind of reference (or one of them is a bare name). A subject ref
336:     never matches a global one, even with an identical name.
337:     """
338:     target_name = _ref_name(ref)
339:     target_kind = _ref_kind(ref)
340:     for entry in mounted:
341:         if entry == ref:
342:             return True
343:         if _ref_name(entry) != target_name:
344:             continue
345:         entry_kind = _ref_kind(entry)
346:         if target_kind == entry_kind or "bare" in (target_kind, entry_kind):
347:             return True
348:     return False
349: 
350: 
351: def _mounted_identity(ref: str) -> tuple[str, str, str]:
352:     """What a mounted entry denotes, for ambiguity detection.
353: 
354:     A subject reference is identified by its subject *and* name; every global
355:     spelling of one name (bare, ``user:kb:``, ``admin:kb:``) is one identity,
356:     because the historical resolver answers all of them for the current user.
357:     Two *different* resource families sharing a name are what must never be
358:     guessed between.
359:     """
```

L349–L373：
```text
349: 
350: 
351: def _mounted_identity(ref: str) -> tuple[str, str, str]:
352:     """What a mounted entry denotes, for ambiguity detection.
353: 
354:     A subject reference is identified by its subject *and* name; every global
355:     spelling of one name (bare, ``user:kb:``, ``admin:kb:``) is one identity,
356:     because the historical resolver answers all of them for the current user.
357:     Two *different* resource families sharing a name are what must never be
358:     guessed between.
359:     """
360:     decoded = decode_subject_kb_ref(ref)
361:     if decoded is not None:
362:         return ("subject", decoded[0], decoded[1])
363:     return ("global", "", _ref_name(ref))
364: 
365: 
366: def _unique_mounted_match(ref: str, mounted: Sequence[str]) -> str | None:
367:     """The one mounted resource a bare *ref* names; ``None`` when none matches.
368: 
369:     Spellings of the *same* resource are not an ambiguity (a bare name plus its
370:     explicit wire id denotes one global library): the explicit wire spelling is
371:     preferred so the mounted set keeps a canonical identity. Distinct resources
372:     sharing a name are an ambiguity, and the caller gets ``invalid_input``
373:     rather than a guess between subject and global.
```

L364–L396：
```text
364: 
365: 
366: def _unique_mounted_match(ref: str, mounted: Sequence[str]) -> str | None:
367:     """The one mounted resource a bare *ref* names; ``None`` when none matches.
368: 
369:     Spellings of the *same* resource are not an ambiguity (a bare name plus its
370:     explicit wire id denotes one global library): the explicit wire spelling is
371:     preferred so the mounted set keeps a canonical identity. Distinct resources
372:     sharing a name are an ambiguity, and the caller gets ``invalid_input``
373:     rather than a guess between subject and global.
374:     """
375:     name = _ref_name(ref)
376:     if not is_valid_kb_name(name):
377:         raise json_store.invalid_input("知识库名称非法")
378:     matches = [entry for entry in mounted if _ref_name(entry) == name]
379:     if not matches:
380:         return None
381:     identities = {_mounted_identity(entry) for entry in matches}
382:     if len(identities) > 1:
383:         raise json_store.invalid_input("知识库名称在本轮挂载中不唯一")
384:     for entry in matches:
385:         if _ref_kind(entry) == "global":
386:             return entry
387:     return matches[0]
388: 
389: 
390: # ---------------------------------------------------------------------------
391: # Resolver
392: # ---------------------------------------------------------------------------
393: def _http_error_to_subject_error(exc: BaseException) -> SubjectOperationError:
394:     """Project the legacy ``HTTPException`` of the global resolver onto C02."""
395:     status = getattr(exc, "status_code", None)
396:     if status in (401, 403):
```

L405–L435：
```text
405: 
406: 
407: def _resolve_global(ref: str, *, require_write: bool = False) -> ResolvedSubjectKb:
408:     """Explicit ``admin:kb:`` / ``user:kb:`` — original authorization + audit."""
409:     from deeptutor.multi_user.knowledge_access import resolve_for_rag
410: 
411:     try:
412:         resource = resolve_for_rag(ref)
413:     except SubjectOperationError:
414:         raise
415:     except Exception as exc:  # HTTPException(403/404) and nothing else expected
416:         raise _http_error_to_subject_error(exc) from exc
417:     if resource is None:
418:         raise subject_error(ErrorCode.KB_NOT_FOUND)
419:     return ResolvedSubjectKb(
420:         kb_ref=resource.id,
421:         name=resource.name,
422:         base_dir=Path(resource.base_dir),
423:         subject_id=None,
424:         read_only=bool(resource.read_only),
425:         provider=resolve_bound_provider(
426:             str(resource.base_dir.resolve()), resource.name
427:         ),
428:     )
429: 
430: 
431: def _resolve_subject(
432:     subject_id: str,
433:     kb_name: str,
434:     *,
435:     expected_subject_id: str | None,
```

L429–L479：
```text
429: 
430: 
431: def _resolve_subject(
432:     subject_id: str,
433:     kb_name: str,
434:     *,
435:     expected_subject_id: str | None,
436:     require_ready: bool,
437: ) -> ResolvedSubjectKb:
438:     """One subject library: scope, existence, authorization, then readiness."""
439:     if expected_subject_id is None or subject_id != expected_subject_id:
440:         # Cross-subject access is a scope failure, not a lookup failure. The
441:         # rejection happens before any path or registry read of the other tree.
442:         raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
443:     # ``subject_dir`` validates the slug, confines the path and raises 404 for an
444:     # id that is not registered *for the current user* — never creating it.
445:     store.subject_dir(subject_id)
446:     registered, record = _registration(subject_id, kb_name)
447:     if not registered:
448:         raise subject_error(ErrorCode.KB_NOT_FOUND)
449:     # Confinement of the KB leaf happens before anything is read from it.
450:     kb_dir = confined_kb_dir(subject_id, kb_name)
451: 
452:     base = uploads.kb_base_path(subject_id)
453:     status = ""
454:     if require_ready:
455:         projection = subject_kb_status(subject_id, kb_name, record=record)
456:         status = str(projection.get("status") or "")
457:         if status != "ready":
458:             raise subject_error(ErrorCode.KB_NOT_READY)
459:     return ResolvedSubjectKb(
460:         kb_ref=encode_subject_kb_ref(subject_id, kb_name),
461:         name=kb_name,
462:         base_dir=Path(base),
463:         subject_id=subject_id,
464:         read_only=False,
465:         provider=resolve_bound_provider(str(Path(base).resolve()), kb_name),
466:         status=status,
467:     )
468: 
469: 
470: def resolve_kb_ref(
471:     kb_ref: str,
472:     *,
473:     expected_subject_id: str | None = None,
474:     mounted_refs: Iterable[object] | None = None,
475:     require_ready: bool = True,
476: ) -> ResolvedSubjectKb:
477:     """Resolve one reference to an authorized, server-owned resource.
478: 
479:     ``kb_ref`` is a subject wire id, an existing global wire id, or a bare name:
```

### `deeptutor/services/rag/provider_binding.py`

SHA256 `dbcb607dfe01a2924eabc57cffd71cdb22257ca6c3b7270c9f4f6b1c22869a12`。

L17–L52：
```text
17: 
18: 
19: def load_kb_config_entry(kb_base_dir: str | Path, kb_name: str) -> dict[str, Any]:
20:     """Return the raw ``kb_config.json`` entry for ``kb_name``, if present."""
21:     config_path = Path(kb_base_dir) / "kb_config.json"
22:     if not config_path.exists():
23:         return {}
24:     try:
25:         with open(config_path, encoding="utf-8") as handle:
26:             entry = json.load(handle).get("knowledge_bases", {}).get(kb_name, {})
27:         return entry if isinstance(entry, dict) else {}
28:     except Exception:
29:         return {}
30: 
31: 
32: def load_metadata_provider(kb_base_dir: str | Path, kb_name: str) -> str | None:
33:     """Return the provider stored in legacy ``metadata.json``, if present."""
34:     metadata_path = Path(kb_base_dir) / kb_name / "metadata.json"
35:     if not metadata_path.exists():
36:         return None
37:     try:
38:         with open(metadata_path, encoding="utf-8") as handle:
39:             provider = json.load(handle).get("rag_provider")
40:     except Exception:
41:         return None
42:     return normalize_provider_name(provider) if provider else None
43: 
44: 
45: def resolve_bound_provider(kb_base_dir: str | Path, kb_name: str | None) -> str:
46:     """Resolve the provider DeepTutor has bound to a KB.
47: 
48:     Order:
49:     1. ``kb_config.json``: authoritative runtime state.
50:     2. ``metadata.json``: legacy/import fallback.
51:     3. default provider.
52:     """
```

### `deeptutor/services/session/turn_runtime.py`

SHA256 `bcf6a34b65f80dd80b0db22c72e4726fa978634abc5567fd332b2f9d36ef9dcc`。

L359–L387：
```text
359: 
360: 
361: def _requested_subject(payload: dict[str, Any], raw_config: dict[str, Any]) -> Any:
362:     """The explicit request state: a value, ``None`` (clear) or "absent".
363: 
364:     Both carrier positions are accepted (top-level for SDK/direct callers,
365:     ``config`` for the composer) and compared **as given**: when both are present
366:     they must be the same request, otherwise the turn is rejected as
367:     ``invalid_input`` instead of one silently winning.
368:     """
369:     from deeptutor.subjects import json_store
370: 
371:     top = payload.get("subject_id") if "subject_id" in payload else _SUBJECT_ABSENT
372:     nested = raw_config.get("subject_id") if "subject_id" in raw_config else _SUBJECT_ABSENT
373:     if top is not _SUBJECT_ABSENT and nested is not _SUBJECT_ABSENT:
374:         if _subject_value(top) != _subject_value(nested):
375:             raise json_store.invalid_input("科目参数在两个位置不一致")
376:     chosen = top if top is not _SUBJECT_ABSENT else nested
377:     if chosen is _SUBJECT_ABSENT:
378:         return _SUBJECT_ABSENT
379:     return _subject_value(chosen)
380: 
381: 
382: def resolve_subject_scope(
383:     requested: Any, stored: Any, *, validate: bool = True
384: ) -> str | None:
385:     """Turn the three-state request plus the session preference into one value.
386: 
387:     Omitted keeps the session's stored subject (including its ``None``), an
```

L1307–L1331：
```text
1307:         # a deleted subject must surface as a visible refusal, not as a turn
1308:         # replayed against another subject or a half-regenerated history.
1309:         regenerate_subject = resolve_subject_scope(_snapshot_subject(snapshot), None)
1310: 
1311:         last_message = await self.store.get_last_message(session_id)
1312:         previous_turn_id: str | None = None
1313:         if last_message is not None and last_message.get("role") == "assistant":
1314:             for event in last_message.get("events") or []:
1315:                 turn_id = str((event or {}).get("turn_id") or "")
1316:                 if turn_id:
1317:                     previous_turn_id = turn_id
1318:                     break
1319:             await self.store.delete_message(last_message["id"])
1320: 
1321:         capability = str(
1322:             overrides.get("capability")
1323:             or last_user.get("capability")
1324:             or preferences.get("capability")
1325:             or "chat"
1326:         )
1327:         tools = list(
1328:             overrides.get("tools")
1329:             if overrides.get("tools") is not None
1330:             else preferences.get("tools") or []
1331:         )
```

L1330–L1343：
```text
1330:             else preferences.get("tools") or []
1331:         )
1332:         knowledge_bases = list(
1333:             overrides.get("knowledge_bases")
1334:             if overrides.get("knowledge_bases") is not None
1335:             else preferences.get("knowledge_bases") or []
1336:         )
1337:         language = str(overrides.get("language") or preferences.get("language") or "en")
1338: 
1339:         config: dict[str, Any] = dict(overrides.get("config") or {})
1340:         # The server's resolved scope is the only one this turn may carry: a
1341:         # stale ``config.subject_id`` from the client would otherwise conflict
1342:         # with the snapshot value validated above.
1343:         config.pop("subject_id", None)
```

L2144–L2158：
```text
2144:                     payload.get("knowledge_bases"), subject_id
2145:                 )
2146:             if subject_kb_warnings:
2147:                 logger.warning(
2148:                     "subject knowledge base warnings for turn %s: %s",
2149:                     turn_id,
2150:                     [item["kb_ref"] for item in subject_kb_warnings],
2151:                 )
2152: 
2153:             context = UnifiedContext(
2154:                 session_id=session_id,
2155:                 user_message=effective_user_message,
2156:                 conversation_history=conversation_history,
2157:                 enabled_tools=payload.get("tools"),
2158:                 active_capability=payload.get("capability"),
```

L2187–L2198：
```text
2187:                     # context *and* in the persisted DONE metadata so the
2188:                     # degradation stays verifiable after the turn.
2189:                     "subject_kb_warnings": subject_kb_warnings,
2190:                     "knowledge_bases_mounted": list(mounted_knowledge_bases),
2191:                     "memory_references": memory_references,
2192:                     "question_bank_context": question_bank_context,
2193:                     "memory_context": memory_context,
2194:                     "active_persona": active_persona,
2195:                     "llm_selection": payload.get("llm_selection") or {},
2196:                     "llm_model": str(getattr(llm_config, "model", "") or ""),
2197:                     "llm_provider": str(getattr(llm_config, "provider_name", "") or ""),
2198:                     # Per-turn full-text payload for read_source. Empty when
```

### `deeptutor/agents/chat/agentic_pipeline.py`

SHA256 `301f436f5918774e51e6999fef33c7352203ffb817fbc9f8af5cb69dd03d2067`。

L121–L140：
```text
121: 
122: 
123: def _context_subject_id(context: UnifiedContext) -> str | None:
124:     """The turn's validated subject, read verbatim from the runtime metadata.
125: 
126:     ``None`` (no subject) and ``""`` are both "no subject"; a value is the slug
127:     ``turn_runtime`` already validated. This is the only source the tool scope is
128:     built from — the model cannot contribute to it.
129:     """
130:     raw = (context.metadata or {}).get("subject_id")
131:     if isinstance(raw, str):
132:         value = raw.strip()
133:         return value or None
134:     return None
135: 
136: 
137: # Chat memory tools a partner turn replaces with the partner_* variants.
138: _PARTNER_SUPPRESSED_TOOLS: tuple[str, ...] = ("read_memory", "write_memory")
139: 
140: 
```

L1111–L1129：
```text
1111:             # empty scope must still be the authoritative one, not "whatever the
1112:             # model left behind").
1113:             for key in kb_scope.SCOPE_KWARGS:
1114:                 kwargs.pop(key, None)
1115:             subject_scope = _context_subject_id(context)
1116:             mounted = [str(ref) for ref in (context.knowledge_bases or []) if str(ref).strip()]
1117:             kwargs["_subject_id"] = subject_scope
1118:             # ``None`` and ``[]`` mean different things: a turn with neither a
1119:             # subject nor an explicit selection keeps the historical global
1120:             # resolver, while a subject turn (even an empty one) is answered
1121:             # only from what it mounted.
1122:             kwargs["_mounted_refs"] = mounted if (subject_scope or mounted) else None
1123:         if tool_name == "rag":
1124:             kwargs.setdefault("mode", "hybrid")
1125:         elif tool_name == "kb_files":
1126:             # The report is read by the user as much as by the model, so it is
1127:             # written in the turn's language. Injected server-side; the tool
1128:             # exposes no ``language`` parameter for the model to get wrong.
1129:             kwargs["language"] = context.language or "en"
```

L1663–L1694：
```text
1663: 
1664:     @staticmethod
1665:     def _collect_kb_manifests(
1666:         kbs: list[str],
1667:         *,
1668:         subject_id: str | None = None,
1669:         mounted_refs: list[str] | None = None,
1670:     ) -> list[KbManifest]:
1671:         """Read one inventory per attached library, through the scoped resolver.
1672: 
1673:         A canonical wire reference (``subject:kb:…``/``admin:kb:…``/
1674:         ``user:kb:…`` — what the runtime mounts) is resolved by the shared
1675:         subject resolver, so a same-named library elsewhere is never described.
1676:         A bare name is handed to the historical access-checked manifest seam: no
1677:         runtime turn produces one any more (mounting canonicalises every
1678:         reference), so this only serves direct callers.
1679:         """
1680:         manifests: list[KbManifest] = []
1681:         for kb in kbs:
1682:             try:
1683:                 manifest = _scoped_kb_manifest(
1684:                     kb,
1685:                     subject_id=subject_id,
1686:                     mounted_refs=mounted_refs,
1687:                     limit=MANIFEST_NOTE_LIMIT,
1688:                 )
1689:             except Exception as exc:
1690:                 logger.warning("Failed to read documents of knowledge base '%s': %s", kb, exc)
1691:                 continue
1692:             if manifest is not None:
1693:                 manifests.append(manifest)
1694:         return manifests
```

### `deeptutor/tools/rag_tool.py`

SHA256 `78f569a809756fa885c9317e5bb4d04e2e6391e0030d756eaa669886c1caa3cf`。

L54–L110：
```text
54:     argument wins whenever it is not ``None``.
55:     """
56:     if subject_id is None:
57:         subject_id = _subject_id
58:     if mounted_refs is None:
59:         mounted_refs = _mounted_refs
60:     query = query.strip() if isinstance(query, str) else ""
61:     kb_name = kb_name.strip() if isinstance(kb_name, str) else ""
62:     if not query:
63:         raise ValueError("RAG query must be a non-empty string.")
64:     if not kb_name:
65:         raise ValueError("RAG requires an explicit kb_name.")
66: 
67:     scope: dict[str, Any] | None = None
68:     if kb_base_dir is None:
69:         from deeptutor.subjects import kb_scope
70: 
71:         resource = kb_scope.resolve_kb_ref(
72:             kb_name,
73:             expected_subject_id=subject_id,
74:             mounted_refs=mounted_refs,
75:             require_ready=True,
76:         )
77:         kb_base_dir = str(resource.base_dir)
78:         # The service addresses a library by its canonical *disk* name: the wire
79:         # id is an identity, never a directory name.
80:         kb_name = resource.name
81:         provider = provider or resource.provider
82:         scope = {
83:             "kb_ref": resource.kb_ref,
84:             "name": resource.name,
85:             "subject_id": resource.subject_id,
86:             "read_only": resource.read_only,
87:             "provider": resource.provider,
88:             "kb_dir": str(resource.kb_dir),
89:         }
90: 
91:     service = RAGService(kb_base_dir=kb_base_dir, provider=provider)
92:     result = await service.search(
93:         query=query,
94:         kb_name=kb_name,
95:         event_sink=event_sink,
96:         **kwargs,
97:     )
98:     if scope is not None and isinstance(result, dict):
99:         result[SCOPE_KEY] = scope
100:     return result
101: 
102: 
103: async def initialize_rag(
104:     kb_name: str,
105:     documents: List[str],
106:     provider: Optional[str] = None,
107:     kb_base_dir: Optional[str] = None,
108:     **kwargs,
109: ) -> bool:
110:     """Index ``documents`` into ``kb_name`` using the configured RAG pipeline."""
```

### `deeptutor/tools/builtin/__init__.py`

SHA256 `353af821a3e41ffc7c3daa9ce64f54486acb178eed925cdfa9f9e3bb5a6e5881`。

L114–L144：
```text
114: 
115: 
116: def _public_rag_result(result: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
117:     """The engine's result with its sources replaced by the projected citations.
118: 
119:     ``ToolResult.metadata`` is public (it rides the tool trace and the persisted
120:     events), so the raw ``result["sources"]`` — which may carry a host file path,
121:     an internal directory or a key — is never forwarded as-is.
122:     """
123:     metadata = {
124:         key: value
125:         for key, value in result.items()
126:         if key not in _RAG_RESULT_DENY and not str(key).startswith("_")
127:     }
128:     metadata["sources"] = sources
129:     return metadata
130: 
131: 
132: def _project_path(value: Any, kb_dir: str) -> Any:
133:     """Keep a provenance path useful without leaking the host location."""
134:     if not isinstance(value, str) or not value:
135:         return value
136:     if not os.path.isabs(value):
137:         return value
138:     if kb_dir:
139:         try:
140:             return Path(value).relative_to(Path(kb_dir)).as_posix()
141:         except ValueError:
142:             pass
143:     return Path(value).name
144: 
```

L130–L151：
```text
130: 
131: 
132: def _project_path(value: Any, kb_dir: str) -> Any:
133:     """Keep a provenance path useful without leaking the host location."""
134:     if not isinstance(value, str) or not value:
135:         return value
136:     if not os.path.isabs(value):
137:         return value
138:     if kb_dir:
139:         try:
140:             return Path(value).relative_to(Path(kb_dir)).as_posix()
141:         except ValueError:
142:             pass
143:     return Path(value).name
144: 
145: 
146: def _rag_sources(
147:     result: dict[str, Any],
148:     *,
149:     query: str,
150:     kb_name: str,
151:     scope: dict[str, Any] | None = None,
```

L263–L278：
```text
263:         # public result (it carries the KB directory), it only informs the
264:         # citation identity written below.
265:         scope = result.pop(scope_key, None) if isinstance(result, dict) else None
266:         content = result.get("answer") or result.get("content", "")
267:         sources = _rag_sources(result, query=query, kb_name=kb_name, scope=scope)
268:         return ToolResult(
269:             content=content,
270:             sources=sources,
271:             metadata=_public_rag_result(result, sources),
272:         )
273: 
274: 
275: class KbFilesTool(_PromptHintsMixin, BaseTool):
276:     """Enumerate what a knowledge base holds — the query ``rag`` cannot serve.
277: 
278:     Retrieval returns passages; it cannot report how many documents a KB holds
```

L249–L267：
```text
249:                 **extra_kwargs,
250:             )
251:         except (SubjectOperationError, SubjectStorageError) as exc:
252:             # A refused or unusable scope is a visible tool failure (C02): the
253:             # model gets the fixed message and must not answer from another
254:             # library, and the failure carries the structured code/retryable.
255:             mapped = map_subject_exception(exc)
256:             failure = to_tool_result(mapped)
257:             return ToolResult(
258:                 content=mapped.message,
259:                 success=False,
260:                 metadata=failure["metadata"],
261:             )
262:         # The scope is server-owned and internal: it never becomes part of the
263:         # public result (it carries the KB directory), it only informs the
264:         # citation identity written below.
265:         scope = result.pop(scope_key, None) if isinstance(result, dict) else None
266:         content = result.get("answer") or result.get("content", "")
267:         sources = _rag_sources(result, query=query, kb_name=kb_name, scope=scope)
```

### `deeptutor/agents/question/pipeline.py`

SHA256 `9925a40b572442cecdf8a535ac9050ebf37e6fbaa68a1b649a83792f92cdf12a`。

L1531–L1559：
```text
1531:         return schemas
1532: 
1533:     def _augment_tool_kwargs(
1534:         self,
1535:         tool_name: str,
1536:         args: dict[str, Any],
1537:         context: UnifiedContext,
1538:     ) -> dict[str, Any]:
1539:         kwargs = dict(args)
1540:         turn_id = str(context.metadata.get("turn_id", "") or "").strip()
1541:         task_dir = None
1542:         if turn_id:
1543:             task_dir = get_path_service().get_task_workspace(FEATURE, turn_id)
1544:         if tool_name == "rag":
1545:             kwargs.setdefault("mode", "hybrid")
1546:             if self.kb_name:
1547:                 kwargs.setdefault("kb_name", self.kb_name)
1548:         elif tool_name == "code_execution":
1549:             from deeptutor.services.sandbox import Mount
1550: 
1551:             if task_dir is not None:
1552:                 code_dir = task_dir / "code_runs"
1553:                 code_dir.mkdir(parents=True, exist_ok=True)
1554:                 kwargs["_sandbox_workdir"] = str(code_dir)
1555:                 kwargs["_sandbox_mounts"] = (
1556:                     Mount(host_path=str(code_dir), sandbox_path=str(code_dir), read_only=False),
1557:                 )
1558:         elif tool_name in {"reason", "brainstorm"}:
1559:             kwargs.setdefault("context", context.user_message)
```

### `deeptutor/agents/research/pipeline.py`

SHA256 `ae9cfe9fad64359581e6ffe341c4997323aabcf7d2f59d2045906036a4c8d42e`。

L1823–L1851：
```text
1823:         return schemas
1824: 
1825:     def _augment_tool_kwargs(
1826:         self,
1827:         tool_name: str,
1828:         args: dict[str, Any],
1829:         context: UnifiedContext,
1830:     ) -> dict[str, Any]:
1831:         kwargs = dict(args)
1832:         turn_id = str(context.metadata.get("turn_id", "") or "").strip()
1833:         task_dir = None
1834:         if turn_id:
1835:             task_dir = get_path_service().get_task_workspace("deep_research", turn_id)
1836:         if tool_name == "rag":
1837:             kwargs.setdefault("mode", "hybrid")
1838:             if self.kb_name:
1839:                 kwargs.setdefault("kb_name", self.kb_name)
1840:         elif tool_name == "code_execution":
1841:             from deeptutor.services.sandbox import Mount
1842: 
1843:             if task_dir is not None:
1844:                 code_dir = task_dir / "code_runs"
1845:                 code_dir.mkdir(parents=True, exist_ok=True)
1846:                 kwargs["_sandbox_workdir"] = str(code_dir)
1847:                 kwargs["_sandbox_mounts"] = (
1848:                     Mount(host_path=str(code_dir), sandbox_path=str(code_dir), read_only=False),
1849:                 )
1850:         elif tool_name == "web_search":
1851:             kwargs.setdefault("query", context.user_message)
```

### `deeptutor/services/rag/pipelines/pageindex/pipeline.py`

SHA256 `19b62236169f24e88d0881c9dded14dc31a45987a7d821e93d40414c4b99dda6`。

L160–L200：
```text
160:     TREE_CHARS_PER_DOC = 6000
161: 
162:     async def search(self, query: str, kb_name: str, **_kwargs) -> Dict[str, Any]:
163:         """Return each document's tree outline (titles / pages / summaries).
164: 
165:         The deprecated REST retrieval endpoint is gone; deep, query-driven
166:         retrieval is agentic via the PageIndex MCP tools in chat. For
167:         programmatic callers this returns the documents' real structure as
168:         context — shallow but honest grounding.
169:         """
170:         docs = self.document_map(kb_name)
171: 
172:         if not docs:
173:             return {
174:                 "query": query,
175:                 "answer": (
176:                     "This PageIndex knowledge base has no indexed documents yet. "
177:                     "Add documents before querying."
178:                 ),
179:                 "content": "",
180:                 "sources": [],
181:                 "provider": storage.PROVIDER,
182:                 "needs_reindex": True,
183:             }
184: 
185:         try:
186:             client = self._get_client()
187:             results = await asyncio.gather(
188:                 *(client.get_document(doc_id, summary=True) for doc_id in docs.values()),
189:                 return_exceptions=True,
190:             )
191:         except PageIndexNotConfiguredError as exc:
192:             return {
193:                 "query": query,
194:                 "answer": str(exc),
195:                 "content": "",
196:                 "sources": [],
197:                 "provider": storage.PROVIDER,
198:                 "error_type": "not_configured",
199:             }
200: 
```

L222–L238：
```text
222:             }
223: 
224:         content = "\n\n".join(parts)
225:         return {
226:             "query": query,
227:             "answer": content,
228:             "content": content,
229:             "sources": sources,
230:             "provider": storage.PROVIDER,
231:         }
232: 
233:     @classmethod
234:     def _format_tree(
235:         cls, file_name: str, doc_id: str, tree: Any
236:     ) -> tuple[str, list[dict[str, Any]]]:
237:         """Render a PageIndex tree as an indented outline + per-section sources."""
238:         lines: list[str] = []
```

### `web/lib/subject-scope.ts`

SHA256 `beff7c9c72f58c2eba934016f87b0bcceca21a6d12ec26d3c54e1924f4acc6ee`。

L107–L131：
```text
107: 
108: /** Read the scope recorded on a stored request snapshot. */
109: export function readSnapshotScope(snapshot: unknown): SnapshotScope {
110:   const record =
111:     snapshot && typeof snapshot === "object"
112:       ? (snapshot as Record<string, unknown>)
113:       : {};
114:   for (const key of ["subject_id", "subjectId"] as const) {
115:     if (key in record) {
116:       return { hasScope: true, value: normalizeSubject(record[key]) };
117:     }
118:   }
119:   return { hasScope: false, value: null };
120: }
121: 
122: /**
123:  * The `subject_id` a retry / edit / replay must send.
124:  *
125:  * The original turn is the authority: an explicit value (including `null`) is
126:  * replayed as-is, and a legacy snapshot that never recorded a scope replays as
127:  * 无科目 — inheriting the *current* preference would rewrite history (the
128:  * backend applies the same rule, so both ends agree).
129:  */
130: export function subjectForReplay(snapshot: unknown): string | null {
131:   const recorded = readSnapshotScope(snapshot);
```

L167–L183：
```text
167:  * optional replayed snapshot. One decision point, used by every send path.
168:  */
169: export function resolveSendSubject(
170:   scope: SubjectSessionScope | undefined,
171:   snapshot?: unknown,
172: ): string | null {
173:   if (snapshot !== undefined && snapshot !== null) return subjectForReplay(snapshot);
174:   return subjectForRequest(scope ?? newSessionScope());
175: }
176: 
177: /**
178:  * Apply one scope event to a session's scope.
179:  *
180:  * This *is* the reducer's subject logic (``MARK_SESSION_LOADING`` /
181:  * ``LOAD_SESSION`` / ``SET_SUBJECT_ID`` call it), so the rules cannot drift
182:  * between the state store and the tests:
183:  *
```

### `web/context/UnifiedChatContext.tsx`

SHA256 `6ee0ce74e747a566dbfe14d1e34f5a2498f58a8752013f1e7d6a0b2b8ba8a658`。

L1042–L1112：
```text
1042: }
1043: 
1044: function hydrateRequestSnapshot(
1045:   message: SessionMessage,
1046:   content: string,
1047:   attachments: MessageAttachment[],
1048: ): MessageRequestSnapshot | undefined {
1049:   const metadata = asRecord(message.metadata);
1050:   const stored = asRecord(
1051:     metadata?.request_snapshot ?? metadata?.requestSnapshot,
1052:   );
1053:   if (!stored) return undefined;
1054: 
1055:   const snapshot: MessageRequestSnapshot = {
1056:     content: typeof stored.content === "string" ? stored.content : content,
1057:     capability:
1058:       typeof stored.capability === "string"
1059:         ? stored.capability
1060:         : message.capability || "",
1061:     enabledTools: asStringArray(stored.enabledTools),
1062:     knowledgeBases: asStringArray(stored.knowledgeBases),
1063:     language: typeof stored.language === "string" ? stored.language : "en",
1064:     ...(attachments.length ? { attachments } : {}),
1065:   };
1066: 
1067:   const config = asRecord(stored.config);
1068:   const notebookReferences = asNotebookReferences(stored.notebookReferences);
1069:   const historyReferences = asStringArray(stored.historyReferences);
1070:   const questionNotebookReferences = asQuestionReferences(
1071:     stored.questionNotebookReferences,
1072:   );
1073:   const persona =
1074:     typeof stored.persona === "string" && stored.persona.length > 0
1075:       ? stored.persona
1076:       : "";
1077:   const memoryReferences = asMemoryReferences(stored.memoryReferences);
1078:   const bookReferences = normalizeBookReferences(stored.bookReferences);
1079:   const llmSelection = asLLMSelection(stored.llmSelection);
1080:   const masteryPathId =
1081:     typeof (stored.masteryPathId ?? stored.mastery_path_id) === "string"
1082:       ? String(stored.masteryPathId ?? stored.mastery_path_id).trim()
1083:       : "";
1084: 
1085:   if (config && Object.keys(config).length) snapshot.config = config;
1086:   if (notebookReferences.length)
1087:     snapshot.notebookReferences = notebookReferences;
1088:   if (historyReferences.length) snapshot.historyReferences = historyReferences;
1089:   if (questionNotebookReferences.length) {
1090:     snapshot.questionNotebookReferences = questionNotebookReferences;
1091:   }
1092:   if (bookReferences.length) snapshot.bookReferences = bookReferences;
1093:   if (persona) snapshot.persona = persona;
1094:   if (memoryReferences.length) snapshot.memoryReferences = memoryReferences;
1095:   if (llmSelection) snapshot.llmSelection = llmSelection;
1096:   if (masteryPathId) snapshot.masteryPathId = masteryPathId;
1097:   return snapshot;
1098: }
1099: 
1100: export function UnifiedChatProvider({
1101:   children,
1102: }: {
1103:   children: React.ReactNode;
1104: }) {
1105:   const [state, dispatch] = useReducer(reducer, initialState);
1106:   const stateRef = useRef(initialState);
1107:   const runnersRef = useRef<
1108:     Map<
1109:       string,
1110:       {
1111:         key: string;
1112:         client: UnifiedWSClient;
```

L1445–L1480：
```text
1445:   }, []);
1446: 
1447:   const latestLoadKeyRef = useRef<string | null>(null);
1448: 
1449:   const loadSession = useCallback(
1450:     async (
1451:       sessionId: string,
1452:       options?: { signal?: AbortSignal; revalidate?: boolean },
1453:     ) => {
1454:       // Entering a session: its stored subject is not known yet, so close the
1455:       // send gate (and drop any scope this tab carried) before the fetch.
1456:       if (!options?.revalidate) {
1457:         latestLoadKeyRef.current = sessionId;
1458:         dispatch({ type: "MARK_SESSION_LOADING", key: sessionId });
1459:       }
1460:       const session = await getSession(sessionId, options?.signal);
1461:       const key = session.session_id || session.id;
1462:       // If the user navigated somewhere else while this fetch was in flight the
1463:       // response is stale: it may fill *its own* session's cache, but it must
1464:       // not select that session (which would also put its subject scope back on
1465:       // screen over the new one).
1466:       const superseded =
1467:         !options?.revalidate && latestLoadKeyRef.current !== sessionId;
1468:       const activeTurn = Array.isArray(session.active_turns)
1469:         ? session.active_turns[0]
1470:         : undefined;
1471:       if (options?.revalidate) {
1472:         // Background refresh of a session already on screen. Drop the whole
1473:         // snapshot — data *and* the re-subscribe below — once a turn is live
1474:         // locally: this tab is already receiving that turn's events, so
1475:         // re-subscribing from ``after_seq: 0`` would replay them on top of
1476:         // what we have, and the snapshot predates the turn anyway.
1477:         const local = stateRef.current.sessions[key];
1478:         if (!local || local.isStreaming || local.status === "running") return;
1479:       }
1480:       const messages = hydrateMessages(session.messages ?? []);
```

L1690–L1725：
```text
1690:           mime_type: a.mime_type,
1691:         })) ?? msgAttachments;
1692:       const effectiveSubject = resolveSendSubject(session, replaySnapshot);
1693:       // Capability config first, subject merged last: the capability's own
1694:       // fields survive and a clear is an explicit ``null`` (the key is always
1695:       // present), never a dropped key that the backend would read as "inherit".
1696:       const effectiveConfig = mergeSubjectIntoConfig(
1697:         config ?? replaySnapshot?.config,
1698:         effectiveSubject,
1699:       );
1700:       const effectiveNotebookReferences =
1701:         replaySnapshot?.notebookReferences ?? notebookReferences;
1702:       const effectiveHistoryReferences =
1703:         replaySnapshot?.historyReferences ?? historyReferences;
1704:       const effectiveQuestionNotebookReferences =
1705:         replaySnapshot?.questionNotebookReferences ??
1706:         questionNotebookReferences;
1707:       const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
1708:         content,
1709:         capability: effectiveCapability,
1710:         enabledTools: [...effectiveTools],
1711:         knowledgeBases: [...effectiveKnowledgeBases],
1712:         language: effectiveLanguage,
1713:         ...(effectiveAttachments?.length
1714:           ? { attachments: effectiveAttachments }
1715:           : {}),
1716:         ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
1717:           ? { config: effectiveConfig }
1718:           : {}),
1719:         ...(effectiveNotebookReferences?.length
1720:           ? { notebookReferences: effectiveNotebookReferences }
1721:           : {}),
1722:         ...(effectiveHistoryReferences?.length
1723:           ? { historyReferences: [...effectiveHistoryReferences] }
1724:           : {}),
1725:         ...(effectiveQuestionNotebookReferences?.length
```

L2019–L2028：
```text
2019:   }, []);
2020: 
2021:   const newSession = useCallback(() => {
2022:     dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
2023:   }, [makeDraftKey]);
2024: 
2025:   const editMessage = useCallback(
2026:     async (messageId: number, newContent: string) => {
2027:       const trimmed = newContent.trim();
2028:       if (!trimmed) return;
```

### `web/components/chat/home/SubjectSelector.tsx`

SHA256 `7a49c0fb11a04c7432b3dc0d53a36a5f121746238d68034890a8273cbd9ccbff`。

L39–L60：
```text
39:   const [open, setOpen] = useState(false);
40:   const ref = useRef<HTMLDivElement>(null);
41:   const current = subjects.find((s) => s.id === value);
42: 
43:   useEffect(() => {
44:     if (!open) return;
45:     const close = (e: MouseEvent) => {
46:       if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
47:     };
48:     document.addEventListener("mousedown", close);
49:     return () => document.removeEventListener("mousedown", close);
50:   }, [open]);
51: 
52:   if (subjects.length === 0) return null;
53: 
54:   // Same placement + viewport-safe width contract as the other composer
55:   // selectors, so a long subject name cannot push the menu off-screen either.
56:   const menuPlacementClass =
57:     placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5";
58: 
59:   return (
60:     <div ref={ref} className="relative">
```

### `web/app/(workspace)/home/[[...sessionId]]/page.tsx`

SHA256 `8fcdedd51ae65fa113e8f7f9551eb66485d302fa78d685e738f22027be1b8c9c`。

L1539–L1561：
```text
1539:   // is restored from the session's preferences on load, cleared when switching
1540:   // sessions, and never carried from one conversation into another.
1541:   const subjectId = state.subjectId ?? "";
1542:   const subjectHydrated = state.subjectHydrated;
1543:   const [subjectOptions, setSubjectOptions] = useState<{ id: string; name: string }[]>([]);
1544:   useEffect(() => {
1545:     let cancelled = false;
1546:     void (async () => {
1547:       try {
1548:         const res = await apiFetch("/api/v1/subjects");
1549:         if (res.ok) {
1550:           const data = await res.json();
1551:           if (!cancelled) setSubjectOptions(data.subjects ?? []);
1552:         }
1553:       } catch {
1554:         /* subjects unavailable */
1555:       }
1556:     })();
1557:     return () => {
1558:       cancelled = true;
1559:     };
1560:   }, []);
1561:   const subagentBudget = null;
```

L1577–L1588：
```text
1577:       // drop it or send the wrong one. Wait for hydration (the composer shows
1578:       // the pending state) instead of guessing.
1579:       if (!subjectHydrated) return;
1580: 
1581:       let extraAttachments = attachments.map((a) => ({
1582:         type: a.type,
1583:         filename: a.filename,
1584:         base64: a.base64,
1585:         mime_type: a.mimeType,
1586:       }));
1587:       let config: Record<string, unknown> | undefined;
1588: 
```

### `deeptutor/api/routers/unified_ws.py`

SHA256 `5a6bed835c44b05702bc32b0e0c0a1a2c9843a5fc420a1e0f954c1b55e5e7b60`。

L156–L178：
```text
156:                 try:
157:                     _, turn = await runtime.start_turn(msg)
158:                 except (SubjectOperationError, SubjectStorageError) as exc:
159:                     # A refused subject scope (unknown/foreign subject, conflict,
160:                     # bad type) is a business error: project it through C02
161:                     # instead of the generic ``str(exc)`` branch. The
162:                     # ``RuntimeError`` compatibility branch below is unchanged.
163:                     await reject_subject_error(
164:                         exc, session_id=str(msg.get("session_id") or "")
165:                     )
166:                     continue
167:                 except RuntimeError as exc:
168:                     await safe_send(
169:                         {
170:                             "type": "error",
171:                             "source": "unified_ws",
172:                             "stage": "",
173:                             "content": str(exc),
174:                             "metadata": {"turn_terminal": True, "status": "rejected"},
175:                             "session_id": str(msg.get("session_id") or ""),
176:                             "turn_id": "",
177:                             "seq": 0,
178:                         }
```

### `deeptutor/subjects/errors.py`

SHA256 `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88`。

L401–L419：
```text
401: 
402: 
403: def to_tool_result(error: SubjectOperationError) -> dict[str, Any]:
404:     """ToolResult 失败形态：``success=False`` 且 ``metadata.error`` 同构。
405: 
406:     调用者负责用它构造真正的 ToolResult；这里只固定失败语义与 error 数据，
407:     不返回任何 artifact URL。
408:     """
409:     return {"success": False, "metadata": {"error": to_error_dict(error)}}
410: 
411: 
412: __all__ = [
413:     "ERROR_SPECS",
414:     "ErrorCode",
415:     "ErrorSpec",
416:     "MAX_MESSAGE_LENGTH",
417:     "StorageCorruptError",
418:     "StorageIOError",
419:     "SubjectOperationError",
```

### `deeptutor/multi_user/knowledge_access.py`

SHA256 `54bc1a02a711ced8718ac596a08d3c8169cd4403578562e61f45ac7d0e7302c2`。

L86–L125：
```text
86:     assigned_names = _assigned_admin_names()
87: 
88:     if requested_source == "admin":
89:         if name not in assigned_names:
90:             raise HTTPException(status_code=403, detail="Knowledge base is not assigned to you")
91:         if require_write:
92:             raise HTTPException(
93:                 status_code=403, detail="Assigned admin knowledge bases are read-only"
94:             )
95:         return KnowledgeResource(
96:             id=f"admin:kb:{name}",
97:             name=name,
98:             base_dir=admin_kb_base_dir(),
99:             source="admin",
100:             assigned=True,
101:             read_only=True,
102:         )
103: 
104:     if requested_source == "user":
105:         resolved = _resolve_default_or_name(user_manager, name)
106:         return KnowledgeResource(
107:             id=f"user:kb:{resolved}",
108:             name=resolved,
109:             base_dir=current_kb_base_dir(),
110:             source="user",
111:             assigned=False,
112:             read_only=False,
113:         )
114: 
115:     if name.lower() in DEFAULT_KB_ALIASES:
116:         resolved = _resolve_default_or_name(user_manager, name)
117:         return KnowledgeResource(
118:             id=f"user:kb:{resolved}",
119:             name=resolved,
120:             base_dir=current_kb_base_dir(),
121:             source="user",
122:             assigned=False,
123:             read_only=False,
124:         )
125: 
```

### `deeptutor/core/agentic/tool_dispatch.py`

SHA256 `57f2ff01220fb2124fbef1cbe5de98c3ebed2a2a65a330920b9fe6c22c98452d`。

L605–L624：
```text
605:                     trace_kind="call_status",
606:                     call_state="error",
607:                     error=str(exc),
608:                 ),
609:             )
610:         unknown_msg = (
611:             unknown_error_message_factory(tool_name)
612:             if unknown_error_message_factory is not None
613:             else f"Error executing {tool_name}: {exc}"
614:         )
615:         return {
616:             "result_text": unknown_msg,
617:             "success": False,
618:             "sources": [],
619:             "metadata": {"error": str(exc)},
620:             "terminate_turn": False,
621:             "pause_for_user": None,
622:         }
623: 
624: 
```

### `deeptutor/subjects/uploads.py`

SHA256 `439e0de6c389f819ff8f85d54365b01baee48d15732bdefedb766ad0f7d7aba5`。

L277–L311：
```text
277: 
278: 
279: def kb_base_path(subject_id: str, *, create: bool = False) -> Path:
280:     """The subject's ``knowledge_bases`` root, confined (created only on write).
281: 
282:     A GET must not bring the directory into existence, so the read paths use
283:     ``create=False`` and the store helper that always mkdir's is not used.
284:     """
285:     directory = store.subject_dir(subject_id)
286:     base = json_store.confined(directory, directory / "knowledge_bases")
287:     if create:
288:         json_store.make_directory(base)
289:     return base
290: 
291: 
292: def kb_paths(
293:     subject_id: str, kb_name: str, *, create: bool = False
294: ) -> tuple[Path, Path]:
295:     """``(kb_dir, raw_dir)`` strictly inside the subject's own KB root.
296: 
297:     A KB whose ``kb_config.json`` points at a linked external index is refused
298:     instead of being written through: the subject upload entry must never turn
299:     into a writer for a library outside this subject.
300:     """
301:     base = kb_base_path(subject_id, create=create)
302:     kb_dir = json_store.confined(
303:         base, base / json_store.safe_segment(kb_name, what="知识库名称")
304:     )
305:     if not _same_path(resolve_kb_dir(base, kb_name), kb_dir):
306:         raise subject_error(ErrorCode.SCOPE_FORBIDDEN)
307:     raw_dir = json_store.confined(kb_dir, kb_dir / "raw")
308:     if create:
309:         json_store.make_directory(kb_dir)
310:         json_store.make_directory(raw_dir)
311:     return kb_dir, raw_dir
```

### `deeptutor/subjects/material_manifest.py`

SHA256 `d80aaf5e653ff411d292001ef945b919fd5998d15793f5c303700883f422c79b`。

L580–L616：
```text
580: 
581: 
582: def project_status(
583:     *,
584:     kb_dir: Path,
585:     raw_dir: Path,
586:     materials_dir: Path | None,
587:     subject_id: str,
588:     kb_name: str,
589:     manager_status: dict | None,
590:     worker_alive: bool = False,
591:     queued: bool = False,
592:     task_id: str | None = None,
593:     verify_hashes: bool = False,
594: ) -> dict:
595:     """Read-only projection of one subject KB's count, source and index state.
596: 
597:     Never writes, never schedules, never consults the auto-registering
598:     ``list_knowledge_bases``. The returned dict keeps the historical
599:     ``{status, progress, updated_at}`` shape (plus ``documents``/``task_id``/
600:     counters) and the ``progress`` payload is rebuilt from fixed copy — the
601:     global background tasks store raw diagnostics in ``progress``, and those
602:     must not reach a client.
603:     """
604:     raw_files = source_files(raw_dir, digest=verify_hashes)
605:     documents = len(raw_files)
606:     manifest = load_manifest(kb_dir, subject_id=subject_id, kb_name=kb_name)
607:     index_state = load_index_state(kb_dir, subject_id=subject_id, kb_name=kb_name)
608:     manager_status = manager_status or {}
609: 
610:     if manifest is None:
611:         # Legacy library: no recorded source identity to compare against. The
612:         # first successful upload is what establishes a manifest; a GET never
613:         # writes one.
614:         manifest_diff: dict = {"ok": True, "legacy": True}
615:         expected_fingerprint = fingerprint(raw_files) if verify_hashes else None
616:     else:
```

### `tests/phase1/test_p1_20.py`

SHA256 `f59d4737e23b015282d105e64c58cf683e6ad31f43de6b7a93111c0ac72b0bcb`。

L327–L352：
```text
327: 
328: 
329: def test_a_library_known_only_by_its_config_entry_still_resolves(libraries):
330:     """kb_config 条目本身就是登记：不需要 knowledge.json 记录也在。
331: 
332:     一个没有源、也没有已发布索引的 legacy 库由 S05 的兼容分支判 ready；这里如实
333:     断言解析沿用**同一投影**，而不是新造一套 ready 判据。
334:     """
335:     subject = libraries["A"]
336:     _write_kb_config(subject, {"config-only-kb": {"status": "ready"}})
337:     resolved = kb_scope.resolve_kb_ref(
338:         _ref(subject, "config-only-kb"), expected_subject_id=subject.subject_id
339:     )
340:     assert resolved.name == "config-only-kb"
341:     assert resolved.kb_dir == Path(subject.knowledge_bases) / "config-only-kb"
342:     assert resolved.status == "ready"
343:     assert kb_scope.is_subject_kb_registered(subject.subject_id, "config-only-kb") is True
344:     assert kb_scope.is_subject_kb_registered(subject.subject_id, "ghost-kb") is False
345: 
346: 
347: # ---------------------------------------------------------------------------
348: # readiness 只来自源/索引投影
349: # ---------------------------------------------------------------------------
350: def test_not_ready_libraries_are_refused(libraries):
351:     """stale / error / rebuilding / initializing / 假 ready 全部 409。"""
352:     subject = libraries["A"]
```

### `tests/phase1/test_p1_21.py`

SHA256 `0b84b381f356053ccf7b52c2dc57007d8a9af26613dddf17100398071b9e3639`。

L497–L538：
```text
497: 
498: 
499: def test_both_stores_project_the_same_subject_scope(runtime_env):
500:     subject_a = helpers.make_subject(runtime_env.admin_root, "科目A")
501:     a = subject_a.subject_id
502: 
503:     async def scenario() -> None:
504:         sqlite = runtime_env.store
505:         memory = _MemoryStore()
506:         sqlite_session = await sqlite.create_session()
507:         memory_session = await memory.create_session()
508:         requests = [None, "", "   ", a, "不存在的科目", "../x", 7]
509: 
510:         for request in requests:
511:             for store, session_id in (
512:                 (sqlite, sqlite_session["id"]),
513:                 (memory, memory_session["id"]),
514:             ):
515:                 await store.update_session_preferences(
516:                     session_id, {"subject_id": request if request in (None, "", a) else None}
517:                 )
518:             stored_sqlite = await _preference(runtime_env, sqlite_session["id"])
519:             stored_memory = (await memory.get_session(memory_session["id"]))["preferences"][
520:                 "subject_id"
521:             ]
522:             assert stored_sqlite == stored_memory, request
523: 
524:             results = []
525:             for stored in (stored_sqlite, stored_memory):
526:                 try:
527:                     results.append(("ok", resolve_subject_scope(request, stored)))
528:                 except SubjectOperationError as exc:
529:                     results.append(("error", exc.code.value))
530:             assert results[0] == results[1], request
531: 
532:         # 真实 SQLite 也必须原样保存显式 None（不能被当成"没设置"丢掉）。
533:         await sqlite.update_session_preferences(sqlite_session["id"], {"subject_id": None})
534:         assert await _preference(runtime_env, sqlite_session["id"]) is None
535:         await memory.update_session_preferences(memory_session["id"], {"subject_id": None})
536:         assert (await memory.get_session(memory_session["id"]))["preferences"]["subject_id"] is None
537: 
538:         # 冲突在任何 store 上都在写入之前失败。
```

### `tests/phase1/test_p1_22.py`

SHA256 `129830fe0d6cd018f352792c3973e8789c75080dab17195dab793bf1a6343514`。

L318–L349：
```text
318: 
319: 
320: def test_a_not_ready_library_is_not_mounted_and_the_warning_is_visible(runtime_env):
321:     admin_root = runtime_env.admin_root
322:     subject = helpers.make_subject(admin_root, "科目A")
323:     ready_dir = _make_ready_kb(subject, "kb-ready", marker="ready", kb_type="assignment")
324:     stale_dir = _make_ready_kb(subject, "kb-stale", marker="stale", kb_type="textbook")
325:     # 让 stale 库的已发布索引落后于当前源：真实 stale，不是"状态缺失"。
326:     (Path(stale_dir) / "raw" / "stale.txt").write_text("stale changed\n", encoding="utf-8")
327:     assert ready_dir.exists()
328: 
329:     # 另有一个 registry 说 ready、但没有任何测量结果的库：同样不算 ready。
330:     _publish_ready(subject, "kb-unknown", marker="unknown", kb_type="ppt")
331:     manifest_mod.index_state_path(Path(subject.knowledge_bases) / "kb-unknown").unlink()
332:     _write_kb_config(subject, {"kb-unknown": {"status": "ready"}})
333:     store.upsert_knowledge_record(
334:         subject.subject_id, {"kb_name": "kb-unknown", "type": "ppt", "documents": 1}
335:     )
336: 
337:     events = _turn(runtime_env, {"subject_id": subject.subject_id})
338: 
339:     mounted = _CapturingOrchestrator.captured["knowledge_bases"]
340:     assert mounted == [kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-ready")], mounted
341: 
342:     warnings = _done(events)["metadata"]["subject_kb_warnings"]
343:     by_ref = {item["kb_ref"]: item for item in warnings}
344:     assert set(by_ref) == {
345:         kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-stale"),
346:         kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-unknown"),
347:     }
348:     assert by_ref[kb_scope.encode_subject_kb_ref(subject.subject_id, "kb-stale")]["status"] == "stale"
349:     assert (
```

### `tests/phase1/test_p1_23.py`

SHA256 `b46c7b58dc6861297f95b3b525c6c12856b030dba4731eb255824ec6476952a8`。

L399–L423：
```text
399:     assert failing["success"] is not False
400:     assert len(service.instances) == 1
401:     service.class_error = RuntimeError("engine exploded")
402:     failed = _execute(
403:         monkeypatch,
404:         pipeline,
405:         _context(subject_id="科目a", mounted=[three_libraries.ref_a]),
406:         {"query": "q", "kb_name": three_libraries.ref_a},
407:     )
408:     # 检索失败是可见的失败结果，而不是"再试一次别的库"。
409:     assert failed["success"] is False
410:     assert "engine exploded" in json.dumps(failed, ensure_ascii=False)
411:     # 只多了一次调用，且仍然是本科目录：没有"失败后换全局库再试"。
412:     assert len(service.instances) == 2
413:     assert service.instances[1].base_dir == str(subject_a.knowledge_bases)
414:     assert not any(
415:         inst.base_dir == str(helpers.global_kb_root(three_libraries.admin_root))
416:         for inst in service.instances
417:     )
418: 
419: 
420: def test_sources_keep_real_provenance_and_never_leak_host_paths(
421:     monkeypatch, service, three_libraries
422: ):
423:     pipeline = _pipeline(monkeypatch)
```

### `tests/phase1/test_p1_24.py`

SHA256 `bb4204cd61cbaa67090bc7307da09698417cb795a44e168e5a192866b223cca7`。

L337–L364：
```text
337: 
338: 
339: def test_a_pageindex_turn_reaches_the_existing_outline_without_inventing_mcp(
340:     monkeypatch, p1_runtime
341: ):
342:     from deeptutor.subjects import kb_scope as scope
343: 
344:     subject = helpers.make_subject(p1_runtime, "科目A")
345:     _make_pageindex_kb(subject)
346:     ref = scope.encode_subject_kb_ref(subject.subject_id, "pageindex-kb")
347:     pipeline = _pipeline(monkeypatch)
348:     context = _context(subject_id=subject.subject_id, mounted=[ref], tools=["rag"])
349: 
350:     asyncio.run(pipeline._prepare_deferred_tools(context))
351: 
352:     # 既有 rag outline 路径可达：这个库没有被排除在 rag 之外。
353:     assert pipeline._coexisting_rag_kbs(context) == [ref]
354:     assert _schema_for(pipeline, context, "rag")["parameters"]["properties"]["kb_name"][
355:         "enum"
356:     ] == [ref]
357:     assert ref in pipeline._pageindex_docs
358: 
359:     note = pipeline._pageindex_system_note()
360:     assert "retrieval_kind=outline" in note
361:     assert "pageindex-kb" in note and ref in note
362:     # 如实说明能力边界：既不虚构 MCP 工具，也不出现任何 mcp_* 工具名。
363:     assert "mcp" not in note.lower()
364:     assert "no additional deep-retrieval tool" in note
```

### `web/tests/phase1-25.test.ts`

SHA256 `2ac557ddea1647498e96199c801cb0690acb198f000348a218cd6ac5bf567281`。

按符号定向阅读：`test("replay`（相邻逻辑；未生成不准确行号）。

### `tests/agents/chat/test_message_build.py`

SHA256 `0585aac7e44aa027dfa223fd6cc2be7a56c24236b2494cd60791f44b18ac8f0b`。

L12–L56：
```text
12: 
13: 
14: def test_summary_system_message_reaches_messages() -> None:
15:     pipeline = AgenticChatPipeline(language="en")
16:     context = UnifiedContext(
17:         session_id="s1",
18:         user_message="next question",
19:         conversation_history=[
20:             {"role": "system", "content": "earlier turns summary"},
21:             {"role": "user", "content": "old question"},
22:             {"role": "assistant", "content": "old answer"},
23:         ],
24:     )
25: 
26:     messages = pipeline._build_loop_messages(
27:         context=context,
28:         enabled_tools=[],
29:     )
30: 
31:     # The summary rides directly after the main system prompt, before history.
32:     assert messages[1]["role"] == "system"
33:     assert "earlier turns summary" in str(messages[1]["content"])
34:     assert messages[2] == {"role": "user", "content": "old question"}
35:     # Exactly one summary injection — no duplicates elsewhere.
36:     summary_count = sum(
37:         1
38:         for m in messages[1:]
39:         if m["role"] == "system" and "earlier turns summary" in str(m["content"])
40:     )
41:     assert summary_count == 1
42: 
43: 
44: def test_empty_system_entries_still_filtered() -> None:
45:     pipeline = AgenticChatPipeline(language="en")
46:     context = UnifiedContext(
47:         session_id="s1",
48:         user_message="q",
49:         conversation_history=[
50:             {"role": "system", "content": "   "},
51:             {"role": "user", "content": "old question"},
52:         ],
53:     )
54: 
55:     messages = pipeline._build_loop_messages(
56:         context=context,
```

### `tests/tools/test_rag_tool.py`

SHA256 `ae08738ee165f556650f0f752e3b8eec63dccf4a85989e0e1e7de248f34128e6`。

按符号定向阅读：`def test_raganything_alias`（相邻逻辑；未生成不准确行号）。

## 范围与前置

允许23路径与R1–R8符号范围以REWORK_S07为准。最新receipt冻结82条源码；59条S01–S06源码只读。新补5个接缝均是当前已有功能/测试，不提前做第二阶段。
所有用户数据保持原样。跨目录pytest收集前由S01 launcher初始化临时HOME；不能复制真实settings。
报告必须区分：两项已独立证明的历史模型配置失败、两个embedding配置导致的旧skip、DNS旧skip，以及本轮真实功能失败。浏览器总验收留S15，不把后端/Node通过扩写成全项目无bug。

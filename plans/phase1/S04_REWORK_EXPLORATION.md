# S04返修：已探索文件清单 + 关键片段

探索日期：2026-10-13。项目根 `/home/albert/selflearn/selflearn`。配合 `REWORK_S04.txt` 使用；这是当前S04提交版，旧首次探索包的源码hash已过时。

先核 `.phase1-evidence/stages/S04/review.json` 指向的changes_requested receipt、当前37个源码hash和本包hash；源码未变可复用片段直接返修，不做全仓库orientation。实现需要的上下文只按相邻符号补读；hash变化查最小diff，不覆盖文件恢复旧版本。

## 1. 文件与探索范围

| 相对项目根路径 | SHA256 | 已探索范围/用途 |
|---|---|---|
| `plans/phase1/REWORK_S04.txt` | `532be013b3456ec29507c7b91bb29f404e095e06ab689202b431744981e82838` | 本轮R1–R5目标/六路径范围/证据/完成门。 |
| `plans/phase1/stages/S04.md` | `099b7064374d770b722f74a7d1e7ea5b3d89de2db3226f52a199d8c995ec3990` | changes_requested；原六卡阶段，返修不进入S05。 |
| `plans/phase1/START_S04.txt` | `69a2b1a298b3db51d9a56e5c558d6c1ea7b0f9e0a1f1222511df8b3d6dc5cba0` | 原阶段业务规范与保护；本轮按REWORK收窄范围。 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | 已读C01–C06/C14；精确模型枚举、身份、固定安全响应与阶段证据。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | 已查ExamCandidate/ExamStored/DetectionResponse/Warning/ErrorResponse/StageReport，契约只读。 |
| `deeptutor/subjects/exam_detection.py` | `c23e3a9ffec2426320c77cc55e273e9f6df3e167f19b223188dafae2253deade` | 已读全文件；R1候选level、parse_points与实际调用/提示词/负向排除。 |
| `deeptutor/subjects/exam_points.py` | `1f489e69f8561c430d9e6ec727dc18a17a4ea008a8ab4d832b2e2d250f002a93` | 已读校验/构造/手工add与新upsert；R1批量候选、R2批内确认、R3复用元数据。 |
| `deeptutor/api/subject_route.py` | `ade5386fe045fdc976b5ce581d215b82b2cecaf11664594b8631189238aca412` | 已读全文件；R4错误边界、HTTPException放行、日志诊断。 |
| `deeptutor/api/routers/subjects.py` | `386ac975bc998b6fbaeea16ad7ae24feae1b3ee7da9ca43ffb8aa2badb695a63` | 定向读check/detect/PATCH及review-pack/report捕获LLM异常；当前只读，R4在wrapper解决。 |
| `deeptutor/subjects/grading.py` | `8c1c8d68ecd832accb0f1aa289c57b901cecbb70edeae0f2672f4631e5c6ed1f` | 已读全文件，实际generation/枚举/反馈；本轮保留只读。 |
| `deeptutor/subjects/wrong_book.py` | `957813c428f45a8f8d691e28bc580c70f4b00110a2820381de6fed65fde2d6ab` | 已读单次submit/new_entry/attempt/读视图；本轮保留原子提交，只读。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 已查异常类型、mapper和固定HTTP投影；只读，不靠消息分类。 |
| `deeptutor/subjects/model_output.py` | `7ebe1f77d497ed3dcf11914540f14e4d83d026160e3165d7311dc1a2c95e77f8` | 已查ModelOutputError.reason及严格对象入口；只读。 |
| `tests/phase1/test_p1_07.py` | `23ac0ec2c669bce4cf49704d10ca56a1db347c8c2d0965b0dbbe05deae079a54` | 已查schema/引用/负向护栏/实际generation与冲突的level归一化正例。 |
| `tests/phase1/test_p1_08.py` | `fe2e4b0d4f7389e776e7a31d4e05ec258f2594c470b8d76326f9734235b9f60d` | 已查确认、去重、旧记录、写故障、HTTP以及term/404宽泛比较。 |
| `tests/phase1/test_p1_56.py` | `c30efcb10839ab7317e348a690133f8368d6ff273cef74005f753404cca7db0e` | 已查业务错误、原生auth/422、普通HTTPException控制；缺cause路径。 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 定向读isolated_runtime/route_client及provider接口；只读复用，未全文件重审。 |
| `.phase1-evidence/reviews/S04/probe_s04.py` | `7458d3c0797f57f82e9a057735bc7aaa0168138400190b2db5eb1ac9f958b72f` | 协调者新独立14方法，含合法对照；28处失败，只运行不修改。 |

本轮允许写：exam_detection.py、exam_points.py、subject_route.py、test_p1_07/08/56.py（完整路径见REWORK）。其他清单路径只读。两个原新生产文件及六份测试已存在，不再按首次包的“尚不存在”搜索实现。

## 2. 复用接口与结论

- R1只收紧检测模型与新批量入口；grading.verdict的strip/lower是C05明确允许，必须保留。旧manual/inferred读取不因新候选严格校验而被删除或迁移。
- R2当前`if key in seen: continue`丢掉后续explicit；去重结果只有一个record，但确认依据应聚合整批，最后再做返回视图。原有线程锁与单write已可用，无需重写事务框架。
- R3 `_stored_view`只对缺键setdefault，不校验存在的subject_id/level；缺键legacy读默认与显式null/错误值必须分开。当前失败是响应身份/Schema错误，没有证实读取别科物理文件。
- R4真实review-pack把LLMEmptyResponseError包装HTTPException并保留__cause__，仅在SubjectRoute识别这个明确cause即可修复；不用修改报告/复习实现。auth401/403/native422及无业务cause旧HTTPException保持。
- map_subject_exception按真实异常类型返回固定ERROR_SPECS值；to_http_payload返回detail字符串+error。通用ValueError/TypeError不是provider问题。原始cause/受控诊断留服务端，勿混入JSON。
- `store.subject_dir`严格当前用户注册身份；`json_transaction`+tx.read_list/write_list已提供锁/严格读取/原子提交，传参错误用json_store.invalid_input，存量坏元字段用json_store.corrupt_error。这些基础只读。
- 测试复用p1_runtime/p1_route_client/provider stubs及tmp-home回归启动器。独立probe通过合法base→单字段破坏定位缺陷；其源码与日志都保留，worker只运行并把行为用例移植到六路径内测试。

## 3. 当前原样关键片段

### _candidate

`deeptutor/subjects/exam_detection.py:174–187`

```python
    if "level" not in raw:
        raise ModelOutputError(REASON_LEVEL_MISSING)
    if not isinstance(raw["level"], str):
        raise ModelOutputError(REASON_LEVEL_NOT_A_STRING)
    level = raw["level"].strip().lower()
    if level not in DETECT_LEVELS:
        raise ModelOutputError(REASON_LEVEL_UNKNOWN)

    if normalize_whitespace(evidence) not in normalize_whitespace(transcript):
        # Not a direct quote: the whole round fails (C06) instead of dropping
        # this candidate and reporting the rest as a success.
        raise ModelOutputError(REASON_EVIDENCE_NOT_IN_TRANSCRIPT)

    return {"content": content, "level": level, "evidence": evidence, "kp": kp}
```

### _detected_candidate

`deeptutor/subjects/exam_points.py:247–284`

```python
def _detected_candidate(raw: object, *, term: str, source: str) -> dict:
    """Validate one detector candidate **strictly** (no level fallback).

    ``add_point``/``add_many`` keep the historical manual rule that an unknown
    level becomes ``inferred``. A detector candidate must not: C06 allows only
    ``explicit``/``emphasis``, and quietly re-labelling a broken level is how a
    wrong level reached the collection before.
    """
    if not isinstance(raw, dict):
        raise json_store.invalid_input("考点必须是对象")

    content = raw.get("content", "")
    if not isinstance(content, str):
        raise json_store.invalid_input("考点内容必须是字符串")
    content = content.strip()
    if not content:
        raise json_store.invalid_input("考点内容不能为空")

    level = raw.get("level")
    if not isinstance(level, str):
        raise json_store.invalid_input("level 必须是字符串")
    level = level.strip().lower()
    if level not in DETECTED_LEVELS:
        raise json_store.invalid_input("检测考点的 level 只能是 explicit 或 emphasis")

    evidence = raw.get("evidence", "")
    if not isinstance(evidence, str):
        raise json_store.invalid_input("evidence 必须是字符串")

    return {
        "content": content,
        "level": level,
        "evidence": evidence.strip(),
        "kp": _text(raw, "kp", ""),
        "term": term,
        "source": _text(raw, "source", source) or source,
        "anchor": _text(raw, "anchor", ""),
    }
```

### _stored_view

`deeptutor/subjects/exam_points.py:224–244`

```python
def _stored_view(record: dict, subject_id: str) -> dict:
    """A response-shaped copy of a stored point (never written back).

    Reused legacy records may predate some keys; the response still has to match
    the ExamStored schema, so the *missing* fields get their defaults here. A
    value that is present is never replaced.
    """
    view = dict(record)
    for key, default in (
        ("subject_id", subject_id),
        ("content", ""),
        ("level", "inferred"),
        ("evidence", ""),
        ("kp", ""),
        ("term", ""),
        ("source", "manual"),
        ("anchor", ""),
        ("confirmed", False),
    ):
        view.setdefault(key, default)
    return view
```

### _validate

`deeptutor/subjects/exam_points.py:65–93`

```python
def _validate(points: list[dict], source: Path) -> list[dict]:
    """Check the fields this module reads; keep every unknown field.

    ``id`` and ``content`` are required; the display/query text fields and
    ``confirmed`` are validated only when present (a missing optional field is
    a legacy record, an explicitly wrong type is corruption).
    """
    for index, point in enumerate(points):
        if not isinstance(point.get("id"), str) or not point["id"]:
            raise json_store.corrupt_error(source.name, "考点记录缺少合法 id", index=index)
        if not isinstance(point.get("content"), str):
            raise json_store.corrupt_error(source.name, "考点缺少 content", index=index)
        for key in _OPTIONAL_TEXT:
            value = point.get(key)
            if key in point and not isinstance(value, str):
                raise json_store.corrupt_error(
                    source.name, f"{key} 不是字符串", index=index
                )
        confirmed = point.get("confirmed")
        if "confirmed" in point and not isinstance(confirmed, bool):
            raise json_store.corrupt_error(source.name, "confirmed 不是布尔值", index=index)
        created = point.get("created_at")
        if "created_at" in point and (
            isinstance(created, bool) or not isinstance(created, (int, float))
        ):
            raise json_store.corrupt_error(
                source.name, "created_at 不是数值", index=index
            )
    return points
```

### R2重复分支（确认提升在continue之后）

`deeptutor/subjects/exam_points.py:380–393`

```python
            if key in seen:
                # Duplicate inside this same batch: the round reports the entry
                # once (``detected`` counts saved/reused candidates, not rows).
                continue
            existing = by_key.get(key)
            if existing is not None:
                seen[key] = existing
                if candidate["confirmed"] and not bool(existing.get("confirmed", False)):
                    # explicit / auto_confirm may promote; emphasis never revokes.
                    existing["confirmed"] = True
                    changed = True
                stored.append(_stored_view(existing, subject_id))
                continue

```

### R4当前错误边界

`deeptutor/api/subject_route.py:52–84`

```python
    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def subject_error_boundary(request: Request) -> Response:
            try:
                return await original(request)
            except (HTTPException, RequestValidationError):
                # 认证 / 原生参数校验 / 既有 HTTPException：保持框架行为。
                raise
            except Exception as exc:  # noqa: BLE001 - C02 统一安全出口
                error = map_subject_exception(exc)
                if error.code is ErrorCode.INTERNAL_ERROR:
                    # 未知内部异常：服务端记录原始 cause 与堆栈，对外只有固定消息。
                    logger.warning(
                        "subject route internal error: %s %s (%s)",
                        request.method,
                        request.url.path,
                        type(exc).__name__,
                        exc_info=exc,
                    )
                else:
                    logger.warning(
                        "subject route %s: %s %s (%s)",
                        error.code.value,
                        request.method,
                        request.url.path,
                        type(exc).__name__,
                    )
                return JSONResponse(
                    status_code=error.http_status, content=to_http_payload(error)
                )

        return subject_error_boundary
```

### 真实review-pack异常已有明确cause（此文件只读）

`deeptutor/api/routers/subjects.py:662–665`

```python
    try:
        markdown = await review_guide.generate_guide_markdown(subject_id, term=term)
    except LLMEmptyResponseError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
```

### test_a_level_inside_the_enum_is_accepted_with_normalisation

`tests/phase1/test_p1_07.py:259–269`

```python
def test_a_level_inside_the_enum_is_accepted_with_normalisation(p1_runtime: Path, level: str):
    candidate = {
        "content": "c",
        "level": level,
        "evidence": "这个内容很重要",
        "kp": "k",
    }

    points, _ = ed.parse_points(_points_json(candidate), TRANSCRIPT)

    assert points[0]["level"] == level.strip().lower()
```

### R5过宽term断言

`tests/phase1/test_p1_08.py:491–491`

```python
    assert all(p["term"] == subject.subject_id or p["term"] == "2026春" for p in body["stored"])
```

### R5过宽404断言

`tests/phase1/test_p1_08.py:690–690`

```python
    assert response.status_code in (400, 404)
```

### to_http_payload

`deeptutor/subjects/errors.py:393–395`

```python
def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}
```

## 4. 证据入口与保留限制

`reviews/S04/execution.log`实际重跑298定向、2560相关目录/18历史skip、Ruff和1833归档均成功；`probe_s04.py`14方法含子场景失败28。签收状态为changes_requested，失败不是环境阻塞，也不是新增需求。

保留允许的限制：Linux/WSL flock及临时锁文件、中间目录理论TOCTOU、无真实provider/browser验证、P1-39/P1-54与C07–C13后续阶段。不把明确业务cause泄漏、模型枚举放宽或坏复用元数据当延期限制。

每个R目标/允许符号/完成证据以及统一收尾命令已在REWORK_S04.txt，不另发逐R交接。完成本返修阶段后停，等待整体复核，不进入S05。

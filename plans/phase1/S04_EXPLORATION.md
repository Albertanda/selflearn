# S04 已探索文件清单 + 关键片段

探索日期：2026-10-13。项目根：`/home/albert/selflearn/selflearn`。配合 `START_S04.txt` 使用；仅供S04已授权目标。

前置是S03-final当前签收，27个已验收源码hash见 `.phase1-evidence/stages/S03/review.json` 指向的receipt。本包hash是协调者补修后的版本；不可恢复worker旧版本。行号一基；以下均从当前源码原样摘取，节选范围不表示整文件已穷尽审查。

先核hash，再复用下列定位和片段直接编码；未变的片段不用为orientation重读。实现确需上下文时只补读对应函数及直接依赖。变化时查最小diff，不覆盖文件恢复hash。

## 1. 文件清单与版本

| 已探索文件（相对项目根） | SHA256 | 探索范围/用途 |
|---|---|---|
| `AGENTS.md` | `fcfc6783e9699552efef19cb5427b26e8063260c455e1c1953f86eaa69621c79` | 已读架构/入口/依赖层；无额外写入或审批规则。历史上游功能描述不等于当前已接通功能。 |
| `plans/phase1/STAGE_WORKFLOW.md` | `34f378797cde73adbcebd856ad37a7c6bd3b408aba68903a22997d2ac88745b0` | 2.1阶段授权/串行单元/证据/探索包复用规则。 |
| `plans/phase1/EXECUTION_GUIDE.md` | `eb688596ef5409a2b1c6dcbc92d4f30304102bb0a176df21d0ea375b30acb03e` | 2.1执行边界及当前阶段选择规则。 |
| `plans/phase1/FRAMEWORK.md` | `9190d8ad2f513a1fef09020c98d6bd8816274834cf9a2d8c75abae6397cc77f1` | 第一阶段目标/边界/修复体系；第二阶段功能排除。 |
| `plans/phase1/stages/S04.md` | `1c9715d31717504d5d970c7ff90a4ea071f7b1bbd241559b144cb17ade8efe66` | 六单元顺序、12路径并集、C01–C06。 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | C01–C06/C14；本文提炼C05/C06摘要并给schema定位，正文仍为执行规范。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | $defs GradeModelOutput/GradeResponse/ExamCandidate/DetectionModelOutput/ExamStored/DetectionResponse/Warning/ErrorResponse/StageReport。 |
| `deeptutor/api/routers/subjects.py` | `3c703611b0e9de24cb7b40d2bdbbdc3700a1b105ca72b1804928810d7c0fbff7` | imports/router/_require_subject/PATCH/check/_ai_grade/detect及全路由异常出口定位；P06/P08/P15/P56可写。 |
| `deeptutor/subjects/exam_detection.py` | `25321eab532519034b6526323444cdaf4a87a0473598db609aabe7f5504e06d5` | 已读全文件：v3提示词、detect_points、宽松解析；P07可写。 |
| `deeptutor/subjects/wrong_book.py` | `4b4e628f482d53db0c6cdb937d5f1dadfa8d4db0721530ee19b1625f5d964ddb` | 已读校验/读视图/原始事务/attempt/精确匹配；P06仅新增组合提交及必要内部复用。 |
| `deeptutor/subjects/exam_points.py` | `024e623963234ac520ba030eca99ae7a9371e4864088b1bbcda4270b7cb44b7e` | 已读校验/构造/批量事务/确认/摘要；P08仅批量upsert及必要内部复用。 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 已读严格reader/路径/锁/事务；S03-final已补fork线程锁、非普通文件及IO出口，只读。 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | 已读注册/创建/身份/路径/update；S03-final严格null和名称/IO，仅只读复用。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | ErrorCode/ERROR_SPECS/异常继承/mapper/安全HTTP投影；S02已签收，只读。 |
| `deeptutor/subjects/generation.py` | `831c50decd82ee2977e2e3046346044d7ab7f08659cd25c79070d015f63969bc` | 已读全文件：先验截断再返回正文；complete_subject_text真实响应路径，只读。 |
| `deeptutor/subjects/model_output.py` | `7ebe1f77d497ed3dcf11914540f14e4d83d026160e3165d7311dc1a2c95e77f8` | 已读严格单对象及围栏/思考块/数值拒绝规则；parse_model_object，只读。 |
| `tests/phase1/helpers.py` | `0c2a250878a18044a742c32b4ff7d75c7c2a1ef2dd421a3b80185de951c8228b` | 探索隔离入口、SubjectPaths/make_subject、FakeLLMClient/install_provider_stubs及route_client，不代表其他辅助全读。只读。 |
| `tests/phase1/conftest.py` | `bc6a0cd965bcd848508874856b1c52fa00a0285c35b1507a284ed21834bca8f1` | 已读全文件：显式p1_runtime/subjects/providers/route_client等夹具，只读。 |
| `.phase1-evidence/stages/S01/rework01/run_regression_tmp_home.py` | `c40d69f6b3c4309da47bc2f026f8ed8c5413d0d1a75abcf8e05249d58ec17b59` | 已读全文件：pytest收集前tmp home/假默认配置/清凭证/结束清理，只读运行。 |
| `plans/phase1/cards/P1-05.md` | `c002dfedf7bc2c58fb7cd7882970e6e8573c115e9b21289e988bdbbb8cb3fd72` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |
| `plans/phase1/cards/P1-06.md` | `01c3c4230327ec879e75832e893cffb5e1f88920e7150f88551e027856033a5a` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |
| `plans/phase1/cards/P1-07.md` | `19bd54514eaccf42bf99120fe35b14d959c6e740ebc2d5c6c7ecd1b4facd9769` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |
| `plans/phase1/cards/P1-08.md` | `e6c714add002d0b280dfce0220a5aff9daba6ac46ef80bd30fb1014aa10d41e9` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |
| `plans/phase1/cards/P1-15.md` | `08bd2f9f59b8a89af8d4c5ab2cb9de2fc9f24534709e9927ba08b4cbf8cfcdee` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |
| `plans/phase1/cards/P1-56.md` | `864094300ddc4d0e2e05780f9a69af3df9ea94882bf187ae51a652b0cc7b0072` | 已读目标/范围/步骤/验收；阶段内编码单元，历史单卡停止规则被2.1替代。 |

计划内新建、当前不存在：`deeptutor/subjects/grading.py`、`deeptutor/api/subject_route.py`、六份 `tests/phase1/test_p1_05/06/07/08/15/56.py`（分别独立文件）。无需搜索其他位置的同名实现。

## 2. 已确认问题与只读依赖

- P05/P06：旧_ai_grade贪婪regex/宽catch，任何故障转wrong；check_answer分步查题/建题/attempt且新correct也入本。评级先在锁外完成，组合提交在锁内重查同题、只写一个原始集合。
- P07/P08：旧detect_points把异常做空结果，parser容错/强制转换/跳过坏项，route丢弃error并逐点写。v3第二例quote在原文中不存在。完整schema与原文引用验证后才过滤负向证据，再批量upsert。
- P15：`Form(None)`将显式空串也解析成None（独立HTTP实测见 `.phase1-evidence/reviews/S03-final/probe_patch_form.py`）。必须看实际表单字段是否出现，空PATCH不得调用update_subject。
- P56：subject router目前普通APIRouter，_require_subject不先验slug且404回显输入；list/profile等严格存储错误无统一投影。新APIRoute包住handler及依赖，只作用subject，不注册全局handler。
- json_store/store：`store.subject_dir(sid)`检查当前用户注册身份，`subject_data_path`先约束根/叶，unknown=404；`json_transaction(directory)`真实RLock+flock，可重入。`tx.read_list(path)`严格读，`tx.write_list(path, records)`原子写，OS失败StorageIOError。事务互斥不是多文件回滚数据库。
- wrong_book：`_validate(raw,path)`验证存量；`load`返回重算mastery/status的读视图；提交应读原始数组，避免给无关legacy记录回写派生字段。`_recompute`沿用既有舍入/classify；find_by_question按trim后精确相等，不能扩成相似度。
- exam_points：`_validate`旧inferred兼容、显式null拒绝；`_build_point`仍是manual兼容规则，不能拿它的未知level→inferred规则代替P07严格模型schema。`add_many`已一次写但只追加，不去重且confirmed全false。
- errors：`subject_error(ErrorCode.INVALID_MODEL_OUTPUT, cause=exc)`可构造安全具名异常；`map_subject_exception`识别真实类型，不靠消息猜；`to_http_payload`保留detail字符串。原生422/auth401/403及headers优先保留；旧HTTPException按START边界处理。
- generation：complete_subject_text返回str，内部使用factory.complete_response得到真实TutorResponse；非空length/空length/空stop依次抛SubjectOutputTruncated/LLMReasoningBudgetExhausted/LLMEmptyResponseError，不在新模块吞掉。预算保持原LLM_MAX_TOKENS。
- model_output：parse_model_object严格唯一JSON对象，允许现有合法围栏/思考块包装；空/多对象/截断/坏围栏/NaN/Inf失败。新模块只做业务schema，不重写parser。
- tests：p1_runtime显式隔离+网络guard；p1_route_client是实际subject router TestClient（默认跳过真实认证，认证用例定向恢复/覆盖依赖），不是fake backend；stub完整generation链要用真实TutorResponse。p1_subjects键是展示名，sid取返回SubjectPaths.subject_id。

## 3. 原样关键片段

### 当前router初始化（依赖保留）

`deeptutor/api/routers/subjects.py:29–36`

```python
from deeptutor.subjects import (
    exam_points,
    knowledge_points,
    store,
    wrong_book,
)

router = APIRouter()
```

### _require_subject

`deeptutor/api/routers/subjects.py:61–65`

```python
def _require_subject(subject_id: str) -> dict:
    subject = store.get_subject(subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"Subject '{subject_id}' not found")
    return subject
```

### patch_subject

`deeptutor/api/routers/subjects.py:91–99`

```python
async def patch_subject(
    subject_id: str,
    description: str = Form(None),
    term: str = Form(None),
    _: None = Depends(require_auth),
):
    _require_subject(subject_id)
    updated = store.update_subject(subject_id, description=description or "", term=term or "")
    return {"subject": updated}
```

### _ai_grade

`deeptutor/api/routers/subjects.py:410–444`

```python
async def _ai_grade(question: str, student_answer: str, reference_answer: str) -> tuple[str, str]:
    """Grade one answer via the main LLM (verdict: correct / partial / wrong)."""
    from deeptutor.services.llm.config import get_llm_config
    from deeptutor.subjects.generation import complete_subject_text

    cfg = get_llm_config()
    prompt = (
        "你是一名严谨且鼓励学习者的助教，正在批改一道题。\n\n"
        f"题目：{question}\n"
        + (f"参考答案：{reference_answer}\n" if reference_answer else "")
        + f"学生作答：{student_answer}\n\n"
        "请只输出 JSON：{\"verdict\": \"correct|partial|wrong\", \"feedback\": \"简短分条反馈（哪里对、哪里错、如何改正）\"}"
    )
    try:
        raw = await complete_subject_text(
            prompt=prompt,
            system_prompt="你是严格的批改助教。",
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
        import json as _json
        import re as _re

        text = raw.strip()
        m = _re.search(r"\{[\s\S]*\}", text)
        if m:
            data = _json.loads(m.group(0))
            verdict = str(data.get("verdict", "wrong")).lower()
            if verdict not in ("correct", "partial", "wrong"):
                verdict = "wrong"
            return verdict, str(data.get("feedback", ""))[:500]
        return "wrong", text[:300]
    except Exception as exc:  # noqa: BLE001
        return "wrong", f"批改服务不可用：{exc}"
```

### check_answer（关键提交段）

`deeptutor/api/routers/subjects.py:388–407`

```python
    verdict, feedback = await _ai_grade(question, student_answer, reference_answer)
    is_correct = verdict == "correct"

    entry = wrong_book.find_by_question(subject_id, question)
    if entry is None:
        entry = wrong_book.add_entry(
            subject_id,
            question=question,
            answer=reference_answer,
            kp=kp,
            source="check",
        )
    entry = wrong_book.record_attempt(subject_id, entry["id"], correct=is_correct)

    return {
        "verdict": verdict,
        "feedback": feedback,
        "correct": is_correct,
        "entry": entry,
    }
```

### detect_exam_points（关键提交段）

`deeptutor/api/routers/subjects.py:512–535`

```python
    result = await exam_detection.detect_points(transcript, term=term, source=source)
    candidates = result["points"]
    stored = []
    for p in candidates:
        confirmed = bool(auto_confirm) or p["level"] == "explicit"
        stored.append(
            exam_points.add_point(
                subject_id,
                content=p["content"],
                level=p["level"],
                evidence=p.get("evidence", ""),
                kp=p.get("kp", ""),
                term=term,
                source=source,
                anchor=p.get("anchor", ""),
                confirmed=confirmed,
            )
        )
    return {
        "version": result["version"],
        "detected": len(candidates),
        "stored": stored,
        "raw": result.get("raw", ""),
    }
```

### 当前提示词示例（第二例引用需改）

`deeptutor/subjects/exam_detection.py:40–48`

```python
## 示例
输入："这个内容很重要，大家一定要重视起来，几乎年年都要用到。"
输出：{"points": [{"content": "常微分方程组的解法（整体重要性）", "level": "emphasis", "evidence": "这个内容很重要，大家一定要重视起来，几乎年年都要用到", "kp": "常微分方程组"}]}

输入："去年期末考试最后一道大题就考的消元法，大家今年注意。"
输出：{"points": [{"content": "消元法解常微分方程组", "level": "emphasis", "evidence": "去年期末考试，最后一道大题就是考的消元法", "kp": "消元法"}]}

输入："这个不难，不用重点看，大家了解一下就行。"
输出：{"points": []}
```

### detect_points（关键提交段）

`deeptutor/subjects/exam_detection.py:75–85`

```python
    except Exception as exc:  # noqa: BLE001
        # Includes LLMReasoningBudgetExhausted: the caller gets a diagnosable
        # message instead of an empty point list that looks like "no signals".
        return {"version": prompt_version, "points": [], "raw": "", "error": str(exc)}

    points = _parse_points(raw)
    for p in points:
        p.setdefault("term", term)
        p.setdefault("source", source)
        p.setdefault("anchor", "")
    return {"version": prompt_version, "points": points, "raw": raw}
```

### _parse_points

`deeptutor/subjects/exam_detection.py:88–124`

```python
def _parse_points(raw: str) -> list[dict]:
    """Robustly pull ``{"points": [...]}`` out of an LLM response."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        # Trailing commas / prose tolerance.
        cleaned = re.sub(r",\s*([}\]])", r"\1", m.group(0))
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        return []
    out = []
    for p in points:
        if not isinstance(p, dict):
            continue
        content = str(p.get("content") or "").strip()
        if not content:
            continue
        level = str(p.get("level") or "emphasis").lower()
        if level not in ("explicit", "emphasis", "inferred"):
            level = "emphasis"
        out.append(
            {
                "content": content,
                "level": level,
                "evidence": str(p.get("evidence") or "").strip(),
                "kp": str(p.get("kp") or "").strip(),
            }
        )
    return out
```

### _recompute

`deeptutor/subjects/wrong_book.py:190–200`

```python
def _recompute(entry: dict) -> dict:
    """Refresh mastery score + status from the attempt history.

    ``correct`` is taken as-is: :func:`_validate`/``record_attempt`` already
    guarantee it is a real bool, so nothing here can coerce ``"false"``.
    """
    correctness = [attempt["correct"] for attempt in entry.get("attempts", [])]
    # One rounding step shared with ``classify`` — see MASTERY_PRECISION.
    entry["mastery"] = mastery_score(correctness)
    entry["status"] = classify(correctness)
    return entry
```

### record_attempt（关键提交段）

`deeptutor/subjects/wrong_book.py:259–274`

```python
    now = int(time.time())
    d = store.subject_dir(subject_id)
    with json_store.json_transaction(d) as tx:
        path = tx.path(WRONG_BOOK_NAME)
        entries = _validate(tx.read_list(path), path)
        for entry in entries:
            if entry["id"] != entry_id:
                continue
            entry.setdefault("attempts", []).append(
                {"ts": now, "correct": correct, "session_id": session_id or ""}
            )
            entry = _recompute(entry)
            entry["updated_at"] = now
            tx.write_list(path, entries)
            return _project(entry)
        return None
```

### add_many

`deeptutor/subjects/exam_points.py:180–204`

```python
def add_many(subject_id: str, points: list[dict]) -> list[dict]:
    """Add a batch (detector output) and return the stored points.

    The whole batch is validated and built **before** the file is opened, and
    all of it is committed in one locked write: a malformed item at position N
    leaves nothing from positions 0..N-1 behind.
    """
    if not isinstance(points, list):
        raise json_store.invalid_input("批次必须是数组")

    batch: list[dict] = []
    for raw in points:
        payload = dict(raw) if isinstance(raw, dict) else raw
        if isinstance(payload, dict):
            payload.setdefault("source", "lecture_detection")
        batch.append(_build_point(subject_id, payload, confirmed=False))

    d = store.subject_dir(subject_id)
    with json_store.json_transaction(d) as tx:
        path = tx.path(EXAM_POINTS_NAME)
        stored = _validate(tx.read_list(path), path)
        stored.extend(batch)
        tx.write_list(path, stored)

    return [point for point in batch if point["content"]]
```

### parse_model_object

`deeptutor/subjects/model_output.py:205–220`

```python
def parse_model_object(raw: str) -> dict[str, Any]:
    """返回 ``raw`` 中**唯一**的 JSON 对象。

    Raises:
        ModelOutputError: 顶层不是对象、JSON 截断/非法、存在两个及以上候选、
            围栏或 think 未闭合、以及围栏/对象之后还有非空内容。
    """
    if not isinstance(raw, str):
        raise ModelOutputError(REASON_NOT_A_STRING)
    text = _strip_think_blocks(raw)
    if not text:
        raise ModelOutputError(REASON_EMPTY)
    text = _strip_code_fence(text)
    if not text.strip():
        raise ModelOutputError(REASON_EMPTY)
    return _decode_single_object(text)
```

### complete_subject_text（关键提交段）

`deeptutor/subjects/generation.py:102–114`

```python
    from deeptutor.services.llm.factory import complete_response

    budget = max_tokens or LLM_MAX_TOKENS
    response = await complete_response(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=budget,
    )

    return validate_subject_response(response, max_tokens=budget)
```

### to_http_payload

`deeptutor/subjects/errors.py:393–395`

```python
def to_http_payload(error: SubjectOperationError) -> dict[str, Any]:
    """HTTP 投影：保留旧 ``detail: string``，增加结构化 ``error``。"""
    return {"detail": error.message, "error": to_error_dict(error)}
```

### 异步stub返回真实TutorResponse

`tests/phase1/helpers.py:750–752`

```python
    async def complete_response(self, prompt: str = "", **kwargs: Any):
        self._record(prompt=prompt, **kwargs)
        return _tutor_response(str(self.response), self.finish_reason, self.usage)
```

### route_client

`tests/phase1/helpers.py:1148–1155`

```python
def route_client() -> Iterator[Any]:
    """在当前隔离作用域内创建并**关闭**一个真实路由客户端。"""
    if _ACTIVE_ROOT.get() is None:
        raise IsolationError("route_client requires an active isolated_runtime scope")
    from fastapi.testclient import TestClient

    with TestClient(build_route_app()) as client:
        yield client
```

## 4. 契约定位与证据入口

C01/C02：严格存储/身份/固定安全错误；C03：PATCH未提供保留，空字符串清空；C04：唯一完整对象；C05：只允许三种评级，新correct不入本，partial=false；C06：直接引用、负向排除、批量去重、默认term。以DATA_CONTRACTS正文和schemas相关$defs为准，不修改契约。

GradeResponse要求verdict/feedback/correct/entry/saved；DetectionResponse要求version/detected/stored/raw/warnings；Warning只允许code/message/count/kb_ref/status（必需code/message）；ErrorResponse.detail必须字符串。成功detected=len(stored)，重复条目可复用，raw不能附provider诊断/思考。

S03已验收：355定向通过、2262相关目录通过/18历史skip、Ruff、旧探针和实际fork验证；完整签收及保护结果见最新receipt。历史skip不增加，本阶段不跑真实LLM/browser，不把mock当全产品验收。

S04测试命令、范围和完成门见START_S04.txt；新worker证据记录器仅向stages/S04追加，不能调用会写S03日志的旧runlog。

S03余留：中间目录check/open理论TOCTOU（叶O_NOFOLLOW）、仅Linux/WSL文件锁、真实坏存量不迁移；删除政策P1-54/aggregate无证据语义P1-39保留后续。当前阶段只修已派六卡，不恢复这些历史限制。

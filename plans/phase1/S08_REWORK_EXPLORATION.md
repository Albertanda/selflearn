# S08 返修：已探索的文件清单 + 关键片段

2026-10-17。基于worker S08已交付、协调者尚未修改任何生产/既有测试的当前源码。配套REWORK_S08.txt及S08 changes_requested receipt。不要重做全仓orientation，先核对94条源码基准和下面完整SHA，再按符号进入对应单元。

原165项定向及3556项相关回归/19历史skip通过，独立32场景仍为28失败/4通过。下面旧片段用于定位缺陷，不代表建议保留。probe正例、真实bwrap ODE stdout伪造及64MiB worker输出内存反例均已实际执行；pytest首次拼写错误与审计脚本的行分隔假设错误留在日志，不计作产品缺陷。

## 已固定的设计边界

- 原S08十路径白名单不扩大；其他依赖、原派发和旧证据只读。R1→R2→R3→R4→R5→R6→R7→R8串行阶段返修，不逐卡交接，不进入S09。
- current-user+已登记subject+服务端rid推出唯一staging/public/work/attempts身份；dataclass类型本身不是所有权证明，合法读允许重建对象，写还需合法running状态。
- 普通创建竞争/发布失败/异常收尾必须正确，本次不要求全局调度器或跨多文件崩溃事务；未知跨进程活跃性保守保持running，不能直接写abandoned。
- timeout覆盖创建后到读流/等待/reap的全过程；PGID在创建时固定，leader先退出仍清理组；worker内部抓日志也有界。控制协议与诊断预算分开限界，不能截断唯一JSON后误认协议失败。
- 唯一JSON对象仍需固定schema/mode/status/字段类型/交叉一致性验证；不靠int/bool/str隐式转换修复坏结构。
- attempt按代次CAS收尾，绑定执行成功和产物size/hash；P34验证真实字节时再比对，失败/替换/旧收尾不得冒充当前图。
- ODE trusted父worker留在隔离环境内，不能import模型。模型子进程只能提供采样数值；可信父worker自己算原表达式参考值与差异，拒绝模型自签ok/error/finite。仍只称五点数值一致，不称整篇数学证明。
- 报告API/Tool/全文review接线仍是S09，真实OS验收仍为S15/P50；本轮真实bwrap探针不替代最终门。

## 探索文件与完整SHA256

| 文件 | SHA256 | 用途 |
|---|---|---|
| `deeptutor/services/pdf/report_inputs.py` | `7c4b09d622d7cfc3b403abef02707b640dd0913d8bdd44962a0956ec6b6b7d91` | R1：固定chart名与可编码code；保持纯输入先于副作用。 |
| `deeptutor/services/pdf/report_store.py` | `518cd7ed239ff97e550851d00d4b9e4bb286e2755efccb848e26de11b4c904b7` | R2/R3：身份、metadata、原子创建和状态收尾。 |
| `deeptutor/services/pdf/chart_executor.py` | `19004e73dda27a2ab15bbc5c97bd255305d0b0aa8d30562bb682b17f1abdabbb` | R2/R4/R5/R6：真正执行边界、协议和attempt。 |
| `deeptutor/services/pdf/chart_worker.py` | `411cc0436fb9fc75f66e66916086ee8ceb81ec570c464e8e197740695ad2c811` | R4/R7：worker内部也要有界；可信父进程不能采信模型自签结论。 |
| `deeptutor/services/pdf/chart_validation.py` | `fd747baea4719fb5494f6950e805dbe6f1235bfa02527410bc0e9e11510f231b` | R6/R7：执行成功与artifact绑定，以及可信数值检查。 |
| `deeptutor/services/pdf/report.py` | `26c9395f7ec2c185d13abc2f3c526bde61a90b52bcff07e68121af1ffe9d379e` | P31已有接线保持；裸旧helper属于P35/S09，不提前扩编排。 |
| `tests/phase1/test_p1_31.py` | `28bfe3b1094d0980dd9602b4460cd4ba1922add4980539855db7bbd0c44e86b1` | 输入现有正例保留；补R1。 |
| `tests/phase1/test_p1_32.py` | `062b39babd7ae63f4ed89155d6aad99fe93641cfc926ec713e758d8a0496c18b` | 原P32正例/异常注入/并发断言保留；补R2/R3。 |
| `tests/phase1/test_p1_33.py` | `b35a76553e2dbcbe9549e568c319453535bedb461fc02527c93808630c51c2fa` | 共享backend只读；补真实worker边界而非仅外层捕获。 |
| `tests/phase1/test_p1_34.py` | `9c5749902a4e05b359fe06ce41602470358afec7aabc09e11d0f92741d6580fb` | 保留PNG解码/像素/路径、真executor正例；补失败attempt和ODE伪造。 |
| `deeptutor/subjects/json_store.py` | `719522ccfe3b3981579fe5111759348b482a64b78e794efa81dc8d7fb014e2ca` | 只读，复用strict/短事务锁，不改共享store。 |
| `deeptutor/subjects/store.py` | `be30bb435011ca2f8b4e952f2a70cb0a8d21f4f02033167e2e4870857cc30a23` | 只读，当前用户与已登记subject根是权威。 |
| `deeptutor/subjects/errors.py` | `fd99442eb26315e3308bc2de9ad1bc0ea8649cdc17301bb1270765b941809b88` | 只读，使用C02现有安全code/message/status，不发明裸异常。 |
| `deeptutor/services/sandbox/backends.py` | `78544bd063dae285ab52d13fcfb353194f67c6ae695bcbebea6231d0e906a326` | 只读，不把报告修复扩散到全局backend。 |
| `deeptutor/services/sandbox/spec.py` | `3fd1906248bd0ed4a38deeb770cf0da35414bd38ee3271a64c39ff01e303bacf` | 只读，ExecResult.ok不含exit code判定。 |
| `plans/phase1/DATA_CONTRACTS.md` | `05a0a376ca08b64020f61de9f5ef50171eee7d9142e9fb6abfcd7adff81e9862` | C11仍是权威，没有更改契约。 |
| `plans/phase1/schemas.json` | `1a1460811f89bc343d247dae7168886ec498145cc3f1c82591cef313d58e720d` | ReportFile/Metadata/Response与私有extra扩展边界，勿改schema。 |
| `plans/phase1/START_S08.txt` | `201b813a24b7ce64c423d9170421e815192a444e4318f0dc3c5bc55d165aa618` | 原开工要求已授权，同期窄返修细化。 |
| `.phase1-evidence/reviews/S08/probe_s08.py` | `b3afa065bee885a0e46ecbce4f386c78697973be6ea2792b8c412f1c4b027940` | 只读独立32场景：28失败/4通过，优先直接运行；不能编辑逃避验收。 |

## 关键片段

### deeptutor/services/pdf/report_inputs.py

R1：固定chart名与可编码code；保持纯输入先于副作用。

L254–L268

```python


def build_chart_code_prompt(
    description: object, *, out_path: object, ode_rhs: object = ""
) -> str:
    """构造单张图的代码提示词。

    ``ode_rhs`` 为空（``""``/空白）时使用 :data:`PLAIN_CHART_CODE_PROMPT`：没有默认
    方程、没有 ``f(x, y)``、没有"必须遵守 ODE"段。非空时**先**通过
    :func:`validate_ode_expression`，再插入校验后的原表达式。

    ``out_path`` 必须是服务端预分配的裸文件名（``chart_N.png``）：这里用
    :func:`deeptutor.subjects.json_store.safe_segment` 拒绝任何路径分隔符，避免把
    调用方给的路径拼进提示词。
    """
```

L274–L288

```python
            f"单张图的描述超过 {MAX_CHART_DESCRIPTION_CHARS} 字符上限"
        )
    name = json_store.safe_segment(out_path, what="图表文件名")
    expression = validate_ode_expression(ode_rhs)
    if not expression:
        return PLAIN_CHART_CODE_PROMPT.format(description=text, out_path=name)
    return ODE_CHART_CODE_PROMPT.format(
        ode_section=ODE_SECTION.format(ode_rhs=expression),
        description=text,
        out_path=name,
    )


# ---------------------------------------------------------------------------
# 模型响应
```

L303–L317

```python


def parse_chart_code_response(raw: object) -> str:
    """从模型响应里取出图表代码：``{"code": "<非空字符串>"}``。

    ``code`` 缺失、不是字符串（list/dict/数字/bool/None）、或只有空白，都是
    ``invalid_model_output``——本函数返回的一定是可以写进脚本文件的源码文本。
    """
    payload = parse_chart_object(raw)
    if "code" not in payload:
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
    code = payload["code"]
    if not isinstance(code, str) or not code.strip():
        raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
    return code
```

### deeptutor/services/pdf/report_store.py

R2/R3：身份、metadata、原子创建和状态收尾。

L470–L484

```python


def _require_run(run: object) -> ReportRun:
    """只接受本模块构造出的 :class:`ReportRun`（不接受 Path/自定义 id）。"""
    if not isinstance(run, ReportRun):
        raise json_store.invalid_input("run 必须是服务端创建的 ReportRun")
    _require_report_id(run.report_id)
    return run


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def create_report_run(subject_id: str, *, reviewed_from: str | None = None) -> ReportRun:
    """创建一个新的报告运行：服务端 id + 私有目录 + ``running`` metadata。
```

L360–L374

```python
# metadata 读
# ---------------------------------------------------------------------------
def _manifest_from_payload(
    payload: object, *, staging: Path | None, public: Path | None, metadata_path: Path | None
) -> ReportManifest:
    """把一份 metadata 收成 :class:`ReportManifest`；字段不合契约即 storage_corrupt。"""
    if not isinstance(payload, Mapping):
        raise json_store.corrupt_error(METADATA_NAME, "顶层不是对象")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise json_store.corrupt_error(METADATA_NAME, "schema_version 不受支持")
    report_id = payload.get("report_id")
    if not isinstance(report_id, str) or not _REPORT_ID_RE.match(report_id):
        raise json_store.corrupt_error(METADATA_NAME, "report_id 非法")
    subject_id = payload.get("subject_id")
    if not isinstance(subject_id, str) or not store.is_valid_subject_id(subject_id):
```

L375–L389

```python
        raise json_store.corrupt_error(METADATA_NAME, "subject_id 非法")
    status = payload.get("status")
    if status not in STATUSES:
        raise json_store.corrupt_error(METADATA_NAME, "status 非法")
    created_at = payload.get("created_at")
    if isinstance(created_at, bool) or not isinstance(created_at, int) or created_at < 0:
        raise json_store.corrupt_error(METADATA_NAME, "created_at 非法")
    reviewed_from = payload.get("reviewed_from")
    if reviewed_from is not None and not isinstance(reviewed_from, str):
        raise json_store.corrupt_error(METADATA_NAME, "reviewed_from 非法")
    verification_status = payload.get("verification_status")
    if verification_status not in VERIFICATION_STATUSES:
        raise json_store.corrupt_error(METADATA_NAME, "verification_status 非法")
    if status == STATUS_COMPLETED and verification_status == VERIFICATION_FAILED:
        raise json_store.corrupt_error(METADATA_NAME, "completed 不得是失败验证")
```

L481–L495

```python
# create
# ---------------------------------------------------------------------------
def create_report_run(subject_id: str, *, reviewed_from: str | None = None) -> ReportRun:
    """创建一个新的报告运行：服务端 id + 私有目录 + ``running`` metadata。

    * ``report_id`` 是 :func:`uuid.uuid4().hex`（32 位），调用方不能指定；
    * 私有 staging ``<subject>/_report_runs/<rid>`` 与正式目录
      ``.../reports/<rid>`` 都由当前用户 PathService 推出；
    * 同 id 已存在（staging 或正式目录）→ 拒绝，绝不覆盖；
    * 只建私有目录，不产生任何正式 URL。
    """
    subject = _require_registered_subject(subject_id)
    reviewed = _require_reviewed_from(reviewed_from)
    runs_root = subject / REPORT_RUNS_DIRNAME
    json_store.make_directory(runs_root)
```

L540–L554

```python
        )
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    _register_active(run)
    return run


# ---------------------------------------------------------------------------
# 状态迁移
# ---------------------------------------------------------------------------
def _write_private_metadata(run: ReportRun, manifest: ReportManifest) -> None:
    payload: dict[str, Any] = dict(manifest.as_contract())
    # 私有扩展：服务端内部路径与 owner_pid 只留在这里，绝不进公开投影。
    payload["owner_pid"] = manifest.owner_pid
```

L559–L573

```python


def fail_report_run(run: ReportRun, *, detail: str = "") -> ReportManifest:
    """把本次运行标成 ``failed``（无 URL、无文件）并释放活跃登记。

    已经 ``completed`` 的运行不会被降级覆盖——失败不能抹掉已发布的旧结果。
    """
    run = _require_run(run)
    manifest = read_run_manifest(run)
    if manifest.status == STATUS_COMPLETED:
        release_report_run(run)
        return manifest
    failed = replace(
        manifest,
        status=STATUS_FAILED,
```

L588–L602

```python


def mark_abandoned_if_stale(run: ReportRun) -> ReportManifest | None:
    """把"本进程已不再持有、记录仍是 running"的运行标成 ``abandoned``。

    返回新 manifest；运行仍然活跃或已经不是 running 时返回 ``None``（不改写）。
    判定依据只有本进程登记表：``owner_pid`` 那个整数仍然存在**不算**活跃证明。
    """
    run = _require_run(run)
    manifest = read_run_manifest(run)
    if manifest.status != STATUS_RUNNING or report_run_is_active(manifest):
        return None
    abandoned = replace(manifest, status=STATUS_ABANDONED, files=())
    _write_private_metadata(run, abandoned)
    return abandoned
```

L606–L620

```python
# publish
# ---------------------------------------------------------------------------
def publish_report_run(
    run: ReportRun, *, files: Sequence[ReportFile | Mapping[str, Any]], verification_status: str
) -> ReportManifest:
    """校验并**显式发布**一次运行；只有成功返回的 manifest 才代表正式产物。

    步骤：形状校验 → 逐项按源字节校验（常规文件/非链接/大小/摘要）→ 在正式
    目录同级建临时目录、逐项复制并复核摘要 → 写入公开 metadata 投影 → 原子
    ``rename`` 提交。任何一步失败都回滚本次临时目录，不留半完成目录、不覆盖旧
    completed、不产生 URL。

    本函数**不替代** P35 对全文/编译完成的质量检查：``files`` 必须来自服务端
    已验证清单（例如 P34 的 ``validate_chart_output`` 返回值），不接受模型自签。
    """
```

L623–L637

```python
    if status == VERIFICATION_FAILED:
        raise subject_error(ErrorCode.CHART_FAILED)
    declared = _require_file_set(files)

    current = read_run_manifest(run)
    if current.status != STATUS_RUNNING:
        # 已发布/已失败/已放弃的运行不接受第二次发布。
        raise json_store.invalid_input("只有 running 的运行可以发布")
    if run.public_dir.exists() or run.public_dir.is_symlink():
        raise json_store.invalid_input("该 report_id 已存在正式产物，拒绝覆盖")

    reports_dir = _public_reports_dir(store.subject_dir(run.subject_id))
    json_store.make_directory(reports_dir)
    staging_public = reports_dir / f".publishing-{run.report_id}-{os.getpid()}"

```

L667–L681

```python
            )
            json_store.atomic_write_object(
                staging_public / METADATA_NAME, completed.as_contract()
            )
            # 私有 metadata 先落到 completed：正式目录一旦出现，权威记录必须已经是完成态。
            _write_private_metadata(run, completed)
            try:
                os.replace(staging_public, run.public_dir)
            except OSError as exc:
                _write_private_metadata(run, replace(completed, status=STATUS_FAILED, files=()))
                raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        except BaseException:
            shutil.rmtree(staging_public, ignore_errors=True)
            raise
        finally:
```

L672–L686

```python
            _write_private_metadata(run, completed)
            try:
                os.replace(staging_public, run.public_dir)
            except OSError as exc:
                _write_private_metadata(run, replace(completed, status=STATUS_FAILED, files=()))
                raise subject_error(ErrorCode.STORAGE_IO, cause=exc) from exc
        except BaseException:
            shutil.rmtree(staging_public, ignore_errors=True)
            raise
        finally:
            release_report_run(run)
    return completed


def report_url(manifest: ReportManifest) -> str | None:
```

L448–L462

```python


def read_published_manifest(subject_id: str, report_id: str) -> ReportManifest | None:
    """读一份**已发布**的 metadata；不存在或未完成返回 ``None``（只读，不建目录）。"""
    subject = _require_registered_subject(subject_id)
    rid = _require_report_id(report_id)
    reports_dir = _public_reports_dir(subject)
    if not reports_dir.is_dir():
        return None
    public_dir = reports_dir / rid
    metadata = public_dir / METADATA_NAME
    if public_dir.is_symlink() or not metadata.is_file():
        return None
    payload = json_store.read_object(metadata, default={})
    manifest = _manifest_from_payload(
```

### deeptutor/services/pdf/chart_executor.py

R2/R4/R5/R6：真正执行边界、协议和attempt。

L603–L617

```python


def _kill_group(process: asyncio.subprocess.Process) -> None:
    """终止整个执行进程组；进程组没了才退回单进程 kill。"""
    killed = False
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        killed = True
    if not killed:
        with contextlib.suppress(ProcessLookupError, OSError):
            process.kill()


async def _reap(process: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
```

L637–L651

```python


async def run_bounded_spawn(
    spawn: SpawnCommand,
    limits: ReportResourceLimits,
    *,
    backend_name: str = "",
    env: Mapping[str, str] | None = None,
) -> ChartExecutionResult:
    """启动 *spawn* 并在有界内存内读取输出；超时/取消终止整组。

    这是本模块唯一的进程启动点：``start_new_session=True`` 让子进程成为新进程组
    组长，超时或取消时 ``killpg`` 整组终止再 reap。
    """
    started = time.monotonic()
```

L679–L693

```python
    timed_out = False
    try:
        await asyncio.wait_for(readers, timeout=limits.wall_clock_s)
        await process.wait()
    except asyncio.TimeoutError:
        timed_out = True
        _kill_group(process)
        await _reap(process)
    except asyncio.CancelledError:
        _kill_group(process)
        await _reap(process)
        raise

    stdout, stderr, trimmed = _trim_outputs(
        budget.text("stdout"), budget.text("stderr"), limits.max_output_chars
```

L927–L941

```python


def _parse_worker_payload(result: ChartExecutionResult) -> tuple[ChartExecutionResult, dict | None]:
    """严格解析 worker 的**唯一** stdout 对象；任何多余内容都 fail-closed。"""
    if result.error or result.timed_out:
        return result, None
    if result.exit_code != 0:
        return replace(result, error="worker_failed"), None
    raw = result.stdout.strip()
    try:
        payload = json.loads(raw, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
    except (json.JSONDecodeError, ValueError):
        return replace(result, error="worker_failed"), None
    if not isinstance(payload, dict) or payload.get("status") == "worker_error":
        return replace(result, error="worker_failed"), None
```

L974–L988

```python
    result = replace(
        parsed,
        exit_code=int(payload.get("exit_code", parsed.exit_code)),
        timed_out=bool(payload.get("timed_out", False)),
        error="",
        stdout=stdout,
        stderr=stderr,
        artifact=artifact if isinstance(artifact, Mapping) else None,
        checks=checks if isinstance(checks, Mapping) else None,
        output_truncated=parsed.output_truncated or trimmed,
        worker_payload=payload,
        mode="ode" if ode else "chart",
        status=str(payload.get("status") or ""),
    )
    if payload.get("status") == "worker_error":
```

L745–L759

```python


def begin_chart_attempt(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartAttempt:
    """开始"本次 attempt"：清除该名字的旧产物并写入可核查的记录。

    旧产物**先删**再执行，因此执行后还在那个路径上的文件只可能来自本次 attempt；
    记录写在 staging（不在模型可写挂载里），模型无法伪造。
    """
    if not isinstance(run, report_store.ReportRun):
        raise json_store.invalid_input("run 必须是服务端创建的 ReportRun")
```

L800–L814

```python


def finish_chart_attempt(
    attempt: ChartAttempt, result: ChartExecutionResult | None
) -> dict[str, Any]:
    """记录 attempt 结束（异常也会走到这里，结果记为失败）。"""
    record = read_chart_attempt(attempt.run, attempt.basename) or {}
    record.update(
        {
            "schema": 1,
            "run_id": attempt.run.report_id,
            "staging_dir": str(attempt.run.staging_dir),
            "basename": attempt.basename,
            "attempt_id": attempt.attempt_id,
            "started_at": attempt.started_at,
```

L825–L839

```python


def read_chart_attempt(run: report_store.ReportRun, expected_png: object) -> dict[str, Any] | None:
    """读本次 attempt 记录；不存在返回 ``None``，损坏则明确 ``storage_corrupt``。"""
    name = expected_png if isinstance(expected_png, str) else ""
    if not CHART_NAME_RE.match(name):
        return None
    path = attempt_record_path(run, name)
    if not path.is_file():
        return None
    payload = json_store.read_object(path, default={})
    if not payload:
        return None
    if payload.get("basename") != name or payload.get("staging_dir") != str(run.staging_dir):
        return None
```

L1010–L1024

```python


async def execute_chart_code(
    code: str,
    *,
    run: report_store.ReportRun,
    expected_png: str,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> ChartExecutionResult:
    """在报告沙箱里运行模型图表代码，并返回结构化结果。

    * ``code`` 必须先通过 P31 输入契约（非空字符串）；本函数把它写成工作目录里的
      ``_chart.py``（服务端固定名字）。
    * 执行前清除 ``expected_png`` 的旧产物并写下 attempt 记录，因此执行结束后该路径
      上的文件只可能来自本次 attempt。
```

L1089–L1103

```python


def chart_failure_error(result: ChartExecutionResult) -> SubjectOperationError | None:
    """把执行结果映射成 C02 固定错误；成功返回 ``None``。

    非 0 退出码**总是**失败——即使某个 ``ExecResult.ok`` 说成功。此外：脚本以 0 退出
    却没有产物、ODE 检查没有给出 ``ok: true`` 的结构化结果，都是 ``chart_failed``。
    """
    if result.error:
        if result.error in {"sandbox_spawn_failed", "sandbox_unavailable"}:
            return subject_error(ErrorCode.SANDBOX_UNAVAILABLE)
        if result.error == "sandbox_policy_unsupported":
            return subject_error(ErrorCode.SANDBOX_POLICY_UNSUPPORTED)
        return subject_error(ErrorCode.CHART_FAILED)
    if result.timed_out or result.exit_code != 0:
```

L513–L527

```python


def _assert_mounts_are_narrow(run: report_store.ReportRun, mounts: Sequence[ReportMount]) -> None:
    """不变量：只有一个可写挂载，且只读挂载不覆盖敏感根。"""
    writable = [mount for mount in mounts if not mount.read_only]
    expected = str(run.workdir)
    if len(writable) != 1 or writable[0].host_path != expected:
        raise subject_error(ErrorCode.INTERNAL_ERROR)

    forbidden: list[Path] = []
    for candidate in (
        Path("/"),
        Path.home(),
        _repo_root(),
        _repo_root() / "data",
```

### deeptutor/services/pdf/chart_worker.py

R4/R7：worker内部也要有界；可信父进程不能采信模型自签结论。

L159–L173

```python
# 运行模型脚本
# ---------------------------------------------------------------------------
def _run_script(script: str, workdir: str, *, timeout_s: int) -> dict:
    argv = [sys.executable, "-I", "-B", os.path.join(workdir, script)]
    try:
        completed = subprocess.run(
            argv,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
```

L165–L179

```python
            argv,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": 124,
            "timed_out": True,
            "stdout_tail": _tail(_decode(getattr(exc, "stdout", None))),
            "stderr_tail": _tail(_decode(getattr(exc, "stderr", None))),
        }
    except OSError as exc:
```

L233–L247

```python
# ode 模式：worker 再起一个自己，避免模型脚本自毁带走结果
# ---------------------------------------------------------------------------
def _ode_mode(spec: dict, workdir: str) -> int:
    script = _safe_basename(spec.get("script"), "script")
    expression = spec.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise WorkerError("expression 不能为空")
    points = spec.get("points")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_ODE_POINTS:
        raise WorkerError("points 必须是 1..%d 个点" % MAX_ODE_POINTS)
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in point)
```

L295–L309

```python
        checks = None
    else:
        checks = parsed if isinstance(parsed.get("ok"), bool) else None
    status = "ok" if checks is not None and checks["ok"] else "ode_failed"
    _emit(
        {
            "schema": 1,
            "mode": "ode",
            "status": status,
            "exit_code": int(completed.returncode),
            "timed_out": False,
            "checks": checks,
            "stdout_tail": _tail(stdout),
            "stderr_tail": _tail(stderr),
        }
```

L322–L336

```python


def _ode_eval_mode(spec: dict, workdir: str) -> int:
    """在同一个隔离环境里读模型脚本的 ``f``，并对给定点做数值比较。"""
    script = _safe_basename(spec.get("script"), "script")
    expression = spec.get("expression")
    points = spec.get("points")
    if not isinstance(expression, str):
        raise WorkerError("expression 必须是字符串")
    if not isinstance(points, list):
        raise WorkerError("points 必须是列表")
    _set_hard_limits(spec)

    def _failed(reason: str, **extra: object) -> int:
        _emit({"ok": False, "reason": reason, "finite": False, "max_abs_error": None, **extra})
```

L355–L369

```python
        module = importlib.util.module_from_spec(loader)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            loader.loader.exec_module(module)
            func = getattr(module, "f", None)
            if not callable(func):
                result = {"ok": False, "reason": "missing_f", "finite": False, "max_abs_error": None}
            else:
                code = compile(expression, "<ode_expression>", "eval")
                errors: list[float] = []
                result = {"ok": True, "reason": "", "finite": True, "max_abs_error": 0.0}
                for x_value, y_value in points:
                    got = func(x_value, y_value)
                    expected = eval(  # noqa: S307 - 已通过 AST 白名单，且在隔离环境内
                        code, {"__builtins__": {}}, {**_SAFE_NAMES, "x": x_value, "y": y_value}
                    )
```

L112–L126

```python
# 资源上限（必须在运行模型脚本之前设置）
# ---------------------------------------------------------------------------
def _set_hard_limits(spec: dict) -> dict:
    cpu_seconds = _require_int(spec, "cpu_seconds", minimum=1, maximum=600)
    memory_mb = _require_int(spec, "memory_mb", minimum=64, maximum=65536)
    max_file_bytes = _require_int(spec, "max_file_bytes", minimum=1024, maximum=1 << 32)
    address_space = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError) as exc:  # pragma: no cover - 依赖宿主已有 hard limit
        raise WorkerError(f"无法设置资源上限：{type(exc).__name__}") from exc
    return {
```

### deeptutor/services/pdf/chart_validation.py

R6/R7：执行成功与artifact绑定，以及可信数值检查。

L86–L100

```python


def _attempt_is_current(record: Mapping[str, Any] | None, run: report_store.ReportRun, name: str) -> bool:
    """attempt 记录必须属于本 run、本次 basename，并且已经"清空 + 结束"。"""
    if not isinstance(record, Mapping):
        return False
    return bool(
        record.get("cleared") is True
        and record.get("finished") is True
        and record.get("basename") == name
        and record.get("run_id") == run.report_id
        and record.get("staging_dir") == str(run.staging_dir)
        and isinstance(record.get("attempt_id"), str)
        and record.get("attempt_id")
    )
```

L133–L147

```python


def validate_chart_output(
    run: report_store.ReportRun,
    expected_png: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """验证本次 attempt 的 ``expected_png``，返回 ``ReportFile`` 形状的字典。

    成功：``{"path": "chart_N.png", "size": int, "sha256": str, "role": "chart"}``。
    失败：抛 C02 固定错误（``chart_failed``；名字非法是 ``invalid_input``）。
    """
    if not isinstance(run, report_store.ReportRun):
        raise json_store.invalid_input("run 必须是服务端创建的 ReportRun")
```

L176–L190

```python
        raise _chart_failed()

    _decode_png_strict(target, max_pixels=max_pixels)

    size, digest = _sha256_file(target, limit=max_bytes)
    if size != info.st_size or size <= 0:
        raise _chart_failed()
    return {
        "path": name,
        "size": size,
        "sha256": digest,
        "role": report_store.ROLE_CHART,
    }


```

L189–L203

```python


async def check_ode_numeric(
    run: report_store.ReportRun,
    ode_rhs: object,
    *,
    policy: ReportExecutionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """在隔离环境里用固定 5 点检查 ``f`` 与声明表达式的数值一致性。

    返回 ``{"status": "passed", "max_abs_error": float, "points": int}``；缺 ``f``、
    数值不符、NaN/Inf、坏输出、超时都抛 ``chart_failed``。表达式本身先过 P31 的
    AST 白名单（非法表达式是 ``invalid_input``，不会进入执行器）。

    结论范围仅限"给定 5 点的数值检查通过"，不是解析解证明。
```

L223–L237

```python
        raise _chart_failed()
    error_value = float(error_value)
    if not math.isfinite(error_value) or error_value >= ODE_MAX_ABS_ERROR:
        raise _chart_failed()
    points = checks.get("points")
    if not isinstance(points, int) or isinstance(points, bool) or points != len(ODE_CHECK_POINTS):
        raise _chart_failed()
    return {"status": report_store.VERIFICATION_PASSED, "max_abs_error": error_value, "points": points}


def verification_status(ode_rhs: object, *, passed: bool) -> str:
    """报告级 ``verification_status``：没有 ODE 就是 ``not_requested``。"""
    expression = validate_ode_expression(ode_rhs)
    if not expression:
        return report_store.VERIFICATION_NOT_REQUESTED
```

### deeptutor/services/pdf/report.py

P31已有接线保持；裸旧helper属于P35/S09，不提前扩编排。

L234–L248

```python
    equation at all.
    """
    ode_expression = _validate_ode_expression(ode_rhs)
    context_block = SUBJECT_CONTEXT_TEMPLATE.format(hint=subject_context) if subject_context else ""
    markdown = (
        await _llm(
            REPORT_PROMPT.format(
                title=title, requirements=requirements, subject_context=context_block
            ),
            "你是课程报告撰写助手。",
        )
    ).strip()
    if not markdown:
        raise LLMEmptyResponseError(
            "报告正文生成失败：模型返回空内容。"
```

L252–L266

```python

    # P1-31: one shared placeholder matcher; >8 charts is an explicit invalid_input.
    placeholders = validated_chart_placeholders(markdown)
    chart_paths: list[Path] = []
    for i, placeholder in enumerate(placeholders):
        spec = placeholder.spec
        png = out_dir / f"chart_{i + 1}.png"
        chart_ok = False
        last_rejection = ""
        for attempt in range(3):  # up to 2 retries on failed ODE self-check
            raw = await _llm(
                build_chart_code_prompt(spec, out_path=png.name, ode_rhs=ode_expression),
                "你生成 matplotlib 代码，只输出 JSON。",
            )
            try:
```

L261–L275

```python
        for attempt in range(3):  # up to 2 retries on failed ODE self-check
            raw = await _llm(
                build_chart_code_prompt(spec, out_path=png.name, ode_rhs=ode_expression),
                "你生成 matplotlib 代码，只输出 JSON。",
            )
            try:
                code = parse_chart_code_response(raw)
            except SubjectOperationError as exc:
                # A malformed response is retried like any other failed attempt,
                # but it is never turned into "no code" silently: only the fixed
                # C02 code is logged, never the rejected response text.
                last_rejection = exc.code.value
                logger.warning(
                    "chart %d code response rejected (attempt %d): %s",
                    i + 1,
```

L278–L292

```python
                )
                continue
            if _run_chart_code(code, out_dir) and png.exists():
                if not ode_expression or _chart_ode_matches(out_dir, ode_expression):
                    chart_ok = True
                    break
                logger.warning("chart %d ODE mismatch (attempt %d)", i + 1, attempt + 1)
        ok = chart_ok
        if ok:
            chart_paths.append(png)
        else:
            err = (out_dir / "_chart_err.txt").read_text(encoding="utf-8")[:200] \
                if (out_dir / "_chart_err.txt").exists() else (
                    f"rejected model response: {last_rejection}" if last_rejection
                    else "no chart code"
```

### tests/phase1/test_p1_31.py

输入现有正例保留；补R1。

L36–L50

```python


def test_plain_chart_prompt_carries_no_default_equation() -> None:
    prompt = ri.build_chart_code_prompt("画出各分数段人数柱状图", out_path="chart_1.png")

    assert "画出各分数段人数柱状图" in prompt
    assert "plt.savefig('chart_1.png'" in prompt
    assert '{"code"' in prompt
    for marker in ODE_MARKERS:
        assert marker not in prompt, f"普通图提示词仍出现 ODE 痕迹：{marker}"


def test_legacy_prompt_name_is_the_plain_template() -> None:
    """旧名字保留，但内容必须是"不含默认方程"的模板。"""
    assert report_mod.CHART_CODE_PROMPT == ri.PLAIN_CHART_CODE_PROMPT
```

L356–L370

```python


def test_invalid_expression_is_rejected_before_any_provider_or_executor_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    recorder.install(monkeypatch, [])

    with pytest.raises(json_store.InvalidInputError):
        _run_report(tmp_path, ode_rhs="__import__('os')")

    assert recorder.prompts == []
    assert recorder.executed == []
    assert recorder.ode_checks == []
    assert recorder.renders == 0
```

### tests/phase1/test_p1_32.py

原P32正例/异常注入/并发断言保留；补R2/R3。

L96–L110

```python


def _materialize(run: rs.ReportRun, *, charts: tuple[str, ...] = ("chart_1.png",)) -> list[dict]:
    """在私有 workdir 里写出正文/PDF/图，并返回服务端清单。"""
    markdown = run.workdir / "report.md"
    markdown.write_text("# 报告\n正文\n", encoding="utf-8")
    pdf = run.workdir / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake but declared\n")
    entries = [_entry(markdown, rs.ROLE_MARKDOWN), _entry(pdf, rs.ROLE_PDF)]
    for index, name in enumerate(charts, start=1):
        chart = run.workdir / name
        chart.write_bytes(_png_bytes((index, index, index)))
        entries.append(_entry(chart, rs.ROLE_CHART))
    return entries

```

L141–L155

```python


def test_uuid_collision_is_rejected_without_overwriting(p1_subject, monkeypatch) -> None:
    import uuid as uuid_module

    fixed = uuid_module.UUID("0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(rs.uuid, "uuid4", lambda: fixed)

    first = rs.create_report_run(p1_subject.subject_id)
    sentinel = first.workdir / "keep.txt"
    sentinel.write_text("不要被覆盖\n", encoding="utf-8")
    before = helpers.tree_digest(first.staging_dir)

    with pytest.raises(SubjectOperationError) as info:
        rs.create_report_run(p1_subject.subject_id)
```

L386–L400

```python
# 发布失败注入：没有半完成目录、没有 URL、旧报告不变
# ---------------------------------------------------------------------------
def test_injected_publish_failure_keeps_old_report_and_leaves_no_partial_dir(
    p1_subject, monkeypatch
) -> None:
    old_run = rs.create_report_run(p1_subject.subject_id)
    old_manifest = _publish_ok(old_run)
    old_before = helpers.tree_digest(old_run.public_dir)

    new_run = rs.create_report_run(p1_subject.subject_id)
    declared = _materialize(new_run)

    real_replace = os.replace

    def failing_replace(source, destination, *args, **kwargs):  # type: ignore[no-untyped-def]
```

### tests/phase1/test_p1_33.py

共享backend只读；补真实worker边界而非仅外层捕获。

L434–L448

```python


def test_timeout_kills_the_whole_process_group(p1_run: rs.ReportRun, tmp_path: Path) -> None:
    canary = p1_run.workdir / "grandchild-survived.txt"
    program = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', \"import time;time.sleep(3);"
        f"open({str(canary)!r},'w').write('x')\"])\n"
        "time.sleep(30)\n"
    )
    limits = ce.ReportResourceLimits(
        wall_clock_s=1, cpu_seconds=30, memory_mb=512, max_output_chars=1000,
        max_artifact_bytes=1 << 20,
    )
    spawn = ce.SpawnCommand(
```

L488–L502

```python


def test_output_flood_stays_bounded_while_reading(p1_run: rs.ReportRun) -> None:
    program = (
        "import sys\n"
        "chunk = 'x' * 4096\n"
        "for _ in range(256):\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stderr.write(chunk)\n"
        "sys.stdout.flush(); sys.stderr.flush()\n"
    )
    limits = ce.ReportResourceLimits(
        wall_clock_s=30, cpu_seconds=30, memory_mb=512, max_output_chars=1000,
        max_artifact_bytes=1 << 20,
    )
```

L550–L564

```python


def test_real_sandbox_boundary_probe(p1_run: rs.ReportRun) -> None:
    """真实 bwrap：在沙箱内探测挂载/环境/网络（受控边界，不是 OS 验收）。"""
    worker = Path(ce.__file__).resolve().with_name(ce.WORKER_FILENAME)
    repo_file = Path(ce.__file__).resolve()
    worker_before = _sha256(worker)
    probe = f"""
import json, os, socket, sys
findings = {{}}
findings["cwd"] = os.getcwd()
findings["env_keys"] = sorted(os.environ)
findings["fake_secret"] = {FAKE_SECRET!r} in json.dumps(dict(os.environ))
try:
    with open({str(worker)!r}, "a") as handle:
```

L743–L757

```python


def test_run_result_and_policy_contract_for_p34_and_p35(p1_run: rs.ReportRun) -> None:
    policy = ce.ReportExecutionPolicy()
    assert policy.for_ode().limits(ode=True).wall_clock_s == 30
    assert policy.limits().wall_clock_s == 60
    assert policy.max_pixels == 20_000_000
    assert policy.max_charts == 8
    for bad in ({"wall_clock_s": 0}, {"wall_clock_s": 10_000}, {"memory_mb": 0}, {"max_charts": 9}):
        with pytest.raises(ValueError):
            ce.ReportExecutionPolicy(**bad)

    result = ce.ChartExecutionResult(exit_code=0, timed_out=False, error="")
    assert result.ok is True
    assert ce.chart_failure_error(result) is None
```

### tests/phase1/test_p1_34.py

保留PNG解码/像素/路径、真executor正例；补失败attempt和ODE伪造。

L94–L108

```python


def _write_artifact(
    p1_run: rs.ReportRun, data: bytes, name: str = "chart_1.png", *, script: str | None = None
) -> None:
    """受控地产生"本次 attempt"的产物：记录走真实 begin/finish，字节由测试给出。

    这不是绕过验证：attempt 记录与文件归属仍由服务端流程写下，验证逻辑完全真实。
    """
    if script is not None:
        (p1_run.workdir / ce.CHART_SCRIPT_NAME).write_text(script, encoding="utf-8")
    attempt = ce.begin_chart_attempt(p1_run, name)
    (p1_run.workdir / name).write_bytes(data)
    ce.finish_chart_attempt(
        attempt, ce.ChartExecutionResult(exit_code=0, timed_out=False, error="", status="ok")
```

L119–L133

```python
# 正例与基本属性
# ---------------------------------------------------------------------------
def test_valid_current_png_passes(p1_run: rs.ReportRun) -> None:
    result = _execute(p1_run, _chart_code())
    assert result.ok is True

    entry = cv.validate_chart_output(p1_run, "chart_1.png")

    target = p1_run.workdir / "chart_1.png"
    assert entry == {
        "path": "chart_1.png",
        "size": target.stat().st_size,
        "sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest(),
        "role": rs.ROLE_CHART,
    }
```

### deeptutor/subjects/json_store.py

只读，复用strict/短事务锁，不改共享store。

L180–L194

```python


def confined(root: Path, path: Path) -> Path:
    """Return *path* after proving it stays inside *root* without symlinks.

    Checks the root, every component below it, and the final resolved location.
    Nothing is created or opened here — callers run this *before* touching the
    target, so a rejected path is never read, mkdir'd or locked.
    """
    root = ensure_trusted_root(root)
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise StorageIOError(_ESCAPE_MESSAGE, path=path.name) from None
```

L388–L402

```python


def atomic_write_object(path: Path, payload: dict) -> None:
    """Object counterpart of :func:`atomic_write_list`."""
    path = Path(path)
    if not isinstance(payload, dict):
        raise UpdateCallbackError("对象文档必须是对象")
    _commit(path, dict(payload))


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------
@dataclass
class _LockHandle:
```

L605–L619

```python
# Transactions
# ---------------------------------------------------------------------------
class JsonTransaction:
    """A locked read-modify-write scope over one directory.

    Reentrant: entering the same directory's transaction again from the same
    thread reuses the same lock, and the inner exit does not release the outer
    hold. All paths used here must stay inside :attr:`lock_dir`.
    """

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = Path(lock_dir)
        self._lock: _PathLock | None = None
        self._resolved = ""

```

### deeptutor/subjects/store.py

只读，当前用户与已登记subject根是权威。

L112–L126

```python


def current_subject_paths() -> PathService:
    """The **current user's** ``PathService``, resolved strictly (C01).

    :func:`deeptutor.services.path_service.get_path_service` wraps this in a
    ``try/except`` that falls back to the default (admin) instance. That is the
    right thing for best-effort display paths and exactly the wrong thing for
    learner data: if the current scope cannot be resolved, subject storage must
    fail loudly rather than quietly read or write the administrator's tree.

    Every subject/output helper in this module resolves through here.
    """
    from deeptutor.multi_user.paths import get_current_path_service

```

L187–L201

```python


def subject_dir(subject_id: str) -> Path:
    """The data directory for one subject in the current user's registry.

    Raises an explicit error for an id that is not a plain slug, for a path
    that resolves outside this user's subject root, and for a well-formed id
    that is simply not registered (404) — writing learner data must never bring
    a subject tree into existence.
    """
    path = _subject_dir_unchecked(subject_id)
    if not _is_registered(subject_id):
        raise SubjectNotFoundError(subject_id)
    return path

```

### deeptutor/subjects/errors.py

只读，使用C02现有安全code/message/status，不发明裸异常。

L134–L148

```python
        ErrorCode.REASONING_BUDGET_EXHAUSTED, 502, True, "模型把输出预算耗尽在推理上，请重试。"
    ),
    ErrorCode.SANDBOX_UNAVAILABLE: _spec(
        ErrorCode.SANDBOX_UNAVAILABLE, 503, False, "隔离执行环境不可用。"
    ),
    ErrorCode.SANDBOX_POLICY_UNSUPPORTED: _spec(
        ErrorCode.SANDBOX_POLICY_UNSUPPORTED, 503, False, "当前部署不支持所需的隔离执行策略。"
    ),
    ErrorCode.CHART_FAILED: _spec(
        ErrorCode.CHART_FAILED, 502, True, "图表生成失败。"
    ),
    ErrorCode.RENDER_FAILED: _spec(
        ErrorCode.RENDER_FAILED, 502, True, "文档渲染失败。"
    ),
    ErrorCode.FEATURE_UNAVAILABLE: _spec(
```

L140–L154

```python
        ErrorCode.SANDBOX_POLICY_UNSUPPORTED, 503, False, "当前部署不支持所需的隔离执行策略。"
    ),
    ErrorCode.CHART_FAILED: _spec(
        ErrorCode.CHART_FAILED, 502, True, "图表生成失败。"
    ),
    ErrorCode.RENDER_FAILED: _spec(
        ErrorCode.RENDER_FAILED, 502, True, "文档渲染失败。"
    ),
    ErrorCode.FEATURE_UNAVAILABLE: _spec(
        ErrorCode.FEATURE_UNAVAILABLE, 501, False, "该功能在当前版本不可用。"
    ),
}


def safe_message(text: str, *, fallback: str = "服务内部错误，请稍后重试。") -> str:
```

L300–L314

```python


def subject_error(code: ErrorCode | str, *, cause: BaseException | None = None) -> SubjectOperationError:
    """用 C02 表中的固定投影构造错误（消息/状态/retryable 都来自表）。"""
    resolved = ErrorCode(code) if not isinstance(code, ErrorCode) else code
    spec = ERROR_SPECS[resolved]
    return SubjectOperationError(
        spec.code,
        spec.message,
        http_status=spec.http_status,
        retryable=spec.retryable,
        cause=cause,
    )


```

### deeptutor/services/sandbox/backends.py

只读，不把报告修复扩散到全局backend。

L111–L125

```python


class BwrapBackend(SandboxBackend):
    """Bubblewrap mount-namespace isolation (Linux only)."""

    level = IsolationLevel.SYSTEM

    _RO_SYSTEM_DIRS = ("/usr", "/usr/local", "/bin", "/lib", "/lib64", "/etc", "/sbin")
    _DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    def __init__(
        self,
        bwrap_path: str = "bwrap",
        *,
        venv_path: str | Path | None = None,
```

L278–L292

```python


async def _communicate(process: asyncio.subprocess.Process, timeout_s: int) -> ExecResult:
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        process.kill()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=5.0)
        return ExecResult(timed_out=True, exit_code=124)
    return ExecResult(
        stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
        stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
        exit_code=process.returncode if process.returncode is not None else 0,
    )
```

### deeptutor/services/sandbox/spec.py

只读，ExecResult.ok不含exit code判定。

L97–L111

```python

@dataclass(frozen=True)
class ExecResult:
    """Outcome of a sandboxed execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    error: str = ""  # set when the sandbox itself failed (not the command)

    @property
    def ok(self) -> bool:
        return not self.error and not self.timed_out

```

### plans/phase1/DATA_CONTRACTS.md

C11仍是权威，没有更改契约。

L132–L146

```text
知识点关联从本 subject 的未归档 wrong entry 和对应学期考点派生。build 可重复执行，新增/归档/删除后 aggregate 不把不存在或已归档记录计入。现有人工点保留；不自动从教材抽知识点，不把整个学习库迁到 Guided Learning 数据模型。

## C11：报告、执行与产物

report_id 使用服务端 uuid hex（无时间秒碰撞）。私有 staging：`workspace/subjects/<sid>/_report_runs/<rid>`；成功正式产物：`public outputs/subjects/<sid>/reports/<rid>`。旧报告目录不迁移，受约束的 legacy review 可以读同科旧正文。新任务不共享 _chart.py、_ode_check.py、chart_1.png 或错误日志。

create 两入口统一调用同一 pipeline，持久化 report.md、report.pdf、chart_N.png、私有 report metadata，保留 markdown_tokens/chart_count/url/path 旧字段并增加 report_id/status。URL 从实际 server 相对路径构造；path 若继续保留只能指本科正式产物，不暴露任意 path 参数。

```json
{"report_id":"...","status":"completed","chart_count":1,"markdown_tokens":600,"url":"/api/outputs/subjects/复变函数/reports/<rid>/report.pdf","path":"<server-owned-path>","verification_status":"not_requested"}
```

正文完整，所有声明图表均成功且有效，PDF 确实编译/可打开后才 completed/发布 URL。允许无声明图的纯正文报告，但不能把声明图的失败变成 completed；缺图为 chart_failed。CHART 正则识别与替换使用同一个 match，支持零空格/多空格。脚本成功需退出码为 0（ExecResult.ok 本身不检查 exit_code），目标 PNG 是当前任务的新常规非 symlink 文件，Pillow验证有效、路径被限定、size 上限，不能仅检查 exists。所有正文/核查 Markdown 图片引用都只能是本任务经过验证的 chart_N.png 白名单；包括模型自行输出的图片引用，也不得接受外部URL、绝对/相对穿越或引号注入到Typst。临时脚本/错误日志不能随目录整包发布，正式目录只发布文档、验证图片及私有manifest。

source_file 是当前 turn source_index 中的附件 source_id，只能读取服务端已附着文本；无可解析 ID 返回 invalid_input。禁止读取模型给的宿主任意路径。API 使用 requirements 即可，不为其新增通用文件读取参数。
```

L214–L228

```text
| 20 | `resolve_kb_ref(kb_ref, *, expected_subject_id, mounted_refs=None, require_ready=True) -> ResolvedSubjectKb` | fields为kb_ref/name/base_dir/subject_id/read_only/provider；严格授权且有C08歧义策略 |
| 26 | `async describe_image_for_index(image_path, *, source_file, page=None, location=None)` | fields为text/content_kind/source_file/page/location/asset_ref/skip_reason；描述或具名跳过，不伪造页码 |
| 32 | `create_report_run(subject_id, *, reviewed_from=None) -> ReportRun` | fields为report_id/subject_id/staging_dir/public_dir；生成服务端id |
| 32 | `publish_report_run(run, *, files, verification_status) -> ReportManifest` | 校验并发布；fields对应schema；不发布临时脚本 |
| 32 | `resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest` | 当前科已知报告，可发现legacy；不得任意文件读 |
| 33 | `async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult` | fields为exit_code/timed_out/error/stdout/stderr；合格policy才执行，无裸fallback |
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

## 附录B：机器可检验的字段示例

`schemas.json` 使用 JSON Schema 2020-12 的 `$defs` 定义错误、规范化批改/检测结果、上传、作用域、知识点评估、图像覆盖、报告、source manifest、导出manifest和completion。`examples.json` 记录每种形状的有效样例及必须拒绝的反例，均为虚构数据。

```

L217–L229

```text
| 32 | `publish_report_run(run, *, files, verification_status) -> ReportManifest` | 校验并发布；fields对应schema；不发布临时脚本 |
| 32 | `resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest` | 当前科已知报告，可发现legacy；不得任意文件读 |
| 33 | `async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult` | fields为exit_code/timed_out/error/stdout/stderr；合格policy才执行，无裸fallback |
| 34 | `validate_chart_output(run, expected_png) -> dict` | 当前目录的有效新PNG，返回relative path/size/hash或失败 |
| 40 | `export_subject_bundle(subject_id) -> dict` | 私有snapshot→ZIP；fields为export_id/schema_version/zip_path/manifest，路径server-owned |

ReportRun/ReportManifest可用dataclass或Pydantic实现，字段名称按表固定。旧completed报告没有report_id时允许返回受约束的legacy标识，但不能伪造新UUID并改写旧文件。JSON存储其他方法仍保留原签名，消费者接入这些基础接口。

## 附录B：机器可检验的字段示例

`schemas.json` 使用 JSON Schema 2020-12 的 `$defs` 定义错误、规范化批改/检测结果、上传、作用域、知识点评估、图像覆盖、报告、source manifest、导出manifest和completion。`examples.json` 记录每种形状的有效样例及必须拒绝的反例，均为虚构数据。

Schema验证字段和枚举，不替代行为验证：路径包含关系、授权、来源真实性、事务锁、失败字节不变、provider截断、网络/沙箱等仍按C01–C14执行测试。也不要求生产添加jsonschema依赖；可用既有Pydantic/代码验证实现相同义务。schema中的批改输出是trim/lower归一化后的结果，允许预验证进行C05规定的大小写归一化。
```

### plans/phase1/schemas.json

ReportFile/Metadata/Response与私有extra扩展边界，勿改schema。

L835–L849

```json
      "additionalProperties": false
    },
    "ReportFile": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "pattern": "^(?!\\.\\.?$)[^/\\\\\\x00-\\x1f]+(?![\\s\\S])"
        },
        "size": {
          "type": "integer",
          "minimum": 0
        },
        "sha256": {
          "type": "string",
```

L866–L880

```json
      "additionalProperties": false
    },
    "ReportMetadata": {
      "type": "object",
      "properties": {
        "schema_version": {
          "const": 1
        },
        "report_id": {
          "type": "string",
          "pattern": "^[a-f0-9]{32}(?![\\s\\S])"
        },
        "subject_id": {
          "type": "string",
          "pattern": "^[a-z0-9\\u4e00-\\u9fff][a-z0-9\\u4e00-\\u9fff-]{0,63}(?![\\s\\S])"
```

### plans/phase1/START_S08.txt

原开工要求已授权，同期窄返修细化。

L27–L41

```text
二、四个内部单元

P1-31 报告输入、严格code对象及ODE提示
目标：普通统计图不被默认ODE污染；任何将进入执行器的表达式/代码对象先通过固定输入契约。
允许：report.py 的CHART_CODE_PROMPT/_extract_json/纯输入接缝、report_inputs.py、test_p1_31.py；不接通整篇publish或改API/工具。
数据与实现要求：
- ode_rhs为空时无默认f、无x**2-y、无“必须遵守ODE”段，按图表spec构造普通绘图提示；有ODE才插入经过验证的原表达式。不能靠prompt要求代替代码验证。
- 表达式以AST解析：仅x/y、有限实数常量、二元+ - * / **、一元+/-，及sin/cos/exp/log/sqrt/abs这6个名字的一参数直接调用。拒绝bool、NaN/Inf、属性/下标/import/lambda/推导式/未知名/双下划线/关键字参数。不要用宿主eval试算模型或用户表达式；计算量仍归受限worker。
- 模型图表响应复用已验收parse_model_object/完整对象验证；code必须非空字符串，不接收list/dict/截断JSON/尾随对象，不靠贪婪regex或自动“补半JSON”。沿用生成服务预算/截断边界，不直接返回空dict掩盖失败。
- 图占位识别有统一纯helper，最多8张，超过明确invalid_input。P35再用同一match替换占位，本阶段为它保留数据，不引入新的图表语言或数学证明系统。
证据：普通图prompt无默认方程；合法x**2-y/sin(x)-y接受；仅改变一个语法节点的反例逐一拒绝；模型code正确对象正例→类型/空白/半JSON/多对象失败；0/1/8/9图；表达式拒绝发生在调用provider/executor前。
完成：P31定向通过，纯输入无文件/网络副作用，再进入P32。

P1-32 独立run、状态与完成发布
目标：每次报告有独立服务端身份与私有目录；失败不覆盖旧completed或暴露正式URL。
```

L38–L52

```text
完成：P31定向通过，纯输入无文件/网络副作用，再进入P32。

P1-32 独立run、状态与完成发布
目标：每次报告有独立服务端身份与私有目录；失败不覆盖旧completed或暴露正式URL。
允许：report_store.py、test_p1_32.py；只实现目录/manifest/读取辅助，不调用模型或执行图表。
固定接口（DATA_CONTRACTS附录A）：
create_report_run(subject_id, *, reviewed_from=None) -> ReportRun
publish_report_run(run, *, files, verification_status) -> ReportManifest
resolve_report_for_review(subject_id, *, report_id=None, legacy_path=None) -> ReportManifest
ReportRun至少有report_id/subject_id/staging_dir/public_dir；ReportManifest字段与ReportMetadata一致，并保留服务端内部路径与安全公开投影的区分。
要求：
- uuid.uuid4().hex作为32位report_id；当前用户/已登记subject；通过S03 confined/strict reader构造路径。private staging=subject/_report_runs/rid；completed=当前用户public outputs/subjects/sid/reports/rid。不能信任传入Path/自定义ID拼目录；重复ID即拒绝，不覆盖。
- metadata schema_version=1，status仅running/completed/failed/abandoned，created_at非负int、reviewed_from可null、verification_status仅not_requested/passed/failed、files为ReportFile(path相对basename,size,sha256,role=markdown/pdf/chart)，owner_pid可选。未知私有扩展可保留，不能公开宿主目录/诊断。
- 仅显式publish才产生正式资源；同subject短锁保护发布/互斥，文件复制到本次私有目标再完成rename/commit，普通失败回滚本次产物。检查常规文件/非symlink/路径归属/size/hash，不把外部源或模型指定目的地复制过去。发布清单仅正文MD、真正PDF、经验证PNG，不能整包拷贝脚本/日志/缓存。权威metadata保持私有，公开投影只含契约字段。
- completed要求not_requested或passed，failed验证不能publish；缺正文/PDF、空文件、hash不符、重复path/未知role/多份主正文或主PDF拒绝；chart角色允许多项且总数不超过8。publish不替代P35对全文/编译完成的质量检查；其输入必须来自服务端已验证文件清单，不接受模型自签。
```

L56–L70

```text
完成：P32定向通过，状态/files符合ReportMetadata schema，再进入P33。

P1-33 专用受限图表执行器与可信worker
目标：供P35和P34复用的唯一report-only执行边界；无合格backend时固定503，不能退回宿主执行。
允许：chart_executor.py、chart_worker.py、test_p1_33.py。依赖BwrapBackend/ExecRequest等只读，不改普通exec/sandbox service/settings/core runner。
接口：内部ReportExecutionPolicy与ChartExecutionResult（至少exit_code/timed_out/error/stdout/stderr）；async execute_chart_code(code, *, run, expected_png, policy) -> ChartExecutionResult（与DATA_CONTRACTS附录A固定异步签名一致）。模型不提供policy/limits/mounts/env/worker路径。
关键已探索事实：当前BwrapBackend固定挂载/usr等及/etc、继承进程env；health只看error不看exit_code；_communicate无输出内存上限且超时只杀单进程，ResourceLimits的CPU/内存并未自动强制。直接调用它或SandboxService不能满足C11，不得以level=SYSTEM标签当全部证明。
要求：
- 在新chart_executor内复用/窄派生BwrapBackend的组装思路，实现报告专用策略；不扩共享服务。backend必须可证逐任务OS隔离，拒绝APPLICATION/OFF、未证明逐任务最小mounts的sidecar/shared runner；不信任仅同名类或可伪造level字段。
- 只将当前run workdir作为可写宿主挂载；解释器/其真实managed runtime、必要libs、字体、trusted worker只读。不能挂repo/home/settings/其他科/其他run为可读目录；不能照搬/etc全目录作为最小所需。namespace内/proc、/dev、私有tmpfs的必要可写不等同于增加可写宿主树。
- 明确--clearenv/等效隔离；env白名单固定，不复制os.environ。PATH/Python隔离参数/字体缓存由服务端指定，缓存限本run，拒绝凭据/代理/PYTHONPATH/sitecustomize影响。argv无shell，用ExecRequest.of_argv或等效一致向量，不让模型拼command。
- chart_worker是仓库新可信文件，单独只读挂载，不复制到模型可写目录后再信任执行。先设置进程级hard RLIMIT CPU30s、地址空间1536MiB、文件大小界限，再运行模型脚本；子进程继承。worker控制参数仅服务端生成，不由模型脚本提供。不能宣称实现了整进程树累计cgroup配额。
- 图表墙钟60s，ODE30s；stdout/stderr合计有界10000字符，读取期间就限内存，不能先communicate全部再截断。墙钟超时终止整个执行进程组并reap，处理取消/异常的清理，保持其他run不受影响。
- 严格综合error、timed_out、exit_code==0；ExecResult.ok忽略非零exit_code，不能单独用它。backend健康测试也看真实退出码/timeout；不存在/不健康固定sandbox_unavailable503，不裸subprocess fallback、自动下载或改系统策略。
- OS隔离真实验证属于S15/P50门；S08用fake backend与受控进程边界验证策略/限额/失败。可以做无副作用健康探测；缺OS能力时证明503，不拿fake冒充OS隔离成功，不为跑真实模型脚本安装环境。
```

L72–L86

```text
完成：P33定向通过、request/result契约与失败映射可供P34/P35直接调用，再进入P34。

P1-34 当前任务PNG与ODE数值产物验证
目标：存在文件不等于有效图；旧图、越界图、未验证声明不能发布；ODE通过只称给定五点数值检查。
允许：chart_validation.py、test_p1_34.py；不编排全文报告、不在宿主import或执行模型_chart.py。
接口：validate_chart_output(run, expected_png) -> dict（至少relative path/size/hash或明确C02失败）；其它纯helper命名自定但后续P35可复用。
要求：expected_png是服务端预分配basename chart_N.png（N 1..8），隶属本run；每次重试删除/隔离该次旧产物，不能凭mtime或exists把上次成功图当本次。仅普通非链接新文件，拒绝父/叶链接、另一run/穿越路径。
Pillow verify并实际解码检查：非空、有效PNG、<=10MiB、<=20百万像素；解压炸弹warning/error均拒绝，读取/验证不能无界。成功返回真实hash/size与相对名，代码exit0无图仍chart_failed。
ODE检查必须经P33同一trusted worker/executor、验证后的表达式；在隔离环境读取当前脚本的f及声明表达式，使用固定5点(-2.5,1.0),(0,0.5),(1.7,-2),(2.2,2.5),(-0.8,-3)，所有数值有限，最大绝对误差<1e-6才passed。缺f、mismatch、NaN/Inf、坏输出/超时均失败；not_requested仅无ODE。不得宿主eval/import模型、借普通runner兜底。输出解析拒绝不完整/伪造结构，不夸大为解析解或整篇数学已证明。
证据：有效当前PNG正例→空/损坏/别run/链接/超byte/超像素/解码warning反例；exit0缺图失败；两次attempt不复用旧图；ODE五点合法/不符/非有限/超时，fake落在executor边界，调用实际validation，不仅断言helper曾被调用。
完成：P34定向通过，然后统一收尾，不继续P35。

三、统一验证与交付

每单元测试一次，有实际变动/失败才追加。全部跨目录pytest在收集前用现有只读S01 launcher初始化临时HOME，默认fake provider，禁止读取真实目录填环境：
```

### .phase1-evidence/reviews/S08/probe_s08.py

只读独立32场景：28失败/4通过，优先直接运行；不能编辑逃避验收。

L75–L89

```python


def test_wall_clock_also_covers_wait_after_output_eof(tmp_path):
    async def scenario():
        spawn=ce.SpawnCommand((sys.executable,'-I','-c','import os,time;os.close(1);os.close(2);time.sleep(2)'),tmp_path,{})
        limits=ce.ReportResourceLimits(1,5,128,1000,1024)
        result=await asyncio.wait_for(ce.run_bounded_spawn(spawn,limits),timeout=4)
        assert result.timed_out, 'EOF结束了deadline，进程越过1秒时限后仍返回成功'
    asyncio.run(scenario())


def test_exited_leader_does_not_leave_descendant_alive(tmp_path):
    pidfile=tmp_path/'leader.pid';canary=tmp_path/'survivor'
    program="import subprocess,sys,os;open(%r,'w').write(str(os.getpid()));subprocess.Popen([sys.executable,'-I','-c',%r])"%(str(pidfile),"import time;time.sleep(2);open(%r,'w').write('survived')"%str(canary))
    async def scenario():
```

L138–L152

```python


def test_uuid_create_race_cannot_delete_successful_creator(p1_runtime,monkeypatch):
    subject=helpers.make_subject(p1_runtime,'UUID竞争');fixed=uuid.UUID('11'*16)
    monkeypatch.setattr(rs.uuid,'uuid4',lambda:fixed)
    real=rs.json_store.make_directory;barrier=threading.Barrier(2);complete=threading.Event();guard=threading.Lock();order=[];result=[]
    def intercepted(path,**kwargs):
        if Path(path).name==fixed.hex and kwargs.get('exist_ok') is False:
            with guard:index=len(order);order.append(index)
            barrier.wait(timeout=5)
            if index==1:assert complete.wait(5)
        return real(path,**kwargs)
    monkeypatch.setattr(rs.json_store,'make_directory',intercepted)
    def create():
        try:
```

L226–L240

```python


def test_ode_model_cannot_self_certify_success_via_stdout(run):
    path=run.workdir/ce.CHART_SCRIPT_NAME
    path.write_text('def f(x,y): return x-y\n')
    positive=asyncio.run(cv.check_ode_numeric(run,'x-y'));assert positive['status']=='passed'
    payload={'ok':True,'finite':True,'points':5,'max_abs_error':0.0}
    path.write_text("import os\ndef f(x,y): return 123456\nif __name__ == '_chart_model':\n    os.write(1,%r)\n    os._exit(0)\n"%json.dumps(payload).encode())
    with pytest.raises(SubjectOperationError):asyncio.run(cv.check_ode_numeric(run,'x-y'))


def test_worker_output_flood_is_drained_bounded_not_materialized(run):
    # Actual isolated worker, 64MiB hard address-space cap. 128MiB log stream
    # must be discarded while draining instead of exhausting worker memory.
    policy=ce.ReportExecutionPolicy(memory_mb=64,cpu_seconds=5,wall_clock_s=8)
```

L235–L246

```python


def test_worker_output_flood_is_drained_bounded_not_materialized(run):
    # Actual isolated worker, 64MiB hard address-space cap. 128MiB log stream
    # must be discarded while draining instead of exhausting worker memory.
    policy=ce.ReportExecutionPolicy(memory_mb=64,cpu_seconds=5,wall_clock_s=8)
    control=asyncio.run(ce.execute_chart_code("import os\nos.write(1,b'x'*4096)\nopen('chart_1.png','wb').write(%r)\n"%png(),run=run,expected_png='chart_1.png',policy=policy))
    assert control.ok and control.status=='ok', '相同64MiB策略的短输出正例必须先通过'
    code="import os\nfor i in range(32768): os.write(1,b'x'*4096)\nopen('chart_1.png','wb').write(%r)\n"%png()
    result=asyncio.run(ce.execute_chart_code(code,run=run,expected_png='chart_1.png',policy=policy))
    assert result.ok and result.status=='ok', 'worker先communicate整段日志导致自身OOM/崩溃而非有界读取: '+repr((result.error,result.status,result.stdout,result.worker_payload))
    assert len(result.stdout)+len(result.stderr)<=policy.max_output_chars
```

## 用例定位与验证顺序

独立probe中的名称直接对应REWORK_S08各单元，无须再找缺陷：R1=prompt/code；R2=server_owned/metadata；R3=publish_rejection/fail_cleanup/uuid/live_foreign；R4=wall_clock/exited_leader/output_flood；R5=worker_protocol；R6=failed_attempt/old_attempt/post_execution；R7=negative_numeric/ode_model。详见REWORK_S08中的用例映射和完成条件。将有效断言迁入四份允许的仓内测试；原独立probe保持原hash，返修前后原样各跑一次。

当前正常的无ODE输入、完整发布和当前PNG必须保留；newline basename拒绝与bool exit产生失败这两个已通过场景也不能回退。真实资料与memory仅不透明snapshot；所有业务收集使用临时HOME launcher。原S08报告的最早related/ruff/bad-control日志互相穿插，应保留为历史，新返修日志严格串行。

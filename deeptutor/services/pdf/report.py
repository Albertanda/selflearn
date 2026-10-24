"""Report writing (M7/P1-35) — one server-owned run, one explicit publication.

Pipeline: LLM writes Markdown with ``{{CHART: description}}`` placeholders
-> LLM emits matplotlib code per chart -> the **P33/P34 sandbox executor** runs
it (no host ``subprocess`` fallback) -> validated PNG -> trusted Typst template
-> PDF parsed and opened -> all files published together by
:func:`deeptutor.services.pdf.report_store.publish_report_run`.

The run id, staging directory and public directory are decided by
``report_store`` from the current user + registered subject; no caller-supplied
``out_dir`` can redirect them.  A declared chart that cannot be produced makes
the whole run ``chart_failed`` with no public URL: a failed figure is never
turned into text and then called a successful report.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import re
import stat
from typing import Any, Sequence
import warnings

from deeptutor.services.llm.config import get_llm_config
from deeptutor.services.llm.exceptions import LLMEmptyResponseError
from deeptutor.services.pdf import chart_executor, chart_validation, report_inputs, report_store
from deeptutor.services.pdf.report_inputs import (
    build_chart_code_prompt,
    parse_chart_code_response,
    parse_chart_object,
    validate_ode_expression,
    validated_chart_placeholders,
)
from deeptutor.services.pdf.review_guide import (
    _TYST_DOC,
    _md_to_typst,
    estimate_tokens,
    typst_compile,
)
from deeptutor.subjects import LLM_MAX_TOKENS, json_store, store, subject_operations
from deeptutor.subjects.errors import (
    ErrorCode,
    SubjectOperationError,
    SubjectStorageError,
    subject_error,
)
from deeptutor.subjects.generation import complete_subject_text

logger = logging.getLogger(__name__)

REPORT_PROMPT = """你是一名大学助教，根据题目要求撰写一份课程报告（中文）。

## 报告题目
{title}

## 题目要求
{requirements}
{subject_context}
## 写作要求
1. 结构：# 标题 开头，然后是 ## 引言、## 各分析章节（按题目要求组织）、## 结论。
2. 需要用图表达的地方插入占位符：{{CHART: 图表描述}}——描述里写清楚要画什么（函数/数据、坐标轴含义、x 范围）。每张图占位符独占一行。
3. 数学公式用 Unicode 文本（如 y′ = x² − y、e^(−x)），不要用 LaTeX 命令。
4. 只使用 Markdown 子集：#、##、-、**加粗**；不要表格、代码块、链接。
5. 正文 800-1200 字（不含图），内容准确、结构完整，直接基于题目要求。
6. 数学严谨性：凡是给出解析解、平衡点、稳定性等结论，必须代入原方程验证后再写；精确解写出来前先自查（例如 y' = x² − y 的通解是 y = x² − 2x + 2 + C·e^(−x)，代回可验证）；不要臆造公式或结论。
"""

#: Rendered into ``{subject_context}`` when the turn carries subject scope.
#: The leading newline keeps the section separated from 题目要求; an empty
#: context renders as "" so the prompt is unchanged for subject-less turns.
SUBJECT_CONTEXT_TEMPLATE = """
## 学情信息
{hint}
（如与题目相关，可结合该科目的错题与考点组织内容；不相关则忽略。）
"""

CHART_CODE_PROMPT = report_inputs.PLAIN_CHART_CODE_PROMPT
"""旧名字保留为**普通**图表模板（P1-31）。

实际使用的提示词一律由
:func:`deeptutor.services.pdf.report_inputs.build_chart_code_prompt` 构造
（无 ODE → 普通模板；有 ODE → 插入 AST 校验后的原表达式）。
"""

REVIEW_PROMPT = """你是一名严谨的课程助教，正在对一份课程报告做**核查与修复**。请逐条核对：
1. 数学正确性（公式、解的推导、结论是否站得住；能代入验证的必须验证）；
2. 图表与文字是否对应（图的内容是否支持对应章节的说法）；
3. 结构完整性与题目要求覆盖度。

输出修复后的完整报告（Markdown，结构与要求同原报告；数学用 Unicode 表达；不引入新图，
只能原样保留原图引用行 `![chart N](chart_N.png)`）。直接输出修复版全文。
"""

#: One Markdown image line, in the only shape this pipeline sends to Typst:
#: a bare, server-allocated ``chart_N.png`` basename with no title / quotes /
#: path separator.  Everything else that *looks* like an image is rejected.
_IMAGE_LINE_RE = re.compile(r"^!\[[^\]\n]*\]\((?P<target>[^)\s]+)\)$")
_IMAGE_MARKER_RE = re.compile(r"!\[|<img\b", re.IGNORECASE)

#: Bounded retries for one declared chart: code response -> executor ->
#: validated artifact -> (optional) trusted ODE check.
_MAX_CHART_ATTEMPTS = 3


async def _llm(prompt: str, system: str) -> str:
    """One report-pipeline completion.

    Runs through the shared subject-feature helper, which applies the explicit
    generation budget (a reasoning model bills its chain-of-thought against the
    same ``max_tokens``, and the 4096 default can be spent entirely on reasoning)
    and reports a budget-truncated generation by name instead of returning "".
    """
    cfg = get_llm_config()
    return await complete_subject_text(
        prompt=prompt,
        system_prompt=system,
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
    )


def _extract_json(raw: str) -> dict:
    """Strict single-object parse of one model response (P1-31).

    Delegates to the accepted C04 parser and raises the fixed C02 error instead
    of returning ``{}`` for a broken/truncated response.
    """
    return parse_chart_object(raw)


def _validate_ode_expression(ode_rhs: object) -> str:
    """P1-31 seam: the validated ODE right-hand side, or ``""`` when absent.

    Kept as a module-level alias so the ``generate_report`` flow validates the
    expression exactly once, before any provider or executor call, and passes the
    *same* validated text to the prompt builder and the ODE checker.
    """
    return validate_ode_expression(ode_rhs)


# ---------------------------------------------------------------------------
# Image references: only this run's verified chart basenames, nothing else
# ---------------------------------------------------------------------------
def _image_line_target(line: str) -> str | None:
    """The target of a supported image line, or ``None`` for ordinary text."""
    match = _IMAGE_LINE_RE.fullmatch(line.strip())
    return match.group("target") if match is not None else None


def _sanitize_image_references(markdown: str, allowed_names: Sequence[str]) -> list[str]:
    """Prove every image reference points at an already verified basename.

    Supported form is exactly one ``![alt](chart_N.png)`` per line.  Reference
    style, HTML ``<img>``, external URLs, absolute/relative paths, quotes,
    titles, unknown chart numbers and unverified files are all rejected before
    Typst sees the document — the model's raw path is never forwarded.
    """
    allowed = set(allowed_names)
    used: list[str] = []
    for line in markdown.splitlines():
        if _IMAGE_MARKER_RE.search(line) is None:
            continue
        target = _image_line_target(line)
        if target is None or target not in allowed:
            raise subject_error(ErrorCode.INVALID_MODEL_OUTPUT)
        used.append(target)
    return used


# ---------------------------------------------------------------------------
# Trusted Typst rendering + independent PDF verification
# ---------------------------------------------------------------------------
def _pdf_counts(path: Path) -> tuple[int, int]:
    """(pages, embedded images) from a real PDF parser; ``render_failed`` otherwise."""
    try:
        import pymupdf

        with pymupdf.open(str(path)) as document:
            pages = int(document.page_count)
            images = 0
            for page in document:
                images += len(page.get_images(full=True))
        return pages, images
    except Exception as exc:  # noqa: BLE001 - damaged/truncated PDF is a render failure
        raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc


def _verify_report_pdf(path: Path, expected_images: int = 0) -> tuple[int, int]:
    """Require an actually opened PDF with at least one page/image.

    ``typst_compile`` returning ``True`` or a file merely existing is not
    enough: the emitted document must parse, have a page, and (when charts were
    declared) actually embed them.
    """
    if not path.is_file() or path.is_symlink():
        raise subject_error(ErrorCode.RENDER_FAILED)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            prefix = handle.read(5)
    except OSError as exc:
        raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc
    if not 0 < size <= report_store.MAX_PUBLISHED_FILE_BYTES or prefix != b"%PDF-":
        raise subject_error(ErrorCode.RENDER_FAILED)
    pages, images = _pdf_counts(path)
    if pages < 1 or images < expected_images:
        raise subject_error(ErrorCode.RENDER_FAILED)
    return pages, images


def _render_report_pdf(
    markdown: str,
    chart_names: Sequence[str],
    out_path: Path,
    typst_bin: Path,
) -> bool:
    """Render verified Markdown + whitelisted images with the trusted template.

    The ``#image(...)`` call is generated **from the server-side name table**,
    never from the model's path text: ``_md_to_typst`` escapes body text, so a
    token is parked per image line and replaced after conversion.  A model
    cannot inject Typst code through the alt text or the target because both
    were already restricted by :func:`_sanitize_image_references`.
    """
    _sanitize_image_references(markdown, chart_names)
    tokens: dict[str, str] = {}
    lines: list[str] = []
    for line in markdown.splitlines():
        target = _image_line_target(line)
        if target is not None:
            # Same pre-validated table: the call only ever carries a basename.
            if target not in set(chart_names):
                return False
            token = f"CHARTIMAGE{len(tokens)}TOKEN"
            tokens[token] = f'#image("{report_inputs.chart_target_basename(target)}", width: 85%)'
            lines.append(token)
            lines.append("")
            continue
        lines.append(line)
    body = _md_to_typst("\n".join(lines))
    for token, call in tokens.items():
        if body.count(token) != 1:
            return False
        body = body.replace(token, call)
    src = _TYST_DOC.format(body=body)
    tmp = out_path.with_suffix(".typ")
    tmp.write_text(src, encoding="utf-8")
    return typst_compile(tmp, out_path, typst_bin)


def _file_entry(path: Path, role: str) -> dict[str, Any]:
    """A ReportFile-shaped entry computed from the actual bytes."""
    limit = (chart_validation.MAX_CHART_BYTES if role == report_store.ROLE_CHART
             else report_store.MAX_PUBLISHED_FILE_BYTES)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                raise subject_error(ErrorCode.RENDER_FAILED)
            data = handle.read(limit + 1)
        if not 0 < len(data) <= limit:
            raise subject_error(ErrorCode.RENDER_FAILED)
    except OSError as exc:
        raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc
    return {
        "path": path.name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "role": role,
    }


def _render_in_owned_context(
    markdown: str,
    chart_names: Sequence[str],
    out_path: Path,
    typst_bin: Path,
    expected_workspace: str,
    expected_images: int,
) -> bool:
    """Render + parse the PDF in a worker thread with the caller's user scope.

    ``asyncio.to_thread`` copies the current context, so the thread must still
    resolve the *same* PathService the async caller used.  If it cannot, the
    render is refused instead of silently writing under the administrator root.
    Typst/PDF parsing is synchronous and can take seconds; neither runs on the
    event loop, and a renderer exception becomes the fixed ``render_failed``.
    """
    paths = store.current_subject_paths()
    if str(paths.workspace_root) != expected_workspace:
        raise subject_error(ErrorCode.INTERNAL_ERROR)
    try:
        rendered = _render_report_pdf(markdown, chart_names, out_path, typst_bin)
    except SubjectOperationError:
        raise
    except Exception as exc:  # noqa: BLE001 - renderer failure is C02 render_failed
        raise subject_error(ErrorCode.RENDER_FAILED, cause=exc) from exc
    if not rendered:
        return False
    _verify_report_pdf(out_path, expected_images)
    return True


def _canonical_reports_dir(subject_id: str) -> Path:
    """The only directory a compatibility ``out_dir`` may name."""
    subject = store.subject_dir(subject_id)
    return store.current_subject_paths().get_public_outputs_root() / "subjects" / subject.name / "reports"


def _validate_out_dir(out_dir: object, subject_id: str) -> None:
    """Retired argument: accepted only when it is the server canonical location."""
    if out_dir is None:
        return
    if isinstance(out_dir, bool) or not isinstance(out_dir, (str, Path)):
        raise json_store.invalid_input("out_dir 必须是路径")
    try:
        actual = Path(out_dir).resolve()
        expected = _canonical_reports_dir(subject_id).resolve()
    except OSError:
        raise json_store.invalid_input("out_dir 无效") from None
    if actual != expected:
        raise json_store.invalid_input("out_dir 不是服务端规范位置")


# ---------------------------------------------------------------------------
# Chart + ODE execution for one declared figure
# ---------------------------------------------------------------------------
async def _produce_chart(
    run: report_store.ReportRun,
    name: str,
    spec: str,
    ode_expression: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Produce one declared chart; only a complete verified attempt returns.

    The three attempts are strictly sequential inside this run (the executor
    refuses overlapping runs).  Every attempt overwrites the private attempt
    record and clears the old PNG, so a previous image can never satisfy a
    later failure.  ``sandbox_*`` errors are infrastructure errors: they are
    reported immediately instead of being retried into ``chart_failed``.
    """
    last_rejection = ""
    for attempt in range(1, _MAX_CHART_ATTEMPTS + 1):
        raw = await _llm(
            build_chart_code_prompt(spec, out_path=name, ode_rhs=ode_expression),
            "你生成 matplotlib 代码，只输出 JSON。",
        )
        try:
            code = parse_chart_code_response(raw)
        except SubjectOperationError as exc:
            # A malformed response is retried like any other failed attempt, but
            # only the fixed C02 code is logged — never the rejected text.
            last_rejection = exc.code.value
            logger.warning("chart %s code response rejected (attempt %d): %s", name, attempt, last_rejection)
            continue

        result = await chart_executor.execute_chart_code(code, run=run, expected_png=name)
        failure = chart_executor.chart_failure_error(result)
        if failure is not None:
            if failure.code in {
                ErrorCode.SANDBOX_UNAVAILABLE,
                ErrorCode.SANDBOX_POLICY_UNSUPPORTED,
            }:
                raise failure
            last_rejection = failure.code.value
            logger.warning("chart %s execution failed (attempt %d): %s", name, attempt, last_rejection)
            continue

        try:
            entry = await asyncio.to_thread(chart_validation.validate_chart_output, run, name)
            checks: dict[str, Any] = {}
            if ode_expression:
                checks = await chart_validation.check_ode_numeric(run, ode_expression)
        except SubjectOperationError as exc:
            if exc.code in {
                ErrorCode.SANDBOX_UNAVAILABLE,
                ErrorCode.SANDBOX_POLICY_UNSUPPORTED,
            }:
                raise
            last_rejection = exc.code.value
            logger.warning("chart %s validation failed (attempt %d): %s", name, attempt, last_rejection)
            continue
        return entry, checks

    # The declaration could not be satisfied: the whole report fails, and the
    # model's failed figure is never swapped for a text note labelled success.
    raise subject_error(ErrorCode.CHART_FAILED)


def _manifest_file_bytes(manifest: report_store.ReportManifest, entry: report_store.ReportFile) -> bytes:
    """Read one declared source file after proving identity, path and hash.

    Used by review: the original report tree is only ever read here, never
    rewritten.  Missing/symlinked/hash-mismatched files are ``storage_corrupt``
    (the manifest promised something the tree cannot deliver).
    """
    base = manifest.public_dir
    if base is None:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    try:
        path = json_store.confined(base, base / entry.path)
    except SubjectStorageError as exc:
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc
    try:
        limit = (chart_validation.MAX_CHART_BYTES if entry.role == report_store.ROLE_CHART
                 else report_store.MAX_PUBLISHED_FILE_BYTES)
        if entry.size > limit:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        # Non-blocking + nofollow also refuse FIFO/symlink replacement at open.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != entry.size:
                raise subject_error(ErrorCode.STORAGE_CORRUPT)
            data = handle.read(limit + 1)
    except SubjectOperationError:
        raise
    except OSError as exc:
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc
    if len(data) > limit or len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    return data


def _validate_png_bytes(data: bytes) -> None:
    """Strict Pillow decode for a copied original chart (never a worker record)."""
    from io import BytesIO

    from PIL import Image

    try:
        if not data or len(data) > chart_validation.MAX_CHART_BYTES:
            raise ValueError("invalid chart size")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("not a single-frame PNG")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > chart_validation.MAX_CHART_PIXELS:
                    raise ValueError("bad dimensions")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
    except Exception as exc:  # noqa: BLE001 - damaged/truncated image
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc


def _source_markdown(manifest: report_store.ReportManifest) -> str:
    entry = manifest.file_for_role(report_store.ROLE_MARKDOWN)
    if entry is None:
        raise subject_error(ErrorCode.STORAGE_CORRUPT)
    data = _manifest_file_bytes(manifest, entry)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc


def _copy_verified_charts(
    source: report_store.ReportManifest, run: report_store.ReportRun
) -> list[dict[str, Any]]:
    """Copy every original chart into the new run after independent verification.

    This is a trusted server-side copy of bytes that already passed publication;
    it deliberately does **not** create a P34 attempt record or pretend a worker
    executed anything.  Only the real bytes (size/sha256) are bound for publish.
    """
    copied: list[dict[str, Any]] = []
    names: set[str] = set()
    for entry in source.files:
        if entry.role != report_store.ROLE_CHART:
            continue
        if entry.path in names:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
        names.add(entry.path)
        data = _manifest_file_bytes(source, entry)
        _validate_png_bytes(data)
        target = json_store.confined(run.workdir, run.workdir / entry.path)
        try:
            target.write_bytes(data)
        except OSError as exc:
            raise subject_error(ErrorCode.STORAGE_CORRUPT, cause=exc) from exc
        copied.append(_file_entry(target, report_store.ROLE_CHART))
        if len(copied) > report_store.MAX_CHART_FILES:
            raise subject_error(ErrorCode.STORAGE_CORRUPT)
    return copied


def _copy_verified_charts_leased(
    source: report_store.ReportManifest, run: report_store.ReportRun
) -> list[dict[str, Any]]:
    """Thread body: hold a subject lease until the copy really finishes.

    A cancelled request releases its own lease, but this inner lease remains
    until the worker thread returns, so a delete cannot start while bytes are
    still being copied into the run directory.
    """
    with subject_operations.acquire_activity(run.subject_id, kind="report-copy"):
        return _copy_verified_charts(source, run)


def _render_with_lease(*args: Any, **kwargs: Any) -> bool:
    """Render-thread body with its own lease, independent of request lifetime."""
    subject_id = str(kwargs.pop("lease_subject_id"))
    with subject_operations.acquire_activity(subject_id, kind="report-render"):
        return _render_in_owned_context(*args, **kwargs)


async def _publish_rendered(
    run: report_store.ReportRun,
    *,
    markdown: str,
    charts: list[dict[str, Any]],
    verification_status: str,
) -> tuple[report_store.ReportManifest, str]:
    """Render/verify/publish one already-complete run; no partial URL survives."""
    chart_names = [str(entry["path"]) for entry in charts]
    _sanitize_image_references(markdown, chart_names)
    report_md = run.workdir / "report.md"
    report_md.write_text(markdown, encoding="utf-8")
    pdf_path = run.workdir / "report.pdf"
    typst_bin = Path(__file__).resolve().parents[3] / "tools" / "bin" / "typst"
    expected_workspace = str(store.current_subject_paths().workspace_root)
    rendered = await asyncio.to_thread(
        _render_with_lease,
        markdown,
        chart_names,
        pdf_path,
        typst_bin,
        expected_workspace,
        len(set(chart_names)),
        lease_subject_id=run.subject_id,
    )
    if not rendered:
        raise subject_error(ErrorCode.RENDER_FAILED)
    def prepare():
        with subject_operations.acquire_activity(run.subject_id, kind="report-prepare"):
            files = [_file_entry(report_md, report_store.ROLE_MARKDOWN),
                     _file_entry(pdf_path, report_store.ROLE_PDF), *charts]
            return report_store._prepare_report_publication(
                run, files=files, verification_status=verification_status)

    prepared = asyncio.create_task(asyncio.to_thread(prepare))

    def discard(done: asyncio.Task) -> None:
        try:
            report_store._discard_report_publication(done.result())
        except BaseException:
            # Consume a failed preparation; never replace cancellation.
            pass

    try:
        publication = await asyncio.shield(prepared)
    except BaseException:
        prepared.add_done_callback(discard)
        raise
    manifest = report_store._commit_report_publication(publication)
    pdf_entry = manifest.file_for_role(report_store.ROLE_PDF)
    if pdf_entry is None:
        raise subject_error(ErrorCode.RENDER_FAILED)
    relative_path = (
        f"subjects/{manifest.subject_id}/{report_store.REPORTS_DIRNAME}/"
        f"{manifest.report_id}/{pdf_entry.path}"
    )
    return manifest, relative_path


def _project(
    manifest: report_store.ReportManifest,
    *,
    title: str,
    markdown: str,
    chart_count: int,
) -> dict:
    url = report_store.report_url(manifest)
    if url is None:
        raise subject_error(ErrorCode.RENDER_FAILED)
    pdf_entry = manifest.file_for_role(report_store.ROLE_PDF)
    if pdf_entry is None:
        raise subject_error(ErrorCode.RENDER_FAILED)
    relative_path = (
        f"subjects/{manifest.subject_id}/{report_store.REPORTS_DIRNAME}/"
        f"{manifest.report_id}/{pdf_entry.path}"
    )
    return {
        "report_id": manifest.report_id,
        "status": manifest.status,
        "title": title,
        "markdown": markdown,
        "markdown_tokens": estimate_tokens(markdown),
        "chart_count": chart_count,
        "pdf_ok": True,
        "pdf_path": relative_path,
        "url": url,
        "path": relative_path,
        "verification_status": manifest.verification_status,
    }


def _fail_preserving_error(run: report_store.ReportRun) -> None:
    """A cleanup IO error must not replace the original failure/cancellation."""
    try:
        report_store.fail_report_run(run)
    except Exception:
        # fail_report_run already releases active ownership in its finally.
        # Keep corrupt diagnostics untouched; never log provider text or paths.
        logger.warning("report failure metadata could not be finalized")


# ---------------------------------------------------------------------------
# Public pipeline
# ---------------------------------------------------------------------------
async def generate_report(
    subject_id: str,
    *,
    title: str,
    requirements: str,
    out_dir: Path | None = None,
    ode_rhs: str = "",
    subject_context: str = "",
) -> dict:
    """Generate a complete report and publish it as one atomic run.

    ``out_dir`` is retired: when a legacy caller still passes it, it must name
    the server-canonical public reports directory for this subject, otherwise
    the call is rejected before any run or file exists.

    Returns the public projection (``report_id``/``status``/``chart_count``/
    ``markdown_tokens``/``url``/``path``/``verification_status``) plus the
    rendered Markdown for consumers that already display it.  Every failure
    after the run exists marks it ``failed`` and leaves no public URL.
    """
    ode_expression = _validate_ode_expression(ode_rhs)
    if not isinstance(title, str) or not title.strip():
        raise json_store.invalid_input("报告题目不能为空")
    if not isinstance(requirements, str):
        raise json_store.invalid_input("报告要求必须是文本")
    if not isinstance(subject_context, str):
        raise json_store.invalid_input("学情信息必须是文本")
    _validate_out_dir(out_dir, subject_id)

    lease = subject_operations.acquire_activity(subject_id, kind="report")
    try:
        run = report_store.create_report_run(subject_id, lease=lease)
    except BaseException:
        lease.release()
        raise
    try:
        context_block = (
            SUBJECT_CONTEXT_TEMPLATE.format(hint=subject_context) if subject_context else ""
        )
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
                f"通常是推理模型的思考 token 耗尽了 max_tokens（当前 {LLM_MAX_TOKENS}），请重试。",
                details={"subject_id": subject_id, "max_tokens": LLM_MAX_TOKENS},
            )

        placeholders = validated_chart_placeholders(markdown)
        charts: list[dict[str, Any]] = []
        for index, placeholder in enumerate(placeholders, start=1):
            name = f"chart_{index}.png"
            entry, _checks = await _produce_chart(run, name, placeholder.spec, ode_expression)
            charts.append(entry)
            # The replacement uses the *same* match object the recognizer found,
            # so zero-space / multi-space / multi-line placeholders are handled
            # identically and no placeholder survives into the document.
            markdown = markdown.replace(placeholder.raw, f"![chart {index}]({name})", 1)

        verification = chart_validation.verification_status(
            ode_expression, passed=bool(ode_expression and charts)
        )
        manifest, _relative_path = await _publish_rendered(
            run,
            markdown=markdown,
            charts=charts,
            verification_status=verification,
        )
        return _project(manifest, title=title, markdown=markdown, chart_count=len(charts))
    except BaseException:
        # Cancellation is a failure too: the run must not stay ``running`` and
        # no partial publication may exist.  ``completed`` is never downgraded.
        _fail_preserving_error(run)
        raise
    finally:
        lease.release()


async def review_report(
    subject_id: str,
    *,
    report_id: str | None = None,
    legacy_path: str | None = None,
    instructions: str = "",
    subject_context: str = "",
) -> dict:
    """Review one known report and publish a **new** run without touching it.

    The target is discovered by ``report_store.resolve_report_for_review``;
    the original Markdown/PDF/charts are only read after their manifest hashes
    match, and every retained chart is copied into the new run's own directory.
    The reviewed Markdown may not introduce new image references, and the new
    document is never labelled as numerically verified (only the original
    figures retain their provenance).
    """
    if not isinstance(instructions, str) or not isinstance(subject_context, str):
        raise json_store.invalid_input("核查说明必须是文本")
    try:
        source = report_store.resolve_report_for_review(
            subject_id, report_id=report_id or None, legacy_path=legacy_path or None
        )
    except SubjectStorageError as exc:
        # An escaping/symlinked legacy path is "not a known report", not a
        # storage failure the caller could act on; do not echo the path issue.
        raise subject_error(ErrorCode.ENTRY_NOT_FOUND, cause=exc) from exc
    original = await asyncio.to_thread(_source_markdown, source)

    reviewed_from = source.reviewed_from or source.report_id
    lease = subject_operations.acquire_activity(subject_id, kind="report-review")
    try:
        run = report_store.create_report_run(
            subject_id, reviewed_from=reviewed_from, lease=lease
        )
    except BaseException:
        lease.release()
        raise
    try:
        charts = await asyncio.to_thread(_copy_verified_charts_leased, source, run)
        context_block = (
            SUBJECT_CONTEXT_TEMPLATE.format(hint=subject_context) if subject_context else ""
        )
        extra = f"\n\n## 额外核查要求\n{instructions}" if instructions.strip() else ""
        markdown = (
            await _llm(
                REVIEW_PROMPT + extra + context_block + "\n\n## 原报告\n" + original,
                "你是课程报告核查助手。",
            )
        ).strip()
        if not markdown:
            raise LLMEmptyResponseError(
                "报告核查失败：模型返回空内容（推理 token 可能耗尽了输出预算），请重试。",
                details={"subject_id": subject_id},
            )
        manifest, _relative_path = await _publish_rendered(
            run,
            markdown=markdown,
            charts=charts,
            verification_status=report_store.VERIFICATION_NOT_REQUESTED,
        )
        title = next(
            (line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")),
            "报告核查",
        )
        return _project(manifest, title=title, markdown=markdown, chart_count=len(charts))
    except BaseException:
        _fail_preserving_error(run)
        raise
    finally:
        lease.release()

"""One image → one *text* description for the indexing path (P1-26, C09).

Why this module exists
----------------------
Indexing used to drop **every** image unless both the embedding model *and* the
main LLM were multimodal (see ``document_loader._load_image_nodes``). A KB on the
default text embedding therefore contained no trace of its figures at all, and
the user had no way to tell "this document has no images" from "we skipped
them". C09 replaces the all-or-nothing rule with:

    parser / standalone image asset
        → vision model chosen by the existing vision strategy
        → factual description / OCR
        → an ordinary **text** ``Document`` in the normal text-embedding index

Nothing here changes the embedding model, its dimension, or the index
signature, and no image vector is ever fabricated: the description is text, and
it is embedded by the same text path as the rest of the document.

Fixed interface (``plans/phase1/DATA_CONTRACTS.md`` appendix A)
--------------------------------------------------------------
``async describe_image_for_index(image_path, *, source_file, page=None,
location=None)`` returns the seven ``ImageDescription`` projection fields
``text / content_kind / source_file / page / location / asset_ref /
skip_reason``. A described image has non-empty ``text`` with an explicit
"来自图像" prefix and ``skip_reason=None``; a skipped image has ``text=""`` and
one of the five C09 skip reasons. The result is a frozen dataclass *and* a
``Mapping``, so both ``result.text`` and ``result["text"]`` work for callers.

Deliberate limits
-----------------
* ``source_file`` is the trusted original file name. Non-strings, separators,
  control characters and dot-only names are rejected instead of being ``str()``
  -ed into an opaque provenance value.
* ``page`` is only ever what the parser actually reported — this module never
  guesses a page from an asset file name and never converts between 0/1-based
  numbering.
* ``asset_ref`` is a constrained *relative* identifier. ``asset_ref_from_root``
  computes it against a real asset root and refuses anything that escapes that
  root; standalone image files simply use their file name.
* Failures never leak the provider's exception text: every provider-side
  failure is published as ``vision_failed``, while ``failure_kind`` keeps a
  stable internal diagnostic for tests and server logs.
* No caching, no parallel description, no batch OCR: one image, bounded
  attempts, bounded output, bounded wall clock.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from dataclasses import dataclass, fields
import io
import logging
import os
from pathlib import Path
import re
import stat as stat_module
from typing import Any

from deeptutor.services.config.provider_runtime import (
    resolve_llm_runtime_config,
    resolve_vision_runtime_config,
)
from deeptutor.services.llm.capabilities import supports_vision
from deeptutor.services.settings.vision_strategy import get_vision_strategy
from deeptutor.subjects.generation import validate_subject_response
from deeptutor.utils.document_images import (
    MAX_IMAGE_BYTES,
    MIN_IMAGE_BYTES,
    SUPPORTED_IMAGE_EXTENSIONS,
)

logger = logging.getLogger(__name__)

#: ``content_kind`` of a described image (``schemas.json`` ``ImageDescription``).
CONTENT_KIND = "image_description"

#: Every successful description starts with this marker so a retrieved chunk is
#: unambiguous about *not* being body text taken from the document.
DESCRIPTION_PREFIX = "【来自图像】"

#: The five C09 skip reasons. The first one is a *document*-level statement
#: ("the parser extracted no assets"), the other four count one skipped image.
SKIP_PARSER_NO_ASSETS = "parser_no_assets"
SKIP_VISION_UNAVAILABLE = "vision_unavailable"
SKIP_VISION_FAILED = "vision_failed"
SKIP_BUDGET = "budget"
SKIP_UNSUPPORTED_IMAGE = "unsupported_image"
SKIP_REASONS = (
    SKIP_PARSER_NO_ASSETS,
    SKIP_VISION_UNAVAILABLE,
    SKIP_VISION_FAILED,
    SKIP_BUDGET,
    SKIP_UNSUPPORTED_IMAGE,
)

#: Stable internal diagnostics for a failed description. The *public* skip
#: reason of all of them is ``vision_failed``; these names exist so a test (or a
#: server log line) can still tell an empty answer from a truncated one.
FAILURE_EMPTY = "empty"
FAILURE_TRUNCATED = "truncated"
FAILURE_REASONING_BUDGET = "reasoning_budget_exhausted"
FAILURE_TIMEOUT = "timeout"
FAILURE_PROVIDER = "provider_error"

#: Output budget for one description. The prompt asks for <180 words, so 512
#: tokens is generous while still bounding a runaway reasoning model.
DESCRIBE_MAX_TOKENS = 512
#: Wall-clock budget for one attempt. A hung vision endpoint must not hold the
#: whole indexing worker.
DESCRIBE_TIMEOUT_SECONDS = 120.0
#: At most main + dedicated: one optimistic attempt each, never a retry loop.
MAX_CANDIDATE_ATTEMPTS = 2

IMAGE_DESCRIPTION_SYSTEM_PROMPT = (
    "You describe images for a retrieval-augmented knowledge base. "
    "Be factual, concise, and include any visible text, labels, diagrams, "
    "tables, logos, or important visual relationships. Do not invent details."
)

IMAGE_DESCRIPTION_PROMPT = (
    "Describe this image so that a text-only answer generator can understand "
    "and cite it later. Include visible text/OCR if present, the main subject, "
    "and any educational or technical meaning. Keep the answer under 180 words."
)

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
}

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

#: ``source_file`` stays a plain file name: no separators, no control
#: characters, no "."/".." (mirrors the ``ImageDescription`` JSON Schema
#: pattern so the projection cannot hold a path).
_FORBIDDEN_SOURCE_CHARS = re.compile(r"[/\\\x00-\x1f\x7f]")


@dataclass(frozen=True, eq=False)
class ImageDescription(Mapping[str, Any]):
    """The fixed ``ImageDescription`` projection.

    Frozen *and* mapping-like: ``result.text``, ``result["text"]``,
    ``dict(result)`` and ``dataclasses.asdict(result)`` all yield the same
    seven fields, and equality works against another instance or a plain dict.
    """

    text: str
    content_kind: str
    source_file: str
    page: int | None
    location: str | None
    asset_ref: str
    skip_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """The projection as a plain dict (schema-shaped)."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(fields(self))

    @property
    def skipped(self) -> bool:
        return self.skip_reason is not None


def _described(
    *,
    text: str,
    source_file: str,
    asset_ref: str,
    page: int | None,
    location: str | None,
) -> ImageDescription:
    return ImageDescription(
        text=text,
        content_kind=CONTENT_KIND,
        source_file=source_file,
        page=page,
        location=location,
        asset_ref=asset_ref,
        skip_reason=None,
    )


def _skipped(
    *,
    reason: str,
    source_file: str,
    asset_ref: str,
    page: int | None,
    location: str | None,
) -> ImageDescription:
    return ImageDescription(
        text="",
        content_kind=CONTENT_KIND,
        source_file=source_file,
        page=page,
        location=location,
        asset_ref=asset_ref,
        skip_reason=reason,
    )


# ---------------------------------------------------------------------------
# Argument validation — reject caller errors instead of coercing them
# ---------------------------------------------------------------------------
def _validated_source_file(source_file: Any) -> str:
    if not isinstance(source_file, str):
        raise TypeError(
            f"source_file must be a string, got {type(source_file).__name__}"
        )
    name = source_file.strip()
    if not name or name in (".", ".."):
        raise ValueError("source_file must be a non-empty file name")
    if _FORBIDDEN_SOURCE_CHARS.search(name):
        raise ValueError(
            "source_file must be a bare file name (no separators or control characters)"
        )
    return name


def _validated_page(page: Any) -> int | None:
    if page is None:
        return None
    if isinstance(page, bool) or not isinstance(page, int):
        raise TypeError(
            f"page must be an int or None, got {type(page).__name__}"
        )
    if page < 0:
        raise ValueError("page must not be negative")
    return page


def _validated_location(location: Any) -> str | None:
    if location is None:
        return None
    if not isinstance(location, str):
        raise TypeError(
            f"location must be a string or None, got {type(location).__name__}"
        )
    text = location.strip()
    if not text:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError("location must not contain control characters")
    return text


def _validated_asset_ref(asset_ref: Any) -> str:
    if not isinstance(asset_ref, str):
        raise TypeError(
            f"asset_ref must be a string, got {type(asset_ref).__name__}"
        )
    ref = asset_ref.strip()
    if not ref:
        raise ValueError("asset_ref must not be empty")
    if "\\" in ref or ref.startswith("/") or re.match(r"^[A-Za-z]:", ref):
        raise ValueError("asset_ref must be a relative identifier, not a path")
    parts = [part for part in ref.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("asset_ref must not escape its asset root")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in ref):
        raise ValueError("asset_ref must not contain control characters")
    return "/".join(parts)


def asset_ref_from_root(image_path: str | os.PathLike[str], asset_root: str | os.PathLike[str]) -> str:
    """The real relative asset id of ``image_path`` under ``asset_root``.

    The parser writes extracted figures into a per-document asset directory, so
    the identifier a citation needs is the path *inside* that directory
    (``images/figure-1.png``) — never the cache path and never a page number
    guessed from the file name. Anything that does not live inside the root
    (``..``, an absolute path elsewhere, a symlink) is rejected with
    ``ValueError`` so a caller cannot publish an escaping reference.
    """
    root = Path(os.path.normpath(str(Path(asset_root).expanduser())))
    candidate = Path(os.path.normpath(str(Path(image_path).expanduser())))
    root_text = str(root)
    candidate_text = str(candidate)
    if candidate_text == root_text or not candidate_text.startswith(root_text + os.sep):
        raise ValueError("image does not live inside the asset root")
    if os.path.islink(candidate_text):
        # The reference itself must be the regular file the caller enumerated,
        # never a link that redirects the later read somewhere else.
        raise ValueError("image does not live inside the asset root")
    relative = candidate_text[len(root_text) + 1 :]
    return _validated_asset_ref(Path(relative).as_posix())


def confined_image_root(asset_root: str | os.PathLike[str]) -> Path | None:
    """The asset root when it can be enumerated safely, else ``None``.

    Every component of the path must be a **real** directory: a symlinked root
    (or a symlinked parent component) would silently hand us a tree that belongs
    to somebody else, so it is refused before any ``is_dir``/``os.walk``/read.
    An unusable root must be reported as *unverified* by the caller — never
    enumerated "around" the link to keep the counts up.
    """
    raw = Path(str(asset_root).strip() or ".")
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    parts = raw.parts
    if not parts:
        return None
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except OSError:
            return None
        if stat_module.S_ISLNK(info.st_mode) or not stat_module.S_ISDIR(info.st_mode):
            return None
    return raw


def is_regular_file_leaf(path: str | os.PathLike[str]) -> bool:
    """True only for a real regular file: not a symlink, not a special leaf."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat_module.S_ISREG(info.st_mode)


def standalone_asset_ref(image_path: str | os.PathLike[str]) -> str:
    """The asset id of a standalone uploaded image: its own file name."""
    return _validated_asset_ref(Path(image_path).name)


# ---------------------------------------------------------------------------
# Reading and validating the image bytes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ImageInspection:
    """Outcome of the shared single-image gate: bytes + mime, or a skip reason."""

    data: bytes | None = None
    mime_type: str = ""
    skip_reason: str | None = None


def inspect_image_file(path: str | os.PathLike[str]) -> ImageInspection:
    """Read at most ``MAX_IMAGE_BYTES`` after stat-ing, then verify the format.

    Order matters: the size decision is made from ``lstat`` *before* any byte is
    read, the read itself is capped, and the leaf is opened ``O_NOFOLLOW`` so a
    symlink swapped in after the ``lstat`` cannot redirect the read.
    """
    path = Path(path)
    if confined_image_root(path.parent) is None:
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    try:
        info = os.lstat(path)
    except OSError:
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    if stat_module.S_ISLNK(info.st_mode) or not stat_module.S_ISREG(info.st_mode):
        # Symlinked or non-regular leaves are never followed into the read.
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    if info.st_size < MIN_IMAGE_BYTES or info.st_size > MAX_IMAGE_BYTES:
        return ImageInspection(skip_reason=SKIP_BUDGET)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        handle = os.open(path, flags)
    except OSError:
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    try:
        stat_result = os.fstat(handle)
        if not stat_module.S_ISREG(stat_result.st_mode):
            return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
        size = stat_result.st_size
        if size < MIN_IMAGE_BYTES or size > MAX_IMAGE_BYTES:
            return ImageInspection(skip_reason=SKIP_BUDGET)
        chunks: list[bytes] = []
        remaining = MAX_IMAGE_BYTES + 1
        while remaining > 0:
            chunk = os.read(handle, min(remaining, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    finally:
        os.close(handle)

    data = b"".join(chunks)
    if len(data) != size:
        # Short read / grew past the cap between stat and read: not a usable
        # image, and never silently truncated into the model request.
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    mime_type = _detected_mime_type(data, path)
    if mime_type is None:
        return ImageInspection(skip_reason=SKIP_UNSUPPORTED_IMAGE)
    return ImageInspection(data=data, mime_type=mime_type)


def _detected_mime_type(data: bytes, path: Path) -> str | None:
    """The raster MIME type the *bytes* really are, or ``None`` if unsupported.

    Content wins over the extension: a ``.png`` holding JPEG bytes is accepted
    as JPEG, while a vector/unsupported payload keeps the file's extension from
    smuggling it in. Pillow is the validator when present; without it the
    declared extension is the best available evidence.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a hard dependency here
        Image = None  # type: ignore[assignment]

    if Image is None:  # pragma: no cover - defensive fallback
        extension = path.suffix.lower()
        if extension in SUPPORTED_IMAGE_EXTENSIONS:
            return _MIME_BY_EXT.get(extension)
        return None

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.verify()
    except Exception:
        return None
    return _MIME_BY_FORMAT.get(image_format)


# ---------------------------------------------------------------------------
# Vision selection (existing ``vision_strategy`` semantics, unchanged schema)
# ---------------------------------------------------------------------------
def _safe_strategy_name() -> str:
    try:
        return str(get_vision_strategy())
    except Exception:  # pragma: no cover - defensive, mirrors _candidate_configs
        return "unknown"


def _usable(config: Any) -> bool:
    return config is not None and bool(getattr(config, "model", ""))


def _resolve_config(resolver: Any, label: str) -> Any:
    """Resolve one candidate config, never letting its failure escape.

    A broken main-model catalog entry must not turn into a failed image: the
    caller simply loses that candidate (and still has the dedicated model).
    """
    try:
        return resolver()
    except Exception as exc:
        logger.info(
            "Vision candidate %s could not be resolved (%s); continuing without it",
            label,
            type(exc).__name__,
        )
        return None


def _candidate_configs() -> list[tuple[str, Any]]:
    """Ordered, bounded vision candidates for the *current* strategy.

    ``auto`` uses the capability-allowed main model and keeps a configured
    dedicated model for one optimistic fallback; ``prefer_dedicated`` and
    ``dedicated_only`` are (as in the settings module) the same policy and never
    fall back to main. Each resolution is individually guarded, so an
    unresolvable main model still leaves the dedicated model usable.
    """
    try:
        strategy = get_vision_strategy()
    except Exception as exc:
        logger.info(
            "Vision strategy could not be read (%s); using the default policy",
            type(exc).__name__,
        )
        strategy = "auto"
    dedicated = _resolve_config(resolve_vision_runtime_config, "dedicated")
    if strategy in ("prefer_dedicated", "dedicated_only"):
        return [("dedicated", dedicated)] if _usable(dedicated) else []

    main = _resolve_config(resolve_llm_runtime_config, "main")
    candidates: list[tuple[str, Any]] = []
    if _usable(main):
        try:
            main_capable = bool(
                supports_vision(getattr(main, "binding", ""), getattr(main, "model", None))
            )
        except Exception as exc:
            logger.info(
                "Vision capability probe failed for the main model (%s); "
                "preferring the dedicated model",
                type(exc).__name__,
            )
            main_capable = False
        if main_capable:
            candidates.append(("main", main))
    if _usable(dedicated):
        candidates.append(("dedicated", dedicated))
    return candidates[:MAX_CANDIDATE_ATTEMPTS]


def failure_kind(exc: BaseException) -> str:
    """Stable internal diagnostic for one failed description attempt.

    Public results only ever say ``vision_failed``; this mapping keeps the
    empty / truncated / budget / timeout / provider cases distinguishable for
    tests and server logs without exposing the exception text.
    """
    from deeptutor.services.llm.exceptions import (
        LLMEmptyResponseError,
        LLMReasoningBudgetExhausted,
    )
    from deeptutor.subjects.errors import SubjectOutputTruncated

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return FAILURE_TIMEOUT
    if isinstance(exc, SubjectOutputTruncated):
        return FAILURE_TRUNCATED
    if isinstance(exc, LLMReasoningBudgetExhausted):
        return FAILURE_REASONING_BUDGET
    if isinstance(exc, LLMEmptyResponseError):
        return FAILURE_EMPTY
    return FAILURE_PROVIDER


def image_payload(inspection: ImageInspection, *, mime_type: str | None = None) -> dict[str, str]:
    """Encode already-inspected bytes once, for either image path."""
    data = inspection.data or b""
    resolved_mime = mime_type or inspection.mime_type or "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "base64": encoded,
        "data_uri": f"data:{resolved_mime};base64,{encoded}",
        "mime_type": resolved_mime,
    }


async def describe_image_text(
    config: Any,
    *,
    image_base64: str,
    mime_type: str,
    image_filename: str,
) -> str:
    """One **bounded, strict** image-description attempt; raises when it fails.

    Both image paths (the default text description and the legacy multimodal
    ``ImageNode`` path) go through here so they share one output budget, one
    timeout and the S02 empty/truncation contract. ``strict_image_attempt``
    makes the call exactly one wire request carrying the image: no hidden
    retries, and no "answer without the image" degradation that would be
    promoted to an OCR result.
    """
    from deeptutor.services.llm import factory

    response = await asyncio.wait_for(
        factory.complete_response(
            prompt=IMAGE_DESCRIPTION_PROMPT,
            system_prompt=IMAGE_DESCRIPTION_SYSTEM_PROMPT,
            model=getattr(config, "model", None),
            api_key=getattr(config, "api_key", "") or None,
            base_url=getattr(config, "base_url", None),
            api_version=getattr(config, "api_version", None),
            binding=getattr(config, "binding", None),
            extra_headers=getattr(config, "extra_headers", None) or None,
            max_tokens=DESCRIBE_MAX_TOKENS,
            image_data=image_base64,
            image_mime_type=mime_type,
            # The *source document's* name, never the cache asset path.
            image_filename=image_filename,
            strict_image_attempt=True,
        ),
        timeout=DESCRIBE_TIMEOUT_SECONDS,
    )
    return validate_subject_response(response, max_tokens=DESCRIBE_MAX_TOKENS)


def _header(source_file: str, page: int | None, location: str | None) -> str:
    header = f"{DESCRIPTION_PREFIX}{source_file}"
    if page is not None:
        header += f"（第 {page} 页）"
    if location:
        header += f"（位置：{location}）"
    return header


async def describe_image_for_index(
    image_path: str | os.PathLike[str],
    *,
    source_file: str,
    page: int | None = None,
    location: str | None = None,
    asset_ref: str | None = None,
) -> ImageDescription:
    """Describe one image for the text index, or name why it was skipped.

    ``asset_ref`` is the constrained relative asset identifier the loader
    computed for a parser asset (see :func:`asset_ref_from_root`); when it is
    omitted the image is a standalone file and its own name is used.

    Cancellation always propagates; every other outcome is either a described
    image or a named skip.
    """
    if not isinstance(image_path, (str, os.PathLike)):
        raise TypeError(
            f"image_path must be a path, got {type(image_path).__name__}"
        )
    source = _validated_source_file(source_file)
    page_value = _validated_page(page)
    location_value = _validated_location(location)
    path = Path(image_path)
    ref = (
        _validated_asset_ref(asset_ref)
        if asset_ref is not None
        else standalone_asset_ref(path)
    )

    inspection = await asyncio.to_thread(inspect_image_file, path)
    if inspection.skip_reason is not None:
        logger.info(
            "Skipped image for indexing: asset=%s reason=%s", ref, inspection.skip_reason
        )
        return _skipped(
            reason=inspection.skip_reason,
            source_file=source,
            asset_ref=ref,
            page=page_value,
            location=location_value,
        )

    candidates = _candidate_configs()
    if not candidates:
        logger.warning(
            "Skipped image for indexing: no vision model is available for "
            "asset=%s (strategy=%s)",
            ref,
            _safe_strategy_name(),
        )
        return _skipped(
            reason=SKIP_VISION_UNAVAILABLE,
            source_file=source,
            asset_ref=ref,
            page=page_value,
            location=location_value,
        )

    payload = image_payload(inspection)
    last_kind = FAILURE_PROVIDER
    for label, config in candidates[:MAX_CANDIDATE_ATTEMPTS]:
        try:
            body = await describe_image_text(
                config,
                image_base64=payload["base64"],
                mime_type=payload["mime_type"],
                image_filename=source,
            )
        except Exception as exc:
            # ``asyncio.CancelledError`` is a BaseException in 3.12 and is not
            # caught here, so a cancelled indexing task still cancels.
            last_kind = failure_kind(exc)
            logger.warning(
                "Image description failed (candidate=%s binding=%s model=%s reason=%s)",
                label,
                getattr(config, "binding", ""),
                getattr(config, "model", ""),
                last_kind,
            )
            continue
        text = body.strip()
        if not text:
            last_kind = FAILURE_EMPTY
            continue
        return _described(
            text=f"{_header(source, page_value, location_value)}\n{text}",
            source_file=source,
            asset_ref=ref,
            page=page_value,
            location=location_value,
        )

    logger.warning(
        "Skipped image for indexing: every vision candidate failed for asset=%s "
        "(reason=%s, attempts=%s)",
        ref,
        last_kind,
        len(candidates[:MAX_CANDIDATE_ATTEMPTS]),
    )
    return _skipped(
        reason=SKIP_VISION_FAILED,
        source_file=source,
        asset_ref=ref,
        page=page_value,
        location=location_value,
    )


__all__ = [
    "CONTENT_KIND",
    "DESCRIPTION_PREFIX",
    "DESCRIBE_MAX_TOKENS",
    "DESCRIBE_TIMEOUT_SECONDS",
    "FAILURE_EMPTY",
    "FAILURE_PROVIDER",
    "FAILURE_REASONING_BUDGET",
    "FAILURE_TIMEOUT",
    "FAILURE_TRUNCATED",
    "IMAGE_DESCRIPTION_PROMPT",
    "IMAGE_DESCRIPTION_SYSTEM_PROMPT",
    "ImageDescription",
    "is_regular_file_leaf",
    "inspect_image_file",
    "image_payload",
    "describe_image_text",
    "confined_image_root",
    "ImageInspection",
    "MAX_CANDIDATE_ATTEMPTS",
    "SKIP_BUDGET",
    "SKIP_PARSER_NO_ASSETS",
    "SKIP_REASONS",
    "SKIP_UNSUPPORTED_IMAGE",
    "SKIP_VISION_FAILED",
    "SKIP_VISION_UNAVAILABLE",
    "asset_ref_from_root",
    "describe_image_for_index",
    "failure_kind",
    "standalone_asset_ref",
]

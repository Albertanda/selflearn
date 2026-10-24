"""Small, dependency-free helpers for durable service files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

#: JSON documents the atomic writer accepts: the existing object form **and** the
#: top-level array form the subject data files use (``index.json``,
#: ``wrong_book.json``, ``exam_points.json``, ``knowledge.json``,
#: ``knowledge_points.json``).
JSONDocument = dict[str, Any] | list[Any]


def atomic_write_json(path: Path, payload: JSONDocument) -> None:
    """Write *payload* (JSON object or array) as UTF-8 JSON.

    Durability contract:

    * the temporary file lives in the **same directory** as the target, so the
      final step is a same-filesystem atomic replace;
    * ``flush`` + ``fsync`` happen before the replace, and a failing ``fsync``
      propagates: a write we cannot prove durable must not be reported as
      persisted (the previous target bytes stay in place);
    * ``allow_nan=False`` rejects ``NaN``/``Infinity`` — they are not valid JSON
      and would otherwise flow into templates as a bogus mastery value;
    * any failure before the replace leaves the old target untouched and removes
      the temporary file.

    A failure *after* a successful replace (e.g. the caller raising later) has
    already published the new bytes; that is not a reason to expect the old ones.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with a same-directory atomic replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["JSONDocument", "atomic_write_json", "atomic_write_text"]

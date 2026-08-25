"""Vision routing strategy (M8): how image-understanding tools pick a model.

    strategy:
      auto              — probe the main LLM's multimodal capability; use it
                           when supported, otherwise the dedicated vision model
                           (dedicated model as fallback).
      prefer_dedicated  — always use the dedicated vision model.
      dedicated_only    — same as prefer_dedicated (alias, kept for clarity).

Stored in ``data/user/settings/vision_strategy.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.path_service import get_path_service

DEFAULTS = {"strategy": "auto"}
VALID = ("auto", "prefer_dedicated", "dedicated_only")


def _path() -> Path:
    return get_path_service().get_settings_file("vision_strategy")


def get_vision_strategy() -> str:
    path = _path()
    if not path.exists():
        return DEFAULTS["strategy"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULTS["strategy"]
    strategy = str(data.get("strategy", DEFAULTS["strategy"]))
    return strategy if strategy in VALID else DEFAULTS["strategy"]


def save_vision_strategy(strategy: str) -> str:
    if strategy not in VALID:
        strategy = DEFAULTS["strategy"]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"strategy": strategy}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return strategy

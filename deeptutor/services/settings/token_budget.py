"""Token-saver settings (M5+): context-compression switch + ratio.

File: ``data/user/settings/token_budget.json``

    enabled       — true (default): three-layer injection + bounded history
                    (truncate/compress early turns aggressively).
                    false: send the FULL history + injection + profile to the
                    model, and only start compressing once history reaches
                    ``context_ratio`` of the model's context window.
    context_ratio — fraction of the model context window that triggers
                    compression when ``enabled`` is false (default 0.7).
"""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.path_service import get_path_service

DEFAULTS = {"enabled": True, "context_ratio": 0.7}
MIN_RATIO = 0.1
MAX_RATIO = 0.95


def _path() -> Path:
    return get_path_service().get_settings_file("token_budget")


def get_token_budget_settings() -> dict:
    path = _path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    out = dict(DEFAULTS)
    if isinstance(data, dict):
        if isinstance(data.get("enabled"), bool):
            out["enabled"] = data["enabled"]
        ratio = data.get("context_ratio")
        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
            out["context_ratio"] = max(MIN_RATIO, min(MAX_RATIO, float(ratio)))
    return out


def save_token_budget_settings(*, enabled: bool, context_ratio: float) -> dict:
    ratio = max(MIN_RATIO, min(MAX_RATIO, float(context_ratio)))
    payload = {"enabled": bool(enabled), "context_ratio": round(ratio, 3)}
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

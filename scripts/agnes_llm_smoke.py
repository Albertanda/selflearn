#!/usr/bin/env python3
"""Explicit, bounded Agnes chat smoke.

This is not part of automated tests.  It reads the existing Agnes profile from
the local catalog, makes at most three synthetic chat requests with
``max_tokens <= 64`` and never falls back to another provider.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Callable
from urllib import error, request
from urllib.parse import urlsplit

TARGET_PROFILE_ID = "llm-profile-1792841570392"
TARGET_MODEL_ID = "llm-model-51f6b172-f944-40e7-b251-279b227757c4"
TARGET_HOST = "apihub.agnes-ai.com"
TARGET_MODEL = "agnes-3.0-flash"
SYNTHETIC_PROMPT = "Reply with the single word OK. Synthetic CP-R1 smoke; no personal data."
MAX_CALLS = 3
MAX_TOKENS = 64
TIMEOUT_SECONDS = 45
MAX_RESPONSE_BYTES = 1024 * 1024


class SmokeError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _profile(catalog: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profiles = (
        catalog.get("services", {}).get("llm", {}).get("profiles", [])
        if isinstance(catalog.get("services"), dict)
        else []
    )
    profile = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
    if profile is None:
        raise SmokeError("The exact Agnes profile is not configured.")
    return profile


def _model(profile: dict[str, Any], model_id: str) -> dict[str, Any]:
    model = next(
        (m for m in (profile.get("models") or []) if isinstance(m, dict) and m.get("id") == model_id),
        None,
    )
    if model is None:
        raise SmokeError("The exact Agnes model is not configured.")
    return model


def validate_target(catalog: dict[str, Any], profile_id: str, model_id: str) -> dict[str, Any]:
    profile = _profile(catalog, profile_id)
    if profile.get("binding") not in {"custom", "vllm"}:
        raise SmokeError("The selected profile is not an Agnes custom/vLLM connection.")
    base_url = str(profile.get("base_url") or "").rstrip("/")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise SmokeError("The Agnes endpoint is invalid.") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != TARGET_HOST
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/v1"
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in base_url)
    ):
        raise SmokeError("The selected endpoint is not the expected HTTPS Agnes host/path.")
    model = _model(profile, model_id)
    if model.get("model") != TARGET_MODEL:
        raise SmokeError("The selected model is not agnes-3.0-flash.")
    if not str(profile.get("api_key") or ""):
        raise SmokeError("The Agnes credential is missing.")
    return profile


def _classify(status: int | None, exc: BaseException | None) -> str:
    if isinstance(exc, (SmokeError, json.JSONDecodeError, UnicodeDecodeError)):
        return "invalid_response"
    if isinstance(exc, TimeoutError) or (isinstance(exc, error.URLError) and isinstance(exc.reason, TimeoutError)):
        return "timeout"
    if exc is not None:
        return "network"
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limited"
    if status is not None and 400 <= status < 500:
        return "http_4xx"
    if status is not None and status >= 500:
        return "http_5xx"
    return "unknown"


def _call(opener, profile: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    url = str(profile.get("base_url") or "").rstrip("/") + "/chat/completions"
    payload = {
        "model": model.get("model"),
        "messages": [{"role": "user", "content": SYNTHETIC_PROMPT}],
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", "Bearer " + str(profile.get("api_key") or ""))
    started = time.monotonic()
    status: int | None = None
    exc: BaseException | None = None
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SmokeError("Agnes response exceeded the smoke size limit.")
            body = raw.decode("utf-8")
            parsed = json.loads(body)
            choices = parsed.get("choices") if isinstance(parsed, dict) else None
            if not isinstance(choices, list) or not choices:
                raise SmokeError("Malformed Agnes response.")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                )
            if not isinstance(content, str) or not content.strip():
                raise SmokeError("Agnes response contained no assistant text.")
    except error.HTTPError as caught:
        status = caught.code
        exc = None if caught.code in (401, 403, 429) or caught.code >= 400 else caught
    except Exception as caught:  # noqa: BLE001 - classify and report only
        exc = caught
    elapsed_ms = round((time.monotonic() - started) * 1000)
    ok = status == 200 and exc is None
    return {
        "status": "success" if ok else "failed",
        "http_status": status,
        "model": model.get("model"),
        "duration_ms": elapsed_ms,
        "error_category": None if ok else _classify(status, exc),
    }


def run_smoke(
    catalog: dict[str, Any],
    *,
    profile_id: str,
    model_id: str,
    calls: int = 1,
    opener_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if calls < 1 or calls > MAX_CALLS:
        raise SmokeError("Smoke calls must be between 1 and 3.")
    profile = validate_target(catalog, profile_id, model_id)
    model = _model(profile, model_id)
    opener = (opener_factory or (lambda: request.build_opener(_NoRedirect())))()
    results = [_call(opener, profile, model) for _ in range(calls)]
    return {
        "status": "success" if all(item["status"] == "success" for item in results) else "failed",
        "profile_id": profile_id,
        "model_id": model_id,
        "model": model.get("model"),
        "calls": len(results),
        "limits": {"max_calls": MAX_CALLS, "max_tokens": MAX_TOKENS, "timeout_seconds": TIMEOUT_SECONDS},
        "results": results,
        "default_fallback": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-file", type=Path, default=Path("data/user/settings/model_catalog.json"))
    parser.add_argument("--profile-id", default=TARGET_PROFILE_ID)
    parser.add_argument("--model-id", default=TARGET_MODEL_ID)
    parser.add_argument("--calls", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        catalog = json.loads(args.catalog_file.read_text(encoding="utf-8"))
        result = run_smoke(
            catalog,
            profile_id=args.profile_id,
            model_id=args.model_id,
            calls=args.calls,
        )
    except (SmokeError, OSError, json.JSONDecodeError) as exc:
        result = {
            "status": "blocked",
            "profile_id": args.profile_id,
            "model_id": args.model_id,
            "calls": 0,
            "limits": {"max_calls": MAX_CALLS, "max_tokens": MAX_TOKENS, "timeout_seconds": TIMEOUT_SECONDS},
            "results": [],
            "default_fallback": False,
            "error": str(exc),
        }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())

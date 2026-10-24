#!/usr/bin/env python3
"""Migrate the exact Agnes profile to a named custom provider.

Dry-run is the default.  ``--apply`` only sends the transformed catalog through
the running local management API; it never writes the real catalog file from a
standalone process.  Secrets are read from the local catalog only after an
exact profile/URL/model match and are never printed or logged.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from ipaddress import ip_address
import json
from pathlib import Path
import sys
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from deeptutor.services.config.custom_providers import (
    CustomProviderValidationError,
    validate_custom_provider_catalog,
)

TARGET_PROFILE_ID = "llm-profile-1792841570392"
TARGET_MODEL_ID = "llm-model-51f6b172-f944-40e7-b251-279b227757c4"
TARGET_BASE_URL = "https://apihub.agnes-ai.com/v1"
TARGET_MODEL = "agnes-3.0-flash"
TARGET_NAME = "Agnes"
DEFINITION_ID = f"cp_{uuid5(NAMESPACE_URL, 'cp-r1:agnes:' + TARGET_PROFILE_ID)}"
DEFINITION = {
    "id": DEFINITION_ID,
    "service": "llm",
    "binding": "custom",
    "name": TARGET_NAME,
    "icon": {"kind": "builtin", "value": "flask"},
}
VLLM_SLOT_ID = "llm-profile-vllm-local"


class AgnesMigrationError(RuntimeError):
    pass


class RevisionConflict(AgnesMigrationError):
    def __init__(self, current_revision: str | None = None):
        super().__init__("The saved catalog changed; re-read required.")
        self.current_revision = current_revision


def _llm(catalog: dict[str, Any]) -> dict[str, Any]:
    services = catalog.get("services") if isinstance(catalog.get("services"), dict) else {}
    llm = services.get("llm") if isinstance(services.get("llm"), dict) else {}
    return llm


def _profiles(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (_llm(catalog).get("profiles") or []) if isinstance(p, dict)]


def _target(catalog: dict[str, Any]) -> dict[str, Any]:
    profile = next((p for p in _profiles(catalog) if p.get("id") == TARGET_PROFILE_ID), None)
    if profile is None:
        raise AgnesMigrationError("Exact Agnes profile was not found; refusing to migrate.")
    if profile.get("binding") not in {"vllm", "custom"}:
        raise AgnesMigrationError("Agnes profile protocol changed; refusing to migrate.")
    models = [m for m in (profile.get("models") or []) if isinstance(m, dict)]
    if not any(m.get("id") == TARGET_MODEL_ID and m.get("model") == TARGET_MODEL for m in models):
        raise AgnesMigrationError("Exact Agnes model identity did not match; refusing to migrate.")
    if str(profile.get("base_url") or "").rstrip("/") != TARGET_BASE_URL.rstrip("/"):
        raise AgnesMigrationError("Agnes endpoint did not match the expected origin; refusing to migrate.")
    return profile


def _clean_vllm_profiles(catalog: dict[str, Any], *, exclude_id: str | None = None) -> list[dict[str, Any]]:
    return [
        p
        for p in _profiles(catalog)
        if p.get("id") != exclude_id and p.get("binding") == "vllm"
    ]


def _has_clean_slot(catalog: dict[str, Any], *, exclude_id: str | None = None) -> bool:
    return any(
        not str(p.get("base_url") or "").strip()
        and not str(p.get("api_key") or "").strip()
        and not (p.get("models") or [])
        for p in _clean_vllm_profiles(catalog, exclude_id=exclude_id)
    )


def _new_slot_id(catalog: dict[str, Any]) -> str:
    used = {p.get("id") for p in _profiles(catalog)}
    if VLLM_SLOT_ID not in used:
        return VLLM_SLOT_ID
    for index in range(2, 100):
        candidate = f"{VLLM_SLOT_ID}-{index}"
        if candidate not in used:
            return candidate
    raise AgnesMigrationError("Could not allocate a stable empty vLLM slot id.")


def _definition(catalog: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    definitions = catalog.get("custom_providers") if isinstance(catalog.get("custom_providers"), list) else []
    existing = next(
        (
            item
            for item in definitions
            if isinstance(item, dict)
            and item.get("service") == "llm"
            and item.get("binding") == "custom"
            and str(item.get("name") or "").strip().casefold() == "agnes"
        ),
        None,
    )
    if existing is not None:
        return deepcopy(existing), False
    return deepcopy(DEFINITION), True


def migration_plan(catalog: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized dry-run/apply plan for the exact target."""

    working = deepcopy(catalog)
    profile = _target(working)
    already = (
        profile.get("binding") == "custom"
        and profile.get("name") == TARGET_NAME
        and isinstance(profile.get("custom_provider_id"), str)
        and any(
            item.get("id") == profile.get("custom_provider_id") and item.get("name") == TARGET_NAME
            for item in (working.get("custom_providers") or [])
            if isinstance(item, dict)
        )
    )
    definition, created = _definition(working)
    add_slot = not _has_clean_slot(working, exclude_id=TARGET_PROFILE_ID)
    no_op = bool(already and not add_slot)

    changes: list[dict[str, Any]] = []
    if profile.get("name") != TARGET_NAME:
        changes.append({"profile_id": TARGET_PROFILE_ID, "field": "name", "from": profile.get("name"), "to": TARGET_NAME})
    if profile.get("binding") != "custom":
        changes.append({"profile_id": TARGET_PROFILE_ID, "field": "binding", "from": profile.get("binding"), "to": "custom"})
    if profile.get("custom_provider_id") != definition["id"]:
        changes.append(
            {
                "profile_id": TARGET_PROFILE_ID,
                "field": "custom_provider_id",
                "from": profile.get("custom_provider_id"),
                "to": definition["id"],
            }
        )
    if created and not any(
        isinstance(item, dict) and item.get("id") == definition["id"]
        for item in (working.get("custom_providers") or [])
    ):
        changes.append({"custom_provider": "created", "id": definition["id"], "name": TARGET_NAME})
    if add_slot:
        changes.append({"vllm_empty_slot": "created", "id": _new_slot_id(working)})

    # Reuse an existing Agnes definition even if its icon was edited by the user.
    if already:
        definition = next(
            item for item in (working.get("custom_providers") or [])
            if isinstance(item, dict) and item.get("id") == profile.get("custom_provider_id")
        )

    if not no_op:
        definitions = [
            item for item in (working.get("custom_providers") or []) if isinstance(item, dict)
        ]
        if not any(item.get("id") == definition["id"] for item in definitions):
            definitions.append(deepcopy(definition))
        working["custom_providers"] = definitions
        target = next(p for p in _profiles(working) if p.get("id") == TARGET_PROFILE_ID)
        target["name"] = TARGET_NAME
        target["binding"] = "custom"
        target["custom_provider_id"] = definition["id"]
        if add_slot:
            slot_id = _new_slot_id(working)
            working["services"]["llm"]["profiles"].append(
                {
                    "id": slot_id,
                    "name": "vLLM/Local",
                    "binding": "vllm",
                    "base_url": "",
                    "api_key": "",
                    "api_version": "",
                    "extra_headers": {},
                    "models": [],
                }
            )
        try:
            validate_custom_provider_catalog(working, catalog)
        except CustomProviderValidationError as exc:
            raise AgnesMigrationError(f"Migrated catalog failed validation: {exc}") from exc

    return {
        "source_profile_id": TARGET_PROFILE_ID,
        "source_model_id": TARGET_MODEL_ID,
        "definition_id": definition["id"],
        "no_op": no_op,
        "created_definition": bool(created and not already),
        "added_vllm_slot": bool(add_slot),
        "changes": changes,
        "catalog": working,
    }


def local_credentials(catalog_path: Path) -> dict[str, Any]:
    """Read only the exact target's credentials for the explicit apply request."""

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    profile = _target(catalog)
    return {
        "api_key": str(profile.get("api_key") or ""),
        "extra_headers": deepcopy(profile.get("extra_headers") or {}),
    }


def _attach_credentials(catalog: dict[str, Any], credentials: dict[str, Any]) -> None:
    profile = _target(catalog)
    if not credentials.get("api_key"):
        raise AgnesMigrationError("The local Agnes credential is missing; refusing to apply.")
    profile["api_key"] = credentials["api_key"]
    profile["extra_headers"] = deepcopy(credentials.get("extra_headers") or {})


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    opener = request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        return exc.code, parsed


def fetch_catalog(api_url: str) -> tuple[dict[str, Any], str]:
    _validate_management_url(api_url)
    status, payload = _http_json("GET", api_url.rstrip("/") + "/api/v1/settings/catalog")
    if status in (401, 403):
        raise AgnesMigrationError("Management API authentication failed; migration left untouched.")
    if status != 200 or not isinstance(payload.get("catalog"), dict) or not payload.get("revision"):
        raise AgnesMigrationError(f"Could not read the management catalog (HTTP {status}).")
    return payload["catalog"], str(payload["revision"])


def apply_via_api(api_url: str, catalog_path: Path, *, retries: int = 2) -> dict[str, Any]:
    _validate_management_url(api_url)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        catalog, revision = fetch_catalog(api_url)
        plan = migration_plan(catalog)
        if plan["no_op"]:
            return {**plan, "applied": False, "attempts": attempt + 1}
        # A 409 may mean the user just rotated the key or removed a header.
        # Re-read on every attempt; never write the previous attempt's secret
        # into the newer catalog revision.
        credentials = local_credentials(catalog_path)
        _attach_credentials(plan["catalog"], credentials)
        status, payload = _http_json(
            "PUT",
            api_url.rstrip("/") + "/api/v1/settings/catalog",
            payload={"catalog": plan["catalog"], "expected_revision": revision},
        )
        if status == 200:
            return {**plan, "applied": True, "attempts": attempt + 1}
        if status == 409:
            last_error = RevisionConflict(payload.get("current_revision"))
            continue
        if status in (401, 403):
            raise AgnesMigrationError("Management API authentication failed; migration left untouched.")
        raise AgnesMigrationError(f"Management API rejected the migration (HTTP {status}).")
    raise last_error or AgnesMigrationError("Migration conflicted repeatedly; catalog left untouched.")


def _validate_management_url(api_url: str) -> None:
    try:
        parsed = urlsplit(api_url)
        parsed.port
        host = parsed.hostname or ""
        loopback = host == "localhost" or ip_address(host).is_loopback
    except ValueError as exc:
        raise AgnesMigrationError("Management API must use a loopback origin.") from exc
    if (
        not loopback or parsed.scheme not in {"http", "https"}
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
    ):
        raise AgnesMigrationError("Management API must use a loopback origin without credentials or a path.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--catalog-file",
        type=Path,
        default=Path("data/user/settings/model_catalog.json"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retries", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.apply:
            result = apply_via_api(args.api_url, args.catalog_file, retries=max(0, min(args.retries, 3)))
        else:
            catalog, _revision = fetch_catalog(args.api_url)
            result = migration_plan(catalog)
        # Sanitized summary only; never serialize catalog or credentials.
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key != "catalog"
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except AgnesMigrationError as exc:
        print(f"migration-error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

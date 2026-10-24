"""Named custom provider definitions stored alongside the model catalog.

The definition is presentation and protocol metadata only.  URLs, credentials,
models and reasoning settings remain on the profile/model rows; a display name
must never become a request transport or grant a vendor capability.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

MAX_CUSTOM_PROVIDERS = 100
MAX_PROVIDER_NAME = 80
BUILTIN_ICONS: tuple[str, ...] = (
    "bot",
    "server",
    "school",
    "flask",
    "cloud",
    "network",
)

CUSTOM_PROVIDER_BINDINGS: dict[str, tuple[str, ...]] = {
    "llm": ("custom", "custom_anthropic"),
    "vision": ("custom", "custom_anthropic"),
    "embedding": ("custom",),
    "stt": ("custom",),
    "tts": ("custom",),
    "imagegen": ("custom", "custom_chat"),
    "videogen": ("custom",),
}

_BINDING_LABELS = {
    "custom": ("OpenAI-compatible", "OpenAI-compatible chat / embeddings / media protocol."),
    "custom_anthropic": ("Anthropic Messages", "Anthropic Messages API (not OpenAI chat)."),
    "custom_chat": ("Chat Completions image output", "Image output through an OpenAI-compatible chat completion."),
}
_SERVICE_CUSTOM_LABELS = {
    "llm": ("OpenAI-compatible chat", "OpenAI-compatible Chat Completions API."),
    "vision": ("OpenAI-compatible vision", "Chat Completions with image_url content."),
    "embedding": ("OpenAI-compatible embeddings", "OpenAI-compatible Embeddings API."),
    "stt": ("OpenAI-compatible transcription", "OpenAI-compatible audio transcriptions (multipart upload)."),
    "tts": ("OpenAI-compatible speech", "OpenAI-compatible audio speech synthesis."),
    "imagegen": ("OpenAI-compatible images", "OpenAI-compatible Images API."),
    "videogen": ("Existing async video task protocol", "Uses the existing async video submit/poll adapter; this is not a universal OpenAI video protocol."),
}
_ID_RE = re.compile(r"^cp_[A-Za-z0-9][A-Za-z0-9_-]{1,79}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class CustomProviderValidationError(ValueError):
    """A proposed definition or profile reference is invalid."""


class CustomProviderConflict(CustomProviderValidationError):
    """A definition cannot be removed while a profile still references it."""


def custom_provider_definitions(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    raw = catalog.get("custom_providers") if isinstance(catalog, dict) else None
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def custom_provider_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in custom_provider_definitions(catalog)
        if item.get("id")
    }


def _icon_value(icon: Any) -> dict[str, str] | None:
    if icon in (None, ""):
        return None
    if not isinstance(icon, dict):
        raise CustomProviderValidationError("Provider icon must be an object or null.")
    unknown = set(icon) - {"kind", "value"}
    if unknown:
        raise CustomProviderValidationError("Provider icon has unsupported fields.")
    kind = icon.get("kind")
    value = icon.get("value")
    if not isinstance(value, str):
        raise CustomProviderValidationError("Provider icon value must be a string.")
    if kind == "builtin":
        normalized = str(value or "").strip().lower()
        if normalized not in BUILTIN_ICONS:
            raise CustomProviderValidationError("Unknown built-in provider icon.")
        return {"kind": "builtin", "value": normalized}
    if kind == "emoji":
        text = str(value or "")
        count = len(text)
        if count < 1 or count > 8 or _CONTROL_RE.search(text):
            raise CustomProviderValidationError("Emoji provider icon must be 1-8 characters.")
        return {"kind": "emoji", "value": text}
    raise CustomProviderValidationError("Provider icon kind must be builtin or emoji.")


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise CustomProviderValidationError("Provider name must be a string.")
    name = value.strip()
    if not name or len(name) > MAX_PROVIDER_NAME:
        raise CustomProviderValidationError("Provider name must be 1-80 characters.")
    if _CONTROL_RE.search(name):
        raise CustomProviderValidationError("Provider name cannot contain control characters.")
    return name


def normalize_custom_provider_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Normalize only the fields owned by this feature, in place."""

    if "custom_providers" not in catalog:
        return catalog
    raw = catalog.get("custom_providers")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("name"), str):
                item["name"] = item["name"].strip()
            icon = item.get("icon")
            if (
                isinstance(icon, dict)
                and icon.get("kind") == "builtin"
                and isinstance(icon.get("value"), str)
            ):
                icon["value"] = icon["value"].strip().lower()
    services = catalog.get("services")
    if isinstance(services, dict):
        for service in services.values():
            if not isinstance(service, dict):
                continue
            for profile in service.get("profiles", []) or []:
                if not isinstance(profile, dict):
                    continue
                if "custom_provider_id" in profile and profile.get("custom_provider_id") in ("", None):
                    profile.pop("custom_provider_id", None)
    return catalog


def validate_custom_provider_catalog(
    catalog: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> None:
    """Validate definitions and their profile references.

    Missing ``custom_providers`` is valid and means an empty list.  Extra
    definition fields, duplicate ids/names, protocol mismatches, missing
    references and removal of a referenced definition are rejected.
    """

    raw = catalog.get("custom_providers") if isinstance(catalog, dict) else None
    if "custom_providers" not in catalog:
        definitions: list[Any] = []
    elif isinstance(raw, list):
        definitions = raw
    else:
        raise CustomProviderValidationError("custom_providers must be an array.")
    if len(definitions) > MAX_CUSTOM_PROVIDERS:
        raise CustomProviderValidationError("At most 100 custom providers are allowed.")

    seen_ids: set[str] = set()
    seen_names: set[tuple[str, str]] = set()
    normalized: dict[str, dict[str, Any]] = {}
    for item in definitions:
        if not isinstance(item, dict):
            raise CustomProviderValidationError("Each custom provider must be an object.")
        unknown = set(item) - {"id", "service", "binding", "name", "icon"}
        if unknown:
            raise CustomProviderValidationError("Custom provider has unsupported fields.")
        provider_id = item.get("id")
        if not isinstance(provider_id, str) or not _ID_RE.fullmatch(provider_id):
            raise CustomProviderValidationError("Custom provider id is invalid.")
        if provider_id in seen_ids:
            raise CustomProviderValidationError("Custom provider ids must be unique.")
        seen_ids.add(provider_id)
        service = item.get("service")
        binding = item.get("binding")
        if not isinstance(service, str) or service not in CUSTOM_PROVIDER_BINDINGS:
            raise CustomProviderValidationError("Custom provider service is not supported.")
        if not isinstance(binding, str) or binding not in CUSTOM_PROVIDER_BINDINGS[service]:
            raise CustomProviderValidationError(
                f"{binding!r} is not a supported protocol for {service}."
            )
        name = _name(item.get("name"))
        name_key = (str(service), name.casefold())
        if name_key in seen_names:
            raise CustomProviderValidationError(
                "Custom provider names must be unique within a service."
            )
        seen_names.add(name_key)
        icon = _icon_value(item.get("icon"))
        normalized[provider_id] = {
            "id": provider_id,
            "service": service,
            "binding": binding,
            "name": name,
            "icon": icon,
        }

    # id/service/binding are immutable once saved.  Name and icon are editable.
    before = custom_provider_by_id(current or {})
    for provider_id, definition in normalized.items():
        old = before.get(provider_id)
        if old is not None and (
            old.get("service") != definition["service"]
            or old.get("binding") != definition["binding"]
        ):
            raise CustomProviderValidationError(
                "A custom provider's service and protocol cannot change after saving."
            )

    # Referenced definitions may not be removed.
    removed = set(before) - set(normalized)
    if removed:
        referenced = _referenced_ids(catalog)
        if removed & referenced:
            raise CustomProviderConflict(
                "A custom provider is still referenced by a connection and cannot be removed."
            )

    services = catalog.get("services")
    if isinstance(services, dict):
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            for profile in service.get("profiles", []) or []:
                if not isinstance(profile, dict):
                    continue
                ref = profile.get("custom_provider_id")
                if ref in (None, ""):
                    continue
                if profile.get("managed_by") or profile.get("read_only"):
                    raise CustomProviderValidationError(
                        "Managed or read-only profiles cannot switch custom provider identity."
                    )
                if not isinstance(ref, str) or ref not in normalized:
                    raise CustomProviderValidationError(
                        "A profile references a custom provider that does not exist."
                    )
                definition = normalized[ref]
                if definition["service"] != service_name:
                    raise CustomProviderValidationError(
                        "A profile cannot reference a custom provider from another service."
                    )
                binding = str(profile.get("binding") or profile.get("provider") or "")
                if binding != definition["binding"]:
                    raise CustomProviderValidationError(
                        "The profile protocol must match the custom provider protocol."
                    )


def _referenced_ids(catalog: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    services = catalog.get("services")
    if not isinstance(services, dict):
        return result
    for service in services.values():
        if not isinstance(service, dict):
            continue
        for profile in service.get("profiles", []) or []:
            if isinstance(profile, dict) and isinstance(profile.get("custom_provider_id"), str):
                result.add(profile["custom_provider_id"])
    return result


def resolve_provider_presentation(
    catalog: dict[str, Any],
    service: str,
    profile: dict[str, Any],
    *,
    fallback_label: str | None = None,
) -> dict[str, Any]:
    """Single safe display summary used by every settings/chat surface."""

    reference = profile.get("custom_provider_id") if isinstance(profile, dict) else None
    definition = custom_provider_by_id(catalog).get(str(reference)) if reference else None
    if definition is not None and definition.get("service") == service:
        try:
            icon = _icon_value(definition.get("icon"))
        except CustomProviderValidationError:
            # Legacy catalogs may predate validation. Never forward malformed
            # children to React or serialize arbitrary icon fields to users.
            icon = None
        return {
            "provider_label": str(definition.get("name") or ""),
            "provider_icon": deepcopy(icon),
            "custom_provider_id": str(definition.get("id") or ""),
        }

    binding = str(
        (profile.get("provider") if service == "search" else profile.get("binding"))
        or ""
    )
    label = fallback_label
    if label is None and service in {"llm", "vision"}:
        from deeptutor.services.provider_registry import find_by_name

        spec = find_by_name(binding)
        label = spec.label if spec is not None else binding
    if not label:
        label = binding or str(profile.get("name") or "")
    return {
        "provider_label": label,
        "provider_icon": None,
        "custom_provider_id": None,
    }


def custom_provider_capabilities() -> dict[str, Any]:
    protocols: dict[str, list[dict[str, str]]] = {}
    for service, bindings in CUSTOM_PROVIDER_BINDINGS.items():
        protocols[service] = [
            {
                "value": binding,
                "label": (_SERVICE_CUSTOM_LABELS[service] if binding == "custom" else _BINDING_LABELS[binding])[0],
                "description": (_SERVICE_CUSTOM_LABELS[service] if binding == "custom" else _BINDING_LABELS[binding])[1],
            }
            for binding in bindings
        ]
    return {
        "protocols": protocols,
        "icons": list(BUILTIN_ICONS),
        "max_name_length": MAX_PROVIDER_NAME,
        "max_providers": MAX_CUSTOM_PROVIDERS,
    }


__all__ = [
    "BUILTIN_ICONS",
    "CUSTOM_PROVIDER_BINDINGS",
    "CustomProviderConflict",
    "CustomProviderValidationError",
    "MAX_CUSTOM_PROVIDERS",
    "MAX_PROVIDER_NAME",
    "custom_provider_by_id",
    "custom_provider_capabilities",
    "custom_provider_definitions",
    "normalize_custom_provider_catalog",
    "resolve_provider_presentation",
    "validate_custom_provider_catalog",
]

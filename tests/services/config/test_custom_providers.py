from __future__ import annotations

from copy import deepcopy

import pytest

from deeptutor.services.config.custom_providers import (
    CustomProviderConflict,
    CustomProviderValidationError,
    custom_provider_capabilities,
    normalize_custom_provider_catalog,
    resolve_provider_presentation,
    validate_custom_provider_catalog,
)


def definition(**overrides):
    value = {
        "id": "cp_11111111-1111-4111-8111-111111111111",
        "service": "llm",
        "binding": "custom",
        "name": "School gateway",
        "icon": {"kind": "builtin", "value": "school"},
    }
    value.update(overrides)
    return value


def catalog(*, definitions=None, profiles=None):
    return {
        "version": 1,
        "unknown_top_level": {"keep": True},
        **({"custom_providers": definitions} if definitions is not None else {}),
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": profiles
                if profiles is not None
                else [
                    {
                        "id": "p1",
                        "name": "My school",
                        "binding": "custom",
                        "custom_provider_id": definition()["id"],
                        "base_url": "https://school.example/v1",
                        "api_key": "sk-test",
                        "extra_headers": {},
                        "models": [{"id": "m1", "name": "Mystery", "model": "school/mystery"}],
                    }
                ],
            }
        },
    }


def test_missing_custom_providers_is_valid_and_old_catalog_roundtrips():
    old = {
        "version": 1,
        "unknown_top_level": {"keep": True},
        "services": {
            "llm": {
                "active_profile_id": "p1",
                "active_model_id": "m1",
                "profiles": [
                    {
                        "id": "p1",
                        "name": "Old custom",
                        "binding": "custom",
                        "base_url": "https://old.example/v1",
                        "models": [{"id": "m1", "model": "old-model"}],
                    }
                ],
            }
        },
    }
    before = deepcopy(old)
    validate_custom_provider_catalog(old, old)
    assert old == before
    assert "custom_providers" not in old


def test_definition_and_reference_are_valid_for_all_supported_protocols():
    capabilities = custom_provider_capabilities()
    assert capabilities["protocols"]["llm"] == [
        {
            "value": "custom",
            "label": "OpenAI-compatible chat",
            "description": "OpenAI-compatible Chat Completions API.",
        },
        {
            "value": "custom_anthropic",
            "label": "Anthropic Messages",
            "description": "Anthropic Messages API (not OpenAI chat).",
        },
    ]
    for service, protocols in capabilities["protocols"].items():
        for protocol in protocols:
            item = definition(service=service, binding=protocol["value"])
            validate_custom_provider_catalog(
                {"version": 1, "custom_providers": [item], "services": {}}
            )


def test_name_is_trimmed_and_duplicates_are_casefolded_per_service():
    first = definition(name="  School Gateway  ")
    second = definition(
        id="cp_22222222-2222-4222-8222-222222222222",
        name="school gateway",
    )
    value = catalog(definitions=[first, second])
    normalize_custom_provider_catalog(value)
    assert first["name"] == "School Gateway"
    with pytest.raises(CustomProviderValidationError, match="unique"):
        validate_custom_provider_catalog(value)
    # Different service may reuse the name.
    other = definition(
        id="cp_33333333-3333-4333-8333-333333333333",
        service="embedding",
        binding="custom",
        name="School Gateway",
    )
    validate_custom_provider_catalog(catalog(definitions=[first, other]))


def test_icon_validation_builtin_emoji_fallback_and_rejections():
    for icon in (None, {"kind": "builtin", "value": "flask"}):
        validate_custom_provider_catalog(catalog(definitions=[definition(icon=icon)]))
    validate_custom_provider_catalog(
        catalog(definitions=[definition(icon={"kind": "emoji", "value": "🧪"})])
    )
    for icon in (
        {"kind": "builtin", "value": "svg"},
        {"kind": "emoji", "value": ""},
        {"kind": "emoji", "value": "123456789"},
        {"kind": "emoji", "value": "x\ny"},
        {"kind": "image", "value": "https://example/x.png"},
        {"kind": "builtin", "value": "bot", "extra": "x"},
        {"kind": "builtin"},
    ):
        with pytest.raises(CustomProviderValidationError):
            validate_custom_provider_catalog(catalog(definitions=[definition(icon=icon)]))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("service", "search", "not supported"),
        ("binding", "openai", "not a supported protocol"),
        ("name", "", "1-80"),
        ("name", "x" * 81, "1-80"),
        ("id", "custom", "id is invalid"),
        ("extra", True, "unsupported fields"),
    ],
)
def test_invalid_definition_is_rejected(field, value, message):
    item = definition(**{field: value})
    with pytest.raises(CustomProviderValidationError, match=message):
        validate_custom_provider_catalog(catalog(definitions=[item]))


def test_duplicate_ids_and_cross_service_reference_are_rejected():
    item = definition()
    with pytest.raises(CustomProviderValidationError, match="unique"):
        validate_custom_provider_catalog(catalog(definitions=[item, deepcopy(item)]))
    wrong_service = {
        "id": "p1",
        "name": "School",
        "binding": "custom",
        "custom_provider_id": item["id"],
        "models": [],
    }
    value = {
        "version": 1,
        "custom_providers": [item],
        "services": {"embedding": {"profiles": [wrong_service]}},
    }
    with pytest.raises(CustomProviderValidationError, match="another service"):
        validate_custom_provider_catalog(value)


def test_protocol_mismatch_and_missing_reference_are_rejected():
    item = definition()
    profile = catalog(definitions=[item])["services"]["llm"]["profiles"][0]
    profile["binding"] = "custom_anthropic"
    with pytest.raises(CustomProviderValidationError, match="protocol"):
        validate_custom_provider_catalog(catalog(definitions=[item], profiles=[profile]))
    profile["binding"] = "custom"
    profile["custom_provider_id"] = "cp_missing"
    with pytest.raises(CustomProviderValidationError, match="does not exist"):
        validate_custom_provider_catalog(catalog(definitions=[item], profiles=[profile]))


def test_id_service_and_binding_are_immutable_but_name_and_icon_are_editable():
    old = catalog(definitions=[definition()])
    validate_custom_provider_catalog(
        catalog(definitions=[definition(name="Renamed", icon={"kind": "emoji", "value": "🧪"})]),
        old,
    )
    with pytest.raises(CustomProviderValidationError, match="cannot change"):
        validate_custom_provider_catalog(
            catalog(definitions=[definition(binding="custom_anthropic")]), old
        )


def test_referenced_definition_cannot_be_deleted_but_unreferenced_can():
    old = catalog(definitions=[definition()])
    with pytest.raises(CustomProviderConflict, match="still referenced"):
        validate_custom_provider_catalog(
            catalog(definitions=[], profiles=old["services"]["llm"]["profiles"]), old
        )
    unreferenced = definition(
        id="cp_22222222-2222-4222-8222-222222222222", name="Unused"
    )
    old = catalog(definitions=[unreferenced])
    validate_custom_provider_catalog(
        catalog(
            definitions=[],
            profiles=[
                {
                    "id": "p1",
                    "name": "Plain",
                    "binding": "custom",
                    "models": [],
                }
            ],
        ),
        old,
    )


def test_presenter_uses_definition_only_for_matching_service_and_never_secrets():
    item = definition(name="学校网关", icon={"kind": "emoji", "value": "🏫"})
    value = catalog(definitions=[item])
    profile = value["services"]["llm"]["profiles"][0]
    presentation = resolve_provider_presentation(value, "llm", profile)
    assert presentation == {
        "provider_label": "学校网关",
        "provider_icon": {"kind": "emoji", "value": "🏫"},
        "custom_provider_id": item["id"],
    }
    serialized = str(presentation)
    assert "sk-test" not in serialized
    assert "school.example" not in serialized
    # A stale cross-service reference falls back to the real technical binding.
    fallback = resolve_provider_presentation(value, "embedding", profile)
    assert fallback["provider_label"] == "custom"
    assert fallback["provider_icon"] is None


@pytest.mark.parametrize("field,value", [("service", []), ("service", {}), ("binding", []), ("icon", {"kind": "emoji", "value": 7}), ("icon", {"kind": "emoji", "value": True})])
def test_review_malformed_definition_types_raise_validation_error(field, value):
    with pytest.raises(CustomProviderValidationError):
        validate_custom_provider_catalog(catalog(definitions=[definition(**{field: value})]))


def test_review_explicit_null_definitions_is_not_an_array():
    with pytest.raises(CustomProviderValidationError):
        validate_custom_provider_catalog({"custom_providers": None, "services": {}})


def test_review_presenter_does_not_crash_or_forward_invalid_icon_from_legacy_data():
    item = definition(icon={"kind": "emoji", "value": {"unexpected": "object"}})
    value = catalog(definitions=[item])
    summary = resolve_provider_presentation(value, "llm", value["services"]["llm"]["profiles"][0])
    assert summary["provider_icon"] is None


def test_review_protocol_help_is_specific_to_the_service_not_universal_openai():
    protocols = custom_provider_capabilities()["protocols"]
    assert "async" in protocols["videogen"][0]["description"]
    assert "not a universal" in protocols["videogen"][0]["description"]
    assert "multipart" in protocols["stt"][0]["description"]
    assert protocols["embedding"][0]["label"] != protocols["llm"][0]["label"]

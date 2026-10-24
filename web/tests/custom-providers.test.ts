import assert from "node:assert/strict";
import test from "node:test";

import {
  CUSTOM_PROVIDER_SENTINEL,
  customProviderById,
  customProviderIdFromSelectValue,
  customProviderSelectValue,
  customProvidersForService,
  localizeProviderLabel,
  connectionLabelText,
  newCustomProviderId,
  resolveProviderPresentation,
  validateCustomProviderIcon,
  validateCustomProviderName,
  type CustomProviderDefinition,
} from "../lib/custom-providers";
import type { CatalogProfile } from "../components/settings/SettingsContext";

const defs: CustomProviderDefinition[] = [
  {
    id: "cp_11111111-1111-4111-8111-111111111111",
    service: "llm",
    binding: "custom",
    name: "学校网关",
    icon: { kind: "emoji", value: "🏫" },
  },
  {
    id: "cp_22222222-2222-4222-8222-222222222222",
    service: "llm",
    binding: "custom_anthropic",
    name: "Claude gateway",
    icon: { kind: "builtin", value: "flask" },
  },
  {
    id: "cp_33333333-3333-4333-8333-333333333333",
    service: "embedding",
    binding: "custom",
    name: "学校网关",
  },
];

const profile = (overrides: Partial<CatalogProfile> = {}): CatalogProfile => ({
  id: "p1",
  name: "Connection",
  binding: "custom",
  custom_provider_id: defs[0].id,
  base_url: "https://school.example/v1",
  api_key: "***",
  api_version: "",
  models: [],
  ...overrides,
});

test("definitions are scoped to a service and both llm protocols are accepted", () => {
  const catalog = { custom_providers: defs } as any;
  assert.deepEqual(
    customProvidersForService(catalog, "llm").map((item) => item.id),
    [defs[1].id, defs[0].id],
  );
  assert.deepEqual(
    customProvidersForService(catalog, "embedding").map((item) => item.id),
    [defs[2].id],
  );
  assert.equal(customProviderById(catalog, defs[1].id)?.binding, "custom_anthropic");
});

test("select values use stable ids and the UI sentinel is never a binding", () => {
  const value = customProviderSelectValue(profile());
  assert.equal(value, `cp:${defs[0].id}`);
  assert.equal(customProviderIdFromSelectValue(value), defs[0].id);
  assert.equal(customProviderIdFromSelectValue("custom"), null);
  assert.equal(CUSTOM_PROVIDER_SENTINEL, "__create_custom_provider__");
  assert.notEqual(customProviderSelectValue(profile({ custom_provider_id: undefined })), CUSTOM_PROVIDER_SENTINEL);
  assert.match(newCustomProviderId(), /^cp_/);
});

test("presentation uses the definition name and icon but keeps the real binding", () => {
  const catalog = { custom_providers: defs } as any;
  const presentation = resolveProviderPresentation(
    catalog,
    "llm",
    profile(),
    "Custom",
  );
  assert.deepEqual(presentation, {
    providerLabel: "学校网关",
    providerIcon: { kind: "emoji", value: "🏫" },
    customProviderId: defs[0].id,
  });
  assert.equal(profile().binding, "custom");
});

test("a stale cross-service reference falls back to the technical binding", () => {
  const catalog = { custom_providers: defs } as any;
  const presentation = resolveProviderPresentation(
    catalog,
    "embedding",
    profile(),
    "OpenAI Compatible",
  );
  assert.equal(presentation.providerLabel, "OpenAI Compatible");
  assert.equal(presentation.providerIcon, null);
  assert.equal(presentation.customProviderId, null);
});

test("name validation trims, limits, rejects controls and enforces per-service uniqueness", () => {
  assert.equal(validateCustomProviderName("  School  ", [], "llm"), null);
  assert.match(validateCustomProviderName("", [], "llm") ?? "", /1–80/);
  assert.match(validateCustomProviderName("x".repeat(81), [], "llm") ?? "", /1–80/);
  assert.match(validateCustomProviderName("x\ny", [], "llm") ?? "", /控制字符/);
  assert.match(
    validateCustomProviderName("学校网关", defs, "llm", defs[1].id) ?? "",
    /重名/,
  );
  // Same name in another service is fine.
  assert.equal(validateCustomProviderName("学校网关", defs, "stt"), null);
  // Editing the same definition may keep its own name.
  assert.equal(validateCustomProviderName("学校网关", defs, "llm", defs[0].id), null);
});

test("icon validation supports builtin/emoji/fallback and rejects unsafe kinds", () => {
  assert.equal(validateCustomProviderIcon(null), null);
  assert.equal(validateCustomProviderIcon({ kind: "builtin", value: "network" }), null);
  assert.equal(validateCustomProviderIcon({ kind: "emoji", value: "🧪" }), null);
  assert.match(validateCustomProviderIcon({ kind: "builtin", value: "svg" as any }) ?? "", /未知/);
  assert.match(validateCustomProviderIcon({ kind: "emoji", value: "" }) ?? "", /1–8/);
  assert.match(validateCustomProviderIcon({ kind: "emoji", value: "123456789" }) ?? "", /1–8/);
  assert.match(validateCustomProviderIcon({ kind: "emoji", value: "x\ny" }) ?? "", /控制/);
  assert.match(validateCustomProviderIcon({ kind: "image", value: "x" } as any) ?? "", /类型/);
});

test("legacy anonymous custom labels localize without touching provider names", () => {
  const t = (key: string) => `zh:${key}`;
  assert.equal(localizeProviderLabel("Custom", t), "zh:Custom (OpenAI-compatible)");
  assert.equal(
    localizeProviderLabel("Custom (Anthropic API)", t),
    "zh:Custom (Anthropic Messages)",
  );
  assert.equal(localizeProviderLabel("学校网关", t), "学校网关");
  assert.equal(localizeProviderLabel("Custom", t, defs[0].id), "Custom");
  assert.equal(connectionLabelText("Custom (OpenAI API)", "Work", t, defs[0].id), "Custom (OpenAI API) · Work");
});

import assert from "node:assert/strict";
import test from "node:test";

import type { Catalog } from "../components/settings/SettingsContext";
import {
  changedDefaultReferences,
  defaultReferenceKey,
  mergeDefaultReferences,
  parseDefaultModelsResponse,
  sameDefaultReference,
  revisionAfterDefaultPatch,
} from "../lib/default-models";

test("a reference patch never certifies an older catalog's unrelated fields", () => {
  assert.equal(revisionAfterDefaultPatch("r1", "r1", "r2"), "r2");
  assert.equal(revisionAfterDefaultPatch("r1", "external-r2", "r3"), "r1");
  assert.equal(revisionAfterDefaultPatch(null, "r1", "r2"), null);
});

function catalog(): Catalog {
  return {
    version: 1,
    services: {
      llm: {
        active_profile_id: "old",
        active_model_id: "old-model",
        profiles: [],
      },
      embedding: {
        active_profile_id: "e",
        active_model_id: "em",
        profiles: [],
      },
      search: { active_profile_id: "s", profiles: [] },
      tts: { active_profile_id: null, active_model_id: null, profiles: [] },
      stt: { active_profile_id: null, active_model_id: null, profiles: [] },
      imagegen: { active_profile_id: null, active_model_id: null, profiles: [] },
      videogen: { active_profile_id: null, active_model_id: null, profiles: [] },
      vision: { active_profile_id: null, active_model_id: null, profiles: [] },
    },
  };
}

test("parser keeps search as a profile and rejects missing revisions", () => {
  const response = parseDefaultModelsResponse({
    revision: "rev-1",
    defaults: { llm: { profile_id: "p", model_id: "m" }, search: null },
    services: {
      llm: {
        kind: "model",
        profiles: [
          {
            profile_id: "p",
            profile_name: "DeepSeek",
            provider: "deepseek",
            provider_label: "DeepSeek",
            provider_icon: { kind: "builtin", value: "flask" },
            custom_provider_id: "cp_1",
            models: [{ model_id: "m", model_name: "Flash" }],
          },
        ],
      },
      search: {
        kind: "profile",
        profiles: [
          {
            profile_id: "s",
            profile_name: "Brave",
            provider: "brave",
            provider_label: "brave",
            models: [],
          },
        ],
      },
    },
  });
  assert.deepEqual(response.services.llm.profiles[0].provider_icon, {
    kind: "builtin",
    value: "flask",
  });
  assert.equal(response.services.llm.profiles[0].custom_provider_id, "cp_1");
  assert.equal(response.services.search.kind, "profile");
  assert.equal(response.services.search.profiles[0].models.length, 0);
  assert.throws(() => parseDefaultModelsResponse({ defaults: {} }));
});

test("changed references only include modifications and never submit clears", () => {
  const changed = changedDefaultReferences(
    {
      llm: { profile_id: "p1", model_id: "m1" },
      search: { profile_id: "s1" },
    },
    {
      llm: { profile_id: "p2", model_id: "m2" },
      search: null,
    },
  );
  assert.deepEqual(changed, { llm: { profile_id: "p2", model_id: "m2" } });
});

test("merge changes only active references and keeps every other draft field", () => {
  const source = catalog();
  source.services.llm.profiles = [
    {
      id: "p2",
      name: "New",
      base_url: "",
      api_key: "",
      api_version: "",
      models: [
        {
          id: "m2",
          name: "Model",
          model: "x",
          ...({ custom: "keep" } as Record<string, unknown>),
        },
      ],
    },
  ];
  const merged = mergeDefaultReferences(source, {
    llm: { profile_id: "p2", model_id: "m2" },
    embedding: { profile_id: "e2", model_id: "em2" },
  });
  assert.equal(merged.services.llm.active_profile_id, "p2");
  assert.equal(merged.services.llm.active_model_id, "m2");
  assert.equal(merged.services.embedding.active_model_id, "em2");
  assert.equal(
    (merged.services.llm.profiles[0].models[0] as unknown as { custom: string })
      .custom,
    "keep",
  );
  assert.equal(merged.services.search.active_profile_id, "s");
});

test("reference keys and equality are stable for profile-only search", () => {
  const ref = { profile_id: "s", model_id: "" };
  assert.equal(defaultReferenceKey(ref), "s\u0000");
  assert.equal(sameDefaultReference(ref, { profile_id: "s" }), true);
  assert.equal(sameDefaultReference(ref, { profile_id: "s", model_id: "m" }), false);
});

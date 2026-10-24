import assert from "node:assert/strict";
import test from "node:test";

import type { CatalogModel, CatalogProfile } from "../components/settings/SettingsContext";
import {
  autoDiscoveryAllowed,
  candidateGroup,
  connectionIdentity,
  filterCandidates,
  mergeDiscoveredModels,
  modelVisibleInPicker,
  parseDiscoveryResponse,
  requiresUnknownConfirmation,
  type DiscoveryModel,
} from "../lib/model-discovery";
import {
  INITIAL_MODEL_DISCOVERY_STATE,
  reduceModelDiscoveryState,
} from "../lib/model-discovery-state";

function candidate(overrides: Partial<DiscoveryModel> = {}): DiscoveryModel {
  return {
    id: "openai/Model-A",
    name: "Model A",
    services: ["llm"],
    classification: "provider",
    runtime_compatibility: "supported",
    reason_code: null,
    source: "remote",
    callability: "not_tested",
    ...overrides,
  };
}

function response(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    service: "llm",
    profile_id: "p1",
    status: "ok",
    models: [candidate()],
    cache: { state: "fresh", fetched_at: "2026-10-23T00:00:00Z", expires_at: "2026-10-23T01:00:00Z" },
    complete: true,
    error: null,
    ...overrides,
  };
}

test("parses a valid envelope and preserves case, slashes, colons, and dots", () => {
  const parsed = parseDiscoveryResponse(
    response({
      models: [
        candidate({ id: "OpenAI/GPT-4.1:Mini.v2-beta", name: "GPT Mini", context_window: 128000 }),
      ],
    }),
  );
  assert.equal(parsed.models[0].id, "OpenAI/GPT-4.1:Mini.v2-beta");
  assert.equal(parsed.models[0].context_window, 128000);
  assert.equal(parsed.cache.state, "fresh");
  assert.equal(parsed.models[0].callability, "not_tested");
});

test("parses an explicit empty directory as success, not auth failure", () => {
  const parsed = parseDiscoveryResponse(
    response({ status: "empty", models: [], cache: { state: "fresh", fetched_at: "x", expires_at: "y" } }),
  );
  assert.equal(parsed.status, "empty");
  assert.deepEqual(parsed.models, []);
  assert.equal(parsed.error, null);
});

test("rejects malformed response fields instead of trusting them", () => {
  assert.throws(() => parseDiscoveryResponse({ schema_version: 2, service: "llm" }));
  assert.throws(() =>
    parseDiscoveryResponse(response({ models: [{ id: "bad\nid", name: "x" }] })),
  );
  assert.throws(() => parseDiscoveryResponse(response({ service: "search" })));
  assert.equal(parseDiscoveryResponse(response({ complete: undefined })).complete, false);
});

test("unknown requires confirmation, unsupported is blocked, wrong category is skipped", () => {
  const unknown = candidate({ classification: "unknown", runtime_compatibility: "unknown" });
  const unsupported = candidate({ id: "unsupported", runtime_compatibility: "unsupported" });
  assert.equal(requiresUnknownConfirmation(unknown), true);
  assert.equal(candidateGroup(unknown), "unknown");
  assert.equal(candidateGroup(unsupported), "unsupported");
  assert.equal(candidateGroup(candidate()), "available");

  const existing: CatalogModel[] = [];
  const skipped = mergeDiscoveredModels({
    existing,
    candidates: [unknown, unsupported],
    selectedIds: [unknown.id, unsupported.id],
    service: "llm",
    idFactory: () => "new-1",
  });
  assert.deepEqual(skipped.models, []);
  const confirmed = mergeDiscoveredModels({
    existing,
    candidates: [unknown],
    selectedIds: [unknown.id],
    confirmedUnknownIds: [unknown.id],
    service: "llm",
    idFactory: () => "new-2",
  });
  assert.equal(confirmed.models.length, 1);
  assert.equal(confirmed.models[0].model, unknown.id);
  const wrongCategory = mergeDiscoveredModels({
    existing,
    candidates: [candidate({ id: "embedding/x", services: ["embedding"] })],
    selectedIds: ["embedding/x"],
    service: "llm",
    idFactory: () => "new-3",
  });
  assert.deepEqual(wrongCategory.models, []);
});

test("merge preserves existing id, alias, parameters, and reuses duplicates", () => {
  const existing: CatalogModel[] = [
    { id: "stable-1", name: "My alias", model: "openai/Model-A", context_window: "999" },
  ];
  const merged = mergeDiscoveredModels({
    existing,
    candidates: [candidate(), candidate({ id: "openai/Model-B" })],
    selectedIds: ["openai/Model-A", "openai/Model-B"],
    service: "llm",
    idFactory: () => "stable-2",
  });
  assert.deepEqual(merged.models[0], existing[0]);
  assert.deepEqual(merged.reusedIds, ["stable-1"]);
  assert.deepEqual(merged.addedIds, ["stable-2"]);
  assert.equal(merged.models[1].model, "openai/Model-B");
});

test("the same provider model can exist independently in another profile", () => {
  const profileA = mergeDiscoveredModels({
    existing: [],
    candidates: [candidate()],
    selectedIds: [candidate().id],
    service: "llm",
    idFactory: () => "a-1",
  });
  const profileB = mergeDiscoveredModels({
    existing: profileA.models,
    candidates: [candidate()],
    selectedIds: [candidate().id],
    service: "llm",
    idFactory: () => "b-1",
  });
  assert.deepEqual(profileB.reusedIds, ["a-1"]);
  const independent = mergeDiscoveredModels({
    existing: [],
    candidates: [candidate()],
    selectedIds: [candidate().id],
    service: "llm",
    idFactory: () => "b-2",
  });
  assert.deepEqual(independent.addedIds, ["b-2"]);
});

test("missing visible_in_picker remains visible and false is hidden", () => {
  assert.equal(modelVisibleInPicker(undefined), true);
  assert.equal(modelVisibleInPicker({}), true);
  assert.equal(modelVisibleInPicker({ visible_in_picker: true }), true);
  assert.equal(modelVisibleInPicker({ visible_in_picker: false }), false);
});

test("search and group filters keep unsupported and unknown distinguishable", () => {
  const models = [
    candidate({ id: "a/chat", name: "Chat" }),
    candidate({ id: "b/embed", name: "Embed", classification: "unknown", runtime_compatibility: "unknown" }),
    candidate({ id: "c/video", name: "Video", runtime_compatibility: "unsupported" }),
  ];
  assert.deepEqual(filterCandidates(models, "chat", "all").map((m) => m.id), ["a/chat"]);
  assert.deepEqual(filterCandidates(models, "", "unknown").map((m) => m.id), ["b/embed"]);
  assert.deepEqual(filterCandidates(models, "", "unsupported").map((m) => m.id), ["c/video"]);
});

test("connection identity changes with origin, key, profile, version, or headers", () => {
  const base: CatalogProfile = {
    id: "p1",
    name: "Profile",
    binding: "openai",
    base_url: "https://api.example/v1",
    api_key: "sk.a.b.c",
    api_version: "",
    extra_headers: { "X-One": "1" },
    models: [],
  };
  const identity = connectionIdentity(base);
  assert.equal(connectionIdentity({ ...base }), identity);
  assert.notEqual(connectionIdentity({ ...base, id: "p2" }), identity);
  assert.notEqual(connectionIdentity({ ...base, base_url: "https://api.example/v2" }), identity);
  assert.notEqual(connectionIdentity({ ...base, api_key: "sk.other" }), identity);
  assert.notEqual(connectionIdentity({ ...base, api_version: "2" }), identity);
  assert.notEqual(connectionIdentity({ ...base, extra_headers: { "X-One": "2" } }), identity);
});

test("auto discovery only applies to the active saved ordinary profile", () => {
  const profile: CatalogProfile = {
    id: "p1",
    name: "Profile",
    binding: "openai",
    base_url: "https://api.example/v1",
    api_key: "***",
    api_version: "",
    models: [],
  };
  assert.equal(autoDiscoveryAllowed(profile, profile), true);
  assert.equal(autoDiscoveryAllowed({ ...profile, id: "draft" }, profile), false);
  assert.equal(autoDiscoveryAllowed({ ...profile, binding: "" }, profile), false);
  assert.equal(autoDiscoveryAllowed({ ...profile, read_only: true }, { ...profile, read_only: true }), false);
  assert.equal(autoDiscoveryAllowed({ ...profile, managed_by: "openai_codex_oauth" }, profile), false);
});

test("a late A response cannot overwrite B's state", () => {
  const startedA = reduceModelDiscoveryState(INITIAL_MODEL_DISCOVERY_STATE, {
    type: "request-started",
    requestKey: "A",
  });
  const startedB = reduceModelDiscoveryState(startedA, {
    type: "request-started",
    requestKey: "B",
  });
  const lateA = reduceModelDiscoveryState(startedB, {
    type: "request-succeeded",
    requestKey: "A",
    response: parseDiscoveryResponse(response({ models: [candidate({ id: "a" })] })),
  });
  assert.strictEqual(lateA, startedB);
  const okB = reduceModelDiscoveryState(startedB, {
    type: "request-succeeded",
    requestKey: "B",
    response: parseDiscoveryResponse(response({ models: [candidate({ id: "b" })] })),
  });
  assert.equal(okB.response?.models[0].id, "b");
  const failed = reduceModelDiscoveryState(okB, {
    type: "request-failed",
    requestKey: "B",
    message: "boom",
  });
  assert.equal(failed.loading, false);
  assert.equal(failed.error, "boom");
  assert.equal(failed.response?.models[0].id, "b");
});

test("candidate parameters are parsed and a new LLM receives source-backed defaults", () => {
  const parsed = parseDiscoveryResponse(
    response({
      models: [
        candidate({
          id: "deepseek-flash",
          name: "DeepSeek V4.1 Flash",
          context_window: 1048576,
          metadata_schema_version: 1,
          parameters: {
            context_window: 1048576,
            max_output_tokens: 393216,
            input_modalities: ["text", "image"],
            output_modalities: ["text"],
            provenance: {
              context_window: {
                kind: "provider_api",
                source_url: "https://api.deepseek.com/models",
                checked_at: "2026-10-24T00:00:00Z",
              },
            },
          },
        }),
      ],
    }),
  );
  const candidateModel = parsed.models[0];
  assert.equal(candidateModel.parameters?.max_output_tokens, 393216);
  assert.equal(candidateModel.parameters?.input_modalities?.[1], "image");

  const merged = mergeDiscoveredModels({
    existing: [],
    candidates: parsed.models,
    selectedIds: ["deepseek-flash"],
    service: "llm",
    idFactory: () => "llm-model-new",
  });
  assert.equal(merged.models[0].id, "llm-model-new");
  assert.equal(merged.models[0].model, "deepseek-flash");
  assert.equal(merged.models[0].context_window, "1048576");
  assert.equal(merged.models[0].max_tokens, "393216");
  assert.equal(merged.models[0].context_window_source, "official");
  assert.deepEqual(merged.models[0].parameter_overrides, {
    context_window: false,
    max_tokens: false,
  });
  assert.ok(merged.models[0].provider_metadata);
});

test("a reused model is untouched and embedding defaults use the documented default", () => {
  const existing: CatalogModel[] = [
    {
      id: "stable-1",
      name: "My Flash",
      model: "deepseek-flash",
      context_window: "1000000",
      max_tokens: "512",
      parameter_overrides: { context_window: true, max_tokens: true },
    },
  ];
  const discovered: DiscoveryModel[] = [
    candidate({
      id: "deepseek-flash",
      context_window: 1048576,
      parameters: {
        context_window: 1048576,
        max_output_tokens: 393216,
        provenance: {
          context_window: {
            kind: "provider_api",
            source_url: "https://api.deepseek.com/models",
            checked_at: "2026-10-24T00:00:00Z",
          },
        },
      },
    }),
    candidate({
      id: "text-embedding-v4",
      services: ["embedding"],
      parameters: {
        default_dimensions: 1024,
        supported_dimensions: [2048, 1024],
        supports_dimensions_parameter: true,
        provenance: {
          default_dimensions: {
            kind: "official_docs",
            source_url: "https://help.aliyun.com/doc",
            checked_at: "2026-10-24T00:00:00Z",
          },
        },
      },
    }),
  ];
  const merged = mergeDiscoveredModels({
    existing,
    candidates: discovered,
    selectedIds: ["deepseek-flash"],
    service: "llm",
    idFactory: () => "unused",
  });
  assert.deepEqual(merged.models[0], existing[0]);
  assert.deepEqual(merged.reusedIds, ["stable-1"]);

  const embedding = mergeDiscoveredModels({
    existing: [],
    candidates: discovered,
    selectedIds: ["text-embedding-v4"],
    service: "embedding",
    idFactory: () => "emb-model-new",
  });
  assert.equal(embedding.models[0].dimension, "1024");
  assert.equal(embedding.models[0].supported_dimensions, "2048,1024");
  assert.equal(embedding.models[0].send_dimensions, true);
});

test("directory URL is part of the connection identity", () => {
  const base: CatalogProfile = {
    id: "p1",
    name: "Gateway",
    base_url: "https://school.example/v1",
    api_key: "***",
    api_version: "",
    extra_headers: {},
    models: [],
  };
  const changed = { ...base, model_directory_url: "https://catalog.example/models" };
  assert.notEqual(connectionIdentity(base), connectionIdentity(changed));
  assert.equal(
    connectionIdentity(changed),
    connectionIdentity({ ...changed }),
  );
});

test("deployment mapping and resource names survive the parser", () => {
  const parsed = parseDiscoveryResponse(
    response({
      models: [
        candidate({
          id: "gpt-4.1",
          deployment_mapping_required: true,
          resource_name: "models/gpt-4.1",
        }),
      ],
    }),
  );
  assert.equal(parsed.models[0].deployment_mapping_required, true);
  assert.equal(parsed.models[0].resource_name, "models/gpt-4.1");
});

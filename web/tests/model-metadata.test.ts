import assert from "node:assert/strict";
import test from "node:test";

import {
  initialCatalogParameters,
  modelOverrideFlags,
  parseModelParameters,
  positiveInteger,
  previewParameterUpdate,
  type ModelParameters,
} from "../lib/model-metadata";

const checked = "2026-10-24T00:00:00Z";
const provenance = {
  context_window: {
    kind: "provider_api" as const,
    source_url: "https://api.deepseek.com/models",
    checked_at: checked,
    json_path: "data[].context_window",
  },
};

test("parameter parser rejects booleans, floats, negatives and unknown keys", () => {
  const parsed = parseModelParameters({
    context_window: 1048576,
    max_input_tokens: true,
    max_output_tokens: 0,
    max_reasoning_tokens: -1,
    default_dimensions: 1.5,
    supported_dimensions: [2048, 1024, 1024, true, "512"],
    supports_dimensions_parameter: true,
    input_modalities: ["text", "TEXT", "bogus"],
    output_modalities: ["text"],
    random_extra: 99,
    provenance,
  });
  assert.ok(parsed);
  assert.equal(parsed.context_window, 1048576);
  assert.equal(parsed.max_input_tokens, undefined);
  assert.equal(parsed.max_output_tokens, undefined);
  assert.deepEqual(parsed.supported_dimensions, [2048, 1024, 512]);
  assert.deepEqual(parsed.input_modalities, ["text"]);
  assert.equal("random_extra" in parsed, false);
  assert.equal(parsed.provenance?.context_window.source_url, "https://api.deepseek.com/models");
});

test("source URLs are stripped of query and userinfo", () => {
  const parsed = parseModelParameters({
    context_window: 4096,
    provenance: {
      context_window: {
        kind: "endpoint_api",
        source_url: "https://user:pass@school.example/models?key=secret#frag",
        checked_at: checked,
      },
    },
  });
  assert.equal(
    parsed?.provenance?.context_window.source_url,
    "https://school.example/models",
  );
});

test("new LLM receives official context and max output but input-only stays separate", () => {
  const parameters: ModelParameters = {
    context_window: 1048576,
    max_output_tokens: 393216,
    input_modalities: ["text", "image"],
    output_modalities: ["text"],
    provenance,
  };
  const updates = initialCatalogParameters("llm", parameters);
  assert.equal(updates.context_window, "1048576");
  assert.equal(updates.max_tokens, "393216");
  assert.equal(updates.context_window_source, "official");
  assert.deepEqual(updates.parameter_overrides, {
    context_window: false,
    max_tokens: false,
  });

  const inputOnly: ModelParameters = {
    max_input_tokens: 200000,
    provenance: {
      max_input_tokens: {
        kind: "official_docs",
        source_url: "https://example.com/doc",
        checked_at: checked,
      },
    },
  };
  const inputUpdates = initialCatalogParameters("llm", inputOnly);
  assert.equal(inputUpdates.max_input_tokens, "200000");
  assert.equal(inputUpdates.context_window, undefined);
  assert.equal(inputUpdates.max_tokens, undefined);
});

test("new embedding uses default, not largest supported dimension", () => {
  const updates = initialCatalogParameters("embedding", {
    default_dimensions: 1024,
    supported_dimensions: [2048, 1536, 1024, 512],
    supports_dimensions_parameter: false,
    provenance: {
      default_dimensions: {
        kind: "official_docs",
        source_url: "https://help.aliyun.com/doc",
        checked_at: checked,
      },
    },
  });
  assert.equal(updates.dimension, "1024");
  assert.equal(updates.supported_dimensions, "2048,1536,1024,512");
  assert.equal(updates.send_dimensions, false);
});

test("legacy non-empty values count as manual and require explicit restore", () => {
  const existing = {
    id: "m1",
    name: "Mine",
    model: "deepseek-flash",
    context_window: "1000000",
    max_tokens: "512",
  };
  const flags = modelOverrideFlags(existing);
  assert.equal(flags.context_window, true);
  assert.equal(flags.max_tokens, true);

  const parameters: ModelParameters = {
    context_window: 1048576,
    max_output_tokens: 393216,
    provenance,
  };
  assert.deepEqual(
    previewParameterUpdate({ existing, parameters, service: "llm" }).changes,
    [],
  );
  const restored = previewParameterUpdate({
    existing,
    parameters,
    service: "llm",
    restoreAuto: ["context_window", "max_tokens"],
  });
  assert.deepEqual(
    restored.changes.map((change) => change.field).sort(),
    ["context_window", "max_tokens"],
  );
  assert.equal(restored.updates.context_window, "1048576");
  assert.equal(restored.updates.max_tokens, "393216");

  const cleared = {
    id: "m2",
    name: "Cleared",
    model: "deepseek-flash",
    parameter_overrides: { context_window: true, max_tokens: true },
  };
  assert.deepEqual(
    previewParameterUpdate({ existing: cleared, parameters, service: "llm" }).changes,
    [],
  );
});

test("positiveInteger rejects unsafe and non-integer numbers", () => {
  assert.equal(positiveInteger(Number.MAX_SAFE_INTEGER + 1), undefined);
  assert.equal(positiveInteger(Number.NaN), undefined);
  assert.equal(positiveInteger(Infinity), undefined);
  assert.equal(positiveInteger("1024"), 1024);
});

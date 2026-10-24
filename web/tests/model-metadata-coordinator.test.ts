import assert from "node:assert/strict";
import test from "node:test";
import { initialCatalogParameters, previewParameterUpdate } from "../lib/model-metadata";

test("LLM import keeps simultaneous input and output limits", () => {
  const value = initialCatalogParameters("llm", { max_input_tokens: 200000, max_output_tokens: 32768 });
  assert.equal(value.max_input_tokens, "200000");
  assert.equal(value.max_tokens, "32768");
  assert.equal(value.context_window, undefined);
});

test("embedding metadata refresh applies choices and automatic request options without dimension change", () => {
  const result = previewParameterUpdate({
    existing: { id: "m", name: "M", model: "e", dimension: "1024", send_dimensions: true,
      parameter_overrides: { dimension: false, send_dimensions: false } },
    service: "embedding", parameters: { default_dimensions: 1024,
      supported_dimensions: [1024, 512], supports_dimensions_parameter: false },
  });
  assert.equal(result.updates.send_dimensions, false);
  assert.equal(result.updates.supported_dimensions, "1024,512");
  assert.equal(result.updates.provider_metadata?.parameters.default_dimensions, 1024);
  assert.equal(result.updates.dimension, undefined);
});

test("restore automatic works for an unchanged dimension", () => {
  const result = previewParameterUpdate({
    existing: { id: "m", name: "M", model: "e", dimension: "1024", parameter_overrides: { dimension: true } },
    service: "embedding", parameters: { default_dimensions: 1024 }, restoreAuto: ["dimension"],
  });
  assert.equal(result.updates.parameter_overrides?.dimension, false);
});

test("manual request options remain until explicitly restored", () => {
  const args = { existing: { id: "m", name: "M", model: "e", send_dimensions: true,
    parameter_overrides: { send_dimensions: true } }, service: "embedding" as const,
    parameters: { supports_dimensions_parameter: false } };
  assert.equal(previewParameterUpdate(args).updates.send_dimensions, undefined);
  assert.equal(previewParameterUpdate({ ...args, restoreAuto: ["send_dimensions"] }).updates.send_dimensions, false);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  llmOptionLabel,
  llmOptionTitle,
  type LLMOption,
} from "../lib/llm-options";

function option(overrides: Partial<LLMOption> = {}): LLMOption {
  return {
    profile_id: "p1",
    model_id: "m1",
    profile_name: "DeepSeek",
    model_name: "DeepSeek V4.1 Flash",
    model: "deepseek-flash",
    provider: "deepseek",
    provider_label: "DeepSeek",
    is_active_default: false,
    ...overrides,
  };
}

test("custom name wins over the call id", () => {
  assert.equal(llmOptionLabel(option()), "DeepSeek V4.1 Flash");
});

test("blank or whitespace name falls back to the real model id", () => {
  assert.equal(llmOptionLabel(option({ model_name: "   " })), "deepseek-flash");
  assert.equal(llmOptionLabel(option({ model_name: "" })), "deepseek-flash");
});

test("title keeps name, model id, profile and provider visible", () => {
  const title = llmOptionTitle(option());
  assert.match(title, /DeepSeek V4\.1 Flash/);
  assert.match(title, /deepseek-flash/);
  assert.match(title, /DeepSeek/);
});

test("renaming does not alter the call id or selection key", () => {
  const renamed = option({ model_name: "My Flash" });
  assert.equal(llmOptionLabel(renamed), "My Flash");
  assert.equal(renamed.model, "deepseek-flash");
  assert.equal(renamed.model_id, "m1");
});

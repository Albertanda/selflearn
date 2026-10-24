import assert from "node:assert/strict";
import test from "node:test";

import type { LLMOption } from "../lib/llm-options";
import {
  findOptionGroup,
  groupLLMOptions,
  modelOptionSource,
  searchLLMOptions,
} from "../lib/model-picker-groups";

function option(overrides: Partial<LLMOption>): LLMOption {
  return {
    profile_id: "p1",
    model_id: "m1",
    profile_name: "DeepSeek",
    model_name: "Same Name",
    model: "deepseek-flash",
    provider: "deepseek",
    provider_label: "DeepSeek",
    is_active_default: false,
    ...overrides,
  };
}

test("identical model names from different connections stay in separate groups", () => {
  const groups = groupLLMOptions([
    option({ profile_id: "p-official", model_id: "m-official" }),
    option({
      profile_id: "p-aliyun",
      model_id: "m-aliyun",
      profile_name: "Aliyun",
      provider: "dashscope",
      provider_label: "阿里云百炼（千问 / DashScope）",
      model: "deepseek-v4.1-flash",
    }),
  ]);
  assert.equal(groups.length, 2);
  assert.deepEqual(
    groups.map((group) => group.profileId),
    ["p-official", "p-aliyun"],
  );
  assert.equal(groups.every((group) => group.options.length === 1), true);
});

test("same vendor with two profiles is not merged and names the connection", () => {
  const groups = groupLLMOptions([
    option({ profile_id: "p-a", profile_name: "Work key" }),
    option({ profile_id: "p-b", profile_name: "Personal key" }),
  ]);
  assert.equal(groups.length, 2);
  assert.deepEqual(
    groups.map((group) => group.connectionLabel),
    ["DeepSeek · Personal key", "DeepSeek · Work key"],
  );
  assert.equal(groups[0].providerLabel, "DeepSeek");
});

test("hidden current remains findable without making it visible", () => {
  const visible = [option({ profile_id: "p1", model_id: "m1" })];
  const hidden = [
    option({
      profile_id: "p1",
      model_id: "m2",
      model_name: "Hidden One",
      hidden: true,
    }),
  ];
  const groups = groupLLMOptions(visible, hidden);
  assert.equal(groups[0].options.length, 1);
  assert.equal(groups[0].hiddenOptions.length, 1);
  assert.equal(groups[0].count, 2);
  assert.equal(
    findOptionGroup(groups, { profile_id: "p1", model_id: "m2" })?.profileId,
    "p1",
  );
});

test("search results always retain their service source", () => {
  const groups = groupLLMOptions([
    option({ profile_id: "p1", model_id: "m1" }),
    option({
      profile_id: "p2",
      model_id: "m2",
      profile_name: "School",
      provider: "custom",
      provider_label: "Custom",
      model: "school-model",
      model_name: "Same Name",
    }),
  ]);
  const hits = searchLLMOptions(groups, "same");
  assert.equal(hits.length, 2);
  assert.deepEqual(
    hits.map((hit) => hit.source).sort(),
    ["Custom", "DeepSeek"],
  );
  assert.equal(hits.every((hit) => hit.group.profileId), true);
});

test("source falls back predictably when no provider label is present", () => {
  const raw = option({
    provider: "",
    provider_label: "",
    profile_name: "Fallback",
  });
  assert.equal(modelOptionSource(raw), "Fallback");
});

test("custom provider definitions drive the group icon and source without changing profile identity", () => {
  const groups = groupLLMOptions([
    option({
      profile_id: "p-custom",
      profile_name: "School gateway key",
      provider: "custom",
      provider_label: "学校网关",
      provider_icon: { kind: "emoji", value: "🏫" },
      custom_provider_id: "cp_1",
    }),
  ]);
  assert.equal(groups[0].providerLabel, "学校网关");
  assert.deepEqual(groups[0].providerIcon, { kind: "emoji", value: "🏫" });
  assert.equal(groups[0].customProviderId, "cp_1");
  assert.equal(groups[0].profileId, "p-custom");
  assert.equal(groups[0].connectionLabel, "学校网关 · School gateway key");
});

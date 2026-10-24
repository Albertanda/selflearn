import assert from "node:assert/strict";
import test from "node:test";

import {
  INHERIT_REASONING,
  modelDefaultReasoningChoices,
  parseReasoningControls,
  parseReasoningOverride,
  reasoningChoiceLabel,
  reasoningChoices,
  sameReasoningOverride,
  type ReasoningControls,
} from "../lib/reasoning-controls";

const DEEPSEEK: ReasoningControls = {
  supported: true,
  control: "effort",
  levels: ["low", "high", "max"],
  can_disable: true,
  default_level: "high",
  aliases: { minimal: "low", medium: "high", xhigh: "high", ultra: "max" },
  source: {
    kind: "official_docs",
    source_url: "https://api-docs.deepseek.com/guides/thinking_mode/",
    checked_at: "2026-10-24T00:00:00.000Z",
  },
};

test("DeepSeek native levels are complete and minimal is not off", () => {
  const values = reasoningChoices(DEEPSEEK).map((choice) => choice.value);
  assert.deepEqual(values, [
    "inherit",
    "provider_default",
    "effort:low",
    "effort:high",
    "effort:max",
    "effort:none",
  ]);
  const minimal = reasoningChoices(DEEPSEEK, {
    mode: "effort",
    effort: "minimal",
  }).find((choice) => choice.override.effort === "minimal");
  assert.equal(minimal?.mappedTo, "low");
  assert.match(minimal?.label ?? "", /→ Low/);
});

test("inherit and provider default are distinct selections", () => {
  assert.equal(sameReasoningOverride(INHERIT_REASONING, { mode: "inherit" }), true);
  assert.equal(
    sameReasoningOverride(INHERIT_REASONING, { mode: "provider_default" }),
    false,
  );
  assert.equal(reasoningChoiceLabel(DEEPSEEK, INHERIT_REASONING), "Inherit model setting");
  assert.equal(
    reasoningChoiceLabel(DEEPSEEK, { mode: "provider_default" }),
    "Provider default",
  );
});

test("budget controls label presets rather than inventing native effort", () => {
  const budget: ReasoningControls = {
    supported: true,
    control: "budget",
    levels: ["low", "medium", "high"],
    can_disable: true,
    default_level: null,
    aliases: { minimal: "low" },
  };
  const choices = modelDefaultReasoningChoices(budget, "");
  assert.deepEqual(
    choices.map((choice) => choice.value),
    ["", "low", "medium", "high", "none"],
  );
  assert.equal(choices[1].label, "Low (budget preset)");
});

test("unsupported and unknown controls expose no fabricated levels", () => {
  assert.deepEqual(
    reasoningChoices({ ...DEEPSEEK, supported: false, levels: [], can_disable: false }).map(
      (choice) => choice.value,
    ),
    ["inherit", "provider_default"],
  );
  assert.deepEqual(
    reasoningChoices(undefined).map((choice) => choice.value),
    ["inherit", "provider_default"],
  );
});

test("parser rejects malformed levels, aliases, and unsanitized sources", () => {
  assert.equal(
    parseReasoningControls({
      supported: true,
      control: "effort",
      levels: ["low", "nonsense"],
      can_disable: true,
      default_level: "low",
      aliases: {},
    }),
    undefined,
  );
  assert.equal(
    parseReasoningControls({
      supported: true,
      control: "effort",
      levels: ["low", "high"],
      can_disable: true,
      default_level: "low",
      aliases: { minimal: "medium" },
    }),
    undefined,
  );
  assert.equal(
    parseReasoningControls({
      ...DEEPSEEK,
      source: { ...DEEPSEEK.source!, source_url: "https://example.com/x?token=1" },
    })?.source?.source_url,
    "https://example.com/x",
  );
});

test("reasoning override parser rejects unknown fields and modes", () => {
  assert.deepEqual(parseReasoningOverride({ mode: "effort", effort: "high" }), {
    mode: "effort",
    effort: "high",
  });
  assert.equal(parseReasoningOverride({ mode: "effort" }), undefined);
  assert.equal(
    parseReasoningOverride({ mode: "inherit", effort: "high" }),
    undefined,
  );
  assert.equal(parseReasoningOverride({ mode: "auto" }), undefined);
  assert.equal(
    parseReasoningOverride({ mode: "inherit", unknown: true }),
    undefined,
  );
});

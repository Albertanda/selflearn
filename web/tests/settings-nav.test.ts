import assert from "node:assert/strict";
import test from "node:test";

import {
  SETTINGS_CATEGORIES,
  breadcrumbFor,
  isNavOnlyRoute,
  storagePathFor,
} from "../lib/settings-nav";

const models = SETTINGS_CATEGORIES.find((category) => category.key === "models");
assert.ok(models?.children);

test("Default models is the first model leaf and is administrator-only", () => {
  const first = models!.children![0];
  assert.equal(first.key, "default-models");
  assert.equal(first.href, "/settings/default-models");
  assert.deepEqual(first.label, { zh: "默认模型", en: "Default models" });
  assert.equal(first.adminOnly, true);
});

test("Chinese LLM leaf is the unified large-language-model name", () => {
  const llm = models!.children!.find((leaf) => leaf.key === "llm");
  assert.ok(llm);
  assert.equal(llm!.label.zh, "大语言模型（LLM）");
  assert.match(llm!.blurb.zh, /默认/);
});

test("breadcrumb follows the model hub order and names", () => {
  const crumbs = breadcrumbFor("/settings/default-models");
  assert.deepEqual(
    crumbs.map((crumb) => crumb.label.zh),
    ["设置", "模型", "默认模型"],
  );
  const llm = breadcrumbFor("/settings/llm");
  assert.deepEqual(
    llm.map((crumb) => crumb.label.zh),
    ["设置", "模型", "大语言模型（LLM）"],
  );
});

test("default models owns its save action and hides the draft toolbar", () => {
  assert.equal(isNavOnlyRoute("/settings/default-models"), true);
  assert.equal(
    storagePathFor("/settings/default-models"),
    "data/user/settings/model_catalog.json",
  );
  assert.equal(isNavOnlyRoute("/settings/llm"), false);
});

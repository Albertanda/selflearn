import assert from "node:assert/strict";
import test from "node:test";

import {
  hasUsableLLMModels,
  invalidateLLMOptionsCache,
  listLLMOptions,
} from "../lib/llm-options";

function mockFetch(payload: unknown) {
  return async () =>
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
}

test("hidden_options are separated from new selections without revoking usability", async () => {
  const original = globalThis.fetch;
  (globalThis as { window?: unknown }).window = {
    location: { pathname: "/home", href: "" },
  };
  globalThis.fetch = mockFetch({
    active: { profile_id: "p1", model_id: "m1" },
    options: [
      { profile_id: "p1", model_id: "m1", profile_name: "P", model_name: "M1", model: "m1", provider: "openai", is_active_default: true },
    ],
    hidden_options: [
      { profile_id: "p1", model_id: "m2", profile_name: "P", model_name: "M2", model: "m2", provider: "openai", is_active_default: false, visible_in_picker: false },
    ],
    has_usable_models: true,
  });
  try {
    invalidateLLMOptionsCache();
    const payload = await listLLMOptions({ force: true });
    assert.deepEqual(payload.options.map((item) => item.model_id), ["m1"]);
    assert.deepEqual(payload.hidden_options?.map((item) => item.model_id), ["m2"]);
    assert.equal(payload.hidden_options?.[0].hidden, true);
    assert.equal(payload.has_usable_models, true);
    assert.equal(hasUsableLLMModels(payload), true);
  } finally {
    invalidateLLMOptionsCache();
    globalThis.fetch = original;
    delete (globalThis as { window?: unknown }).window;
  }
});

test("an old fixture without new fields keeps the exact old response shape", async () => {
  const original = globalThis.fetch;
  (globalThis as { window?: unknown }).window = {
    location: { pathname: "/home", href: "" },
  };
  globalThis.fetch = mockFetch({ active: null, options: [] });
  try {
    invalidateLLMOptionsCache();
    const payload = await listLLMOptions({ force: true });
    assert.deepEqual(payload, { active: null, options: [] });
  } finally {
    invalidateLLMOptionsCache();
    globalThis.fetch = original;
    delete (globalThis as { window?: unknown }).window;
  }
});

test("all authorized models hidden still yields has_usable_models=true", async () => {
  const original = globalThis.fetch;
  (globalThis as { window?: unknown }).window = {
    location: { pathname: "/home", href: "" },
  };
  globalThis.fetch = mockFetch({
    active: null,
    options: [],
    hidden_options: [
      { profile_id: "p1", model_id: "m1", profile_name: "P", model_name: "M1", model: "m1", provider: "", is_active_default: false, visible_in_picker: false },
    ],
    has_usable_models: true,
  });
  try {
    invalidateLLMOptionsCache();
    const payload = await listLLMOptions({ force: true });
    assert.deepEqual(payload.options, []);
    assert.equal(payload.hidden_options?.length, 1);
    assert.equal(hasUsableLLMModels(payload), true);
  } finally {
    invalidateLLMOptionsCache();
    globalThis.fetch = original;
    delete (globalThis as { window?: unknown }).window;
  }
});

test("derives hidden options even if a transitional server only marks the model", async () => {
  const original = globalThis.fetch;
  (globalThis as { window?: unknown }).window = {
    location: { pathname: "/home", href: "" },
  };
  globalThis.fetch = mockFetch({
    active: null,
    options: [
      { profile_id: "p1", model_id: "m1", profile_name: "P", model_name: "M1", model: "m1", provider: "", is_active_default: false, visible_in_picker: false },
    ],
  });
  try {
    invalidateLLMOptionsCache();
    const payload = await listLLMOptions({ force: true });
    assert.deepEqual(payload.options, []);
    assert.equal(payload.hidden_options?.[0].model_id, "m1");
    assert.equal(payload.has_usable_models, true);
  } finally {
    invalidateLLMOptionsCache();
    globalThis.fetch = original;
    delete (globalThis as { window?: unknown }).window;
  }
});

test("a late options response cannot overwrite the cache after a save", async () => {
  const original = globalThis.fetch;
  (globalThis as { window?: unknown }).window = {
    location: { pathname: "/settings", href: "" },
  };
  let resolveOld: ((value: Response) => void) | undefined;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) {
      return new Promise<Response>((resolve) => {
        resolveOld = resolve;
      });
    }
    return new Response(
      JSON.stringify({
        active: { profile_id: "p1", model_id: "m1" },
        options: [
          {
            profile_id: "p1",
            model_id: "m1",
            profile_name: "P",
            model_name: "New name",
            model: "model-1",
            provider: "custom",
            is_active_default: true,
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };
  try {
    invalidateLLMOptionsCache();
    const oldRequest = listLLMOptions({ force: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    invalidateLLMOptionsCache();
    const saved = await listLLMOptions({ force: true });
    assert.equal(saved.options[0].model_name, "New name");

    resolveOld?.(
      new Response(
        JSON.stringify({
          active: { profile_id: "p1", model_id: "m1" },
          options: [
            {
              profile_id: "p1",
              model_id: "m1",
              profile_name: "P",
              model_name: "Old name",
              model: "model-1",
              provider: "custom",
              is_active_default: true,
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await oldRequest;

    const cached = await listLLMOptions();
    assert.equal(cached.options[0].model_name, "New name");
  } finally {
    invalidateLLMOptionsCache();
    globalThis.fetch = original;
    delete (globalThis as { window?: unknown }).window;
  }
});

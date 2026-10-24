import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

import type { CatalogProfile } from "../components/settings/SettingsContext";
import type { useModelDiscovery } from "../components/settings/useModelDiscovery";
import { parseDiscoveryResponse } from "../lib/model-discovery";
import { INITIAL_MODEL_DISCOVERY_STATE, reduceModelDiscoveryState } from "../lib/model-discovery-state";

function response(id: string) {
  return { schema_version: 1, service: "llm", profile_id: "p", status: "ok", models: [
    { id, name: id, services: ["llm"], classification: "provider", runtime_compatibility: "supported", source: "remote" },
  ], cache: { state: "none" }, complete: true, error: null };
}

test("a semantic refresh failure preserves previous candidates even without disk cache", () => {
  const state = { ...INITIAL_MODEL_DISCOVERY_STATE, requestKey: "refresh", response: parseDiscoveryResponse(response("old")) };
  const failed = reduceModelDiscoveryState(state, { type: "request-succeeded", requestKey: "refresh", response: parseDiscoveryResponse({ ...response("unused"), status: "error", models: [], error: { code: "UNAVAILABLE", message: "retry", retryable: true } }) });
  assert.equal(failed.response?.models[0]?.id, "old");
  assert.equal(failed.response?.status, "error");
});

// Execute the real hook with deferred HTTP and controlled React effects.
// In particular, saved keys are masked in both old and new catalog snapshots.
function harness() {
  const slots: any[] = [];
  let cursor = 0, dirty = false;
  let effects: (() => void)[] = [];
  let saved: CatalogProfile = { id: "p", name: "Profile", binding: "custom", base_url: "https://model.invalid/v1", api_key: "***", api_version: "", models: [] };
  let profile = saved;
  let value: ReturnType<typeof useModelDiscovery>;
  const requests: { body: any; resolve: (value: Response) => void }[] = [];
  const same = (a?: unknown[], b?: unknown[]) => Boolean(a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i])));
  const react = {
    useReducer(reducer: any, initial: any) {
      const i = cursor++;
      slots[i] ??= { value: initial };
      return [slots[i].value, (action: any) => {
        const next = reducer(slots[i].value, action);
        if (!Object.is(next, slots[i].value)) dirty = true;
        slots[i].value = next;
      }];
    },
    useRef(initial: any) { const i = cursor++; slots[i] ??= { current: initial }; return slots[i]; },
    useCallback(fn: any, deps: unknown[]) { const i = cursor++; if (!same(slots[i]?.deps, deps)) slots[i] = { fn, deps }; return slots[i].fn; },
    useEffect(fn: any, deps?: unknown[]) {
      const i = cursor++;
      if (!same(slots[i]?.deps, deps)) {
        const previous = slots[i]; slots[i] = { deps };
        effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); });
      }
    },
  };
  const compiled = ts.transpileModule(readFileSync(path.join(process.cwd(), "components/settings/useModelDiscovery.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS } });
  const mod = { exports: {} as { useModelDiscovery: typeof useModelDiscovery } };
  const boundary = (name: string) => {
    if (name === "react") return react;
    if (name === "@/lib/api") return {
      apiUrl: (url: string) => url,
      apiFetch: (_url: string, init: RequestInit) => new Promise<Response>((resolve) => requests.push({ body: JSON.parse(String(init.body)), resolve })),
    };
    return require(name);
  };
  new Function("require", "module", "exports", compiled.outputText)(boundary, mod, mod.exports);
  const render = () => {
    for (let n = 0; n < 20; n++) {
      cursor = 0; dirty = false; effects = [];
      value = mod.exports.useModelDiscovery({ service: "llm", profile, savedProfile: saved });
      effects.forEach((effect) => effect());
      if (!dirty) return;
    }
    throw new Error("hook failed to settle");
  };
  return {
    render, requests, current: () => value,
    editKey() { profile = { ...saved, api_key: "new.fake.key" }; render(); },
    saveKey() { saved = { ...saved }; profile = saved; render(); },
    async finish(index: number, payload: unknown) {
      requests[index].resolve(new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } }));
      await new Promise(setImmediate); render();
    },
    unmount() { slots.forEach((slot) => slot?.cleanup?.()); },
  };
}

test("saving a rotated masked key cannot reuse the old in-flight catalog", async () => {
  const h = harness();
  h.render();
  assert.equal(h.requests.length, 1);
  h.editKey();
  assert.equal(h.requests.length, 1, "typing must not issue requests");
  h.saveKey();
  assert.equal(h.requests.length, 2, "a newly saved masked credential needs its own request");
  await h.finish(0, response("old-account"));
  assert.notEqual(h.current().response?.models[0]?.id, "old-account");
  await h.finish(1, response("new-account"));
  assert.equal(h.current().response?.models[0]?.id, "new-account");
  h.unmount();
});

test("explicit retry bypasses the automatic failure cooldown", async () => {
  const h = harness();
  h.render();
  await h.finish(0, { ...response("unused"), status: "error", models: [], error: { code: "RATE_LIMITED", message: "retry", retryable: true } });
  const pending = h.current().retry();
  assert.equal(h.requests[1].body.mode, "refresh");
  await h.finish(1, response("recovered"));
  await pending;
  h.unmount();
});

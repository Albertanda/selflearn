import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const ROOT = process.cwd();
const read = (rel: string) => readFileSync(path.join(ROOT, rel), "utf8");

test("both existing subject pages use the shared asynchronous ASR panel", () => {
  const detail = read("app/(workspace)/subjects/[id]/page.tsx");
  const list = read("app/(workspace)/subjects/page.tsx");
  assert.match(detail, /AsrJobPanel/);
  assert.match(list, /AsrJobPanel/);
  assert.doesNotMatch(detail, /uploadAudioAction/);
  assert.match(list, /课堂录音/);
  assert.match(list, /文档与录音不能混在同一批/);
});

test("the panel keeps accepted/progress/failure/completion copy distinct", () => {
  const panel = read("components/subjects/AsrJobPanel.tsx");
  assert.match(panel, /data-asr-job-id/);
  assert.match(panel, /data-asr-status/);
  assert.match(panel, /取消转写/);
  assert.match(panel, /继续未完成片段/);
  assert.match(panel, /使用转写结果/);
  assert.match(panel, /role="progressbar"/);
  assert.doesNotMatch(panel, /转写完成/);
  const client = read("lib/asr-jobs.ts");
  assert.match(client, /已接收/);
  assert.match(client, /不会自动建立索引/);
  assert.match(client, /materials\/lecture/);
});

test("the hook aborts local polls, guards revisions and never auto-posts/retries", () => {
  const hook = read("hooks/useSubjectAsrJobs.ts");
  assert.match(hook, /AbortController/);
  assert.match(hook, /next\.revision < previous\.revision/);
  assert.match(hook, /ASR_JOB_POLL_WARNING/);
  assert.match(hook, /retryablePollFailure/);
  // The mount path only lists jobs; it does not create or retry.
  const refresh = hook.slice(hook.indexOf("const refresh"), hook.indexOf("const reset"));
  assert.doesNotMatch(refresh, /createAsrJob|retryAsrJob/);
  assert.doesNotMatch(hook, /setInterval/);
});

test("the dedicated App Router route forwards both streaming POST and recovered GET", () => {
  const route = read("app/api/v1/subjects/[subjectId]/asr/jobs/route.ts");
  assert.match(route, /export function POST/);
  assert.match(route, /export function GET/);
  const proxy = read("proxy.ts");
  assert.match(proxy, /api\/v1\/subjects\/\[\^\/\]\+\/asr\/jobs\$/);
});

// Execute the production hook with controlled React scheduling and deferred
// API boundaries. This catches late completions; source matching cannot.
import ts from "typescript";
import type { UseSubjectAsrJobs } from "../hooks/useSubjectAsrJobs";
import type { AsrJobView } from "../lib/asr-jobs";

function hookHarness(action: "cancel" | "retry") {
  const slots: any[] = [];
  let cursor = 0;
  let dirty = false;
  let subjectId = "a";
  let effects: (() => void)[] = [];
  let value: UseSubjectAsrJobs;
  let uploads = 0;
  let resolveAction!: (job: AsrJobView) => void;
  const delayed = new Promise<AsrJobView>((resolve) => { resolveAction = resolve; });
  const same = (a?: unknown[], b?: unknown[]) => !!a && !!b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const react = {
    useState(initial: any) {
      const i = cursor++;
      slots[i] ??= { value: initial };
      return [slots[i].value, (next: any) => { if (!Object.is(slots[i].value, next)) dirty = true; slots[i].value = next; }];
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
  const job = (sid: string): AsrJobView => ({
    job_id: sid === "a" ? "00000000000040008000000000000001" : "00000000000040008000000000000002",
    subject_id: sid, status: action === "retry" ? "failed" : "running", phase: "transcribing", revision: 1,
    created_at: "x", updated_at: "x", files: [],
    progress: { files_total: 0, chunks_total: 0, chunks_completed: 0, audio_total_ms: 0, audio_completed_ms: 0 },
    error: null, can_retry: action === "retry", can_cancel: action === "cancel", result_available: false,
  });
  const compiled = ts.transpileModule(read("hooks/useSubjectAsrJobs.ts"), { compilerOptions: { module: ts.ModuleKind.CommonJS } });
  const mod = { exports: {} as { useSubjectAsrJobs?: (o: any) => UseSubjectAsrJobs } };
  const boundary = (name: string) => {
    if (name === "react") return react;
    if (name === "@/lib/subject-results") return require("../lib/subject-results");
    if (name === "@/lib/asr-jobs") return {
      ...require("../lib/asr-jobs"), listAsrJobs: async (_r: any, sid: string) => [job(sid)],
      cancelAsrJob: () => delayed, retryAsrJob: () => delayed,
    };
    return require(name);
  };
  new Function("require", "module", "exports", "setTimeout", "clearTimeout", compiled.outputText)(boundary, mod, mod.exports, () => 1, () => {});
  const render = () => {
    for (let n = 0; n < 20; n++) {
      dirty = false; cursor = 0; effects = [];
      value = mod.exports.useSubjectAsrJobs!({ subjectId, request: async () => { uploads += 1; return new Response("{}"); } });
      effects.forEach((fn) => fn());
      if (!dirty) return;
    }
    throw new Error("hook did not settle");
  };
  return {
    render, current: () => value, uploads: () => uploads,
    async settle() { await new Promise(setImmediate); render(); },
    switchSubject() { subjectId = "b"; render(); },
    finishOld() { resolveAction({ ...job("a"), revision: 2 }); },
    unmount() { slots.forEach((s) => s?.cleanup?.()); },
  };
}

for (const action of ["cancel", "retry"] as const) {
  test(`late ${action} response cannot replace the newly selected subject`, async () => {
    const h = hookHarness(action);
    h.render(); await h.settle();
    assert.equal(h.current().job?.subject_id, "a");
    const pending = h.current()[action]();
    h.switchSubject(); await h.settle();
    assert.equal(h.current().job?.subject_id, "b");
    h.finishOld(); await pending; await h.settle();
    assert.equal(h.current().job?.subject_id, "b");
    assert.equal(h.current().busy, false);
    h.unmount();
  });
}

test("an active job keeps its poll ownership and prevents a second upload", async () => {
  const h = hookHarness("cancel");
  h.render(); await h.settle();
  assert.equal(h.current().job?.status, "running");
  assert.equal(await h.current().start([new File(["x"], "another.wav")]), false);
  assert.equal(h.uploads(), 0);
  assert.equal(h.current().job?.subject_id, "a");
  h.unmount();
});

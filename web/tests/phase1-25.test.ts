/**
 * P1-25 — subject scope: restore, clear, session switch and capability config
 * merge (C08 / C13).
 *
 * The behaviour under test is the code the UI actually runs: the session scope
 * transitions of ``UnifiedChatContext``'s reducer, the merge that ``page.tsx``
 * performs last in ``handleSend``, and the replay rule used by retry / edit /
 * replay. Everything is a pure function from ``lib/subject-scope`` so it runs
 * under ``node --test`` (compiled by ``scripts/run-node-tests.mjs``) with no
 * browser, and ``tsc`` proves the call sites type-check.
 *
 * The one thing a pure suite cannot see is whether the UI *calls* these
 * functions at all (a helper nobody uses would pass every test above), so the
 * last test checks the wiring. It is a supplement, not the evidence: every
 * scenario above is real behaviour.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  applySessionScope,
  mergeSubjectIntoConfig,
  newSessionScope,
  normalizeSubject,
  readSnapshotScope,
  resolveSendSubject,
  revalidatedScope,
  subjectForRequest,
  subjectFromConfig,
  subjectSendable,
  type SubjectSessionScope,
} from "../lib/subject-scope";
import { buildQuizWSConfig, type DeepQuestionFormConfig } from "../lib/quiz-types";
import { buildResearchWSConfig } from "../lib/research-types";

const SUBJECT_A = "科目a";
const SUBJECT_B = "科目b";

/** Enter a session, then apply its stored preferences (the real two steps). */
function loaded(preferences: unknown): SubjectSessionScope {
  const entering = applySessionScope(newSessionScope(), { type: "loading" });
  return applySessionScope(entering, { type: "load", preferences });
}

// ---------------------------------------------------------------------------
// 新会话 / 恢复 / 清空 / gate
// ---------------------------------------------------------------------------
test("a new session starts with no subject and is usable immediately", () => {
  const scope = newSessionScope();
  assert.equal(scope.subjectId, null);
  assert.equal(subjectSendable(scope), true);
  assert.equal(subjectForRequest(scope), null);
});

test("entering a session drops the previous scope and closes the send gate", () => {
  const previous = applySessionScope(newSessionScope(), {
    type: "select",
    value: "科目上一轮",
  });
  const entering = applySessionScope(previous, { type: "loading" });

  assert.equal(entering.subjectId, null, "旧 scope 被带进了新会话");
  assert.equal(subjectSendable(entering), false, "hydration 完成前不应允许发送");
});

test("the session's stored subject is restored on load — and absence means none", () => {
  assert.equal(loaded({ subject_id: SUBJECT_A }).subjectId, SUBJECT_A);
  assert.equal(subjectSendable(loaded({ subject_id: SUBJECT_A })), true);

  // 存储里没有这个键 = 这个会话没有科目，不是"沿用上一个会话"。
  const never = loaded({ tools: ["rag"], capability: "chat" });
  assert.equal(never.subjectId, null);
  assert.equal(never.subjectHydrated, true);

  // 历史遗留的 "" 视为清空。
  assert.equal(loaded({ subject_id: "" }).subjectId, null);
  assert.equal(loaded({ subject_id: "   " }).subjectId, null);
  // 非字符串不是合法 scope，按"无科目"处理而不是抛错。
  assert.equal(loaded({ subject_id: 42 }).subjectId, null);
});

test("clearing keeps an explicit null (never a dropped key)", () => {
  const scope = applySessionScope(loaded({ subject_id: SUBJECT_A }), {
    type: "select",
    value: "",
  });
  assert.equal(scope.subjectId, null);
  assert.equal(subjectSendable(scope), true, "清空不改变 hydration");

  const config = mergeSubjectIntoConfig({ depth: "standard" }, subjectForRequest(scope));
  assert.equal("subject_id" in config, true, "清空必须保留属性存在性");
  assert.equal(config.subject_id, null, "清空必须发明确 null");
  assert.deepEqual(subjectFromConfig(config), { hasScope: true, value: null });
});

test("choosing a subject keeps the gate closed until hydration finishes", () => {
  const entering = applySessionScope(newSessionScope(), { type: "loading" });
  const picked = applySessionScope(entering, { type: "select", value: SUBJECT_A });
  assert.equal(picked.subjectId, SUBJECT_A);
  assert.equal(subjectSendable(picked), false, "未完成恢复就允许发送了");
});

// ---------------------------------------------------------------------------
// 会话切换与过期响应
// ---------------------------------------------------------------------------
test("switching sessions does not carry the previous subject along", () => {
  const sessionOne = loaded({ subject_id: SUBJECT_A });
  const enteringTwo = applySessionScope(sessionOne, { type: "loading" });
  const sessionTwo = applySessionScope(enteringTwo, {
    type: "load",
    preferences: { subject_id: SUBJECT_B },
  });

  assert.equal(sessionOne.subjectId, SUBJECT_A, "会话一的 scope 被改写");
  assert.equal(sessionTwo.subjectId, SUBJECT_B);
  assert.notEqual(sessionTwo.subjectId, sessionOne.subjectId);

  // 切回一个"没有科目"的会话也一样：不继承另一个会话的值。
  const backToEmpty = applySessionScope(
    applySessionScope(sessionTwo, { type: "loading" }),
    { type: "load", preferences: {} },
  );
  assert.equal(backToEmpty.subjectId, null);
});

test("a stale response only fills its own session, never the new one", () => {
  // 用户切到会话二，会话一的响应晚到：它只能写会话一自己的 state。
  const sessionTwo = loaded({ subject_id: SUBJECT_B });
  const lateSessionOne = revalidatedScope(
    applySessionScope(sessionTwo, { type: "loading" }),
    { subject_id: SUBJECT_A },
  );
  // （上面这一步模拟"延迟响应落在它自己的 entry 上"：entry 是新建的、
  //  未 hydrate 的会话一，因此它被填充而不会触碰会话二。）
  assert.equal(lateSessionOne.subjectId, SUBJECT_A);
  assert.equal(sessionTwo.subjectId, SUBJECT_B, "过期响应覆盖了新会话的 scope");
});

test("a background refresh never overwrites a choice made in the composer", () => {
  const picked = applySessionScope(loaded({ subject_id: SUBJECT_A }), {
    type: "select",
    value: SUBJECT_B,
  });
  const refreshed = revalidatedScope(picked, { subject_id: SUBJECT_A });
  assert.equal(refreshed.subjectId, SUBJECT_B, "后台刷新把用户刚选的科目改回去了");

  // 但一个还没 hydrate 的 entry 必须被填充，否则发送门永远不会打开。
  const unhydrated = applySessionScope(newSessionScope(), { type: "loading" });
  const filled = revalidatedScope(unhydrated, { subject_id: SUBJECT_A });
  assert.equal(filled.subjectId, SUBJECT_A);
  assert.equal(subjectSendable(filled), true);
});

// ---------------------------------------------------------------------------
// 能力 config 合并
// ---------------------------------------------------------------------------
const QUIZ_CONFIG: DeepQuestionFormConfig = {
  mode: "custom",
  question_types: ["choice"],
  num_questions: 5,
  difficulty: "medium",
  per_type_counts: {},
  paper_path: "",
  max_questions: 20,
  topic: "三角函数",
};

test("the subject is merged last and capability fields survive", () => {
  const quiz = buildQuizWSConfig(QUIZ_CONFIG);
  const merged = mergeSubjectIntoConfig(quiz, SUBJECT_A);

  for (const [key, value] of Object.entries(quiz)) {
    assert.deepEqual(merged[key], value, `能力字段 ${key} 被 subject 合并覆盖`);
  }
  assert.equal(merged.subject_id, SUBJECT_A);

  // 反例（原来的 bug 形状）：先把 subject 放进 config，随后被能力 config
  // 整个覆盖赋值 —— subject 就丢了。这正是"最后合并"要避免的。
  let wrongOrder: Record<string, unknown> | undefined = {
    subject_id: SUBJECT_A,
  };
  wrongOrder = buildQuizWSConfig(QUIZ_CONFIG);
  assert.equal("subject_id" in wrongOrder, false, "反例本身不成立");

  const research = buildResearchWSConfig({
    mode: "report",
    depth: "standard",
    language: "zh",
    topic: "光合作用",
  } as never);
  const researchMerged = mergeSubjectIntoConfig(research, SUBJECT_B);
  for (const [key, value] of Object.entries(research)) {
    assert.deepEqual(researchMerged[key], value);
  }
  assert.equal(researchMerged.subject_id, SUBJECT_B);
});

test("visualize-shaped configs keep their fields and get an explicit null", () => {
  // visualize-types 通过 "@/lib/..." 运行时别名导入，node 测试无法直接加载，
  // 因此这里用同形状的对象验证合并规则本身（真实调用点由 tsc 校验）。
  const visualize = { render_mode: "svg", style: "hand-drawn", language: "zh" };
  const merged = mergeSubjectIntoConfig(visualize, null);
  assert.deepEqual(merged, { ...visualize, subject_id: null });
  assert.equal("subject_id" in merged, true);
});

test("a config-less send still carries the subject key", () => {
  const merged = mergeSubjectIntoConfig(undefined, SUBJECT_A);
  assert.deepEqual(merged, { subject_id: SUBJECT_A });
  assert.deepEqual(mergeSubjectIntoConfig(null, null), { subject_id: null });
});

// ---------------------------------------------------------------------------
// replay（retry / edit / 重新生成）
// ---------------------------------------------------------------------------
test("a replayed turn keeps its own scope even after the user picked another", () => {
  const scopeNow = loaded({ subject_id: SUBJECT_B });
  const snapshot = { content: "q", subject_id: SUBJECT_A };

  assert.equal(resolveSendSubject(scopeNow, snapshot), SUBJECT_A);
  assert.equal(scopeNow.subjectId, SUBJECT_B, "replay 改写了当前选择");
});

test("a replayed explicit null is not replaced by the current subject", () => {
  const scopeNow = loaded({ subject_id: SUBJECT_B });
  const snapshot = { content: "q", subject_id: null };

  assert.equal(resolveSendSubject(scopeNow, snapshot), null);
  const merged = mergeSubjectIntoConfig({}, resolveSendSubject(scopeNow, snapshot));
  assert.equal("subject_id" in merged, true);
  assert.equal(merged.subject_id, null);
});

test("a legacy snapshot without a scope replays as no subject", () => {
  const scopeNow = loaded({ subject_id: SUBJECT_B });
  const legacy = { content: "q", capability: "chat" };

  assert.equal(resolveSendSubject(scopeNow, legacy), null, "旧快照被塞进了当前科目");
  assert.deepEqual(readSnapshotScope(legacy), { hasScope: false, value: null });
  assert.deepEqual(readSnapshotScope({ subject_id: null }), {
    hasScope: true,
    value: null,
  });
  // camelCase 兼容位置也要读。
  assert.deepEqual(readSnapshotScope({ subjectId: SUBJECT_A }), {
    hasScope: true,
    value: SUBJECT_A,
  });
});

test("a plain send (no replay) uses the session's own scope", () => {
  assert.equal(resolveSendSubject(loaded({ subject_id: SUBJECT_A })), SUBJECT_A);
  assert.equal(resolveSendSubject(loaded({})), null);
  assert.equal(resolveSendSubject(undefined), null);
});

test("normalizeSubject never turns a real identity into something else", () => {
  assert.equal(normalizeSubject(SUBJECT_A), SUBJECT_A);
  assert.equal(normalizeSubject("  " + SUBJECT_A + "  "), SUBJECT_A);
  assert.equal(normalizeSubject(""), null);
  assert.equal(normalizeSubject(null), null);
  assert.equal(normalizeSubject(undefined), null);
  assert.equal(normalizeSubject(0), null);
  // 大小写/中文本身不被改写（身份按原样比较）。
  assert.equal(normalizeSubject("Assignment-KB"), "Assignment-KB");
});

// ---------------------------------------------------------------------------
// 接线补充检查：UI 必须实际调用这些 helper
// ---------------------------------------------------------------------------
test("the chat UI calls these helpers (wiring supplement)", () => {
  // 编译产物在 web/dist/node-tests/tests/ 下，仓库 web/ 根在三级之上。
  const root = pathModule.resolve(__dirname, "..", "..", "..");
  const context = readFileSync(
    path.join(root, "context", "UnifiedChatContext.tsx"),
    "utf8",
  );
  const page = readFileSync(
    path.join(root, "app", "(workspace)", "home", "[[...sessionId]]", "page.tsx"),
    "utf8",
  );
  const selector = readFileSync(
    path.join(root, "components", "chat", "home", "SubjectSelector.tsx"),
    "utf8",
  );

  // 会话状态机：加载/切换/选择都走同一个纯函数。
  assert.match(context, /applySessionScope\(/);
  assert.match(context, /revalidatedScope\(/);
  assert.match(context, /subjectSendable\(session\)/);
  assert.match(context, /resolveSendSubject\(session, replaySnapshot\)/);
  // 发送前的 gate（hydration 未完成不发）。
  assert.match(page, /if \(!subjectHydrated\) return;/);
  // 能力 config 先构造、subject 最后合并。
  assert.match(page, /mergeSubjectIntoConfig\(config, subjectId\)/);
  // 选择器提供"无科目"这一项，并且它是一次显式清空。
  assert.match(selector, /onChange\(""\)/);
});

// ---------------------------------------------------------------------------
// R3/R4: the real provider wiring (hydrator, load callback, selector, warnings)
//
// The helpers above are pure, but the defects this round fixed lived in the
// *wiring*: the hydrator dropped the scope, two loads of one session could
// apply out of order, a new conversation did not invalidate an in-flight load,
// and the selector disappeared when the last subject was deleted. Those live in
// `UnifiedChatContext.tsx` / `SubjectSelector.tsx`, which cannot be imported
// here (they resolve `@/…` aliases at runtime). So this section extracts the
// actual function bodies from the real source with the TypeScript compiler and
// runs them with explicit bindings — the same technique the reviewer's probe
// uses — and asserts their real behaviour. No copy of the logic is kept here:
// if the source changes, these tests change with it.
// ---------------------------------------------------------------------------
import { readFileSync as readSource } from "node:fs";
import pathModule from "node:path";
import vm from "node:vm";
import ts from "typescript";

const WEB_ROOT = pathModule.resolve(__dirname, "..", "..", "..");
const PROVIDER_SOURCE = readSource(
  pathModule.join(WEB_ROOT, "context", "UnifiedChatContext.tsx"),
  "utf8",
);
const PROVIDER_FILE = ts.createSourceFile(
  "provider.tsx",
  PROVIDER_SOURCE,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);

function findNode(predicate: (node: ts.Node) => boolean): ts.Node {
  let found: ts.Node | undefined;
  const walk = (node: ts.Node): void => {
    if (!found && predicate(node)) found = node;
    if (!found) ts.forEachChild(node, walk);
  };
  walk(PROVIDER_FILE);
  assert.ok(found, "actual source symbol missing");
  return found as ts.Node;
}

function transpile(text: string): string {
  return ts.transpileModule(text, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
}

function moduleFrom(
  text: string,
  requireFn: (name: string) => unknown = require,
): Record<string, unknown> {
  const exports: Record<string, unknown> = {};
  const ctx = { exports, module: { exports }, require: requireFn };
  vm.runInNewContext(transpile(text), ctx);
  return (ctx.module as { exports: Record<string, unknown> }).exports;
}

function hydrateFunction(scopeModule: Record<string, unknown>) {
  const node = findNode(
    (candidate) =>
      ts.isFunctionDeclaration(candidate) &&
      candidate.name?.text === "hydrateRequestSnapshot",
  ) as ts.FunctionDeclaration;
  const body = node.getText(PROVIDER_FILE).replace(/^function hydrateRequestSnapshot/, "function");
  return vm.runInNewContext(transpile(`const hydrate=${body};hydrate;`), {
    asRecord: (x: unknown) =>
      x && typeof x === "object" && !Array.isArray(x) ? x : undefined,
    asStringArray: (x: unknown) => (Array.isArray(x) ? x : []),
    asNotebookReferences: () => [],
    asQuestionReferences: () => [],
    asMemoryReferences: () => [],
    normalizeBookReferences: () => [],
    asLLMSelection: () => undefined,
    parseReasoningOverride: (value: unknown) =>
      value && typeof value === "object" && "mode" in value ? value : undefined,
    scopeModule,
  }) as (message: unknown, content: string, attachments: unknown[]) => unknown;
}

function callback(name: string, ctx: Record<string, unknown>) {
  const declaration = findNode(
    (candidate) =>
      ts.isVariableDeclaration(candidate) && candidate.name.getText(PROVIDER_FILE) === name,
  ) as ts.VariableDeclaration;
  const initializer = declaration.initializer;
  assert.ok(initializer && ts.isCallExpression(initializer));
  const fn = initializer.arguments[0].getText(PROVIDER_FILE);
  return vm.runInNewContext(transpile(`(${fn})`), ctx) as (...args: never[]) => unknown;
}

/** The bindings `loadSession` closes over, with observable stubs. */
function loadHarness() {
  const pending: Array<(value: unknown) => void> = [];
  const rejections: Array<(error: unknown) => void> = [];
  const actions: Array<Record<string, unknown>> = [];
  const ctx = {
    latestLoadKeyRef: { current: null as unknown },
    stateRef: { current: { sessions: {} as Record<string, unknown> } },
    dispatch: (action: Record<string, unknown>) => actions.push(action),
    getSession: () =>
      new Promise((resolve, reject) => {
        pending.push(resolve as (value: unknown) => void);
        rejections.push(reject);
      }),
    hydrateMessages: (x: unknown) => x,
    asLLMSelection: () => undefined,
    asReasoningPreferences: () => ({}),
    llmSelectionKey: (selection: unknown) => {
      const value = selection as { profile_id?: string; model_id?: string } | null;
      return value?.profile_id && value?.model_id
        ? `${value.profile_id}:${value.model_id}`
        : "";
    },
    readStoredResponseLanguage: () => "en",
    normalizeSelectedBranches: () => ({}),
    sendThroughRunner: () => {},
    makeDraftKey: () => "draft-new",
  };
  return {
    pending,
    rejections,
    actions,
    ctx,
    load: callback("loadSession", ctx) as (id: string, options?: unknown) => Promise<unknown>,
    fresh: callback("newSession", ctx) as () => void,
  };
}

function session(id: string, subject: string | null) {
  return {
    id,
    session_id: id,
    messages: [],
    preferences: subject === null ? {} : { subject_id: subject },
  };
}

test("the real hydrator keeps the scope of a stored server snapshot", () => {
  const scope = moduleFrom(
    readSource(pathModule.join(WEB_ROOT, "lib", "subject-scope.ts"), "utf8"),
  );
  const hydrate = hydrateFunction(scope);

  const stored = {
    content: "q",
    knowledgeBases: [],
    subject_id: "scope-a",
    config: { subject_id: "scope-a" },
  };
  const hydrated = hydrate({ metadata: { request_snapshot: stored } }, "q", []) as Record<
    string,
    unknown
  >;
  // The canonical shape carries the scope at the top level, and replaying the
  // hydrated snapshot yields the *original* scope, not the composer's.
  assert.equal(hydrated.subject_id, "scope-a");
  assert.equal(
    (scope.resolveSendSubject as (...args: unknown[]) => unknown)(
      { subjectId: "scope-b", subjectHydrated: true },
      hydrated,
    ),
    "scope-a",
  );
});

test("the real hydrator keeps an explicit null and a camelCase scope", () => {
  const scope = moduleFrom(
    readSource(pathModule.join(WEB_ROOT, "lib", "subject-scope.ts"), "utf8"),
  );
  const hydrate = hydrateFunction(scope);

  const cleared = hydrate(
    { metadata: { request_snapshot: { content: "q", subject_id: null } } },
    "q",
    [],
  ) as Record<string, unknown>;
  assert.equal("subject_id" in cleared, true);
  assert.equal(cleared.subject_id, null);
  assert.equal(
    (scope.resolveSendSubject as (...args: unknown[]) => unknown)(
      { subjectId: "scope-b", subjectHydrated: true },
      cleared,
    ),
    null,
    "an explicit null snapshot must not inherit the current subject",
  );

  const camel = hydrate(
    { metadata: { request_snapshot: { content: "q", subjectId: "scope-c" } } },
    "q",
    [],
  ) as Record<string, unknown>;
  assert.equal(camel.subject_id, "scope-c");

  const legacy = hydrate(
    { metadata: { request_snapshot: { content: "q", capability: "chat" } } },
    "q",
    [],
  ) as Record<string, unknown>;
  assert.equal("subject_id" in legacy, false, "a legacy snapshot has no scope to replay");
  assert.equal(
    (scope.resolveSendSubject as (...args: unknown[]) => unknown)(
      { subjectId: "scope-b", subjectHydrated: true },
      legacy,
    ),
    null,
  );
});

test("the optimistic config-only snapshot replays its own scope", () => {
  const scope = moduleFrom(
    readSource(pathModule.join(WEB_ROOT, "lib", "subject-scope.ts"), "utf8"),
  );
  const merged = (scope.mergeSubjectIntoConfig as (...args: unknown[]) => unknown)(
    { depth: "standard" },
    "scope-a",
  );
  assert.equal(
    (scope.resolveSendSubject as (...args: unknown[]) => unknown)(
      { subjectId: "scope-b", subjectHydrated: true },
      { content: "q", config: merged },
    ),
    "scope-a",
  );
});

test("the real load callback marks loading, selects, and carries the scope", async () => {
  const harness = loadHarness();
  const promise = harness.load("A");
  assert.equal(harness.actions.at(-1)?.type, "MARK_SESSION_LOADING");
  harness.pending[0](session("A", "scope-a"));
  await promise;
  assert.equal(harness.actions.at(-1)?.type, "LOAD_SESSION");
  const carried = harness.actions.at(-1)?.preferences as { subject_id?: string };
  assert.equal(carried.subject_id, "scope-a");
});

test("a new conversation invalidates an older in-flight load", async () => {
  const harness = loadHarness();
  const stale = harness.load("A");
  harness.fresh();
  harness.pending[0](session("A", "scope-a"));
  await stale;
  assert.equal(
    harness.actions.at(-1)?.type,
    "REVALIDATE_SESSION",
    "an old response selected its session after NEW_SESSION",
  );
  assert.equal(harness.actions.at(-1)?.key, "A");
});

test("two loads of one session cannot apply the older scope last", async () => {
  const harness = loadHarness();
  const older = harness.load("A");
  const newer = harness.load("A");
  harness.pending[1](session("A", "new-scope"));
  await newer;
  assert.equal(harness.actions.at(-1)?.type, "LOAD_SESSION");
  harness.pending[0](session("A", "old-scope"));
  await older;
  assert.equal(
    harness.actions.at(-1)?.type,
    "REVALIDATE_SESSION",
    "the same session key had no request-generation guard",
  );
});

test("a failed load reopens the send gate instead of closing it forever", async () => {
  const harness = loadHarness();
  const promise = harness.load("A");
  harness.rejections[0](new Error("offline"));
  await assert.rejects(promise as Promise<unknown>);
  const failure = harness.actions.find((action) => action.type === "SESSION_LOAD_FAILED");
  assert.ok(failure, "a failed load left the gate closed with no recovery");
  assert.equal(failure?.key, "A");
});

test("the real selector still offers the explicit clear when the last subject is gone", () => {
  const jsx = (type: unknown, props: unknown) => ({ type, props });
  const selector = moduleFrom(
    readSource(pathModule.join(WEB_ROOT, "components", "chat", "home", "SubjectSelector.tsx"), "utf8"),
    (name: string) => {
      if (name === "react") {
        return { useEffect: () => {}, useRef: () => ({ current: null }), useState: () => [true, () => {}] };
      }
      if (name === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: "fragment" };
      if (name === "react-i18next") {
        return { useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }) };
      }
      if (name === "lucide-react") {
        return { BookOpen: "BookOpen", Check: "Check", ChevronDown: "ChevronDown" };
      }
      throw new Error(`unexpected runtime import ${name}`);
    },
  ).default as (props: Record<string, unknown>) => unknown;

  assert.ok(
    selector({ subjects: [{ id: "scope-a", name: "A" }], value: "scope-a", onChange: () => {} }),
  );
  assert.ok(
    selector({ subjects: [], value: "deleted-scope", onChange: () => {} }),
    "the last subject was deleted: the clear entry is unreachable",
  );
  assert.equal(
    selector({ subjects: [], value: "", onChange: () => {} }),
    null,
    "with nothing to show and nothing selected the control stays hidden",
  );
});

// ---------------------------------------------------------------------------
// R4: the degradation notices the provider consumes and the page shows
// ---------------------------------------------------------------------------
test("turn warnings are validated, bounded and replayed per session", async () => {
  const scope = moduleFrom(
    readSource(pathModule.join(WEB_ROOT, "lib", "subject-scope.ts"), "utf8"),
  );
  const apply = scope.applySubjectWarnings as (
    entry: Record<string, unknown>,
    warnings: unknown,
  ) => Record<string, unknown>;
  const visible = scope.visibleSubjectWarnings as (entry: unknown) => unknown[];

  const doneMetadata = {
    subject_kb_warnings: [
      {
        kb_ref: "subject:kb:scope-a:kb-stale",
        status: "stale",
        code: "kb_not_ready",
        message: "知识库尚未就绪，请稍后重试。",
        exception: "ignored", // unknown fields never reach the UI
      },
      { kb_ref: "", status: "stale" }, // no usable identity → dropped
      "not-an-object",
    ],
  };
  const sessionA = apply({ subjectId: "scope-a" }, doneMetadata.subject_kb_warnings);
  const sessionB = apply({ subjectId: "scope-b" }, undefined);

  assert.equal(visible(sessionA).length, 1);
  const notice = visible(sessionA)[0] as Record<string, unknown>;
  assert.equal(notice.kbRef, "subject:kb:scope-a:kb-stale");
  assert.equal(notice.status, "stale");
  assert.equal(notice.message, "知识库尚未就绪，请稍后重试。");
  assert.equal("exception" in notice, false);

  // A later turn without warnings clears the notice, and another session never
  // sees it. (Length, not deepEqual: the helpers ran in their own VM context, so
  // their arrays do not share this realm's prototype.)
  const settled = apply(sessionA, []);
  assert.equal(visible(settled).length, 0);
  assert.equal(visible(sessionB).length, 0);
  assert.equal(JSON.stringify(visible(sessionB)), "[]");

  const bounded = apply({}, Array.from({ length: 50 }, (_, i) => ({ kb_ref: `kb-${i}` })));
  assert.equal(visible(bounded).length, 20);
});

import { test, expect, type APIRequestContext, type Download, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const STAGE = process.env.S15_EVIDENCE_DIR || path.resolve(__dirname, "../../.phase1-evidence/stages/S15");
const STATE_FILE = process.env.S15_RUN_STATE_FILE || path.join(STAGE, "run_state.json");
const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
const EVIDENCE_FILE = path.join(STAGE, `browser_evidence.${state.run_label}.json`);
const SHOTS = path.join(STAGE, "screenshots");

interface TurnRecord {
  content: string;
  start?: Record<string, any>;
  events: Record<string, any>[];
  sources: Record<string, any>[];
  sessionId?: string;
  done?: boolean;
  terminal?: Record<string, any>;
}

const evidence: Record<string, any> = { run_label: state.run_label, browser: {}, tests: {} };
const turns: TurnRecord[] = [];
const externalRequests: string[] = [];
const pageErrors: string[] = [];
const consoleErrors: string[] = [];

let filler: { id: string; name: string }[] = [];
let subjectA: { id: string; name: string };
let subjectB: { id: string; name: string };
let sessionA = "";
let sessionB = "";
let lastSubject: { id: string; name: string };
let globalKb = "";

function attachCapture(page: Page): void {
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/api/v1/ws")) return;
    let active: TurnRecord | undefined;
    socket.on("framesent", (frame) => {
      try {
        const message = JSON.parse(String(frame.payload));
        if (message.type === "start_turn") {
          active = { content: String(message.content || ""), start: message, events: [], sources: [] };
          turns.push(active);
        }
      } catch {}
    });
    socket.on("framereceived", (frame) => {
      try {
        const event = JSON.parse(String(frame.payload));
        const record = active;
        if (!record) return;
        record.events.push(event);
        if (event.type === "session") {
          const id = event.metadata?.session_id;
          if (id) record.sessionId = String(id);
        }
        if (event.type === "sources") {
          for (const source of event.metadata?.sources || []) {
            if (source && typeof source === "object") record.sources.push(source);
          }
        }
        if (event.type === "done") { record.done = true; record.terminal = event; }
      } catch {}
    });
  });
}

const guardedContexts = new WeakSet();
async function guardBrowser(page: Page): Promise<void> {
  const context = page.context();
  if (guardedContexts.has(context)) return;
  guardedContexts.add(context);
  const allowed = (value: string) => {
    const url = new URL(value);
    return url.hostname === "127.0.0.1" && new Set([state.ports.web, state.ports.backend]).has(Number(url.port));
  };
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const testPorts = new Set([state.ports.web, state.ports.backend]);
    if ((url.hostname === "127.0.0.1" && testPorts.has(Number(url.port)))
        || url.protocol === "data:" || url.protocol === "blob:") {
      return route.continue();
    }
    externalRequests.push(url.href);
    return route.abort();
  });
  await context.routeWebSocket(/.*/, (socket) => {
    if (allowed(socket.url())) socket.connectToServer();
    else { externalRequests.push(socket.url()); socket.close({code: 1008, reason: "S15 undeclared endpoint"}); }
  });
  const observe = (opened: Page) => {
  opened.on("pageerror", (error) => pageErrors.push(String(error)));
  opened.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  };
  context.pages().forEach(observe);
  context.on("page", observe);
}

function record(testName: string, payload: Record<string, any>): void {
  evidence.tests[testName] = { ...payload, recorded_at: new Date().toISOString() };
  fs.mkdirSync(STAGE, { recursive: true });
  fs.writeFileSync(EVIDENCE_FILE, JSON.stringify({
    ...evidence,
    external_requests: externalRequests,
    page_errors: pageErrors,
    console_errors: consoleErrors,
  }, null, 2) + "\n");
}


async function clickAndDownload(page: Page, click: () => Promise<void>): Promise<Download> {
  const downloads: Download[] = [];
  const popups: Page[] = [];
  page.on("download", (download) => downloads.push(download));
  page.on("popup", (popup) => {
    popups.push(popup);
    popup.on("download", (download) => downloads.push(download));
  });
  await click();
  await expect.poll(() => downloads.length, {
    timeout: 60_000,
    message: `no browser download event (popups=${popups.length})`,
  }).toBeGreaterThan(0);
  return downloads[0];
}

async function screenshot(page: Page, name: string): Promise<string> {
  fs.mkdirSync(SHOTS, { recursive: true });
  const file = path.join(SHOTS, `${state.run_label}-${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

function turnFor(content: string): TurnRecord | undefined {
  return turns.find((item) => item.content.includes(content));
}

async function waitTurn(content: string, status = "completed"): Promise<TurnRecord> {
  await expect.poll(() => turnFor(content)?.start, { timeout: 30_000 }).toBeTruthy();
  await expect.poll(() => turnFor(content)?.done, { timeout: 90_000 }).toBe(true);
  const record = turnFor(content)!;
  expect(record.start?.content).toContain(content);
  expect(record.terminal?.metadata?.status).toBe(status);
  return record;
}

function subjectTrigger(page: Page) {
  return page.locator('button[title="Subject context"], button[title="科目上下文"]');
}

async function openSubjectMenu(page: Page) {
  const trigger = subjectTrigger(page);
  await trigger.scrollIntoViewIfNeeded();
  await trigger.click();
  const menu = trigger.locator("xpath=../div[contains(@class,'overflow-y-auto')]");
  await expect(menu).toBeVisible();
  return { trigger, menu };
}

async function chooseSubject(page: Page, name: string): Promise<void> {
  const { trigger, menu } = await openSubjectMenu(page);
  const item = menu.getByRole("button", { name, exact: true });
  await item.scrollIntoViewIfNeeded();
  await item.click();
  await expect(trigger).toContainText(name);
}

async function closeActivityPanel(page: Page): Promise<void> {
  const close = page.getByRole("button", { name: "Close viewer" });
  if (await close.isVisible().catch(() => false)) await close.click();
}

async function clearSubject(page: Page): Promise<void> {
  const { trigger, menu } = await openSubjectMenu(page);
  await menu.getByRole("button", { name: /^(No subject|无科目)$/ }).click();
  await expect(trigger).toContainText(/No subject|无科目/);
}

function capabilityTrigger(page: Page) {
  return page.getByRole("button", { name: "Add files & context" }).locator("xpath=../..").getByRole("button").first();
}

async function chooseCapability(page: Page, name: string): Promise<void> {
  const trigger = capabilityTrigger(page);
  await trigger.click();
  const menu = trigger.locator("xpath=../div[contains(@class,'dt-popup-up')]");
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: new RegExp(`^${name}\\b`) }).first().click();
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const input = page.getByRole("textbox", {name: /How can I help you today\?|Type a message|今天想了解|输入消息/}).last();
  await expect(input).toBeVisible();
  await input.fill(text);
  await input.press("Enter");
}

async function visibleSource(page: Page, filename: string, excluded: string): Promise<void> {
  const header = page.getByRole("button", {name: /^Done\b/}).last();
  await expect(header).toBeVisible();
  if (await header.getAttribute("aria-expanded") !== "true") await header.click();
  const trace = header.locator("xpath=..");
  for (let depth=0; depth<3; depth++) {
    for (const row of await trace.locator('[role="button"][aria-expanded="false"]').all()) {
      if (await row.isVisible()) await row.click();
    }
  }
  await expect(trace.getByText(filename, {exact:false}).last()).toBeVisible();
  expect(await trace.innerText()).not.toContain(excluded);
  await header.click();
}

async function createSubject(request: APIRequestContext, name: string) {
  const response = await request.post("/api/v1/subjects", { form: { name, description: "", term: "2026" } });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()).subject as { id: string; name: string };
}

async function uploadText(subjectId: string, filename: string, text: string) {
  const form = new FormData();
  form.append("type", "assignment");
  form.append("files", new Blob([text], { type: "text/plain" }), filename);
  const response = await fetch(`${state.origins.web}/api/v1/subjects/${subjectId}/knowledge/upload`, {
    method: "POST", body: form,
  });
  const body = await response.text();
  expect(response.status, body).toBe(200);
  return JSON.parse(body);
}

async function ensureGlobalKb(name: string): Promise<void> {
  const form = new FormData();
  form.append("name", name);
  form.append("rag_provider", "llamaindex");
  form.append("files", new Blob(["E2E-G-ONLY-93e2 全局知识库的唯一检索标记。"], { type: "text/plain" }), "global-marker.txt");
  const response = await fetch(`${state.origins.web}/api/v1/knowledge/create`, { method: "POST", body: form });
  const body = await response.text();
  expect(response.status, body).toBe(200);
  await expect.poll(async () => {
    const listed = await (await fetch(`${state.origins.web}/api/v1/knowledge/list`)).json();
    const rows = Array.isArray(listed) ? listed : (listed.knowledge_bases || []);
    const row = rows.find((item: any) => item.name === name);
    return row?.status || "missing";
  }, { timeout: 120_000, intervals: [500, 1000, 2000] }).toBe("ready");
}


function hashTree(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(file);
      else if (entry.isFile()) out[path.relative(root, file)] = createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    }
  };
  walk(root);
  return out;
}

function wavBytes(seconds = 0.25): Buffer {
  const rate = 8000;
  const samples = Math.floor(rate * seconds);
  const data = Buffer.alloc(samples * 2);
  for (let i = 0; i < samples; i += 1) {
    data.writeInt16LE(Math.round(Math.sin((2 * Math.PI * 440 * i) / rate) * 1200), i * 2);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

function subjectDir(subjectId: string): string {
  return path.join(state.source_root, "data", "user", "workspace", "subjects", subjectId);
}

async function waitKbReady(request: APIRequestContext, subjectId: string, kbName = "assignment-kb") {
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/subjects/${subjectId}/knowledge/${kbName}/status`);
    if (response.status() !== 200) return `http-${response.status()}`;
    const body = await response.json();
    return body.status || body.status?.status || "unknown";
  }, { timeout: 90_000, intervals: [250, 500, 1000, 2000] }).toBe("ready");
}

test.beforeAll(async ({ request }) => {
  const stamp = Date.now().toString(36).slice(-5);
  subjectA = await createSubject(request, `S15 Subject A ${stamp}`);
  subjectB = await createSubject(request, `S15 Subject B ${stamp}`);
  filler = [];
  for (let i = 1; i <= 16; i += 1) {
    filler.push(await createSubject(request, `S15 Subject ${String(i).padStart(2, "0")} ${stamp}`));
  }
  lastSubject = filler[filler.length - 1];
  globalKb = `s15-global-${stamp}`;
  await ensureGlobalKb(globalKb);
  evidence.subjects = { a: subjectA, b: subjectB, filler_count: filler.length, last: lastSubject, global_kb: globalKb };
});

test.afterAll(async () => {
  fs.writeFileSync(EVIDENCE_FILE, JSON.stringify({
    ...evidence,
    external_requests: externalRequests,
    page_errors: pageErrors,
    console_errors: consoleErrors,
  }, null, 2) + "\n");
});

test("B1 subject menu, session hydration, clear, and no cross-session scope", async ({ page, request, browser }) => {
  evidence.browser = { version: browser.version(), executable: state.browser_executable };
  await guardBrowser(page);
  attachCapture(page);
  await page.goto("/home");
  await expect(subjectTrigger(page)).toBeVisible();

  // The browser-side egress guard must abort anything outside the two test
  // loopback ports. This deliberate probe is recorded, then removed so the
  // stage-level "no unexpected egress" assertion remains meaningful.
  const probe = `${state.origins.model}/s15-egress-probe`;
  const egressBlocked = await page.evaluate(async (url) => {
    try {
      await fetch(url, { mode: "no-cors" });
      return false;
    } catch {
      return true;
    }
  }, probe);
  expect(egressBlocked).toBe(true);
  const probeUrls = externalRequests.filter((url) => url === probe);
  expect(probeUrls.length).toBeGreaterThan(0);
  for (let i = externalRequests.length - 1; i >= 0; i -= 1) {
    if (externalRequests[i] === probe) externalRequests.splice(i, 1);
  }
  const wsProbe = `${state.origins.model.replace("http:", "ws:")}/s15-egress-probe`;
  await page.evaluate((url) => new Promise<void>((resolve) => {
    const socket = new WebSocket(url);
    socket.onclose = () => resolve();
    socket.onerror = () => resolve();
  }), wsProbe);
  await expect.poll(() => externalRequests.includes(wsProbe)).toBe(true);
  externalRequests.splice(externalRequests.indexOf(wsProbe), 1);

  const { trigger, menu } = await openSubjectMenu(page);
  const metrics = await menu.evaluate((element) => ({ scrollHeight: element.scrollHeight, clientHeight: element.clientHeight }));
  expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);
  const last = menu.getByRole("button", { name: lastSubject.name, exact: true });
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
  const menuShot = await screenshot(page, "b1-menu-last-subject");
  await last.click();
  await expect(trigger).toContainText(lastSubject.name);
  const selectedShot = await screenshot(page, "b1-last-subject-selected");

  await sendMessage(page, "E2E-B1-A");
  const first = await waitTurn("E2E-B1-A");
  expect(first.start?.subject_id).toBe(lastSubject.id);
  expect(first.sessionId).toBeTruthy();
  sessionA = first.sessionId!;
  await expect(page.getByText("E2E-ANSWER:E2E-B1-A", { exact: false }).last()).toBeVisible();

  const firstSession = await (await request.get(`/api/v1/sessions/${sessionA}`)).json();
  expect(firstSession.preferences.subject_id).toBe(lastSubject.id);
  const firstUser = firstSession.messages.find((message: any) => message.role === "user" && message.content === "E2E-B1-A");
  expect(firstUser.metadata.request_snapshot.subject_id).toBe(lastSubject.id);
  const restoredShot = await screenshot(page, "b1-session-a");

  await page.reload();
  await expect(subjectTrigger(page)).toContainText(lastSubject.name);
  await expect(page.getByText("E2E-ANSWER:E2E-B1-A", { exact: false }).last()).toBeVisible();

  await page.goto("/home");
  await expect(subjectTrigger(page)).toContainText(/No subject|无科目/);
  await chooseSubject(page, lastSubject.name);
  await clearSubject(page);
  await sendMessage(page, "E2E-B1-B");
  const second = await waitTurn("E2E-B1-B");
  expect(second.start?.subject_id).toBeNull();
  expect(second.sessionId).toBeTruthy();
  sessionB = second.sessionId!;
  await expect(page.getByText("E2E-ANSWER:E2E-B1-B", { exact: false }).last()).toBeVisible();

  await page.reload();
  await expect(subjectTrigger(page)).toContainText(/No subject|无科目/);
  await page.goto(`/home/${sessionA}`);
  await expect(subjectTrigger(page)).toContainText(lastSubject.name);
  const finalShot = await screenshot(page, "b1-session-a-restored");

  const secondSession = await (await request.get(`/api/v1/sessions/${sessionB}`)).json();
  expect(secondSession.preferences.subject_id ?? null).toBeNull();
  const secondUser = secondSession.messages.find((message: any) => message.role === "user" && message.content === "E2E-B1-B");
  expect(secondUser.metadata.request_snapshot.subject_id ?? null).toBeNull();
  record("B1", {
    contract: "C08 three-state scope + no cross-session inheritance + visible scrollable menu",
    browser_egress_blocked: true,
    browser_egress_probe: probeUrls,
    subjects: { count: filler.length + 2, last: lastSubject.name },
    menu_metrics: metrics,
    menu_last_in_viewport: true,
    session_a: sessionA,
    session_b: sessionB,
    turn_a_start: first.start,
    turn_b_start: second.start,
    session_a_preferences: firstSession.preferences,
    session_b_preferences: secondSession.preferences,
    request_snapshot_a: firstUser.metadata.request_snapshot,
    request_snapshot_b: secondUser.metadata.request_snapshot,
    screenshots: [menuShot, selectedShot, restoredShot, finalShot],
  });
  expect(externalRequests).toEqual([]);
});

test("B2 capability switch and real A/B RAG sources do not cross", async ({ page, request }) => {
  await guardBrowser(page);
  attachCapture(page);
  await page.goto(`/home/${sessionA}`);
  await expect(subjectTrigger(page)).toContainText(lastSubject.name);

  await uploadText(subjectA.id, "a-marker.txt", "E2E-A-ONLY-71c0 科目 A 的独有检索标记。常微分方程。\n");
  await uploadText(subjectB.id, "b-marker.txt", "E2E-B-ONLY-82d1 科目 B 的独有检索标记。线性代数。\n");
  await waitKbReady(request, subjectA.id);
  await waitKbReady(request, subjectB.id);

  await chooseSubject(page, subjectA.name);
  await sendMessage(page, "E2E-B2-CHAT");
  const chatTurn = await waitTurn("E2E-B2-CHAT");
  expect(chatTurn.start?.subject_id).toBe(subjectA.id);
  expect(chatTurn.start?.capability).toBe("chat");

  // Switch to Quiz in the same session. The actual start_turn frame must carry
  // the capability and still carry the same subject. The provider implements
  // the real explore/plan/question protocol; the whole Quiz must complete.
  await chooseCapability(page, "Quiz");
  const confirm = page.getByRole("button", { name: "Confirm", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.click();
  await sendMessage(page, "E2E-B2-QUIZ");
  const quizTurn = await waitTurn("E2E-B2-QUIZ");
  expect(quizTurn.start?.capability).toBe("deep_question");
  expect(quizTurn.start?.subject_id).toBe(subjectA.id);
  const quizResult = quizTurn.events.find((event) => event.type === "result");
  expect(quizResult?.metadata?.summary?.success).toBe(true);
  expect(quizResult?.metadata?.summary?.completed).toBe(3);
  await expect(page.getByText("E2E-QUIZ-1: What is 1 + 1?", {exact: false}).first()).toBeVisible();
  const quizShot = await screenshot(page, "b2-quiz-scope");
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/sessions/${sessionA}`);
    return (await response.json()).status;
  }, { timeout: 30_000 }).not.toBe("running");

  // Return to Chat and close the Activity panel the Quiz config opened.
  await chooseCapability(page, "Chat");
  await closeActivityPanel(page);

  await sendMessage(page, "E2E-RAG-A What unique evidence does my current subject contain?");
  const aTurn = await waitTurn("E2E-RAG-A");
  expect(aTurn.sources.length).toBeGreaterThan(0);
  const aSourceText = JSON.stringify(aTurn.sources);
  expect(aSourceText).toContain("E2E-A-ONLY-71c0");
  expect(aSourceText).not.toContain("E2E-B-ONLY-82d1");
  const rawA = fs.readFileSync(path.join(subjectDir(subjectA.id), "knowledge_bases", "assignment-kb", "raw", "a-marker.txt"), "utf-8");
  expect(rawA).toContain("E2E-A-ONLY-71c0");
  const afterA = await (await request.get(`/api/v1/sessions/${sessionA}`)).json();
  const answerA = [...afterA.messages].reverse().find((message: any) => message.role === "assistant");
  expect(answerA.content).toContain("E2E-ANSWER:E2E-RAG-A");
  expect(answerA.content).toContain("GROUNDED:E2E-A-ONLY-71c0");
  expect(answerA.content).not.toContain("E2E-B-ONLY");
  await visibleSource(page, "a-marker.txt", "b-marker.txt");

  await chooseSubject(page, subjectB.name);
  await sendMessage(page, "E2E-RAG-B What unique evidence does my current subject contain?");
  const bTurn = await waitTurn("E2E-RAG-B");
  expect(bTurn.sources.length).toBeGreaterThan(0);
  const bSourceText = JSON.stringify(bTurn.sources);
  expect(bSourceText).toContain("E2E-B-ONLY-82d1");
  expect(bSourceText).not.toContain("E2E-A-ONLY-71c0");
  const rawB = fs.readFileSync(path.join(subjectDir(subjectB.id), "knowledge_bases", "assignment-kb", "raw", "b-marker.txt"), "utf-8");
  expect(rawB).toContain("E2E-B-ONLY-82d1");
  const afterB = await (await request.get(`/api/v1/sessions/${sessionA}`)).json();
  const answerB = [...afterB.messages].reverse().find((message: any) => message.role === "assistant");
  expect(answerB.content).toContain("E2E-ANSWER:E2E-RAG-B");
  expect(answerB.content).toContain("GROUNDED:E2E-B-ONLY-82d1");
  expect(answerB.content).not.toContain("E2E-A-ONLY");
  await expect(page.getByText("E2E-ANSWER:E2E-RAG-B", { exact: false }).last()).toBeVisible();
  await visibleSource(page, "b-marker.txt", "a-marker.txt");
  const ragShot = await screenshot(page, "b2-rag-b");

  // Explicit global KB: clear the subject first, then attach the global KB by
  // name through the composer. The wire frame must carry the global ref and the
  // real RAG result must identify that global KB, not either subject KB.
  await clearSubject(page);
  const kbTrigger = page.getByRole("button", { name: /Select knowledge bases|选择知识库/ });
  await kbTrigger.click();
  const kbMenu = kbTrigger.locator("xpath=../div[contains(@class,'dt-popup-up')]");
  await kbMenu.getByRole("button", { name: globalKb, exact: true }).click();
  await sendMessage(page, "E2E-RAG-GLOBAL What unique evidence does my attached library contain?");
  const globalTurn = await waitTurn("E2E-RAG-GLOBAL");
  expect(globalTurn.start?.subject_id).toBeNull();
  expect(JSON.stringify(globalTurn.start?.knowledge_bases)).toContain(globalKb);
  const globalSourceText = JSON.stringify(globalTurn.sources);
  expect(globalSourceText).toContain("E2E-G-ONLY-93e2");
  const rawGlobal = fs.readFileSync(path.join(state.source_root, "data", "knowledge_bases", globalKb, "raw", "global-marker.txt"), "utf-8");
  expect(rawGlobal).toContain("E2E-G-ONLY-93e2");
  const afterGlobal = await (await request.get(`/api/v1/sessions/${sessionA}`)).json();
  const answerGlobal = [...afterGlobal.messages].reverse().find((message: any) => message.role === "assistant");
  expect(answerGlobal.content).toContain("E2E-ANSWER:E2E-RAG-GLOBAL");
  expect(answerGlobal.content).toContain("GROUNDED:E2E-G-ONLY-93e2");
  expect(globalSourceText).not.toContain("E2E-A-ONLY-71c0");
  expect(globalSourceText).not.toContain("E2E-B-ONLY-82d1");
  const globalShot = await screenshot(page, "b2-global-source");

  const session = await (await request.get(`/api/v1/sessions/${sessionA}`)).json();
  const userMessages = session.messages.filter((message: any) => message.role === "user");
  const snapshots = userMessages.map((message: any) => message.metadata?.request_snapshot).filter(Boolean);
  expect(snapshots.some((snapshot: any) => snapshot.subject_id === subjectA.id)).toBe(true);
  expect(snapshots.some((snapshot: any) => snapshot.subject_id === subjectB.id)).toBe(true);

  record("B2", {
    contract: "C08 capability+subject merge; real A/B RAG source identity and isolation",
    subject_a: subjectA.id,
    subject_b: subjectB.id,
    chat_start: chatTurn.start,
    quiz_start: quizTurn.start,
    a_start: aTurn.start,
    b_start: bTurn.start,
    a_sources: aTurn.sources,
    b_sources: bTurn.sources,
    raw_source_identity: { a: createHash("sha256").update(rawA).digest("hex"), b: createHash("sha256").update(rawB).digest("hex"), global: createHash("sha256").update(rawGlobal).digest("hex") },
    answers: { a: answerA.content, b: answerB.content, global: answerGlobal.content },
    global_start: globalTurn.start,
    global_sources: globalTurn.sources,
    session_preferences: session.preferences,
    request_snapshots: snapshots,
    screenshots: [quizShot, ragShot, globalShot],
  });
  expect(externalRequests).toEqual([]);
});


test("B3 browser document index, ASR transcript, and failure recovery", async ({ page, request }) => {
  await guardBrowser(page);
  attachCapture(page);
  const stamp = Date.now().toString(36).slice(-4);
  const docName = `s15-doc-${stamp}.txt`;
  const docMarker = `E2E-B3-DOC-${stamp}`;
  const docText = `${docMarker} 浏览器上传的文档索引标记。真实 multipart 上传与 LlamaIndex 检索。\n`;

  await page.goto("/subjects");
  await expect(page.getByText(subjectA.name, { exact: true })).toBeVisible();
  const fileInput = page.locator(`#file-${subjectA.id}`);
  const row = page.locator("div.rounded-xl").filter({ has: fileInput }).first();
  const subjectBefore = hashTree(subjectDir(subjectA.id));

  // Targeted HTTP failure: no request reaches the backend, busy must clear and
  // no success count may appear. The same page then retries successfully.
  let failDoc = true;
  await page.route(`**/api/v1/subjects/${subjectA.id}/knowledge/upload`, async (route) => {
    if (failDoc) {
      failDoc = false;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E-FORCED-DOC-FAIL" }) });
      return;
    }
    await route.continue();
  });
  await fileInput.setInputFiles({ name: docName, mimeType: "text/plain", buffer: Buffer.from(docText) });
  await expect(page.getByText("E2E-FORCED-DOC-FAIL", { exact: false })).toBeVisible();
  await expect(row.getByText("上传材料", { exact: true })).toBeVisible();
  expect(await page.getByText(/已保存 \d+ 个文件/).count()).toBe(0);
  const afterFailure = hashTree(subjectDir(subjectA.id));
  expect(afterFailure).toEqual(subjectBefore);
  const failureShot = await screenshot(page, "b3-doc-failure");

  const uploadResponse = page.waitForResponse((response) =>
    response.url().includes(`/api/v1/subjects/${subjectA.id}/knowledge/upload`) && response.request().method() === "POST");
  await fileInput.setInputFiles({ name: docName, mimeType: "text/plain", buffer: Buffer.from(docText) });
  const upload = await uploadResponse;
  expect(upload.status()).toBe(200);
  await expect(page.getByText(/已保存 1 个文件/)).toBeVisible();
  await waitKbReady(request, subjectA.id);
  await expect(row.getByText(/ready/).first()).toBeVisible();
  const successShot = await screenshot(page, "b3-doc-ready");

  // The newly indexed document is retrievable through a real browser turn.
  await page.goto("/home");
  await chooseSubject(page, subjectA.name);
  await sendMessage(page, `E2E-B3-QUERY ${docMarker}`);
  const queryTurn = await waitTurn("E2E-B3-QUERY");
  expect(queryTurn.start?.subject_id).toBe(subjectA.id);
  expect(JSON.stringify(queryTurn.sources)).toContain(docMarker);
  expect(JSON.stringify(queryTurn.sources)).toContain(docName);
  const querySession = queryTurn.sessionId!;
  const queryShot = await screenshot(page, "b3-doc-query");

  // Audio transcribe: real browser file input + multipart, deterministic STT
  // only at the provider boundary. It must report lecture storage, never index.
  await page.goto(`/subjects/${subjectA.id}`);
  await page.getByRole("button", { name: "期末考点" }).click();
  const card = page.getByText("课堂考点检测", { exact: true }).locator("xpath=..");
  await expect(card).toBeVisible();
  const audioInput = card.locator('input[type=file]');
  const kbBeforeAudio = hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"));
  let failAudio = true;
  await page.route(`**/api/v1/subjects/${subjectA.id}/asr/jobs`, async (route) => {
    if (failAudio && route.request().method() === "POST") {
      failAudio = false;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "E2E-FORCED-AUDIO-FAIL",
          error: { code: "provider_unavailable", message: "E2E-FORCED-AUDIO-FAIL", retryable: true },
        }),
      });
      return;
    }
    await route.continue();
  });
  const wav = wavBytes();
  await audioInput.setInputFiles({ name: `s15-lecture-${stamp}.wav`, mimeType: "audio/wav", buffer: wav });
  await expect(page.getByText("E2E-FORCED-AUDIO-FAIL", { exact: false })).toBeVisible();
  await expect(card.getByText("上传录音（mp3/m4a/wav）", { exact: true })).toBeVisible();
  expect(await page.getByText(/转写完成/).count()).toBe(0);
  expect(hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"))).toEqual(kbBeforeAudio);
  const audioFailureShot = await screenshot(page, "b3-audio-failure");

  await audioInput.setInputFiles({ name: `s15-lecture-${stamp}.wav`, mimeType: "audio/wav", buffer: wav });
  await expect(page.getByText(/转写完成（1 个文件）/)).toBeVisible();
  await expect(page.getByText(/materials\/lecture/)).toBeVisible();
  await expect(page.getByText(/不会自动建立索引/)).toBeVisible();
  const cardText = await card.innerText();
  expect(cardText).not.toMatch(/\bready\b|已索引|图片覆盖|image coverage/i);
  const transcript = card.locator("textarea");
  await expect(transcript).toHaveValue(/E2E-TRANSCRIPT-B3/);
  expect(hashTree(path.join(subjectDir(subjectA.id), "knowledge_bases"))).toEqual(kbBeforeAudio);

  const lectureDir = path.join(subjectDir(subjectA.id), "materials", "lecture");
  const lectureFiles = fs.readdirSync(lectureDir).sort();
  expect(lectureFiles.some((name) => name === `s15-lecture-${stamp}.wav`)).toBe(true);
  const transcriptFile = lectureFiles.find((name) => name.startsWith(`s15-lecture-${stamp}.wav`) && name.endsWith(".txt"));
  expect(transcriptFile).toBeTruthy();
  expect(fs.readFileSync(path.join(lectureDir, transcriptFile!), "utf-8")).toContain("E2E-TRANSCRIPT-B3");
  const audioShot = await screenshot(page, "b3-audio-success");

  record("B3", {
    contract: "C07/C13 real multipart document index and audio transcribe; failure releases busy and never writes success",
    document: { name: docName, marker: docMarker, upload_status: upload.status(), query_session: querySession },
    document_failure_tree_unchanged: afterFailure,
    audio: {
      file: `s15-lecture-${stamp}.wav`,
      card_text: cardText,
      transcript_file: transcriptFile,
      lecture_files: lectureFiles,
      kb_tree_unchanged: true,
    },
    query_sources: queryTurn.sources,
    screenshots: [failureShot, successShot, queryShot, audioFailureShot, audioShot],
  });
  expect(externalRequests).toEqual([]);
});

test("B4 real ZIP export, generation failure recovery, and unchanged old artifacts", async ({ page, request }) => {
  await guardBrowser(page);
  const downloadDir = path.join(STAGE, "downloads");
  fs.mkdirSync(downloadDir, { recursive: true });
  await page.goto(`/subjects/${subjectA.id}`);
  await expect(page.getByRole("button", { name: "导出科目资料" })).toBeVisible();

  const firstDownload = await clickAndDownload(page, async () => {
    await page.getByRole("button", { name: "导出科目资料" }).click();
  });
  const firstName = firstDownload.suggestedFilename();
  expect(firstName).toMatch(/\.zip$/i);
  const firstPath = path.join(downloadDir, `${state.run_label}-${firstName}`);
  await firstDownload.saveAs(firstPath);
  await expect(page.getByText("导出已开始下载。", { exact: false })).toBeVisible();
  const firstBytes = fs.readFileSync(firstPath);
  expect(firstBytes.subarray(0, 2).toString("ascii")).toBe("PK");
  const zipNames = JSON.parse(execFileSync(state.python, ["-c",
    "import json,sys,zipfile,hashlib; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; m=json.loads(z.read('manifest.json')); assert len(z.namelist())==len(set(z.namelist())); assert set(z.namelist())=={'manifest.json'}|{f['path'] for f in m['files']}; [(lambda b,f: (len(b)==f['size'] and hashlib.sha256(b).hexdigest()==f['sha256']) or (_ for _ in ()).throw(AssertionError('member mismatch')))(z.read(f['path']),f) for f in m['files']]; print(json.dumps(z.namelist(), ensure_ascii=False))",
    firstPath], { encoding: "utf-8" }));
  expect(zipNames.length).toBeGreaterThan(0);
  expect(zipNames.some((name: string) => typeof name === "string")).toBe(true);
  const firstHash = createHash("sha256").update(firstBytes).digest("hex");
  const outputTreeBeforeFailure = hashTree(subjectDir(subjectA.id));
  const publicRoot = path.join(state.source_root, "data", "user", "subjects", subjectA.id);
  const publicBefore = hashTree(publicRoot);
  expect(publicBefore[firstName]).toBe(firstHash);
  const exportShot = await screenshot(page, "b4-export-download");

  // Export failure: the old completed ZIP must remain byte-identical and no
  // success toast/new download may appear.
  let failExport = true;
  await page.route(`**/api/v1/subjects/${subjectA.id}/export`, async (route) => {
    if (failExport) {
      failExport = false;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E-FORCED-EXPORT-FAIL" }) });
      return;
    }
    await route.continue();
  });
  const noDownload = page.waitForEvent("download", { timeout: 1500 }).catch(() => null);
  await page.getByRole("button", { name: "导出科目资料" }).click();
  await expect(page.getByText("E2E-FORCED-EXPORT-FAIL", { exact: false })).toBeVisible();
  expect(await noDownload).toBeNull();
  await expect(page.getByRole("button", { name: "导出科目资料" })).toBeEnabled();
  expect(await page.getByText("导出已开始下载。", { exact: false }).count()).toBe(0);
  expect(hashTree(subjectDir(subjectA.id))).toEqual(outputTreeBeforeFailure);
  expect(hashTree(publicRoot)).toEqual(publicBefore);
  expect(createHash("sha256").update(fs.readFileSync(firstPath)).digest("hex")).toBe(firstHash);

  // A successful export metadata response does not prove the file transfer
  // succeeded. Fail the actual download, including a 200 HTML error page.
  const downloadFailures: string[] = [];
  for (const fault of ["http", "html", "network"]) {
    let received = false;
    const pattern = "**/api/outputs/**";
    await page.route(pattern, async (route) => {
      received = true;
      if (fault === "network") await route.abort("failed");
      else if (fault === "html") await route.fulfill({status:200, contentType:"text/html", body:"<html>PRIVATE-ERROR</html>"});
      else await route.fulfill({status:503, contentType:"application/json", body:JSON.stringify({error:{message:"下载服务暂时不可用。"}})});
    });
    const noFile = page.waitForEvent("download", {timeout:1000}).catch(() => null);
    await page.getByRole("button", {name:"导出科目资料"}).click();
    const message = fault === "http" ? "下载服务暂时不可用。" : fault === "html" ? "下载文件无效，请重试。" : "网络连接失败，请检查网络后重试。";
    await expect(page.getByText(message, {exact:true})).toBeVisible();
    expect(received).toBe(true);
    expect(await noFile).toBeNull();
    await expect(page.getByRole("button", {name:"导出科目资料"})).toBeEnabled();
    await expect(page.getByText("导出已开始下载。", {exact:false})).toHaveCount(0);
    expect(hashTree(publicRoot)[firstName]).toBe(firstHash);
    downloadFailures.push(fault);
    await page.unroute(pattern);
  }
  const recoveredDownload = await clickAndDownload(page, () => page.getByRole("button", {name:"导出科目资料"}).click());
  const recoveredPath = path.join(downloadDir, `${state.run_label}-recovered-${recoveredDownload.suggestedFilename()}`);
  await recoveredDownload.saveAs(recoveredPath);
  expect(fs.readFileSync(recoveredPath).subarray(0,4).toString("binary")).toBe("PK\x03\x04");
  await expect(page.getByText("导出已开始下载。", {exact:false})).toBeVisible();
  const exportFailureShot = await screenshot(page, "b4-export-failure");

  // Same page, same button, retry succeeds and produces a distinct real ZIP.
  const secondDownload = await clickAndDownload(page, async () => {
    await page.getByRole("button", { name: "导出科目资料" }).click();
  });
  const secondPath = path.join(downloadDir, `${state.run_label}-retry-${secondDownload.suggestedFilename()}`);
  await secondDownload.saveAs(secondPath);
  const secondBytes = fs.readFileSync(secondPath);
  expect(secondBytes.subarray(0, 2).toString("ascii")).toBe("PK");
  expect(createHash("sha256").update(secondBytes).digest("hex")).not.toBe(firstHash);
  expect(createHash("sha256").update(fs.readFileSync(firstPath)).digest("hex")).toBe(firstHash);

  // One generation action: exam-point detection. First force an HTTP failure,
  // assert busy clears and no success text, then retry on the same page.
  await page.getByRole("button", { name: "期末考点" }).click();
  const detectButton = page.getByRole("button", { name: "检测考点" });
  const transcript = page.locator("textarea[placeholder*='粘贴']").first();
  await expect(transcript).toBeVisible();
  await transcript.fill("这个知识点很重要，大家一定要重视起来。");
  let failDetect = true;
  await page.route(`**/api/v1/subjects/${subjectA.id}/exam-points/detect`, async (route) => {
    if (failDetect) {
      failDetect = false;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E-FORCED-DETECT-FAIL" }) });
      return;
    }
    await route.continue();
  });
  await detectButton.click();
  await expect(page.getByText("E2E-FORCED-DETECT-FAIL", { exact: false })).toBeVisible();
  await expect(detectButton).toBeEnabled();
  expect(await page.getByText(/检出 \d+ 条候选考点/).count()).toBe(0);
  await expect(page.getByText("没有可用的模型配置", { exact: false })).toHaveCount(0);
  const detectFailureShot = await screenshot(page, "b4-generation-failure");

  await detectButton.click();
  await expect(page.getByText(/检出 1 条候选考点/)).toBeVisible();
  await expect(page.getByText("E2E 考点：常微分方程解的存在唯一性", { exact: false })).toBeVisible();
  const detectSuccessShot = await screenshot(page, "b4-generation-success");

  const detail = await (await request.get(`/api/v1/subjects/${subjectA.id}/exam-points`)).json();
  expect(detail.points.some((point: any) => String(point.content).includes("E2E 考点"))).toBe(true);

  record("B4", {
    contract: "C13 export/generation busy resets, fixed failure surface, real ZIP download, old artifacts preserved",
    download: {
      first: { name: firstName, bytes: firstBytes.length, sha256: firstHash, entries: zipNames.length },
      retry: { name: secondDownload.suggestedFilename(), bytes: secondBytes.length, sha256: createHash("sha256").update(secondBytes).digest("hex") },
      paths: [firstPath, secondPath],
    },
    export_failure: { message: "E2E-FORCED-EXPORT-FAIL", old_zip_unchanged: true, no_download: true },
    download_failures: downloadFailures,
    generation_failure: { message: "E2E-FORCED-DETECT-FAIL", busy_released: true, no_success_text: true },
    generation_success: { count: detail.points.length, point: "E2E 考点：常微分方程解的存在唯一性" },
    screenshots: [exportShot, exportFailureShot, detectFailureShot, detectSuccessShot],
  });
  expect(externalRequests).toEqual([]);
});

test("B5 knowledge entry, truthful PageIndex outline, and removed dead entries", async ({ page }) => {
  await guardBrowser(page);
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: /Knowledge Center/ })).toBeVisible();
  await page.getByRole("button", { name: "New knowledge base" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  const dialogText = await dialog.innerText();
  expect(dialogText).not.toMatch(/obsidian|vault/i);
  await expect(dialog.locator("button").filter({ hasText: /obsidian|vault/i })).toHaveCount(0);
  const llama = dialog.getByRole("button", { name: /LlamaIndex/ });
  await expect(llama).toBeVisible();
  await expect(llama).toBeEnabled();
  const pageIndex = dialog.getByRole("button", { name: /PageIndex/ });
  await expect(pageIndex).toBeVisible();
  await expect(pageIndex).toBeEnabled();
  await expect(dialog.getByRole("button", { name: /LightRAG Server/ })).toBeVisible();

  await pageIndex.click();
  await expect(dialog.getByText(/Hosted document outlines/i)).toBeVisible();
  await expect(dialog.getByText(/outline/i).first()).toBeVisible();
  await expect(dialog.getByText(/needs an API key/i)).toBeVisible();
  expect(await dialog.innerText()).not.toMatch(/\bMCP\b|MCP tool|deep retrieval/i);
  await expect(dialog.getByRole("button", { name: "Choose files" })).toBeVisible();
  await expect(pageIndex).toHaveClass(/border-\[var\(--primary\)\]/);
  const pageIndexClass = await pageIndex.getAttribute("class");
  const pageIndexDialogText = await dialog.innerText();
  expect(pageIndexClass).toContain("border-[var(--primary)]");
  expect(pageIndexDialogText).toMatch(/needs an API key/i);
  const modalShot = await screenshot(page, "b5-knowledge-modal-pageindex");

  await dialog.getByRole("button", { name: /Cancel|Close/ }).first().click();
  await expect(dialog).toHaveCount(0);

  const navState = await page.locator("aside a[href]").evaluateAll((links) =>
    links.map((link) => ({ href: link.getAttribute("href") || "", text: (link.textContent || "").trim() })));
  expect(navState.some((item) => /partner|book|obsidian|tutorbot|matrix/i.test(item.href))).toBe(false);
  expect(navState.some((item) => /^(Partner|Book|Obsidian)$/i.test(item.text))).toBe(false);
  await expect(page.getByText(/Connect Obsidian|Connect vault|Obsidian vault/i)).toHaveCount(0);

  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toMatch(/Connect Obsidian|Connect vault/i);
  const knowledgeShot = await screenshot(page, "b5-knowledge-home");

  record("B5", {
    contract: "C13 dead Obsidian/Partner/Book entries absent; existing KB engines and truthful PageIndex outline retained",
    dialog_text_excerpt: dialogText.slice(0, 1200),
    pageindex_dialog_text_excerpt: pageIndexDialogText.slice(0, 1200),
    pageindex_class: pageIndexClass,
    pageindex: {
      visible: true,
      enabled: true,
      outline_copy: true,
      needs_key_notice: true,
      no_mcp_claim: true,
      choose_files: true,
    },
    nav_links: navState,
    screenshots: [modalShot, knowledgeShot],
  });
  expect(externalRequests).toEqual([]);
});

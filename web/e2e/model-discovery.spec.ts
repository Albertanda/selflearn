import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const STAGE = process.env.S15_EVIDENCE_DIR || path.resolve(__dirname, "../../.phase1-evidence/model-discovery/MD-R1-browser");
const STATE_FILE = process.env.S15_RUN_STATE_FILE || path.join(STAGE, "run_state.json");
const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
const MODEL_ORIGIN = process.env.S15_MODEL_ORIGIN || state.origins.model;
const SHOTS = path.join(STAGE, "screenshots");
const EVIDENCE_FILE = path.join(STAGE, "browser_evidence.md.json");
const externalRequests: string[] = [];
const pageErrors: string[] = [];
const consoleErrors: string[] = [];
const checks: Record<string, unknown> = {};

function record(): void {
  fs.mkdirSync(STAGE, { recursive: true });
  fs.writeFileSync(
    EVIDENCE_FILE,
    JSON.stringify(
      {
        stage: "MD-R1",
        run_id: state.run_id,
        browser: state.browser_executable,
        checks,
        external_requests: externalRequests,
        page_errors: pageErrors,
        console_errors: consoleErrors,
        recorded_at: new Date().toISOString(),
      },
      null,
      2,
    ) + "\n",
  );
}

function guardBrowser(page: Page): void {
  const context = page.context();
  const allowed = (value: string) => {
    const url = new URL(value);
    return (
      url.hostname === "127.0.0.1" &&
      new Set([state.ports.web, state.ports.backend]).has(Number(url.port))
    );
  };
  void context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (
      (url.hostname === "127.0.0.1" &&
        new Set([state.ports.web, state.ports.backend]).has(Number(url.port))) ||
      url.protocol === "data:" ||
      url.protocol === "blob:"
    ) {
      return route.continue();
    }
    externalRequests.push(url.href);
    return route.abort();
  });
  void context.routeWebSocket(/.*/, (socket) => {
    if (allowed(socket.url())) socket.connectToServer();
    else {
      externalRequests.push(socket.url());
      socket.close({ code: 1008, reason: "undeclared endpoint" });
    }
  });
  context.on("page", (opened) => {
    opened.on("pageerror", (error) => pageErrors.push(String(error)));
    opened.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
}

async function shot(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const input = page
    .getByRole("textbox", {
      name: /How can I help you today\?|Type a message|今天想了解|输入消息/,
    })
    .last();
  await expect(input).toBeVisible();
  await input.fill(text);
  await input.press("Enter");
}

async function stats(request: APIRequestContext): Promise<Record<string, any>> {
  return (await (await request.get(`${MODEL_ORIGIN}/md/stats`)).json()) as Record<string, any>;
}

async function control(
  request: APIRequestContext,
  params: Record<string, string | number>,
): Promise<void> {
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])),
  );
  const response = await request.get(`${MODEL_ORIGIN}/md/control?${query.toString()}`);
  expect(response.ok()).toBe(true);
}

async function catalog(page: Page): Promise<any> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/settings", { cache: "no-store" });
    return response.json();
  });
}

async function llmOptions(page: Page): Promise<any> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/settings/llm-options", { cache: "no-store" });
    return response.json();
  });
}

async function openDiscovery(page: Page) {
  await page.getByTestId("model-discovery-open").click();
  const dialog = page.getByTestId("model-discovery-dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

async function closeDiscovery(page: Page): Promise<void> {
  const dialog = page.getByTestId("model-discovery-dialog");
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toBeHidden();
}

function row(dialog: ReturnType<Page["getByTestId"]>, id: string) {
  return dialog.locator(`[data-testid="model-discovery-row"][data-model-id="${id}"]`);
}

async function ensureRow(dialog: ReturnType<Page["getByTestId"]>, id: string) {
  const target = row(dialog, id);
  await expect(target).toBeVisible({ timeout: 20_000 });
  return target;
}

async function saveDraft(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Save Draft", exact: true }).click();
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
}

test("MD-R1 discovery, cache, draft, hidden session, and seven services", async ({
  page,
  request,
}) => {
  test.setTimeout(420_000);
  guardBrowser(page);
  checks.run_id = state.run_id;
  checks.evidence_dir = STAGE;

  // ── 1. A selected non-default model survives being hidden, including reload ──
  await page.goto("/home");
  const selector = page.getByRole("button", { name: "Select model", exact: true });
  await expect(selector).toBeEnabled({ timeout: 30_000 });
  await selector.click();
  const hiddenOption = page.getByRole("button", { name: /s15-hidden-chat/ }).last();
  await expect(hiddenOption).toBeVisible();
  await hiddenOption.click();
  await expect(selector).toContainText("s15-hidden-chat");
  await sendMessage(page, "E2E-MD-HIDDEN-BEFORE");
  await expect(page.getByText("E2E-ANSWER:E2E-MD-HIDDEN-BEFORE", { exact: false }).last()).toBeVisible({
    timeout: 60_000,
  });
  await expect.poll(() => page.url()).toMatch(/\/home\/[^/]+$/);
  const sessionUrl = page.url();
  const sessionId = sessionUrl.split("/").pop() || "";
  const sessionBefore = await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/sessions/${id}`, { cache: "no-store" });
    return response.json();
  }, sessionId);
  checks.hidden_session_url = sessionUrl;
  checks.hidden_session_before = {
    llm_selection:
      sessionBefore.preferences?.llm_selection ??
      sessionBefore.session?.preferences?.llm_selection,
    messages: sessionBefore.messages?.length ?? sessionBefore.session?.messages?.length,
    top_level_keys: Object.keys(sessionBefore),
    session_keys: sessionBefore.session ? Object.keys(sessionBefore.session) : [],
    session_preferences: sessionBefore.session?.preferences,
  };
  checks.hidden_selected_before = await selector.textContent();
  record();
  expect(sessionBefore.preferences?.llm_selection?.model_id).toBe(
    "s15-hidden-model",
  );

  await page.goto("/settings/llm");
  await expect(page.getByText("Provider connection")).toBeVisible();
  await page.getByRole("button", { name: /S15 deterministic local model/ }).first().click();
  await page.getByRole("button", { name: /^s15-hidden-chat/ }).first().click();
  const visibilityToggle = page.getByLabel("Show in chat picker", { exact: true });
  await expect(visibilityToggle).toBeChecked();
  await visibilityToggle.uncheck();
  // Keep the saved global default visible while hiding the other model.
  await page.getByRole("button", { name: /^s15-fake-chat/ }).first().click();
  await saveDraft(page);
  const hiddenCatalog = await catalog(page);
  const hiddenLlm = hiddenCatalog.catalog.services.llm;
  const hiddenProfile = hiddenLlm.profiles.find(
    (profile: any) => profile.id === "s15-local-llm-profile",
  );
  const hiddenModel = hiddenProfile.models.find(
    (model: any) => model.id === "s15-hidden-model",
  );
  const defaultModel = hiddenProfile.models.find(
    (model: any) => model.id === "s15-local-llm-model",
  );
  checks.hidden_catalog = {
    active_profile_id: hiddenLlm.active_profile_id,
    active_model_id: hiddenLlm.active_model_id,
    hidden: {
      id: hiddenModel.id,
      name: hiddenModel.name,
      model: hiddenModel.model,
      visible_in_picker: hiddenModel.visible_in_picker,
    },
    default_visible: defaultModel.visible_in_picker,
  };
  expect(hiddenLlm.active_model_id).toBe("s15-local-llm-model");
  expect(hiddenModel.id).toBe("s15-hidden-model");
  expect(hiddenModel.name).toBe("s15-hidden-chat");
  expect(hiddenModel.model).toBe("s15-hidden-chat");
  expect(hiddenModel.visible_in_picker).toBe(false);
  expect(defaultModel.visible_in_picker).not.toBe(false);

  const hiddenOptions = await llmOptions(page);
  checks.hidden_options = {
    options: hiddenOptions.options.map((item: any) => item.model_id),
    hidden_options: hiddenOptions.hidden_options?.map((item: any) => item.model_id),
    has_usable_models: hiddenOptions.has_usable_models,
  };
  expect(hiddenOptions.options.map((item: any) => item.model_id)).not.toContain(
    "s15-hidden-model",
  );
  expect(
    hiddenOptions.hidden_options.map((item: any) => item.model_id),
  ).toContain("s15-hidden-model");
  expect(hiddenOptions.has_usable_models).toBe(true);

  await page.goto(sessionUrl);
  await expect(selector).toBeEnabled({ timeout: 30_000 });
  await expect
    .poll(async () => selector.getAttribute("data-selected-model"), {
      timeout: 20_000,
    })
    .toBe("s15-local-llm-profile:s15-hidden-model");
  checks.selected_after_reload = {
    text: await selector.textContent(),
    data_selected_model: await selector.getAttribute("data-selected-model"),
    data_selected_hidden: await selector.getAttribute("data-selected-hidden"),
    options: await llmOptions(page),
  };
  record();
  await expect(selector).toContainText("(hidden)", { timeout: 20_000 });
  await selector.click();
  const hiddenCurrentRow = page
    .getByRole("button", { name: /s15-hidden-chat/ })
    .last();
  await expect(hiddenCurrentRow).toContainText("Hidden");
  await shot(page, "md-hidden-current");
  await selector.click();
  await sendMessage(page, "E2E-MD-HIDDEN-AFTER");
  await expect(page.getByText("E2E-ANSWER:E2E-MD-HIDDEN-AFTER", { exact: false }).last()).toBeVisible({
    timeout: 60_000,
  });
  checks.hidden_session_still_usable = true;

  // ── 2. Default hide is rejected, before save, with no catalog mutation ──
  await page.goto("/settings/llm");
  await page.getByRole("button", { name: /S15 deterministic local model/ }).first().click();
  await page.getByRole("button", { name: /^s15-fake-chat/ }).first().click();
  const defaultToggle = page.getByLabel("Show in chat picker", { exact: true });
  await expect(defaultToggle).toBeDisabled();
  const rejected = await page.evaluate(async () => {
    const settings = await (await fetch("/api/v1/settings", { cache: "no-store" })).json();
    const proposed = settings.catalog;
    const llm = proposed.services.llm;
    const profile = llm.profiles.find(
      (item: any) => item.id === llm.active_profile_id,
    );
    const model = profile.models.find(
      (item: any) => item.id === llm.active_model_id,
    );
    model.visible_in_picker = false;
    const response = await fetch("/api/v1/settings/catalog", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ catalog: proposed }),
    });
    return { status: response.status, body: await response.text() };
  });
  checks.default_hide_rejected = rejected.status;
  expect(rejected.status).toBe(400);
  const afterReject = await catalog(page);
  const afterDefault = afterReject.catalog.services.llm.profiles
    .find((profile: any) => profile.id === "s15-local-llm-profile")
    .models.find((model: any) => model.id === "s15-local-llm-model");
  expect(afterDefault.visible_in_picker).not.toBe(false);

  // ── 3. Search, unknown confirmation, multi-select add, draft, save ──────────
  const dialog = await openDiscovery(page);
  await ensureRow(dialog, "gpt-4.1");
  const search = dialog.getByTestId("model-discovery-search");
  await search.fill("custom/unknown-fixture");
  const unknownRow = await ensureRow(dialog, "custom/unknown-fixture");
  await expect(unknownRow.locator("input[type=checkbox]")).toBeDisabled();
  await unknownRow.getByRole("button", { name: "Confirm for this category" }).click();
  await expect(unknownRow.locator("input[type=checkbox]")).toBeEnabled();
  await search.fill("gpt-4.1");
  await ensureRow(dialog, "gpt-4.1");
  await ensureRow(dialog, "gpt-4.1-mini");
  await row(dialog, "gpt-4.1").locator("input[type=checkbox]").check();
  await row(dialog, "gpt-4.1-mini").locator("input[type=checkbox]").check();
  await shot(page, "md-dialog");
  await dialog.getByTestId("model-discovery-add").click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /^GPT 4.1 fixture/ }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^GPT 4.1 Mini fixture/ }).first()).toBeVisible();
  await shot(page, "md-added-draft");

  const beforeSave = await llmOptions(page);
  checks.added_before_save = {
    options: beforeSave.options.map((item: any) => item.model),
  };
  expect(beforeSave.options.map((item: any) => item.model)).not.toContain("gpt-4.1");

  let failedSave = false;
  await page.route("**/api/v1/settings/catalog", async (route) => {
    if (route.request().method() !== "PUT" || failedSave) {
      await route.continue();
      return;
    }
    failedSave = true;
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "simulated save failure" }),
    });
  });
  await page.getByRole("button", { name: "Save Draft", exact: true }).click();
  await expect(page.getByText("simulated save failure", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^GPT 4.1 fixture/ }).first()).toBeVisible();
  const afterFailure = await llmOptions(page);
  expect(afterFailure.options.map((item: any) => item.model)).not.toContain("gpt-4.1");
  checks.save_failure_kept_draft = true;
  await page.unroute("**/api/v1/settings/catalog");
  await saveDraft(page);
  const savedCatalog = await catalog(page);
  const savedLlm = savedCatalog.catalog.services.llm;
  const savedProfile = savedLlm.profiles.find(
    (profile: any) => profile.id === "s15-local-llm-profile",
  );
  const original = savedProfile.models.find(
    (model: any) => model.id === "s15-local-llm-model",
  );
  const savedNew = savedProfile.models.find((model: any) => model.model === "gpt-4.1");
  const savedHidden = savedProfile.models.find(
    (model: any) => model.id === "s15-hidden-model",
  );
  checks.added_after_save = {
    active_model_id: savedLlm.active_model_id,
    original,
    new_model: savedNew,
    hidden: savedHidden,
  };
  expect(savedLlm.active_model_id).toBe("s15-local-llm-model");
  expect(original.id).toBe("s15-local-llm-model");
  expect(original.name).toBe("s15-fake-chat");
  expect(original.model).toBe("s15-fake-chat");
  expect(savedNew.id).not.toBe("gpt-4.1");
  expect(savedNew.model).toBe("gpt-4.1");
  expect(savedHidden.visible_in_picker).toBe(false);

  const afterSaveOptions = await llmOptions(page);
  expect(afterSaveOptions.options.map((item: any) => item.model)).toContain("gpt-4.1");
  await page.goto("/home");
  await expect(selector).toBeEnabled({ timeout: 30_000 });
  await selector.click();
  await expect(page.getByRole("button", { name: /gpt-4.1-mini/ }).last()).toBeVisible();
  await selector.click();
  checks.saved_model_visible_in_chat = true;

  // ── 4. Save a new vision connection: first automatic query, then cache ──────
  await page.goto("/settings/vision");
  await expect(page.getByText("Provider connection")).toBeVisible();
  await expect
    .poll(async () => (await stats(request)).counts["/discovery/vision/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
  await control(request, { reset: 1, fail: 0, delayA: 0 });
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  const visionBase = page.locator('input[placeholder="https://api.openai.com/v1"]').first();
  const visionKey = page.locator('input[placeholder="sk-..."]').first();
  await visionBase.fill(`${MODEL_ORIGIN}/discovery/vision/v1`);
  await visionKey.fill("sk-s15-new-vision-fictitious");
  await page.waitForTimeout(600);
  checks.no_request_while_editing = (await stats(request)).counts["/discovery/vision/v1/models"] || 0;
  expect(checks.no_request_while_editing).toBe(0);
  await saveDraft(page);
  await expect
    .poll(async () => (await stats(request)).counts["/discovery/vision/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBe(1);
  const visionDialog = await openDiscovery(page);
  await ensureRow(visionDialog, "gpt-4o");
  await shot(page, "md-vision-new-connection");
  await closeDiscovery(page);
  await openDiscovery(page);
  await ensureRow(page.getByTestId("model-discovery-dialog"), "gpt-4o");
  await closeDiscovery(page);
  expect((await stats(request)).counts["/discovery/vision/v1/models"]).toBe(1);
  await page.reload();
  await expect(page.getByText("Provider connection")).toBeVisible();
  const visionAfterReload = await openDiscovery(page);
  await ensureRow(visionAfterReload, "gpt-4o");
  await closeDiscovery(page);
  checks.first_auto_and_cache = {
    count_after_reopen: (await stats(request)).counts["/discovery/vision/v1/models"],
  };
  expect((await stats(request)).counts["/discovery/vision/v1/models"]).toBe(1);

  // ── 5. Delayed A then B; late A must not replace B; refresh failure keeps old ─
  await page.goto("/settings/llm");
  await expect(page.getByText("Provider connection")).toBeVisible();
  await control(request, { reset: 1, fail: 0, delayA: 2500 });
  await page.getByRole("button", { name: /Discovery delay A/ }).first().click();
  await expect
    .poll(async () => (await stats(request)).counts["/discovery/a/v1/models"] || 0, {
      timeout: 10_000,
    })
    .toBe(1);
  await page.getByRole("button", { name: /Discovery delay B/ }).first().click();
  await expect
    .poll(async () => (await stats(request)).counts["/discovery/b/v1/models"] || 0, {
      timeout: 10_000,
    })
    .toBe(1);
  const abDialog = await openDiscovery(page);
  await ensureRow(abDialog, "gpt-4.1-b");
  await expect(row(abDialog, "gpt-4.1-a")).toHaveCount(0);
  await page.waitForTimeout(3_200);
  await expect(row(abDialog, "gpt-4.1-b")).toBeVisible();
  await expect(row(abDialog, "gpt-4.1-a")).toHaveCount(0);
  await shot(page, "md-delay-b");
  await row(abDialog, "gpt-4.1-b").locator("input[type=checkbox]").check();
  await abDialog.getByTestId("model-discovery-add").click();
  await expect(page.getByRole("button", { name: /^B fixture/ }).first()).toBeVisible();

  await control(request, { fail: 1 });
  await openDiscovery(page);
  const failedDialog = page.getByTestId("model-discovery-dialog");
  await failedDialog.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(failedDialog.getByText(/供应商目录服务暂时不可用/)).toBeVisible({
    timeout: 20_000,
  });
  await ensureRow(failedDialog, "gpt-4.1-b");
  await expect(page.getByRole("button", { name: /^B fixture/ }).first()).toBeVisible();
  await shot(page, "md-refresh-failure");
  await closeDiscovery(page);
  await control(request, { fail: 0, delayA: 0 });
  await page.reload();
  checks.delayed_response = "B remained after delayed A";

  // ── 6. Seven category entries; search has no entry; unsupported blocked ─────
  const categories: Array<{
    service: string;
    route: string;
    profile?: string;
    model: string;
    group?: string;
  }> = [
    { service: "llm", route: "/settings/llm", profile: "S15 deterministic local model", model: "gpt-4.1" },
    { service: "embedding", route: "/settings/embedding", profile: "Discovery embedding", model: "text-embedding-3-small" },
    { service: "stt", route: "/settings/stt", profile: "Discovery STT", model: "whisper-1" },
    { service: "tts", route: "/settings/tts", model: "tts-1" },
    { service: "imagegen", route: "/settings/image", model: "dall-e-3" },
    { service: "videogen", route: "/settings/video", model: "sora-1", group: "unsupported" },
    { service: "vision", route: "/settings/vision", model: "gpt-4o" },
  ];
  const seen: Record<string, string[]> = {};
  for (const category of categories) {
    await page.goto(category.route);
    await expect(page.getByText("Provider connection")).toBeVisible();
    if (category.profile) {
      await page.getByRole("button", { name: new RegExp(category.profile) }).first().click();
    }
    await page.getByTestId("model-discovery-open").click();
    const categoryDialog = page.getByTestId("model-discovery-dialog");
    await expect(categoryDialog).toBeVisible();
    const categoryRow = await ensureRow(categoryDialog, category.model);
    if (category.group) {
      await expect(categoryRow).toHaveAttribute("data-group", category.group);
      await expect(categoryRow.locator("input[type=checkbox]")).toBeDisabled();
    }
    seen[category.service] = await categoryDialog
      .locator('[data-testid="model-discovery-row"]')
      .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-model-id") || ""));
    if (category.service === "vision") await shot(page, "md-seven-vision");
    if (category.service === "videogen") await shot(page, "md-seven-videogen");
    await closeDiscovery(page);
  }
  checks.seven_services = seen;
  expect(Object.keys(seen).sort()).toEqual(
    ["llm", "embedding", "stt", "tts", "imagegen", "videogen", "vision"].sort(),
  );
  expect(seen.llm).not.toEqual(seen.stt);
  expect(seen.stt).not.toEqual(seen.vision);

  await page.goto("/settings/search");
  await expect(page.getByRole("heading", { name: "Search", exact: true })).toBeVisible();
  await expect(page.getByTestId("model-discovery-open")).toHaveCount(0);
  checks.search_has_no_entry = true;

  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  checks.console_errors = consoleErrors;
  record();
  expect(fs.existsSync(EVIDENCE_FILE)).toBe(true);
});

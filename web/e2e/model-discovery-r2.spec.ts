import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const STAGE =
  process.env.S15_EVIDENCE_DIR ||
  path.resolve(__dirname, "../../.phase1-evidence/model-discovery/MD-R2-browser");
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
        stage: "MD-R2",
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
  const allowed = (value: string) => {
    const url = new URL(value);
    return (
      url.hostname === "127.0.0.1" &&
      new Set([state.ports.web, state.ports.backend]).has(Number(url.port))
    );
  };
  const context = page.context();
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
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
}

async function shot(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

async function stats(request: APIRequestContext): Promise<Record<string, any>> {
  return (await (await request.get(`${MODEL_ORIGIN}/md/stats`)).json()) as Record<string, any>;
}

async function fixtureRequests(request: APIRequestContext): Promise<Record<string, any>> {
  return (await (await request.get(`${MODEL_ORIGIN}/md/requests`)).json()) as Record<string, any>;
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

async function addProfile(page: Page): Promise<number> {
  await expect(page.getByTestId("profile-tab").first()).toBeVisible();
  const before = await page.getByTestId("profile-tab").count();
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  await expect(page.getByTestId("profile-tab")).toHaveCount(before + 1);
  return before + 1;
}

async function selectProfileById(page: Page, profileId: string): Promise<void> {
  await page
    .locator(`[data-testid="profile-tab"][data-profile-id="${profileId}"]`)
    .click();
}

async function providerSelect(page: Page) {
  return page.getByRole("combobox").first();
}

async function fillConnection(
  page: Page,
  base: string,
  key: string,
  directoryUrl?: string,
): Promise<void> {
  await page
    .locator(
      'input[placeholder="https://api.openai.com/v1"], input[placeholder="https://api.openai.com/v1/embeddings"]',
    )
    .first()
    .fill(base);
  await page.locator('input[placeholder="sk-..."]').first().fill(key);
  if (directoryUrl !== undefined) {
    const extra = page.getByRole("button", { name: /Extra \(optional\)/ });
    if (await page.getByTestId("model-directory-url").isHidden()) await extra.click();
    await page.getByTestId("model-directory-url").fill(directoryUrl);
  }
}

async function selectChip(page: Page, name: RegExp): Promise<void> {
  await page.getByRole("button", { name }).first().click();
}

async function renameActiveModel(page: Page, from: RegExp, to: string): Promise<void> {
  await page.getByRole("button", { name: from }).first().dblclick();
  const input = page.getByLabel("Rename model");
  await input.fill(to);
  await input.press("Enter");
  await expect(page.getByRole("button", { name: new RegExp(to) }).first()).toBeVisible();
}

async function openChatSelector(page: Page, profileId?: string) {
  await page.getByRole("button", { name: "Select model", exact: true }).click();
  if (profileId) {
    await page
      .locator(
        `[data-testid="llm-provider-group"][data-profile-id="${profileId}"]`,
      )
      .click();
  }
  await expect(page.getByTestId("llm-option-row").first()).toBeVisible({ timeout: 30_000 });
}

function capabilityTrigger(page: Page) {
  return page
    .getByRole("button", { name: "Add files & context" })
    .locator("xpath=../..")
    .getByRole("button")
    .first();
}

async function chooseCapability(page: Page, name: string): Promise<void> {
  await capabilityTrigger(page).click();
  await page
    .getByRole("button", { name: new RegExp(`^${name}\\b`) })
    .last()
    .click();
}

test("MD-R2 provider policies, parameters, runtime budget and custom names", async ({
  page,
  request,
}) => {
  test.setTimeout(600_000);
  guardBrowser(page);
  checks.run_id = state.run_id;
  checks.evidence_dir = STAGE;
  await control(request, { reset: 1, fail: 0, delayA: 0 });

  // ── 1. DeepSeek: native-compatible structured fields, add Pro ─────────────
  await page.goto("/settings/llm");
  await expect(page.getByText("Provider connection")).toBeVisible();
  await addProfile(page);
  await (await providerSelect(page)).selectOption("deepseek");
  await fillConnection(page, `${MODEL_ORIGIN}/r2/deepseek/v1`, "sk-r2-deepseek-fictitious");
  await saveDraft(page);
  await expect
    .poll(async () => (await stats(request)).counts["/r2/deepseek/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBe(1);

  const deepseekDialog = await openDiscovery(page);
  await ensureRow(deepseekDialog, "deepseek-flash");
  await ensureRow(deepseekDialog, "deepseek-v4-pro");
  await row(deepseekDialog, "deepseek-v4-pro").locator("input[type=checkbox]").check();
  await deepseekDialog.getByTestId("model-discovery-add").click();
  await expect(page.getByTestId("llm-context-window")).toHaveValue("1048576");
  await expect(page.getByTestId("llm-max-tokens")).toHaveValue("393216");
  await renameActiveModel(page, /DeepSeek V4 Pro/, "My DeepSeek Pro");
  await saveDraft(page);
  checks.deepseek_pro_import = {
    context_window: await page.getByTestId("llm-context-window").inputValue(),
    max_tokens: await page.getByTestId("llm-max-tokens").inputValue(),
  };

  // Add Flash, then make its values manual, proving legacy/manual precedence.
  const flashDialog = await openDiscovery(page);
  await ensureRow(flashDialog, "deepseek-flash");
  await row(flashDialog, "deepseek-flash").locator("input[type=checkbox]").check();
  await flashDialog.getByTestId("model-discovery-add").click();
  await selectChip(page, /DeepSeek V4.1 Flash/);
  await page.getByTestId("llm-context-window").fill("1000000");
  await page.getByTestId("llm-max-tokens").fill("512");
  await renameActiveModel(page, /DeepSeek V4.1 Flash/, "My Flash");
  await saveDraft(page);

  // ── 2. Explicit update preview: cancel, then restore automatic values ────
  const refreshDialog = await openDiscovery(page);
  await refreshDialog.getByRole("button", { name: "Refresh", exact: true }).click();
  await ensureRow(refreshDialog, "deepseek-flash");
  await closeDiscovery(page);
  await selectChip(page, /My Flash/);
  await expect(page.getByTestId("llm-parameter-update")).toBeVisible();
  await page.getByTestId("llm-parameter-update").click();
  const preview = page.getByTestId("parameter-update-dialog");
  await expect(preview).toBeVisible();
  await expect(preview.getByTestId("parameter-update-change")).toHaveCount(0);
  await expect(preview.getByText("Manual values", { exact: true })).toBeVisible();
  await preview.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByTestId("llm-context-window")).toHaveValue("1000000");
  await expect(page.getByTestId("llm-max-tokens")).toHaveValue("512");
  checks.preview_cancel_preserved = true;

  await page.getByTestId("llm-parameter-update").click();
  await expect(preview).toBeVisible();
  await preview.getByText("Restore automatic value for context_window", { exact: true }).click();
  await preview.getByText("Restore automatic value for max_tokens", { exact: true }).click();
  await expect(preview.getByTestId("parameter-update-change")).toHaveCount(2);
  await preview.getByTestId("parameter-update-apply").click();
  await expect(page.getByTestId("llm-context-window")).toHaveValue("1048576");
  await expect(page.getByTestId("llm-max-tokens")).toHaveValue("393216");
  await saveDraft(page);
  checks.preview_restore_applied = true;

  const deepseekCatalog = await catalog(page);
  const deepseekProfile = deepseekCatalog.catalog.services.llm.profiles.find(
    (profile: any) => profile.binding === "deepseek",
  );
  const flashSaved = deepseekProfile.models.find(
    (model: any) => model.model === "deepseek-flash",
  );
  const proSaved = deepseekProfile.models.find(
    (model: any) => model.model === "deepseek-v4-pro",
  );
  expect(flashSaved.name).toBe("My Flash");
  expect(flashSaved.context_window).toBe("1048576");
  expect(flashSaved.max_tokens).toBe("393216");
  expect(flashSaved.parameter_overrides.context_window).toBe(false);
  expect(flashSaved.parameter_overrides.max_tokens).toBe(false);
  expect(proSaved.name).toBe("My DeepSeek Pro");
  checks.deepseek_saved = {
    flash: {
      name: flashSaved.name,
      model: flashSaved.model,
      context_window: flashSaved.context_window,
      max_tokens: flashSaved.max_tokens,
      overrides: flashSaved.parameter_overrides,
    },
    pro: {
      name: proSaved.name,
      model: proSaved.model,
      max_tokens: proSaved.max_tokens,
      source: proSaved.context_window_source,
    },
  };

  // ── 3. Chat uses the custom name and the real call ID/budget ─────────────
  await page.goto("/home");
  await openChatSelector(page, deepseekProfile.id);
  await page
    .locator('[data-testid="llm-option-row"][data-model-value="deepseek-v4-pro"]')
    .click();
  await expect(page.getByRole("button", { name: /Select model/ })).toContainText(
    "My DeepSeek Pro",
  );
  const input = page
    .getByRole("textbox", {
      name: /How can I help you today\?|Type a message|今天想了解|输入消息/,
    })
    .last();
  await input.fill("E2E-R2-BUDGET-PROBE");
  await input.press("Enter");
  await expect(page.getByText(/E2E-ANSWER:E2E-R2-BUDGET-PROBE/).last()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page).toHaveURL(/\/home\/[^/]+/);
  const sessionUrl = page.url();
  const fixture = await fixtureRequests(request);
  const chatCalls = fixture.requests.filter(
    (item: any) => item.model === "deepseek-v4-pro",
  );
  const chatCall = [...chatCalls]
    .reverse()
    .find((item: any) => Number(item.max_tokens) >= 1000);
  expect(chatCall).toBeTruthy();
  expect(chatCall.max_tokens).toBe(8000);
  checks.chat_call = chatCall;
  checks.chat_calls = chatCalls;
  checks.chat_selected_label = await page
    .getByRole("button", { name: /Select model/ })
    .innerText();

  // ── 4. Hidden current model keeps the custom name and stable selection ────
  // Move the saved default through the dedicated default API. Editing a model
  // in the catalog no longer changes the default implicitly.
  await page.evaluate(
    async ({ profileId, modelId }) => {
      const current = await (
        await fetch("/api/v1/settings/default-models", { cache: "no-store" })
      ).json();
      const response = await fetch("/api/v1/settings/default-models", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: current.revision,
          defaults: { llm: { profile_id: profileId, model_id: modelId } },
        }),
      });
      if (!response.ok) throw new Error(await response.text());
    },
    { profileId: deepseekProfile.id, modelId: flashSaved.id },
  );
  await page.goto("/settings/llm");
  await page.getByRole("button", { name: /DeepSeek/ }).first().click();
  await selectChip(page, /My DeepSeek Pro/);
  const visibilityToggle = page.getByLabel("Show in chat picker", { exact: true });
  await expect(visibilityToggle).toBeChecked();
  await visibilityToggle.uncheck();
  // Keep the saved default on a visible model while the session continues to
  // reference the now-hidden Pro model.
  await selectChip(page, /My Flash/);
  await saveDraft(page);
  await page.goto(sessionUrl);
  const hiddenTrigger = page.getByRole("button", { name: /Select model/ });
  await expect(hiddenTrigger).toContainText("My DeepSeek Pro (hidden)", {
    timeout: 30_000,
  });
  await expect(hiddenTrigger).toHaveAttribute("data-selected-hidden", "true");
  checks.hidden_current = {
    label: await hiddenTrigger.innerText(),
    selected_hidden: await hiddenTrigger.getAttribute("data-selected-hidden"),
  };

  // ── 4b. The quiz follow-up picker uses the same custom name and hidden state
  await chooseCapability(page, "Quiz");
  const confirmQuiz = page.getByRole("button", { name: "Confirm", exact: true });
  await expect(confirmQuiz).toBeVisible();
  await confirmQuiz.click();
  const quizInput = page
    .getByRole("textbox", {
      name: /How can I help you today\?|Type a message|今天想了解|输入消息/,
    })
    .last();
  await quizInput.fill("E2E-R2-FOLLOWUP");
  await quizInput.press("Enter");
  await expect(
    page.getByText("E2E-QUIZ-1: What is 1 + 1?", { exact: false }).first(),
  ).toBeVisible({ timeout: 90_000 });
  await page.getByTestId("quiz-answer-input").fill("2");
  await page.getByTestId("quiz-check-answer").click();
  await page.getByTestId("open-followup").first().click();
  const followupSelector = page
    .getByRole("button", { name: "Select model", exact: true })
    .last();
  await expect(followupSelector).toBeVisible({ timeout: 30_000 });
  await expect(followupSelector).toContainText("My Flash", {
    timeout: 30_000,
  });
  checks.followup_picker = {
    label: await followupSelector.innerText(),
    selected_hidden: await followupSelector.getAttribute("data-selected-hidden"),
    source_visible: true,
  };
  await page.getByRole("button", { name: "Close viewer" }).click();

  // ── 5. Aliyun LLM: one identity, explicit directory URL, qwen text model ──
  await page.goto("/settings/llm");
  await addProfile(page);
  await (await providerSelect(page)).selectOption("dashscope");
  await fillConnection(
    page,
    `${MODEL_ORIGIN}/r2/aliyun/compatible-mode/v1`,
    "sk-r2-aliyun-fictitious",
    `${MODEL_ORIGIN}/r2/aliyun/api/v1/models`,
  );
  await saveDraft(page);
  await expect
    .poll(async () => (await stats(request)).counts["/r2/aliyun/api/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
  const aliyunDialog = await openDiscovery(page);
  await ensureRow(aliyunDialog, "qwen-plus");
  await expect(row(aliyunDialog, "text-embedding-v4")).toHaveCount(0);
  await expect(row(aliyunDialog, "qwen3-asr-flash")).toHaveCount(0);
  await row(aliyunDialog, "qwen-plus").locator("input[type=checkbox]").check();
  await aliyunDialog.getByTestId("model-discovery-add").click();
  await expect(page.getByTestId("llm-context-window")).toHaveValue("1000000");
  await expect(page.getByTestId("llm-max-tokens")).toHaveValue("32768");
  await renameActiveModel(page, /通义千问 Plus/, "My Qwen Plus");
  await saveDraft(page);
  const aliyunCatalog = await catalog(page);
  const aliyunProfile = aliyunCatalog.catalog.services.llm.profiles.find(
    (profile: any) => profile.binding === "dashscope",
  );
  const qwenSaved = aliyunProfile.models.find(
    (model: any) => model.model === "qwen-plus",
  );
  expect(qwenSaved.name).toBe("My Qwen Plus");
  expect(qwenSaved.context_window).toBe("1000000");
  checks.aliyun = {
    profile_id: aliyunProfile.id,
    binding: aliyunProfile.binding,
    directory_url: aliyunProfile.model_directory_url,
    model: qwenSaved.model,
    context_window: qwenSaved.context_window,
    max_tokens: qwenSaved.max_tokens,
  };

  // ── 6. Embedding defaults do not touch the active index dimension ────────
  await page.goto("/settings/embedding");
  await expect(page.getByText("Provider connection")).toBeVisible();
  const embeddingBefore = (await catalog(page)).catalog.services.embedding;
  await addProfile(page);
  await fillConnection(page, `${MODEL_ORIGIN}/r2/embedding/v1`, "sk-r2-embedding-fictitious");
  await saveDraft(page);
  await expect
    .poll(
      async () =>
        ((await stats(request)).counts["/r2/embedding/v1/models"] || 0) +
        ((await stats(request)).counts["/r2/embedding/v1/embeddings/models"] || 0),
      { timeout: 30_000 },
    )
    .toBe(1);
  const embeddingDialog = await openDiscovery(page);
  await ensureRow(embeddingDialog, "school-embedding-default");
  await row(embeddingDialog, "school-embedding-default")
    .locator("input[type=checkbox]")
    .check();
  await embeddingDialog.getByTestId("model-discovery-add").click();
  await saveDraft(page);
  const embeddingAfter = (await catalog(page)).catalog.services.embedding;
  const importedEmbedding = embeddingAfter.profiles
    .flatMap((profile: any) => profile.models)
    .find((model: any) => model.model === "school-embedding-default");
  expect(importedEmbedding.dimension).toBe("1024");
  expect(importedEmbedding.supported_dimensions).toBe("2048,1024");
  const originalEmbedding = embeddingAfter.profiles
    .flatMap((profile: any) => profile.models)
    .find((model: any) => model.id === embeddingBefore.active_model_id);
  expect(String(originalEmbedding.dimension)).toBe("32");
  checks.embedding = {
    imported_dimension: importedEmbedding.dimension,
    choices: importedEmbedding.supported_dimensions,
    active_before: embeddingBefore.active_model_id,
    active_after: embeddingAfter.active_model_id,
    existing_dimension: originalEmbedding.dimension,
  };

  // ── 7. School gateway: prefix fallback, extra header, unknown batch confirm
  await page.goto("/settings/llm");
  await addProfile(page);
  await fillConnection(page, `${MODEL_ORIGIN}/r2/school/ai/v1`, "sk-r2-school-fictitious");
  const extraButton = page.getByRole("button", { name: /Extra \(optional\)/ });
  await extraButton.click();
  await page.locator('textarea[placeholder=\'{"APP-Code":"your-app-code"}\']').fill(
    '{"X-School-App":"demo"}',
  );
  await saveDraft(page);
  await expect
    .poll(async () => (await stats(request)).counts["/r2/school/ai/models"] || 0, {
      timeout: 30_000,
    })
    .toBe(1);
  const schoolDialog = await openDiscovery(page);
  await ensureRow(schoolDialog, "school/DeepSeek-V4");
  await ensureRow(schoolDialog, "school/Mystery");
  await schoolDialog.getByTestId("model-discovery-confirm-all").click();
  await row(schoolDialog, "school/DeepSeek-V4").locator("input[type=checkbox]").check();
  await row(schoolDialog, "school/Mystery").locator("input[type=checkbox]").check();
  await schoolDialog.getByTestId("model-discovery-add").click();
  await saveDraft(page);
  const schoolCatalog = await catalog(page);
  const schoolProfile = schoolCatalog.catalog.services.llm.profiles.find(
    (profile: any) => profile.base_url.endsWith("/r2/school/ai/v1"),
  );
  const schoolModels = schoolProfile.models.filter((model: any) =>
    model.model.startsWith("school/"),
  );
  expect(schoolModels.map((model: any) => model.model).sort()).toEqual([
    "school/DeepSeek-V4",
    "school/Mystery",
  ]);
  const deepAlias = schoolModels.find(
    (model: any) => model.model === "school/DeepSeek-V4",
  );
  expect(deepAlias.context_window).toBe("65536");
  const fixtureAfterSchool = await fixtureRequests(request);
  const schoolDirectoryCalls = fixtureAfterSchool.directory_requests.filter(
    (item: any) => item.pathname.startsWith("/r2/school/"),
  );
  expect(schoolDirectoryCalls.some((item: any) => item.school_header === "demo")).toBe(
    true,
  );
  checks.school = {
    profile_id: schoolProfile.id,
    models: schoolModels.map((model: any) => model.model),
    context_window: deepAlias.context_window,
    max_tokens: deepAlias.max_tokens,
    directory_calls: schoolDirectoryCalls,
  };

  // ── 8. Refresh failure keeps old candidates/parameters; 401 is not empty ──
  await control(request, { fail: 1 });
  await openDiscovery(page);
  await page
    .getByTestId("model-discovery-dialog")
    .getByRole("button", { name: "Refresh", exact: true })
    .click();
  const failedDialog = page.getByTestId("model-discovery-dialog");
  await expect(failedDialog.getByText(/供应商目录服务暂时不可用/)).toBeVisible({
    timeout: 20_000,
  });
  await ensureRow(failedDialog, "school/DeepSeek-V4");
  await expect(failedDialog.getByText("Stale server cache")).toBeVisible();
  checks.refresh_failure_keeps_candidates = true;
  await closeDiscovery(page);
  await control(request, { fail: 0 });

  await page.goto("/settings/llm");
  await addProfile(page);
  await fillConnection(page, `${MODEL_ORIGIN}/r2/unauthorized/v1`, "sk-r2-unauthorized");
  await saveDraft(page);
  await expect
    .poll(async () => (await stats(request)).counts["/r2/unauthorized/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBe(1);
  const unauthorizedDialog = await openDiscovery(page);
  await expect(unauthorizedDialog.getByText(/供应商拒绝了凭据/)).toBeVisible({
    timeout: 20_000,
  });
  expect((await stats(request)).counts["/r2/unauthorized/v1/models"]).toBe(1);
  checks.unauthorized = { count: 1 };
  await closeDiscovery(page);

  // ── 9. Changing directory origin while using a masked key needs re-entry ─
  await page.goto("/settings/llm");
  const currentCatalog = await catalog(page);
  const schoolProfileNow = currentCatalog.catalog.services.llm.profiles.find(
    (profile: any) => profile.base_url.endsWith("/r2/school/ai/v1"),
  );
  expect(schoolProfileNow).toBeTruthy();
  await selectProfileById(page, schoolProfileNow.id);
  await page.getByRole("button", { name: /Extra \(optional\)/ }).click();
  await page
    .getByTestId("model-directory-url")
    .fill(`http://127.0.0.1:${state.ports.web}/r2/school/ai/models`);
  await page.getByRole("button", { name: "Save Draft", exact: true }).click();
  await expect(
    page.getByText(/provider identity or URL origin changed/i),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("model-directory-url")).toHaveValue(
    `http://127.0.0.1:${state.ports.web}/r2/school/ai/models`,
  );
  checks.directory_origin_requires_reentry = true;
  checks.cross_origin_saved = false;

  // Restore the same-origin directory configuration before the invalid-URL probe.
  await page
    .getByTestId("model-directory-url")
    .fill(`${MODEL_ORIGIN}/r2/school/ai/models`);
  await saveDraft(page);

  // ── 10. Failed save keeps the draft, including the invalid directory URL ──
  const sameOriginInvalid = `${MODEL_ORIGIN}/r2/school/ai/models#fragment`;
  await page.getByTestId("model-directory-url").fill(sameOriginInvalid);
  await page.getByRole("button", { name: "Save Draft", exact: true }).click();
  await expect(
    page.getByText(/model_directory_url must not contain a fragment/),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("model-directory-url")).toHaveValue(
    sameOriginInvalid,
  );
  checks.save_failure_keeps_draft = true;

  checks.external_requests = externalRequests;
  checks.page_errors = pageErrors;
  checks.console_errors = consoleErrors;
  record();
  expect(pageErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

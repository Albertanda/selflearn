import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const STAGE =
  process.env.S15_EVIDENCE_DIR ||
  path.resolve(__dirname, "../../.phase1-evidence/model-management/MM-R3-browser");
const STATE_FILE = process.env.S15_RUN_STATE_FILE || path.join(STAGE, "run_state.json");
const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
const MODEL_ORIGIN = process.env.S15_MODEL_ORIGIN || state.origins.model;
const BACKEND_ORIGIN = state.origins.backend;
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
        stage: "MM-R3",
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

async function fixtureRequests(request: APIRequestContext): Promise<any> {
  return (await (await request.get(`${MODEL_ORIGIN}/md/requests`)).json()) as any;
}

async function requestCount(request: APIRequestContext): Promise<number> {
  return ((await fixtureRequests(request)).requests as any[]).length;
}

async function waitForChatRequest(
  request: APIRequestContext,
  after: number,
  pathname: string,
): Promise<any> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const payload = await fixtureRequests(request);
    const found = (payload.requests as any[])
      .slice(after)
      .find((item) => String(item.pathname).includes(pathname));
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`chat request not observed for ${pathname}`);
}

async function catalog(page: Page): Promise<any> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/settings", { cache: "no-store" });
    return response.json();
  });
}

async function defaultModels(page: Page): Promise<any> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/settings/default-models", {
      cache: "no-store",
    });
    return response.json();
  });
}

function mainSelector(page: Page) {
  return page.getByTestId("llm-selector-button").first();
}

function reasoningButton(page: Page) {
  return page.getByTestId("reasoning-selector-button").last();
}

async function openPicker(page: Page): Promise<void> {
  const trigger = mainSelector(page);
  await expect(trigger).toBeEnabled({ timeout: 30_000 });
  await trigger.click();
  await expect(page.getByTestId("llm-picker-menu")).toBeVisible();
}

async function chooseConnection(page: Page, profileId: string): Promise<void> {
  await page
    .locator(
      `[data-testid="llm-provider-group"][data-profile-id="${profileId}"]`,
    )
    .click();
  await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute(
    "data-view",
    "models",
  );
}

async function chooseModel(
  page: Page,
  profileId: string,
  modelId: string,
): Promise<void> {
  await openPicker(page);
  await chooseConnection(page, profileId);
  await page
    .locator(`[data-testid="llm-option-row"][data-model-id="${modelId}"]`)
    .click();
  await expect(page.getByTestId("llm-picker-menu")).toBeHidden();
}

async function chooseReasoning(page: Page, value: string): Promise<void> {
  const button = reasoningButton(page);
  await expect(button).toBeEnabled({ timeout: 30_000 });
  await button.click();
  await page
    .locator(`[data-testid="reasoning-option"][data-value="${value}"]`)
    .click();
  await expect(page.getByTestId("reasoning-menu")).toBeHidden();
}

function chatInput(page: Page) {
  return page.getByTestId("chat-composer").last().getByRole("textbox").last();
}

async function sendChat(
  page: Page,
  request: APIRequestContext,
  marker: string,
  pathname: string,
): Promise<any> {
  const before = await requestCount(request);
  const input = chatInput(page);
  await expect(input).toBeVisible({ timeout: 30_000 });
  await input.fill(marker);
  await input.press("Enter");
  await expect(
    page.getByText(`E2E-ANSWER:${marker}`, { exact: false }).last(),
  ).toBeVisible({ timeout: 90_000 });
  return waitForChatRequest(request, before, pathname);
}

async function spaToModels(page: Page): Promise<void> {
  await page.locator('nav a[href="/settings/models"]').first().click();
  await expect(page).toHaveURL(/\/settings\/models$/);
}

async function spaToDefaultModels(page: Page): Promise<void> {
  await page.locator('a[href="/settings/default-models"]').first().click();
  await expect(page).toHaveURL(/\/settings\/default-models$/);
  await expect(page.getByTestId("default-models-editor")).toBeVisible({
    timeout: 30_000,
  });
}

test("MM-R3 layered picker, reasoning wire, follow-up, defaults and edit separation", async ({
  page,
  request,
}) => {
  test.setTimeout(900_000);
  guardBrowser(page);
  checks.run_id = state.run_id;
  checks.evidence_dir = STAGE;

  // ── 1. Two-layer picker: same model name on two providers, no silent switch
  await page.goto("/home");
  const trigger = mainSelector(page);
  await expect(trigger).toBeVisible({ timeout: 60_000 });
  await expect(trigger).toContainText("Same Flash");
  await openPicker(page);
  await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute(
    "data-view",
    "providers",
  );
  await expect(page.getByTestId("llm-provider-group")).toHaveCount(4);
  const deepseekGroups = page.locator(
    '[data-testid="llm-provider-group"][data-provider="deepseek"]',
  );
  await expect(deepseekGroups).toHaveCount(2);
  const groupLabels = await deepseekGroups.allInnerTexts();
  expect(new Set(groupLabels).size).toBe(2);
  await chooseConnection(page, "r3-aliyun");
  // First-layer selection only opens the second layer.
  await expect(trigger).toContainText("Same Flash");
  await expect(trigger).not.toContainText("Qwen 3.8");
  await page.getByTestId("llm-picker-search").fill("Same");
  const searchResults = page.getByTestId("llm-search-result");
  await expect(searchResults).toHaveCount(3);
  const searchTextBoxes = await searchResults.allInnerTexts();
  expect(searchTextBoxes.some((text) => text.includes("DeepSeek"))).toBe(true);
  expect(
    searchTextBoxes.some((text) => text.includes("阿里云百炼")),
  ).toBe(true);
  await page.getByTestId("llm-picker-search").fill("");
  await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute(
    "data-view",
    "models",
  );
  await expect(page.getByTestId("llm-picker-back")).toBeVisible();
  checks.cross_connection_search = searchTextBoxes;
  await page.getByTestId("llm-picker-back").click();
  await chooseConnection(page, "r3-deepseek");
  await page
    .locator('[data-testid="llm-option-row"][data-model-id="r3-ds-flash"]')
    .click();
  await expect(trigger).toContainText("DeepSeek");
  await expect(trigger).toContainText("Same Flash");
  checks.two_layer = {
    provider_groups: 4,
    deepseek_connections: groupLabels,
    selected: await trigger.innerText(),
  };

  // ── 2. DeepSeek native low/high/max, aliases, provider default and off
  const chatRequests: any[] = [];
  await chooseReasoning(page, "effort:low");
  chatRequests.push(
    await sendChat(
      page,
      request,
      "E2E-R3-DS-LOW",
      "/r3/deepseek/v1/chat/completions",
    ),
  );
  expect(chatRequests.at(-1).model).toBe("deepseek-flash");
  expect(chatRequests.at(-1).reasoning_effort).toBe("low");
  expect(chatRequests.at(-1).thinking).toEqual({ type: "enabled" });

  await chooseReasoning(page, "effort:max");
  chatRequests.push(
    await sendChat(
      page,
      request,
      "E2E-R3-DS-MAX",
      "/r3/deepseek/v1/chat/completions",
    ),
  );
  expect(chatRequests.at(-1).reasoning_effort).toBe("max");
  expect(chatRequests.at(-1).thinking).toEqual({ type: "enabled" });

  await chooseReasoning(page, "provider_default");
  chatRequests.push(
    await sendChat(
      page,
      request,
      "E2E-R3-DS-PROVIDER",
      "/r3/deepseek/v1/chat/completions",
    ),
  );
  expect(chatRequests.at(-1).reasoning_effort).toBeNull();
  expect(chatRequests.at(-1).thinking).toBeNull();

  await chooseReasoning(page, "effort:none");
  chatRequests.push(
    await sendChat(
      page,
      request,
      "E2E-R3-DS-OFF",
      "/r3/deepseek/v1/chat/completions",
    ),
  );
  expect(chatRequests.at(-1).reasoning_effort).toBeNull();
  expect(chatRequests.at(-1).thinking).toEqual({ type: "disabled" });

  await chooseReasoning(page, "inherit");
  chatRequests.push(
    await sendChat(
      page,
      request,
      "E2E-R3-DS-INHERIT",
      "/r3/deepseek/v1/chat/completions",
    ),
  );
  expect(chatRequests.at(-1).reasoning_effort).toBe("high");
  expect(chatRequests.at(-1).thinking).toEqual({ type: "enabled" });
  checks.deepseek_reasoning = chatRequests;

  // ── 3. Aliyun Qwen 3.8: its own effort field, then reload + regenerate
  await chooseModel(page, "r3-aliyun", "r3-qwen38");
  await expect(trigger).toContainText("Qwen 3.8");
  await chooseReasoning(page, "effort:medium");
  const qwenRequest = await sendChat(
    page,
    request,
    "E2E-R3-QWEN",
    "/r3/aliyun/compatible-mode/v1/chat/completions",
  );
  expect(qwenRequest.model).toBe("qwen3.8-max");
  expect(qwenRequest.reasoning_effort).toBe("medium");
  expect(qwenRequest.enable_thinking).toBe(true);
  expect(qwenRequest.thinking_budget).toBeNull();
  checks.qwen_reasoning = qwenRequest;
  const sessionUrl = page.url();

  // Switching models restores that model's own last choice, not Qwen's.
  await chooseModel(page, "r3-deepseek", "r3-ds-flash");
  await expect(reasoningButton(page)).toHaveAttribute(
    "data-reasoning-value",
    "inherit",
  );
  await chooseModel(page, "r3-aliyun", "r3-qwen38");
  await expect(reasoningButton(page)).toHaveAttribute(
    "data-reasoning-value",
    "effort:medium",
  );
  checks.per_model_reasoning = {
    deepseek: "inherit",
    qwen: "effort:medium",
  };

  await page.reload();
  await expect(mainSelector(page)).toContainText("Qwen 3.8", {
    timeout: 60_000,
  });
  await expect(reasoningButton(page)).toHaveAttribute(
    "data-reasoning-value",
    "effort:medium",
  );
  const beforeRegen = await requestCount(request);
  await page
    .getByRole("button", { name: /Regenerate|重新生成/ })
    .last()
    .click();
  const regen = await waitForChatRequest(
    request,
    beforeRegen,
    "/r3/aliyun/compatible-mode/v1/chat/completions",
  );
  expect(regen.reasoning_effort).toBe("medium");
  await expect(reasoningButton(page)).toHaveAttribute(
    "data-reasoning-value",
    "effort:medium",
  );
  checks.reload_regenerate = {
    url: sessionUrl,
    reasoning: await reasoningButton(page).getAttribute("data-reasoning-value"),
    request: regen,
  };

  // ── 4. Unknown custom gateway exposes no invented levels
  await chooseModel(page, "r3-school", "r3-school-model");
  await expect(trigger).toContainText("School Mystery");
  await expect(page.getByTestId("reasoning-selector-button")).toHaveCount(0);
  checks.unknown_gateway = {
    selected: await trigger.innerText(),
    reasoning_controls: 0,
  };

  // ── 5. Quiz follow-up sends a real turn with the same picker/reasoning
  await page.goto("/home");
  await page.getByTestId("capability-trigger").click();
  await page.locator('[data-testid="capability-option"][data-capability="deep_question"]').click();
  const confirm = page.getByRole("button", { name: /Confirm|确认|确定/ }).first();
  await expect(confirm).toBeVisible({ timeout: 30_000 });
  await confirm.click();
  const quizInput = chatInput(page);
  await quizInput.fill("E2E-R3-QUIZ");
  await quizInput.press("Enter");
  await expect(
    page.getByText("E2E-QUIZ-1: What is 1 + 1?", { exact: false }).first(),
  ).toBeVisible({ timeout: 120_000 });
  // Wait for the final quiz payload and session hydration before answering;
  // the streaming preview is replaced when the turn completes.
  await expect(page.getByTestId("chat-composer").first().getByRole("button", { name: /^(Send|发送)$/ })).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("quiz-answer-input").fill("2");
  await expect(page.getByTestId("quiz-answer-input")).toHaveValue("2");
  await page.getByTestId("quiz-check-answer").click();
  await expect(page.getByTestId("open-followup").first()).toBeVisible({
    timeout: 30_000,
  });
  await page.getByTestId("open-followup").first().click();
  const followup = page.getByTestId("followup-composer");
  await expect(followup).toBeVisible({ timeout: 60_000 });
  const followTrigger = followup.getByTestId("llm-selector-button");
  await expect(followTrigger).toBeEnabled({ timeout: 30_000 });
  await followTrigger.click();
  await followup
    .locator('[data-testid="llm-provider-group"][data-profile-id="r3-aliyun"]')
    .click();
  await followup
    .locator('[data-testid="llm-option-row"][data-model-id="r3-qwen38"]')
    .click();
  const followReasoning = followup.getByTestId("reasoning-selector-button");
  await expect(followReasoning).toBeEnabled({ timeout: 30_000 });
  await followReasoning.click();
  await followup
    .locator('[data-testid="reasoning-option"][data-value="effort:low"]')
    .click();
  const beforeFollow = await requestCount(request);
  const followInput = followup
    .getByTestId("chat-composer")
    .getByRole("textbox")
    .last();
  await followInput.fill("E2E-R3-FOLLOWUP");
  await followInput.press("Enter");
  await expect(
    page.getByText("E2E-ANSWER:E2E-R3-FOLLOWUP", { exact: false }).last(),
  ).toBeVisible({ timeout: 90_000 });
  const followRequest = await waitForChatRequest(
    request,
    beforeFollow,
    "/r3/aliyun/compatible-mode/v1/chat/completions",
  );
  expect(followRequest.model).toBe("qwen3.8-max");
  expect(followRequest.reasoning_effort).toBe("low");
  expect(followRequest.enable_thinking).toBe(true);
  checks.followup = {
    model: followRequest.model,
    reasoning_effort: followRequest.reasoning_effort,
    enable_thinking: followRequest.enable_thinking,
  };
  const closeViewer = page.getByRole("button", {
    name: /Close viewer|关闭查看器/,
  });
  if (await closeViewer.count()) await closeViewer.first().click();

  // Reopening the same question must retain its model and per-model effort,
  // even though the composer component has unmounted in the meantime.
  await page.getByTestId("open-followup").first().click();
  await expect(followup).toBeVisible({ timeout: 30_000 });
  await expect(followTrigger).toContainText("Qwen 3.8");
  await expect(followReasoning).toHaveAttribute("data-reasoning-value", "effort:low");
  const beforeReopen = await requestCount(request);
  await followInput.fill("E2E-R3-FOLLOWUP-REOPEN");
  await followInput.press("Enter");
  await expect(page.getByText("E2E-ANSWER:E2E-R3-FOLLOWUP-REOPEN").last()).toBeVisible({ timeout: 90_000 });
  const reopenedRequest = await waitForChatRequest(request, beforeReopen, "/r3/aliyun/compatible-mode/v1/chat/completions");
  expect(reopenedRequest.model).toBe("qwen3.8-max");
  expect(reopenedRequest.reasoning_effort).toBe("low");
  checks.followup_reopen = { model: reopenedRequest.model, effort: reopenedRequest.reasoning_effort };
  if (await closeViewer.count()) await closeViewer.first().click();
  let failedFollowupHistoryOnce = false;
  let rejectFollowupHistory = true;
  await page.route("**/api/v1/sessions/*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    // React may cancel an early hydration fetch and issue a newer one. Keep
    // the outage active until the explicit retry, rather than failing only
    // an abandoned request and accidentally testing the successful one.
    if (rejectFollowupHistory && Array.isArray(body.messages) && body.messages.some((message: any) => String(message.content).includes("E2E-R3-FOLLOWUP-REOPEN"))) {
      failedFollowupHistoryOnce = true;
      return route.fulfill({ status: 503, json: { detail: "fixture follow-up history failure" } });
    }
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(page.getByTestId("open-followup").first()).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("open-followup").first().click();
  await expect(followup).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Failed to load session|加载会话失败/, { exact: true })).toBeVisible({ timeout: 30_000 });
  rejectFollowupHistory = false;
  await page.getByTestId("followup-history-retry").click();
  await expect(followTrigger).toContainText("Qwen 3.8", { timeout: 30_000 });
  await expect(followReasoning).toHaveAttribute("data-reasoning-value", "effort:low");
  const beforeRestored = await requestCount(request);
  await followInput.fill("E2E-R3-FOLLOWUP-RESTORED");
  await followInput.press("Enter");
  await expect(page.getByText("E2E-ANSWER:E2E-R3-FOLLOWUP-RESTORED").last()).toBeVisible({ timeout: 90_000 });
  const restoredRequest = await waitForChatRequest(request, beforeRestored, "/r3/aliyun/compatible-mode/v1/chat/completions");
  expect(restoredRequest.model).toBe("qwen3.8-max");
  expect(restoredRequest.reasoning_effort).toBe("low");
  expect(failedFollowupHistoryOnce).toBe(true);
  await page.unroute("**/api/v1/sessions/*");
  checks.followup_refresh = { model: restoredRequest.model, effort: restoredRequest.reasoning_effort, failed_history_retry: true };
  if (await closeViewer.count()) await closeViewer.first().click();

  // ── 6. Default page: first nav item, Chinese name, explicit save
  await page.goto("/settings/models");
  await expect(page.locator('a[href="/settings/default-models"]')).toHaveCount(1);
  const modelLeafOrder = await page
    .locator('a[href="/settings/default-models"], a[href="/settings/llm"]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")));
  expect(modelLeafOrder).toEqual([
    "/settings/default-models",
    "/settings/llm",
  ]);
  await expect(
    page.locator('a[href="/settings/default-models"]'),
  ).toContainText("默认模型");
  await expect(page.locator('a[href="/settings/llm"]')).toContainText(
    "大语言模型（LLM）",
  );
  checks.nav = {
    model_leaf_order: modelLeafOrder,
    default_label: await page
      .locator('a[href="/settings/default-models"]')
      .innerText(),
    llm_label: await page.locator('a[href="/settings/llm"]').innerText(),
  };
  await page.locator('a[href="/settings/default-models"]').click();
  await expect(page).toHaveURL(/\/settings\/default-models$/);
  await expect(page.getByTestId("default-models-editor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("default-select-llm")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("apply-catalog")).toHaveCount(0);
  await expect(page.getByTestId("default-save")).toBeDisabled();

  const cfg = await catalog(page);
  const aliProfile = cfg.catalog.services.llm.profiles.find(
    (profile: any) => profile.id === "r3-aliyun",
  );
  const aliFlash = aliProfile.models.find((model: any) => model.id === "r3-ali-flash");
  const qwen38 = aliProfile.models.find((model: any) => model.id === "r3-qwen38");
  const llmSelect = page.getByTestId("default-select-llm");
  const aliFlashValue = await llmSelect
    .locator(
      `option[data-profile-id="r3-aliyun"][data-model-id="r3-ali-flash"]`,
    )
    .getAttribute("value");
  await llmSelect.selectOption(aliFlashValue!);
  await expect(page.getByTestId("default-save")).toBeEnabled();
  await page.getByTestId("default-save").click();
  await expect
    .poll(
      async () =>
        (await catalog(page)).catalog.services.llm.active_model_id,
      { timeout: 30_000 },
    )
    .toBe("r3-ali-flash");
  const afterDefault = await catalog(page);
  expect(afterDefault.catalog.services.llm.active_profile_id).toBe("r3-aliyun");
  expect(afterDefault.catalog.services.llm.active_model_id).toBe("r3-ali-flash");
  checks.default_llm = {
    profile_id: aliProfile.id,
    model_id: aliFlash.id,
    active_after: afterDefault.catalog.services.llm,
  };

  // ── 7. 409 conflict keeps the pending choice; cancel restores saved value
  const pageDefaults = await defaultModels(page);
  const external = await request.patch(
    `${BACKEND_ORIGIN}/api/v1/settings/default-models`,
    {
      data: {
        expected_revision: pageDefaults.revision,
        defaults: {
          tts: {
            profile_id: "r3-tts-alt",
            model_id: "r3-tts-alt-model",
          },
        },
      },
    },
  );
  expect(external.ok()).toBe(true);
  const qwenValue = await llmSelect
    .locator(`option[data-profile-id="r3-aliyun"][data-model-id="r3-qwen38"]`)
    .getAttribute("value");
  await llmSelect.selectOption(qwenValue!);
  const [conflictResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/settings/default-models") &&
        response.request().method() === "PATCH",
    ),
    page.getByTestId("default-save").click(),
  ]);
  expect(conflictResponse.status()).toBe(409);
  await expect(page.getByTestId("default-models-error")).toContainText(
    /saved catalog changed|已保存的目录发生了变化/,
    { timeout: 30_000 },
  );
  await expect(llmSelect).toHaveValue(qwenValue!);
  await page.getByTestId("default-cancel").click();
  await expect(llmSelect).not.toHaveValue(qwenValue!);
  checks.default_conflict = {
    external_status: external.status(),
    ui_status: conflictResponse.status(),
    kept_selection_after_conflict: true,
    cancel_restored: true,
  };

  // ── 8. Editing/browsing/add/rename do not change the saved default
  await page.goto("/settings/llm");
  await page
    .locator('[data-testid="profile-tab"][data-profile-id="r3-aliyun"]')
    .click();
  await page
    .locator('[data-testid="model-chip"][data-model-id="r3-qwen38"]')
    .click();
  const reasons = await page
    .getByTestId("model-reasoning-effort")
    .locator("option")
    .evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLOptionElement).value),
    );
  expect(reasons).toContain("low");
  expect(reasons).toContain("medium");
  expect(reasons).toContain("xhigh");
  checks.settings_reasoning = { model: "qwen3.8-max", values: reasons };
  await page
    .locator('[data-testid="model-chip"][data-model-id="r3-qwen38"]')
    .dblclick();
  const renameInput = page.getByTestId("model-rename-input");
  await renameInput.fill("Qwen 3.8 renamed");
  await renameInput.press("Enter");
  await page.getByTestId("add-model").click();
  const newChip = page.getByTestId("model-chip").last();
  const newModelId = await newChip.getAttribute("data-model-id");
  await page.getByTestId("model-id-input").fill("e2e-draft-model");
  const afterEditing = await catalog(page);
  expect(afterEditing.catalog.services.llm.active_model_id).toBe("r3-ali-flash");

  // A draft-only model must not enter the saved-only default candidates, and
  // the dirty draft must survive the independent default save.
  await spaToModels(page);
  await spaToDefaultModels(page);
  await expect(
    page.locator(`option[data-model-id="${newModelId}"]`),
  ).toHaveCount(0);
  await expect(page.getByTestId("default-select-llm")).not.toHaveValue("");
  await spaToModels(page);
  await page.locator('a[href="/settings/llm"]').first().click();
  await expect(
    page.locator(`[data-testid="model-chip"][data-model-id="${newModelId}"]`),
  ).toHaveCount(1);
  checks.draft_survives_default_save = true;

  await page.getByTestId("save-draft").click();
  await expect(page.getByTestId("save-draft")).toBeDisabled({
    timeout: 30_000,
  });
  const afterSave = await catalog(page);
  expect(afterSave.catalog.services.llm.active_profile_id).toBe("r3-aliyun");
  expect(afterSave.catalog.services.llm.active_model_id).toBe("r3-ali-flash");
  await page.getByTestId("apply-catalog").click();
  await expect
    .poll(async () => (await catalog(page)).catalog.services.llm.active_model_id, {
      timeout: 30_000,
    })
    .toBe("r3-ali-flash");
  // A diagnostic run targets the local editor selection, never the default.
  await page.getByTestId("run-test").click();
  await page.waitForTimeout(4_000);
  const afterDiagnostics = await catalog(page);
  expect(afterDiagnostics.catalog.services.llm.active_model_id).toBe(
    "r3-ali-flash",
  );
  checks.edit_does_not_change_default = {
    active_after_edit: afterEditing.catalog.services.llm,
    active_after_save: afterSave.catalog.services.llm,
    active_after_diagnostics: afterDiagnostics.catalog.services.llm,
    new_model_id: newModelId,
  };

  // ── 9. Other default services + embedding does not call inference
  await page.goto("/settings/default-models");
  await expect(page.getByTestId("default-models-editor")).toBeVisible({
    timeout: 30_000,
  });
  const embSelect = page.getByTestId("default-select-embedding");
  const embValue = await embSelect
    .locator(
      'option[data-profile-id="r3-embed-alt"][data-model-id="r3-embed-alt-model"]',
    )
    .getAttribute("value");
  await embSelect.selectOption(embValue!);
  const searchSelect = page.getByTestId("default-select-search");
  const searchValue = await searchSelect
    .locator('option[data-profile-id="r3-search-ddgs"]')
    .getAttribute("value");
  await searchSelect.selectOption(searchValue!);
  const sttSelect = page.getByTestId("default-select-stt");
  const sttValue = await sttSelect
    .locator('option[data-profile-id="r3-stt-alt"][data-model-id="r3-stt-alt-model"]')
    .getAttribute("value");
  await sttSelect.selectOption(sttValue!);
  const beforeEmbedding = (
    await fixtureRequests(request)
  ).requests.filter((item: any) => String(item.pathname).endsWith("/embeddings"))
    .length;
  await page.getByTestId("default-save").click();
  await expect
    .poll(
      async () =>
        (await catalog(page)).catalog.services.embedding.active_profile_id,
      { timeout: 30_000 },
    )
    .toBe("r3-embed-alt");
  const afterEmbedding = (
    await fixtureRequests(request)
  ).requests.filter((item: any) => String(item.pathname).endsWith("/embeddings"))
    .length;
  expect(afterEmbedding).toBe(beforeEmbedding);
  const afterServices = await catalog(page);
  expect(afterServices.catalog.services.embedding.active_profile_id).toBe(
    "r3-embed-alt",
  );
  expect(afterServices.catalog.services.search.active_profile_id).toBe(
    "r3-search-ddgs",
  );
  expect(afterServices.catalog.services.stt.active_model_id).toBe(
    "r3-stt-alt-model",
  );
  checks.other_defaults = {
    embedding: afterServices.catalog.services.embedding.active_model_id,
    search: afterServices.catalog.services.search.active_profile_id,
    stt: afterServices.catalog.services.stt.active_model_id,
    embedding_requests_before: beforeEmbedding,
    embedding_requests_after: afterEmbedding,
  };

  // ── 10. A new chat with no explicit pick follows the newly saved default
  await page.goto("/home");
  const defaultChat = await sendChat(
    page,
    request,
    "E2E-R3-NEW-DEFAULT",
    "/r3/aliyun/compatible-mode/v1/chat/completions",
  );
  expect(defaultChat.model).toBe("deepseek-v4.1-flash");
  checks.new_default_chat = defaultChat;

  // ── 11. Narrow viewport, keyboard path through both layers, apply copy
  await page.setViewportSize({ width: 390, height: 844 });
  await openPicker(page);
  await page.getByTestId("llm-provider-group").first().focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute(
    "data-view",
    "models",
  );
  await page.getByTestId("llm-option-row").first().focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("llm-picker-menu")).toBeHidden();
  await shot(page, "r3-narrow-keyboard");
  await page.goto("/settings/llm");
  await expect(page.getByTestId("apply-catalog")).toBeVisible();
  await expect(page.getByTestId("apply-catalog")).toHaveAttribute(
    "title",
    /保存全部草稿修改|Save all draft changes/,
  );
  checks.keyboard_narrow = true;
  checks.apply_copy = await page
    .getByTestId("apply-catalog")
    .getAttribute("title");

  checks.external_requests = externalRequests;
  checks.page_errors = pageErrors;
  checks.console_errors = consoleErrors;
  record();
  await shot(page, "r3-settings-final");
  expect(pageErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

test.describe("MM-R3 touch picker", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test("provider and model layers are tappable", async ({ page }) => {
    test.setTimeout(180_000);
    guardBrowser(page);
    await page.goto("/home");
    const trigger = page.getByTestId("llm-selector-button").first();
    await expect(trigger).toBeEnabled({ timeout: 60_000 });
    await trigger.tap();
    await expect(page.getByTestId("llm-picker-menu")).toBeVisible();
    await page
      .locator(
        '[data-testid="llm-provider-group"][data-profile-id="r3-deepseek"]',
      )
      .tap();
    await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute(
      "data-view",
      "models",
    );
    await page
      .locator('[data-testid="llm-option-row"][data-model-id="r3-ds-pro"]')
      .tap();
    await expect(page.getByTestId("llm-picker-menu")).toBeHidden();
    await expect(trigger).toContainText("Same Pro");
    checks.touch_picker = {
      selected: await trigger.innerText(),
      viewport: "390x844",
    };
    record();
  });
});

test("MM-R3 picker error and empty fallbacks", async ({ page }) => {
  guardBrowser(page);
  await page.route("**/api/v1/settings/llm-options", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "E2E-R3-LLM-OPTIONS-FAIL" }),
    }),
  );
  await page.goto("/home");
  const trigger = page.getByTestId("llm-selector-button").first();
  await expect(trigger).toBeEnabled({ timeout: 60_000 });
  await expect(trigger).toContainText(/Refresh models|Models unavailable/);
  checks.picker_refresh_failure = {
    label: await trigger.innerText(),
    enabled: await trigger.isEnabled(),
  };
  await page.unroute("**/api/v1/settings/llm-options");
  await page.route("**/api/v1/settings/llm-options", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active: null,
        options: [],
        hidden_options: [],
        has_usable_models: false,
      }),
    }),
  );
  await page.reload();
  await expect(trigger).toBeEnabled({ timeout: 60_000 });
  await trigger.click();
  await expect(page.getByTestId("llm-picker-menu")).toBeVisible();
  await expect(
    page.getByText(/No models are available for this account|此账号没有可用模型/),
  ).toBeVisible();
  checks.picker_empty = {
    label: await trigger.innerText(),
    empty_state: true,
  };
  record();
});

test("MM-R3 a newer defaults page cannot make an older draft overwrite external edits", async ({ page, request }) => {
  guardBrowser(page);
  await page.goto("/settings/llm");
  const budget = page.getByTestId("llm-max-tokens");
  await expect(budget).toBeVisible({ timeout: 60_000 });
  await budget.fill("7777");
  const before = await catalog(page);
  const externalCatalog = structuredClone(before.catalog);
  externalCatalog.mm_r3_external_marker = "must survive a stale settings save";
  const external = await request.put(`${BACKEND_ORIGIN}/api/v1/settings/catalog`, {
    data: { catalog: externalCatalog, expected_revision: before.catalog_revision },
  });
  expect(external.ok()).toBe(true);

  // Keep the original SettingsProvider (and its dirty draft) mounted while
  // the independent defaults page fetches the newer saved revision.
  await spaToModels(page);
  await spaToDefaultModels(page);
  const select = page.getByTestId("default-select-llm");
  await expect(select).toBeEnabled();
  const oldValue = await select.inputValue();
  const candidates = await select.locator("option").evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLOptionElement).value).filter(Boolean),
  );
  const nextValue = candidates.find((value) => value !== oldValue)!;
  expect(nextValue).toBeTruthy();
  await select.selectOption(nextValue);
  const [patched] = await Promise.all([
    page.waitForResponse((response) => response.url().includes("/settings/default-models") && response.request().method() === "PATCH"),
    page.getByTestId("default-save").click(),
  ]);
  expect(patched.status()).toBe(200);
  await spaToModels(page);
  await page.locator('a[href="/settings/llm"]').first().click();
  await expect(budget).toHaveValue("7777");
  const [saved] = await Promise.all([
    page.waitForResponse((response) => response.url().includes("/settings/catalog") && response.request().method() === "PUT"),
    page.getByTestId("save-draft").click(),
  ]);
  expect(saved.status()).toBe(409);
  await expect(budget).toHaveValue("7777");
  expect((await catalog(page)).catalog.mm_r3_external_marker).toBe(externalCatalog.mm_r3_external_marker);
  checks.stale_draft_after_newer_default_patch = { default_patch_status: patched.status(), stale_save_status: saved.status(), external_edit_preserved: true, local_draft_preserved: true };
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  record();
});

test("MM-R3 hidden search and unknown reasoning recovery", async ({ page }) => {
  guardBrowser(page);
  let changed = false;
  await page.route("**/api/v1/settings/llm-options", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (changed) {
      const selected = payload.options.find((option: any) => option.model_id === "r3-ds-flash");
      expect(selected).toBeTruthy();
      const unknown = { supported: null, control: "unknown", levels: [], can_disable: null, default_level: null, aliases: {} };
      payload.options = payload.options.filter((option: any) => option.model_id !== selected.model_id);
      payload.hidden_options = [
        { ...selected, model_name: "Hidden selected current", hidden: true, visible_in_picker: false, reasoning_controls: unknown },
        { ...selected, model_id: "hidden-unselected", model_name: "Hidden unselected", hidden: true, visible_in_picker: false },
      ];
    }
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/home");
  await chooseModel(page, "r3-deepseek", "r3-ds-flash");
  await chooseReasoning(page, "effort:low");
  changed = true;
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/settings/llm-options")),
    page.evaluate(() => window.dispatchEvent(new Event("focus"))),
  ]);
  await expect(mainSelector(page)).toContainText("Hidden selected current");
  await openPicker(page);
  const search = page.getByTestId("llm-picker-menu").getByRole("textbox");
  await search.fill("Hidden unselected");
  await expect(page.getByTestId("llm-search-result")).toHaveCount(0);
  await search.fill("Hidden selected current");
  await expect(page.getByTestId("llm-search-result")).toHaveCount(1);
  await search.press("Escape");
  await expect(reasoningButton(page)).toBeEnabled();
  await chooseReasoning(page, "inherit");
  await expect(reasoningButton(page)).toHaveAttribute("data-reasoning-value", "inherit");
  checks.hidden_search_and_unknown_recovery = { unselected_hidden_absent: true, selected_hidden_present: true, reset_to_inherit: true };
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  record();
});

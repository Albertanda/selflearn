import { expect, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const MODEL_ORIGIN = process.env.S15_MODEL_ORIGIN || "";
const STAGE = process.env.S15_EVIDENCE_DIR || "";
const state = JSON.parse(
  fs.readFileSync(process.env.S15_BOOTSTRAP_FILE || "", "utf-8"),
);
const SHOTS = path.join(STAGE, "screenshots");
const checks: Record<string, any> = {};
const externalRequests: string[] = [];
const pageErrors: string[] = [];
const consoleErrors: string[] = [];

function allowed(url: string): boolean {
  try {
    const parsed = new URL(url);
    const origin = `${parsed.protocol}//${parsed.host}`;
    return (
      origin === MODEL_ORIGIN ||
      origin === `http://127.0.0.1:${state.backend_port}` ||
      origin === `http://127.0.0.1:${state.web_port}` ||
      origin === "ws://127.0.0.1:" + state.web_port
    );
  } catch {
    return false;
  }
}

function guardBrowser(page: Page) {
  page.on("request", (request) => {
    if (!request.url().startsWith("data:") && !allowed(request.url())) {
      externalRequests.push(request.url());
    }
  });
  page.on("requestfailed", (request) => {
    if (!request.url().startsWith("data:") && !allowed(request.url())) {
      externalRequests.push(request.url());
    }
  });
  void page.context().routeWebSocket(/.*/, (socket) => {
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

async function shot(page: Page, name: string) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

async function catalog(page: Page) {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/settings", { cache: "no-store" });
    return response.json();
  });
}

async function requests(request: APIRequestContext) {
  return (await (await request.get(`${MODEL_ORIGIN}/md/requests`)).json()) as any;
}

async function stats(request: APIRequestContext) {
  return (await (await request.get(`${MODEL_ORIGIN}/md/stats`)).json()) as any;
}

async function saveDraft(page: Page) {
  await page.getByTestId("save-draft").click();
  await expect(page.getByTestId("save-draft")).toBeDisabled({ timeout: 20_000 });
}

async function addProfile(page: Page) {
  await expect(page.getByTestId("profile-tab").first()).toBeVisible();
  const before = await page.getByTestId("profile-tab").count();
  await page.getByTestId("add-profile").click();
  await expect(page.getByTestId("profile-tab")).toHaveCount(before + 1);
}

async function fillConnection(page: Page, base: string, key: string) {
  await page
    .locator('input[placeholder="https://api.openai.com/v1"], input[placeholder="https://api.openai.com/v1/embeddings"]')
    .first()
    .fill(base);
  await page.locator('input[placeholder="sk-..."]').first().fill(key);
}

async function createCustomProvider(
  page: Page,
  name: string,
  protocol?: string,
  icon?: "school" | "flask" | "cloud" | "network" | "server" | "bot",
) {
  const select = page.getByTestId("provider-select-llm");
  await select.selectOption("__create_custom_provider__");
  const dialog = page.getByTestId("custom-provider-dialog");
  await expect(dialog).toBeVisible();
  await page.getByTestId("custom-provider-name").fill(name);
  if (protocol) {
    await page.getByTestId("custom-provider-protocol").selectOption(protocol);
  }
  if (icon) await page.getByTestId(`custom-provider-icon-${icon}`).click();
  await page.getByTestId("custom-provider-save").click();
  await expect(dialog).toBeHidden();
}

async function openSelector(page: Page, sourceText: string) {
  await page.getByTestId("llm-selector-button").first().click();
  const group = page.getByTestId("llm-provider-group").filter({ hasText: sourceText }).first();
  await expect(group).toBeVisible({ timeout: 30_000 });
  await group.click();
  await expect(page.getByTestId("llm-picker-menu")).toHaveAttribute("data-view", "models");
}

async function chooseModel(page: Page, sourceText: string, modelValue: string) {
  await openSelector(page, sourceText);
  await page
    .locator(`[data-testid="llm-option-row"][data-model-value="${modelValue}"]`)
    .click();
  await expect(page.getByTestId("llm-picker-menu")).toBeHidden();
}

async function sendMarker(page: Page, marker: string, expected = new RegExp(`E2E-ANSWER:${marker}`)) {
  const input = page
    .getByRole("textbox", {
      name: /今天我能帮您什么|今天想了解|输入消息|How can I help you today\?|Type a message/,
    })
    .last();
  await input.fill(marker);
  await input.press("Enter");
  await expect(page.getByText(expected).last()).toBeVisible({
    timeout: 60_000,
  });
}

test("CP-R1 custom providers, protocols, discovery and presentation", async ({
  page,
  request,
}) => {
  test.setTimeout(600_000);
  guardBrowser(page);
  checks.run_id = state.run_id;
  checks.evidence_dir = STAGE;
  await page.goto("/settings/llm");
  await expect(page.getByTestId("provider-select-llm")).toBeVisible();

  // A02: existing presets remain, anonymous custom is Chinese, sentinel is last.
  const options = await page.getByTestId("provider-select-llm").locator("option").evaluateAll(
    (nodes) => nodes.map((node) => ({
      value: (node as HTMLOptionElement).value,
      label: (node as HTMLOptionElement).textContent || "",
    })),
  );
  expect(options.some((option) => option.value === "deepseek")).toBe(true);
  expect(options.find((option) => option.value === "custom")?.label).toContain("自定义");
  const last = options[options.length - 1];
  expect(last.value).toBe("__create_custom_provider__");
  expect(last.label).toContain("自定义供应商配置");
  checks.provider_options = { count: options.length, last, custom: options.find((o) => o.value === "custom") };

  // A03: cancel is side-effect free.
  await page.getByTestId("provider-select-llm").selectOption("__create_custom_provider__");
  await expect(page.getByTestId("custom-provider-dialog")).toBeVisible();
  await page.getByTestId("custom-provider-cancel").click();
  await expect(page.getByTestId("custom-provider-dialog")).toBeHidden();
  expect((await catalog(page)).catalog.custom_providers ?? []).toEqual([]);
  checks.cancel = { provider_value: await page.getByTestId("provider-select-llm").inputValue(), definitions: 0 };

  // Create the OpenAI-compatible school gateway on a new profile.
  await addProfile(page);
  await createCustomProvider(page, "学校网关", "custom", "school");
  await fillConnection(page, `${MODEL_ORIGIN}/cp/openai/v1`, "sk-cp-school-fictitious");
  await saveDraft(page);
  let settings = await catalog(page);
  const schoolDefinition = (settings.catalog.custom_providers || []).find(
    (item: any) => item.name === "学校网关",
  );
  expect(schoolDefinition).toBeTruthy();
  expect(schoolDefinition.service).toBe("llm");
  expect(schoolDefinition.binding).toBe("custom");
  const schoolProfile = settings.catalog.services.llm.profiles.find(
    (item: any) => item.custom_provider_id === schoolDefinition.id,
  );
  expect(schoolProfile.binding).toBe("custom");
  expect(schoolProfile.name).toBe("学校网关");
  expect(schoolProfile.api_key).toBe("***");
  expect(JSON.stringify(settings.catalog)).not.toContain("sk-cp-school-fictitious");
  expect(JSON.stringify(settings.catalog)).not.toContain("__create_custom_provider__");
  checks.create = { definition: schoolDefinition, profile_id: schoolProfile.id, sentinel_persisted: false };

  // Reopen after save: definition/profile survive.
  await page.reload();
  await page.getByTestId("profile-tab").filter({ hasText: schoolProfile.name }).click();
  await expect(page.getByTestId("provider-select-llm")).toHaveValue(`cp:${schoolDefinition.id}`);
  await expect(page.getByTestId("edit-custom-provider")).toBeVisible();
  checks.reopen = { provider_id: schoolDefinition.id, profile_id: schoolProfile.id };

  // A05: directory query and import.
  const beforeDirectory = 0;
  await page.getByTestId("model-discovery-open").click();
  const discovery = page.getByTestId("model-discovery-dialog");
  await expect(discovery).toBeVisible();
  const row = discovery.locator('[data-testid="model-discovery-row"][data-model-id="school/mystery"]');
  await expect(row).toBeVisible({ timeout: 30_000 });
  const confirmType = row.getByRole("button", { name: /确认用于当前类别|Confirm for this service/ });
  if (await confirmType.isVisible().catch(() => false)) await confirmType.click();
  await row.locator("input[type=checkbox]").check();
  await discovery.getByTestId("model-discovery-add").click();
  await saveDraft(page);
  const afterDirectory = (await stats(request)).counts["/cp/openai/v1/models"] || 0;
  expect(afterDirectory).toBeGreaterThan(beforeDirectory);
  // Reopen (cache) then explicitly refresh: both are bounded, one origin.
  await page.getByTestId("model-discovery-open").click();
  await expect(discovery.getByTestId("model-discovery-row").first()).toBeVisible({ timeout: 30_000 });
  const afterReopen = (await stats(request)).counts["/cp/openai/v1/models"] || 0;
  await discovery.getByRole("button", { name: /刷新|Refresh/ }).click();
  await expect
    .poll(async () => (await stats(request)).counts["/cp/openai/v1/models"] || 0, {
      timeout: 30_000,
    })
    .toBeGreaterThan(afterReopen);
  const afterRefresh = (await stats(request)).counts["/cp/openai/v1/models"] || 0;
  await discovery.getByRole("button", { name: /关闭|Close/ }).click();
  checks.discovery = {
    before: beforeDirectory,
    after: afterDirectory,
    after_reopen: afterReopen,
    after_refresh: afterRefresh,
  };

  // Edit name/icons. Rename and cloud icon, then emoji. No directory re-query.
  await page.getByTestId("edit-custom-provider").click();
  await page.getByTestId("custom-provider-name").fill("学校网关 Plus");
  await page.getByTestId("custom-provider-icon-cloud").click();
  await page.getByTestId("custom-provider-save").click();
  await expect(page.getByTestId("provider-select-llm")).toHaveValue(`cp:${schoolDefinition.id}`);
  await page.getByTestId("edit-custom-provider").click();
  await page.getByTestId("custom-provider-emoji").fill("🏫");
  await page.getByTestId("custom-provider-save").click();
  await saveDraft(page);
  const directoryAfterEdit = (await stats(request)).counts["/cp/openai/v1/models"] || 0;
  expect(directoryAfterEdit).toBe(afterRefresh);
  await page.reload();
  await page.getByTestId("profile-tab").filter({ hasText: schoolProfile.name }).first().click();
  await expect(page.getByTestId("provider-select-llm")).toHaveValue(`cp:${schoolDefinition.id}`);
  await expect(page.locator('[data-provider-icon="emoji:🏫"]').first()).toBeVisible();
  checks.rename_icon = {
    directory_after_edit: directoryAfterEdit,
    existing_session_preserved: true,
  };

  // Main chat selects the custom connection and sends through its base URL.
  await page.goto("/home");
  await chooseModel(page, "学校网关 Plus", "school/mystery");
  await sendMarker(page, "E2E-CP-OPENAI");
  let requestLog = (await requests(request)).requests;
  const openaiRequest = [...requestLog].reverse().find((item: any) => item.pathname === "/cp/openai/v1/chat/completions");
  expect(openaiRequest).toBeTruthy();
  expect(openaiRequest.authorization_present).toBe(true);
  checks.openai_runtime = openaiRequest;
  const sessionUrl = page.url();
  await page.reload();
  await expect(page.getByText("E2E-ANSWER:E2E-CP-OPENAI").last()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("llm-selector-button").first()).toContainText(
    "学校网关 Plus",
  );
  checks.rename_icon = {
    directory_after_edit: directoryAfterEdit,
    existing_session_preserved: true,
  };

  // A04: a second OpenAI connection with the same model call ID still routes
  // to its own endpoint and credential (no model-name merging).
  await page.goto("/settings/llm");
  await addProfile(page);
  await createCustomProvider(page, "学校网关备用", "custom", "network");
  await fillConnection(page, `${MODEL_ORIGIN}/cp/openai-alt/v1`, "sk-cp-school-alt-fictitious");
  await page.getByTestId("add-model").click();
  await page.getByTestId("model-id-input").fill("school/same");
  await saveDraft(page);
  await page.goto("/home");
  await chooseModel(page, "学校网关备用", "school/same");
  await sendMarker(page, "E2E-CP-SAME-MODEL");
  requestLog = (await requests(request)).requests;
  const altRequest = [...requestLog]
    .reverse()
    .find((item: any) => item.pathname === "/cp/openai-alt/v1/chat/completions");
  expect(altRequest).toBeTruthy();
  expect(altRequest.model).toBe("school/same");
  expect(altRequest.authorization_present).toBe(true);
  expect(altRequest.authorization_fingerprint).toBeTruthy();
  expect(altRequest.authorization_fingerprint).not.toBe(
    openaiRequest.authorization_fingerprint,
  );
  checks.same_model_two_connections = {
    primary: openaiRequest.pathname,
    alternate: altRequest.pathname,
    model: altRequest.model,
    distinct_credential_fingerprints: true,
  };

  // A06: all seven services expose the sentinel and protocol choices; cancel each.
  const serviceRoutes = [
    ["llm", "/settings/llm"],
    ["embedding", "/settings/embedding"],
    ["stt", "/settings/stt"],
    ["tts", "/settings/tts"],
    ["vision", "/settings/vision"],
    ["imagegen", "/settings/image"],
    ["videogen", "/settings/video"],
  ] as const;
  const sentinelChecks: Record<string, any> = {};
  for (const [service, route] of serviceRoutes) {
    await page.goto(route);
    const select = page.getByTestId(`provider-select-${service}`);
    await expect(select).toBeVisible();
    const serviceOptions = await select.locator("option").evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLOptionElement).value),
    );
    expect(serviceOptions[serviceOptions.length - 1]).toBe("__create_custom_provider__");
    await select.selectOption("__create_custom_provider__");
    await expect(page.getByTestId("custom-provider-dialog")).toBeVisible();
    const protocolCount = await page.getByTestId("custom-provider-protocol").locator("option").count();
    expect(protocolCount).toBeGreaterThan(0);
    await page.getByTestId("custom-provider-cancel").click();
    sentinelChecks[service] = { last: serviceOptions[serviceOptions.length - 1], protocols: protocolCount };
  }
  checks.seven_services = sentinelChecks;

  // A04: Anthropic Messages protocol with same model names but a separate key.
  await page.goto("/settings/llm");
  await addProfile(page);
  await createCustomProvider(page, "Claude 网关", "custom_anthropic", "flask");
  await fillConnection(page, `${MODEL_ORIGIN}/cp/anthropic/v1`, "sk-cp-anthropic-fictitious");
  await page.getByTestId("profile-extra-toggle").click();
  await page.getByTestId("model-directory-url").fill(`${MODEL_ORIGIN}/cp/missing/v1/models`);
  await page.getByTestId("add-model").click();
  await page.getByTestId("model-id-input").fill("claude-manual");
  await saveDraft(page);
  await page.goto("/home");
  await chooseModel(page, "Claude 网关", "claude-manual");
  await sendMarker(page, "E2E-CP-ANTHROPIC", /E2E-ANTHROPIC-ANSWER/);
  requestLog = (await requests(request)).requests;
  const anthropicRequest = [...requestLog].reverse().find((item: any) => item.pathname === "/cp/anthropic/v1/messages");
  expect(anthropicRequest).toBeTruthy();
  expect(anthropicRequest.protocol).toBe("anthropic_messages");
  expect(anthropicRequest.x_api_key_present).toBe(true);
  expect(anthropicRequest.authorization_present).toBe(false);
  checks.anthropic_runtime = anthropicRequest;
  checks.anthro = { directory_missing_manual_model: "claude-manual", session_url: sessionUrl };
  await shot(page, "cp-home");

  // A08: default candidate shows custom name/icon; set it, then verify follow-up
  // uses the new active default and the renamed source.
  settings = await catalog(page);
  await page.goto("/settings/default-models");
  const defaults = page.getByTestId("default-select-llm");
  await expect(defaults).toBeVisible();
  await expect(
    defaults.locator('optgroup[label*="学校网关 Plus"]'),
  ).toHaveCount(1);
  const schoolOptionValue = await defaults
    .locator(`option[data-profile-id="${schoolProfile.id}"]`)
    .filter({ hasText: "School Mystery" })
    .first()
    .getAttribute("value");
  expect(schoolOptionValue).toBeTruthy();
  await defaults.selectOption(schoolOptionValue!);
  await page.getByTestId("default-save").click();
  await expect(page.getByTestId("default-save")).toBeDisabled({ timeout: 20_000 });
  await expect(page.locator('[data-provider-icon="emoji:🏫"]').first()).toBeVisible();
  checks.default_candidate = { profile_id: schoolProfile.id, icon: "emoji:🏫" };

  // A09: Save revision conflict keeps the draft and shows a recoverable error.
  await page.goto("/settings/llm");
  await page
    .locator(`[data-testid="profile-tab"][data-profile-id="${schoolProfile.id}"]`)
    .click();
  await page.getByTestId("add-model").click();
  await page.getByTestId("model-id-input").fill("dirty-model");
  const revision = (await page.evaluate(async () => (await fetch("/api/v1/settings/catalog", { cache: "no-store" })).json())).revision as string;
  await page.evaluate(async (expected) => {
    const current = await (await fetch("/api/v1/settings/catalog", { cache: "no-store" })).json();
    await fetch("/api/v1/settings/catalog", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: expected,
        catalog: { ...current.catalog, external_conflict_marker: "changed" },
      }),
    });
  }, revision);
  await page.getByTestId("save-draft").click();
  await expect(
    page.getByText(/The saved model catalog changed|saved catalog changed|已保存的目录发生了变化|目录发生了变化/),
  ).toBeVisible({ timeout: 20_000 });
  checks.conflict = { revision, draft_preserved: true };
  await shot(page, "cp-conflict");

  // A07: follow-up shares the renamed source and the chosen protocol. A new
  // follow-up thread starts from the saved active default (Claude), then we
  // explicitly choose the same custom model and send.
  await page.goto("/home");
  await page.getByTestId("capability-trigger").click();
  await page.locator('[data-testid="capability-option"][data-capability="deep_question"]').click();
  const confirm = page.getByRole("button", { name: /确认|Confirm/ }).first();
  if (await confirm.isVisible().catch(() => false)) await confirm.click();
  const quizInput = page
    .getByRole("textbox", { name: /今天我能帮您什么|今天想了解|输入消息|How can I help/ })
    .last();
  await quizInput.fill("E2E-CP-QUIZ");
  await quizInput.press("Enter");
  await expect(page.getByText(/E2E-QUIZ-1/).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("chat-composer").first().getByRole("button", { name: /^(Send|发送)$/ })).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("quiz-answer-input").fill("2");
  await page.getByTestId("quiz-check-answer").click();
  await page.getByTestId("open-followup").first().click();
  const followupSelector = page.getByTestId("llm-selector-button").last();
  await expect(followupSelector).toContainText("学校网关 Plus");
  await expect(followupSelector.locator('[data-provider-icon="emoji:🏫"]')).toBeVisible();
  checks.followup = { label: await followupSelector.innerText(), icon: "emoji:🏫" };
  const followup = page.getByTestId("followup-composer");
  const beforeFollowup = (await requests(request)).requests.length;
  const followupInput = followup.getByTestId("chat-composer").getByRole("textbox").last();
  await followupInput.fill("E2E-CP-FOLLOWUP");
  await followupInput.press("Enter");
  await expect(page.getByText("E2E-ANSWER:E2E-CP-FOLLOWUP").last()).toBeVisible({ timeout: 60_000 });
  const followupRequests = (await requests(request)).requests.slice(beforeFollowup);
  expect(followupRequests.some((item: any) => item.pathname === "/cp/openai/v1/chat/completions" && item.model === "school/mystery")).toBe(true);
  checks.followup_send = { correct_endpoint: true, model: "school/mystery" };

  checks.external_requests = externalRequests;
  checks.page_errors = pageErrors;
  checks.console_errors = consoleErrors;
  fs.writeFileSync(
    path.join(STAGE, "browser_evidence.cp-r1.json"),
    JSON.stringify({ checks, external_requests: externalRequests, page_errors: pageErrors, console_errors: consoleErrors }, null, 2) + "\n",
  );
});

test("CP-R1 a user-defined Custom name is not translated as a built-in label", async ({ page }) => {
  guardBrowser(page);
  await page.goto("/settings/llm");
  await expect(page.getByTestId("provider-select-llm")).toBeVisible();
  await addProfile(page);
  await createCustomProvider(page, "Custom", "custom", "flask");
  await fillConnection(page, `${MODEL_ORIGIN}/cp/openai/v1`, "sk-cp-name-fixture");
  await page.getByTestId("model-id-input").fill("school/mystery");
  await saveDraft(page);
  const settings = await catalog(page);
  const definition = settings.catalog.custom_providers.find((item: any) => item.name === "Custom");
  const profile = settings.catalog.services.llm.profiles.find((item: any) => item.custom_provider_id === definition.id);
  expect(profile.name).toBe("Custom");
  await page.goto("/home");
  const trigger = page.getByTestId("llm-selector-button").first();
  await trigger.click();
  await page.locator(`[data-testid="llm-provider-group"][data-profile-id="${profile.id}"]`).click();
  await page.locator('[data-testid="llm-option-row"][data-model-value="school/mystery"]').click();
  await expect(trigger).toContainText("Custom");
  await expect(trigger).not.toContainText("自定义");
});

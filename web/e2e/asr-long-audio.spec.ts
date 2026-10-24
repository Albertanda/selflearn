import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = "/api/v1";

function wavBytes(seconds = 1): Buffer {
  const rate = 16000;
  const samples = Math.max(1, Math.round(seconds * rate));
  const data = Buffer.alloc(samples * 2);
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

async function createSubject(request: any, label: string) {
  const response = await request.post(`${API}/subjects`, {
    form: { name: label, description: "", term: "2026" },
  });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()).subject as { id: string; name: string };
}

function subjectRoot(id: string): string {
  const source = process.env.S15_SOURCE_ROOT;
  if (!source) throw new Error("S15_SOURCE_ROOT is required");
  return path.join(source, "data", "user", "workspace", "subjects", id);
}

test("65s real-provider-delay job returns 202, survives refresh and publishes once", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(190_000);
  const subject = await createSubject(request, `ASR长录音-${Date.now().toString(36).slice(-5)}`);
  await page.goto(`/subjects/${subject.id}`);
  await page.getByRole("button", { name: "期末考点" }).click();
  await expect(page.getByText("课堂考点检测", { exact: true })).toBeVisible();
  const panel = page.getByText("课堂录音转写", { exact: true }).locator("xpath=../..");
  const input = panel.locator('input[type="file"]');
  await expect(input).toBeAttached();

  const postStatuses: number[] = [];
  page.on("response", (response) => {
    if (response.request().method() === "POST" && response.url().includes("/asr/jobs")) {
      postStatuses.push(response.status());
    }
  });

  const marker = `E2E-ASR-65S-${Date.now().toString(36).slice(-5)}`;
  const wav = wavBytes(2);
  const started = Date.now();
  await input.setInputFiles({ name: "asr-long-65s.wav", mimeType: "audio/wav", buffer: wav });
  await expect(panel.locator("[data-asr-job-id]")).toBeVisible({ timeout: 20_000 });
  const acceptedMs = Date.now() - started;
  expect(acceptedMs, `POST/accept took ${acceptedMs}ms`).toBeLessThan(20_000);
  await expect(panel.locator("[data-asr-job-id]")).toHaveAttribute("data-asr-job-id", /^[0-9a-f]{32}$/);
  const jobId = await panel.locator("[data-asr-job-id]").getAttribute("data-asr-job-id");
  expect(jobId).toBeTruthy();

  // The job must still be alive well past the old 30 s proxy boundary.  This
  // does not simply raise a timeout: the POST already returned 202 and the UI
  // is polling a persisted job while the provider sleeps for 65 s.
  await page.waitForTimeout(33_000);
  expect(await page.getByText(/E2E-FORCED|500|Internal Server Error/).count()).toBe(0);

  await page.reload();
  await page.getByRole("button", { name: "期末考点" }).click();
  await expect(page.getByText("课堂考点检测", { exact: true })).toBeVisible();
  const resumed = page.getByText("课堂录音转写", { exact: true }).locator("xpath=../..");
  await expect(resumed.locator("[data-asr-job-id]")).toHaveAttribute("data-asr-job-id", jobId!, { timeout: 25_000 });
  const card = page.getByText("课堂考点检测", { exact: true }).locator("xpath=..");
  await expect(card).toContainText("转写完成（1 个文件）", { timeout: 120_000 });
  await expect(card.locator("textarea")).toHaveValue(/E2E-TRANSCRIPT-B3/);
  const textareaValue = await card.locator("textarea").inputValue();
  expect(textareaValue.split("E2E-TRANSCRIPT-B3").length - 1).toBe(1);

  expect(postStatuses.every((status) => status === 202), postStatuses.join(",")).toBe(true);
  expect(postStatuses.some((status) => status === 500)).toBe(false);

  const lecture = path.join(subjectRoot(subject.id), "materials", "lecture");
  expect(fs.readFileSync(path.join(lecture, "asr-long-65s.wav")).subarray(0, 4).toString()).toBe("RIFF");
  const transcript = fs.readFileSync(path.join(lecture, "asr-long-65s.wav.transcript.txt"), "utf-8");
  expect(transcript).toContain("E2E-TRANSCRIPT-B3");
  const privateInput = path.join(subjectRoot(subject.id), ".asr_jobs", jobId!, "input");
  expect(fs.existsSync(privateInput)).toBe(false);
  expect(fs.existsSync(path.join(subjectRoot(subject.id), "knowledge_bases", "lecture-kb"))).toBe(false);

  await page.screenshot({ path: testInfo.outputPath("asr-65s-completed.png"), fullPage: true });
  expect(marker.length).toBeGreaterThan(0);
});

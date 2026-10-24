import assert from "node:assert/strict";
import test from "node:test";

import {
  createAsrJob,
  fetchAsrResult,
  getAsrJob,
  isActiveJob,
  jobStatusCopy,
  listAsrJobs,
  mergeTranscriptText,
  newRequestId,
  progressPercent,
  type AsrJobView,
} from "../lib/asr-jobs";
import type { SubjectRequest } from "../lib/subject-results";

function jobPayload(overrides: Record<string, unknown> = {}) {
  return {
    job: {
      job_id: "a".repeat(32),
      subject_id: "sub-1",
      status: "queued",
      phase: "queued",
      revision: 1,
      created_at: "2026-10-22T00:00:00Z",
      updated_at: "2026-10-22T00:00:00Z",
      files: [{ file_index: 0, name: "lecture.wav", size_bytes: 123 }],
      progress: { files_total: 1, chunks_total: 0, chunks_completed: 0, audio_total_ms: 0, audio_completed_ms: 0 },
      error: null,
      can_retry: false,
      can_cancel: true,
      result_available: false,
      ...overrides,
    },
  };
}

function response(body: unknown, status = 202): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

test("create sends repeated files plus a UUID4 request id and accepts only 202", async () => {
  let captured: { url: string; init?: RequestInit } | undefined;
  const request: SubjectRequest = async (url, init) => {
    captured = { url: String(url), init };
    return response(jobPayload());
  };
  const file = new File([new Uint8Array([1, 2, 3])], "lecture.wav", { type: "audio/wav" });
  const job = await createAsrJob({ request, subjectId: "sub-1", files: [file], requestId: "11111111-1111-4111-8111-111111111111" });
  assert.equal(job.job_id, "a".repeat(32));
  assert.equal(job.status, "queued");
  assert.match(captured!.url, /\/api\/v1\/subjects\/sub-1\/asr\/jobs$/);
  const body = captured!.init?.body;
  assert.ok(body instanceof FormData);
  assert.equal(body.get("request_id"), "11111111-1111-4111-8111-111111111111");
  assert.equal(body.get("language"), "zh");
  assert.equal((body.getAll("files")[0] as File).name, "lecture.wav");

  const wrong = async () => response(jobPayload(), 200);
  await assert.rejects(() => createAsrJob({ request: wrong, subjectId: "sub-1", files: [file] }), /无法解析/);
});

test("newRequestId is a UUID4 and is usable as a job request id", () => {
  const first = newRequestId();
  const second = newRequestId();
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notEqual(first, second);
});

test("list/get/result parse the frozen JobView shape", async () => {
  const request: SubjectRequest = async (url) => {
    if (String(url).endsWith("/result")) {
      return response({
        operation: "transcribe",
        job_id: "a".repeat(32),
        files: ["lecture.wav"],
        transcripts: [{ file: "lecture.wav", text: "hello", model: "m" }],
        message: "done",
      }, 200);
    }
    if (String(url).includes("/asr/jobs?")) return response({ jobs: [jobPayload().job] }, 200);
    return response(jobPayload(), 200);
  };
  const rows = await listAsrJobs(request, "sub-1", 20);
  assert.equal(rows.length, 1);
  const one = await getAsrJob(request, "sub-1", "a".repeat(32));
  assert.equal(one.progress.files_total, 1);
  const result = await fetchAsrResult(request, "sub-1", "a".repeat(32));
  assert.equal(result.transcripts[0].text, "hello");
});

test("a 202 is never copied as a completion and failed jobs keep their safe error", async () => {
  const queued = jobPayload().job as unknown as AsrJobView;
  assert.equal(isActiveJob(queued), true);
  assert.match(jobStatusCopy(queued), /已接收/);
  assert.doesNotMatch(jobStatusCopy(queued), /完成/);
  const failed = jobPayload({
    status: "failed",
    phase: "transcribing",
    error: { code: "asr_provider_auth", message: "凭据或权限无效。", retryable: false },
  }).job as unknown as AsrJobView;
  assert.equal(isActiveJob(failed), false);
  assert.match(jobStatusCopy(failed), /凭据/);
});

test("progress, duplicates and merge order are explicit", () => {
  const job = jobPayload().job as unknown as AsrJobView;
  assert.equal(progressPercent(job), 0);
  job.progress.chunks_total = 4;
  job.progress.chunks_completed = 3;
  assert.equal(progressPercent(job), 75);
  assert.equal(
    mergeTranscriptText([
      { file: "a", text: "same", model: "m" },
      { file: "a", text: "same", model: "m" },
      { file: "a", text: "", model: "m" },
    ]),
    "same\n\nsame",
  );
});

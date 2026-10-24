// Typed client for the ASR-R1 asynchronous job API.
//
// The browser starts an upload, receives 202, and then polls the job.  A 202 is
// never treated as a completed transcription.  All error text goes through the
// same safe C02 projection as the rest of the subject pages; no raw server body
// is displayed.

import {
  SAFE_BAD_RESPONSE,
  SubjectActionError,
  isJsonObject,
  readJsonObject,
  readSubjectFailure,
  type JsonObject,
  type SubjectRequest,
} from "./subject-results";

export const ASR_JOB_ACCEPTED = "录音已接收，正在准备转写…";
export const ASR_JOB_RECOVERED = "已找回最近一次转写任务。";
export const ASR_JOB_POLL_WARNING = "暂时无法获取转写进度，正在重试…";

export type AsrJobStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export type AsrPhase =
  | "queued"
  | "probing"
  | "segmenting"
  | "transcribing"
  | "merging"
  | "publishing"
  | "finished";

export type AsrJobError = {
  code: string;
  message: string;
  retryable: boolean;
  failed_file_index?: number;
  failed_chunk_index?: number;
};

export type AsrJobFile = {
  file_index: number;
  name: string;
  size_bytes: number;
};

export type AsrJobProgress = {
  files_total: number;
  chunks_total: number;
  chunks_completed: number;
  audio_total_ms: number;
  audio_completed_ms: number;
};

export type AsrJobView = {
  job_id: string;
  subject_id: string;
  status: AsrJobStatus;
  phase: AsrPhase;
  revision: number;
  created_at: string;
  updated_at: string;
  files: AsrJobFile[];
  progress: AsrJobProgress;
  error: AsrJobError | null;
  can_retry: boolean;
  can_cancel: boolean;
  result_available: boolean;
};

export type AsrTranscript = {
  file: string;
  text: string;
  model: string;
};

export type AsrResult = {
  operation: "transcribe";
  job_id: string;
  files: string[];
  transcripts: AsrTranscript[];
  message: string;
};

const STATUSES = new Set<AsrJobStatus>([
  "queued",
  "running",
  "cancelling",
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);
const PHASES = new Set<AsrPhase>([
  "queued",
  "probing",
  "segmenting",
  "transcribing",
  "merging",
  "publishing",
  "finished",
]);

function stringField(object: JsonObject, key: string): string | undefined {
  const value = object[key];
  return typeof value === "string" ? value : undefined;
}

function numberField(object: JsonObject, key: string): number | undefined {
  const value = object[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function integer(value: number | undefined, fallback = 0): number {
  return value === undefined || !Number.isInteger(value) ? fallback : value;
}

function parseJob(payload: unknown): AsrJobView {
  if (!isJsonObject(payload) || !isJsonObject(payload.job)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const job = payload.job;
  const status = stringField(job, "status");
  const phase = stringField(job, "phase");
  if (!status || !STATUSES.has(status as AsrJobStatus)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  if (!phase || !PHASES.has(phase as AsrPhase)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const jobId = stringField(job, "job_id");
  const subjectId = stringField(job, "subject_id");
  if (!jobId || !/^[0-9a-f]{32}$/.test(jobId) || !subjectId) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const filesRaw = job.files;
  if (!Array.isArray(filesRaw)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const files: AsrJobFile[] = filesRaw.map((row) => {
    if (!isJsonObject(row)) throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    const name = stringField(row, "name");
    const fileIndex = numberField(row, "file_index");
    if (!name || fileIndex === undefined) {
      throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    }
    return {
      file_index: integer(fileIndex),
      name,
      size_bytes: integer(numberField(row, "size_bytes")),
    };
  });
  const progressRaw = job.progress;
  if (!isJsonObject(progressRaw)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const progress: AsrJobProgress = {
    files_total: integer(numberField(progressRaw, "files_total"), files.length),
    chunks_total: integer(numberField(progressRaw, "chunks_total")),
    chunks_completed: integer(numberField(progressRaw, "chunks_completed")),
    audio_total_ms: integer(numberField(progressRaw, "audio_total_ms")),
    audio_completed_ms: integer(numberField(progressRaw, "audio_completed_ms")),
  };
  let error: AsrJobError | null = null;
  if (isJsonObject(job.error)) {
    const code = stringField(job.error, "code");
    const message = stringField(job.error, "message");
    const retryable = job.error.retryable;
    if (!code || !message || typeof retryable !== "boolean") {
      throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    }
    error = {
      code,
      message,
      retryable,
      ...(numberField(job.error, "failed_file_index") === undefined
        ? {}
        : { failed_file_index: integer(numberField(job.error, "failed_file_index")) }),
      ...(numberField(job.error, "failed_chunk_index") === undefined
        ? {}
        : { failed_chunk_index: integer(numberField(job.error, "failed_chunk_index")) }),
    };
  }
  return {
    job_id: jobId,
    subject_id: subjectId,
    status: status as AsrJobStatus,
    phase: phase as AsrPhase,
    revision: integer(numberField(job, "revision"), 1),
    created_at: stringField(job, "created_at") ?? "",
    updated_at: stringField(job, "updated_at") ?? "",
    files,
    progress,
    error,
    can_retry: job.can_retry === true,
    can_cancel: job.can_cancel === true,
    result_available: job.result_available === true,
  };
}

function parseList(payload: unknown): AsrJobView[] {
  if (!isJsonObject(payload) || !Array.isArray(payload.jobs)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  return payload.jobs.map((item) => parseJob({ job: item }));
}

function parseResult(payload: unknown, jobId: string): AsrResult {
  if (!isJsonObject(payload)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  if (stringField(payload, "operation") !== "transcribe" || stringField(payload, "job_id") !== jobId) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const files = payload.files;
  const rows = payload.transcripts;
  if (!Array.isArray(files) || files.some((item) => typeof item !== "string")) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  if (!Array.isArray(rows)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  const transcripts: AsrTranscript[] = rows.map((row) => {
    if (!isJsonObject(row)) throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    const file = stringField(row, "file");
    const text = row.text;
    const model = stringField(row, "model") ?? "";
    if (!file || typeof text !== "string") {
      throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    }
    return { file, text, model };
  });
  return {
    operation: "transcribe",
    job_id: jobId,
    files: files as string[],
    transcripts,
    message: stringField(payload, "message") ?? "转写完成。",
  };
}

export function newRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  if (cryptoApi?.getRandomValues) {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  throw new SubjectActionError("当前浏览器无法生成安全的请求编号。", "protocol");
}

export async function createAsrJob(options: {
  request: SubjectRequest;
  subjectId: string;
  files: File[];
  requestId?: string;
  language?: string;
}): Promise<AsrJobView> {
  const body = new FormData();
  for (const file of options.files) body.append("files", file);
  body.append("request_id", options.requestId ?? newRequestId());
  body.append("language", options.language ?? "zh");
  let response: Response;
  try {
    response = await options.request(
      `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/asr/jobs`,
      { method: "POST", body },
    );
  } catch {
    throw new SubjectActionError("网络连接失败，请检查网络后重试。", "network");
  }
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  if (response.status !== 202) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  return parseJob(await readJsonObject(response));
}

export async function listAsrJobs(
  request: SubjectRequest,
  subjectId: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<AsrJobView[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  const response = await request(
    `/api/v1/subjects/${encodeURIComponent(subjectId)}/asr/jobs?${query}`,
    { method: "GET", signal },
  );
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return parseList(await readJsonObject(response));
}

export async function getAsrJob(
  request: SubjectRequest,
  subjectId: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<AsrJobView> {
  const response = await request(
    `/api/v1/subjects/${encodeURIComponent(subjectId)}/asr/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET", signal },
  );
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return parseJob(await readJsonObject(response));
}

export async function cancelAsrJob(
  request: SubjectRequest,
  subjectId: string,
  jobId: string,
): Promise<AsrJobView> {
  const response = await request(
    `/api/v1/subjects/${encodeURIComponent(subjectId)}/asr/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return parseJob(await readJsonObject(response));
}

export async function retryAsrJob(
  request: SubjectRequest,
  subjectId: string,
  jobId: string,
): Promise<AsrJobView> {
  const response = await request(
    `/api/v1/subjects/${encodeURIComponent(subjectId)}/asr/jobs/${encodeURIComponent(jobId)}/retry`,
    { method: "POST" },
  );
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return parseJob(await readJsonObject(response));
}

export async function fetchAsrResult(
  request: SubjectRequest,
  subjectId: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<AsrResult> {
  const response = await request(
    `/api/v1/subjects/${encodeURIComponent(subjectId)}/asr/jobs/${encodeURIComponent(jobId)}/result`,
    { method: "GET", signal },
  );
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return parseResult(await readJsonObject(response), jobId);
}

export function isActiveJob(job: AsrJobView | null): boolean {
  return job !== null && (job.status === "queued" || job.status === "running" || job.status === "cancelling");
}

export function isTerminalJob(job: AsrJobView | null): boolean {
  return job !== null && !isActiveJob(job);
}

export function mergeTranscriptText(rows: AsrTranscript[]): string {
  return rows
    .map((row) => row.text)
    .filter((text) => text.trim().length > 0)
    .join("\n\n");
}

export function progressPercent(job: AsrJobView): number {
  if (job.progress.chunks_total > 0) {
    return Math.max(0, Math.min(100, Math.round((job.progress.chunks_completed / job.progress.chunks_total) * 100)));
  }
  if (job.progress.audio_total_ms > 0) {
    return Math.max(0, Math.min(100, Math.round((job.progress.audio_completed_ms / job.progress.audio_total_ms) * 100)));
  }
  return 0;
}

export function jobStatusCopy(job: AsrJobView): string {
  if (job.status === "queued") return ASR_JOB_ACCEPTED;
  if (job.status === "cancelling") return "正在取消转写任务…";
  if (job.status === "cancelled") return "转写任务已取消；未发布正式转写。";
  if (job.status === "interrupted") return "转写任务中断，已完成的片段保留；可显式重试。";
  if (job.status === "failed") return job.error?.message ?? "转写失败，请重试。";
  if (job.status === "completed") {
    return `转写完成（${job.files.length} 个文件）；结果已保存到该科“课堂录音”材料（materials/lecture），不会自动建立索引。`;
  }
  if (job.phase === "probing") return "正在探测录音时长与格式…";
  if (job.phase === "segmenting") return "正在按时间顺序规划录音片段…";
  if (job.phase === "merging") return "正在按时间顺序合并各段转写…";
  if (job.phase === "publishing") return "所有片段已完成，正在发布正式转写…";
  if (job.phase === "transcribing") {
    const done = job.progress.chunks_completed;
    const total = job.progress.chunks_total;
    return total > 0
      ? `正在转写 ${done}/${total} 段（${progressPercent(job)}%）…`
      : "正在转写录音片段…";
  }
  return "正在转写录音…";
}

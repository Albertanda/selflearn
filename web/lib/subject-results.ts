// Subject-page action results, safe error projection and upload/export copy.
//
// Every subject action on the two existing pages goes through the functions in
// this module.  They are deliberately UI-free (no React imports): the page
// passes its state setters and a fetch-like function, which lets the node tests
// observe the *real* busy/message/input/download choreography instead of only
// parsing a response body.
//
// Error rules (C02/C13):
// * prefer the structured ``error.message``;
// * fall back to the legacy string ``detail`` only when it is a short, plain
//   message;
// * never surface HTML, stack traces, newlines or an arbitrary response body.

export type SubjectRequest = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export type JsonObject = Record<string, unknown>;

export type FailureKind = "network" | "http" | "protocol";

export type SubjectFailure = {
  kind: FailureKind;
  message: string;
  status?: number;
  code?: string;
  retryable?: boolean;
};

export const SAFE_NETWORK_MESSAGE = "网络连接失败，请检查网络后重试。";
export const SAFE_BAD_RESPONSE = "服务返回了无法解析的内容，请重试。";
export const SAFE_UNKNOWN_MESSAGE = "操作失败，请稍后重试。";
export const SAFE_BAD_EXPORT_URL = "导出链接无效，请重试。";
export const SAFE_BAD_DOWNLOAD = "下载文件无效，请重试。";
export const EXPORT_SCOPE_NOTE =
  "科目资料与学习记录导出（不含聊天历史，不提供导入恢复）";

export class SubjectActionError extends Error {
  readonly kind: FailureKind;
  readonly status?: number;
  readonly code?: string;
  readonly retryable?: boolean;

  constructor(
    message: string,
    kind: FailureKind,
    extra: { status?: number; code?: string; retryable?: boolean } = {},
  ) {
    super(message);
    this.name = "SubjectActionError";
    this.kind = kind;
    this.status = extra.status;
    this.code = extra.code;
    this.retryable = extra.retryable;
  }
}

export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(object: JsonObject, key: string): string | undefined {
  const value = object[key];
  return typeof value === "string" ? value : undefined;
}

function numberField(object: JsonObject, key: string): number | undefined {
  const value = object[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function sanitizeServerMessage(raw: string | undefined): string | null {
  if (!raw) return null;
  const text = raw.trim();
  if (!text || text.length > 240) return null;
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text)) return null;
  // A real C02 message is one short line.  Newlines usually mean a traceback
  // leaked into ``detail``; an HTML tag means a proxy/login page did.
  if (text.includes("\n") || text.includes("\r")) return null;
  if (/<\/?[a-z][^>]*>/i.test(text)) return null;
  if (/(traceback|stack trace|File "[^"]+", line \d+|at [\w$.]+ \()/i.test(text)) {
    return null;
  }
  return text;
}

function defaultHttpMessage(status: number): string {
  if (status === 401) return "登录状态已失效，请重新登录。";
  if (status === 403) return "没有权限执行此操作。";
  if (status === 404) return "请求的内容不存在或已被删除。";
  if (status === 409) return "当前有操作正在进行，请稍后重试。";
  if (status === 422 || status === 400) return "请求参数无效，请检查后重试。";
  if (status >= 500) return "服务暂时不可用，请稍后重试。";
  return "请求未完成，请稍后重试。";
}

/** Project a non-2xx response without ever exposing its raw body. */
export async function readSubjectFailure(
  response: Response,
): Promise<SubjectFailure> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // HTML/proxy/empty body: use the fixed status copy below.
  }

  let structured: JsonObject | null = null;
  if (isJsonObject(body) && isJsonObject(body.error)) {
    structured = body.error;
  }
  const rawMessage =
    (structured && stringField(structured, "message")) ??
    (isJsonObject(body) ? stringField(body, "detail") : undefined) ??
    (typeof body === "string" ? body : undefined);
  const message =
    sanitizeServerMessage(rawMessage) ?? defaultHttpMessage(response.status);
  const code = structured ? stringField(structured, "code") : undefined;
  const retryable =
    structured && typeof structured.retryable === "boolean"
      ? structured.retryable
      : undefined;

  return {
    kind: "http",
    message,
    status: response.status,
    ...(code ? { code } : {}),
    ...(retryable === undefined ? {} : { retryable }),
  };
}

export function safeThrownMessage(error: unknown): string {
  if (error instanceof SubjectActionError) return error.message;
  if (error instanceof DOMException && error.name === "AbortError") {
    return "请求已取消。";
  }
  if (error instanceof TypeError) return SAFE_NETWORK_MESSAGE;
  return SAFE_UNKNOWN_MESSAGE;
}

export function toSubjectFailure(error: unknown): SubjectFailure {
  if (error instanceof SubjectActionError) {
    return {
      kind: error.kind,
      message: error.message,
      ...(error.status === undefined ? {} : { status: error.status }),
      ...(error.code === undefined ? {} : { code: error.code }),
      ...(error.retryable === undefined ? {} : { retryable: error.retryable }),
    };
  }
  return { kind: "network", message: safeThrownMessage(error) };
}

export async function readJsonObject(response: Response): Promise<JsonObject> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  if (!isJsonObject(body)) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  return body;
}

/**
 * Perform one JSON request and return only a verified object body.
 *
 * Network failures, non-2xx responses and malformed JSON all throw
 * ``SubjectActionError``; callers therefore cannot continue a success branch
 * after any of them.
 */
export async function requestSubjectJson(
  request: SubjectRequest,
  url: string,
  init?: RequestInit,
): Promise<JsonObject> {
  let response: Response;
  try {
    response = await request(url, init);
  } catch (error) {
    throw new SubjectActionError(safeThrownMessage(error), "network");
  }
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  return readJsonObject(response);
}

export type ActionHooks = {
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
};

export type ActionResult<T> =
  | { ok: true; value: T }
  | { ok: false; failure: SubjectFailure };

/**
 * Run an action with an observable busy boundary.
 *
 * ``setBusy(false)`` runs in ``finally`` on every path (network throw, HTTP
 * error, malformed body, success).  ``onError`` receives only the safe
 * projected message.
 */
export async function runSubjectAction<T>(
  hooks: ActionHooks,
  run: () => Promise<T>,
): Promise<ActionResult<T>> {
  if (hooks.isCurrent?.() === false) {
    return { ok: false, failure: { kind: "network", message: "请求已取消。" } };
  }
  hooks.setBusy?.(true);
  try {
    return { ok: true, value: await run() };
  } catch (error) {
    const failure = toSubjectFailure(error);
    if (hooks.isCurrent?.() !== false) hooks.onError(failure.message);
    return { ok: false, failure };
  } finally {
    if (hooks.isCurrent?.() !== false) hooks.setBusy?.(false);
  }
}

function buildFormData(fields: Record<string, string>): FormData {
  const body = new FormData();
  for (const [key, value] of Object.entries(fields)) body.append(key, value);
  return body;
}

function requireObjectField(payload: JsonObject, key: string): JsonObject {
  const value = payload[key];
  if (!isJsonObject(value)) throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  return value;
}

function transcriptsFrom(payload: JsonObject): JsonObject[] {
  const rows = arrayField(payload, "transcripts");
  if (rows.some((row) => typeof row.text !== "string")) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Subject list: create / upload / delete
// ---------------------------------------------------------------------------

export async function createSubjectAction(options: {
  request: SubjectRequest;
  name: string;
  term: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
  clearInputs: () => void;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(options.request, "/api/v1/subjects", {
        method: "POST",
        body: buildFormData({ name: options.name, term: options.term }),
      });
      const subject = requireObjectField(payload, "subject");
      if (!stringField(subject, "id")) throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
      return true;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.clearInputs();
  options.onSuccess();
  return true;
}

export async function deleteSubjectAction(options: {
  request: SubjectRequest;
  subjectId: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}`,
        { method: "DELETE" },
      );
      if (payload.status !== "deleted" || payload.subject_id !== options.subjectId) {
        throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
      }
      return true;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess();
  return true;
}

// ---------------------------------------------------------------------------
// Upload: transcribe vs index copy
// ---------------------------------------------------------------------------

export type KnowledgeStatusProjection = {
  status?: string;
  documents?: number;
  materials_in_sync?: boolean;
  busy?: boolean;
  queued?: boolean;
  progress?: { percent?: number; message?: string };
  image_coverage?: JsonObject | null;
  image_coverage_warning?: string | null;
};

export type KnowledgeProjection = {
  kb_name?: string;
  type?: string;
  documents?: number;
  status?: KnowledgeStatusProjection;
};

export type UploadOutcome = {
  operation: "transcribe" | "index";
  message: string;
  count: number;
  transcriptText?: string;
  kbName?: string;
};

function knowledgeStatus(value: unknown): KnowledgeStatusProjection | undefined {
  if (typeof value === "string") return { status: value };
  if (!isJsonObject(value)) return undefined;
  const coverage = value.image_coverage;
  const status: KnowledgeStatusProjection = {
    status: stringField(value, "status"),
    documents: numberField(value, "documents"),
    materials_in_sync:
      typeof value.materials_in_sync === "boolean"
        ? value.materials_in_sync
        : undefined,
    busy: typeof value.busy === "boolean" ? value.busy : undefined,
    queued: typeof value.queued === "boolean" ? value.queued : undefined,
    progress: isJsonObject(value.progress)
      ? { percent: numberField(value.progress, "percent"), message: stringField(value.progress, "message") }
      : undefined,
    image_coverage: isJsonObject(coverage) ? coverage : null,
    image_coverage_warning:
      typeof value.image_coverage_warning === "string"
        ? value.image_coverage_warning
        : null,
  };
  return status;
}

export function asKnowledgeProjection(
  record: JsonObject,
): KnowledgeProjection {
  return {
    kb_name: stringField(record, "kb_name"),
    type: stringField(record, "type"),
    documents: numberField(record, "documents"),
    status: knowledgeStatus(record.status),
  };
}

const INDEX_STATUS_LABELS: Record<string, string> = {
  ready: "索引已完成",
  rebuilding: "正在重建索引",
  initializing: "正在初始化索引",
  stale: "索引落后于当前资料",
  error: "上次索引失败，可重试",
};

function indexStatusCopy(status: KnowledgeStatusProjection): string {
  const name = status.status ?? "";
  const label = INDEX_STATUS_LABELS[name] ?? "状态未知";
  const queued = status.queued || status.busy ? "（任务已排队）" : "";
  return `索引状态：${label}${queued}。`;
}

function materialSyncCopy(status: KnowledgeStatusProjection): string {
  if (status.materials_in_sync === true) return "材料同步：已同步。";
  if (status.materials_in_sync === false) {
    return "材料同步：未同步（需重建索引）。";
  }
  return "材料同步：未知。";
}

function coverageCopy(status: KnowledgeStatusProjection): string {
  const coverage = status.image_coverage;
  if (!coverage) return "图片覆盖：未测量（不推断为完整）。";
  const seen = numberField(coverage, "images_seen");
  const indexed = numberField(coverage, "images_indexed");
  const skipped = numberField(coverage, "images_skipped");
  if (seen === undefined || indexed === undefined || skipped === undefined) {
    return "图片覆盖：未测量（不推断为完整）。";
  }
  return `图片覆盖：已索引 ${indexed}/${seen}，跳过 ${skipped}。`;
}

/**
 * The one honest copy projection for a C07 upload response.
 *
 * ``documents`` is the authoritative index-source count, never this upload's
 * file count and never a chunk count.  A transcribe batch never claims an
 * index was started.
 */
export function projectUploadOutcome(
  payload: JsonObject,
  record?: KnowledgeProjection,
): UploadOutcome {
  const operation = stringField(payload, "operation");
  if (operation === "transcribe") {
    const transcripts = transcriptsFrom(payload);
    const count = transcripts.length;
    const text = transcripts
      .map((item) => stringField(item, "text") ?? "")
      .filter((value) => value.length > 0)
      .join("\n\n");
    const message =
      count > 0 && text
        ? `转写完成（${count} 个文件）；转写文本已保存到该科“课堂录音”材料（materials/lecture），不会自动建立索引。`
        : "转写完成，但没有返回文本内容，请检查录音。";
    return { operation, message, count, ...(text ? { transcriptText: text } : {}) };
  }
  if (operation === "index") {
    const documents = numberField(payload, "documents");
    if (documents === undefined || !Number.isInteger(documents) || documents < 0) {
      throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    }
    const kbName = stringField(payload, "kb_name") ?? record?.kb_name;
    const fileCount = Array.isArray(payload.files) ? payload.files.length : 0;
    const saved = fileCount > 0 ? `已保存 ${fileCount} 个文件` : "文件已保存";
    const parts = [
      kbName
        ? `${saved}到知识库“${kbName}”；当前权威资料 ${documents} 个（documents 计数）。`
        : `${saved}；当前权威资料 ${documents} 个（documents 计数）。`,
    ];
    if (record?.status) {
      parts.push(indexStatusCopy(record.status));
      parts.push(materialSyncCopy(record.status));
      parts.push(coverageCopy(record.status));
      if (record.status.image_coverage_warning) {
        parts.push(`覆盖警告：${record.status.image_coverage_warning}`);
      }
    } else {
      parts.push("索引任务已排队，正在建立索引；可稍后刷新查看状态。");
      parts.push("材料同步与图片覆盖：刷新后可见。");
    }
    return {
      operation,
      message: parts.join(" "),
      count: documents,
      ...(kbName ? { kbName } : {}),
    };
  }
  throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
}

export async function uploadSubjectMaterialAction(options: {
  request: SubjectRequest;
  subjectId: string;
  files: File[];
  type: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  reloadKnowledge?: () => Promise<KnowledgeProjection[]>;
}): Promise<boolean> {
  if (options.files.length === 0) return false;
  const body = buildFormData({ type: options.type });
  for (const file of options.files) body.append("files", file);

  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/knowledge/upload`,
        { method: "POST", body },
      );
      let record: KnowledgeProjection | undefined;
      if (
        options.reloadKnowledge &&
        stringField(payload, "operation") === "index"
      ) {
        try {
          const rows = await options.reloadKnowledge();
          const kbName = stringField(payload, "kb_name");
          record = rows.find((row) => row.kb_name === kbName);
        } catch {
          // The upload itself succeeded; a status reload failure must not turn
          // it into a false upload failure (or fake a ready index).
        }
      }
      return projectUploadOutcome(payload, record);
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess(result.value.message);
  return true;
}

// ---------------------------------------------------------------------------
// Detail actions: attempt / archive / confirm / profile / review pack / export
// ---------------------------------------------------------------------------

export async function submitSubjectPostAction(options: {
  request: SubjectRequest;
  subjectId: string;
  path: string;
  fields: Record<string, string>;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}${options.path}`,
        { method: "POST", body: buildFormData(options.fields) },
      );
      requireObjectField(payload, options.path === "/profile"
        ? "profile" : options.path.startsWith("/wrong-book/") ? "entry" : "point");
      return true;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess();
  return true;
}

export function recordAttemptAction(options: {
  request: SubjectRequest;
  subjectId: string;
  entryId: string;
  correct: boolean;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  return submitSubjectPostAction({
    request: options.request,
    subjectId: options.subjectId,
    path: `/wrong-book/${encodeURIComponent(options.entryId)}/attempt`,
    fields: { correct: String(options.correct) },
    setBusy: options.setBusy,
    isCurrent: options.isCurrent,
    onError: options.onError,
    onSuccess: options.onSuccess,
  });
}

export function archiveEntryAction(options: {
  request: SubjectRequest;
  subjectId: string;
  entryId: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  return submitSubjectPostAction({
    request: options.request,
    subjectId: options.subjectId,
    path: `/wrong-book/${encodeURIComponent(options.entryId)}/archive`,
    fields: {},
    setBusy: options.setBusy,
    isCurrent: options.isCurrent,
    onError: options.onError,
    onSuccess: options.onSuccess,
  });
}

export function confirmExamPointAction(options: {
  request: SubjectRequest;
  subjectId: string;
  pointId: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  return submitSubjectPostAction({
    request: options.request,
    subjectId: options.subjectId,
    path: `/exam-points/${encodeURIComponent(options.pointId)}/confirm`,
    fields: {},
    setBusy: options.setBusy,
    isCurrent: options.isCurrent,
    onError: options.onError,
    onSuccess: options.onSuccess,
  });
}

export function saveProfileAction(options: {
  request: SubjectRequest;
  subjectId: string;
  goals: string;
  explanationStyle: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: () => void;
}): Promise<boolean> {
  return submitSubjectPostAction({
    request: options.request,
    subjectId: options.subjectId,
    path: "/profile",
    fields: {
      goals: options.goals,
      explanation_style: options.explanationStyle,
    },
    setBusy: options.setBusy,
    isCurrent: options.isCurrent,
    onError: options.onError,
    onSuccess: options.onSuccess,
  });
}

export function outputDownloadUrl(payload: JsonObject): string | null {
  const url = stringField(payload, "url");
  if (!url) return null;
  if (!url.startsWith("/api/outputs/") || url.startsWith("//")) return null;
  if (url.includes("..") || url.includes("\\") || url.includes("\n")) return null;
  return url;
}

/** Fetch the actual bytes before announcing a download; never save an error page. */
export async function fetchSubjectArtifact(
  request: SubjectRequest, url: string, format: "zip" | "pdf" | "docx",
): Promise<Blob> {
  if (!outputDownloadUrl({url})) throw new SubjectActionError(SAFE_BAD_EXPORT_URL, "protocol");
  const response = await request(url, {method: "GET"});
  if (!response.ok) {
    const failure = await readSubjectFailure(response);
    throw new SubjectActionError(failure.message, "http", failure);
  }
  const blob = await response.blob();
  const prefix = new Uint8Array(await blob.slice(0, 8).arrayBuffer());
  const valid = format === "pdf"
    ? blob.size >= 8 && new TextDecoder().decode(prefix).startsWith("%PDF-")
    : blob.size >= 22 && prefix[0] === 0x50 && prefix[1] === 0x4b
      && ((prefix[2] === 3 && prefix[3] === 4) || (prefix[2] === 5 && prefix[3] === 6));
  if (!valid || /text\/html|application\/json/i.test(blob.type)) {
    throw new SubjectActionError(SAFE_BAD_DOWNLOAD, "protocol");
  }
  return blob;
}

export async function exportSubjectAction(options: {
  request: SubjectRequest;
  subjectId: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: (url: string) => void;
  openDownload: (url: string) => void | Promise<void>;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/export`,
        { method: "GET" },
      );
      const url = outputDownloadUrl(payload);
      if (!url) throw new SubjectActionError(SAFE_BAD_EXPORT_URL, "protocol");
      if (options.isCurrent?.() === false) return url;
      await options.openDownload(url);
      return url;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess(result.value);
  return true;
}

export async function generateReviewPackAction(options: {
  request: SubjectRequest;
  subjectId: string;
  format: "pdf" | "docx";
  term?: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: (url: string) => void;
  openDownload: (url: string) => void | Promise<void>;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/review-pack`,
        {
          method: "POST",
          body: buildFormData({
            format: options.format,
            term: options.term ?? "",
          }),
        },
      );
      const url = outputDownloadUrl(payload);
      if (!url) throw new SubjectActionError(SAFE_BAD_EXPORT_URL, "protocol");
      if (options.isCurrent?.() === false) return url;
      await options.openDownload(url);
      return url;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess(result.value);
  return true;
}

// ---------------------------------------------------------------------------
// Detail: ASR upload + exam-point detection
// ---------------------------------------------------------------------------

export type AudioUploadOutcome = { message: string; text: string; count: number };

export async function uploadAudioAction(options: {
  request: SubjectRequest;
  subjectId: string;
  files: File[];
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: (outcome: AudioUploadOutcome) => void;
}): Promise<boolean> {
  if (options.files.length === 0) return false;
  const body = buildFormData({ type: "lecture" });
  for (const file of options.files) body.append("files", file);

  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/knowledge/upload`,
        { method: "POST", body },
      );
      const operation = stringField(payload, "operation");
      if (operation !== "transcribe") {
        throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
      }
      const transcripts = transcriptsFrom(payload);
      const text = transcripts
        .map((item) => stringField(item, "text") ?? "")
        .filter((value) => value.length > 0)
        .join("\n\n");
      const message = text
        ? `转写完成（${transcripts.length} 个文件）；转写文本已保存到该科“课堂录音”材料（materials/lecture），并填入下方检测框，不会自动建立索引。`
        : "转写完成，但没有返回文本内容，请检查录音。";
      return { message, text, count: transcripts.length };
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess(result.value);
  return true;
}

export async function detectExamPointsAction(options: {
  request: SubjectRequest;
  subjectId: string;
  transcript: string;
  term?: string;
  setBusy?: (busy: boolean) => void;
  isCurrent?: () => boolean;
  onError: (message: string) => void;
  onSuccess: (message: string, detected: number) => void;
}): Promise<boolean> {
  const result = await runSubjectAction(
    options,
    async () => {
      const payload = await requestSubjectJson(
        options.request,
        `/api/v1/subjects/${encodeURIComponent(options.subjectId)}/exam-points/detect`,
        {
          method: "POST",
          body: buildFormData({
            transcript: options.transcript,
            term: options.term ?? "",
          }),
        },
      );
      const detected = numberField(payload, "detected");
      if (detected === undefined || !Number.isInteger(detected) || detected < 0) {
        throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
      }
      return detected;
    },
  );
  if (!result.ok || options.isCurrent?.() === false) return false;
  options.onSuccess(
    `检出 ${result.value} 条候选考点（明示已自动确认，其余请在列表中确认）`,
    result.value,
  );
  return true;
}

// ---------------------------------------------------------------------------
// Read paths: list + detail
// ---------------------------------------------------------------------------

export type SubjectsView = {
  subjects: JsonObject[];
  knowledge: Record<string, KnowledgeProjection[]>;
};

export async function loadSubjectsView(options: {
  request: SubjectRequest;
  onLoaded: (view: SubjectsView) => void;
  onError?: (message: string) => void;
  notify?: boolean;
  isCurrent?: () => boolean;
}): Promise<SubjectsView | null> {
  let payload: JsonObject;
  try {
    payload = await requestSubjectJson(options.request, "/api/v1/subjects");
    const subjects = arrayField(payload, "subjects");
    if (subjects.some((row) => !stringField(row, "id"))) {
      throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
    }
  } catch (error) {
    if (options.notify !== false && options.isCurrent?.() !== false) {
      options.onError?.(toSubjectFailure(error).message);
    }
    return null;
  }

  const subjects = arrayField(payload, "subjects");
  const pairs = await Promise.all(
    subjects.map(async (subject) => {
      const id = stringField(subject, "id");
      if (!id) return [null, null] as const;
      try {
        const kbPayload = await requestSubjectJson(
          options.request,
          `/api/v1/subjects/${encodeURIComponent(id)}/knowledge`,
        );
        const rows = arrayField(kbPayload, "knowledge").map(asKnowledgeProjection);
        return [id, rows] as const;
      } catch {
        return [id, null] as const;
      }
    }),
  );

  const knowledge: Record<string, KnowledgeProjection[]> = {};
  let failed = 0;
  for (const [id, rows] of pairs) {
    if (!id) continue;
    if (rows === null) failed += 1;
    else knowledge[id] = rows;
  }
  if (options.isCurrent?.() === false) return null;
  options.onLoaded({ subjects, knowledge });
  if (failed > 0 && options.notify !== false) {
    options.onError?.("部分知识库状态加载失败，请稍后重试。");
  }
  return { subjects, knowledge };
}

export type SubjectDetailView = {
  knowledge: JsonObject[];
  wrongs: JsonObject[];
  points: JsonObject[];
  profile: JsonObject | null;
  loaded: { knowledge: boolean; wrongs: boolean; points: boolean; profile: boolean };
};

type Fetched = { ok: true; body: JsonObject } | { ok: false; failure: SubjectFailure };

async function fetchJson(
  request: SubjectRequest,
  url: string,
): Promise<Fetched> {
  try {
    return { ok: true, body: await requestSubjectJson(request, url) };
  } catch (error) {
    return { ok: false, failure: toSubjectFailure(error) };
  }
}

function arrayField(body: JsonObject, key: string): JsonObject[] {
  const value = body[key];
  if (!Array.isArray(value) || value.some((row) => !isJsonObject(row))) {
    throw new SubjectActionError(SAFE_BAD_RESPONSE, "protocol");
  }
  return value as JsonObject[];
}

export async function loadSubjectDetail(options: {
  request: SubjectRequest;
  subjectId: string;
  onLoaded: (view: SubjectDetailView) => void;
  onError?: (message: string) => void;
  notify?: boolean;
  isCurrent?: () => boolean;
}): Promise<boolean> {
  const base = `/api/v1/subjects/${encodeURIComponent(options.subjectId)}`;
  const [knowledge, wrongs, points, profile] = await Promise.all([
    fetchJson(options.request, `${base}/knowledge`),
    fetchJson(options.request, `${base}/wrong-book`),
    fetchJson(options.request, `${base}/exam-points`),
    fetchJson(options.request, `${base}/profile`),
  ]);

  const failures: SubjectFailure[] = [];
  const view: SubjectDetailView = {
    knowledge: [],
    wrongs: [],
    points: [],
    profile: null,
    loaded: { knowledge: false, wrongs: false, points: false, profile: false },
  };

  if (knowledge.ok) {
    try {
      view.knowledge = arrayField(knowledge.body, "knowledge");
      view.loaded.knowledge = true;
    } catch (error) {
      failures.push(toSubjectFailure(error));
    }
  } else failures.push(knowledge.failure);

  if (wrongs.ok) {
    try {
      view.wrongs = arrayField(wrongs.body, "entries");
      view.loaded.wrongs = true;
    } catch (error) {
      failures.push(toSubjectFailure(error));
    }
  } else failures.push(wrongs.failure);

  if (points.ok) {
    try {
      view.points = arrayField(points.body, "points");
      view.loaded.points = true;
    } catch (error) {
      failures.push(toSubjectFailure(error));
    }
  } else failures.push(points.failure);

  if (profile.ok) {
    try {
      view.profile = requireObjectField(profile.body, "profile");
      view.loaded.profile = true;
    } catch (error) {
      failures.push(toSubjectFailure(error));
    }
  } else failures.push(profile.failure);

  if (options.isCurrent?.() === false) return false;
  options.onLoaded(view);
  if (failures.length > 0 && options.notify !== false) {
    options.onError?.(failures[0].message);
  }
  return failures.length === 0;
}

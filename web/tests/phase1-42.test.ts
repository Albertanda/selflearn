import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

import {
  EXPORT_SCOPE_NOTE,
  SAFE_BAD_EXPORT_URL,
  SAFE_BAD_RESPONSE,
  SAFE_NETWORK_MESSAGE,
  archiveEntryAction,
  createSubjectAction,
  deleteSubjectAction,
  detectExamPointsAction,
  exportSubjectAction,
  generateReviewPackAction,
  loadSubjectDetail,
  loadSubjectsView,
  recordAttemptAction,
  saveProfileAction,
  uploadAudioAction,
  uploadSubjectMaterialAction,
  type SubjectRequest,
} from "../lib/subject-results";

type Reply =
  | { kind: "response"; make: () => Response }
  | { kind: "throw"; error: Error };

function json(body: unknown, status = 200): Reply {
  return {
    kind: "response",
    make: () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  };
}

function raw(
  body: string,
  status = 200,
  contentType = "text/html; charset=utf-8",
): Reply {
  return {
    kind: "response",
    make: () =>
      new Response(body, {
        status,
        headers: { "content-type": contentType },
      }),
  };
}

function boom(error: Error = new TypeError("Failed to fetch")): Reply {
  return { kind: "throw", error };
}

function responder(replies: Reply[]): {
  request: SubjectRequest;
  calls: { url: string; init?: RequestInit }[];
} {
  const calls: { url: string; init?: RequestInit }[] = [];
  let index = 0;
  const request: SubjectRequest = async (input, init) => {
    calls.push({ url: String(input), init });
    const reply = replies[Math.min(index, replies.length - 1)];
    index += 1;
    if (!reply) throw new Error("no reply configured");
    if (reply.kind === "throw") throw reply.error;
    return reply.make();
  };
  return { request, calls };
}

function busyRecorder(): {
  values: boolean[];
  setBusy: (value: boolean) => void;
} {
  const values: boolean[] = [];
  return { values, setBusy: (value: boolean) => values.push(value) };
}

function uploadedForm(init?: RequestInit): FormData {
  assert.ok(init?.body instanceof FormData);
  return init.body;
}

test("a failed create ends busy and keeps the inputs", async () => {
  const { request } = responder([boom()]);
  const busy = busyRecorder();
  let success = 0;
  let cleared = 0;
  let message = "";

  const ok = await createSubjectAction({
    request,
    name: "常微分方程",
    term: "2026秋",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
    clearInputs: () => {
      cleared += 1;
    },
  });

  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, SAFE_NETWORK_MESSAGE);
  assert.equal(success, 0);
  assert.equal(cleared, 0);
});

test("C02 error.message wins over the legacy detail and is shown safely", async () => {
  const { request } = responder([
    json(
      {
        detail: "旧版 detail 不应优先",
        error: {
          code: "invalid_input",
          message: "科目名称已存在。",
          retryable: false,
        },
      },
      409,
    ),
  ]);
  let message = "";
  let success = 0;
  let cleared = 0;

  const ok = await createSubjectAction({
    request,
    name: "重复科目",
    term: "",
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
    clearInputs: () => {
      cleared += 1;
    },
  });

  assert.equal(ok, false);
  assert.equal(message, "科目名称已存在。");
  assert.equal(success, 0);
  assert.equal(cleared, 0);
});

test("legacy string detail still works, but HTML/tracebacks never reach the UI", async () => {
  const legacy = responder([json({ detail: "旧版错误：请重新填写。" }, 400)]);
  let legacyMessage = "";
  await createSubjectAction({
    request: legacy.request,
    name: "科目",
    term: "",
    onError: (value) => {
      legacyMessage = value;
    },
    onSuccess: () => undefined,
    clearInputs: () => undefined,
  });
  assert.equal(legacyMessage, "旧版错误：请重新填写。");

  const html = responder([
    json({ detail: "<html><body>proxy login</body></html>" }, 502),
  ]);
  let htmlMessage = "";
  await createSubjectAction({
    request: html.request,
    name: "科目",
    term: "",
    onError: (value) => {
      htmlMessage = value;
    },
    onSuccess: () => undefined,
    clearInputs: () => undefined,
  });
  assert.equal(htmlMessage, "服务暂时不可用，请稍后重试。");
  assert.ok(!htmlMessage.includes("<"));
});

test("a 2xx response with a malformed body is a protocol failure, not success", async () => {
  const { request } = responder([raw("<html>not json</html>", 200)]);
  const busy = busyRecorder();
  let message = "";
  let success = 0;

  const ok = await createSubjectAction({
    request,
    name: "科目",
    term: "",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
    clearInputs: () => undefined,
  });

  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, SAFE_BAD_RESPONSE);
  assert.equal(success, 0);
});

test("a successful create clears the inputs and reports success", async () => {
  const { request, calls } = responder([json({ subject: { id: "s1" } }, 201)]);
  const busy = busyRecorder();
  let success = 0;
  let cleared = 0;

  const ok = await createSubjectAction({
    request,
    name: "数值分析",
    term: "2026秋",
    setBusy: busy.setBusy,
    onError: () => assert.fail("unexpected error"),
    onSuccess: () => {
      success += 1;
    },
    clearInputs: () => {
      cleared += 1;
    },
  });

  assert.equal(ok, true);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(success, 1);
  assert.equal(cleared, 1);
  assert.equal(calls[0]?.url, "/api/v1/subjects");
  assert.equal(calls[0]?.init?.method, "POST");
  const form = uploadedForm(calls[0]?.init);
  assert.equal(form.get("name"), "数值分析");
  assert.equal(form.get("term"), "2026秋");
});

test("transcribe upload says where the text went and never claims an index build", async () => {
  const { request, calls } = responder([
    json({
      operation: "transcribe",
      transcripts: [{ text: "第一段" }, { text: "第二段" }],
    }),
  ]);
  const busy = busyRecorder();
  let message = "";
  let reloaded = 0;

  const ok = await uploadSubjectMaterialAction({
    request,
    subjectId: "subject-1",
    files: [new File(["audio"], "lecture.mp3", { type: "audio/mpeg" })],
    type: "lecture",
    setBusy: busy.setBusy,
    onError: () => assert.fail("unexpected error"),
    onSuccess: (value) => {
      message = value;
    },
    reloadKnowledge: async () => {
      reloaded += 1;
      return [];
    },
  });

  assert.equal(ok, true);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(reloaded, 0);
  assert.match(message, /转写完成（2 个文件）/);
  assert.match(message, /文本已保存/);
  assert.match(message, /不会自动建立索引/);
  assert.ok(!message.includes("正在建立索引"));
  assert.ok(!message.includes("建库"));
  const form = uploadedForm(calls[0]?.init);
  assert.equal(form.get("type"), "lecture");
  assert.equal(form.get("files") instanceof File, true);
});

test("index upload reports authoritative documents, sync, queue and coverage", async () => {
  const { request } = responder([
    json({
      operation: "index",
      documents: 7,
      kb_name: "assignment-kb",
      files: ["a.pdf", "b.pdf"],
    }),
  ]);
  const busy = busyRecorder();
  let message = "";
  let reloaded = 0;

  const ok = await uploadSubjectMaterialAction({
    request,
    subjectId: "subject-1",
    files: [new File(["a"], "a.pdf", { type: "application/pdf" })],
    type: "auto",
    setBusy: busy.setBusy,
    onError: () => assert.fail("unexpected error"),
    onSuccess: (value) => {
      message = value;
    },
    reloadKnowledge: async () => {
      reloaded += 1;
      return [
        {
          kb_name: "assignment-kb",
          documents: 7,
          status: {
            status: "rebuilding",
            documents: 7,
            materials_in_sync: true,
            busy: true,
            queued: true,
            image_coverage: {
              images_seen: 4,
              images_indexed: 3,
              images_skipped: 1,
              skip_reasons: { parser_no_assets: 0 },
            },
            image_coverage_warning: "部分图片未建立索引",
          },
        },
      ];
    },
  });

  assert.equal(ok, true);
  assert.equal(reloaded, 1);
  assert.deepEqual(busy.values, [true, false]);
  assert.match(message, /当前权威资料 7 个（documents 计数）/);
  assert.match(message, /正在重建索引/);
  assert.match(message, /任务已排队/);
  assert.match(message, /材料同步：已同步/);
  assert.match(message, /图片覆盖：已索引 3\/4，跳过 1/);
  assert.match(message, /覆盖警告：部分图片未建立索引/);
  assert.ok(!message.includes("chunk"));
});

test("a malformed index response does not report an authoritative count", async () => {
  const { request } = responder([json({ operation: "index", kb_name: "k" })]);
  const busy = busyRecorder();
  let message = "";
  let success = 0;

  const ok = await uploadSubjectMaterialAction({
    request,
    subjectId: "subject-1",
    files: [new File(["a"], "a.pdf")],
    type: "auto",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
  });

  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, SAFE_BAD_RESPONSE);
  assert.equal(success, 0);
});

test("export opens the authenticated outputs URL only after a 2xx json response", async () => {
  const { request, calls } = responder([
    json({
      url: "/api/outputs/subjects/s1/subject-s1-uuid.zip",
      size: 100,
      export_id: "uuid",
      schema_version: 1,
    }),
  ]);
  const busy = busyRecorder();
  const opened: string[] = [];
  let success = "";

  const ok = await exportSubjectAction({
    request,
    subjectId: "s1",
    setBusy: busy.setBusy,
    onError: () => assert.fail("unexpected error"),
    onSuccess: (url) => {
      success = url;
    },
    openDownload: (url) => { opened.push(url); },
  });

  assert.equal(ok, true);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(calls[0]?.url, "/api/v1/subjects/s1/export");
  assert.equal(calls[0]?.init?.method, "GET");
  assert.deepEqual(opened, ["/api/outputs/subjects/s1/subject-s1-uuid.zip"]);
  assert.equal(success, "/api/outputs/subjects/s1/subject-s1-uuid.zip");
  assert.match(EXPORT_SCOPE_NOTE, /不含聊天历史/);
  assert.match(EXPORT_SCOPE_NOTE, /不提供导入恢复/);
});

test("a failed export ends busy and never opens a window", async () => {
  const { request } = responder([
    json(
      { error: { code: "storage_io", message: "导出失败，请稍后重试。", retryable: true } },
      500,
    ),
  ]);
  const busy = busyRecorder();
  const opened: string[] = [];
  let message = "";

  const ok = await exportSubjectAction({
    request,
    subjectId: "s1",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => assert.fail("unexpected success"),
    openDownload: (url) => { opened.push(url); },
  });

  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, "导出失败，请稍后重试。");
  assert.deepEqual(opened, []);
});

test("export rejects a non-outputs or malformed URL without opening it", async () => {
  for (const url of [
    "https://evil.example/export.zip",
    "//evil.example/export.zip",
    "/api/v1/subjects/s1/export",
    "/api/outputs/../settings.json",
  ]) {
    const { request } = responder([json({ url })]);
    const opened: string[] = [];
    let message = "";
    const ok = await exportSubjectAction({
      request,
      subjectId: "s1",
      onError: (value) => {
        message = value;
      },
      onSuccess: () => assert.fail("unexpected success"),
      openDownload: (value) => { opened.push(value); },
    });
    assert.equal(ok, false, url);
    assert.equal(message, SAFE_BAD_EXPORT_URL, url);
    assert.deepEqual(opened, [], url);
  }
});

test("delete failure keeps the row and the message, delete success refreshes", async () => {
  const failed = responder([boom()]);
  const busy = busyRecorder();
  let message = "";
  let success = 0;
  const ok = await deleteSubjectAction({
    request: failed.request,
    subjectId: "s1",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
  });
  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, SAFE_NETWORK_MESSAGE);
  assert.equal(success, 0);

  const done = responder([json({ status: "deleted", subject_id: "s1" })]);
  let deleted = 0;
  const okDelete = await deleteSubjectAction({
    request: done.request,
    subjectId: "s1",
    onError: () => assert.fail("unexpected error"),
    onSuccess: () => {
      deleted += 1;
    },
  });
  assert.equal(okDelete, true);
  assert.equal(deleted, 1);
  assert.equal(done.calls[0]?.init?.method, "DELETE");
});

test("attempt and archive failures do not refresh or claim success", async () => {
  const attempt = responder([boom()]);
  const busy = busyRecorder();
  let message = "";
  let success = 0;
  const okAttempt = await recordAttemptAction({
    request: attempt.request,
    subjectId: "s1",
    entryId: "e1",
    correct: true,
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
  });
  assert.equal(okAttempt, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, SAFE_NETWORK_MESSAGE);
  assert.equal(success, 0);
  assert.equal(attempt.calls[0]?.url, "/api/v1/subjects/s1/wrong-book/e1/attempt");
  assert.equal(uploadedForm(attempt.calls[0]?.init).get("correct"), "true");

  const archive = responder([raw("<html>boom</html>", 500)]);
  let archiveMessage = "";
  let archiveSuccess = 0;
  const okArchive = await archiveEntryAction({
    request: archive.request,
    subjectId: "s1",
    entryId: "e1",
    onError: (value) => {
      archiveMessage = value;
    },
    onSuccess: () => {
      archiveSuccess += 1;
    },
  });
  assert.equal(okArchive, false);
  assert.equal(archiveMessage, "服务暂时不可用，请稍后重试。");
  assert.equal(archiveSuccess, 0);
});

test("a failed profile save never shows the saved message", async () => {
  const { request } = responder([
    json({ error: { message: "画像保存失败，请重试。" } }, 503),
  ]);
  const busy = busyRecorder();
  let message = "";
  let success = 0;
  const ok = await saveProfileAction({
    request,
    subjectId: "s1",
    goals: "通过考试",
    explanationStyle: "balanced",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => {
      success += 1;
    },
  });
  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, "画像保存失败，请重试。");
  assert.equal(success, 0);
});

test("review-pack failure is visible, ends busy and opens no window", async () => {
  const { request } = responder([
    json({ error: { message: "生成失败，请稍后重试。" } }, 500),
  ]);
  const busy = busyRecorder();
  const opened: string[] = [];
  let message = "";
  const ok = await generateReviewPackAction({
    request,
    subjectId: "s1",
    format: "pdf",
    setBusy: busy.setBusy,
    onError: (value) => {
      message = value;
    },
    onSuccess: () => assert.fail("unexpected success"),
    openDownload: (url) => { opened.push(url); },
  });
  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(message, "生成失败，请稍后重试。");
  assert.deepEqual(opened, []);
});

test("review-pack success opens exactly its outputs URL", async () => {
  const { request, calls } = responder([
    json({ url: "/api/outputs/subjects/s1/review-guide-abc.pdf", status: "completed" }),
  ]);
  const opened: string[] = [];
  let message = "";
  const ok = await generateReviewPackAction({
    request,
    subjectId: "s1",
    format: "pdf",
    term: "2026秋",
    onError: () => assert.fail("unexpected error"),
    onSuccess: () => {
      message = "ok";
    },
    openDownload: (url) => { opened.push(url); },
  });
  assert.equal(ok, true);
  assert.equal(message, "ok");
  assert.deepEqual(opened, ["/api/outputs/subjects/s1/review-guide-abc.pdf"]);
  assert.equal(calls[0]?.url, "/api/v1/subjects/s1/review-pack");
  const form = uploadedForm(calls[0]?.init);
  assert.equal(form.get("format"), "pdf");
  assert.equal(form.get("term"), "2026秋");
});

test("audio upload delivers transcript text and never says it started an index", async () => {
  const { request } = responder([
    json({
      operation: "transcribe",
      transcripts: [{ text: "甲" }, { text: "乙" }],
    }),
  ]);
  let outcomeText = "";
  let message = "";
  let success = 0;
  const ok = await uploadAudioAction({
    request,
    subjectId: "s1",
    files: [new File(["audio"], "lecture.wav", { type: "audio/wav" })],
    onError: () => assert.fail("unexpected error"),
    onSuccess: (outcome) => {
      success += 1;
      outcomeText = outcome.text;
      message = outcome.message;
    },
  });
  assert.equal(ok, true);
  assert.equal(success, 1);
  assert.equal(outcomeText, "甲\n\n乙");
  assert.match(message, /文本已保存/);
  assert.match(message, /不会自动建立索引/);
  assert.ok(!message.includes("正在建立索引"));

  const failed = responder([json({ error: { message: "转写失败，请重试。" } }, 502)]);
  let failedMessage = "";
  let failedSuccess = 0;
  const okFailed = await uploadAudioAction({
    request: failed.request,
    subjectId: "s1",
    files: [new File(["audio"], "lecture.wav")],
    onError: (value) => {
      failedMessage = value;
    },
    onSuccess: () => {
      failedSuccess += 1;
    },
  });
  assert.equal(okFailed, false);
  assert.equal(failedMessage, "转写失败，请重试。");
  assert.equal(failedSuccess, 0);
});

test("detection failure never reports zero candidates", async () => {
  const { request } = responder([raw("<html>gateway</html>", 502)]);
  const busy = busyRecorder();
  let shown = "";
  let success = 0;
  const ok = await detectExamPointsAction({
    request,
    subjectId: "s1",
    transcript: "课堂内容",
    setBusy: busy.setBusy,
    onError: (value) => {
      shown = value;
    },
    onSuccess: () => {
      success += 1;
    },
  });
  assert.equal(ok, false);
  assert.deepEqual(busy.values, [true, false]);
  assert.equal(shown, "服务暂时不可用，请稍后重试。");
  assert.equal(success, 0);

  const malformed = responder([json({ detected: "0" })]);
  let malformedMessage = "";
  const okMalformed = await detectExamPointsAction({
    request: malformed.request,
    subjectId: "s1",
    transcript: "课堂内容",
    onError: (value) => {
      malformedMessage = value;
    },
    onSuccess: () => assert.fail("unexpected success"),
  });
  assert.equal(okMalformed, false);
  assert.equal(malformedMessage, SAFE_BAD_RESPONSE);
});

test("detection success uses the server count and refreshes once", async () => {
  const { request } = responder([json({ detected: 3, points: [] })]);
  let message = "";
  let refreshed = 0;
  const ok = await detectExamPointsAction({
    request,
    subjectId: "s1",
    transcript: "课堂内容",
    onError: () => assert.fail("unexpected error"),
    onSuccess: (value, detected) => {
      message = value;
      refreshed += 1;
      assert.equal(detected, 3);
    },
  });
  assert.equal(ok, true);
  assert.match(message, /检出 3 条候选考点/);
  assert.equal(refreshed, 1);
});

test("detail refresh applies successful panels and reports one safe failure", async () => {
  const { request } = responder([
    json({ knowledge: [{ kb_name: "kb-1" }] }),
    raw("<html>bad gateway</html>", 502),
    json({ points: [{ id: "p1" }] }),
    json({ profile: { goals: "通过", explanation_style: "theory" } }),
  ]);
  const busy = busyRecorder();
  let loaded: { knowledge: unknown[]; wrongs: unknown[]; points: unknown[]; profile: unknown } | null =
    null;
  let message = "";
  const ok = await loadSubjectDetail({
    request,
    subjectId: "s1",
    onLoaded: (view) => {
      loaded = view;
    },
    onError: (value) => {
      message = value;
    },
  });
  assert.equal(ok, false);
  assert.equal(message, "服务暂时不可用，请稍后重试。");
  assert.ok(loaded);
  assert.equal((loaded as { knowledge: unknown[] }).knowledge.length, 1);
  assert.equal((loaded as { wrongs: unknown[] }).wrongs.length, 0);
  assert.equal((loaded as { points: unknown[] }).points.length, 1);
  assert.equal(
    (loaded as { profile: { goals?: string } }).profile?.goals,
    "通过",
  );
  assert.deepEqual(busy.values, []);
});

test("list refresh failure reports safely and never renders a fake empty success", async () => {
  const { request } = responder([boom()]);
  let loaded = 0;
  let message = "";
  const view = await loadSubjectsView({
    request,
    onLoaded: () => {
      loaded += 1;
    },
    onError: (value) => {
      message = value;
    },
  });
  assert.equal(view, null);
  assert.equal(loaded, 0);
  assert.equal(message, SAFE_NETWORK_MESSAGE);
});

test("list refresh keeps per-subject knowledge and reports a partial failure", async () => {
  const { request } = responder([
    json({ subjects: [{ id: "s1" }, { id: "s2" }] }),
    json({ knowledge: [{ kb_name: "kb-1", documents: 2 }] }),
    boom(),
  ]);
  let view: {
    subjects: unknown[];
    knowledge: Record<string, unknown[]>;
  } | null = null;
  let message = "";
  const result = await loadSubjectsView({
    request,
    onLoaded: (loaded) => {
      view = loaded;
    },
    onError: (value) => {
      message = value;
    },
  });
  assert.ok(result);
  assert.ok(view);
  assert.equal((view as { subjects: unknown[] }).subjects.length, 2);
  assert.equal(
    (view as { knowledge: Record<string, unknown[]> }).knowledge.s1?.length,
    1,
  );
  assert.equal(
    (view as { knowledge: Record<string, unknown[]> }).knowledge.s2,
    undefined,
  );
  assert.match(message, /部分知识库状态加载失败/);
});

test("both existing pages delegate their actions to the tested helpers", () => {
  const listPage = readFileSync(
    path.resolve("app/(workspace)/subjects/page.tsx"),
    "utf8",
  );
  const detailPage = readFileSync(
    path.resolve("app/(workspace)/subjects/[id]/page.tsx"),
    "utf8",
  );
  for (const name of [
    "createSubjectAction",
    "uploadSubjectMaterialAction",
    "deleteSubjectAction",
    "loadSubjectsView",
  ]) {
    assert.match(listPage, new RegExp(`${name}\\(`), name);
  }
  for (const name of [
    "recordAttemptAction",
    "archiveEntryAction",
    "saveProfileAction",
    "generateReviewPackAction",
    "detectExamPointsAction",
    "exportSubjectAction",
    "loadSubjectDetail",
  ]) {
    assert.match(detailPage, new RegExp(`${name}\\(`), name);
  }
  assert.match(detailPage, /EXPORT_SCOPE_NOTE/);
  assert.match(detailPage, /<AsrJobPanel/);
  assert.match(detailPage, /mastery: number;/);
  assert.match(detailPage, /<ExamPointDetect key=\{subjectId\}/);
});

// Coordinator acceptance: execute the actual page handlers with a minimal
// hook scheduler. Only React/Next/browser boundaries are replaced; production
// page source and action helpers execute unchanged. This is not a browser gate.
function pageHarness(file: string, request: SubjectRequest, initialSubject = "a") {
  const slots: any[] = [];
  let cursor = 0;
  let dirty = false;
  let subject = initialSubject;
  let tree: any;
  let effects: (() => void)[] = [];
  const timers: (() => void)[] = [];
  const downloads: string[] = [];
  const equal = (a?: unknown[], b?: unknown[]) =>
    !!a && !!b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const hooks = {
    useState(initial: any) {
      const slot = cursor++;
      slots[slot] ??= { value: typeof initial === "function" ? initial() : initial };
      return [slots[slot].value, (value: any) => {
        const next = typeof value === "function" ? value(slots[slot].value) : value;
        if (!Object.is(next, slots[slot].value)) dirty = true;
        slots[slot].value = next;
      }];
    },
    useRef(initial: any) {
      const slot = cursor++;
      slots[slot] ??= { current: initial };
      return slots[slot];
    },
    useCallback(fn: any, deps: unknown[]) {
      const slot = cursor++;
      if (!equal(slots[slot]?.deps, deps)) slots[slot] = { fn, deps };
      return slots[slot].fn;
    },
    useEffect(fn: () => void | (() => void), deps?: unknown[]) {
      const slot = cursor++;
      if (!equal(slots[slot]?.deps, deps)) {
        const previous = slots[slot];
        slots[slot] = { deps };
        effects.push(() => {
          previous?.cleanup?.();
          slots[slot].cleanup = fn();
        });
      }
    },
  };
  const compiled = ts.transpileModule(readFileSync(path.resolve(file), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  });
  const mod = { exports: {} as { default?: () => unknown } };
  const boundaryRequire = (name: string) => {
    if (name === "react") return hooks;
    if (name === "next/navigation") return { useParams: () => ({ id: subject }) };
    if (name === "next/link") return { __esModule: true, default: "a" };
    if (name === "react-i18next") return { useTranslation: () => ({ t: (v: string) => v }) };
    if (name === "@/lib/api") return { apiFetch: request };
    if (name === "@/components/subjects/AsrJobPanel") {
      return { __esModule: true, default: () => null };
    }
    if (name === "@/lib/subject-results") return require("../lib/subject-results");
    return require(name);
  };
  new Function("require", "module", "exports", "window", "document", "URL", "setInterval", "clearInterval", compiled.outputText)(
    boundaryRequire, mod, mod.exports,
    { open: (url: string) => downloads.push(url), setTimeout: (fn: () => void) => fn() },
    {body:{appendChild:()=>{}},createElement:()=>({href:"",download:"",click(){downloads.push(this.download);},remove(){}})},
    {createObjectURL:()=>"blob:test-owned-download",revokeObjectURL:()=>{}},
    (fn: () => void) => { timers.push(fn); return timers.length; }, () => {},
  );
  function render() {
    for (let i = 0; i < 20; i += 1) {
      dirty = false; cursor = 0; effects = [];
      tree = mod.exports.default!();
      effects.forEach((fn) => fn());
      if (!dirty) return tree;
    }
    throw new Error("page effects did not settle");
  }
  function all(node: any): any[] {
    if (Array.isArray(node)) return node.flatMap((item) => all(item));
    if (!node || typeof node !== "object" || !node.props) return [];
    return [node, ...all(node.props.children)];
  }
  function text(node: any): string {
    if (Array.isArray(node)) return node.map((item) => text(item)).join("");
    if (node == null || typeof node === "boolean") return "";
    if (typeof node !== "object") return String(node);
    return text(node.props?.children);
  }
  return {
    render, text: () => text(tree), downloads,
    find: (predicate: (node: any) => boolean) => {
      const node = all(tree).find(predicate); assert.ok(node, "page node missing"); return node;
    },
    click(label: string) {
      const node = all(tree).find((n) => n.type === "button" && text(n) === label);
      assert.ok(node, `missing button ${label}`); return node.props.onClick();
    },
    switchSubject(id: string) { subject = id; render(); },
    poll() { timers.at(-1)?.(); },
    unmount() { slots.forEach((slot) => slot?.cleanup?.()); },
    async settle() { await new Promise(setImmediate); await new Promise(setImmediate); render(); },
  };
}

const LIST_PAGE = "app/(workspace)/subjects/page.tsx";
const DETAIL_PAGE = "app/(workspace)/subjects/[id]/page.tsx";
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function detailReplies(url: string, goals = "") {
  if (url.startsWith("/api/outputs/")) return new Response(Buffer.concat([Buffer.from("PK\x03\x04"),Buffer.alloc(30)]));
  if (url.endsWith("/knowledge")) return response({ knowledge: [] });
  if (url.endsWith("/wrong-book")) return response({ entries: [] });
  if (url.endsWith("/exam-points")) return response({ points: [] });
  if (url.endsWith("/profile")) return response({ profile: { goals, explanation_style: "theory" } });
  throw new Error(`unexpected URL ${url}`);
}

for (const action of ["create", "delete", "profile"] as const) {
  test(`acceptance: ${action} rejects a 2xx object without its success envelope`, async () => {
    const busy = busyRecorder(); let success = 0; let message = "";
    const hooks = { request: async () => response({}), subjectId: "a", setBusy: busy.setBusy,
      onError: (value: string) => { message = value; }, onSuccess: () => { success += 1; } };
    const ok = action === "create"
      ? await createSubjectAction({ ...hooks, name: "A", term: "", clearInputs: () => { success += 1; } })
      : action === "delete" ? await deleteSubjectAction(hooks)
      : await saveProfileAction({ ...hooks, goals: "A", explanationStyle: "balanced" });
    assert.equal(ok, false); assert.equal(success, 0); assert.equal(message, SAFE_BAD_RESPONSE);
    assert.deepEqual(busy.values, [true, false]);
  });
}

test("acceptance: malformed list objects do not erase a successful list", async () => {
  let loaded = 0; let message = "";
  const result = await loadSubjectsView({ request: async () => response({}),
    onLoaded: () => { loaded += 1; }, onError: (v) => { message = v; } });
  assert.equal(result, null); assert.equal(loaded, 0); assert.equal(message, SAFE_BAD_RESPONSE);
});

for (const documents of [-1, 1.5]) {
  test(`acceptance: index count ${documents} is not an authoritative document count`, async () => {
    let success = 0;
    const ok = await uploadSubjectMaterialAction({ request: async () => response({ operation: "index", documents }),
      subjectId: "a", type: "auto", files: [new File(["a"], "a.txt")],
      onError: () => {}, onSuccess: () => { success += 1; } });
    assert.equal(ok, false); assert.equal(success, 0);
  });
}

for (const audio of [false, true]) {
  test(`acceptance: ${audio ? "audio" : "material"} upload rejects a missing transcript array`, async () => {
    let success = 0;
    const hooks = { request: async () => response({ operation: "transcribe" }), subjectId: "a",
      files: [new File(["a"], "a.mp3")], onError: () => {}, onSuccess: () => { success += 1; } };
    const ok = audio ? await uploadAudioAction(hooks) : await uploadSubjectMaterialAction({ ...hooks, type: "auto" });
    assert.equal(ok, false); assert.equal(success, 0);
  });
}

test("acceptance: real list rendering keeps knowledge type and progress", async () => {
  const h = pageHarness(LIST_PAGE, async (url) => String(url).endsWith("/subjects")
    ? response({ subjects: [{ id: "a", name: "A" }] })
    : response({ knowledge: [{ kb_name: "same", type: "textbook", documents: 1,
      status: { status: "rebuilding", progress: { percent: 37, message: "working" } } }] }));
  h.render(); await h.settle();
  assert.match(h.text(), /textbook/); assert.match(h.text(), /37%/); h.unmount();
});

test("acceptance: real upload handler reads status only from its own subject", async () => {
  const h = pageHarness(LIST_PAGE, async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return response({ operation: "index", kb_name: "same", documents: 2 });
    if (url.endsWith("/subjects")) return response({ subjects: [{ id: "b", name: "B" }, { id: "a", name: "A" }] });
    return response({ knowledge: [{ kb_name: "same", type: "textbook", documents: 2,
      status: { status: "ready", image_coverage_warning: url.includes("/b/") ? "OTHER-SUBJECT" : "OWN-SUBJECT" } }] });
  });
  h.render(); await h.settle();
  await h.find((n) => n.type === "input" && n.props.id === "file-a").props.onChange({ target: { files: [new File(["a"], "a.txt")] } });
  h.render(); assert.match(h.text(), /OWN-SUBJECT/); assert.doesNotMatch(h.text(), /OTHER-SUBJECT/); h.unmount();
});

test("acceptance: the real upload file input is disabled while its request runs", async () => {
  let finish!: (value: Response) => void;
  const h = pageHarness(LIST_PAGE, async (input, init) => {
    if (init?.method === "POST") return new Promise<Response>((resolve) => { finish = resolve; });
    return String(input).endsWith("/subjects") ? response({ subjects: [{ id: "a", name: "A" }] }) : response({ knowledge: [] });
  });
  h.render(); await h.settle();
  const running = h.find((n) => n.type === "input" && n.props.id === "file-a").props.onChange({ target: { files: [new File(["a"], "a.txt")] } });
  h.render();
  const disabled = h.find((n) => n.type === "input" && n.props.id === "file-a").props.disabled;
  finish(response({ operation: "index", documents: 1 })); await running; h.unmount();
  assert.equal(disabled, true);
});

test("acceptance: switching subjects resets profile when the new profile read fails", async () => {
  const h = pageHarness(DETAIL_PAGE, async (input) => {
    const url = String(input);
    if (url.includes("/b/") && url.endsWith("/profile")) return response({}, 503);
    return detailReplies(url, url.includes("/a/") ? "PRIVATE-A-GOAL" : "");
  });
  h.render(); await h.settle(); h.click("画像"); h.render();
  assert.equal(h.find((n) => n.type === "textarea").props.value, "PRIVATE-A-GOAL");
  h.switchSubject("b"); await h.settle();
  assert.equal(h.find((n) => n.type === "textarea").props.value, ""); h.unmount();
});

for (const mode of ["export", "review-pack"] as const) {
  test(`acceptance: stale ${mode} completion cannot open a download for another subject`, async () => {
    let finish!: (value: Response) => void;
    const h = pageHarness(DETAIL_PAGE, async (input) => {
      const url = String(input);
      if (url.endsWith(`/${mode}`)) return new Promise<Response>((resolve) => { finish = resolve; });
      return detailReplies(url);
    });
    h.render(); await h.settle();
    if (mode === "review-pack") { h.click("复习包"); h.render(); h.click("生成 PDF"); }
    else h.click("导出科目资料");
    h.switchSubject("b"); await h.settle();
    finish(response({ url: "/api/outputs/subjects/a/result.zip" })); await h.settle();
    assert.deepEqual(h.downloads, []); assert.doesNotMatch(h.text(), /已开始下载|已生成，开始下载/); h.unmount();
  });
}

test("acceptance: an older list refresh cannot overwrite a newer view", async () => {
  let finish!: (value: Response) => void; let lists = 0;
  const h = pageHarness(LIST_PAGE, async (input) => {
    if (!String(input).endsWith("/subjects")) return response({ knowledge: [] });
    if (++lists === 1) return new Promise<Response>((resolve) => { finish = resolve; });
    return response({ subjects: [{ id: "new", name: "NEW-VIEW" }] });
  });
  h.render(); h.poll(); await h.settle(); assert.match(h.text(), /NEW-VIEW/);
  finish(response({ subjects: [{ id: "old", name: "OLD-VIEW" }] })); await h.settle();
  assert.match(h.text(), /NEW-VIEW/); assert.doesNotMatch(h.text(), /OLD-VIEW/); h.unmount();
});

test("acceptance: a failed detail panel refresh preserves its last successful data", async () => {
  let reads = 0;
  const h = pageHarness(DETAIL_PAGE, async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return response({ entry: { id: "entry-1" } });
    if (url.endsWith("/wrong-book")) {
      if (++reads > 1) return response({}, 503);
      return response({ entries: [{ id: "entry-1", question: "KEEP-QUESTION", answer: "A", kp: "K",
        status: "untracked", mastery: 0, attempts: [], archived: false }] });
    }
    return detailReplies(url);
  });
  h.render(); await h.settle(); h.click("错题集"); h.render();
  assert.match(h.text(), /KEEP-QUESTION/); h.click("记录答对"); await h.settle();
  assert.match(h.text(), /KEEP-QUESTION/); assert.doesNotMatch(h.text(), /暂无错题/); h.unmount();
});

test("acceptance: an old action cannot clear the next subject's busy or error state", async () => {
  const finish: Record<string, (value: Response) => void> = {};
  const h = pageHarness(DETAIL_PAGE, async (input) => {
    const url = String(input);
    if (url.endsWith("/export")) return new Promise<Response>((resolve) => { finish[url.split("/").at(-2)!] = resolve; });
    return detailReplies(url);
  });
  h.render(); await h.settle(); h.click("导出科目资料");
  h.switchSubject("b"); await h.settle(); h.click("导出科目资料"); h.render();
  finish.a(response({ detail: "OLD-A-ERROR" }, 409)); await h.settle();
  assert.doesNotMatch(h.text(), /OLD-A-ERROR/);
  assert.equal(h.find((n) => n.type === "button" && n.props.className?.includes("border px-3")).props.disabled, true);
  finish.b(response({ url: "/api/outputs/subjects/b/result.zip" })); await h.settle();
  assert.deepEqual(h.downloads, ["result.zip"]); h.unmount();
});

test("acceptance: unmount invalidates a pending download callback", async () => {
  let finish!: (value: Response) => void;
  const h = pageHarness(DETAIL_PAGE, async (input) => String(input).endsWith("/export")
    ? new Promise<Response>((resolve) => { finish = resolve; }) : detailReplies(String(input)));
  h.render(); await h.settle(); h.click("导出科目资料"); h.unmount();
  finish(response({ url: "/api/outputs/subjects/a/result.zip" })); await h.settle();
  assert.deepEqual(h.downloads, []);
});

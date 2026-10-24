import assert from "node:assert/strict";
import test from "node:test";

import {
  exportSubjectAction, generateReviewPackAction, SAFE_NETWORK_MESSAGE,
  fetchSubjectArtifact, SAFE_BAD_DOWNLOAD,
} from "../lib/subject-results";

for (const mode of ["export", "review"] as const) {
  test(`${mode} waits for download failure and never announces success`, async () => {
    const busy: boolean[] = [], errors: string[] = [], success: string[] = [];
    const rejection = Promise.reject(new TypeError("PRIVATE-download-failure"));
    void rejection.catch(() => {});
    const options = {
      request: async () => Response.json({url: "/api/outputs/subjects/test/result.zip"}),
      subjectId: "test", format: "pdf" as const,
      setBusy: (value: boolean) => busy.push(value),
      onError: (message: string) => errors.push(message),
      onSuccess: (url: string) => success.push(url),
      openDownload: () => rejection,
    };
    const result = await (mode === "export" ? exportSubjectAction(options) : generateReviewPackAction(options));
    assert.equal(result, false);
    assert.deepEqual(success, []);
    assert.deepEqual(errors, [SAFE_NETWORK_MESSAGE]);
    assert.deepEqual(busy, [true, false]);
  });

  test(`${mode} stays busy until its asynchronous download finishes`, async () => {
    const busy: boolean[] = [], success: string[] = [];
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const options = {
      request: async () => Response.json({url: "/api/outputs/subjects/test/result.zip"}),
      subjectId: "test", format: "pdf" as const,
      setBusy: (value: boolean) => busy.push(value), onError: () => {},
      onSuccess: (url: string) => success.push(url), openDownload: () => pending,
    };
    const running = mode === "export" ? exportSubjectAction(options) : generateReviewPackAction(options);
    try {
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(success, []);
      assert.deepEqual(busy, [true]);
    } finally { release(); }
    assert.equal(await running, true);
    assert.equal(success.length, 1);
    assert.deepEqual(busy, [true, false]);
  });
}

for (const format of ["zip", "pdf", "docx"] as const) {
  test(`${format} download rejects HTTP failures and HTML/JSON error bodies`, async () => {
    for (const response of [
      new Response("private diagnostic", {status: 503}),
      new Response("<html>wrong payload</html>", {headers:{"content-type":"text/html"}}),
      Response.json({error:"private diagnostic"}),
      new Response(new Uint8Array()),
    ]) {
      await assert.rejects(fetchSubjectArtifact(async () => response, "/api/outputs/test/file", format),
        (error: Error) => !error.message.includes("private diagnostic"));
    }
  });
  test(`${format} accepts binary bytes and refuses misleading error content types`, async () => {
    const bytes = format === "pdf" ? Buffer.from("%PDF-1.7\nfixture") : Buffer.concat([Buffer.from("PK\x03\x04"), Buffer.alloc(30)]);
    const blob = await fetchSubjectArtifact(async () => new Response(bytes), "/api/outputs/test/file", format);
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), new Uint8Array(bytes));
    await assert.rejects(fetchSubjectArtifact(async () => new Response(bytes, {headers:{"content-type":"application/json"}}), "/api/outputs/test/file", format),
      {message: SAFE_BAD_DOWNLOAD});
  });
}

test("artifact download rejects foreign URLs before fetching", async () => {
  let called = false;
  await assert.rejects(fetchSubjectArtifact(async () => {called=true; return new Response();}, "https://outside.invalid/file.zip", "zip"));
  assert.equal(called, false);
});

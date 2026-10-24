/**
 * MM-R3 isolated browser wrapper.  It reuses the audited S15 disposable-source
 * runner, loopback model server, installed Chromium and cleanup guard; only
 * the evidence directory, fixture label and spec change.
 */
import path from "node:path";

const repo = path.resolve(__dirname, "..");
process.env.S15_EVIDENCE_DIR ||= path.join(
  repo,
  ".phase1-evidence",
  "model-management",
  "MM-R3-browser",
);
process.env.S15_RUN_LABEL ||= "mm-r3";
process.env.S15_TEST_MATCH = "model-management-r3.spec.ts";
process.env.S15_CHROMIUM ||=
  "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const base = require("./playwright.phase1.config");
export default base.default || base;

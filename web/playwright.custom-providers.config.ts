/**
 * CP-R1 isolated browser wrapper. Reuses the audited S15 disposable-source
 * runner, loopback fixture server, installed Chromium and cleanup guard.
 */
import path from "node:path";

const repo = path.resolve(__dirname, "..");
process.env.S15_EVIDENCE_DIR ||= path.join(
  repo,
  ".phase1-evidence",
  "custom-providers",
  "CP-R1-browser",
);
process.env.S15_RUN_LABEL ||= "cp-r1";
process.env.S15_TEST_MATCH = "custom-providers.spec.ts";
process.env.S15_CHROMIUM ||=
  "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const base = require("./playwright.phase1.config");
export default base.default || base;

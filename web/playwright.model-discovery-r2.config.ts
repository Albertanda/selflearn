/**
 * MD-R2 isolated browser wrapper. All assignments must happen before the base
 * config is evaluated so its disposable source copy, loopback guard and
 * evidence ownership remain in force.
 */
import path from "node:path";

const repo = path.resolve(__dirname, "..");
process.env.S15_EVIDENCE_DIR ||= path.join(
  repo,
  ".phase1-evidence",
  "model-discovery",
  "MD-R2-browser",
);
process.env.S15_RUN_LABEL ||= "md-r2";
process.env.S15_TEST_MATCH = "model-discovery-r2.spec.ts";
process.env.S15_CHROMIUM ||=
  "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const base = require("./playwright.phase1.config");
export default base.default || base;

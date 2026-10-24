/**
 * MD-R1 isolated browser wrapper.
 *
 * All assignments happen before the base config is evaluated so its
 * sealed-evidence check, disposable source copy, loopback-only guard, and
 * teardown ownership remain in force.
 */
import path from "node:path";

const repo = path.resolve(__dirname, "..");
process.env.S15_EVIDENCE_DIR ||= path.join(
  repo,
  ".phase1-evidence",
  "model-discovery",
  "MD-R1-browser",
);
process.env.S15_RUN_LABEL ||= "md";
process.env.S15_TEST_MATCH = "model-discovery.spec.ts";
process.env.S15_CHROMIUM ||=
  "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

// Playwright evaluates this wrapper with its TS loader; the base config must
// see the assignments above, so require it after them rather than re-exporting.
const base = require("./playwright.phase1.config");
export default base.default || base;

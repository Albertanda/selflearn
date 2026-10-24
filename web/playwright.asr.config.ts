/**
 * ASR-R1 browser acceptance config.
 *
 * It reuses the sealed, hardened S15 runner (real Next/FastAPI/Chromium,
 * disposable source copy, loopback-only guards, owned cleanup) and only
 * changes the suite, the evidence root and the deterministic STT delay.  The
 * environment assignments happen before the base config is evaluated, so the
 * base config's sealed-evidence and bootstrap ownership checks still apply.
 */
import path from "node:path";

const repo = path.resolve(__dirname, "..");
process.env.S15_EVIDENCE_DIR ||= path.join(repo, ".phase1-evidence", "repairs", "ASR-R1", "browser-asr");
process.env.S15_RUN_LABEL ||= "asr";
process.env.S15_TEST_MATCH = "asr-long-audio.spec.ts";
process.env.S15_ASR_DELAY_MS ||= "65000";
process.env.S15_CHROMIUM ||= "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

// Playwright loads this file with its TypeScript config loader; `require` is
// evaluated after the assignments above (a static re-export would not be).
const base = require("./playwright.phase1.config");
export default base.default || base;

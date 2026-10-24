/**
 * S15/P1-53 isolated browser acceptance configuration.
 *
 * Owns only the throwaway runner for `web/e2e/phase1.spec.ts`: it builds a
 * temporary source copy, generates fictitious settings, and starts three
 * supervised loopback services — a deterministic model/STT/embedding server,
 * the real FastAPI app, and the real Next dev server. Playwright stops the
 * supervisors, which forward termination to their whole process groups.
 *
 * It does not alter `web/playwright.config.ts`, production settings, the real
 * `data/` trees, or `web/.next*`.
 */
import { defineConfig, devices } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const REPO = fs.realpathSync(path.resolve(__dirname, ".."));
function inside(root: string, value: string): boolean {
  const relative = path.relative(root, value);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}
function canonical(value: string): string {
  let parent = path.resolve(value);
  const suffix: string[] = [];
  while (!fs.existsSync(parent)) {
    suffix.unshift(path.basename(parent));
    const next = path.dirname(parent);
    if (next === parent) throw new Error("Cannot resolve S15 path");
    parent = next;
  }
  return path.join(fs.realpathSync(parent), ...suffix);
}
const STAGE = canonical(process.env.S15_EVIDENCE_DIR || path.join(REPO, ".phase1-evidence", "stages", "S15"));
if (!inside(path.join(REPO, ".phase1-evidence"), STAGE)) throw new Error("S15 evidence must stay under .phase1-evidence");
if (fs.existsSync(path.join(STAGE, "report.json")) || fs.existsSync(path.join(STAGE, "closing_manifest.json"))) {
  throw new Error("Sealed S15 evidence: set S15_EVIDENCE_DIR to a fresh directory");
}
const RUN_LABEL = process.env.S15_RUN_LABEL || "good";
if (!/^[a-zA-Z0-9_-]{1,48}$/.test(RUN_LABEL)) throw new Error("Invalid S15_RUN_LABEL");
const TEST_MATCH = process.env.S15_TEST_MATCH || "phase1.spec.ts";
if (!/^[a-zA-Z0-9_.-]{1,80}$/.test(TEST_MATCH)) throw new Error("Invalid S15_TEST_MATCH");
const ASR_DELAY_MS = Number(process.env.S15_ASR_DELAY_MS || "0");
if (!Number.isInteger(ASR_DELAY_MS) || ASR_DELAY_MS < 0 || ASR_DELAY_MS > 180_000) {
  throw new Error("Invalid S15_ASR_DELAY_MS");
}
const PROVIDED_SOURCE = process.env.S15_SOURCE_COPY
  ? canonical(process.env.S15_SOURCE_COPY)
  : null;
const TEMP_BASE = canonical(process.env.S15_TEMP_BASE || os.tmpdir());
if (inside(REPO, TEMP_BASE) || inside(TEMP_BASE, REPO)) throw new Error("S15 temporary base must be outside the repository");
process.env.S15_TEMP_BASE = TEMP_BASE;
function validateSource(source: string): void {
  if (!inside(TEMP_BASE, source) || inside(REPO, source) || inside(source, REPO)) {
    throw new Error("S15_SOURCE_COPY must be a disposable source outside the repository");
  }
}
if (PROVIDED_SOURCE) validateSource(PROVIDED_SOURCE);
const ARTIFACTS = process.env.S15_ARTIFACTS_DIR
  ? canonical(process.env.S15_ARTIFACTS_DIR)
  : path.join(STAGE, "playwright-artifacts");
if (!inside(STAGE, ARTIFACTS)) throw new Error("S15 artifacts must stay under the fresh evidence directory");

// Playwright evaluates this config once in the runner and again in each
// worker. The first evaluation chooses the isolated root and ports and writes
// a bootstrap file; the worker inherits S15_BOOTSTRAP_FILE and must reuse the
// exact same instance instead of opening a second temp server set.
interface Bootstrap {
  run_label: string;
  run_id: string;
  run_root: string;
  source_root: string;
  model_port: number;
  backend_port: number;
  web_port: number;
  token: string;
  evidence_dir: string;
}
let bootstrapPath = process.env.S15_BOOTSTRAP_FILE;
const controller = !bootstrapPath;
let bootstrap: Bootstrap | null = null;
if (bootstrapPath) {
  bootstrap = JSON.parse(fs.readFileSync(bootstrapPath, "utf-8")) as Bootstrap;
  validateSource(canonical(bootstrap.run_root));
  validateSource(canonical(bootstrap.source_root));
  if (canonical(bootstrapPath) !== path.join(canonical(bootstrap.run_root), "bootstrap.json")
      || !path.basename(bootstrap.run_root).startsWith("selflearn-s15-")
      || !bootstrap.token || bootstrap.token !== process.env.S15_BOOTSTRAP_TOKEN
      || canonical(bootstrap.source_root) !== path.join(canonical(bootstrap.run_root), "src")
      || bootstrap.evidence_dir !== STAGE || bootstrap.run_label !== RUN_LABEL) {
    throw new Error("Invalid S15 bootstrap ownership");
  }
}
if (!bootstrap) {
  if (fs.existsSync(path.join(STAGE, "run_state.json"))) throw new Error("S15 evidence directory was already used; select a fresh directory");
  if (PROVIDED_SOURCE && (fs.existsSync(path.join(PROVIDED_SOURCE, "data")) || !fs.existsSync(path.join(PROVIDED_SOURCE, "web", "next.config.js")))) {
    throw new Error("S15_SOURCE_COPY must contain source and no existing data");
  }
  const runId = `${Date.now()}-${process.pid}`;
  const runRoot = fs.mkdtempSync(path.join(TEMP_BASE, `selflearn-s15-${RUN_LABEL}-`));
  const ports = freePorts(3);
  bootstrap = {
    run_label: RUN_LABEL,
    run_id: runId,
    run_root: runRoot,
    source_root: path.join(runRoot, "src"),
    model_port: ports[0],
    backend_port: ports[1],
    web_port: ports[2],
    token: randomUUID(),
    evidence_dir: STAGE,
  };
  bootstrapPath = path.join(runRoot, "bootstrap.json");
  fs.writeFileSync(bootstrapPath, JSON.stringify(bootstrap, null, 2) + "\n", "utf-8");
  process.env.S15_BOOTSTRAP_FILE = bootstrapPath;
  process.env.S15_BOOTSTRAP_TOKEN = bootstrap.token;
}
const RUN_ROOT = bootstrap.run_root;
const SOURCE_ROOT = bootstrap.source_root;
const MODEL_PORT = bootstrap.model_port;
const BACKEND_PORT = bootstrap.backend_port;
const WEB_PORT = bootstrap.web_port;
if (new Set([MODEL_PORT, BACKEND_PORT, WEB_PORT]).size !== 3
    || ![MODEL_PORT, BACKEND_PORT, WEB_PORT].every((port) => Number.isInteger(port) && port > 1023 && port < 65536)) {
  throw new Error("Invalid S15 bootstrap ports");
}
const LOG_DIR = path.join(STAGE, "run-logs");
const MODEL_LOG = path.join(LOG_DIR, `${RUN_LABEL}-model.jsonl`);
const BACKEND_LOG = path.join(LOG_DIR, `${RUN_LABEL}-backend.log`);
const NEXT_LOG = path.join(LOG_DIR, `${RUN_LABEL}-next.log`);
const STATE_FILE = path.join(STAGE, "run_state.json");

function freePorts(count: number): number[] {
  const script = `
import json, socket
socks = []
try:
    for _ in range(${count}):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        socks.append(s)
    print(json.dumps([s.getsockname()[1] for s in socks]))
finally:
    for s in socks:
        s.close()
`;
  return JSON.parse(execFileSync(path.join(REPO, ".venv", "bin", "python"), ["-c", script], { encoding: "utf-8" }));
}

// Reuse the pre-existing Chromium system-library bundle on this host. This
// is not an install or upgrade: it only puts already-present runtime libraries
// on the loader path for the existing browser binary.
const NATIVE_LIBS = "/home/albert/.cache/novel-writer-ui-test/native/root/usr/lib/x86_64-linux-gnu";
for (const key of Object.keys(process.env)) {
  if ((/API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH_FILE/i.test(key) && !key.startsWith("S15_BOOTSTRAP_"))
      || /^(OPENAI_|ANTHROPIC_|CODEBUDDY_|DEEPTUTOR_|HTTP_PROXY$|HTTPS_PROXY$|ALL_PROXY$|NODE_OPTIONS$|PYTHONPATH$|PYTEST_|CODEX_HOME$|CLAUDE_CONFIG_DIR$)/i.test(key)) delete process.env[key];
}
process.env.LD_LIBRARY_PATH = fs.existsSync(NATIVE_LIBS) ? NATIVE_LIBS : "";
process.env.HOME = path.join(RUN_ROOT, "home");
process.env.TMPDIR = path.join(RUN_ROOT, "tmp");
process.env.XDG_CONFIG_HOME = path.join(RUN_ROOT, "home", ".config");
process.env.XDG_CACHE_HOME = path.join(RUN_ROOT, "home", ".cache");
process.env.XDG_DATA_HOME = path.join(RUN_ROOT, "home", ".local", "share");
process.env.CODEX_HOME = path.join(RUN_ROOT, "home", "codex");
process.env.CLAUDE_CONFIG_DIR = path.join(RUN_ROOT, "home", "claude");

// Reuse an already-present CJK font so screenshots render the product's
// hard-coded Chinese labels instead of missing-glyph boxes. Nothing is
// installed: the font file is copied into the disposable run root.
const FONT_DIR = path.join(RUN_ROOT, "fonts");
if (controller) fs.mkdirSync(FONT_DIR, { recursive: true });
for (const candidate of ["/mnt/c/Windows/Fonts/msyh.ttc", "/mnt/c/Windows/Fonts/simhei.ttf"]) {
  if (!controller || !fs.existsSync(candidate)) continue;
  const target = path.join(FONT_DIR, path.basename(candidate));
  try {
    if (!fs.existsSync(target)) execFileSync("cp", [candidate, target]);
    fs.chmodSync(target, 0o444);
  } catch {
    // A missing/unreadable optional font only affects screenshot glyphs.
  }
}
const FONT_CONFIG = path.join(RUN_ROOT, "fonts.conf");
if (controller) fs.writeFileSync(FONT_CONFIG, `<fontconfig>\n  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n  <dir>${FONT_DIR}</dir>\n  <cachedir>${path.join(RUN_ROOT, "font-cache")}</cachedir>\n</fontconfig>\n`, "utf-8");
process.env.FONTCONFIG_FILE = FONT_CONFIG;

const WEB_ORIGIN = `http://127.0.0.1:${WEB_PORT}`;
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`;
process.env.S15_MODEL_ORIGIN = `http://127.0.0.1:${MODEL_PORT}`;

process.env.S15_RUN_STATE_FILE = STATE_FILE;
process.env.S15_RUN_ROOT = RUN_ROOT;
process.env.S15_SOURCE_ROOT = SOURCE_ROOT;
process.env.S15_RUN_LABEL = RUN_LABEL;
process.env.S15_EVIDENCE_DIR = STAGE;

function writeJson(file: string, value: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n", "utf-8");
}

function hashFile(file: string): string {
  return createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function copySource(): void {
  const allowed = ["deeptutor", "web", "pyproject.toml", "requirements.txt", "requirements", "scripts"];
  fs.mkdirSync(SOURCE_ROOT, { recursive: true });
  for (const name of allowed) {
    const from = path.join(PROVIDED_SOURCE || REPO, name);
    if (!fs.existsSync(from)) continue;
    fs.cpSync(from, path.join(SOURCE_ROOT, name), {
      recursive: true,
      dereference: false,
      filter: (src) => {
        const rel = path.relative(PROVIDED_SOURCE || REPO, src).split(path.sep).join("/");
        if (rel.split("/").some((part) => [".git", "node_modules", "__pycache__", ".pytest_cache"].includes(part))) return false;
        if (rel.split("/").some((part) => part === ".env" || part.startsWith(".env."))) return false;
        if (fs.lstatSync(src).isSymbolicLink()) return false;
        if (rel.startsWith("web/.next") || rel.startsWith("web/.next-deeptutor")) return false;
        if (rel === "web/dist" || rel.startsWith("web/dist/")) return false;
        if (rel.startsWith("web/test-results") || rel.startsWith("web/playwright-report")) return false;
        return true;
      },
    });
  }
  const modules = path.join(SOURCE_ROOT, "web", "node_modules");
  if (!fs.existsSync(modules)) {
    fs.symlinkSync(path.join(REPO, "web", "node_modules"), modules, "dir");
  }
}

function writeR3Settings(): void {
  const dir = path.join(SOURCE_ROOT, "data", "user", "settings");
  const base = `http://127.0.0.1:${MODEL_PORT}`;
  const checked = "2026-10-24T00:00:00Z";
  const controls = (
    levels: string[],
    aliases: Record<string, string>,
    defaultLevel: string | null,
    control = "effort",
    canDisable = true,
  ) => ({
    supported: true,
    control,
    levels,
    can_disable: canDisable,
    default_level: defaultLevel,
    aliases,
    source: {
      kind: "official_docs",
      source_url: "https://api-docs.deepseek.com/guides/thinking_mode/",
      checked_at: checked,
    },
  });
  const withControls = (
    levels: string[],
    aliases: Record<string, string>,
    defaultLevel: string | null,
    control = "effort",
    canDisable = true,
  ) => ({
    provider_metadata: {
      schema_version: 1,
      parameters: {},
      reasoning_controls: controls(
        levels,
        aliases,
        defaultLevel,
        control,
        canDisable,
      ),
    },
    parameter_overrides: { context_window: false, max_tokens: false },
  });
  const profile = (
    id: string,
    name: string,
    binding: string,
    baseUrl: string,
    models: Array<Record<string, unknown>>,
    extra: Record<string, unknown> = {},
  ) => ({
    id,
    name,
    binding,
    base_url: baseUrl,
    api_key: "sk-r3-fictitious-only",
    api_version: "",
    extra_headers: {},
    models,
    ...extra,
  });
  const simpleModels = (prefix: string, suffix: string) => [
    {
      id: `${prefix}-main`,
      name: `${prefix} main`,
      model: `${prefix}-main-${suffix}`,
    },
    {
      id: `${prefix}-alt`,
      name: `${prefix} alt`,
      model: `${prefix}-alt-${suffix}`,
    },
  ];
  writeJson(path.join(dir, "interface.json"), {
    theme: "snow",
    language: "zh",
    response_language: "en",
  });
  writeJson(path.join(dir, "model_catalog.json"), {
    version: 1,
    services: {
      llm: {
        active_profile_id: "r3-deepseek",
        active_model_id: "r3-ds-flash",
        profiles: [
          profile(
            "r3-deepseek",
            "DeepSeek fixture",
            "deepseek",
            `${base}/r3/deepseek/v1`,
            [
              {
                id: "r3-ds-flash",
                name: "Same Flash",
                model: "deepseek-flash",
                visible_in_picker: true,
                ...withControls(
                  ["low", "high", "max"],
                  {
                    minimal: "low",
                    medium: "high",
                    xhigh: "high",
                    ultra: "max",
                  },
                  "high",
                ),
              },
              {
                id: "r3-ds-pro",
                name: "Same Pro",
                model: "deepseek-v4-pro",
                visible_in_picker: true,
                ...withControls(
                  ["low", "high", "max"],
                  {
                    minimal: "low",
                    medium: "high",
                    xhigh: "high",
                    ultra: "max",
                  },
                  "high",
                ),
              },
            ],
            {
              model_directory_url: `${base}/r3/deepseek/v1/models`,
            },
          ),
          profile(
            "r3-deepseek-alt",
            "DeepSeek second key",
            "deepseek",
            `${base}/r3/deepseek-alt/v1`,
            [
              {
                id: "r3-ds-alt-pro",
                name: "Alt Pro",
                model: "deepseek-v4-pro",
                visible_in_picker: true,
                ...withControls(
                  ["low", "high", "max"],
                  {
                    minimal: "low",
                    medium: "high",
                    xhigh: "high",
                    ultra: "max",
                  },
                  "high",
                ),
              },
            ],
            {
              model_directory_url: `${base}/r3/deepseek-alt/v1/models`,
            },
          ),
          profile(
            "r3-aliyun",
            "Aliyun fixture",
            "dashscope",
            `${base}/r3/aliyun/compatible-mode/v1`,
            [
              {
                id: "r3-ali-flash",
                name: "Same Flash",
                model: "deepseek-v4.1-flash",
                visible_in_picker: true,
                ...withControls(
                  ["low", "high", "max"],
                  {
                    minimal: "low",
                    medium: "high",
                    xhigh: "high",
                    ultra: "max",
                  },
                  "high",
                ),
              },
              {
                id: "r3-qwen38",
                name: "Qwen 3.8",
                model: "qwen3.8-max",
                visible_in_picker: true,
                ...withControls(
                  ["low", "medium", "xhigh"],
                  { minimal: "low", high: "xhigh", max: "xhigh" },
                  "xhigh",
                ),
              },
              {
                id: "r3-qwen35",
                name: "Qwen 3.5 budget",
                model: "qwen3.5-plus",
                visible_in_picker: true,
                ...withControls(
                  ["low", "medium", "high"],
                  { minimal: "low", xhigh: "high", max: "high" },
                  null,
                  "budget",
                ),
              },
            ],
            {
              model_directory_url: `${base}/r3/aliyun/api/v1/models`,
            },
          ),
          profile(
            "r3-school",
            "School gateway",
            "custom",
            `${base}/r3/school/v1`,
            [
              {
                id: "r3-school-model",
                name: "School Mystery",
                model: "school/mystery",
                visible_in_picker: true,
              },
            ],
            {
              model_directory_url: `${base}/r3/school/v1/models`,
            },
          ),
        ],
      },
      embedding: {
        active_profile_id: "r3-embed-main",
        active_model_id: "r3-embed-main-model",
        profiles: [
          {
            id: "r3-embed-main",
            name: "Embedding main",
            binding: "openai",
            base_url: `${base}/v1/embeddings`,
            api_key: "sk-r3-fictitious-only",
            api_version: "",
            extra_headers: {},
            models: [
              {
                id: "r3-embed-main-model",
                name: "embedding-main",
                model: "embedding-main",
                dimension: "32",
                send_dimensions: false,
              },
            ],
          },
          {
            id: "r3-embed-alt",
            name: "Embedding alt",
            binding: "openai",
            base_url: `${base}/r3/embedding/v1/embeddings`,
            api_key: "sk-r3-fictitious-only",
            api_version: "",
            extra_headers: {},
            models: [
              {
                id: "r3-embed-alt-model",
                name: "embedding-alt",
                model: "embedding-alt",
                dimension: "1024",
                send_dimensions: false,
              },
            ],
          },
        ],
      },
      search: {
        active_profile_id: "r3-search-brave",
        profiles: [
          {
            id: "r3-search-brave",
            name: "Brave fixture",
            provider: "brave",
            api_key: "r3-search-fictitious",
            base_url: "",
            models: [],
          },
          {
            id: "r3-search-ddgs",
            name: "DuckDuckGo fixture",
            provider: "duckduckgo",
            api_key: "",
            base_url: "",
            models: [],
          },
        ],
      },
      stt: {
        active_profile_id: "r3-stt-main",
        active_model_id: "r3-stt-main-model",
        profiles: [
          profile(
            "r3-stt-main",
            "STT main",
            "openai",
            `${base}/v1`,
            [
              {
                id: "r3-stt-main-model",
                name: "STT main model",
                model: "whisper-1",
              },
            ],
          ),
          profile(
            "r3-stt-alt",
            "STT alt",
            "openai",
            `${base}/r3/stt/v1`,
            [
              {
                id: "r3-stt-alt-model",
                name: "STT alt model",
                model: "whisper-alt",
              },
            ],
          ),
        ],
      },
      tts: {
        active_profile_id: "r3-tts-main",
        active_model_id: "r3-tts-main-model",
        profiles: [
          profile(
            "r3-tts-main",
            "TTS main",
            "openai",
            `${base}/v1`,
            [
              {
                id: "r3-tts-main-model",
                name: "TTS main model",
                model: "tts-1",
                voice: "alloy",
                response_format: "mp3",
              },
            ],
          ),
          profile(
            "r3-tts-alt",
            "TTS alt",
            "openai",
            `${base}/r3/tts/v1`,
            [
              {
                id: "r3-tts-alt-model",
                name: "TTS alt model",
                model: "tts-alt",
                voice: "nova",
                response_format: "mp3",
              },
            ],
          ),
        ],
      },
      vision: {
        active_profile_id: "r3-vision-main",
        active_model_id: "r3-vision-main-model",
        profiles: [
          profile(
            "r3-vision-main",
            "Vision main",
            "openai",
            `${base}/v1`,
            [
              {
                id: "r3-vision-main-model",
                name: "Vision main model",
                model: "gpt-4o",
              },
            ],
          ),
          profile(
            "r3-vision-alt",
            "Vision alt",
            "openai",
            `${base}/r3/vision/v1`,
            [
              {
                id: "r3-vision-alt-model",
                name: "Vision alt model",
                model: "gpt-4o-mini",
              },
            ],
          ),
        ],
      },
      imagegen: {
        active_profile_id: "r3-image-main",
        active_model_id: "r3-image-main-model",
        profiles: [
          profile(
            "r3-image-main",
            "Image main",
            "openai",
            `${base}/v1`,
            [
              {
                id: "r3-image-main-model",
                name: "Image main model",
                model: "dall-e-3",
              },
            ],
          ),
          profile(
            "r3-image-alt",
            "Image alt",
            "openai",
            `${base}/r3/image/v1`,
            [
              {
                id: "r3-image-alt-model",
                name: "Image alt model",
                model: "gpt-image-1",
              },
            ],
          ),
        ],
      },
      videogen: {
        active_profile_id: "r3-video-main",
        active_model_id: "r3-video-main-model",
        profiles: [
          profile(
            "r3-video-main",
            "Video main",
            "openai",
            `${base}/v1`,
            [
              {
                id: "r3-video-main-model",
                name: "Video main model",
                model: "sora-1",
              },
            ],
          ),
          profile(
            "r3-video-alt",
            "Video alt",
            "openai",
            `${base}/r3/video/v1`,
            [
              {
                id: "r3-video-alt-model",
                name: "Video alt model",
                model: "sora-alt",
              },
            ],
          ),
        ],
      },
    },
  });
}

function writeCpSettings(): void {
  const dir = path.join(SOURCE_ROOT, "data", "user", "settings");
  const base = `http://127.0.0.1:${MODEL_PORT}`;
  const profile = (
    id: string,
    name: string,
    binding: string,
    baseUrl: string,
    model: string,
    extra: Record<string, unknown> = {},
  ) => ({
    id,
    name,
    binding,
    base_url: baseUrl,
    api_key: "sk-cp-fictitious-only",
    api_version: "",
    extra_headers: {},
    models: [{ id: `${id}-model`, name: model, model }],
    ...extra,
  });
  writeJson(path.join(dir, "interface.json"), {
    theme: "snow",
    language: "zh",
    response_language: "en",
  });
  writeJson(path.join(dir, "model_catalog.json"), {
    version: 1,
    services: {
      llm: {
        active_profile_id: "cp-deepseek",
        active_model_id: "cp-deepseek-model",
        profiles: [
          profile(
            "cp-deepseek",
            "DeepSeek 默认连接",
            "openai",
            `${base}/v1`,
            "s15-fake-chat",
          ),
        ],
      },
      embedding: {
        active_profile_id: "cp-embedding",
        active_model_id: "cp-embedding-model",
        profiles: [
          {
            ...profile(
              "cp-embedding",
              "Embedding 连接",
              "openai",
              `${base}/v1/embeddings`,
              "s15-fake-embedding",
            ),
            models: [
              {
                id: "cp-embedding-model",
                name: "embedding",
                model: "s15-fake-embedding",
                dimension: "32",
                send_dimensions: false,
              },
            ],
          },
        ],
      },
      stt: {
        active_profile_id: "cp-stt",
        active_model_id: "cp-stt-model",
        profiles: [profile("cp-stt", "STT 连接", "openai", `${base}/v1`, "whisper-1")],
      },
      tts: {
        active_profile_id: "cp-tts",
        active_model_id: "cp-tts-model",
        profiles: [
          {
            ...profile("cp-tts", "TTS 连接", "openai", `${base}/v1`, "tts-1"),
            models: [
              {
                id: "cp-tts-model",
                name: "tts-1",
                model: "tts-1",
                voice: "alloy",
                response_format: "mp3",
              },
            ],
          },
        ],
      },
      vision: {
        active_profile_id: "cp-vision",
        active_model_id: "cp-vision-model",
        profiles: [profile("cp-vision", "Vision 连接", "openai", `${base}/v1`, "gpt-4o")],
      },
      imagegen: {
        active_profile_id: "cp-imagegen",
        active_model_id: "cp-imagegen-model",
        profiles: [
          profile("cp-imagegen", "Image 连接", "openai", `${base}/v1`, "dall-e-3"),
        ],
      },
      videogen: {
        active_profile_id: "cp-videogen",
        active_model_id: "cp-videogen-model",
        profiles: [
          profile("cp-videogen", "Video 连接", "openai", `${base}/v1`, "sora-1"),
        ],
      },
      search: {
        active_profile_id: "cp-search",
        profiles: [
          {
            id: "cp-search",
            name: "Brave fixture",
            provider: "brave",
            api_key: "cp-search-fictitious",
            base_url: "",
            models: [],
          },
        ],
      },
    },
  });
}

function writeSettings(): void {
  const dir = path.join(SOURCE_ROOT, "data", "user", "settings");
  fs.mkdirSync(dir, { recursive: true });
  writeJson(path.join(dir, "system.json"), {
    backend_port: BACKEND_PORT,
    next_public_api_base: WEB_ORIGIN,
    next_public_api_base_external: WEB_ORIGIN,
    auth_enabled: false,
    disable_ssl_verify: false,
  });
  writeJson(path.join(dir, "auth.json"), { enabled: false, secret: "s15-fictitious-only", users: [] });
  if (RUN_LABEL === "mm-r3") {
    writeR3Settings();
    return;
  }
  if (RUN_LABEL === "cp-r1") {
    writeCpSettings();
    return;
  }
  writeJson(path.join(dir, "model_catalog.json"), {
    version: 1,
    services: {
      llm: {
        active_profile_id: "s15-local-llm-profile",
        active_model_id: "s15-local-llm-model",
        profiles: [{
          id: "s15-local-llm-profile",
          name: "S15 deterministic local model",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [
            { id: "s15-local-llm-model", name: "s15-fake-chat", model: "s15-fake-chat", supports_vision: false },
            { id: "s15-hidden-model", name: "s15-hidden-chat", model: "s15-hidden-chat", supports_vision: false },
          ],
        }, {
          id: "s15-discovery-a",
          name: "Discovery delay A",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/a/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-a-model", name: "s15-a-existing", model: "s15-a-existing" }],
        }, {
          id: "s15-discovery-b",
          name: "Discovery delay B",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/b/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-b-model", name: "s15-b-existing", model: "s15-b-existing" }],
        }],
      },
      embedding: {
        active_profile_id: "s15-local-embedding-profile",
        active_model_id: "s15-local-embedding-model",
        profiles: [{
          id: "s15-local-embedding-profile",
          name: "S15 deterministic local embedding",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/v1/embeddings`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-local-embedding-model", name: "s15-fake-embedding", model: "s15-fake-embedding", dimension: 32, send_dimensions: false }],
        }, {
          id: "s15-discovery-embedding",
          name: "Discovery embedding",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/embedding/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-embedding-model", name: "text-embedding-3-small", model: "text-embedding-3-small", dimension: 32, send_dimensions: false }],
        }],
      },
      stt: {
        active_profile_id: "s15-local-stt-profile",
        active_model_id: "s15-local-stt-model",
        profiles: [{
          id: "s15-local-stt-profile",
          name: "S15 deterministic local STT",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-local-stt-model", name: "s15-fake-stt", model: "s15-fake-stt" }],
        }, {
          id: "s15-discovery-stt",
          name: "Discovery STT",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/stt/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-stt-model", name: "whisper-1", model: "whisper-1" }],
        }],
      },
      tts: {
        active_profile_id: "s15-discovery-tts",
        active_model_id: "s15-discovery-tts-model",
        profiles: [{
          id: "s15-discovery-tts",
          name: "Discovery TTS",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/tts/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-tts-model", name: "tts-1", model: "tts-1", voice: "alloy", response_format: "mp3" }],
        }],
      },
      imagegen: {
        active_profile_id: "s15-discovery-imagegen",
        active_model_id: "s15-discovery-imagegen-model",
        profiles: [{
          id: "s15-discovery-imagegen",
          name: "Discovery imagegen",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/imagegen/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-imagegen-model", name: "dall-e-3", model: "dall-e-3" }],
        }],
      },
      videogen: {
        active_profile_id: "s15-discovery-videogen",
        active_model_id: "s15-discovery-videogen-model",
        profiles: [{
          id: "s15-discovery-videogen",
          name: "Discovery videogen",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/videogen/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-videogen-model", name: "sora-1", model: "sora-1" }],
        }],
      },
      vision: {
        active_profile_id: "s15-discovery-vision",
        active_model_id: "s15-discovery-vision-model",
        profiles: [{
          id: "s15-discovery-vision",
          name: "Discovery vision",
          binding: "openai",
          base_url: `http://127.0.0.1:${MODEL_PORT}/discovery/vision/v1`,
          api_key: "sk-s15-fictitious-only",
          models: [{ id: "s15-discovery-vision-model", name: "gpt-4o", model: "gpt-4o" }],
        }],
      },
      search: { active_profile_id: null, profiles: [] },
    },
  });
}

const MODEL_SERVER = String.raw`
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";

const port = Number(process.argv[2]);
const logPath = process.argv[3];
const asrDelayMs = ${ASR_DELAY_MS};
const log = (row) => fs.appendFileSync(logPath, JSON.stringify(row) + "\n");

function vector(text) {
  const dims = Array(32).fill(0);
  const tokens = String(text).toLowerCase().match(/[a-z0-9]+/g) || [];
  for (const token of tokens) {
    const digest = crypto.createHash("sha256").update(token).digest();
    dims[digest[0] % 32] += 1;
  }
  const norm = Math.sqrt(dims.reduce((acc, value) => acc + value * value, 0)) || 1;
  return dims.map((value) => value / norm);
}
function collectText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => {
    if (typeof part === "string") return part;
    if (part && typeof part === "object") return String(part.text || part.content || "");
    return "";
  }).join("\n");
  return "";
}
function chatText(messages) {
  const users = messages.filter((m) => m && m.role === "user");
  const lastUser = users.length ? collectText(users[users.length - 1].content) : "";
  const allSystem = messages.filter((m) => m && m.role === "system").map((m) => collectText(m.content)).join("\n");
  const labelled = (label, body) => String.fromCharCode(96).repeat(2) + label + String.fromCharCode(96).repeat(2) + "\n" + body;
  if (/You are the Quiz Planner/.test(allSystem)) {
    const count = Math.min(3, Math.max(1, Number((lastUser.match(/Number of questions:\s*(\d+)/) || ["", "3"])[1])));
    return labelled("PLAN", JSON.stringify({analysis:"Deterministic isolated quiz", templates:Array.from({length:count},(_,i)=>({
      question_id:"q_"+(i+1), topic:"E2E quiz topic "+(i+1), question_type:"short_answer", difficulty:"easy",
    }))}));
  }
  if (/You are writing \*\*one\*\* quiz question/.test(allSystem)) {
    const number = (allSystem.match(/#(\d+) of/) || ["", "1"])[1];
    return labelled("FINISH", JSON.stringify({question:"E2E-QUIZ-"+number+": What is 1 + 1?",correct_answer:"2",explanation:"Adding one and one gives two.",question_type:"short_answer"}));
  }
  if (/Exploration Agent for a tutor-style quiz generator/.test(allSystem)) return labelled("FINISH", "E2E-QUIZ-READY: I will prepare three isolated fixture questions.");
  if (/考点|课堂讲课转写/.test(allSystem) || /"points"/.test(lastUser)) {
    const transcript = lastUser.replace(/^[\s\S]*?转写[:：]\s*/, "").trim();
    const evidence = "这个知识点很重要，大家一定要重视起来。";
    return JSON.stringify({ points: [{
      content: "E2E 考点：常微分方程解的存在唯一性",
      level: "explicit",
      evidence: transcript.includes(evidence) ? evidence : transcript.slice(0, Math.min(40, transcript.length)),
      kp: "E2E 考点",
    }] });
  }
  if (/session title|conversation title|标题/.test(allSystem)) return "E2E 会话标题";
  const marker = (lastUser.match(/E2E-[A-Z0-9][A-Z0-9-]*/) || ["E2E-NONE"])[0];
  const seed = lastUser.split("[Knowledge Base Context]").slice(1).join("[Knowledge Base Context]");
  const retrieved = [...new Set(seed.match(/E2E-[ABG]-ONLY-[a-z0-9]+/g) || [])];
  return "E2E-ANSWER:" + marker + (retrieved.length ? " GROUNDED:" + retrieved.join(",") : "");
}
let discoveryFail = false;
let discoveryDelayA = 0;
const discoveryCounts = {};
const requestLog = [];
const directoryLog = [];
function r2Directory(pathname) {
  if (pathname === "/r2/deepseek/v1/models") {
    return { object: "list", data: [
      { id: "deepseek-flash", name: "DeepSeek V4.1 Flash", context_window: 1048576, max_output_tokens: 393216,
        input_modalities: ["text", "image"], output_modalities: ["text"] },
      { id: "deepseek-v4-pro", name: "DeepSeek V4 Pro", context_window: 1048576, max_output_tokens: 393216,
        input_modalities: ["text"], output_modalities: ["text"] },
    ] };
  }
  if (pathname === "/r2/aliyun/api/v1/models") {
    return { success: true, output: { total: 4, page_no: 1, page_size: 100, models: [
      { model: "qwen-plus", name: "通义千问 Plus", capabilities: ["TG"], inference_provider: "aliyun-bailian",
        model_info: { context_window: 1000000, max_input_tokens: 995904, max_output_tokens: 32768 } },
      { model: "text-embedding-v4", name: "文本向量 V4", capabilities: ["TR"], inference_provider: "aliyun-bailian",
        model_info: { context_window: 8192, max_output_tokens: 8192 } },
      { model: "qwen3-asr-flash", name: "千问 ASR Flash", capabilities: ["ASR"], inference_provider: "aliyun-bailian" },
      { model: "qwen3-vl-plus", name: "千问 VL Plus", capabilities: ["VU"], inference_provider: "aliyun-bailian" },
    ] } };
  }
  if (pathname === "/r2/school/ai/models") {
    return { data: [
      { id: "school/DeepSeek-V4", name: "School DeepSeek V4", context_window: 65536, max_output_tokens: 8192,
        input_modalities: ["text"], output_modalities: ["text"] },
      { id: "school/Mystery", name: "School Mystery" },
    ] };
  }
  if (
    pathname === "/r2/embedding/v1/models" ||
    pathname === "/r2/embedding/v1/embeddings/models"
  ) {
    return { object: "list", data: [
      { id: "school-embedding-default", name: "School Embedding 1024",
        default_dimensions: 1024, supported_dimensions: [2048, 1024], supports_dimensions_parameter: true },
      { id: "school-embedding-choices", name: "School Embedding Choices",
        supported_dimensions: [2048, 1536] },
    ] };
  }
  return null;
}
function r3Directory(pathname) {
  if (pathname === "/r3/deepseek/v1/models") {
    return { object: "list", data: [
      { id: "deepseek-flash", name: "DeepSeek Flash", context_window: 1048576,
        max_output_tokens: 393216,
        effort: { supported_levels: ["low", "high", "max"], default_level: "high" } },
      { id: "deepseek-v4-pro", name: "DeepSeek Pro", context_window: 1048576,
        max_output_tokens: 393216,
        effort: { supported_levels: ["low", "high", "max"], default_level: "high" } },
    ] };
  }
  if (pathname === "/r3/deepseek-alt/v1/models") {
    return { object: "list", data: [
      { id: "deepseek-v4-pro", name: "DeepSeek Pro", context_window: 1048576,
        max_output_tokens: 393216,
        effort: { supported_levels: ["low", "high", "max"], default_level: "high" } },
    ] };
  }
  if (pathname === "/r3/aliyun/api/v1/models") {
    return { success: true, output: { total: 3, page_no: 1, page_size: 100, models: [
      { model: "deepseek-v4.1-flash", name: "Aliyun DeepSeek Flash", capabilities: ["TG"],
        inference_provider: "aliyun-bailian",
        model_info: { context_window: 1048576, max_output_tokens: 393216 } },
      { model: "qwen3.8-max", name: "Qwen 3.8 Max", capabilities: ["TG"],
        inference_provider: "aliyun-bailian",
        model_info: { context_window: 1048576, max_output_tokens: 65536 } },
      { model: "qwen3.5-plus", name: "Qwen 3.5 Plus", capabilities: ["TG"],
        inference_provider: "aliyun-bailian",
        model_info: { context_window: 1000000, max_output_tokens: 32768 } },
    ] } };
  }
  if (pathname === "/r3/school/v1/models") {
    return { object: "list", data: [
      { id: "school/mystery", name: "School Mystery" },
    ] };
  }
  return null;
}
function cpDirectory(pathname) {
  if (pathname === "/cp/openai/v1/models") {
    return { object: "list", data: [
      { id: "school/mystery", name: "School Mystery", context_window: 65536, max_output_tokens: 8192 },
      { id: "school/same", name: "Same Model", context_window: 32768, max_output_tokens: 4096 },
    ] };
  }
  if (pathname === "/cp/anthropic/v1/models") {
    return { data: [
      { id: "claude-school", display_name: "Claude School", type: "model" },
      { id: "same-model", display_name: "Same Model", type: "model" },
    ], has_more: false };
  }
  return null;
}

function discoveryModels(service) {
  const rows = {
    llm: [
      { id: "gpt-4.1", name: "GPT 4.1 fixture" },
      { id: "gpt-4.1-mini", name: "GPT 4.1 Mini fixture" },
      { id: "custom/unknown-fixture", name: "Unknown fixture" },
    ],
    embedding: [
      { id: "text-embedding-3-small", name: "Embedding small fixture" },
      { id: "text-embedding-3-large", name: "Embedding large fixture" },
    ],
    stt: [
      { id: "whisper-1", name: "Whisper fixture" },
      { id: "gpt-4o-mini-transcribe", name: "Transcribe fixture" },
    ],
    tts: [
      { id: "tts-1", name: "TTS 1 fixture" },
      { id: "gpt-4o-mini-tts", name: "Mini TTS fixture" },
    ],
    imagegen: [
      { id: "dall-e-3", name: "DALL-E fixture" },
      { id: "gpt-image-1", name: "Image fixture" },
    ],
    videogen: [
      { id: "sora-1", name: "Sora fixture" },
      { id: "custom-video-fixture", name: "Unknown video fixture" },
    ],
    vision: [
      { id: "gpt-4o", name: "Vision fixture", services: ["vision"] },
      { id: "custom/vision-fixture", name: "Unknown vision fixture", services: ["vision"] },
    ],
    a: [{ id: "gpt-4.1-a", name: "Delayed A fixture" }],
    b: [{ id: "gpt-4.1-b", name: "B fixture" }],
  };
  return rows[service] || rows.llm;
}
function completionBody(text, model) {
  return { id: "chatcmpl-s15", object: "chat.completion", created: Math.floor(Date.now() / 1000), model,
    choices: [{ index: 0, message: { role: "assistant", content: text }, finish_reason: "stop" }],
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } };
}
function streamCompletion(res, text, model) {
  res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive" });
  const base = { id: "chatcmpl-s15", object: "chat.completion.chunk", created: Math.floor(Date.now() / 1000), model };
  res.write("data: " + JSON.stringify({ ...base, choices: [{ index: 0, delta: { role: "assistant" }, finish_reason: null }] }) + "\n\n");
  const pieces = text.length > 120 ? [text.slice(0, 120), text.slice(120)] : [text];
  for (const piece of pieces) res.write("data: " + JSON.stringify({ ...base, choices: [{ index: 0, delta: { content: piece }, finish_reason: null }] }) + "\n\n");
  res.write("data: " + JSON.stringify({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }] }) + "\n\n");
  res.write("data: [DONE]\n\n");
  res.end();
}

http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const raw = Buffer.concat(chunks);
    const url = req.url || "";
    log({ method: req.method, url, bytes: raw.length, at: new Date().toISOString() });
    const pathname = url.split("?")[0];
    if (req.method === "POST" && pathname.endsWith("/chat/completions")) {
      let parsedBody = {};
      try { parsedBody = JSON.parse(raw.toString("utf8")); } catch {}
      requestLog.push({
        pathname,
        model: parsedBody.model || null,
        max_tokens: parsedBody.max_tokens ?? parsedBody.max_completion_tokens ?? null,
        message_count: Array.isArray(parsedBody.messages) ? parsedBody.messages.length : null,
        stream: Boolean(parsedBody.stream),
        reasoning_effort: parsedBody.reasoning_effort ?? null,
        thinking: parsedBody.thinking ?? null,
        enable_thinking: parsedBody.enable_thinking ?? null,
        thinking_budget: parsedBody.thinking_budget ?? null,
        temperature: parsedBody.temperature ?? null,
        authorization_present: Boolean(req.headers.authorization),
        authorization_fingerprint: req.headers.authorization
          ? crypto.createHash("sha256").update(req.headers.authorization).digest("hex").slice(0, 12)
          : null,
        at: new Date().toISOString(),
      });
      if (requestLog.length > 100) requestLog.shift();
    }
    if (pathname === "/md/control") {
      const parsed = new URL(url, "http://127.0.0.1");
      if (parsed.searchParams.has("fail")) discoveryFail = parsed.searchParams.get("fail") === "1";
      if (parsed.searchParams.has("delayA")) discoveryDelayA = Number(parsed.searchParams.get("delayA") || "0");
      if (parsed.searchParams.get("reset") === "1") {
        for (const key of Object.keys(discoveryCounts)) delete discoveryCounts[key];
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, fail: discoveryFail, delay_a: discoveryDelayA }));
      return;
    }
    if (pathname === "/md/stats") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ counts: discoveryCounts, fail: discoveryFail, delay_a: discoveryDelayA }));
      return;
    }
    if (pathname === "/md/requests") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ requests: requestLog, directory_requests: directoryLog }));
      return;
    }
    if (req.method === "GET" && pathname.startsWith("/r3/")) {
      const payload = r3Directory(pathname);
      res.writeHead(payload ? 200 : 404, { "Content-Type": "application/json" });
      res.end(JSON.stringify(payload || { error: "no r3 fixture route" }));
      return;
    }
    if (req.method === "GET" && pathname.startsWith("/r2/")) {
      discoveryCounts[pathname] = (discoveryCounts[pathname] || 0) + 1;
      directoryLog.push({
        pathname,
        authorization_present: Boolean(req.headers.authorization),
        school_header: req.headers["x-school-app"] || null,
        at: new Date().toISOString(),
      });
      if (directoryLog.length > 100) directoryLog.shift();
      if (pathname === "/r2/unauthorized/v1/models") {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "fixture unauthorized" }));
        return;
      }
      if (pathname === "/r2/school/ai/v1/models") {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "fixture path fallback" }));
        return;
      }
      const payload = r2Directory(pathname);
      if (payload) {
        if (discoveryFail) {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "fixture directory failed" }));
          return;
        }
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(payload));
        return;
      }
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "no r2 fixture route" }));
      return;
    }
    if (req.method === "GET" && pathname.startsWith("/cp/")) {
      discoveryCounts[pathname] = (discoveryCounts[pathname] || 0) + 1;
      directoryLog.push({
        pathname,
        authorization_present: Boolean(req.headers.authorization),
        x_api_key_present: Boolean(req.headers["x-api-key"]),
        authorization_fingerprint: req.headers.authorization
          ? crypto.createHash("sha256").update(req.headers.authorization).digest("hex").slice(0, 12)
          : req.headers["x-api-key"]
            ? crypto.createHash("sha256").update(String(req.headers["x-api-key"])).digest("hex").slice(0, 12)
            : null,
        anthropic_version: req.headers["anthropic-version"] || null,
        at: new Date().toISOString(),
      });
      if (directoryLog.length > 100) directoryLog.shift();
      const payload = cpDirectory(pathname);
      res.writeHead(payload ? 200 : 404, { "Content-Type": "application/json" });
      res.end(JSON.stringify(payload || { error: "no cp fixture directory" }));
      return;
    }
    if (req.method === "GET" && (pathname === "/v1/models" || pathname === "/v1/embeddings/models" || pathname.startsWith("/discovery/"))) {
      let service = pathname === "/v1/models" ? "llm" : pathname === "/v1/embeddings/models" ? "embedding" : "";
      if (!service && pathname.startsWith("/discovery/")) {
        service = pathname.split("/")[2] || "llm";
      }
      discoveryCounts[pathname] = (discoveryCounts[pathname] || 0) + 1;
      const send = () => {
        if (discoveryFail) {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "fixture directory failed" }));
          return;
        }
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ object: "list", data: discoveryModels(service) }));
      };
      if (service === "a" && discoveryDelayA > 0) setTimeout(send, discoveryDelayA);
      else send();
      return;
    }
    if (req.method === "POST" && url.endsWith("/embeddings")) {
      let body = {};
      try { body = JSON.parse(raw.toString("utf8")); } catch {}
      const inputs = Array.isArray(body.input) ? body.input : [body.input ?? ""];
      const data = inputs.map((item, index) => ({ object: "embedding", index, embedding: vector(item) }));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ object: "list", data, model: body.model || "s15-fake-embedding", usage: { prompt_tokens: 1, total_tokens: 1 } }));
      return;
    }
    if (req.method === "POST" && url.endsWith("/audio/transcriptions")) {
      const send = () => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ text: "E2E-TRANSCRIPT-B3 课堂录音转写内容，用于考察材料去向。" }));
      };
      if (asrDelayMs > 0) setTimeout(send, asrDelayMs);
      else send();
      return;
    }
    if (req.method === "POST" && pathname.endsWith("/messages")) {
      let parsedBody = {};
      try { parsedBody = JSON.parse(raw.toString("utf8")); } catch {}
      requestLog.push({
        pathname,
        protocol: "anthropic_messages",
        model: parsedBody.model || null,
        max_tokens: parsedBody.max_tokens ?? null,
        message_count: Array.isArray(parsedBody.messages) ? parsedBody.messages.length : null,
        stream: Boolean(parsedBody.stream),
        authorization_present: Boolean(req.headers.authorization),
        x_api_key_present: Boolean(req.headers["x-api-key"]),
        authorization_fingerprint: req.headers.authorization
          ? crypto.createHash("sha256").update(req.headers.authorization).digest("hex").slice(0, 12)
          : req.headers["x-api-key"]
            ? crypto.createHash("sha256").update(String(req.headers["x-api-key"])).digest("hex").slice(0, 12)
            : null,
        anthropic_version: req.headers["anthropic-version"] || null,
        at: new Date().toISOString(),
      });
      if (requestLog.length > 100) requestLog.shift();
    }
    if (req.method === "POST" && pathname.endsWith("/messages")) {
      let body = {};
      try { body = JSON.parse(raw.toString("utf8")); } catch {}
      const model = body.model || "claude-school";
      if (!body.stream) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({
          id: "msg_cp", type: "message", role: "assistant", model,
          content: [{ type: "text", text: "E2E-ANTHROPIC-ANSWER" }],
          stop_reason: "end_turn", stop_sequence: null,
          usage: { input_tokens: 1, output_tokens: 1 },
        }));
        return;
      }
      res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive" });
      const send = (event, data) => res.write("event: " + event + "\ndata: " + JSON.stringify(data) + "\n\n");
      send("message_start", { type: "message_start", message: {
        id: "msg_cp", type: "message", role: "assistant", model,
        content: [], stop_reason: null, stop_sequence: null,
        usage: { input_tokens: 1, output_tokens: 0 },
      }});
      send("content_block_start", { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } });
      send("content_block_delta", { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "E2E-ANTHROPIC-ANSWER" } });
      send("content_block_stop", { type: "content_block_stop", index: 0 });
      send("message_delta", { type: "message_delta", delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 1 } });
      send("message_stop", { type: "message_stop" });
      res.end();
      return;
    }
    if (req.method === "POST" && url.endsWith("/chat/completions")) {
      let body = {};
      try { body = JSON.parse(raw.toString("utf8")); } catch {}
      const model = body.model || "s15-fake-chat";
      const text = chatText(Array.isArray(body.messages) ? body.messages : []);
      if (body.stream) streamCompletion(res, text, model);
      else { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify(completionBody(text, model))); }
      return;
    }
    if (url === "/health") { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify({ ok: true })); return; }
    res.writeHead(404, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: "not found" }));
  });
}).listen(port, "127.0.0.1", () => console.log("S15_MODEL_READY " + port));
`;

const BACKEND_LAUNCHER = String.raw`
from pathlib import Path
import os
import uvicorn
import deeptutor
from deeptutor.api.main import app
print("S15_BACKEND_MODULE " + str(Path(deeptutor.__file__).resolve()), flush=True)
print("S15_BACKEND_HOME " + os.environ.get("DEEPTUTOR_HOME", ""), flush=True)
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["BACKEND_PORT"]), log_level="info", lifespan="on")
`;

// Reuse the S13 Python network guard verbatim. The backend may connect only
// to the three loopback endpoints registered below; external DNS/TCP fails.
const VERIFY_SOURCE = fs.readFileSync(path.join(REPO, "scripts", "phase1_verify.py"), "utf-8");
const GUARD_MATCH = VERIFY_SOURCE.match(/NETWORK_GUARD = """([\s\S]*?)"""/);
if (!GUARD_MATCH) throw new Error("S13 network guard not found");
const PY_GUARD = GUARD_MATCH[1];
const GUARD_DIR = path.join(RUN_ROOT, "guard");
const GUARD_REGISTRY = path.join(GUARD_DIR, "endpoints.json");
const NODE_GUARD_FILE = path.join(GUARD_DIR, "network.cjs");
const NODE_GUARD = String.raw`
const fs = require('node:fs'), net = require('node:net'), dns = require('node:dns'), path = require('node:path');
const ports = new Set(process.env.S15_ALLOWED_PORTS.split(',').map(Number));
function denied(kind, host) {
  const error = new Error('S15 network guard: undeclared endpoint blocked');
  error.code = 'ES15_NETWORK_GUARD';
  fs.appendFileSync(process.env.S15_NODE_GUARD_LOG, JSON.stringify({kind, host: String(host), pid: process.pid})+'\n');
  return error;
}
function loopback(host) { return ['127.0.0.1','::1','localhost'].includes(String(host || 'localhost')); }
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  let first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options = typeof first === 'object' ? first : typeof first === 'number' ? {port: first, host: args[1]} : {path: first};
  if (options.path) {
    const relative = path.relative(process.env.S15_RUN_ROOT, String(options.path));
    if (relative.startsWith('..') || path.isAbsolute(relative)) throw denied('unix', 'outside-owned-root');
  } else if (!loopback(options.host) || !ports.has(Number(options.port))) throw denied('tcp', options.host);
  return connect.apply(this, args);
};
const lookup = dns.lookup;
dns.lookup = function(host, options, callback) {
  if (loopback(host)) return lookup.apply(this, arguments);
  const cb = typeof options === 'function' ? options : callback;
  queueMicrotask(() => cb(denied('dns', host)));
};
const promiseLookup = dns.promises.lookup;
dns.promises.lookup = async function(host, ...args) {
  if (!loopback(host)) throw denied('dns', host);
  return promiseLookup.call(this, host, ...args);
};
for (const name of Object.keys(dns).filter(name => name.startsWith('resolve') || name === 'reverse')) {
  dns[name] = function(host, ...args) { const cb=args[args.length-1]; queueMicrotask(()=>cb(denied('dns',host))); };
  dns.promises[name] = async function(host) { throw denied('dns',host); };
}
const dgram = require('node:dgram');
dgram.Socket.prototype.send = function() { throw denied('udp', 'disabled'); };
`;
if (controller) {
  fs.mkdirSync(GUARD_DIR, { recursive: true });
  fs.writeFileSync(path.join(GUARD_DIR, "sitecustomize.py"), PY_GUARD, "utf-8");
  writeJson(GUARD_REGISTRY, [["loopback", MODEL_PORT], ["loopback", BACKEND_PORT], ["loopback", WEB_PORT]]);
  fs.writeFileSync(NODE_GUARD_FILE, NODE_GUARD, "utf-8");
}
process.env.S15_ALLOWED_PORTS = [MODEL_PORT, BACKEND_PORT, WEB_PORT].join(",");
process.env.S15_NODE_GUARD_LOG = path.join(STAGE, "node-egress.jsonl");
process.env.NODE_OPTIONS = `--require ${JSON.stringify(NODE_GUARD_FILE)}`;
createRequire(path.join(REPO, "web", "package.json"))(NODE_GUARD_FILE);

const SUPERVISOR = String.raw`
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

log_path = Path(sys.argv[1])
pid_path = Path(sys.argv[2])
log = log_path.open("ab", buffering=0)
child = subprocess.Popen(sys.argv[3:], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
import json
def identity(pid):
    return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
pid_path.write_text(json.dumps({"pid": child.pid, "start": identity(child.pid)}))
def forward(signum, frame):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    raise SystemExit(0)
signal.signal(signal.SIGTERM, forward)
signal.signal(signal.SIGINT, forward)
raise SystemExit(child.wait())
`;

function shellQuote(value: string): string {
  return "'" + value.replace(/'/g, "'\"'\"'") + "'";
}

function envArgs(env: Record<string, string>): string {
  return Object.entries(env).map(([key, value]) => `${key}=${shellQuote(value)}`).join(" ");
}

function supervisorScript(name: string, env: Record<string, string>, command: string[]): string {
  const file = path.join(RUN_ROOT, `start-${name}.sh`);
  const log = path.join(LOG_DIR, `${RUN_LABEL}-${name}.log`);
  const pid = path.join(RUN_ROOT, `${name}.pid`);
  const envWithPath = {
    PATH: "/usr/local/bin:/usr/bin:/bin", LANG: "C.UTF-8", TZ: "UTC",
    S15_RUN_ROOT: RUN_ROOT, S15_ALLOWED_PORTS: process.env.S15_ALLOWED_PORTS!,
    S15_NODE_GUARD_LOG: process.env.S15_NODE_GUARD_LOG!, NODE_OPTIONS: process.env.NODE_OPTIONS!,
    ...env,
  };
  if (!controller) return file;
  fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.writeFileSync(file, [
    "#!/bin/bash",
    "set -eu",
    `exec ${shellQuote(path.join(REPO, ".venv", "bin", "python"))} ${shellQuote(path.join(RUN_ROOT, "supervisor.py"))} ${shellQuote(log)} ${shellQuote(pid)} ` +
      `env -i ${envArgs(envWithPath)} ${command.map(shellQuote).join(" ")}`,
    "",
  ].join("\n"), { mode: 0o755 });
  return file;
}

// Build the isolated tree before Playwright validates/starts the services.
if (controller) {
fs.mkdirSync(LOG_DIR, { recursive: true });
fs.mkdirSync(ARTIFACTS, { recursive: true });
fs.mkdirSync(RUN_ROOT, { recursive: true });
if (!fs.existsSync(path.join(SOURCE_ROOT, "web", "next.config.js"))) copySource();
if (!fs.existsSync(path.join(SOURCE_ROOT, "web", "node_modules"))) {
  fs.symlinkSync(path.join(REPO, "web", "node_modules"), path.join(SOURCE_ROOT, "web", "node_modules"), "dir");
}
writeSettings();
fs.mkdirSync(path.join(RUN_ROOT, "home"), { recursive: true });
fs.mkdirSync(path.join(RUN_ROOT, "tmp"), { recursive: true });
fs.writeFileSync(path.join(RUN_ROOT, "model_server.mjs"), MODEL_SERVER, "utf-8");
fs.writeFileSync(path.join(RUN_ROOT, "backend_launcher.py"), BACKEND_LAUNCHER, "utf-8");
fs.writeFileSync(path.join(RUN_ROOT, "supervisor.py"), SUPERVISOR, "utf-8");
}

const modelScript = supervisorScript("model", {
  HOME: path.join(RUN_ROOT, "home"),
  TMPDIR: path.join(RUN_ROOT, "tmp"),
  NEXT_TELEMETRY_DISABLED: "1",
}, [process.execPath, path.join(RUN_ROOT, "model_server.mjs"), String(MODEL_PORT), MODEL_LOG]);

const backendScript = supervisorScript("backend", {
  DEEPTUTOR_HOME: SOURCE_ROOT,
  HOME: path.join(RUN_ROOT, "home"),
  XDG_CONFIG_HOME: path.join(RUN_ROOT, "home", ".config"),
  XDG_DATA_HOME: path.join(RUN_ROOT, "home", ".local", "share"),
  XDG_CACHE_HOME: path.join(RUN_ROOT, "home", ".cache"),
  TMPDIR: path.join(RUN_ROOT, "tmp"),
  PYTHONPATH: `${GUARD_DIR}:${SOURCE_ROOT}`,
  S13_ENDPOINT_REGISTRY: GUARD_REGISTRY,
  PYTHONUNBUFFERED: "1",
  PYTHONDONTWRITEBYTECODE: "1",
  BACKEND_PORT: String(BACKEND_PORT),
  AUTH_ENABLED: "false",
  ...(process.env.SELFLEARN_FFMPEG_BIN ? { SELFLEARN_FFMPEG_BIN: process.env.SELFLEARN_FFMPEG_BIN } : {}),
  ...(process.env.SELFLEARN_FFPROBE_BIN ? { SELFLEARN_FFPROBE_BIN: process.env.SELFLEARN_FFPROBE_BIN } : {}),
}, [path.join(REPO, ".venv", "bin", "python"), path.join(RUN_ROOT, "backend_launcher.py")]);

const nextScript = supervisorScript("next", {
  DEEPTUTOR_HOME: SOURCE_ROOT,
  HOME: path.join(RUN_ROOT, "home"),
  XDG_CONFIG_HOME: path.join(RUN_ROOT, "home", ".config"),
  XDG_DATA_HOME: path.join(RUN_ROOT, "home", ".local", "share"),
  XDG_CACHE_HOME: path.join(RUN_ROOT, "home", ".cache"),
  TMPDIR: path.join(RUN_ROOT, "tmp"),
  BACKEND_PORT: String(BACKEND_PORT),
  DEEPTUTOR_API_BASE_URL: BACKEND_ORIGIN,
  NEXT_PUBLIC_API_BASE: WEB_ORIGIN,
  NEXT_PUBLIC_API_BASE_EXTERNAL: WEB_ORIGIN,
  NEXT_PUBLIC_AUTH_ENABLED: "false",
  AUTH_ENABLED: "false",
  WEB_BASE_URL: WEB_ORIGIN,
  DEEPTUTOR_NEXT_DIST_DIR: ".next-s15",
  NEXT_TELEMETRY_DISABLED: "1",
  NODE_ENV: "development",
}, [
  process.execPath,
  path.join(REPO, "web", "node_modules", "next", "dist", "bin", "next"),
  "dev", "--webpack", "--hostname", "127.0.0.1", "--port", String(WEB_PORT),
]);

function optionalMtime(file: string): number | null {
  return fs.existsSync(file) ? fs.statSync(file).mtimeMs : null;
}
const realNextMtime = optionalMtime(path.join(REPO, "web", ".next"));
const realNextDeptutorMtime = optionalMtime(path.join(REPO, "web", ".next-deeptutor"));
const state = {
  schema_version: 1,
  stage_id: "S15",
  run_label: RUN_LABEL,
  run_id: bootstrap.run_id,
  started_at: new Date().toISOString(),
  run_root: RUN_ROOT,
  source_root: SOURCE_ROOT,
  source_is_copy: true,
  provided_source: PROVIDED_SOURCE,
  ports: { model: MODEL_PORT, backend: BACKEND_PORT, web: WEB_PORT },
  origins: { web: WEB_ORIGIN, backend: BACKEND_ORIGIN, model: `http://127.0.0.1:${MODEL_PORT}` },
  logs: { model: MODEL_LOG, backend: BACKEND_LOG, next: NEXT_LOG },
  scripts: { model: modelScript, backend: backendScript, next: nextScript },
  state_file: STATE_FILE,
  real_source_head: execFileSync("git", ["rev-parse", "HEAD"], { cwd: REPO, encoding: "utf-8" }).trim(),
  real_next_mtime: realNextMtime,
  real_next_deeptutor_mtime: realNextDeptutorMtime,
  data_before_sha256: fs.existsSync(path.join(STAGE, "data_before.json")) ? hashFile(path.join(STAGE, "data_before.json")) : null,
  browser_executable: process.env.S15_CHROMIUM || "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
  browser_native_libs: NATIVE_LIBS,
  browser_font_config: FONT_CONFIG,
  python: path.join(REPO, ".venv", "bin", "python"),
  python_guard: { sitecustomize: path.join(GUARD_DIR, "sitecustomize.py"), registry: GUARD_REGISTRY },
};
if (controller) {
  writeJson(STATE_FILE, state);
  fs.writeFileSync(path.join(LOG_DIR, `${RUN_LABEL}-runner.json`), JSON.stringify(state, null, 2) + "\n", "utf-8");
}

const TEARDOWN = String.raw`
const fs = require('node:fs'), path = require('node:path'), net = require('node:net');
const {execFileSync} = require('node:child_process');
module.exports = async function() {
  const state = JSON.parse(fs.readFileSync(process.env.S15_RUN_STATE_FILE, 'utf8'));
  const root = state.run_root;
  // Only PID + birth identity recorded by our supervisor may be signalled.
  const stop = ` + "`" + String.raw`
import json,os,signal,sys,time
from pathlib import Path
root=Path(sys.argv[1])
def identity(pid):
    try:
        tail=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
        return tail[19] if tail[0]!='Z' else None
    except FileNotFoundError:
        return None
for name in ('next','backend','model'):
    file=root/(name+'.pid')
    if not file.exists(): continue
    item=json.loads(file.read_text());pid=item['pid']
    if identity(pid)!=item['start']: continue
    if os.getpgid(pid)!=pid: raise RuntimeError('Unexpected owned process group')
    try: os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError: continue
    deadline=time.monotonic()+8
    while identity(pid)==item['start'] and time.monotonic()<deadline: time.sleep(.05)
    if identity(pid)==item['start']:
        try: os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError: pass
` + "`" + String.raw`;
  execFileSync(state.python, ['-c', stop, root], {timeout: 35000});
  async function closed(port) {
    return new Promise(resolve => {
      const socket = net.connect({host:'127.0.0.1',port});
      socket.setTimeout(300);
      socket.once('connect',()=>{socket.destroy();resolve(false);});
      socket.once('error',()=>{socket.destroy();resolve(true);});
      socket.once('timeout',()=>{socket.destroy();resolve(false);});
    });
  }
  const deadline=Date.now()+10000;
  let ports;
  do {
    ports=Object.fromEntries(await Promise.all(Object.entries(state.ports).map(async([name,port])=>[name,await closed(port)])));
    if(Object.values(ports).every(Boolean))break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }while(Date.now()<deadline);
  if(!Object.values(ports).every(Boolean))throw new Error('S15 owned service port remains open');
  fs.rmSync(root,{recursive:true,force:true});
  fs.writeFileSync(path.join(process.env.S15_EVIDENCE_DIR,'cleanup.json'),JSON.stringify({
    ok:!fs.existsSync(root),ports_closed:ports,temporary_roots_removed:!fs.existsSync(root),
    removed_roots:[root],pid_birth_identity_checked:true,
  },null,2)+'\n');
};
`;
const teardownFile = path.join(RUN_ROOT, "teardown.cjs");
if (controller) fs.writeFileSync(teardownFile, TEARDOWN, "utf8");

export default defineConfig({
  globalTeardown: teardownFile,
  testDir: "./e2e",
  testMatch: TEST_MATCH,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  outputDir: ARTIFACTS,
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(LOG_DIR, `${RUN_LABEL}-playwright.json`) }],
  ],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: WEB_ORIGIN,
    locale: "en-US",
    timezoneId: "Asia/Shanghai",
    colorScheme: "light",
    viewport: { width: 1280, height: 720 },
    acceptDownloads: true,
    serviceWorkers: "block",
    launchOptions: {
      executablePath: process.env.S15_CHROMIUM || "/home/albert/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
    },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
  },
  webServer: [
    {
      command: `bash ${shellQuote(modelScript)}`,
      url: `http://127.0.0.1:${MODEL_PORT}/health`,
      cwd: RUN_ROOT,
      timeout: 30_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
      stdout: "ignore",
      stderr: "ignore",
    },
    {
      command: `bash ${shellQuote(backendScript)}`,
      url: `${BACKEND_ORIGIN}/api/v1/subjects`,
      cwd: SOURCE_ROOT,
      timeout: 120_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 12_000 },
      stdout: "ignore",
      stderr: "ignore",
    },
    {
      command: `bash ${shellQuote(nextScript)}`,
      url: `${WEB_ORIGIN}/home`,
      cwd: path.join(SOURCE_ROOT, "web"),
      timeout: 240_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 12_000 },
      stdout: "ignore",
      stderr: "ignore",
    },
  ],
});

/**
 * Shared, presentation-only schema for reasoning capabilities.
 *
 * The backend resolves provider/model/wire and returns this safe summary in
 * LLM options and the settings payload.  The web app never re-derives levels
 * from a model name; it only renders the supplied native levels and the
 * compatibility aliases the backend publishes.
 */

export const REASONING_LEVELS = [
  "none",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
  "ultra",
] as const;

export type ReasoningLevel = (typeof REASONING_LEVELS)[number];
export type ReasoningControl = "effort" | "budget" | "toggle" | "adaptive" | "unknown";
export type ReasoningSourceKind = "provider_api" | "endpoint_api" | "official_docs";

export interface ReasoningSource {
  kind: ReasoningSourceKind;
  source_url: string;
  checked_at: string;
}

export interface ReasoningControls {
  supported: boolean | null;
  control: ReasoningControl;
  levels: ReasoningLevel[];
  can_disable: boolean | null;
  default_level: ReasoningLevel | null;
  aliases: Partial<Record<ReasoningLevel, ReasoningLevel>>;
  source?: ReasoningSource;
}

export interface ReasoningOverride {
  mode: "inherit" | "provider_default" | "effort";
  effort?: string;
}

export interface ReasoningSnapshot {
  mode: ReasoningOverride["mode"];
  requested: string | null;
  effective: string | null;
  source: string;
  control: string;
  profile_id?: string;
  model_id?: string;
}

const SOURCE_KINDS = new Set<ReasoningSourceKind>([
  "provider_api",
  "endpoint_api",
  "official_docs",
]);
const CONTROLS = new Set<ReasoningControl>([
  "effort",
  "budget",
  "toggle",
  "adaptive",
  "unknown",
]);
const LEVELS = new Set<string>(REASONING_LEVELS);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cleanUrl(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

function cleanCheckedAt(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

export function parseReasoningControls(value: unknown): ReasoningControls | undefined {
  if (!isRecord(value)) return undefined;
  const supported = value.supported;
  if (supported !== true && supported !== false && supported !== null) return undefined;
  const control = typeof value.control === "string" ? value.control : "unknown";
  if (!CONTROLS.has(control as ReasoningControl)) return undefined;
  const rawLevels = Array.isArray(value.levels) ? value.levels : [];
  const levels: ReasoningLevel[] = [];
  for (const item of rawLevels) {
    if (typeof item !== "string") return undefined;
    const token = item.trim().toLowerCase();
    if (!LEVELS.has(token) || levels.includes(token as ReasoningLevel)) return undefined;
    levels.push(token as ReasoningLevel);
  }
  const defaultRaw =
    typeof value.default_level === "string"
      ? value.default_level.trim().toLowerCase()
      : "";
  if (defaultRaw && !levels.includes(defaultRaw as ReasoningLevel)) return undefined;
  const aliases: Partial<Record<ReasoningLevel, ReasoningLevel>> = {};
  if (value.aliases !== undefined) {
    if (!isRecord(value.aliases)) return undefined;
    for (const [key, target] of Object.entries(value.aliases)) {
      if (!LEVELS.has(key) || typeof target !== "string") return undefined;
      const resolved = target.trim().toLowerCase();
      if (!levels.includes(resolved as ReasoningLevel)) return undefined;
      aliases[key as ReasoningLevel] = resolved as ReasoningLevel;
    }
  }
  let source: ReasoningSource | undefined;
  if (value.source !== undefined) {
    if (!isRecord(value.source)) return undefined;
    const kind = value.source.kind;
    const sourceUrl = cleanUrl(value.source.source_url);
    const checkedAt = cleanCheckedAt(value.source.checked_at);
    if (
      typeof kind !== "string" ||
      !SOURCE_KINDS.has(kind as ReasoningSourceKind) ||
      !sourceUrl ||
      !checkedAt
    ) {
      return undefined;
    }
    source = {
      kind: kind as ReasoningSourceKind,
      source_url: sourceUrl,
      checked_at: checkedAt,
    };
  }
  const canDisable = value.can_disable;
  if (canDisable !== true && canDisable !== false && canDisable !== null) {
    return undefined;
  }
  if (supported === false && (levels.length || defaultRaw || Object.keys(aliases).length)) {
    return undefined;
  }
  return {
    supported,
    control: control as ReasoningControl,
    levels,
    can_disable: canDisable,
    default_level: defaultRaw ? (defaultRaw as ReasoningLevel) : null,
    aliases,
    ...(source ? { source } : {}),
  };
}

export function reasoningControlsKey(
  profileId: string | null | undefined,
  modelId: string | null | undefined,
): string {
  return profileId && modelId ? `${profileId}:${modelId}` : "";
}

export function parseReasoningOverride(value: unknown): ReasoningOverride | undefined {
  if (!isRecord(value)) return undefined;
  const mode = value.mode;
  if (mode !== "inherit" && mode !== "provider_default" && mode !== "effort") {
    return undefined;
  }
  if (mode === "effort") {
    if (typeof value.effort !== "string" || !value.effort.trim()) return undefined;
    if (Object.keys(value).some((key) => key !== "mode" && key !== "effort")) {
      return undefined;
    }
    return { mode, effort: value.effort.trim().toLowerCase() };
  }
  if (value.effort !== undefined && value.effort !== null && value.effort !== "") {
    return undefined;
  }
  if (Object.keys(value).some((key) => key !== "mode" && key !== "effort")) {
    return undefined;
  }
  return { mode };
}

export const INHERIT_REASONING: ReasoningOverride = { mode: "inherit" };
export const PROVIDER_DEFAULT_REASONING: ReasoningOverride = {
  mode: "provider_default",
};

export function reasoningOverrideKey(value: ReasoningOverride | null | undefined): string {
  if (!value) return "inherit";
  return value.mode === "effort" ? `effort:${value.effort ?? ""}` : value.mode;
}

export function sameReasoningOverride(
  a: ReasoningOverride | null | undefined,
  b: ReasoningOverride | null | undefined,
): boolean {
  return reasoningOverrideKey(a) === reasoningOverrideKey(b);
}

export interface ReasoningChoice {
  value: string;
  label: string;
  override: ReasoningOverride;
  nativeLevel?: ReasoningLevel;
  mappedTo?: ReasoningLevel;
  unsupported?: boolean;
}

function levelLabel(level: string, control: ReasoningControl): string {
  const names: Record<string, string> = {
    none: "Off",
    minimal: "Minimal",
    low: "Low",
    medium: "Medium",
    high: "High",
    xhigh: "Extra high",
    max: "Max",
    ultra: "Ultra",
  };
  const base = names[level] ?? level;
  return control === "budget" ? `${base} (budget preset)` : base;
}

/** Native choices plus the two selection modes; an invalid saved value stays
 * visible so the user can recover from it. */
export function reasoningChoices(
  controls: ReasoningControls | null | undefined,
  current: ReasoningOverride = INHERIT_REASONING,
): ReasoningChoice[] {
  const choices: ReasoningChoice[] = [
    {
      value: "inherit",
      label: "Inherit model setting",
      override: INHERIT_REASONING,
    },
    {
      value: "provider_default",
      label: "Provider default",
      override: PROVIDER_DEFAULT_REASONING,
    },
  ];
  if (!controls || controls.supported !== true) return choices;
  for (const level of controls.levels) {
    choices.push({
      value: `effort:${level}`,
      label: levelLabel(level, controls.control),
      override: { mode: "effort", effort: level },
      nativeLevel: level,
    });
  }
  if (
    controls.can_disable === true &&
    !controls.levels.includes("none")
  ) {
    choices.push({
      value: "effort:none",
      label: levelLabel("none", controls.control),
      override: { mode: "effort", effort: "none" },
      nativeLevel: "none",
    });
  }
  if (current.mode === "effort" && current.effort) {
    const token = current.effort.trim().toLowerCase();
    const exists = choices.some(
      (choice) => choice.override.mode === "effort" && choice.override.effort === token,
    );
    if (!exists) {
      const target = controls.aliases[token as ReasoningLevel];
      choices.push({
        value: `effort:${token}`,
        label: target
          ? `${token} → ${levelLabel(target, controls.control)}`
          : `${token} (unsupported)`,
        override: { mode: "effort", effort: token },
        mappedTo: target,
        unsupported: !target,
      });
    }
  }
  return choices;
}

export function reasoningChoiceLabel(
  controls: ReasoningControls | null | undefined,
  current: ReasoningOverride,
): string {
  if (current.mode === "inherit") return "Inherit model setting";
  if (current.mode === "provider_default") return "Provider default";
  const token = (current.effort ?? "").trim().toLowerCase();
  if (token === "none") {
    return controls?.control === "budget" ? "Off" : levelLabel("none", "effort");
  }
  if (controls?.levels.includes(token as ReasoningLevel)) {
    return levelLabel(token, controls.control);
  }
  const target = controls?.aliases[token as ReasoningLevel];
  if (target) return `${token} → ${levelLabel(target, controls?.control ?? "effort")}`;
  return `${token || "Unknown"} (unsupported)`;
}

export function reasoningLevelIsOff(value: string | null | undefined): boolean {
  return String(value ?? "").trim().toLowerCase() === "none";
}


export interface ModelDefaultReasoningChoice {
  value: string;
  label: string;
  unsupported?: boolean;
}

/** Choices for the model's saved default. Empty string means provider default. */
export function modelDefaultReasoningChoices(
  controls: ReasoningControls | null | undefined,
  current = "",
): ModelDefaultReasoningChoice[] {
  const choices: ModelDefaultReasoningChoice[] = [
    { value: "", label: "Provider default" },
  ];
  if (!controls || controls.supported !== true) return choices;
  for (const level of controls.levels) {
    choices.push({
      value: level,
      label: levelLabel(level, controls.control),
    });
  }
  if (
    controls.can_disable === true &&
    !controls.levels.includes("none")
  ) {
    choices.push({ value: "none", label: levelLabel("none", controls.control) });
  }
  const token = current.trim().toLowerCase();
  if (
    token &&
    !choices.some((choice) => choice.value === token)
  ) {
    const target = controls.aliases[token as ReasoningLevel];
    choices.push({
      value: token,
      label: target
        ? `${token} → ${levelLabel(target, controls.control)}`
        : `${token} (unsupported)`,
      unsupported: !target,
    });
  }
  return choices;
}

/**
 * Pure normalization and draft-merge helpers for source-backed model
 * parameters.  It mirrors the Python whitelist; no arbitrary provider JSON is
 * copied and no value is invented from a model name.
 */

import type { CatalogModel, ServiceName } from "@/components/settings/SettingsContext";
import {
  parseReasoningControls,
  type ReasoningControls,
} from "@/lib/reasoning-controls";

export const METADATA_SCHEMA_VERSION = 1 as const;
export const MAX_SUPPORTED_DIMENSIONS = 128;
export const MAX_JSON_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;

export type ParameterKind = "provider_api" | "endpoint_api" | "official_docs";

export interface ParameterProvenance {
  kind: ParameterKind;
  source_url: string;
  checked_at: string;
  json_path?: string;
}

export interface ModelParameters {
  context_window?: number;
  max_input_tokens?: number;
  max_output_tokens?: number;
  max_reasoning_tokens?: number;
  default_dimensions?: number;
  supported_dimensions?: number[];
  supports_dimensions_parameter?: boolean;
  input_modalities?: string[];
  output_modalities?: string[];
  provenance?: Record<string, ParameterProvenance>;
}

export interface ProviderMetadata {
  schema_version: 1;
  parameters: ModelParameters;
  /** Per-model capability summary. Kept beside the parameters whitelist. */
  reasoning_controls?: ReasoningControls;
}

export type ParameterOverrideKey =
  | "context_window"
  | "max_tokens"
  | "dimension"
  | "send_dimensions";

export type ParameterOverrides = Partial<Record<ParameterOverrideKey, boolean>>;

const INTEGER_KEYS = [
  "context_window",
  "max_input_tokens",
  "max_output_tokens",
  "max_reasoning_tokens",
  "default_dimensions",
] as const;
const MODALITY_KEYS = ["input_modalities", "output_modalities"] as const;
const MODALITIES = new Set(["text", "image", "audio", "video"]);
const PROVENANCE_KINDS = new Set<ParameterKind>([
  "provider_api",
  "endpoint_api",
  "official_docs",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function positiveInteger(value: unknown): number | undefined {
  if (typeof value === "boolean" || value === null || value === undefined) {
    return undefined;
  }
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && /^\d+$/.test(value.trim())
        ? Number(value.trim())
        : NaN;
  if (
    !Number.isSafeInteger(parsed) ||
    parsed <= 0 ||
    parsed > MAX_JSON_SAFE_INTEGER
  ) {
    return undefined;
  }
  return parsed;
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
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function cleanModalities(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const result: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const token = item.trim().toLowerCase();
    if (MODALITIES.has(token) && !result.includes(token)) result.push(token);
  }
  return result;
}

export function parseModelParameters(value: unknown): ModelParameters | undefined {
  if (!isRecord(value)) return undefined;
  const result: ModelParameters = {};
  for (const key of INTEGER_KEYS) {
    const parsed = positiveInteger(value[key]);
    if (parsed !== undefined) result[key] = parsed;
  }
  if (Array.isArray(value.supported_dimensions)) {
    const dimensions: number[] = [];
    for (const item of value.supported_dimensions) {
      const parsed = positiveInteger(item);
      if (parsed !== undefined && !dimensions.includes(parsed)) {
        dimensions.push(parsed);
      }
    }
    if (dimensions.length) {
      result.supported_dimensions = dimensions.slice(0, MAX_SUPPORTED_DIMENSIONS);
    }
  }
  if (typeof value.supports_dimensions_parameter === "boolean") {
    result.supports_dimensions_parameter = value.supports_dimensions_parameter;
  }
  for (const key of MODALITY_KEYS) {
    const modalities = cleanModalities(value[key]);
    if (modalities.length) result[key] = modalities;
  }
  if (result.context_window === undefined) delete result.context_window;
  if (isRecord(value.provenance)) {
    const provenance: Record<string, ParameterProvenance> = {};
    for (const [key, item] of Object.entries(value.provenance)) {
      if (!(key in result) || !isRecord(item)) continue;
      const kind = item.kind;
      const sourceUrl = cleanUrl(item.source_url);
      const checkedAt = cleanCheckedAt(item.checked_at);
      if (
        typeof kind !== "string" ||
        !PROVENANCE_KINDS.has(kind as ParameterKind) ||
        !sourceUrl ||
        !checkedAt
      ) {
        continue;
      }
      const entry: ParameterProvenance = {
        kind: kind as ParameterKind,
        source_url: sourceUrl,
        checked_at: checkedAt,
      };
      if (typeof item.json_path === "string" && item.json_path.trim()) {
        entry.json_path = item.json_path.trim().slice(0, 200);
      }
      provenance[key] = entry;
    }
    if (Object.keys(provenance).length) result.provenance = provenance;
  }
  return Object.keys(result).length ? result : undefined;
}

export function parseProviderMetadata(value: unknown): ProviderMetadata | undefined {
  if (!isRecord(value) || value.schema_version !== 1) return undefined;
  const parameters = parseModelParameters(value.parameters) ?? {};
  const reasoningControls = parseReasoningControls(value.reasoning_controls);
  if (
    !Object.keys(parameters).length &&
    !reasoningControls
  ) {
    return undefined;
  }
  return {
    schema_version: 1,
    parameters,
    ...(reasoningControls ? { reasoning_controls: reasoningControls } : {}),
  };
}

export function modelOverrideFlags(
  model: Pick<
    CatalogModel,
    "context_window" | "max_tokens" | "dimension" | "send_dimensions" | "parameter_overrides"
  >,
): Required<ParameterOverrides> {
  const raw = isRecord(model.parameter_overrides)
    ? model.parameter_overrides
    : {};
  const flags = {
    context_window: raw.context_window === true,
    max_tokens: raw.max_tokens === true,
    dimension: raw.dimension === true,
    send_dimensions: raw.send_dimensions === true,
  };
  // Legacy rows have no marker: any non-empty value is a manual choice.
  if (!isRecord(model.parameter_overrides)) {
    if (positiveInteger(model.context_window) !== undefined) {
      flags.context_window = true;
    }
    if (positiveInteger(model.max_tokens) !== undefined) {
      flags.max_tokens = true;
    }
    if (positiveInteger(model.dimension) !== undefined) {
      flags.dimension = true;
    }
    if (model.send_dimensions !== undefined) flags.send_dimensions = true;
  }
  return flags;
}

function newestCheckedAt(parameters: ModelParameters): string | undefined {
  const values = Object.values(parameters.provenance ?? {})
    .map((item) => item.checked_at)
    .filter(Boolean)
    .sort();
  return values.at(-1);
}

/** Values a newly imported model gets; only called for a new internal id. */
export function initialCatalogParameters(
  service: ServiceName,
  parameters: ModelParameters | undefined,
  reasoningControls?: ReasoningControls,
): Partial<CatalogModel> {
  if (!parameters && !reasoningControls) return {};
  const metadata: ProviderMetadata = {
    schema_version: 1,
    parameters: parameters ?? {},
    ...(service === "llm" && reasoningControls
      ? { reasoning_controls: reasoningControls }
      : {}),
  };
  if (!parameters) {
    return service === "llm"
      ? {
          provider_metadata: metadata,
          parameter_overrides: { context_window: false, max_tokens: false },
        }
      : {};
  }
  if (service === "llm") {
    const updates: Partial<CatalogModel> = {
      provider_metadata: metadata,
      parameter_overrides: { context_window: false, max_tokens: false },
    };
    if (parameters.context_window) {
      updates.context_window = String(parameters.context_window);
      updates.context_window_source = "official";
      updates.context_window_detected_at = newestCheckedAt(parameters);
    }
    if (parameters.max_output_tokens) {
      updates.max_tokens = String(parameters.max_output_tokens);
    }
    if (parameters.max_input_tokens) {
      updates.max_input_tokens = String(parameters.max_input_tokens);
    }
    return updates;
  }
  if (service === "embedding") {
    const updates: Partial<CatalogModel> = {
      provider_metadata: metadata,
      parameter_overrides: { dimension: false, send_dimensions: false },
    };
    if (parameters.default_dimensions) {
      updates.dimension = String(parameters.default_dimensions);
    }
    if (parameters.supported_dimensions?.length) {
      updates.supported_dimensions = parameters.supported_dimensions.join(",");
    }
    if (parameters.supports_dimensions_parameter === true) {
      updates.send_dimensions = true;
    } else if (parameters.supports_dimensions_parameter === false) {
      updates.send_dimensions = false;
    }
    return updates;
  }
  return {};
}

export interface ParameterChange {
  field: "context_window" | "max_tokens" | "dimension";
  from: number | undefined;
  to: number | undefined;
}

export interface ParameterPreview {
  changes: ParameterChange[];
  updates: Partial<CatalogModel>;
  overrides: Required<ParameterOverrides>;
}

/** Difference preview for the explicit "update official parameters" action. */
export function previewParameterUpdate(args: {
  existing: CatalogModel;
  parameters: ModelParameters | undefined;
  service: ServiceName;
  restoreAuto?: ParameterOverrideKey[];
  reasoningControls?: ReasoningControls;
}): ParameterPreview {
  const flags = modelOverrideFlags(args.existing);
  const values = args.parameters ?? {};
  const changes: ParameterChange[] = [];
  const updates: Partial<CatalogModel> = {};
  if (
    (!args.parameters && !args.reasoningControls) ||
    !["llm", "embedding"].includes(args.service)
  ) {
    return { changes, updates, overrides: flags };
  }
  const restore = new Set(args.restoreAuto ?? []);
  const nextFlags = { ...flags };
  const fields = args.service === "llm"
    ? [["context_window", "context_window"], ["max_tokens", "max_output_tokens"]] as const
    : [["dimension", "default_dimensions"]] as const;
  for (const [field, parameter] of fields) {
    const desired = values[parameter];
    if (!desired || (flags[field] && !restore.has(field))) continue;
    const current = positiveInteger(args.existing[field]);
    if (current !== desired) {
      changes.push({ field, from: current, to: desired });
      updates[field] = String(desired);
    }
    if (restore.has(field)) nextFlags[field] = false;
    if (field === "context_window") {
      updates.context_window_source = "official";
      updates.context_window_detected_at = args.parameters
        ? newestCheckedAt(args.parameters)
        : undefined;
    }
  }
  if (args.service === "llm" && values.max_input_tokens) {
    updates.max_input_tokens = String(values.max_input_tokens);
  }
  if (args.service === "embedding") {
    if (values.supported_dimensions?.length) {
      updates.supported_dimensions = values.supported_dimensions.join(",");
    }
    if (typeof values.supports_dimensions_parameter === "boolean" &&
        (!flags.send_dimensions || restore.has("send_dimensions"))) {
      updates.send_dimensions = values.supports_dimensions_parameter;
      if (restore.has("send_dimensions")) nextFlags.send_dimensions = false;
    }
  }
  updates.provider_metadata = {
    schema_version: 1,
    parameters: values ?? {},
    ...(args.service === "llm" && args.reasoningControls
      ? { reasoning_controls: args.reasoningControls }
      : {}),
  };
  updates.parameter_overrides = nextFlags;
  // Stable object comparison prevents cache serialization order from making a
  // no-op metadata refresh look like a change.
  const stable = (value: unknown): string | undefined => JSON.stringify(value, (_key, item) => {
    if (isRecord(item)) return Object.fromEntries(Object.keys(item).sort().map((key) => [key, item[key]]));
    return item;
  });
  for (const key of Object.keys(updates) as (keyof CatalogModel)[]) {
    if (stable(updates[key]) === stable(args.existing[key])) delete updates[key];
  }
  return { changes, updates, overrides: flags };
}

export function parameterSourceLabel(
  parameters: ModelParameters | undefined,
  field: string,
): string {
  const item = parameters?.provenance?.[field];
  if (!item) return "";
  if (item.kind === "provider_api") return "Provider API";
  if (item.kind === "endpoint_api") return "Endpoint";
  return "Official docs";
}

/**
 * Shared, presentation-only types and pure helpers for model discovery.
 *
 * This module performs no IO.  Candidates are provider model ids, while a
 * CatalogModel's `id` is the project's stable internal id; the merge helper
 * keeps those two identities separate and never rewrites an existing entry.
 */

import type { CatalogModel, CatalogProfile, ServiceName } from "@/components/settings/SettingsContext";
import {
  initialCatalogParameters,
  parseModelParameters,
  type ModelParameters,
} from "@/lib/model-metadata";
import {
  parseReasoningControls,
  type ReasoningControls,
} from "@/lib/reasoning-controls";

export const DISCOVERY_SERVICES = [
  "llm",
  "embedding",
  "stt",
  "tts",
  "imagegen",
  "videogen",
  "vision",
] as const;

export type DiscoveryService = (typeof DISCOVERY_SERVICES)[number];

export type DiscoveryStatus = "ok" | "empty" | "unsupported" | "error";
export type DiscoveryCacheState = "miss" | "fresh" | "stale" | "none";
export type DiscoveryClassification = "provider" | "curated" | "unknown";
export type DiscoveryCompatibility = "supported" | "unsupported" | "unknown";
export type DiscoverySource = "remote" | "preset";

export interface DiscoveryError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface DiscoveryModel {
  id: string;
  name: string;
  services: DiscoveryService[];
  classification: DiscoveryClassification;
  runtime_compatibility: DiscoveryCompatibility;
  reason_code: string | null;
  source: DiscoverySource;
  callability: "not_tested";
  context_window?: number;
  metadata_schema_version?: 1;
  parameters?: ModelParameters;
  reasoning_controls?: ReasoningControls;
  resource_name?: string;
  deployment_mapping_required?: boolean;
}

export interface DiscoveryCacheInfo {
  state: DiscoveryCacheState;
  fetched_at: string | null;
  expires_at: string | null;
}

export interface DiscoveryResponse {
  schema_version: 1;
  service: DiscoveryService;
  profile_id: string | null;
  status: DiscoveryStatus;
  models: DiscoveryModel[];
  cache: DiscoveryCacheInfo;
  complete: boolean;
  error: DiscoveryError | null;
}

export interface DiscoveryConnection {
  binding?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  api_version?: string | null;
  extra_headers?: Record<string, string> | string | null;
  model_directory_url?: string | null;
}

export type DiscoveryMode = "cache_first" | "refresh";

export interface ModelIdFactory {
  (): string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function allowed<T extends string>(value: unknown, values: readonly T[], fallback: T): T {
  return typeof value === "string" && (values as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

function cleanModelId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const id = value.trim();
  if (!id || id.length > 512 || /[\u0000-\u001f\u007f]/.test(id)) return null;
  return id;
}

function cleanName(value: unknown, fallback: string): string {
  const name = typeof value === "string" ? value.replace(/[\u0000-\u001f\u007f]/g, "").trim() : "";
  return (name || fallback).slice(0, 256);
}

export function parseDiscoveryModel(value: unknown): DiscoveryModel | null {
  if (!isRecord(value)) return null;
  const id = cleanModelId(value.id);
  if (!id) return null;
  const rawServices = Array.isArray(value.services) ? value.services : [];
  const services = rawServices.filter(
    (item): item is DiscoveryService =>
      typeof item === "string" && (DISCOVERY_SERVICES as readonly string[]).includes(item),
  );
  const runtime = allowed<DiscoveryCompatibility>(
    value.runtime_compatibility,
    ["supported", "unsupported", "unknown"],
    "unknown",
  );
  const parameters = parseModelParameters(value.parameters);
  const reasoningControls = parseReasoningControls(value.reasoning_controls);
  const context =
    parameters?.context_window ??
    (typeof value.context_window === "number" &&
    Number.isInteger(value.context_window) &&
    value.context_window > 0
      ? value.context_window
      : undefined);
  return {
    id,
    name: cleanName(value.name, id),
    services,
    classification: allowed<DiscoveryClassification>(
      value.classification,
      ["provider", "curated", "unknown"],
      "unknown",
    ),
    runtime_compatibility: runtime,
    reason_code: typeof value.reason_code === "string" ? value.reason_code : null,
    source: allowed<DiscoverySource>(value.source, ["remote", "preset"], "remote"),
    callability: "not_tested",
    ...(context ? { context_window: context } : {}),
    ...(parameters ? { metadata_schema_version: 1 as const, parameters } : {}),
    ...(reasoningControls
      ? { metadata_schema_version: 1 as const, reasoning_controls: reasoningControls }
      : {}),
    ...(typeof value.resource_name === "string" && value.resource_name
      ? { resource_name: value.resource_name }
      : {}),
    ...(value.deployment_mapping_required === true
      ? { deployment_mapping_required: true }
      : {}),
  };
}

export function parseDiscoveryResponse(value: unknown): DiscoveryResponse {
  if (!isRecord(value)) throw new Error("模型目录响应格式无效。");
  if (value.schema_version !== 1) throw new Error("模型目录响应版本不受支持。");
  const service = allowed<DiscoveryService>(
    value.service,
    DISCOVERY_SERVICES,
    "llm",
  );
  if (value.service !== service) throw new Error("模型目录响应的服务类别无效。");
  const rawModels = Array.isArray(value.models) ? value.models : [];
  const models = rawModels
    .map(parseDiscoveryModel)
    .filter((item): item is DiscoveryModel => item !== null);
  if (models.length !== rawModels.length) {
    throw new Error("模型目录包含无效条目。");
  }
  const cacheValue = isRecord(value.cache) ? value.cache : {};
  const errorValue = isRecord(value.error) ? value.error : null;
  return {
    schema_version: 1,
    service,
    profile_id: typeof value.profile_id === "string" ? value.profile_id : null,
    status: allowed<DiscoveryStatus>(
      value.status,
      ["ok", "empty", "unsupported", "error"],
      "error",
    ),
    models,
    cache: {
      state: allowed<DiscoveryCacheState>(
        cacheValue.state,
        ["miss", "fresh", "stale", "none"],
        "none",
      ),
      fetched_at: typeof cacheValue.fetched_at === "string" ? cacheValue.fetched_at : null,
      expires_at: typeof cacheValue.expires_at === "string" ? cacheValue.expires_at : null,
    },
    complete: value.complete === true,
    error: errorValue
      ? {
          code: text(errorValue.code) || "UNAVAILABLE",
          message: text(errorValue.message) || "目录查询失败。",
          retryable: errorValue.retryable === true,
        }
      : null,
  };
}

export function isDiscoveryService(value: ServiceName): value is DiscoveryService {
  return value !== "search" && (DISCOVERY_SERVICES as readonly string[]).includes(value);
}

export function requiresUnknownConfirmation(
  model: Pick<DiscoveryModel, "classification" | "runtime_compatibility">,
): boolean {
  return (
    model.classification === "unknown" ||
    model.runtime_compatibility === "unknown"
  );
}

export function canAddCandidate(
  model: Pick<DiscoveryModel, "classification" | "runtime_compatibility" | "services">,
  service: DiscoveryService,
  confirmed: boolean,
): boolean {
  if (model.runtime_compatibility === "unsupported") return false;
  if (model.services.length > 0 && !model.services.includes(service)) return false;
  return !requiresUnknownConfirmation(model) || confirmed;
}

export function candidateGroup(
  model: Pick<DiscoveryModel, "classification" | "runtime_compatibility">,
): "available" | "unknown" | "unsupported" {
  if (model.runtime_compatibility === "unsupported") return "unsupported";
  if (requiresUnknownConfirmation(model)) return "unknown";
  return "available";
}

export function filterCandidates(
  models: readonly DiscoveryModel[],
  query: string,
  filter: "all" | "available" | "unknown" | "unsupported",
): DiscoveryModel[] {
  const needle = query.trim().toLowerCase();
  return models.filter((model) => {
    if (filter !== "all" && candidateGroup(model) !== filter) return false;
    if (!needle) return true;
    return (
      model.id.toLowerCase().includes(needle) ||
      model.name.toLowerCase().includes(needle)
    );
  });
}

/** The browser never persists this value; it is an in-memory stale-response guard. */
export function connectionIdentity(
  profile: Pick<
    CatalogProfile,
    | "id"
    | "binding"
    | "base_url"
    | "api_key"
    | "api_version"
    | "extra_headers"
    | "model_directory_url"
  > | null,
): string {
  if (!profile) return "";
  let headers = "";
  if (typeof profile.extra_headers === "string") {
    headers = profile.extra_headers;
  } else if (profile.extra_headers && typeof profile.extra_headers === "object") {
    headers = JSON.stringify(
      Object.entries(profile.extra_headers).sort(([a], [b]) => a.localeCompare(b)),
    );
  }
  return JSON.stringify([
    profile.id,
    profile.binding ?? "",
    profile.base_url ?? "",
    profile.api_key ?? "",
    profile.api_version ?? "",
    profile.model_directory_url ?? "",
    headers,
  ]);
}

export function autoDiscoveryAllowed(
  profile: CatalogProfile | null,
  savedProfile: CatalogProfile | null,
): boolean {
  if (!profile || !savedProfile) return false;
  if (profile.id !== savedProfile.id) return false;
  if (profile.read_only || profile.managed_by) return false;
  const binding = (profile.binding ?? "").trim().toLowerCase().replaceAll("-", "_");
  if (["codebuddy", "codebuddy_code", "workbuddy", "openai_codex", "codex"].includes(binding)) return false;
  return Boolean((profile.binding ?? "").trim() && (profile.base_url ?? "").trim());
}

// Two saved snapshots can both contain *** while representing different
// credentials. Give each snapshot an opaque in-memory revision. StrictMode
// reuses the same object; a successful save provides a new one.
const SAVED_CONNECTION_REVISIONS = new WeakMap<object, number>();
let nextSavedConnectionRevision = 0;
export function savedConnectionRevision(profile: CatalogProfile | null): number {
  if (!profile) return 0;
  let revision = SAVED_CONNECTION_REVISIONS.get(profile);
  if (revision === undefined) {
    revision = ++nextSavedConnectionRevision;
    SAVED_CONNECTION_REVISIONS.set(profile, revision);
  }
  return revision;
}

export function defaultModelIdFactory(service: DiscoveryService): ModelIdFactory {
  return () => {
    const cryptoObject = globalThis.crypto;
    const uuid =
      cryptoObject && typeof cryptoObject.randomUUID === "function"
        ? cryptoObject.randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    return `${service}-model-${uuid}`;
  };
}

export interface MergeCandidatesResult {
  models: CatalogModel[];
  addedIds: string[];
  reusedIds: string[];
}

/** Merge only selected candidates into a copy of one profile's model list. */
export function mergeDiscoveredModels(args: {
  existing: readonly CatalogModel[];
  candidates: readonly DiscoveryModel[];
  selectedIds: Iterable<string>;
  confirmedUnknownIds?: Iterable<string>;
  service: DiscoveryService;
  idFactory?: ModelIdFactory;
}): MergeCandidatesResult {
  const {
    existing,
    candidates,
    selectedIds,
    confirmedUnknownIds = [],
    service,
    idFactory = defaultModelIdFactory(service),
  } = args;
  const selected = new Set(selectedIds);
  const confirmed = new Set(confirmedUnknownIds);
  const models = existing.map((model) => ({ ...model }));
  const byModel = new Map<string, string>();
  const usedIds = new Set(models.map((model) => model.id));
  for (const model of models) {
    if (typeof model.model === "string" && model.model && !byModel.has(model.model)) {
      byModel.set(model.model, model.id);
    }
  }
  const addedIds: string[] = [];
  const reusedIds: string[] = [];
  for (const candidate of candidates) {
    if (!selected.has(candidate.id)) continue;
    if (!canAddCandidate(candidate, service, confirmed.has(candidate.id))) continue;
    const reused = byModel.get(candidate.id);
    if (reused) {
      reusedIds.push(reused);
      continue;
    }
    let internalId = "";
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const proposal = idFactory();
      if (proposal && !usedIds.has(proposal)) {
        internalId = proposal;
        break;
      }
    }
    if (!internalId) continue;
    usedIds.add(internalId);
    byModel.set(candidate.id, internalId);
    const defaults = initialCatalogParameters(
      service,
      candidate.parameters,
      candidate.reasoning_controls,
    );
    models.push({
      id: internalId,
      name: candidate.name,
      model: candidate.id,
      ...defaults,
    });
    addedIds.push(internalId);
  }
  return { models, addedIds, reusedIds };
}

export function modelVisibleInPicker(
  model: Pick<CatalogModel, "visible_in_picker"> | null | undefined,
): boolean {
  return model?.visible_in_picker !== false;
}

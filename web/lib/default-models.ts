import type {
  Catalog,
  DefaultModelReference,
  DefaultModelReferenceMap,
  ServiceName,
} from "@/components/settings/SettingsContext";
import type { ProviderIconSpec } from "@/lib/custom-providers";

export const DEFAULT_MODEL_SERVICES = [
  "llm",
  "embedding",
  "search",
  "stt",
  "tts",
  "vision",
  "imagegen",
  "videogen",
] as const;

export type DefaultModelService = (typeof DEFAULT_MODEL_SERVICES)[number];

export interface DefaultOptionModel {
  model_id: string;
  model_name: string;
  hidden?: boolean;
}

export interface DefaultProfileOption {
  profile_id: string;
  profile_name: string;
  provider: string;
  provider_label: string;
  provider_icon?: ProviderIconSpec | null;
  custom_provider_id?: string | null;
  models: DefaultOptionModel[];
}

export interface DefaultServiceOptions {
  kind: "model" | "profile";
  profiles: DefaultProfileOption[];
}

export interface DefaultModelsResponse {
  revision: string;
  defaults: DefaultModelReferenceMap;
  services: Record<DefaultModelService, DefaultServiceOptions>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function parseDefaultModelsResponse(value: unknown): DefaultModelsResponse {
  if (!isRecord(value) || typeof value.revision !== "string" || !value.revision) {
    throw new Error("Default models response is missing a revision.");
  }
  const defaults: DefaultModelReferenceMap = {};
  if (isRecord(value.defaults)) {
    for (const service of DEFAULT_MODEL_SERVICES) {
      const item = value.defaults[service];
      if (isRecord(item) && text(item.profile_id).trim()) {
        defaults[service] = {
          profile_id: text(item.profile_id).trim(),
          ...(text(item.model_id).trim()
            ? { model_id: text(item.model_id).trim() }
            : {}),
        };
      } else {
        defaults[service] = null;
      }
    }
  }
  const services = {} as Record<DefaultModelService, DefaultServiceOptions>;
  for (const service of DEFAULT_MODEL_SERVICES) {
    const rawService = isRecord(value.services) && isRecord(value.services[service])
      ? (value.services[service] as Record<string, unknown>)
      : {};
    const rawProfiles = Array.isArray(rawService.profiles)
      ? rawService.profiles
      : [];
    const profiles: DefaultProfileOption[] = [];
    for (const rawProfile of rawProfiles) {
      if (!isRecord(rawProfile) || !text(rawProfile.profile_id).trim()) continue;
      const models = Array.isArray(rawProfile.models)
        ? rawProfile.models
            .filter(
              (item): item is Record<string, unknown> =>
                isRecord(item) && Boolean(text(item.model_id).trim()),
            )
            .map((item) => ({
              model_id: text(item.model_id).trim(),
              model_name:
                text(item.model_name).trim() || text(item.model_id).trim(),
              hidden: item.hidden === true,
            }))
        : [];
      profiles.push({
        profile_id: text(rawProfile.profile_id).trim(),
        profile_name:
          text(rawProfile.profile_name).trim() || text(rawProfile.profile_id).trim(),
        provider: text(rawProfile.provider),
        provider_label: text(rawProfile.provider_label) || text(rawProfile.provider),
        provider_icon:
          isRecord(rawProfile.provider_icon) &&
          (rawProfile.provider_icon.kind === "builtin" ||
            rawProfile.provider_icon.kind === "emoji")
            ? (rawProfile.provider_icon as ProviderIconSpec)
            : null,
        custom_provider_id: text(rawProfile.custom_provider_id) || null,
        models,
      });
    }
    services[service] = {
      kind: service === "search" ? "profile" : "model",
      profiles,
    };
  }
  return { revision: value.revision, defaults, services };
}

export function defaultReferenceKey(
  reference: DefaultModelReference | null | undefined,
): string {
  if (!reference?.profile_id) return "";
  return `${reference.profile_id}\u0000${reference.model_id ?? ""}`;
}

export function sameDefaultReference(
  a: DefaultModelReference | null | undefined,
  b: DefaultModelReference | null | undefined,
): boolean {
  return (
    (a?.profile_id ?? "") === (b?.profile_id ?? "") &&
    (a?.model_id ?? "") === (b?.model_id ?? "")
  );
}

/** A reference-only PATCH cannot certify the rest of an older local draft.
 * Keep its old revision so a later full save conflicts instead of overwriting
 * another window's edits that this SettingsProvider has never loaded. */
export function revisionAfterDefaultPatch(
  localRevision: string | null,
  patchBaseRevision: string,
  savedRevision: string,
): string | null {
  return localRevision === patchBaseRevision ? savedRevision : localRevision;
}

export function changedDefaultReferences(
  saved: DefaultModelReferenceMap,
  selected: DefaultModelReferenceMap,
): Partial<Record<ServiceName, DefaultModelReference>> {
  const changed: Partial<Record<ServiceName, DefaultModelReference>> = {};
  for (const service of DEFAULT_MODEL_SERVICES) {
    const next = selected[service];
    if (!next || sameDefaultReference(saved[service], next)) continue;
    changed[service] = next;
  }
  return changed;
}

/** Merge only the active references; every other saved/draft field is kept. */
export function mergeDefaultReferences(
  catalog: Catalog,
  references: DefaultModelReferenceMap,
): Catalog {
  const next = JSON.parse(JSON.stringify(catalog)) as Catalog;
  for (const service of DEFAULT_MODEL_SERVICES) {
    const reference = references[service];
    if (!reference) continue;
    next.services[service].active_profile_id = reference.profile_id;
    if (service !== "search") {
      next.services[service].active_model_id = reference.model_id ?? null;
    }
  }
  return next;
}

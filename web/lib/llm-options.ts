import { apiFetch, apiUrl } from "@/lib/api";
import { invalidateClientCache, withClientCache } from "@/lib/client-cache";
import type { LLMSelection } from "@/lib/unified-ws";
import type { ReasoningControls } from "@/lib/reasoning-controls";
import type { ProviderIconSpec } from "@/lib/custom-providers";

const LLM_OPTIONS_CACHE_KEY = "llm-options:list";
const DEFAULT_LLM_OPTIONS_TIMEOUT_MS = 30_000;
let llmOptionsGeneration = 0;

export interface LLMOption extends LLMSelection {
  profile_name: string;
  model_name: string;
  model: string;
  provider: string;
  /** Human-readable provider name from the registry or a named custom provider. */
  provider_label?: string;
  /** Presentation metadata only; never sent to a provider. */
  provider_icon?: ProviderIconSpec | null;
  custom_provider_id?: string | null;
  context_window?: number;
  is_active_default: boolean;
  /** Presentation metadata; omitted means visible. */
  visible_in_picker?: boolean;
  /** Set only on entries returned through hidden_options. */
  hidden?: boolean;
  /** Safe backend policy; omitted/unknown means no invented levels. */
  reasoning_controls?: ReasoningControls;
}

export interface LLMOptionsResponse {
  active: LLMSelection | null;
  options: LLMOption[];
  /** Authorized models hidden from the new-selection list. */
  hidden_options?: LLMOption[];
  /** Computed before display filtering; hiding never revokes access. */
  has_usable_models?: boolean;
}

/** Compute capability access before display filtering; hidden is not revoked. */
export function hasUsableLLMModels(payload: LLMOptionsResponse): boolean {
  if (typeof payload.has_usable_models === "boolean") {
    return payload.has_usable_models;
  }
  return (
    payload.options.length + (payload.hidden_options?.length ?? 0) > 0
  );
}

/** User-facing name: a non-empty custom name wins, otherwise the call ID. */
export function llmOptionLabel(
  option: Pick<LLMOption, "model_name" | "model"> | null | undefined,
): string {
  if (!option) return "";
  return (option.model_name || "").trim() || option.model || "";
}

/** Full identity for hover text; keeps the real call ID visible after rename. */
export function llmOptionTitle(
  option: Pick<
    LLMOption,
    "model_name" | "model" | "profile_name" | "provider_label" | "provider"
  >,
): string {
  const parts = [
    llmOptionLabel(option),
    option.model,
    option.profile_name,
    option.provider_label || option.provider,
  ].filter((value, index, all) => Boolean(value) && all.indexOf(value) === index);
  return parts.join(" | ");
}

export function llmSelectionKey(selection: LLMSelection | null | undefined) {
  if (!selection?.profile_id || !selection.model_id) return "";
  return `${selection.profile_id}:${selection.model_id}`;
}

export function sameLLMSelection(
  a: LLMSelection | null | undefined,
  b: LLMSelection | null | undefined,
) {
  return llmSelectionKey(a) === llmSelectionKey(b);
}

/** List the configured model profiles.
 *
 *  Cached so the many consumers that need the model list (composer, model
 *  picker, capability gate, partner forms) share one round-trip instead of
 *  each firing their own on mount. Editing a profile calls
 *  ``invalidateLLMOptionsCache``; pass ``force`` to bypass the cache. */
export async function listLLMOptions(options?: {
  force?: boolean;
  timeoutMs?: number;
}): Promise<LLMOptionsResponse> {
  const generation = llmOptionsGeneration;
  return withClientCache<LLMOptionsResponse>(
    LLM_OPTIONS_CACHE_KEY,
    async () => {
      const controller = new AbortController();
      const timeout = setTimeout(
        () => controller.abort(),
        options?.timeoutMs ?? DEFAULT_LLM_OPTIONS_TIMEOUT_MS,
      );
      try {
        const response = await apiFetch(
          apiUrl("/api/v1/settings/llm-options"),
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );
        if (!response.ok) {
          throw new Error(`Failed to load LLM options: ${response.status}`);
        }
        const data = (await response.json()) as LLMOptionsResponse & {
          hidden_options?: unknown;
          has_usable_models?: unknown;
        };
        const rawOptions = Array.isArray(data.options) ? data.options : [];
        const explicitHidden = Array.isArray(data.hidden_options)
          ? (data.hidden_options as LLMOption[])
          : [];
        const hiddenIds = new Set(
          explicitHidden.map((option) => llmSelectionKey(option)),
        );
        const options = rawOptions.filter(
          (option) =>
            option.visible_in_picker !== false &&
            !hiddenIds.has(llmSelectionKey(option)),
        );
        const derivedHidden = rawOptions
          .filter(
            (option) =>
              option.visible_in_picker === false &&
              !hiddenIds.has(llmSelectionKey(option)),
          )
          .map((option) => ({ ...option, hidden: true }));
        const hiddenOptions = [
          ...explicitHidden.map((option) => ({ ...option, hidden: true })),
          ...derivedHidden,
        ];
        const result: LLMOptionsResponse = {
          active: data.active ?? null,
          options,
        };
        if (
          "hidden_options" in data ||
          "has_usable_models" in data ||
          hiddenOptions.length > 0
        ) {
          result.hidden_options = hiddenOptions;
          result.has_usable_models =
            typeof data.has_usable_models === "boolean"
              ? data.has_usable_models
              : rawOptions.length > 0 || explicitHidden.length > 0;
        }
        return result;
      } finally {
        clearTimeout(timeout);
      }
    },
    {
      force: options?.force,
      guard: () => generation === llmOptionsGeneration,
    },
  );
}

export function invalidateLLMOptionsCache(): void {
  // Bump first: an in-flight response belongs to the superseded generation.
  llmOptionsGeneration += 1;
  invalidateClientCache(LLM_OPTIONS_CACHE_KEY);
}

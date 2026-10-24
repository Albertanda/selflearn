"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Database,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import {
  resolveProviderPresentation,
  type CustomProviderService,
} from "@/lib/custom-providers";
import { useSettings, type CatalogProfile } from "./SettingsContext";
import {
  candidateGroup,
  filterCandidates,
  requiresUnknownConfirmation,
  type DiscoveryModel,
  type DiscoveryService,
} from "@/lib/model-discovery";
import { parameterSourceLabel } from "@/lib/model-metadata";
import type { ModelDiscoveryState } from "@/lib/model-discovery-state";

const SERVICE_LABEL: Record<DiscoveryService, string> = {
  llm: "LLM",
  embedding: "Embedding",
  stt: "Speech-to-Text",
  tts: "Text-to-Speech",
  imagegen: "Image Generation",
  videogen: "Video Generation",
  vision: "Vision",
};

function formatWhen(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function reasonKey(reason: string | null): string {
  switch (reason) {
    case "realtime_protocol_unsupported":
      return "Realtime protocols are not supported by this build.";
    case "aliyun_filetrans_protocol_unsupported":
      return "Filetrans uses a different protocol and is not supported here.";
    case "aliyun_fun_asr_protocol_unsupported":
      return "Fun-ASR uses a protocol this build does not implement.";
    case "aliyun_stt_adapter_not_implemented":
      return "This speech model does not have an implemented adapter yet.";
    case "aliyun_tts_adapter_not_implemented":
      return "Aliyun TTS is not implemented in this build.";
    case "aliyun_imagegen_adapter_not_implemented":
      return "Aliyun image generation is not implemented in this build.";
    case "aliyun_videogen_adapter_not_implemented":
      return "Aliyun video generation is not implemented in this build.";
    case "aliyun_vision_model_unverified":
      return "This model's multimodal behavior is not verified for this build.";
    case "aliyun_embedding_model_unverified":
      return "This embedding family is not verified for this build.";
    case "third_party_inference_routing":
      return "A third-party inference provider is listed; the current Aliyun endpoint may not serve it.";
    case "category_unconfirmed":
      return "The provider does not declare a category. Confirm this model is for the current use.";
    case "ollama_capability_not_exposed":
      return "Ollama exposes no capability metadata for this entry.";
    case "siliconflow_tts_model_unverified":
      return "This SiliconFlow TTS model is not verified for this build.";
    case "siliconflow_vision_capability_not_exposed":
      return "SiliconFlow does not expose a vision filter; category is unconfirmed.";
    case "video_adapter_not_available":
      return "Video generation is not implemented for this provider.";
    case "azure_deployment_mapping_required":
      return "This is a base offering, not a deployment name. Enter the deployment name before calling it.";
    case "gemini_generate_content_category_unverified":
      return "generateContent is also used for non-chat models; confirm this is a text chat model.";
    case "gemini_vision_capability_not_exposed":
      return "The directory does not declare image input for this model.";
    case "anthropic_vision_capability_not_exposed":
      return "The directory does not declare image input for this model.";
    case "anthropic_image_input_unsupported":
      return "This model does not accept image input.";
    default:
      return reason || "";
  }
}

export function ModelDiscoveryDialog({
  open,
  onClose,
  service,
  profile,
  state,
  onQuery,
  onRefresh,
  onRetry,
  onAddSelected,
}: {
  open: boolean;
  onClose: () => void;
  service: DiscoveryService;
  profile: CatalogProfile | null;
  state: ModelDiscoveryState;
  onQuery: () => void;
  onRefresh: () => void;
  onRetry: () => void;
  onAddSelected: (ids: string[], confirmed: string[]) => void;
}) {
  const { t } = useTranslation();
  const { draft } = useSettings();
  const presentation = profile
    ? resolveProviderPresentation(
        draft,
        service as CustomProviderService,
        profile,
        SERVICE_LABEL[service],
      )
    : null;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<
    "all" | "available" | "unknown" | "unsupported"
  >("all");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [confirmed, setConfirmed] = useState<Set<string>>(() => new Set());
  const resetKey = `${open}:${profile?.id ?? ""}`;
  const [lastResetKey, setLastResetKey] = useState(resetKey);
  if (lastResetKey !== resetKey) {
    setLastResetKey(resetKey);
    setQuery("");
    setFilter("all");
    setSelected(new Set());
    setConfirmed(new Set());
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const models = useMemo(() => state.response?.models ?? [], [state.response]);
  const visible = useMemo(
    () => filterCandidates(models, query, filter),
    [models, query, filter],
  );
  const groups = useMemo(
    () => ({
      available: visible.filter((model) => candidateGroup(model) === "available"),
      unknown: visible.filter((model) => candidateGroup(model) === "unknown"),
      unsupported: visible.filter((model) => candidateGroup(model) === "unsupported"),
    }),
    [visible],
  );
  const selectable = models.filter(
    (model) =>
      model.runtime_compatibility !== "unsupported" &&
      (!requiresUnknownConfirmation(model) || confirmed.has(model.id)),
  );
  const selectedCount = selectable.filter((model) => selected.has(model.id)).length;

  if (!open) return null;

  const toggleSelected = (model: DiscoveryModel) => {
    if (!selectable.some((item) => item.id === model.id)) return;
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(model.id)) next.delete(model.id);
      else next.add(model.id);
      return next;
    });
  };

  const toggleConfirmed = (model: DiscoveryModel) => {
    const wasConfirmed = confirmed.has(model.id);
    setConfirmed((current) => {
      const next = new Set(current);
      if (next.has(model.id)) next.delete(model.id);
      else next.add(model.id);
      return next;
    });
    if (wasConfirmed) {
      setSelected((current) => {
        const next = new Set(current);
        next.delete(model.id);
        return next;
      });
    }
  };

  const renderRow = (model: DiscoveryModel, group: "available" | "unknown" | "unsupported") => {
    const isUnsupported = group === "unsupported";
    const needsConfirmation = group === "unknown";
    const isConfirmed = confirmed.has(model.id);
    const isSelected = selected.has(model.id);
    const reason = reasonKey(model.reason_code);
    return (
      <div
        key={model.id}
        data-testid="model-discovery-row"
        data-model-id={model.id}
        data-group={group}
        className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
          isSelected
            ? "border-[var(--ring)] bg-[var(--muted)]/40"
            : "border-[var(--border)]/60"
        }`}
      >
        <input
          type="checkbox"
          className="mt-1 h-3.5 w-3.5 shrink-0 accent-[var(--foreground)] disabled:opacity-30"
          checked={isSelected}
          disabled={isUnsupported || (needsConfirmation && !isConfirmed)}
          onChange={() => toggleSelected(model)}
          aria-label={t("Select {{name}}", { name: model.name || model.id })}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-[12.5px] font-medium text-[var(--foreground)]">
              {model.name || model.id}
            </span>
            <span className="rounded-full bg-[var(--muted)] px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              {model.source === "preset" ? t("Preset") : t("Account directory")}
            </span>
            {model.classification === "unknown" ? (
              <span className="rounded-full bg-amber-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
                {t("Type unconfirmed")}
              </span>
            ) : null}
            {model.deployment_mapping_required ? (
              <span className="rounded-full bg-amber-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
                {t("Deployment name required")}
              </span>
            ) : null}
            {model.runtime_compatibility === "unsupported" ? (
              <span className="rounded-full bg-red-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-red-500">
                {t("Unsupported")}
              </span>
            ) : null}
            {model.source === "remote" &&
            model.classification !== "unknown" &&
            model.runtime_compatibility === "supported" ? (
              <span className="rounded-full bg-emerald-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
                {t("Compatible")}
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 break-all font-mono text-[11px] text-[var(--muted-foreground)]">
            {model.id}
          </div>
          {reason ? (
            <div className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
              {t(reason)}
            </div>
          ) : null}
          {needsConfirmation ? (
            <button
              type="button"
              onClick={() => toggleConfirmed(model)}
              className={`mt-1.5 inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10.5px] transition-colors ${
                isConfirmed
                  ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                  : "border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--foreground)]"
              }`}
            >
              {isConfirmed ? <Check className="h-3 w-3" /> : null}
              {isConfirmed
                ? t("Confirmed for this category")
                : t("Confirm for this category")}
            </button>
          ) : null}
          {typeof model.context_window === "number" && model.context_window > 0 ? (
            <div className="mt-1 text-[10.5px] text-[var(--muted-foreground)]/80">
              {t("Context window")}: {model.context_window.toLocaleString()}
              {model.parameters
                ? ` · ${t(parameterSourceLabel(model.parameters, "context_window"))}`
                : ""}
            </div>
          ) : null}
          {model.parameters?.max_input_tokens ? (
            <div className="mt-0.5 text-[10.5px] text-[var(--muted-foreground)]/80">
              {t("Input limit")}:{" "}
              {model.parameters.max_input_tokens.toLocaleString()}
            </div>
          ) : null}
          {model.parameters?.max_output_tokens ? (
            <div className="mt-0.5 text-[10.5px] text-[var(--muted-foreground)]/80">
              {t("Max output")}:{" "}
              {model.parameters.max_output_tokens.toLocaleString()}
            </div>
          ) : null}
          {model.parameters?.default_dimensions ? (
            <div className="mt-0.5 text-[10.5px] text-[var(--muted-foreground)]/80">
              {t("Default dimensions")}:{" "}
              {model.parameters.default_dimensions.toLocaleString()}
              {model.parameters.supported_dimensions?.length
                ? ` · ${model.parameters.supported_dimensions.join(", ")}`
                : ""}
            </div>
          ) : null}
          {model.parameters?.supports_dimensions_parameter === false ? (
            <div className="mt-0.5 text-[10.5px] text-amber-600 dark:text-amber-400">
              {t("This endpoint does not support the dimensions parameter.")}
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  const response = state.response;
  const displayError = state.error ?? response?.error?.message ?? null;
  const cache = response?.cache;
  const cacheLabel = cache
    ? cache.state === "fresh"
      ? t("Fresh server cache")
      : cache.state === "stale"
        ? t("Stale server cache")
        : cache.state === "miss"
          ? t("Not cached yet")
          : t("Not cached")
    : t("Not cached yet");

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("Query models")}
      data-testid="model-discovery-dialog"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--popover)] shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-[var(--foreground)]">
              <Sparkles className="h-4 w-4" />
              {t("Query models")}
              <span className="rounded-full bg-[var(--muted)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
                {t(SERVICE_LABEL[service])}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--muted-foreground)]">
              <span className="inline-flex items-center gap-1">
                <Database className="h-3 w-3" />
                {cacheLabel}
              </span>
              {cache?.fetched_at ? (
                <span>
                  {t("Fetched")}: {formatWhen(cache.fetched_at)}
                </span>
              ) : null}
              {profile ? (
                <span className="inline-flex min-w-0 items-center gap-1 truncate">
                  <ProviderIcon
                    provider={profile.binding}
                    icon={presentation?.providerIcon}
                    size={12}
                  />
                  <span className="truncate">
                    {presentation?.providerLabel || profile.name}
                    {presentation?.providerLabel &&
                    presentation.providerLabel !== profile.name
                      ? ` · ${profile.name}`
                      : ""}
                  </span>
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={onRefresh}
              disabled={state.loading || !profile}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/60 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
            >
              {state.loading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              {t("Refresh")}
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label={t("Close")}
              className="rounded-lg p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)]/60 px-5 py-3">
          <div className="relative min-w-[190px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <input
              className="h-8 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] pl-8 pr-2.5 text-[12px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("Search by name or model ID")}
              aria-label={t("Search models")}
              data-testid="model-discovery-search"
            />
          </div>
          <select
            className="h-8 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2 text-[12px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
            value={filter}
            onChange={(event) =>
              setFilter(
                event.target.value as
                  | "all"
                  | "available"
                  | "unknown"
                  | "unsupported",
              )
            }
            aria-label={t("Filter candidates")}
            data-testid="model-discovery-filter"
          >
            <option value="all">{t("All candidates")}</option>
            <option value="available">{t("Compatible")}</option>
            <option value="unknown">{t("Type unconfirmed")}</option>
            <option value="unsupported">{t("Unsupported")}</option>
          </select>
          <button
            type="button"
            onClick={onQuery}
            disabled={state.loading || !profile}
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--border)]/60 px-2.5 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
          >
            {state.loading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Search className="h-3 w-3" />
            )}
            {t("Query current connection")}
          </button>
        </div>

        {displayError ? (
          <div className="mx-5 mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-300">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div className="min-w-0 flex-1">
              <div>{displayError}</div>
              {response?.status === "error" && response.models.length > 0 ? (
                <div className="mt-0.5 text-[11px] opacity-80">
                  {response.cache.state === "stale"
                    ? t("Showing the last successful directory.")
                    : t("Showing previous or preset candidates.")}
                </div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="shrink-0 rounded-md border border-amber-500/40 px-2 py-0.5 text-[11px]"
            >
              {t("Retry")}
            </button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          {!profile ? (
            <div className="py-10 text-center text-[12px] text-[var(--muted-foreground)]">
              {t("Add and save a connection before querying models.")}
            </div>
          ) : state.loading && models.length === 0 ? (
            <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-[var(--muted-foreground)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("Loading model directory...")}
            </div>
          ) : response?.status === "unsupported" ? (
            <div className="py-8 text-center text-[12px] leading-relaxed text-[var(--muted-foreground)]">
              {response.error?.message
                ? t(response.error.message)
                : t(
                    "This provider does not support online model discovery. Manual model IDs still work.",
                  )}
            </div>
          ) : models.length === 0 ? (
            <div className="py-10 text-center text-[12px] text-[var(--muted-foreground)]">
              {state.response
                ? t("No candidates were returned for this connection.")
                : t("Query this saved connection to load candidates.")}
            </div>
          ) : (
            <div className="space-y-4">
              {groups.available.length > 0 ? (
                <section>
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                    {t("Ready to add")}
                  </h4>
                  <div className="space-y-1.5">
                    {groups.available.map((model) => renderRow(model, "available"))}
                  </div>
                </section>
              ) : null}
              {groups.unknown.length > 0 ? (
                <section data-testid="model-discovery-unknown">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                      {t("Type unconfirmed")}
                    </h4>
                    <button
                      type="button"
                      data-testid="model-discovery-confirm-all"
                      onClick={() =>
                        setConfirmed((current) => {
                          const next = new Set(current);
                          for (const model of groups.unknown) next.add(model.id);
                          return next;
                        })
                      }
                      className="rounded-md border border-[var(--border)]/60 px-2 py-0.5 text-[10.5px] text-[var(--muted-foreground)] hover:border-[var(--foreground)]"
                    >
                      {t("Confirm all for this category")}
                    </button>
                  </div>
                  <div className="space-y-1.5">
                    {groups.unknown.map((model) => renderRow(model, "unknown"))}
                  </div>
                </section>
              ) : null}
              {groups.unsupported.length > 0 ? (
                <section data-testid="model-discovery-unsupported">
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                    {t("Unsupported")}
                  </h4>
                  <div className="space-y-1.5">
                    {groups.unsupported.map((model) =>
                      renderRow(model, "unsupported"),
                    )}
                  </div>
                </section>
              ) : null}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[var(--border)] px-5 py-3">
          <span className="text-[11px] text-[var(--muted-foreground)]">
            {t(
              "Candidates only enter the settings draft. Nothing is saved until you use Save.",
            )}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--border)]/60 px-3 py-1.5 text-[12px] text-[var(--muted-foreground)]"
            >
              {t("Cancel")}
            </button>
            <button
              type="button"
              onClick={() => {
                onAddSelected(
                  selectable
                    .filter((model) => selected.has(model.id))
                    .map((model) => model.id),
                  Array.from(confirmed),
                );
                onClose();
              }}
              disabled={selectedCount === 0}
              data-testid="model-discovery-add"
              className="rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-[12px] font-medium text-[var(--background)] disabled:opacity-40"
            >
              {t("Add selected ({{count}})", { count: selectedCount })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

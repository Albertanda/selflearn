"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  Info,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import { apiFetch, apiUrl } from "@/lib/api";
import {
  CUSTOM_PROVIDER_SENTINEL,
  customProviderIdFromSelectValue,
  customProvidersForService,
  customProviderSelectValue,
  localizeProviderLabel,
  newCustomProviderId,
  resolveProviderPresentation,
  type CustomProviderDefinition,
  type CustomProviderService,
} from "@/lib/custom-providers";
import CustomProviderDialog, {
  type CustomProviderDialogValue,
} from "./CustomProviderDialog";
import {
  modelDefaultReasoningChoices,
  reasoningControlsKey,
} from "@/lib/reasoning-controls";
import { CodexOAuthCard } from "./CodexOAuthCard";
import { CodeBuddyAuthCard } from "./CodeBuddyAuthCard";
import {
  isBoundManagedCodexProfile,
  isCodexOAuthProfile,
  isManagedCodexProfile,
} from "./codex-profile";
import {
  type CatalogModel,
  type CatalogProfile,
  type LlmContextWindowDetection,
  type ProviderOption,
  type ServiceName,
  resolveEditingSelection,
  useSettings,
} from "./SettingsContext";
import { DimensionField } from "./DimensionField";
import { ModelDiscoveryDialog } from "./ModelDiscoveryDialog";
import { useModelDiscovery } from "./useModelDiscovery";
import { nextProfileName } from "./profile-naming";
import {
  mergeDiscoveredModels,
  modelVisibleInPicker,
  type DiscoveryService,
} from "@/lib/model-discovery";
import {
  modelOverrideFlags,
  parameterSourceLabel,
  positiveInteger,
  previewParameterUpdate,
  type ParameterOverrideKey,
} from "@/lib/model-metadata";
import { searchProviderFields } from "./search-providers";
import {
  activeProfileDetail,
  formatContextWindowSource,
  inputClass,
  selectClass,
  selectOptionClass,
  stringifyExtraHeaders,
} from "./shared";

const SERVICE_LABEL: Record<ServiceName, string> = {
  llm: "Large language model (LLM)",
  embedding: "Embedding",
  search: "Search",
  tts: "Text-to-Speech",
  stt: "Speech-to-Text",
  imagegen: "Image Generation",
  videogen: "Video Generation",
  vision: "Vision",
};

export function ServiceConfigEditor({ service }: { service: ServiceName }) {
  const { t } = useTranslation();
  const {
    catalog,
    draft,
    catalogEditable,
    settingsError,
    providers,
    language,
    embeddingCapabilities,
    embeddingDefaultDim,
    logs,
    testRunning,
    mutateCatalog,
    editingSelections,
    reasoningControls,
    selectEditingProfile,
    selectEditingModel,
    addProfile,
    removeEditingProfile,
    addModel,
    removeEditingModel,
    updateProfileField,
    updateModelField,
    updateModelBoolField,
    updateContextWindowField,
    updateLlmBudgetField,
    updateEmbeddingDimensionField,
    updateEmbeddingSendDimensions,
    updateReasoningEffort,
    llmContextDetection,
    applyDetectedContextWindow,
    runDetailedTest,
    setToast,
  } = useSettings();

  const editing = resolveEditingSelection(
    draft,
    service,
    editingSelections[service],
  );
  const activeProfile = editing.profile;
  const activeModel = editing.model;
  const activeProviderValue =
    service === "search"
      ? activeProfile?.provider || ""
      : activeProfile?.binding || "";
  const activeProviderOption = (providers[service] || []).find(
    (option) => option.value === activeProviderValue,
  );
  const isManagedCodex = isManagedCodexProfile(activeProfile);
  const isBoundManagedCodex = isBoundManagedCodexProfile(activeProfile);
  const isCodexOAuth = isCodexOAuthProfile(
    service,
    activeProviderValue,
    activeProviderOption,
    activeProfile,
  );

  const [showApiKey, setShowApiKey] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [editingModelName, setEditingModelName] = useState("");
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editingProfileName, setEditingProfileName] = useState("");
  const [modelsSyncing, setModelsSyncing] = useState(false);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [parameterPreviewOpen, setParameterPreviewOpen] = useState(false);
  const [restoreAuto, setRestoreAuto] = useState<ParameterOverrideKey[]>([]);

  // Reset API-key visibility whenever we land on a different profile or
  // switch services — same effect the old code had, but using React's
  // documented "store previous prop in state" pattern so it happens during
  // render rather than in a useEffect (which the linter forbids).
  const profileKey = `${service}:${activeProfile?.id ?? "none"}`;
  const [lastProfileKey, setLastProfileKey] = useState(profileKey);
  if (lastProfileKey !== profileKey) {
    setLastProfileKey(profileKey);
    if (showApiKey) setShowApiKey(false);
    if (discoveryOpen) setDiscoveryOpen(false);
  }

  const discoveryService: DiscoveryService =
    service === "search" ? "llm" : service;
  const savedProfile =
    service === "search" || !activeProfile
      ? null
      : (catalog.services[service].profiles.find(
          (profile) => profile.id === activeProfile.id,
        ) ?? null);
  const discovery = useModelDiscovery({
    service: discoveryService,
    profile: service === "search" ? null : activeProfile,
    savedProfile,
  });
  const isCurrentGlobalLlmDefault =
    service === "llm" &&
    Boolean(activeProfile && activeModel) &&
    catalog.services.llm.active_profile_id === activeProfile?.id &&
    catalog.services.llm.active_model_id === activeModel?.id;
  const isEditingDefaultProfile =
    Boolean(activeProfile) &&
    draft.services[service].active_profile_id === activeProfile?.id;
  const isEditingDefaultModel =
    isEditingDefaultProfile &&
    (service === "search" ||
      draft.services[service].active_model_id === activeModel?.id);
  const discoveryDisabled =
    service === "search" ||
    !activeProfile ||
    isCodexOAuth ||
    isManagedCodex ||
    activeProfile.binding === "codebuddy";

  const searchProviderRaw =
    service === "search"
      ? (activeProfile?.provider || "").trim().toLowerCase()
      : "";
  const showSearchProviderWarning =
    service === "search" && Boolean(searchProviderRaw);
  // Every judgement below reads the backend's own provider list, so the web app
  // never keeps a second (and drifting) copy of what is supported.
  const searchProviderOption = (providers.search || []).find(
    (option) => option.value === searchProviderRaw,
  );
  const isDeprecatedSearchProvider =
    searchProviderOption?.status === "deprecated";
  const isSupportedSearchProvider =
    Boolean(searchProviderOption) && !isDeprecatedSearchProvider;
  const supportedSearchProviderNames = (providers.search || [])
    .filter(
      (option) => option.status !== "deprecated" && option.value !== "none",
    )
    .map((option) => option.value)
    .join("/");
  // Providers that fail hard rather than falling back need their key before the
  // first query — say so while the user is still on this screen.
  const searchProviderMissingKey =
    service === "search" &&
    isSupportedSearchProvider &&
    searchProviderOption?.requires_api_key === true &&
    searchProviderOption?.soft_fallback === false &&
    !String(activeProfile?.api_key || "").trim();
  const activeLlmDetection =
    service === "llm" &&
    llmContextDetection?.profileId === activeProfile?.id &&
    llmContextDetection?.modelId === activeModel?.id
      ? llmContextDetection
      : null;
  const matchedCandidate = activeModel
    ? discovery.response?.models.find((model) => model.id === activeModel.model)
    : undefined;
  const currentParameterPreview =
    activeModel &&
    (matchedCandidate?.parameters || matchedCandidate?.reasoning_controls)
      ? previewParameterUpdate({
          existing: activeModel,
          parameters: matchedCandidate.parameters,
          service: service === "llm" || service === "embedding" ? service : "llm",
          restoreAuto,
          reasoningControls: matchedCandidate.reasoning_controls,
        })
      : null;
  const manualParameterFields = activeModel
    ? (Object.entries(modelOverrideFlags(activeModel)) as [
        ParameterOverrideKey,
        boolean,
      ][])
        .filter(([, value]) => value)
        .map(([key]) => key)
    : [];
  const activeReasoningControls =
    service === "llm" && activeProfile && activeModel
      ? (reasoningControls[
          reasoningControlsKey(activeProfile.id, activeModel.id)
        ] ?? activeModel.provider_metadata?.reasoning_controls)
      : undefined;
  const storedReasoningValue = (activeModel?.reasoning_effort ?? "").trim();
  const reasoningOptions =
    service === "llm" &&
    activeModel &&
    activeReasoningControls?.supported === true
      ? isManagedCodex
        ? isBoundManagedCodex
          ? modelDefaultReasoningChoices(
              activeReasoningControls,
              activeModel.reasoning_effort ?? "",
            )
          : []
        : modelDefaultReasoningChoices(
            activeReasoningControls,
            activeModel.reasoning_effort ?? "",
          )
      : [];

  const syncProviderModels = async (
    connection?: Pick<CatalogProfile, "binding" | "base_url" | "api_key">,
  ) => {
    if (service !== "llm" || !activeProfile || modelsSyncing) return;
    const binding = connection?.binding ?? activeProfile.binding ?? "";
    const baseUrl = connection?.base_url ?? activeProfile.base_url ?? "";
    const apiKey = connection?.api_key ?? activeProfile.api_key ?? "";
    if (!binding || (binding !== "codebuddy" && !baseUrl.trim())) return;

    const profileId = activeProfile.id;
    setModelsSyncing(true);
    try {
      const response = await apiFetch(apiUrl("/api/v1/settings/fetch-models"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          binding,
          base_url: baseUrl,
          api_key: apiKey || null,
          profile_id: profileId,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(payload.detail || `HTTP ${response.status}`);
      }
      const payload = (await response.json()) as {
        models?: Array<{ id: string; name?: string }>;
      };
      const fetched = payload.models || [];
      if (fetched.length === 0) throw new Error(t("No models returned"));

      mutateCatalog((next) => {
        const target = next.services.llm;
        const profile = target.profiles.find((item) => item.id === profileId);
        if (!profile || profile.binding !== binding) return;
        const existing = new Map(
          profile.models.map((model) => [model.model, model]),
        );
        const fetchedModels = fetched.map((item, index) => {
          const previous = existing.get(item.id);
          return previous
            ? { ...previous, name: item.name || previous.name, model: item.id }
            : {
                id: `llm-model-${Date.now()}-${index}`,
                name: item.name || item.id,
                model: item.id,
              };
        });
        // Directory sync is an edit of this profile, never an implicit
        // default change. Keep the saved default entry even if a transient
        // provider response omitted it.
        const savedDefault = profile.models.find(
          (model) =>
            model.id === target.active_model_id &&
            !fetchedModels.some((item) => item.id === model.id),
        );
        profile.models = savedDefault
          ? [...fetchedModels, savedDefault]
          : fetchedModels;
      });
      setToast(t("Synced {{count}} models", { count: fetched.length }));
    } catch (error) {
      setToast(error instanceof Error ? error.message : String(error));
    } finally {
      setModelsSyncing(false);
    }
  };

  const startModelRename = (model: CatalogModel) => {
    setEditingModelId(model.id);
    setEditingModelName(model.name || model.model || "");
  };

  const commitModelRename = (modelId: string) => {
    const fallbackIndex =
      activeProfile?.models.findIndex((model) => model.id === modelId) ?? -1;
    const fallbackName = defaultModelLabel(language, fallbackIndex + 1);
    const nextName = editingModelName.trim() || fallbackName;
    const profileId = activeProfile?.id;
    mutateCatalog((next) => {
      const profile = next.services[service].profiles.find(
        (item) => item.id === profileId,
      );
      const model = profile?.models.find((item) => item.id === modelId);
      if (model) model.name = nextName;
    });
    setEditingModelId(null);
    setEditingModelName("");
  };

  const cancelModelRename = () => {
    setEditingModelId(null);
    setEditingModelName("");
  };

  const startProfileRename = (profile: CatalogProfile) => {
    setEditingProfileId(profile.id);
    setEditingProfileName(profile.name || "");
  };

  const commitProfileRename = (profileId: string) => {
    const nextName = editingProfileName.trim();
    if (nextName) {
      mutateCatalog((next) => {
        const profile = next.services[service].profiles.find(
          (item) => item.id === profileId,
        );
        if (profile) profile.name = nextName;
      });
    }
    setEditingProfileId(null);
    setEditingProfileName("");
  };

  const cancelProfileRename = () => {
    setEditingProfileId(null);
    setEditingProfileName("");
  };

  if (!catalogEditable) {
    // catalogEditable=false covers two unrelated cases: settings fetch failed,
    // or multi-user grant denied. Split them so a Docker user without the
    // 8001 port mapped does not see an "assigned by administrator" hint.
    if (settingsError) {
      return (
        <div className="rounded-xl border border-dashed border-[var(--border)] px-5 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
          {t(
            "Backend unreachable — model endpoints will appear once the connection is restored. See the banner above for details.",
          )}
        </div>
      );
    }
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-dashed border-[var(--border)] px-5 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
          {t(
            "Model endpoints are assigned by your administrator. You can still personalize theme and language here.",
          )}
        </div>
        {/* One thing an ordinary user CAN configure for themselves: an
            owner-bound Codex login. It authenticates their own ChatGPT plan,
            so it is never something an administrator can grant them — the
            account has to sign in for itself (#781). The card talks only to
            the per-user OAuth endpoints and exposes no catalog. */}
        {service === "llm" && <CodexOAuthCard />}
      </div>
    );
  }

  return (
    <div data-tour={`tour-${service}`} className="space-y-5">
      {activeProfile ? (
        <div className="grid grid-cols-[200px_minmax(0,1fr)] items-start gap-5">
          {/* ── Profile list (sticky so it stays put while the editor scrolls) ── */}
          <aside className="sticky top-4 self-start rounded-xl border border-[var(--border)]/60 bg-[var(--card)]/40 p-2">
            <div className="px-2 pb-2 pt-1 text-[11px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]/70">
              {t("Profiles")}
            </div>
            <div className="space-y-0.5">
              {draft.services[service].profiles.map((profile) => {
                const isActive = profile.id === activeProfile?.id;
                const isSavedDefault =
                  profile.id === draft.services[service].active_profile_id;
                const profileDetail = activeProfileDetail(profile, service, t);
                const isManagedProfile = isManagedCodexProfile(profile);
                const isEditing =
                  editingProfileId === profile.id && !isManagedProfile;
                return (
                  <div
                    key={profile.id}
                    role="button"
                    data-testid="profile-tab"
                    data-profile-id={profile.id}
                    tabIndex={isEditing ? -1 : 0}
                    onClick={() => {
                      if (isEditing) return;
                      selectEditingProfile(service, profile.id);
                    }}
                    onDoubleClick={() => {
                      if (!isManagedProfile) startProfileRename(profile);
                    }}
                    onKeyDown={(e) => {
                      if (isEditing) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        selectEditingProfile(service, profile.id);
                      }
                    }}
                    title={
                      isEditing || isManagedProfile
                        ? undefined
                        : t("Double-click to rename")
                    }
                    className={`group relative cursor-pointer rounded-lg px-3 py-2 text-left transition-colors ${
                      isActive
                        ? "bg-[var(--muted)]/70 text-[var(--foreground)]"
                        : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/30"
                    }`}
                  >
                    {isActive && (
                      <span className="absolute inset-y-2 left-0 w-0.5 rounded-r-full bg-[var(--foreground)]/80" />
                    )}
                    {isEditing ? (
                      <input
                        autoFocus
                        aria-label={t("Rename profile")}
                        className="block w-full rounded border border-[var(--border)] bg-[var(--background)] px-1.5 py-0.5 text-[13px] font-medium text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                        value={editingProfileName}
                        onChange={(e) => setEditingProfileName(e.target.value)}
                        onBlur={() => commitProfileRename(profile.id)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.currentTarget.blur();
                          }
                          if (e.key === "Escape") {
                            e.preventDefault();
                            cancelProfileRename();
                          }
                        }}
                                              />
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <ProviderIcon
                          provider={
                            service === "search"
                              ? profile.provider
                              : profile.binding
                          }
                          icon={
                            service === "search"
                              ? null
                              : resolveProviderPresentation(
                                  draft,
                                  service,
                                  profile,
                                ).providerIcon
                          }
                          size={13}
                        />
                        <div
                          className={`min-w-0 flex-1 truncate text-[13px] leading-tight ${
                            isActive ? "font-semibold" : "font-medium"
                          }`}
                        >
                          {profile.name}
                        </div>
                        {isSavedDefault && (
                          <span className="shrink-0 rounded-full bg-[var(--muted)] px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                            {t("Default")}
                          </span>
                        )}
                        {!isManagedProfile && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              startProfileRename(profile);
                            }}
                            className="-mr-1 shrink-0 rounded-md p-1 text-[var(--muted-foreground)]/60 transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                            aria-label={t("Rename profile")}
                            title={t("Rename profile")}
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                    )}
                    <div className="mt-0.5 truncate text-[11px] leading-tight text-[var(--muted-foreground)]/70">
                      {profileDetail}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-2 border-t border-[var(--border)]/40 pt-2">
              <button
                data-testid="delete-profile"
                onClick={() => removeEditingProfile(service)}
                disabled={
                  !activeProfile || isManagedCodex || isEditingDefaultProfile
                }
                className="flex w-full items-center gap-1.5 rounded-lg px-3 py-1.5 text-left text-[11px] text-[var(--muted-foreground)]/60 transition-colors hover:bg-red-500/5 hover:text-red-500 disabled:opacity-30"
                title={
                  isEditingDefaultProfile
                    ? t(
                        "This profile holds the saved default. Choose another default before deleting it.",
                      )
                    : activeProfile && !isManagedCodex
                      ? t("Permanently remove the selected profile.")
                      : undefined
                }
              >
                <Trash2 className="h-3 w-3 shrink-0" />
                <span className="truncate">
                  {activeProfile
                    ? t("Delete “{{name}}”", { name: activeProfile.name })
                    : t("Delete profile")}
                </span>
              </button>
            </div>
          </aside>

          {/* ── Editor ── */}
          <div className="min-w-0 space-y-5">
            <div className="rounded-xl border border-[var(--border)] p-5">
              <div className="mb-4 flex items-center justify-between gap-2">
                <div className="text-[13px] font-medium text-[var(--foreground)]">
                  {t("Provider connection")}
                </div>
                <button
                  type="button"
                  data-testid="add-profile"
                  onClick={() => addProfile(service)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
                >
                  <Plus className="h-3 w-3" />
                  {t("Profile")}
                </button>
              </div>
              <ProfileFields
                service={service}
                profile={activeProfile}
                showApiKey={showApiKey}
                setShowApiKey={setShowApiKey}
                showSearchProviderWarning={showSearchProviderWarning}
                isSupportedSearchProvider={isSupportedSearchProvider}
                isDeprecatedSearchProvider={isDeprecatedSearchProvider}
                searchProviderMissingKey={searchProviderMissingKey}
                supportedSearchProviderNames={supportedSearchProviderNames}
                onProviderChanged={(provider, previousProvider) => {
                  if (service !== "llm" || !activeProfile) return;
                  const crossesCodeBuddyBoundary =
                    provider.value === "codebuddy" ||
                    previousProvider === "codebuddy";
                  if (crossesCodeBuddyBoundary) {
                    const profileId = activeProfile.id;
                    const modelId = `llm-model-${Date.now()}`;
                    mutateCatalog((next) => {
                      const target = next.services.llm;
                      const profile = target.profiles.find(
                        (item) => item.id === profileId,
                      );
                      if (!profile || profile.binding !== provider.value)
                        return;
                      if (provider.value === "codebuddy") {
                        profile.models = [];
                        return;
                      }
                      profile.models = [
                        {
                          id: modelId,
                          name: defaultModelLabel(language, 1),
                          model: "",
                        },
                      ];
                    });
                  }
                  if (provider.value === "codebuddy") {
                    void syncProviderModels({
                      binding: provider.value,
                      base_url: provider.base_url || "",
                      api_key: "",
                    });
                  }
                }}
              />
            </div>

            {service !== "search" && (
              <div className="rounded-xl border border-[var(--border)] p-5">
                <div className="mb-4 flex items-center justify-between gap-2">
                  <div className="text-[13px] font-medium text-[var(--foreground)]">
                    {t("Models")}
                  </div>
                  {!isCodexOAuth && (
                    <div className="flex items-center gap-2">
                      {!discoveryDisabled && (
                        <button
                          type="button"
                          onClick={() => setDiscoveryOpen(true)}
                          data-testid="model-discovery-open"
                          className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
                          title={t(
                            "Query the provider directory, search, and add models to this draft.",
                          )}
                        >
                          <Sparkles className="h-3 w-3" />
                          {t("Query models")}
                        </button>
                      )}
                      {service === "llm" &&
                        activeProfile.binding === "codebuddy" && (
                          <button
                            type="button"
                            onClick={() => void syncProviderModels()}
                            disabled={modelsSyncing}
                            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
                          >
                            <RefreshCw
                              className={`h-3 w-3 ${modelsSyncing ? "animate-spin" : ""}`}
                            />
                            {t("Sync models")}
                          </button>
                        )}
                      <button
                        type="button"
                        data-testid="add-model"
                        onClick={() => addModel(service)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
                      >
                        <Plus className="h-3 w-3" />
                        {t("Model")}
                      </button>
                      <button
                        data-testid="delete-model"
                        onClick={() => removeEditingModel(service)}
                        disabled={!activeModel || isEditingDefaultModel}
                        title={
                          isEditingDefaultModel
                            ? t(
                                "This is the saved default model. Choose another default before deleting it.",
                              )
                            : undefined
                        }
                        className="inline-flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]/40 transition-colors hover:text-red-500 disabled:opacity-30"
                      >
                        <Trash2 className="h-3 w-3" />
                        {t("Delete")}
                      </button>
                    </div>
                  )}
                </div>
                {activeProfile.models.length > 0 && (
                  <div className="mb-4 flex flex-wrap items-center gap-1.5">
                    {activeProfile.models.map((model, index) => {
                      const isActive = model.id === activeModel?.id;
                      const isSavedDefault =
                        isEditingDefaultProfile &&
                        model.id === draft.services[service].active_model_id;
                      const label =
                        (model.name || "").trim() ||
                        defaultModelLabel(language, index + 1);
                      const metric =
                        service === "llm"
                          ? formatCompactTokens(model.context_window)
                          : service === "embedding"
                            ? formatDimensionBadge(model.dimension)
                            : service === "tts"
                              ? formatVoiceBadge(model.voice)
                              : "";
                      return (
                        <div key={model.id} className="min-w-0">
                          {editingModelId === model.id && !isCodexOAuth ? (
                            <input
                              autoFocus
                              data-testid="model-rename-input"
                              className="h-8 w-60 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 text-[12.5px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                              value={editingModelName}
                              onChange={(e) =>
                                setEditingModelName(e.target.value)
                              }
                              onBlur={() => commitModelRename(model.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.currentTarget.blur();
                                }
                                if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelModelRename();
                                }
                              }}
                              aria-label={t("Rename model")}
                            />
                          ) : (
                            <button
                              type="button"
                              data-testid="model-chip"
                              data-model-id={model.id}
                              onClick={() =>
                                selectEditingModel(service, model.id)
                              }
                              onDoubleClick={() => {
                                if (!isCodexOAuth) startModelRename(model);
                              }}
                              title={
                                isCodexOAuth
                                  ? undefined
                                  : t("Double-click to rename")
                              }
                              className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] transition-colors ${
                                isActive
                                  ? "bg-[var(--muted)] text-[var(--foreground)]"
                                  : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/40"
                              }`}
                            >
                              {isActive && (
                                <CheckCircle2 className="h-3 w-3 shrink-0 text-[var(--foreground)]/70" />
                              )}
                              <span
                                className={`max-w-[280px] truncate leading-none ${
                                  isActive ? "font-medium" : ""
                                }`}
                              >
                                {label}
                              </span>
                              {isSavedDefault && (
                                <span className="shrink-0 rounded-full bg-[var(--muted)] px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                                  {t("Default")}
                                </span>
                              )}
                              {service === "llm" &&
                                !modelVisibleInPicker(model) && (
                                  <EyeOff
                                    className="h-3 w-3 shrink-0 text-[var(--muted-foreground)]/70"
                                    aria-label={t("Hidden from chat picker")}
                                  />
                                )}
                              {metric && (
                                <span className="shrink-0 text-[10.5px] tabular-nums leading-none text-[var(--muted-foreground)]/80">
                                  {metric}
                                </span>
                              )}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                {activeModel && (!isCodexOAuth || isBoundManagedCodex) && (
                  <div className="grid gap-4 sm:grid-cols-2">
                    {!isCodexOAuth && (
                      <div>
                        <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                          {t("Model ID")}
                        </div>
                        <input
                          data-testid="model-id-input"
                          className={inputClass}
                          value={activeModel.model}
                          onChange={(e) =>
                            updateModelField(service, "model", e.target.value)
                          }
                          placeholder="gpt-4o"
                        />
                      </div>
                    )}
                    {service === "llm" && (
                      <>
                        {!isCodexOAuth && (
                          <>
                            <div>
                              <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                                {t("Context Window")}
                              </div>
                              <input
                                className={inputClass}
                                inputMode="numeric"
                                data-testid="llm-context-window"
                                value={activeModel.context_window || ""}
                                onChange={(e) =>
                                  updateContextWindowField(e.target.value)
                                }
                                placeholder="65536"
                              />
                              <ContextWindowMeta model={activeModel} />
                              {!activeModel.context_window &&
                              activeModel.max_input_tokens ? (
                                <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">
                                  {t("Input limit")}:{" "}
                                  {Number(
                                    activeModel.max_input_tokens,
                                  ).toLocaleString("en-US")}{" "}
                                  ·{" "}
                                  {t(
                                    "This is an input-only limit, not the total context window.",
                                  )}
                                </p>
                              ) : null}
                            </div>
                            <div>
                              <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                                {t("Default max output tokens")}
                              </div>
                              <input
                                className={inputClass}
                                inputMode="numeric"
                                data-testid="llm-max-tokens"
                                value={activeModel.max_tokens || ""}
                                onChange={(e) =>
                                  updateLlmBudgetField(e.target.value)
                                }
                                placeholder="4096"
                              />
                              <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                                {t(
                                  "Used when a request has no smaller business budget. The provider's declared maximum is enforced as a ceiling.",
                                )}
                                {activeModel.provider_metadata?.parameters
                                  .max_output_tokens ? (
                                  <>
                                    {" "}
                                    {t("Provider maximum")}:{" "}
                                    {activeModel.provider_metadata.parameters.max_output_tokens.toLocaleString(
                                      "en-US",
                                    )}
                                  </>
                                ) : null}
                              </p>
                            </div>
                            <ContextWindowDetectionBanner
                              model={activeModel}
                              detection={activeLlmDetection}
                              onApply={applyDetectedContextWindow}
                            />
                            {currentParameterPreview &&
                            (currentParameterPreview.changes.length > 0 ||
                              manualParameterFields.length > 0) ? (
                              <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)]/60 bg-[var(--muted)]/20 px-3.5 py-2.5">
                                <div className="text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                                  {t(
                                    "The directory returned different official parameters for this model.",
                                  )}
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setRestoreAuto([]);
                                    setParameterPreviewOpen(true);
                                  }}
                                  data-testid="llm-parameter-update"
                                  className="rounded-md border border-[var(--border)] bg-[var(--background)] px-2.5 py-1 text-[11.5px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--foreground)]"
                                >
                                  {t("Preview official parameter update")}
                                </button>
                              </div>
                            ) : null}
                            <div className="sm:col-span-2 rounded-lg border border-[var(--border)]/60 bg-[var(--muted)]/20 px-3.5 py-3">
                              <label className="flex items-start justify-between gap-3">
                                <span className="min-w-0">
                                  <span className="block text-[12px] font-medium text-[var(--foreground)]">
                                    {t("Show in chat picker")}
                                  </span>
                                  <span className="mt-0.5 block text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                                    {isCurrentGlobalLlmDefault
                                      ? t(
                                          "The current global default cannot be hidden. Choose another default first.",
                                        )
                                      : t(
                                          "Hiding only removes this model from new selections. It keeps its API id, parameters, grants, and existing conversations.",
                                        )}
                                  </span>
                                </span>
                                <input
                                  type="checkbox"
                                  className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--foreground)] disabled:opacity-40"
                                  checked={modelVisibleInPicker(activeModel)}
                                  disabled={isCurrentGlobalLlmDefault}
                                  onChange={(event) => {
                                    if (
                                      isCurrentGlobalLlmDefault &&
                                      !event.target.checked
                                    ) {
                                      setToast(
                                        t(
                                          "Choose another global default before hiding this model.",
                                        ),
                                      );
                                      return;
                                    }
                                    updateModelBoolField(
                                      service,
                                      "visible_in_picker",
                                      event.target.checked,
                                    );
                                  }}
                                  aria-label={t("Show in chat picker")}
                                />
                              </label>
                            </div>
                          </>
                        )}
                        {service === "llm" &&
                          activeModel &&
                          (activeReasoningControls?.supported === false ||
                            (storedReasoningValue &&
                              reasoningOptions.length === 0)) && (
                            <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3.5 py-2 text-[11px] leading-relaxed text-amber-700 dark:text-amber-400">
                              <span>
                                {storedReasoningValue
                                  ? t(
                                      "Stored reasoning setting “{{value}}” has no verified control for this model and is not sent.",
                                      { value: storedReasoningValue },
                                    )
                                  : t(
                                      "This model has no verified reasoning control. No reasoning parameter will be sent.",
                                    )}
                              </span>
                              {storedReasoningValue && (
                                <button
                                  type="button"
                                  onClick={() => updateReasoningEffort("")}
                                  className="rounded-md border border-amber-500/40 px-2 py-0.5 text-[10.5px] font-medium text-amber-700 hover:bg-amber-500/10 dark:text-amber-300"
                                >
                                  {t("Clear reasoning setting")}
                                </button>
                              )}
                            </div>
                          )}
                        {reasoningOptions.length > 0 && (
                          <div>
                            <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                              {t("Reasoning effort")}
                            </div>
                            <div className="relative">
                              <select
                                data-testid="model-reasoning-effort"
                                className={selectClass}
                                value={activeModel.reasoning_effort || ""}
                                onChange={(event) =>
                                  updateReasoningEffort(event.target.value)
                                }
                              >
                                {reasoningOptions.map((option) => (
                                  <option
                                    className={selectOptionClass}
                                    key={option.value || "auto"}
                                    value={option.value}
                                  >
                                    {t(option.label)}
                                  </option>
                                ))}
                              </select>
                              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
                            </div>
                            <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                              {t(
                                "Sets this model's default reasoning depth. Auto leaves the choice to the provider.",
                              )}
                            </p>
                          </div>
                        )}
                      </>
                    )}
                    {service === "embedding" && (
                      <div>
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <span className="text-[12px] text-[var(--muted-foreground)]">
                            {t("Dimension")}
                          </span>
                          <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-[var(--muted-foreground)] select-none">
                            <input
                              type="checkbox"
                              className="h-3 w-3 cursor-pointer accent-[var(--foreground)]"
                              checked={activeModel.send_dimensions !== false}
                              onChange={(e) =>
                                updateEmbeddingSendDimensions(e.target.checked)
                              }
                            />
                            <span>{t("Send dimensions")}</span>
                            <span
                              tabIndex={0}
                              className="group/info relative inline-flex cursor-help focus:outline-none"
                            >
                              <Info className="h-3 w-3 opacity-50 transition-opacity group-hover/info:opacity-100 group-focus/info:opacity-100" />
                              <span
                                role="tooltip"
                                className="pointer-events-none absolute top-full left-1/2 z-20 mt-1.5 w-64 -translate-x-1/2 rounded-lg border border-[var(--border)] bg-[var(--card)] p-2.5 text-[11px] leading-relaxed text-[var(--foreground)] opacity-0 shadow-lg transition-opacity duration-75 group-hover/info:opacity-100 group-focus/info:opacity-100"
                              >
                                {t(
                                  "Send a dimension parameter only when this endpoint supports it. Disable it for fixed-dimension models or gateways that reject the parameter.",
                                )}
                              </span>
                            </span>
                          </label>
                        </div>
                        <DimensionField
                          activeModel={activeModel}
                          activeBinding={activeProfile?.binding}
                          capabilities={embeddingCapabilities}
                          embeddingDefaultDim={embeddingDefaultDim}
                          inputClass={inputClass}
                          onChangeDimension={updateEmbeddingDimensionField}
                        />
                      </div>
                    )}
                    {service === "tts" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Voice")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.voice || ""}
                            onChange={(e) =>
                              updateModelField(service, "voice", e.target.value)
                            }
                            placeholder="alloy"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Provider-specific voice name, e.g. alloy (OpenAI) or model:voice (SiliconFlow).",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Output format")}
                          </div>
                          <div className="relative">
                            <select
                              className={selectClass}
                              value={activeModel.response_format || "mp3"}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "response_format",
                                  e.target.value,
                                )
                              }
                            >
                              {["mp3", "wav", "opus", "aac", "flac", "pcm"].map(
                                (fmt) => (
                                  <option
                                    className={selectOptionClass}
                                    key={fmt}
                                    value={fmt}
                                  >
                                    {fmt}
                                  </option>
                                ),
                              )}
                            </select>
                            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
                          </div>
                        </div>
                      </>
                    )}
                    {service === "imagegen" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Image size")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.size || ""}
                            onChange={(e) =>
                              updateModelField(service, "size", e.target.value)
                            }
                            placeholder="1024x1024"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Default pixel size sent with each request. Leave empty for the provider default.",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Quality / Style")}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              className={inputClass}
                              value={activeModel.quality || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "quality",
                                  e.target.value,
                                )
                              }
                              placeholder={t("quality (e.g. hd)")}
                            />
                            <input
                              className={inputClass}
                              value={activeModel.style || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "style",
                                  e.target.value,
                                )
                              }
                              placeholder={t("style (e.g. vivid)")}
                            />
                          </div>
                        </div>
                      </>
                    )}
                    {service === "videogen" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Aspect ratio")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.aspect_ratio || ""}
                            onChange={(e) =>
                              updateModelField(
                                service,
                                "aspect_ratio",
                                e.target.value,
                              )
                            }
                            placeholder="16:9"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Defaults sent with each request. Leave empty for the provider default.",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Duration / Resolution")}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              className={inputClass}
                              inputMode="numeric"
                              value={activeModel.duration || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "duration",
                                  e.target.value,
                                )
                              }
                              placeholder={t("seconds")}
                            />
                            <input
                              className={inputClass}
                              value={activeModel.resolution || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "resolution",
                                  e.target.value,
                                )
                              }
                              placeholder="720p"
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Diagnostics — per-service, inline ── */}
            <div className="rounded-xl border border-[var(--border)]">
              <div className="flex items-center justify-between px-5 py-3.5">
                <button
                  type="button"
                  onClick={() => setDiagnosticsOpen((v) => !v)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  aria-expanded={diagnosticsOpen}
                >
                  <Terminal className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
                  <span className="text-[13px] font-medium text-[var(--foreground)]">
                    {t("Diagnostics")}
                  </span>
                  {testRunning === service && (
                    <Loader2 className="h-3 w-3 animate-spin text-[var(--primary)]" />
                  )}
                </button>
                <div className="ml-3 flex items-center gap-3">
                  <button
                    type="button"
                    data-testid="run-test"
                    onClick={() => {
                      if (!diagnosticsOpen) setDiagnosticsOpen(true);
                      runDetailedTest(service);
                    }}
                    disabled={testRunning !== null}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
                  >
                    {t("Run test")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDiagnosticsOpen((v) => !v)}
                    className="text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                    aria-label={
                      diagnosticsOpen
                        ? t("Collapse diagnostics")
                        : t("Expand diagnostics")
                    }
                    aria-expanded={diagnosticsOpen}
                  >
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${diagnosticsOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                </div>
              </div>
              {diagnosticsOpen && (
                <div className="border-t border-[var(--border)] px-5 py-4">
                  <p className="mb-3 text-[12px] leading-relaxed text-[var(--muted-foreground)]">
                    {t(
                      "Streams config snapshot, request target, response summary, and service-specific validation for the active {{service}} profile.",
                      { service: t(SERVICE_LABEL[service]) },
                    )}
                  </p>
                  <pre className="max-h-[360px] overflow-auto rounded-lg bg-[#0f0f0f] p-4 font-mono text-[12px] leading-6 text-[#777] whitespace-pre-wrap break-words dark:bg-[#0a0a0a]">
                    {testRunning === service || logs
                      ? logs
                      : t("Waiting for test run...")}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[var(--border)] px-5 py-12 text-center text-[13px] text-[var(--muted-foreground)]">
          <div>{t("No profiles configured. Add a profile to start.")}</div>
          <button
            type="button"
            onClick={() => addProfile(service)}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
          >
            <Plus className="h-3 w-3" />
            {t("Profile")}
          </button>
        </div>
      )}
      {service !== "search" && (
        <ModelDiscoveryDialog
          key={discovery.identity}
          open={discoveryOpen}
          onClose={() => setDiscoveryOpen(false)}
          service={discoveryService}
          profile={activeProfile}
          state={{
            requestKey: discovery.requestKey,
            response: discovery.response,
            loading: discovery.loading,
            error: discovery.error,
          }}
          onQuery={() => void discovery.query("cache_first")}
          onRefresh={() => void discovery.refresh()}
          onRetry={() => void discovery.retry()}
          onAddSelected={(ids, confirmed) => {
            if (!activeProfile) return;
            const merged = mergeDiscoveredModels({
              existing: activeProfile.models,
              candidates: discovery.response?.models ?? [],
              selectedIds: ids,
              confirmedUnknownIds: confirmed,
              service: discoveryService,
            });
            if (merged.addedIds.length === 0) {
              setToast(
                merged.reusedIds.length > 0
                  ? t("The selected models are already configured.")
                  : t("No new models were added."),
              );
              return;
            }
            const profileId = activeProfile.id;
            mutateCatalog((next) => {
              const profile = next.services[service].profiles.find(
                (item) => item.id === profileId,
              );
              if (!profile) return;
              profile.models = merged.models;
            });
            if (merged.addedIds[0]) {
              selectEditingModel(service, merged.addedIds[0]);
            }
            setToast(
              t(
                "Added {{count}} model(s) to this draft. Save or Apply to use them.",
                { count: merged.addedIds.length },
              ),
            );
          }}
        />
      )}
      {parameterPreviewOpen &&
      activeProfile &&
      activeModel &&
      (matchedCandidate?.parameters || matchedCandidate?.reasoning_controls) &&
      currentParameterPreview ? (
        <div
          className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          data-testid="parameter-update-dialog"
        >
          <div className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--popover)] p-5 shadow-2xl">
            <div className="text-[15px] font-semibold text-[var(--foreground)]">
              {t("Update official parameters")}
            </div>
            <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--muted-foreground)]">
              {t(
                "This only changes the unsaved draft. Manual values are preserved unless you explicitly restore automatic values.",
              )}
            </p>
            <div className="mt-3 space-y-1.5">
              {currentParameterPreview.changes.length === 0 ? (
                <div className="rounded-lg border border-[var(--border)]/60 px-3 py-2 text-[12px] text-[var(--muted-foreground)]">
                  {Object.keys(currentParameterPreview.updates).length > 0
                    ? t("Official metadata or automatic request settings will be updated; manual values are preserved.")
                    : t("No automatic value differs from the current draft.")}
                </div>
              ) : (
                currentParameterPreview.changes.map((change) => (
                  <div
                    key={change.field}
                    data-testid="parameter-update-change"
                    className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border)]/60 px-3 py-2 text-[12px]"
                  >
                    <span className="font-mono text-[11.5px] text-[var(--foreground)]">
                      {change.field}
                    </span>
                    <span className="tabular-nums text-[var(--muted-foreground)]">
                      {change.from?.toLocaleString("en-US") ?? t("Unknown")} →{" "}
                      {change.to?.toLocaleString("en-US") ?? t("Unknown")}
                    </span>
                  </div>
                ))
              )}
            </div>
            {manualParameterFields.length > 0 ? (
              <div className="mt-3 space-y-1.5">
                <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
                  {t("Manual values")}
                </div>
                {manualParameterFields.map((field) => (
                  <label
                    key={field}
                    className="flex items-center gap-2 text-[12px] text-[var(--foreground)]"
                  >
                    <input
                      type="checkbox"
                      checked={restoreAuto.includes(field)}
                      onChange={(event) =>
                        setRestoreAuto((current) =>
                          event.target.checked
                            ? [...current, field]
                            : current.filter((item) => item !== field),
                        )
                      }
                    />
                    {t("Restore automatic value for {{field}}", {
                      field,
                    })}
                  </label>
                ))}
              </div>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setParameterPreviewOpen(false)}
                className="rounded-lg border border-[var(--border)]/60 px-3 py-1.5 text-[12px] text-[var(--muted-foreground)]"
              >
                {t("Cancel")}
              </button>
              <button
                type="button"
                disabled={Object.keys(currentParameterPreview.updates).length === 0}
                data-testid="parameter-update-apply"
                onClick={() => {
                  const profileId = activeProfile.id;
                  const modelId = activeModel.id;
                  const updates = currentParameterPreview.updates;
                  mutateCatalog((next) => {
                    const profile = next.services[service].profiles.find(
                      (item) => item.id === profileId,
                    );
                    const model = profile?.models.find(
                      (item) => item.id === modelId,
                    );
                    if (!model) return;
                    Object.assign(model, updates);
                  });
                  setParameterPreviewOpen(false);
                  setToast(
                    t("Applied official parameters to the unsaved draft."),
                  );
                }}
                className="rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-[12px] font-medium text-[var(--background)] disabled:opacity-40"
              >
                {t("Apply to draft")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function defaultModelLabel(language: "en" | "zh", index: number): string {
  const safeIndex = index > 0 ? index : 1;
  return language === "zh" ? `模型${safeIndex}` : `Model ${safeIndex}`;
}

function formatCompactTokens(value: string | number | undefined): string {
  if (value === undefined || value === "") return "";
  const parsed =
    typeof value === "number"
      ? value
      : Number.parseInt(String(value).replace(/[^\d]/g, ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  if (parsed >= 1_000_000) {
    const m = parsed / 1_000_000;
    return `${m >= 10 ? m.toFixed(0) : m.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (parsed >= 1_000) {
    const k = parsed / 1_000;
    return `${k >= 10 ? k.toFixed(0) : k.toFixed(1).replace(/\.0$/, "")}K`;
  }
  return String(parsed);
}

function formatVoiceBadge(value: string | undefined): string {
  const voice = (value || "").trim();
  if (!voice) return "";
  // "model:voice" → show just the voice segment to keep the chip compact.
  const tail = voice.includes(":")
    ? voice.slice(voice.lastIndexOf(":") + 1)
    : voice;
  return tail.length > 14 ? `${tail.slice(0, 13)}…` : tail;
}

function formatDimensionBadge(value: string | number | undefined): string {
  if (value === undefined || value === "") return "";
  const parsed =
    typeof value === "number"
      ? value
      : Number.parseInt(String(value).replace(/[^\d]/g, ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  return `${parsed}d`;
}

function formatIsoLocal(value: string | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
}

function ContextWindowMeta({ model }: { model: CatalogModel }) {
  const { t } = useTranslation();
  if (!model.context_window) return null;
  const source = formatContextWindowSource(model.context_window_source, t);
  const updatedAt = formatIsoLocal(model.context_window_detected_at);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-[var(--muted-foreground)]">
      <span>{t("Source")}:</span>
      <span className="text-[var(--foreground)]/80">{source}</span>
      {updatedAt && (
        <>
          <span className="text-[var(--muted-foreground)]/40">·</span>
          <span title={model.context_window_detected_at}>{updatedAt}</span>
        </>
      )}
    </div>
  );
}

function ContextWindowDetectionBanner({
  model,
  detection,
  onApply,
}: {
  model: CatalogModel;
  detection: LlmContextWindowDetection | null;
  onApply: () => void;
}) {
  const { t } = useTranslation();
  if (!detection) return null;
  const currentRaw = Number.parseInt(
    String(model.context_window || "").replace(/[^\d]/g, ""),
    10,
  );
  const matches =
    Number.isFinite(currentRaw) && currentRaw === detection.contextWindow;
  const detectedFormatted = detection.contextWindow.toLocaleString("en-US");
  const detectedAt = formatIsoLocal(detection.detectedAt);
  const source = formatContextWindowSource(detection.source, t);

  if (matches) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-[12px] text-[var(--muted-foreground)] sm:col-span-2">
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
        <span className="text-[var(--foreground)]/80">
          {t("Detected value matches your current setting")}
        </span>
        <span className="text-[var(--muted-foreground)]/70">
          ({detectedFormatted} · {source})
        </span>
      </div>
    );
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 px-3 py-2 sm:col-span-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12px]">
        <span className="text-[var(--muted-foreground)]">{t("Detected")}:</span>
        <span className="font-mono text-[13px] font-medium text-[var(--foreground)] tabular-nums">
          {detectedFormatted}
        </span>
        <span className="text-[var(--muted-foreground)]/80">· {source}</span>
        {detectedAt && (
          <span className="text-[var(--muted-foreground)]/60">
            · {detectedAt}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onApply}
        className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--background)] px-2.5 py-1 text-[11.5px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--foreground)]"
      >
        {t("Apply")}
      </button>
    </div>
  );
}

function ProfileFields({
  service,
  profile,
  showApiKey,
  setShowApiKey,
  showSearchProviderWarning,
  isSupportedSearchProvider,
  isDeprecatedSearchProvider,
  searchProviderMissingKey,
  supportedSearchProviderNames,
  onProviderChanged,
}: {
  service: ServiceName;
  profile: CatalogProfile;
  showApiKey: boolean;
  setShowApiKey: (next: boolean | ((prev: boolean) => boolean)) => void;
  showSearchProviderWarning: boolean;
  isSupportedSearchProvider: boolean;
  isDeprecatedSearchProvider: boolean;
  searchProviderMissingKey: boolean;
  supportedSearchProviderNames: string;
  onProviderChanged: (
    provider: ProviderOption,
    previousProvider: string,
  ) => void;
}) {
  const { t } = useTranslation();
  const {
    providers,
    draft,
    customProviderCapabilities,
    mutateCatalog,
    updateProfileField,
    updateModelField,
  } = useSettings();
  const [extraOpen, setExtraOpen] = useState(false);
  const [customDialog, setCustomDialog] = useState<
    { mode: "create" } | { mode: "edit"; definition: CustomProviderDefinition } | null
  >(null);

  const customService =
    service === "search" ? null : (service as CustomProviderService);
  const definitions = customService
    ? customProvidersForService(draft, customService)
    : [];
  const protocols = customService
    ? (customProviderCapabilities?.protocols[customService] ?? [])
    : [];
  const providerValue =
    service === "search" ? profile.provider || "" : profile.binding || "";
  const selectValue =
    service === "search" ? providerValue : customProviderSelectValue(profile);
  const providerOption = (providers[service] || []).find(
    (option) => option.value === providerValue,
  );
  const presentation = resolveProviderPresentation(
    draft,
    service as CustomProviderService,
    profile,
    providerOption?.label ?? providerValue,
  );
  const selectedDefinition = profile.custom_provider_id
    ? definitions.find((item) => item.id === profile.custom_provider_id) ?? null
    : null;
  const isManagedCodex = isManagedCodexProfile(profile);
  const isCodexOAuth = isCodexOAuthProfile(
    service,
    providerValue,
    providerOption,
    profile,
  );
  const isCodeBuddyAuth = service === "llm" && providerValue === "codebuddy";

  const fields =
    isCodexOAuth || isCodeBuddyAuth
      ? { apiKey: false, baseUrl: false, baseUrlRequired: false }
      : service === "search"
        ? searchProviderFields(profile.provider, providerOption)
        : { apiKey: true, baseUrl: true, baseUrlRequired: false };
  const missingRequiredBaseUrl =
    fields.baseUrlRequired && !String(profile.base_url || "").trim();

  const saveCustomProvider = (value: CustomProviderDialogValue) => {
    if (!customService) return;
    if (customDialog?.mode === "edit") {
      const definition = customDialog.definition;
      mutateCatalog((next) => {
        const target = (next.custom_providers || []).find(
          (item) => item.id === definition.id,
        );
        if (target) {
          target.name = value.name;
          target.icon = value.icon;
        }
      });
      setCustomDialog(null);
      return;
    }
    const id = newCustomProviderId();
    mutateCatalog((next) => {
      next.custom_providers = [
        ...(next.custom_providers || []),
        {
          id,
          service: customService,
          binding: value.binding,
          name: value.name,
          icon: value.icon,
        },
      ];
      const target = next.services[service].profiles.find(
        (item) => item.id === profile.id,
      );
      if (target) {
        target.binding = value.binding;
        target.custom_provider_id = id;
        target.name = nextProfileName(target.name, presentation.providerLabel, value.name);
      }
    });
    setCustomDialog(null);
  };

  const chooseCustomDefinition = (id: string) => {
    const definition = definitions.find((item) => item.id === id);
    if (!definition) return;
    mutateCatalog((next) => {
      const target = next.services[service].profiles.find(
        (item) => item.id === profile.id,
      );
      if (target) {
        target.binding = definition.binding;
        target.custom_provider_id = definition.id;
        target.name = nextProfileName(target.name, presentation.providerLabel, definition.name);
      }
    });
  };

  return (
    <>
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <div className="text-[12px] text-[var(--muted-foreground)]">
            {t("Provider")}
          </div>
          {selectedDefinition && (
            <button
              type="button"
              data-testid="edit-custom-provider"
              onClick={() =>
                setCustomDialog({ mode: "edit", definition: selectedDefinition })
              }
              className="text-[11px] font-medium text-[var(--foreground)] underline-offset-2 hover:underline"
            >
              {t("Edit provider")}
            </button>
          )}
        </div>
        <div className="relative">
          {providerValue && (
            <ProviderIcon
              provider={providerValue}
              icon={presentation.providerIcon}
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"
            />
          )}
          <select
            className={`${selectClass} ${providerValue ? "pl-9" : ""}`}
            value={selectValue}
            disabled={isManagedCodex}
            data-testid={`provider-select-${service}`}
            onChange={(e) => {
              const val = e.target.value;
              if (customService && val === CUSTOM_PROVIDER_SENTINEL) {
                setCustomDialog({ mode: "create" });
                return;
              }
              const customId = customProviderIdFromSelectValue(val);
              if (customService && customId) {
                chooseCustomDefinition(customId);
                return;
              }
              const field = service === "search" ? "provider" : "binding";
              const options = providers[service] || [];
              const previousLabel =
                resolveProviderPresentation(
                  draft,
                  service as CustomProviderService,
                  profile,
                  options.find((p) => p.value === providerValue)?.label ?? "",
                ).providerLabel || "";
              const match = options.find((p) => p.value === val);
              mutateCatalog((next) => {
                const target = next.services[service].profiles.find(
                  (item) => item.id === profile.id,
                );
                if (target) {
                  target[field] = val;
                  if (field === "binding") delete target.custom_provider_id;
                }
              });
              // Keep an un-customized profile name tracking its provider.
              const renamed = nextProfileName(
                profile.name,
                previousLabel,
                match?.label ?? "",
              );
              if (renamed !== profile.name) {
                updateProfileField(service, "name", renamed);
              }
              if (val === "codebuddy") {
                updateProfileField(service, "base_url", "");
                updateProfileField(service, "api_key", "");
              } else if (match?.base_url) {
                updateProfileField(service, "base_url", match.base_url);
              }
              if (match) {
                onProviderChanged(match, providerValue);
              }
              if (service === "embedding" && match?.default_dim) {
                updateModelField(service, "dimension", match.default_dim);
              }
              if (
                (service === "tts" ||
                  service === "stt" ||
                  service === "imagegen" ||
                  service === "videogen") &&
                match?.default_model
              ) {
                updateModelField(service, "model", match.default_model);
              }
              if (service === "tts" && match?.default_voice) {
                updateModelField(service, "voice", match.default_voice);
              }
            }}
          >
            <option className={selectOptionClass} value="">
              {t("Select provider...")}
            </option>
            {(providers[service] || [])
              .filter((p) => p.status !== "deprecated")
              .map((p) => (
                <option
                  className={selectOptionClass}
                  key={p.value}
                  value={p.value}
                  data-testid={`provider-option-${service}-${p.value}`}
                >
                  {localizeProviderLabel(p.label, t)}
                </option>
              ))}
            {customService &&
              definitions.map((definition) => (
                <option
                  className={selectOptionClass}
                  key={definition.id}
                  value={`cp:${definition.id}`}
                  data-testid="custom-provider-option"
                  data-custom-provider-id={definition.id}
                >
                  {definition.name}
                </option>
              ))}
            {customService && (
              <option
                className={selectOptionClass}
                value={CUSTOM_PROVIDER_SENTINEL}
                data-testid="custom-provider-create-option"
              >
                {t("Custom provider configuration…")}
              </option>
            )}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
        </div>
        {showSearchProviderWarning && (
          <p
            className={`mt-1.5 text-[11px] ${
              isSupportedSearchProvider
                ? "text-emerald-600 dark:text-emerald-400"
                : isDeprecatedSearchProvider
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-red-500"
            }`}
          >
            {isSupportedSearchProvider
              ? searchProviderMissingKey
                ? t(
                    "{{provider}} requires an API key. It will fail hard without credentials.",
                    { provider: providerOption?.label ?? providerValue },
                  )
                : t("Supported provider.")
              : isDeprecatedSearchProvider
                ? t("Deprecated provider. Switch to one of: {{providers}}.", {
                    providers: supportedSearchProviderNames,
                  })
                : t("Unsupported provider. Use one of: {{providers}}.", {
                    providers: supportedSearchProviderNames,
                  })}
          </p>
        )}
      </div>
      {isCodexOAuth && (
        <div className="sm:col-span-2">
          <CodexOAuthCard />
        </div>
      )}
      {isCodeBuddyAuth && (
        <div className="sm:col-span-2">
          <CodeBuddyAuthCard />
        </div>
      )}
      {fields.baseUrl && (
        <div className="sm:col-span-2">
          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
            {service === "embedding" ? t("Endpoint URL") : t("Base URL")}
          </div>
          <input
            className={inputClass}
            value={profile.base_url}
            onChange={(e) =>
              updateProfileField(service, "base_url", e.target.value)
            }
            placeholder={
              service === "embedding"
                ? "https://api.openai.com/v1/embeddings"
                : service === "search"
                  ? "http://localhost:8888"
                  : "https://api.openai.com/v1"
            }
          />
          {service === "embedding" && (
            <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
              {t(
                "Embedding requests are sent to this URL exactly; DeepTutor does not append /embeddings or /api/embed at request time.",
              )}
            </p>
          )}
          {missingRequiredBaseUrl && (
            <p className="mt-1.5 text-[11px] text-amber-600 dark:text-amber-400">
              {t("Required — without it, search falls back to DuckDuckGo.")}
            </p>
          )}
        </div>
      )}
      {fields.apiKey && (
        <div className="sm:col-span-2">
          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
            {t("API Key")}
          </div>
          <div className="relative">
            <input
              type={showApiKey ? "text" : "password"}
              autoComplete="new-password"
              spellCheck={false}
              className={`${inputClass} pr-10 font-mono`}
              value={profile.api_key}
              onChange={(e) =>
                updateProfileField(service, "api_key", e.target.value)
              }
              placeholder="sk-..."
            />
            <button
              type="button"
              onClick={() => setShowApiKey((prev) => !prev)}
              className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
              aria-label={showApiKey ? t("Hide API key") : t("Show API key")}
              title={showApiKey ? t("Hide API key") : t("Show API key")}
            >
              {showApiKey ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      )}
      {!isCodexOAuth && !isCodeBuddyAuth && (
        <div className="sm:col-span-2 rounded-xl border border-[var(--border)]/60 bg-[var(--muted)]/20">
          <button
            type="button"
            data-testid="profile-extra-toggle"
            onClick={() => setExtraOpen((value) => !value)}
            className="flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left"
            aria-expanded={extraOpen}
          >
            <span>
              <span className="block text-[12px] font-medium text-[var(--foreground)]">
                {t("Extra (optional)")}
              </span>
              <span className="mt-0.5 block text-[11px] text-[var(--muted-foreground)]">
                {service === "search"
                  ? t("API version and proxy")
                  : t("API version and extra request headers")}
              </span>
            </span>
            <ChevronDown
              className={`h-4 w-4 text-[var(--muted-foreground)] transition-transform ${
                extraOpen ? "rotate-180" : ""
              }`}
            />
          </button>
          {extraOpen && (
            <div className="grid gap-4 border-t border-[var(--border)]/60 px-3.5 py-4 sm:grid-cols-2">
              <div>
                <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                  {t("API Version")}
                </div>
                <input
                  className={inputClass}
                  value={profile.api_version}
                  onChange={(e) =>
                    updateProfileField(service, "api_version", e.target.value)
                  }
                  placeholder={t("Optional")}
                />
              </div>
              {service !== "search" ? (
                <div className="sm:col-span-2">
                  <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                    {t("Model directory URL (optional)")}
                  </div>
                  <input
                    className={inputClass}
                    data-testid="model-directory-url"
                    value={profile.model_directory_url || ""}
                    onChange={(e) =>
                      updateProfileField(
                        service,
                        "model_directory_url",
                        e.target.value,
                      )
                    }
                    placeholder="https://gateway.example/school/ai/v1/models"
                  />
                  <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    {t(
                      "A complete read-only directory URL. It never changes the chat Base URL, and changing its origin requires re-entering a masked credential.",
                    )}
                  </p>
                </div>
              ) : null}
              {service === "search" ? (
                <div>
                  <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                    {t("Proxy")}
                  </div>
                  <input
                    className={inputClass}
                    value={profile.proxy || ""}
                    onChange={(e) =>
                      updateProfileField(service, "proxy", e.target.value)
                    }
                    placeholder={t("http://127.0.0.1:7890 (optional)")}
                  />
                </div>
              ) : (
                <div className="sm:col-span-2">
                  <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                    {t("Extra Headers (JSON)")}
                  </div>
                  <textarea
                    className={`${inputClass} min-h-[84px] resize-y`}
                    value={stringifyExtraHeaders(profile.extra_headers)}
                    onChange={(e) =>
                      updateProfileField(
                        service,
                        "extra_headers",
                        e.target.value,
                      )
                    }
                    placeholder='{"APP-Code":"your-app-code"}'
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {customDialog && customService && (
        <CustomProviderDialog
          service={customService}
          mode={customDialog.mode}
          initial={
            customDialog.mode === "edit" ? customDialog.definition : null
          }
          protocols={protocols}
          definitions={definitions}
          onCancel={() => setCustomDialog(null)}
          onSave={saveCustomProvider}
        />
      )}
    </div>
    </>
  );
}

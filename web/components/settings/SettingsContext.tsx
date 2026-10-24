"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import type { CodeBlockThemeId } from "@/components/common/code-block-themes";
import {
  normalizeCodeBlockTheme,
  writeStoredCodeBlockShowLineNumbers,
  writeStoredCodeBlockTheme,
  writeStoredCodeBlockWrapLongLines,
  writeStoredLanguage,
  writeStoredResponseLanguage,
} from "@/context/app-shell-storage";
import { useAppShell } from "@/context/AppShellContext";
import { apiFetch, apiUrl } from "@/lib/api";
import { invalidateLLMOptionsCache } from "@/lib/llm-options";
import { DEFAULT_MODEL_SERVICES, revisionAfterDefaultPatch } from "@/lib/default-models";
import { setModelReasoningEffort } from "@/lib/reasoning-effort";
import {
  reasoningControlsKey,
  type ReasoningControls,
} from "@/lib/reasoning-controls";
import { setTheme as applyThemePreference } from "@/lib/theme";
import type {
  ParameterOverrides,
  ProviderMetadata,
} from "@/lib/model-metadata";
import type {
  CustomProviderCapabilities,
  CustomProviderDefinition,
  ProviderIconSpec,
} from "@/lib/custom-providers";

// ─── Domain types ─────────────────────────────────────────────────────────

export type ServiceName =
  | "llm"
  | "embedding"
  | "search"
  | "tts"
  | "stt"
  | "imagegen"
  | "videogen"
  | "vision";

export type CatalogModel = {
  id: string;
  name: string;
  model: string;
  managed_by?: string;
  dimension?: string;
  send_dimensions?: boolean;
  supported_dimensions?: string;
  context_window?: string;
  context_window_source?: string;
  context_window_detected_at?: string;
  /** Provider/endpoint capability facts and their provenance. */
  provider_metadata?: ProviderMetadata;
  /** User-editable default output budget; never the provider maximum itself. */
  max_tokens?: string;
  /** Input-only limit, shown separately from total context. */
  max_input_tokens?: string;
  /** true means the user explicitly overrode the automatic value. */
  parameter_overrides?: ParameterOverrides;
  // Display preference only; missing means visible and is never migrated.
  // Hiding keeps the model id, parameters, grants, and existing sessions.
  visible_in_picker?: boolean;
  reasoning_effort?: string;
  codex_supported_reasoning_levels?: string[];
  // Voice (TTS): free-form provider/model-specific voice string, e.g.
  // "alloy", "autumn", "model:voice". `response_format` is the TTS output
  // codec (mp3/wav/...) and is reused by imagegen ("url"/"b64_json").
  // `language` is an optional STT hint.
  voice?: string;
  response_format?: string;
  language?: string;
  // Image generation: pixel size (e.g. "1024x1024"), quality, and style.
  size?: string;
  quality?: string;
  style?: string;
  // Video generation: aspect ratio (e.g. "16:9"), duration (seconds), resolution.
  aspect_ratio?: string;
  duration?: string;
  resolution?: string;
};

export type LlmContextWindowDetection = {
  profileId: string | null;
  modelId: string | null;
  contextWindow: number;
  source: string;
  detail?: string;
  detectedAt?: string;
};

export type CatalogProfile = {
  id: string;
  name: string;
  managed_by?: string;
  codex_account_binding?: string;
  read_only?: boolean;
  binding?: string;
  provider?: string;
  custom_provider_id?: string;
  base_url: string;
  api_key: string;
  api_version: string;
  extra_headers?: Record<string, string> | string;
  /** Optional complete directory URL; never a chat URL and never persisted as base_url. */
  model_directory_url?: string;
  proxy?: string;
  max_results?: number;
  models: CatalogModel[];
};

export type CatalogService = {
  active_profile_id: string | null;
  active_model_id?: string | null;
  profiles: CatalogProfile[];
};

/** Local editor position. Never written through until an explicit default
 *  action or the ordinary Save/Apply of real configuration changes. */
export type EditingSelection = {
  profileId: string | null;
  modelId: string | null;
};

export type DefaultModelReference = {
  profile_id: string;
  model_id?: string | null;
};

export type DefaultModelReferenceMap = Partial<Record<ServiceName, DefaultModelReference | null>>;

export type Catalog = {
  version: number;
  /** Optional named provider definitions; missing means none. */
  custom_providers?: CustomProviderDefinition[];
  services: {
    llm: CatalogService;
    embedding: CatalogService;
    search: CatalogService;
    tts: CatalogService;
    stt: CatalogService;
    imagegen: CatalogService;
    videogen: CatalogService;
    vision: CatalogService;
  };
};

export type UiSettings = {
  theme: "light" | "dark" | "glass" | "snow";
  language: "en" | "zh";
  response_language: "en" | "zh";
  code_block_theme: string;
  code_block_show_line_numbers: boolean;
  code_block_wrap_long_lines: boolean;
};

type CodeBlockUiSettings = Pick<
  UiSettings,
  | "code_block_theme"
  | "code_block_show_line_numbers"
  | "code_block_wrap_long_lines"
>;

type UiSettingsPatch = Partial<UiSettings>;

export function syncLoadedCodeBlockSettingsToAppShell(
  ui: Partial<CodeBlockUiSettings>,
): CodeBlockUiSettings {
  const normalized = {
    code_block_theme: normalizeCodeBlockTheme(ui.code_block_theme),
    code_block_show_line_numbers:
      ui.code_block_show_line_numbers === true ||
      String(ui.code_block_show_line_numbers).toLowerCase() === "true",
    code_block_wrap_long_lines:
      ui.code_block_wrap_long_lines === true ||
      String(ui.code_block_wrap_long_lines).toLowerCase() === "true",
  };

  writeStoredCodeBlockTheme(normalized.code_block_theme);
  writeStoredCodeBlockShowLineNumbers(normalized.code_block_show_line_numbers);
  writeStoredCodeBlockWrapLongLines(normalized.code_block_wrap_long_lines);

  return normalized;
}

export async function persistUiSettingsPatch(
  patch: UiSettingsPatch,
  fetcher: typeof apiFetch = apiFetch,
): Promise<void> {
  await fetcher(apiUrl("/api/v1/settings/ui"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export type ProviderOption = {
  value: string;
  label: string;
  base_url?: string;
  default_dim?: string;
  default_model?: string;
  default_voice?: string;
  auth_mode?: "api_key" | "oauth";
  // Search providers only, from the backend SEARCH_PROVIDERS spec table:
  // which connection fields the provider consumes, whether missing ones fall
  // back to a free provider or fail hard, and whether it is still offered.
  requires_api_key?: boolean;
  requires_base_url?: boolean;
  soft_fallback?: boolean;
  status?: "supported" | "deprecated";
};

export type SystemStatus = {
  backend: { status: string; timestamp: string };
  llm: { status: string; model?: string; error?: string };
  embeddings: { status: string; model?: string; error?: string };
  search: { status: string; provider?: string; error?: string };
};

export type EmbeddingCapabilities = {
  detected_dim?: number;
  default_dim?: number;
  supported_dimensions?: number[];
  supports_variable_dimensions?: boolean;
  model_known?: boolean;
  active_dim?: number;
  active_dim_source?: string;
};

export type DiagnosticsResult = {
  state: "success" | "failed";
  message: string;
  profileId: string | null;
  modelId: string | null;
};

export type ServiceReadiness =
  | "not_configured"
  | "untested"
  | "passed"
  | "failed";

type SettingsPayload = {
  ui: UiSettings;
  catalog?: Catalog;
  providers?: Record<ServiceName, ProviderOption[]>;
  catalog_revision?: string;
  reasoning_controls?: Record<string, ReasoningControls>;
  custom_provider_capabilities?: CustomProviderCapabilities;
};

const DIAGNOSTICS_RESULTS_KEY = "deeptutor.settings.diagnosticsResults.v1";

// ─── Tour ──────────────────────────────────────────────────────────────────
//
// The tour now spans routes — each step names the sub-page it lives on so the
// controller can navigate there before the spotlight resolves a target. Adding
// a new step is a matter of pushing onto this list; the overlay reads the
// target via ``data-tour=""`` after the page has rendered.

export type TourStep = {
  target: string;
  route: string;
  titleKey: string;
  descKey: string;
};

// Tour step order broadly follows the category order in
// ``web/lib/settings-nav.ts`` so the guided walk moves through the hub's
// sections top to bottom. Each step names the route it lives on (the Status
// step targets the resident module on the hub itself); the overlay resolves
// the ``data-tour`` target after the page renders.
export const TOUR_STEPS: TourStep[] = [
  {
    target: "tour-status",
    route: "/settings",
    titleKey: "settingsTour.status.title",
    descKey: "settingsTour.status.desc",
  },
  {
    target: "tour-cat-appearance",
    route: "/settings",
    titleKey: "settingsTour.appearance.title",
    descKey: "settingsTour.appearance.desc",
  },
  {
    target: "tour-cat-network",
    route: "/settings",
    titleKey: "settingsTour.network.title",
    descKey: "settingsTour.network.desc",
  },
  {
    target: "tour-cat-models",
    route: "/settings",
    titleKey: "settingsTour.models.title",
    descKey: "settingsTour.models.desc",
  },
  {
    target: "tour-cat-knowledge",
    route: "/settings",
    titleKey: "settingsTour.knowledge.title",
    descKey: "settingsTour.knowledge.desc",
  },
  {
    target: "tour-cat-chat",
    route: "/settings",
    titleKey: "settingsTour.chat.title",
    descKey: "settingsTour.chat.desc",
  },
  {
    target: "tour-cat-memory",
    route: "/settings",
    titleKey: "settingsTour.memory.title",
    descKey: "settingsTour.memory.desc",
  },
];

// ─── Helpers ───────────────────────────────────────────────────────────────

export function cloneCatalog(catalog: Catalog): Catalog {
  return JSON.parse(JSON.stringify(catalog)) as Catalog;
}

/** TTS/STT share the catalog shape but configure audio providers. */
export function voiceService(service: ServiceName): boolean {
  return service === "tts" || service === "stt";
}

/** imagegen/videogen share the catalog shape but configure media generation. */
export function generationService(service: ServiceName): boolean {
  return service === "imagegen" || service === "videogen";
}

/** Services whose model entry should prefill from the provider's default model. */
function prefillsDefaultModel(service: ServiceName): boolean {
  return voiceService(service) || generationService(service);
}

export function defaultCatalog(): Catalog {
  return {
    version: 1,
    services: {
      llm: { active_profile_id: null, active_model_id: null, profiles: [] },
      embedding: {
        active_profile_id: null,
        active_model_id: null,
        profiles: [],
      },
      search: { active_profile_id: null, profiles: [] },
      tts: { active_profile_id: null, active_model_id: null, profiles: [] },
      stt: { active_profile_id: null, active_model_id: null, profiles: [] },
      imagegen: {
        active_profile_id: null,
        active_model_id: null,
        profiles: [],
      },
      videogen: {
        active_profile_id: null,
        active_model_id: null,
        profiles: [],
      },
      vision: { active_profile_id: null, active_model_id: null, profiles: [] },
    },
  };
}

export function getActiveProfile(
  catalog: Catalog,
  serviceName: ServiceName,
): CatalogProfile | null {
  const service = catalog.services[serviceName];
  return (
    service.profiles.find(
      (profile) => profile.id === service.active_profile_id,
    ) ??
    service.profiles[0] ??
    null
  );
}

export function getActiveModel(
  catalog: Catalog,
  serviceName: ServiceName,
): CatalogModel | null {
  if (serviceName === "search") return null;
  const service = catalog.services[serviceName];
  const profile = getActiveProfile(catalog, serviceName);
  if (!profile) return null;
  return (
    profile.models.find((model) => model.id === service.active_model_id) ??
    profile.models[0] ??
    null
  );
}

/** Resolve the local editor target without consulting or mutating defaults. */
export function resolveEditingSelection(
  catalog: Catalog,
  serviceName: ServiceName,
  selection?: Partial<EditingSelection> | null,
): {
  profile: CatalogProfile | null;
  model: CatalogModel | null;
  profileId: string | null;
  modelId: string | null;
} {
  const service = catalog.services[serviceName];
  const preferredProfileId = selection?.profileId ?? null;
  const profile =
    service.profiles.find((item) => item.id === preferredProfileId) ??
    service.profiles.find((item) => item.id === service.active_profile_id) ??
    service.profiles[0] ??
    null;
  if (!profile) {
    return { profile: null, model: null, profileId: null, modelId: null };
  }
  const preferredModelId = selection?.modelId ?? null;
  const activeModelId =
    profile.id === service.active_profile_id ? service.active_model_id : null;
  const model =
    profile.models.find((item) => item.id === preferredModelId) ??
    profile.models.find((item) => item.id === activeModelId) ??
    profile.models[0] ??
    null;
  return {
    profile,
    model,
    profileId: profile.id,
    modelId: model?.id ?? null,
  };
}

export function getEditingProfile(
  catalog: Catalog,
  serviceName: ServiceName,
  selection?: Partial<EditingSelection> | null,
): CatalogProfile | null {
  return resolveEditingSelection(catalog, serviceName, selection).profile;
}

export function getEditingModel(
  catalog: Catalog,
  serviceName: ServiceName,
  selection?: Partial<EditingSelection> | null,
): CatalogModel | null {
  return resolveEditingSelection(catalog, serviceName, selection).model;
}

export function serviceConfigured(
  catalog: Catalog,
  serviceName: ServiceName,
): boolean {
  return serviceName === "search"
    ? Boolean(getActiveProfile(catalog, serviceName)?.provider)
    : Boolean(getActiveModel(catalog, serviceName)?.model);
}

export function currentDiagnosticsResult(
  catalog: Catalog,
  serviceName: ServiceName,
  diagnosticsResults: Partial<Record<ServiceName, DiagnosticsResult>>,
): DiagnosticsResult | null {
  const service = catalog.services[serviceName];
  const diagnostics = diagnosticsResults[serviceName];
  if (!diagnostics) return null;
  const profileId = service.active_profile_id ?? null;
  const modelId =
    serviceName === "search" ? null : (service.active_model_id ?? null);
  return diagnostics.profileId === profileId && diagnostics.modelId === modelId
    ? diagnostics
    : null;
}

export function serviceReadiness(
  catalog: Catalog,
  serviceName: ServiceName,
  diagnosticsResults: Partial<Record<ServiceName, DiagnosticsResult>>,
): ServiceReadiness {
  if (!serviceConfigured(catalog, serviceName)) return "not_configured";
  const diagnostics = currentDiagnosticsResult(
    catalog,
    serviceName,
    diagnosticsResults,
  );
  if (diagnostics?.state === "failed") return "failed";
  if (diagnostics?.state === "success") return "passed";
  return "untested";
}

export function servicePendingApply(
  catalog: Catalog,
  draft: Catalog,
  service: ServiceName,
): boolean {
  return (
    JSON.stringify(catalog.services[service]) !==
    JSON.stringify(draft.services[service])
  );
}

function nextModelName(
  models: CatalogModel[],
  language: UiSettings["language"],
): string {
  const prefix = language === "zh" ? "模型" : "Model ";
  const used = new Set(models.map((model) => model.name.trim()));
  let index = models.length + 1;
  while (used.has(`${prefix}${index}`)) {
    index += 1;
  }
  return `${prefix}${index}`;
}

function readStoredDiagnosticsResults(): Partial<
  Record<ServiceName, DiagnosticsResult>
> {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(
      window.sessionStorage.getItem(DIAGNOSTICS_RESULTS_KEY) || "{}",
    ) as Partial<Record<ServiceName, DiagnosticsResult>>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

// ─── Context ───────────────────────────────────────────────────────────────

export interface SettingsExtension {
  dirty: boolean;
  save: () => Promise<void>;
}

type SettingsContextValue = {
  // State
  catalog: Catalog;
  draft: Catalog;
  /** Opaque revision of the saved catalog, used for lock-safe writes. */
  catalogRevision: string | null;
  editingSelections: Partial<Record<ServiceName, EditingSelection>>;
  reasoningControls: Record<string, ReasoningControls>;
  customProviderCapabilities: CustomProviderCapabilities | null;
  status: SystemStatus | null;
  providers: Record<ServiceName, ProviderOption[]>;
  catalogEditable: boolean | null;
  settingsLoading: boolean;
  settingsError: string | null;
  reloadSettings: () => Promise<void>;
  hasUnsavedChanges: boolean;
  theme: UiSettings["theme"];
  language: UiSettings["language"];
  responseLanguage: UiSettings["response_language"];
  codeBlockTheme: UiSettings["code_block_theme"];
  codeBlockShowLineNumbers: UiSettings["code_block_show_line_numbers"];
  codeBlockWrapLongLines: UiSettings["code_block_wrap_long_lines"];
  toast: string;
  setToast: (value: string) => void;

  // UI prefs
  updateTheme: (next: UiSettings["theme"]) => Promise<void>;
  updateLanguage: (next: UiSettings["language"]) => Promise<void>;
  updateResponseLanguage: (
    next: UiSettings["response_language"],
  ) => Promise<void>;
  updateCodeBlockTheme: (next: CodeBlockThemeId) => Promise<void>;
  updateCodeBlockShowLineNumbers: (next: boolean) => Promise<void>;
  updateCodeBlockWrapLongLines: (next: boolean) => Promise<void>;

  // Catalog mutation
  mutateCatalog: (mutator: (next: Catalog) => void) => void;
  selectEditingProfile: (service: ServiceName, profileId: string) => void;
  selectEditingModel: (service: ServiceName, modelId: string) => void;
  addProfile: (service: ServiceName) => void;
  removeEditingProfile: (service: ServiceName) => void;
  addModel: (service: ServiceName) => void;
  removeEditingModel: (service: ServiceName) => void;
  updateProfileField: (
    service: ServiceName,
    field: keyof CatalogProfile,
    value: string,
  ) => void;
  updateModelField: (
    service: ServiceName,
    field: keyof CatalogModel,
    value: string,
  ) => void;
  updateModelBoolField: (
    service: ServiceName,
    field: keyof CatalogModel,
    value: boolean,
  ) => void;
  updateContextWindowField: (value: string) => void;
  updateLlmBudgetField: (value: string) => void;
  updateEmbeddingDimensionField: (value: string) => void;
  updateEmbeddingSendDimensions: (value: boolean) => void;
  updateReasoningEffort: (value: string) => void;
  llmContextDetection: LlmContextWindowDetection | null;
  applyDetectedContextWindow: () => void;

  // Save / apply
  saving: boolean;
  applying: boolean;
  saveCatalog: () => Promise<void>;
  applyCatalog: () => Promise<void>;
  /** Merge only active references returned by the default-models PATCH. */
  applySavedDefaultReferences: (
    defaults: DefaultModelReferenceMap,
    revision: string,
    baseRevision: string,
  ) => void;

  // Sub-page extension hooks. Sub-routes (e.g. /settings/memory) that own
  // state outside the catalog register a "dirty + save" pair so the global
  // Apply button can flush them alongside the catalog. Re-register on every
  // render — the latest closure wins.
  registerExtension: (key: string, ext: SettingsExtension | null) => void;

  // Diagnostics
  logs: string;
  testRunning: ServiceName | null;
  diagnosticsResults: Partial<Record<ServiceName, DiagnosticsResult>>;
  embeddingCapabilities: EmbeddingCapabilities | null;
  runDetailedTest: (service: ServiceName) => Promise<void>;

  // Helpers
  embeddingDefaultDim: (binding?: string) => string;

  // Tour
  tourStepIndex: number;
  startTour: () => void;
  advanceTour: () => void;
  goBackTour: () => void;
  skipTour: () => void;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error("useSettings must be used inside <SettingsProvider>");
  }
  return ctx;
}

// ─── Provider ──────────────────────────────────────────────────────────────

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const router = useRouter();
  // Code-block appearance lives in AppShellContext (the single source of truth,
  // also consumed by RichCodeBlock). Read the values from there and delegate
  // writes to its setters; this provider only adds backend persistence on top.
  const {
    codeBlockTheme,
    codeBlockShowLineNumbers,
    codeBlockWrapLongLines,
    setCodeBlockTheme: setAppShellCodeBlockTheme,
    setCodeBlockShowLineNumbers: setAppShellCodeBlockShowLineNumbers,
    setCodeBlockWrapLongLines: setAppShellCodeBlockWrapLongLines,
  } = useAppShell();

  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [theme, setTheme] = useState<UiSettings["theme"]>("snow");
  const [language, setLanguage] = useState<UiSettings["language"]>("en");
  const [responseLanguage, setResponseLanguage] =
    useState<UiSettings["response_language"]>("en");
  const [catalog, setCatalog] = useState<Catalog>(defaultCatalog());
  const [draft, setDraft] = useState<Catalog>(defaultCatalog());
  const [catalogRevision, setCatalogRevision] = useState<string | null>(null);
  const [editingSelections, setEditingSelections] = useState<
    Partial<Record<ServiceName, EditingSelection>>
  >({});
  const editingSelectionsRef = useRef(editingSelections);
  editingSelectionsRef.current = editingSelections;
  const [reasoningControls, setReasoningControls] = useState<
    Record<string, ReasoningControls>
  >({});
  const [customProviderCapabilities, setCustomProviderCapabilities] =
    useState<CustomProviderCapabilities | null>(null);
  const [catalogEditable, setCatalogEditable] = useState<boolean | null>(null);
  const [providers, setProviders] = useState<
    Record<ServiceName, ProviderOption[]>
  >({
    llm: [],
    embedding: [],
    search: [],
    tts: [],
    stt: [],
    imagegen: [],
    videogen: [],
    vision: [],
  });
  const [toast, setToast] = useState("");
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  // Empty string is the "no diagnostics yet" sentinel; the editor renders
  // a localized placeholder when logs is falsy. Don't seed an English
  // literal here — older code did, then read it back via .startsWith.
  const [logs, setLogs] = useState<string>("");
  const [testRunning, setTestRunning] = useState<ServiceName | null>(null);
  const [diagnosticsResults, setDiagnosticsResults] = useState<
    Partial<Record<ServiceName, DiagnosticsResult>>
  >(() => readStoredDiagnosticsResults());
  const [llmContextDetection, setLlmContextDetection] =
    useState<LlmContextWindowDetection | null>(null);
  const [embeddingCapabilities, setEmbeddingCapabilities] =
    useState<EmbeddingCapabilities | null>(null);
  const [tourStepIndex, setTourStepIndex] = useState(-1);
  const eventSourceRef = useRef<EventSource | null>(null);
  // Extensions register their latest dirty/save on each render. Keep the
  // derived dirty state explicit instead of using an indirect version counter.
  const extensionsRef = useRef<Map<string, SettingsExtension>>(new Map());
  const [hasDirtyExtension, setHasDirtyExtension] = useState(false);
  const registerExtension = useCallback(
    (key: string, ext: SettingsExtension | null) => {
      const map = extensionsRef.current;
      const prev = map.get(key);
      if (ext === null) {
        if (prev === undefined) return;
        map.delete(key);
        setHasDirtyExtension(
          Array.from(map.values()).some((extension) => extension.dirty),
        );
        return;
      }
      if (prev && prev.dirty === ext.dirty && prev.save === ext.save) {
        return;
      }
      map.set(key, ext);
      // Only recompute the dirty summary when dirty flips — save fn changes
      // every render are common and should not re-render the toolbar.
      if (prev?.dirty !== ext.dirty) {
        setHasDirtyExtension(
          Array.from(map.values()).some((extension) => extension.dirty),
        );
      }
    },
    [],
  );

  const [settingsError, setSettingsError] = useState<string | null>(null);

  // Single load step. Kept separate from the mount effect so a "Retry" action
  // can re-run it without remounting the provider.
  const loadSettings = useCallback(async () => {
    setSettingsError(null);
    let settingsLoaded = false;
    try {
      const settingsResponse = await apiFetch(apiUrl("/api/v1/settings"));
      if (!settingsResponse.ok) {
        throw new Error(
          `Settings fetch failed: HTTP ${settingsResponse.status}`,
        );
      }
      const payload = (await settingsResponse.json()) as SettingsPayload;
      if (payload.catalog) {
        setCatalog(payload.catalog);
        setDraft(cloneCatalog(payload.catalog));
        setCatalogRevision(payload.catalog_revision ?? null);
        const loadedCatalog = payload.catalog;
        // Pin the initial editor targets too. Otherwise an editor that has
        // never switched tabs would still follow a newly saved default.
        setEditingSelections((current) => Object.fromEntries(
          DEFAULT_MODEL_SERVICES.map((service) => {
            const selected = resolveEditingSelection(loadedCatalog, service, current[service]);
            return [service, { profileId: selected.profileId, modelId: selected.modelId }];
          }),
        ));
        setReasoningControls(payload.reasoning_controls ?? {});
        setCustomProviderCapabilities(
          payload.custom_provider_capabilities ?? null,
        );
        setCatalogEditable(true);
      } else {
        setCatalogEditable(false);
      }
      setTheme(payload.ui.theme);
      setLanguage(payload.ui.language);
      setResponseLanguage(payload.ui.response_language ?? payload.ui.language);
      // Writes the backend-loaded values into app-shell storage and dispatches
      // the code-block settings event; AppShellContext (the single source) picks
      // them up, so no separate copy needs seeding here.
      syncLoadedCodeBlockSettingsToAppShell(payload.ui);
      if (payload.providers) setProviders(payload.providers);
      settingsLoaded = true;
    } catch (err) {
      console.error("Failed to load settings:", err);
      const message = err instanceof Error ? err.message : String(err);
      setSettingsError(message);
      // Resolve the loading gate so the page can render the error UI instead
      // of staying in an infinite skeleton state.
      setCatalogEditable((current) => (current === null ? false : current));
    }
    try {
      const statusResponse = await apiFetch(apiUrl("/api/v1/system/status"));
      if (statusResponse.ok) {
        setStatus((await statusResponse.json()) as SystemStatus);
      }
    } catch (err) {
      console.error("Failed to load system status:", err);
      // Only surface this when settings itself loaded; otherwise the
      // settings-fetch error already explains the disconnect.
      if (settingsLoaded) {
        setSettingsError(
          (current) =>
            current ??
            (err instanceof Error
              ? t("System status unavailable: {{message}}", {
                  message: err.message,
                })
              : t("System status unavailable.")),
        );
      }
    }
  }, [t]);

  // Load settings + status once on mount. Subsequent navigations between
  // settings sub-pages share this state via the layout-level provider.
  // Code-block switch hydration lives in AppShellContext (the single source),
  // so no separate post-mount re-read is needed here.
  useEffect(() => {
    loadSettings();
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, [loadSettings]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        DIAGNOSTICS_RESULTS_KEY,
        JSON.stringify(diagnosticsResults),
      );
    } catch {
      // Session storage is an enhancement for cross-route feedback only.
    }
  }, [diagnosticsResults]);

  // ── UI preferences ──────────────────────────────────────────────────────
  const updateTheme = useCallback(async (next: UiSettings["theme"]) => {
    setTheme(next);
    applyThemePreference(next);
    await persistUiSettingsPatch({ theme: next });
  }, []);

  const updateLanguage = useCallback(async (next: UiSettings["language"]) => {
    setLanguage(next);
    writeStoredLanguage(next);
    await persistUiSettingsPatch({ language: next });
  }, []);

  const updateResponseLanguage = useCallback(
    async (next: UiSettings["response_language"]) => {
      setResponseLanguage(next);
      writeStoredResponseLanguage(next);
      await persistUiSettingsPatch({ response_language: next });
    },
    [],
  );

  // Each setter updates the app-shell source of truth (which normalizes,
  // persists to localStorage, and notifies consumers) then mirrors the change
  // to the backend.
  const updateCodeBlockTheme = useCallback(
    async (next: CodeBlockThemeId) => {
      setAppShellCodeBlockTheme(next);
      await persistUiSettingsPatch({ code_block_theme: next });
    },
    [setAppShellCodeBlockTheme],
  );

  const updateCodeBlockShowLineNumbers = useCallback(
    async (next: boolean) => {
      setAppShellCodeBlockShowLineNumbers(next);
      await persistUiSettingsPatch({ code_block_show_line_numbers: next });
    },
    [setAppShellCodeBlockShowLineNumbers],
  );

  const updateCodeBlockWrapLongLines = useCallback(
    async (next: boolean) => {
      setAppShellCodeBlockWrapLongLines(next);
      await persistUiSettingsPatch({ code_block_wrap_long_lines: next });
    },
    [setAppShellCodeBlockWrapLongLines],
  );

  // ── Catalog mutators ────────────────────────────────────────────────────
  const mutateCatalog = useCallback((mutator: (next: Catalog) => void) => {
    setDraft((current) => {
      const next = cloneCatalog(current);
      mutator(next);
      return next;
    });
  }, []);

  const embeddingDefaultDim = useCallback(
    (binding?: string) => {
      const match = (providers.embedding || []).find(
        (p) => p.value === (binding || "openai"),
      );
      return match?.default_dim || "3072";
    },
    [providers.embedding],
  );

  const selectEditingProfile = useCallback(
    (service: ServiceName, profileId: string) => {
      setEditingSelections((current) => ({
        ...current,
        [service]: { profileId, modelId: null },
      }));
    },
    [],
  );

  const selectEditingModel = useCallback(
    (service: ServiceName, modelId: string) => {
      setEditingSelections((current) => {
        const selected = resolveEditingSelection(
          draft,
          service,
          current[service],
        );
        return {
          ...current,
          [service]: { profileId: selected.profileId, modelId },
        };
      });
    },
    [draft],
  );

  const addProfile = useCallback(
    (service: ServiceName) => {
      const profileId = `${service}-profile-${Date.now()}`;
      const modelId = `${service}-model-${Date.now()}`;
      const wasEmpty =
        draft.services[service].profiles.length === 0 &&
        !draft.services[service].active_profile_id;
      mutateCatalog((next) => {
        const target = next.services[service];
        const defaultBinding = service === "search" ? undefined : "openai";
        const defaultProvider = service === "search" ? "brave" : undefined;
        const providerKey =
          service === "search" ? defaultProvider : defaultBinding;
        const providerOption = (providers[service] || []).find(
          (p) => p.value === providerKey,
        );
        const providerLabel =
          providerOption?.label ?? providerKey ?? "New Profile";
        const profile: CatalogProfile = {
          id: profileId,
          name: providerLabel,
          binding: defaultBinding,
          provider: defaultProvider,
          base_url: "",
          api_key: "",
          api_version: "",
          extra_headers: service === "search" ? undefined : {},
          proxy: service === "search" ? "" : undefined,
          models: [],
        };
        if (service !== "search") {
          const modelName = nextModelName([], language);
          profile.models.push({
            id: modelId,
            name: modelName,
            model: prefillsDefaultModel(service)
              ? (providerOption?.default_model ?? "")
              : "",
            ...(service === "embedding"
              ? {
                  dimension: embeddingDefaultDim(),
                  send_dimensions: true,
                }
              : {}),
            ...(service === "tts"
              ? {
                  voice: providerOption?.default_voice ?? "",
                  response_format: "mp3",
                }
              : {}),
          });
        }
        target.profiles.push(profile);
        // Only the first configuration of an empty service initialises the
        // persisted default. Later additions are local editor selections.
        if (wasEmpty) {
          target.active_profile_id = profileId;
          if (service !== "search") target.active_model_id = modelId;
        }
      });
      setEditingSelections((current) => ({
        ...current,
        [service]: {
          profileId,
          modelId: service === "search" ? null : modelId,
        },
      }));
      if (wasEmpty) {
        setToast(
          t(
            "This is the first configuration for this service, so its first model is the initial saved default. Review and save the draft to apply it.",
          ),
        );
      }
    },
    [draft, embeddingDefaultDim, language, mutateCatalog, providers, setToast, t],
  );

  const removeEditingProfile = useCallback(
    (service: ServiceName) => {
      const selected = resolveEditingSelection(
        draft,
        service,
        editingSelectionsRef.current[service],
      );
      const profile = selected.profile;
      if (!profile) return;
      if (draft.services[service].active_profile_id === profile.id) {
        setToast(
          t(
            "This is the saved default connection. Choose another default before deleting it.",
          ),
        );
        return;
      }
      const remaining = draft.services[service].profiles.filter(
        (item) => item.id !== profile.id,
      );
      mutateCatalog((next) => {
        next.services[service].profiles = remaining;
      });
      const nextProfile = remaining[0] ?? null;
      setEditingSelections((current) => ({
        ...current,
        [service]: nextProfile
          ? {
              profileId: nextProfile.id,
              modelId: nextProfile.models[0]?.id ?? null,
            }
          : { profileId: null, modelId: null },
      }));
    },
    [draft, mutateCatalog, setToast, t],
  );

  const addModel = useCallback(
    (service: ServiceName) => {
      if (service === "search") return;
      const selected = resolveEditingSelection(
        draft,
        service,
        editingSelectionsRef.current[service],
      );
      if (!selected.profile) return;
      const profileId = selected.profile.id;
      const modelId = `${service}-model-${Date.now()}`;
      mutateCatalog((next) => {
        const profile = next.services[service].profiles.find(
          (item) => item.id === profileId,
        );
        if (!profile) return;
        const providerOption = (providers[service] || []).find(
          (p) => p.value === profile.binding,
        );
        const modelName = nextModelName(profile.models, language);
        profile.models.push({
          id: modelId,
          name: modelName,
          model: prefillsDefaultModel(service)
            ? (providerOption?.default_model ?? "")
            : "",
          ...(service === "embedding"
            ? {
                dimension: embeddingDefaultDim(profile.binding),
                send_dimensions: true,
              }
            : {}),
          ...(service === "tts"
            ? {
                voice: providerOption?.default_voice ?? "",
                response_format: "mp3",
              }
            : {}),
        });
      });
      setEditingSelections((current) => ({
        ...current,
        [service]: { profileId, modelId },
      }));
    },
    [draft, embeddingDefaultDim, language, mutateCatalog, providers],
  );

  const removeEditingModel = useCallback(
    (service: ServiceName) => {
      if (service === "search") return;
      const selected = resolveEditingSelection(
        draft,
        service,
        editingSelectionsRef.current[service],
      );
      const profile = selected.profile;
      const model = selected.model;
      if (!profile || !model) return;
      if (
        draft.services[service].active_profile_id === profile.id &&
        draft.services[service].active_model_id === model.id
      ) {
        setToast(
          t(
            "This is the saved default model. Choose another default before deleting it.",
          ),
        );
        return;
      }
      const remaining = profile.models.filter((item) => item.id !== model.id);
      mutateCatalog((next) => {
        const target = next.services[service].profiles.find(
          (item) => item.id === profile.id,
        );
        if (target) target.models = remaining;
      });
      setEditingSelections((current) => ({
        ...current,
        [service]: {
          profileId: profile.id,
          modelId: remaining[0]?.id ?? null,
        },
      }));
    },
    [draft, mutateCatalog, setToast, t],
  );

  const updateProfileField = useCallback(
    (service: ServiceName, field: keyof CatalogProfile, value: string) => {
      mutateCatalog((next) => {
        const profile = resolveEditingSelection(
          next,
          service,
          editingSelectionsRef.current[service],
        ).profile;
        if (!profile) return;
        (profile[field] as string | undefined) = value;
      });
    },
    [mutateCatalog],
  );

  const updateModelField = useCallback(
    (service: ServiceName, field: keyof CatalogModel, value: string) => {
      if (service === "search") return;
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          service,
          editingSelectionsRef.current[service],
        ).model;
        if (!model) return;
        (model[field] as string | undefined) = value;
      });
    },
    [mutateCatalog],
  );

  const updateModelBoolField = useCallback(
    (service: ServiceName, field: keyof CatalogModel, value: boolean) => {
      if (service === "search") return;
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          service,
          editingSelectionsRef.current[service],
        ).model;
        if (!model) return;
        (model[field] as boolean | undefined) = value;
      });
    },
    [mutateCatalog],
  );

  const updateContextWindowField = useCallback(
    (value: string) => {
      const normalized = value.replace(/[^\d]/g, "");
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          "llm",
          editingSelectionsRef.current.llm,
        ).model;
        if (!model) return;
        model.parameter_overrides = {
          ...(model.parameter_overrides ?? {}),
          context_window: true,
        };
        if (normalized) {
          model.context_window = normalized;
          model.context_window_source = "manual";
          delete model.context_window_detected_at;
        } else {
          delete model.context_window;
          delete model.context_window_source;
          delete model.context_window_detected_at;
        }
      });
    },
    [mutateCatalog],
  );

  const updateLlmBudgetField = useCallback(
    (value: string) => {
      const normalized = value.replace(/[^\d]/g, "");
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          "llm",
          editingSelectionsRef.current.llm,
        ).model;
        if (!model) return;
        model.parameter_overrides = {
          ...(model.parameter_overrides ?? {}),
          max_tokens: true,
        };
        if (normalized) model.max_tokens = normalized;
        else delete model.max_tokens;
      });
    },
    [mutateCatalog],
  );

  const updateEmbeddingDimensionField = useCallback(
    (value: string) => {
      const normalized = value.replace(/[^\d]/g, "");
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          "embedding",
          editingSelectionsRef.current.embedding,
        ).model;
        if (!model) return;
        model.parameter_overrides = {
          ...(model.parameter_overrides ?? {}),
          dimension: true,
        };
        if (normalized) model.dimension = normalized;
        else delete model.dimension;
      });
    },
    [mutateCatalog],
  );

  const updateEmbeddingSendDimensions = useCallback(
    (value: boolean) => {
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          "embedding",
          editingSelectionsRef.current.embedding,
        ).model;
        if (!model) return;
        model.parameter_overrides = {
          ...(model.parameter_overrides ?? {}),
          send_dimensions: true,
        };
        model.send_dimensions = value;
      });
    },
    [mutateCatalog],
  );

  const updateReasoningEffort = useCallback(
    (value: string) => {
      mutateCatalog((next) => {
        const model = resolveEditingSelection(
          next,
          "llm",
          editingSelectionsRef.current.llm,
        ).model;
        if (!model) return;
        setModelReasoningEffort(model, value);
      });
    },
    [mutateCatalog],
  );

  const applyDetectedContextWindow = useCallback(() => {
    if (!llmContextDetection) return;
    mutateCatalog((next) => {
      const profile = next.services.llm.profiles.find(
        (item) => item.id === llmContextDetection.profileId,
      );
      const model = profile?.models.find(
        (item) => item.id === llmContextDetection.modelId,
      );
      if (!model) return;
      model.context_window = String(llmContextDetection.contextWindow);
      model.context_window_source = llmContextDetection.source;
      if (llmContextDetection.detectedAt) {
        model.context_window_detected_at = llmContextDetection.detectedAt;
      } else {
        delete model.context_window_detected_at;
      }
    });
    setToast(t("Detected context window written to draft"));
  }, [llmContextDetection, mutateCatalog, t]);

  // ── Save / Apply ────────────────────────────────────────────────────────
  const saveCatalog = useCallback(async () => {
    if (!catalogEditable) return;
    setSaving(true);
    try {
      const response = await apiFetch(apiUrl("/api/v1/settings/catalog"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          catalog: draft,
          ...(catalogRevision ? { expected_revision: catalogRevision } : {}),
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        catalog?: Catalog;
        revision?: string;
        detail?: string | { message?: string; code?: string };
      };
      if (!response.ok || !payload.catalog) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : payload.detail?.message;
        throw new Error(
          detail || t("Could not save the draft (HTTP {{status}}).", {
            status: response.status,
          }),
        );
      }
      setCatalog(payload.catalog);
      setDraft(cloneCatalog(payload.catalog));
      setCatalogRevision(payload.revision ?? null);
      // The model list the chat composer shows is derived from this catalog.
      invalidateLLMOptionsCache();
      setToast(t("Draft saved"));
    } catch (error) {
      // Keep the dirty draft and the catalog visible so the user can fix the
      // error without losing unsaved candidate selections.
      setToast(
        error instanceof Error
          ? error.message
          : t("Could not save the draft."),
      );
    } finally {
      setSaving(false);
    }
  }, [catalogEditable, catalogRevision, draft, t]);

  const applyCatalog = useCallback(async () => {
    setApplying(true);
    try {
      // Flush extensions (e.g. /settings/memory) first so their saved
      // state is visible to any backend side-effects in /apply below.
      const exts = Array.from(extensionsRef.current.values()).filter(
        (e) => e.dirty,
      );
      await Promise.all(exts.map((e) => e.save()));

      // The catalog apply is only meaningful when editable; an extension-
      // only flush should still produce a success toast.
      if (catalogEditable) {
        const response = await apiFetch(apiUrl("/api/v1/settings/apply"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            catalog: draft,
            ...(catalogRevision ? { expected_revision: catalogRevision } : {}),
          }),
        });
        const payload = (await response.json().catch(() => ({}))) as {
          catalog?: Catalog;
          revision?: string;
          detail?: string | { message?: string; code?: string };
        };
        if (!response.ok || !payload.catalog) {
          const detail =
            typeof payload.detail === "string"
              ? payload.detail
              : payload.detail?.message;
          throw new Error(
            detail || t("Could not apply changes (HTTP {{status}}).", {
              status: response.status,
            }),
          );
        }
        setCatalog(payload.catalog);
        setDraft(cloneCatalog(payload.catalog));
        setCatalogRevision(payload.revision ?? null);
        invalidateLLMOptionsCache();
        const statusResponse = await apiFetch(apiUrl("/api/v1/system/status"));
        if (statusResponse.ok) {
          setStatus((await statusResponse.json()) as SystemStatus);
        }
      }
      setToast(t("All changes saved"));
    } catch (error) {
      setToast(
        error instanceof Error
          ? error.message
          : t("Could not apply changes."),
      );
    } finally {
      setApplying(false);
    }
  }, [catalogEditable, catalogRevision, draft, t]);

  const applySavedDefaultReferences = useCallback(
    (defaults: DefaultModelReferenceMap, revision: string, baseRevision: string) => {
      const mergeReferences = (catalogValue: Catalog): Catalog => {
        const next = cloneCatalog(catalogValue);
        for (const service of Object.keys(defaults) as ServiceName[]) {
          const reference = defaults[service];
          if (!reference) continue;
          next.services[service].active_profile_id = reference.profile_id;
          if (service !== "search") {
            next.services[service].active_model_id =
              reference.model_id ?? null;
          }
        }
        return next;
      };
      setCatalog((current) => mergeReferences(current));
      setDraft((current) => mergeReferences(current));
      setCatalogRevision((current) =>
        revisionAfterDefaultPatch(current, baseRevision, revision),
      );
      invalidateLLMOptionsCache();
    },
    [],
  );

  // ── Diagnostics ─────────────────────────────────────────────────────────
  // Reset capability snapshots when the *editor* target changes. Browsing a
  // different profile must not borrow another profile's diagnostic result.
  const llmEditing = resolveEditingSelection(
    draft,
    "llm",
    editingSelections.llm,
  );
  const embeddingEditing = resolveEditingSelection(
    draft,
    "embedding",
    editingSelections.embedding,
  );
  useEffect(() => {
    setEmbeddingCapabilities(null);
  }, [embeddingEditing.profileId, embeddingEditing.modelId]);

  useEffect(() => {
    setLlmContextDetection((current) => {
      if (!current) return null;
      if (
        current.profileId === llmEditing.profileId &&
        current.modelId === llmEditing.modelId
      ) {
        return current;
      }
      return null;
    });
  }, [llmEditing.profileId, llmEditing.modelId]);

  const runDetailedTest = useCallback(
    async (service: ServiceName) => {
      if (!catalogEditable) return;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setLogs(t("Preparing {{service}} diagnostics...", { service }) + "\n");
      setTestRunning(service);
      const selected = resolveEditingSelection(
        draft,
        service,
        editingSelectionsRef.current[service],
      );
      const runProfileId = selected.profileId;
      const runModelId = service === "search" ? null : selected.modelId;
      const diagnosticCatalog = cloneCatalog(draft);
      if (runProfileId) {
        diagnosticCatalog.services[service].active_profile_id = runProfileId;
        if (service !== "search") {
          diagnosticCatalog.services[service].active_model_id = runModelId;
        }
      }
      setDiagnosticsResults((current) => {
        const next = { ...current };
        delete next[service];
        return next;
      });
      if (service === "llm") setLlmContextDetection(null);
      if (service === "embedding") setEmbeddingCapabilities(null);
      try {
        const response = await apiFetch(
          apiUrl(`/api/v1/settings/tests/${service}/start`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ catalog: diagnosticCatalog }),
          },
        );
        const payload = (await response.json()) as {
          run_id?: string;
          detail?: string;
        };
        if (!response.ok || !payload.run_id) {
          throw new Error(payload.detail || t("Could not start diagnostics."));
        }
        const source = new EventSource(
          apiUrl(`/api/v1/settings/tests/${service}/${payload.run_id}/events`),
          { withCredentials: true },
        );
        eventSourceRef.current = source;
        source.onmessage = (event) => {
          const entry = JSON.parse(event.data) as {
            type: string;
            message: string;
            catalog?: Catalog;
            detected_dim?: number;
            default_dim?: number;
            supported_dimensions?: number[];
            supports_variable_dimensions?: boolean;
            model_known?: boolean;
            active_dim?: number;
            active_dim_source?: string;
            context_window?: number;
            source?: string;
            detail?: string;
            detected_at?: string;
          };
          setLogs((current) => `${current}[${entry.type}] ${entry.message}\n`);
          if (service === "llm" && entry.type === "context_window") {
            const detected =
              typeof entry.context_window === "number"
                ? entry.context_window
                : Number.parseInt(String(entry.context_window ?? ""), 10);
            if (Number.isFinite(detected) && detected > 0) {
              setLlmContextDetection({
                profileId: runProfileId,
                modelId: runModelId,
                contextWindow: detected,
                source: entry.source || "metadata",
                detail: entry.detail,
                detectedAt: entry.detected_at,
              });
            }
          }
          if (entry.type === "capabilities") {
            setEmbeddingCapabilities({
              detected_dim: entry.detected_dim,
              default_dim: entry.default_dim,
              supported_dimensions: entry.supported_dimensions,
              supports_variable_dimensions: entry.supports_variable_dimensions,
              model_known: entry.model_known,
              active_dim: entry.active_dim,
              active_dim_source: entry.active_dim_source,
            });
          }
          if (entry.catalog) {
            // Diagnostic runs target the local editor selection. Their
            // returned catalog is a draft update, never an implicit default
            // change: restore every active reference from the local draft.
            const mergeWithoutDefaults = (current: Catalog): Catalog => {
              const merged = cloneCatalog(entry.catalog as Catalog);
              for (const serviceName of Object.keys(
                merged.services,
              ) as ServiceName[]) {
                merged.services[serviceName].active_profile_id =
                  current.services[serviceName].active_profile_id;
                if (serviceName !== "search") {
                  merged.services[serviceName].active_model_id =
                    current.services[serviceName].active_model_id;
                }
              }
              return merged;
            };
            setCatalog(mergeWithoutDefaults);
            setDraft(mergeWithoutDefaults);
          }
          if (entry.type === "completed" || entry.type === "failed") {
            source.close();
            eventSourceRef.current = null;
            setTestRunning(null);
            setDiagnosticsResults((current) => ({
              ...current,
              [service]: {
                state: entry.type === "completed" ? "success" : "failed",
                message: entry.message,
                profileId: runProfileId,
                modelId: runModelId,
              },
            }));
            setToast(entry.message);
          }
        };
        source.onerror = () => {
          source.close();
          eventSourceRef.current = null;
          setTestRunning(null);
          setLogs(
            (current) =>
              `${current}[failed] ${t("Diagnostics stream disconnected.")}\n`,
          );
          setDiagnosticsResults((current) => ({
            ...current,
            [service]: {
              state: "failed",
              message: t("Diagnostics stream disconnected."),
              profileId: runProfileId,
              modelId: runModelId,
            },
          }));
          setToast(t("Diagnostics stream disconnected"));
        };
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : t("Could not start diagnostics.");
        setLogs((current) => `${current}[failed] ${message}\n`);
        setDiagnosticsResults((current) => ({
          ...current,
          [service]: {
            state: "failed",
            message,
            profileId: runProfileId,
            modelId: runModelId,
          },
        }));
        setToast(message);
        setTestRunning(null);
      }
    },
    [catalogEditable, draft, t],
  );

  // ── Tour ────────────────────────────────────────────────────────────────
  // The tour drives a SpotlightOverlay rendered by the layout. When the step
  // changes, we navigate to the step's route; the overlay then resolves the
  // target via data-tour after the page renders.
  const startTour = useCallback(() => {
    if (TOUR_STEPS.length === 0) return;
    setTourStepIndex(0);
    // No router.push here — the route-sync effect below handles it,
    // and doing it in two places would issue a redundant push.
  }, []);

  // Pure state updaters — DO NOT call router.push inside these. React
  // may invoke the updater twice in StrictMode, and triggering a
  // separate component's setState (Router) from inside a setState
  // callback raises "Cannot update a component while rendering another".
  // The route is synced via the effect below.
  const advanceTour = useCallback(() => {
    setTourStepIndex((idx) => {
      const nextIdx = idx + 1;
      return nextIdx >= TOUR_STEPS.length ? -1 : nextIdx;
    });
  }, []);

  const goBackTour = useCallback(() => {
    setTourStepIndex((idx) => (idx > 0 ? idx - 1 : idx));
  }, []);

  const skipTour = useCallback(() => {
    setTourStepIndex(-1);
  }, []);

  // Sync the URL to the current tour step. Runs after render commits
  // so it never re-enters another component's render.
  useEffect(() => {
    if (tourStepIndex < 0 || tourStepIndex >= TOUR_STEPS.length) return;
    const step = TOUR_STEPS[tourStepIndex];
    router.push(step.route);
  }, [tourStepIndex, router]);

  // ── Derived ─────────────────────────────────────────────────────────────
  const hasUnsavedChanges = useMemo(() => {
    return (
      hasDirtyExtension ||
      (catalogEditable === true &&
        JSON.stringify(catalog) !== JSON.stringify(draft))
    );
  }, [catalog, catalogEditable, draft, hasDirtyExtension]);

  const settingsLoading = catalogEditable === null;

  const value = useMemo<SettingsContextValue>(
    () => ({
      catalog,
      draft,
      catalogRevision,
      editingSelections,
      reasoningControls,
      customProviderCapabilities,
      status,
      providers,
      catalogEditable,
      settingsLoading,
      settingsError,
      reloadSettings: loadSettings,
      hasUnsavedChanges,
      theme,
      language,
      responseLanguage,
      codeBlockTheme,
      codeBlockShowLineNumbers,
      codeBlockWrapLongLines,
      toast,
      setToast,
      updateTheme,
      updateLanguage,
      updateResponseLanguage,
      updateCodeBlockTheme,
      updateCodeBlockShowLineNumbers,
      updateCodeBlockWrapLongLines,
      mutateCatalog,
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
      saving,
      applying,
      saveCatalog,
      applyCatalog,
      applySavedDefaultReferences,
      registerExtension,
      logs,
      testRunning,
      diagnosticsResults,
      embeddingCapabilities,
      runDetailedTest,
      embeddingDefaultDim,
      tourStepIndex,
      startTour,
      advanceTour,
      goBackTour,
      skipTour,
    }),
    [
      addModel,
      addProfile,
      applyDetectedContextWindow,
      applyCatalog,
      applySavedDefaultReferences,
      applying,
      catalog,
      catalogEditable,
      catalogRevision,
      editingSelections,
      codeBlockShowLineNumbers,
      codeBlockTheme,
      codeBlockWrapLongLines,
      diagnosticsResults,
      draft,
      embeddingCapabilities,
      reasoningControls,
      customProviderCapabilities,
      embeddingDefaultDim,
      hasUnsavedChanges,
      language,
      responseLanguage,
      llmContextDetection,
      logs,
      mutateCatalog,
      providers,
      registerExtension,
      removeEditingModel,
      removeEditingProfile,
      runDetailedTest,
      saveCatalog,
      saving,
      selectEditingModel,
      selectEditingProfile,
      settingsError,
      loadSettings,
      settingsLoading,
      skipTour,
      startTour,
      advanceTour,
      goBackTour,
      status,
      testRunning,
      theme,
      toast,
      tourStepIndex,
      updateCodeBlockShowLineNumbers,
      updateCodeBlockTheme,
      updateCodeBlockWrapLongLines,
      updateContextWindowField,
      updateLlmBudgetField,
      updateEmbeddingDimensionField,
      updateEmbeddingSendDimensions,
      updateReasoningEffort,
      updateLanguage,
      updateResponseLanguage,
      updateModelBoolField,
      updateModelField,
      updateProfileField,
      updateTheme,
    ],
  );

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

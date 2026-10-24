"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Save, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import { apiFetch, apiUrl } from "@/lib/api";
import { localizeProviderLabel } from "@/lib/custom-providers";
import {
  changedDefaultReferences,
  defaultReferenceKey,
  DEFAULT_MODEL_SERVICES,
  parseDefaultModelsResponse,
  sameDefaultReference,
  type DefaultModelService,
  type DefaultModelsResponse,
  type DefaultProfileOption,
} from "@/lib/default-models";
import {
  type DefaultModelReference,
  type DefaultModelReferenceMap,
  useSettings,
} from "./SettingsContext";

const SERVICE_LABEL: Record<DefaultModelService, string> = {
  llm: "Large language model (LLM)",
  embedding: "Embedding",
  search: "Search service",
  stt: "Speech-to-text",
  tts: "Text-to-speech",
  vision: "Vision",
  imagegen: "Image generation",
  videogen: "Video generation",
};

function cloneReferences(
  defaults: DefaultModelReferenceMap,
): DefaultModelReferenceMap {
  return JSON.parse(JSON.stringify(defaults)) as DefaultModelReferenceMap;
}

function profileLabel(
  profile: DefaultProfileOption,
  t: (key: string) => string,
): string {
  const vendor = localizeProviderLabel(
    profile.provider_label || profile.provider,
    t,
    profile.custom_provider_id,
  );
  if (!vendor || vendor === profile.profile_name) return profile.profile_name;
  return `${vendor} · ${profile.profile_name}`;
}

function optionReferences(
  service: DefaultModelService,
  data: DefaultModelsResponse,
): Map<string, DefaultModelReference> {
  const result = new Map<string, DefaultModelReference>();
  for (const profile of data.services[service].profiles) {
    if (service === "search") {
      result.set(
        defaultReferenceKey({ profile_id: profile.profile_id }),
        { profile_id: profile.profile_id },
      );
      continue;
    }
    for (const model of profile.models) {
      const reference = {
        profile_id: profile.profile_id,
        model_id: model.model_id,
      };
      result.set(defaultReferenceKey(reference), reference);
    }
  }
  return result;
}

export default function DefaultModelsEditor() {
  const { t } = useTranslation();
  const {
    catalogEditable,
    applySavedDefaultReferences,
  } = useSettings();
  const [data, setData] = useState<DefaultModelsResponse | null>(null);
  const [selected, setSelected] = useState<DefaultModelReferenceMap>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(apiUrl("/api/v1/settings/default-models"), {
        cache: "no-store",
      });
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: string | { message?: string };
      };
      if (!response.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : payload.detail?.message;
        throw new Error(
          detail ||
            t("Could not load default models (HTTP {{status}}).", {
              status: response.status,
            }),
        );
      }
      const parsed = parseDefaultModelsResponse(payload);
      setData(parsed);
      setSelected(cloneReferences(parsed.defaults));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : t("Could not load default models."),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (catalogEditable !== true) return;
    void load();
  }, [catalogEditable, load]);

  const references = useMemo(() => {
    if (!data) return {} as Record<DefaultModelService, Map<string, DefaultModelReference>>;
    return Object.fromEntries(
      DEFAULT_MODEL_SERVICES.map((service) => [
        service,
        optionReferences(service, data),
      ]),
    ) as Record<DefaultModelService, Map<string, DefaultModelReference>>;
  }, [data]);

  const changed = useMemo(
    () => (data ? changedDefaultReferences(data.defaults, selected) : {}),
    [data, selected],
  );
  const attemptedClear = useMemo(
    () =>
      data
        ? DEFAULT_MODEL_SERVICES.filter(
            (service) => data.defaults[service] && !selected[service],
          )
        : [],
    [data, selected],
  );
  const dirty =
    Object.keys(changed).length > 0 || attemptedClear.length > 0;

  const save = useCallback(async () => {
    if (!data || attemptedClear.length > 0) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(apiUrl("/api/v1/settings/default-models"), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: data.revision,
          defaults: changed,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        revision?: string;
        defaults?: DefaultModelReferenceMap;
        detail?: string | { message?: string; code?: string; current_revision?: string };
      };
      if (!response.ok || !payload.revision || !payload.defaults) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : payload.detail?.message;
        const conflict =
          response.status === 409 ||
          (typeof payload.detail === "object" &&
            payload.detail?.code === "CATALOG_REVISION_CONFLICT");
        throw new Error(
          conflict
            ? t(
                "The saved catalog changed while you were editing. Your choices were kept; reload and try again.",
              )
            : detail ||
                t("Could not save default models (HTTP {{status}}).", {
                  status: response.status,
                }),
        );
      }
      const next: DefaultModelsResponse = {
        ...data,
        revision: payload.revision,
        defaults: payload.defaults,
      };
      setData(next);
      setSelected(cloneReferences(payload.defaults));
      applySavedDefaultReferences(payload.defaults, payload.revision, data.revision);
    } catch (saveError) {
      // Never optimistically show success: keep both the fetched data and the
      // user's pending selection so a conflict/rejection is recoverable.
      setError(
        saveError instanceof Error
          ? saveError.message
          : t("Could not save default models."),
      );
    } finally {
      setSaving(false);
    }
  }, [applySavedDefaultReferences, attemptedClear.length, changed, data, t]);

  const cancel = useCallback(() => {
    if (!data) return;
    setSelected(cloneReferences(data.defaults));
    setError(null);
  }, [data]);

  if (catalogEditable === null) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-5 py-10 text-[13px] text-[var(--muted-foreground)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("Loading settings…")}
      </div>
    );
  }

  if (catalogEditable === false) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border)] px-5 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
        {t(
          "Only an administrator can change the deployment default models. Your authorized chat models remain available in the composer.",
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="default-models-editor">
      <div className="rounded-xl border border-[var(--border)]/70 bg-[var(--card)]/40 px-4 py-3 text-[12px] leading-relaxed text-[var(--muted-foreground)]">
        <p>
          {t(
            "Only saved model configurations appear here. Save model settings first if a new connection or model is missing.",
          )}
        </p>
        <p className="mt-1">
          {t(
            "Saving this page updates only the default references. It does not submit unfinished edits from other pages, call a model, or rebuild an index.",
          )}
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-5 py-8 text-[13px] text-[var(--muted-foreground)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("Loading default models…")}
        </div>
      ) : error && !data ? (
        <div
          data-testid="default-models-error"
          className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-[12px] text-red-600 dark:text-red-400"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <>
          <div className="divide-y divide-[var(--border)]/50 overflow-hidden rounded-xl border border-[var(--border)]">
            {DEFAULT_MODEL_SERVICES.map((service) => {
              const options = data.services[service];
              const current = selected[service] ?? null;
              const currentKey = defaultReferenceKey(current);
              const knownKeys = references[service];
              const saved = data.defaults[service] ?? null;
              const selectedProfile = options.profiles.find(
                (profile) => profile.profile_id === current?.profile_id,
              );
              const unavailable =
                Boolean(current) && !knownKeys.has(currentKey);
              return (
                <div
                  key={service}
                  data-testid={`default-service-${service}`}
                  className="grid gap-2 px-4 py-3 sm:grid-cols-[190px_minmax(0,1fr)] sm:items-center"
                >
                  <div>
                    <div className="text-[12.5px] font-medium text-[var(--foreground)]">
                      {t(SERVICE_LABEL[service])}
                    </div>
                    <div className="mt-0.5 text-[10.5px] text-[var(--muted-foreground)]">
                      {service === "search"
                        ? t("A search service profile, not a model.")
                        : t("One default model")}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                    {selectedProfile && (
                      <ProviderIcon
                        provider={selectedProfile.provider}
                        icon={selectedProfile.provider_icon}
                        size={15}
                        className="shrink-0 text-[var(--muted-foreground)]"
                      />
                    )}
                    <select
                      data-testid={`default-select-${service}`}
                      aria-label={t("Default {{service}}", {
                        service: t(SERVICE_LABEL[service]),
                      })}
                      value={currentKey}
                      onChange={(event) => {
                        const reference = references[service].get(
                          event.target.value,
                        );
                        setSelected((previous) => ({
                          ...previous,
                          [service]: reference ?? null,
                        }));
                      }}
                      className="h-9 min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 text-[12.5px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                    >
                      {(!saved || !current) && (
                        <option value="">{t("Not configured")}</option>
                      )}
                      {unavailable && current && (
                        <option value={currentKey}>
                          {t("Current default (unavailable)")}
                        </option>
                      )}
                      {options.profiles.map((profile) => {
                        if (options.kind === "profile") {
                          return (
                            <option
                              key={profile.profile_id}
                              data-profile-id={profile.profile_id}
                              value={defaultReferenceKey({
                                profile_id: profile.profile_id,
                              })}
                            >
                              {profileLabel(profile, t)}
                            </option>
                          );
                        }
                        return (
                          <optgroup
                            key={profile.profile_id}
                            label={profileLabel(profile, t)}
                          >
                            {profile.models.map((model) => {
                              const ref = {
                                profile_id: profile.profile_id,
                                model_id: model.model_id,
                              };
                              return (
                                <option
                                  key={model.model_id}
                                  data-profile-id={profile.profile_id}
                                  data-model-id={model.model_id}
                                  value={defaultReferenceKey(ref)}
                                >
                                  {model.model_name}
                                  {model.hidden ? ` · ${t("Hidden")}` : ""}
                                </option>
                              );
                            })}
                          </optgroup>
                        );
                      })}
                    </select>
                    </div>
                    {options.profiles.length === 0 && (
                      <p className="mt-1 text-[10.5px] text-[var(--muted-foreground)]">
                        {t("No saved configuration for this service.")}
                      </p>
                    )}
                    {saved && !sameDefaultReference(saved, current) && current && (
                      <p className="mt-1 text-[10.5px] text-amber-600 dark:text-amber-400">
                        {t("Pending change")}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {attemptedClear.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11.5px] text-amber-700 dark:text-amber-400">
              {t(
                "This page changes saved references; it cannot clear a default. Choose a saved profile/model.",
              )}
            </div>
          )}
          {error && (
            <div
              data-testid="default-models-error"
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-[12px] text-red-600 dark:text-red-400"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 text-[11.5px] text-[var(--muted-foreground)]">
              {dirty ? (
                <>
                  <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
                  {t("Default selection has unsaved changes")}
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  {t("Defaults match the saved catalog")}
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="default-cancel"
                onClick={cancel}
                disabled={!dirty || saving}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)]/60 px-3 py-1.5 text-[12px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] disabled:opacity-40"
              >
                <Undo2 className="h-3 w-3" />
                {t("Cancel")}
              </button>
              <button
                type="button"
                data-testid="default-save"
                onClick={() => void save()}
                disabled={
                  saving ||
                  attemptedClear.length > 0 ||
                  Object.keys(changed).length === 0
                }
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-[12px] font-medium text-[var(--background)] transition-opacity hover:opacity-80 disabled:opacity-40"
              >
                {saving ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                {t("Save default settings")}
              </button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

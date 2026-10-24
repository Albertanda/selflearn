"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Search,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ProviderIcon from "@/components/common/ProviderIcon";
import type { LLMSelection } from "@/lib/unified-ws";
import {
  llmOptionLabel,
  llmOptionTitle,
  llmSelectionKey,
  sameLLMSelection,
  type LLMOption,
} from "@/lib/llm-options";
import {
  connectionLabelText,
  localizeProviderLabel,
} from "@/lib/custom-providers";
import {
  findOptionGroup,
  groupLLMOptions,
  modelOptionSource,
  searchLLMOptions,
  type LLMOptionGroup,
} from "@/lib/model-picker-groups";

function formatContextWindow(value?: number) {
  if (!value) return "";
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000)}M ctx`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k ctx`;
  return `${value} ctx`;
}

function ModelOptionRow({
  option,
  selected,
  hidden = false,
  onSelect,
}: {
  option: LLMOption;
  selected: boolean;
  hidden?: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const modelLabel = llmOptionLabel(option);
  const source = localizeProviderLabel(modelOptionSource(option), t, option.custom_provider_id);
  const contextWindow = formatContextWindow(option.context_window);
  const nameRef = useRef<HTMLSpanElement>(null);
  const [revealFull, setRevealFull] = useState(false);
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={selected}
      title={llmOptionTitle(option)}
      data-testid="llm-option-row"
      data-model-id={option.model_id}
      data-model-value={option.model}
      onClick={onSelect}
      onMouseEnter={() => {
        const el = nameRef.current;
        setRevealFull(!!el && el.scrollWidth > el.clientWidth + 1);
      }}
      onMouseLeave={() => setRevealFull(false)}
      className={`relative flex w-full items-center gap-2 px-3 py-2 text-left transition-colors active:bg-[var(--muted)]/70 ${
        selected ? "bg-[var(--primary)]/[0.06]" : "hover:bg-[var(--muted)]/45"
      }`}
    >
      <ProviderIcon
        provider={option.provider}
        icon={option.provider_icon}
        size={14}
        className={
          selected ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"
        }
      />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex min-w-0 items-center gap-1.5">
          <span
            ref={nameRef}
            className="min-w-0 truncate text-[12.5px] font-medium text-[var(--foreground)]"
          >
            {modelLabel}
          </span>
          {option.is_active_default && (
            <span className="shrink-0 rounded-full bg-[var(--muted)] px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
              {t("Default")}
            </span>
          )}
          {hidden && (
            <span className="shrink-0 rounded-full bg-amber-500/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
              {t("Hidden")}
            </span>
          )}
        </span>
        <span className="truncate text-[10.5px] leading-tight text-[var(--muted-foreground)]">
          {source}
        </span>
      </span>
      {contextWindow ? (
        <span className="shrink-0 text-[10.5px] tabular-nums text-[var(--muted-foreground)]">
          {contextWindow}
        </span>
      ) : null}
      {selected && (
        <Check
          size={14}
          strokeWidth={2}
          className="shrink-0 text-[var(--primary)]"
        />
      )}
      {revealFull && (
        <span className="pointer-events-none absolute inset-x-1.5 top-1/2 z-10 -translate-y-1/2 break-all rounded-lg border border-[var(--border)] bg-[var(--popover)] px-2 py-1 text-[12px] font-medium text-[var(--foreground)] shadow-md">
          {modelLabel}
        </span>
      )}
    </button>
  );
}

export default function ModelSelector({
  options,
  hiddenOptions = [],
  activeDefault,
  value,
  loading,
  error,
  allowSystemDefault = false,
  systemDefaultLabel,
  systemDefaultDetail,
  helperText,
  placement = "top",
  onChange,
  onRefresh,
}: {
  options: LLMOption[];
  hiddenOptions?: LLMOption[];
  activeDefault: LLMSelection | null;
  value: LLMSelection | null;
  loading: boolean;
  error: boolean;
  allowSystemDefault?: boolean;
  systemDefaultLabel?: string;
  systemDefaultDetail?: string;
  helperText?: string;
  placement?: "top" | "bottom";
  onChange: (selection: LLMSelection | null) => void;
  onRefresh?: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"providers" | "models">("providers");
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const selectedSelection = allowSystemDefault
    ? value
    : (value ?? activeDefault);
  const selectedProfileId = selectedSelection?.profile_id;
  const selectedModelId = selectedSelection?.model_id;
  const groups = useMemo(
    () => groupLLMOptions(options, hiddenOptions.filter((option) =>
      option.profile_id === selectedProfileId && option.model_id === selectedModelId,
    )),
    [hiddenOptions, options, selectedProfileId, selectedModelId],
  );
  const selectedKey = llmSelectionKey(selectedSelection);
  const selectedVisibleOption = useMemo(
    () =>
      options.find((option) => sameLLMSelection(option, selectedSelection)) ??
      null,
    [options, selectedSelection],
  );
  const selectedHiddenOption = useMemo(
    () =>
      selectedVisibleOption
        ? null
        : (hiddenOptions.find((option) =>
            sameLLMSelection(option, selectedSelection),
          ) ?? null),
    [hiddenOptions, selectedSelection, selectedVisibleOption],
  );
  const selectedOption = selectedVisibleOption ?? selectedHiddenOption;
  const selectedIsHidden = Boolean(selectedHiddenOption);
  const selectedGroup = useMemo(
    () => findOptionGroup(groups, selectedSelection),
    [groups, selectedSelection],
  );
  const activeGroup =
    groups.find((group) => group.profileId === activeGroupId) ?? null;
  const searchHits = useMemo(
    () => searchLLMOptions(groups, query),
    [groups, query],
  );

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      if (view === "models" && !query) {
        rootRef.current
          ?.querySelector<HTMLElement>('[data-testid="llm-option-row"]')
          ?.focus();
      } else {
        searchRef.current?.focus();
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [activeGroupId, open, query, view]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current && !rootRef.current.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const defaultLabel = systemDefaultLabel || t("System default");
  const defaultDetail =
    systemDefaultDetail || t("Use the active default model from Settings");
  const canRefresh = error && Boolean(onRefresh);
  const disabled = loading || (!canRefresh && error);
  const modelLabel = selectedOption ? llmOptionLabel(selectedOption) : "";
  const sourceLabel = selectedGroup
    ? connectionLabelText(
        selectedGroup.providerLabel,
        selectedGroup.profileName,
        t,
        selectedGroup.customProviderId,
      )
    : "";
  const label = loading
    ? t("Loading models")
    : error
      ? canRefresh
        ? t("Refresh models")
        : t("Models unavailable")
      : allowSystemDefault && !selectedSelection
        ? defaultLabel
        : selectedOption
          ? `${sourceLabel} · ${modelLabel}${
              selectedIsHidden ? ` ${t("(hidden)")}` : ""
            }`
          : t("Select model");
  const menuPlacementClass =
    placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5";

  const openPicker = () => {
    setView("providers");
    setQuery("");
    setActiveGroupId(selectedGroup?.profileId ?? null);
    setOpen(true);
  };

  const selectOption = (option: LLMOption) => {
    onChange({ profile_id: option.profile_id, model_id: option.model_id });
    setOpen(false);
    setView("providers");
    setQuery("");
  };

  const chooseGroup = (group: LLMOptionGroup) => {
    // Choosing a connection only opens its model list; it never changes the
    // current model or the saved default.
    setActiveGroupId(group.profileId);
    setView("models");
    setQuery("");
  };

  const handleMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      if (view === "models") {
        setView("providers");
      } else {
        setOpen(false);
      }
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled])",
      ),
    );
    if (focusable.length === 0) return;
    event.preventDefault();
    const index = focusable.indexOf(document.activeElement as HTMLElement);
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const next = focusable[(index + delta + focusable.length) % focusable.length];
    next?.focus();
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        data-selected-model={selectedKey}
        data-selected-hidden={selectedIsHidden ? "true" : "false"}
        data-testid="llm-selector-button"
        onClick={() => {
          if (canRefresh) {
            setOpen(false);
            onRefresh?.();
            return;
          }
          if (open) setOpen(false);
          else openPicker();
        }}
        aria-label={canRefresh ? t("Refresh models") : t("Select model")}
        title={
          canRefresh
            ? t("Refresh models")
            : selectedOption
              ? llmOptionTitle(selectedOption)
              : undefined
        }
        aria-expanded={open}
        aria-haspopup="menu"
        className={`inline-flex h-8 max-w-[260px] shrink-0 items-center gap-1.5 rounded-lg px-2 text-[12.5px] font-medium transition-[background-color,color,transform] duration-150 active:scale-[0.97] ${
          disabled
            ? "cursor-not-allowed text-[var(--border)]"
            : open
              ? "bg-[var(--muted)] text-[var(--foreground)]"
              : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/55 hover:text-[var(--foreground)]"
        }`}
      >
        {error ? (
          <AlertCircle size={15} strokeWidth={1.7} className="shrink-0" />
        ) : (
          <ProviderIcon
            provider={selectedOption?.provider}
            icon={selectedOption?.provider_icon}
            size={15}
          />
        )}
        <span className="min-w-0 truncate">{label}</span>
        <ChevronDown
          size={13}
          className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && !disabled && (
        <div
          role="menu"
          data-testid="llm-picker-menu"
          data-view={query ? "search" : view}
          onKeyDown={handleMenuKeyDown}
          className={`absolute right-0 z-50 ${menuPlacementClass} w-[min(340px,calc(100vw-32px))] overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--popover)] shadow-lg backdrop-blur-md`}
        >
          <div className="border-b border-[var(--border)]/50 p-2">
            <div className="relative">
              <Search
                size={13}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
              />
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                data-testid="llm-picker-search"
                aria-label={t("Search models across connections")}
                placeholder={t("Search models across connections")}
                className="h-8 w-full rounded-lg border border-[var(--border)]/60 bg-[var(--background)] pl-8 pr-2 text-[12px] text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]/60 focus:border-[var(--ring)]"
              />
            </div>
            {helperText ? (
              <div className="mt-1.5 px-0.5 text-[10.5px] leading-snug text-[var(--muted-foreground)]">
                {helperText}
              </div>
            ) : null}
          </div>

          {query ? (
            <div className="max-h-[320px] overflow-y-auto py-1">
              <div className="px-3 py-1 text-[10.5px] uppercase tracking-wide text-[var(--muted-foreground)]/70">
                {t("Search results")}
              </div>
              {searchHits.length === 0 ? (
                <div className="px-3 py-4 text-center text-[12px] text-[var(--muted-foreground)]">
                  {t("No models match this search.")}
                </div>
              ) : (
                searchHits.map((hit) => {
                  const optionSelection = {
                    profile_id: hit.option.profile_id,
                    model_id: hit.option.model_id,
                  };
                  return (
                    <button
                      key={`${llmSelectionKey(optionSelection)}:${hit.hidden ? "hidden" : "visible"}`}
                      type="button"
                      role="menuitemradio"
                      aria-checked={
                        llmSelectionKey(optionSelection) === selectedKey
                      }
                      data-testid="llm-search-result"
                      data-source={hit.source}
                      onClick={() => selectOption(hit.option)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[var(--muted)]/45"
                    >
                      <ProviderIcon
                        provider={hit.option.provider}
                        icon={hit.option.provider_icon}
                        size={14}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-medium text-[var(--foreground)]">
                          {llmOptionLabel(hit.option)}
                        </span>
                        <span className="block truncate text-[10.5px] text-[var(--muted-foreground)]">
                          {connectionLabelText(
                            hit.group.providerLabel,
                            hit.group.profileName,
                            t,
                            hit.group.customProviderId,
                          )}
                          {hit.hidden ? ` · ${t("Hidden")}` : ""}
                        </span>
                      </span>
                      {llmSelectionKey(optionSelection) === selectedKey && (
                        <Check
                          size={14}
                          className="shrink-0 text-[var(--primary)]"
                        />
                      )}
                    </button>
                  );
                })
              )}
            </div>
          ) : view === "providers" ? (
            <>
              <div className="flex items-center justify-between px-3 pb-1 pt-2">
                <span
                  data-testid="llm-picker-title"
                  className="text-[10.5px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]/70"
                >
                  {t("Providers & connections")}
                </span>
                <span className="text-[10.5px] text-[var(--muted-foreground)]/60">
                  {t("{{count}} connections", { count: groups.length })}
                </span>
              </div>
              <div className="max-h-[320px] overflow-y-auto py-1">
                {allowSystemDefault && (
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={selectedKey === ""}
                    title={defaultDetail}
                    onClick={() => {
                      onChange(null);
                      setOpen(false);
                    }}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left ${
                      selectedKey === ""
                        ? "bg-[var(--primary)]/[0.06]"
                        : "hover:bg-[var(--muted)]/45"
                    }`}
                  >
                    <Bot
                      size={14}
                      strokeWidth={1.7}
                      className={
                        selectedKey === ""
                          ? "text-[var(--primary)]"
                          : "text-[var(--muted-foreground)]"
                      }
                    />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--foreground)]">
                      {defaultLabel}
                    </span>
                    {selectedKey === "" && (
                      <Check
                        size={14}
                        className="text-[var(--primary)]"
                      />
                    )}
                  </button>
                )}
                {groups.map((group) => (
                  <button
                    key={group.profileId}
                    type="button"
                    role="menuitem"
                    data-testid="llm-provider-group"
                    data-profile-id={group.profileId}
                    data-provider={group.provider}
                    onClick={() => chooseGroup(group)}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors ${
                      group.profileId === selectedGroup?.profileId
                        ? "bg-[var(--primary)]/[0.04]"
                        : "hover:bg-[var(--muted)]/45"
                    }`}
                  >
                    <ProviderIcon
                      provider={group.provider}
                      icon={group.providerIcon}
                      size={15}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-[var(--foreground)]">
                        {connectionLabelText(
                          group.providerLabel,
                          group.profileName,
                          t,
                          group.customProviderId,
                        )}
                      </span>
                      <span className="block truncate text-[10.5px] text-[var(--muted-foreground)]">
                        {group.profileName} ·{" "}
                        {t("{{count}} models", { count: group.count })}
                      </span>
                    </span>
                    <ChevronRight
                      size={14}
                      className="shrink-0 text-[var(--muted-foreground)]/60"
                    />
                  </button>
                ))}
                {groups.length === 0 && (
                  <div className="px-3 py-6 text-center text-[12px] text-[var(--muted-foreground)]">
                    {t("No models are available for this account.")}
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 border-b border-[var(--border)]/40 px-2 py-2">
                <button
                  type="button"
                  data-testid="llm-picker-back"
                  onClick={() => setView("providers")}
                  aria-label={t("Back to providers")}
                  className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-[11.5px] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50 hover:text-[var(--foreground)]"
                >
                  <ArrowLeft size={13} />
                  {t("Back")}
                </button>
                <span className="min-w-0 flex-1 truncate text-right text-[11.5px] font-medium text-[var(--foreground)]">
                  {activeGroup
                    ? connectionLabelText(
                        activeGroup.providerLabel,
                        activeGroup.profileName,
                        t,
                        activeGroup.customProviderId,
                      )
                    : ""}
                </span>
              </div>
              <div className="max-h-[300px] overflow-y-auto py-1">
                {activeGroup?.options.map((option) => (
                  <ModelOptionRow
                    key={llmSelectionKey(option)}
                    option={option}
                    selected={sameLLMSelection(option, selectedSelection)}
                    onSelect={() => selectOption(option)}
                  />
                ))}
                {selectedHiddenOption &&
                  activeGroup &&
                  activeGroup.profileId === selectedHiddenOption.profile_id && (
                    <ModelOptionRow
                      option={selectedHiddenOption}
                      selected
                      hidden
                      onSelect={() => selectOption(selectedHiddenOption)}
                    />
                  )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

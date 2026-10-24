"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Brain, Check, ChevronDown, CircleSlash } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  reasoningChoiceLabel,
  reasoningChoices,
  reasoningOverrideKey,
  type ReasoningControls,
  type ReasoningOverride,
} from "@/lib/reasoning-controls";

/**
 * Per-turn reasoning control.  It renders only the levels the backend
 * published for the selected model; nothing here guesses a model family.
 */
export default function ReasoningSelector({
  controls,
  value,
  onChange,
  placement = "top",
}: {
  controls?: ReasoningControls | null;
  value: ReasoningOverride;
  onChange: (value: ReasoningOverride) => void;
  placement?: "top" | "bottom";
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const explicit = value.mode !== "inherit";
  const effectiveControls = useMemo(
    () =>
      controls ??
      (explicit
        ? ({
            supported: false,
            control: "unknown",
            levels: [],
            can_disable: false,
            default_level: null,
            aliases: {},
          } as ReasoningControls)
        : null),
    [controls, explicit],
  );
  const choices = useMemo(
    () => reasoningChoices(effectiveControls, value),
    [effectiveControls, value],
  );
  const label = reasoningChoiceLabel(effectiveControls, value);
  const supported = effectiveControls?.supported === true;
  const explicitlyUnavailable =
    effectiveControls?.supported === false;
  // An explicit old choice must remain resettable even when the endpoint's
  // capability has become unknown (supported=null) after a refresh.
  const canOpen = supported || explicit;

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

  if (!effectiveControls) return null;

  const selectedKey = reasoningOverrideKey(value);
  const placementClass =
    placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        data-testid="reasoning-selector-button"
        data-reasoning-value={selectedKey}
        data-reasoning-control={effectiveControls.control}
        disabled={!canOpen}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={
          supported
            ? t("Reasoning strength: {{label}}", { label: t(label) })
            : t("Reasoning control is not available for this model")
        }
        title={
          explicitlyUnavailable && !supported
            ? t(
                "This model has no verified reasoning control. No reasoning field will be sent.",
              )
            : t("Reasoning strength")
        }
        onClick={() => canOpen && setOpen((current) => !current)}
        className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2 text-[12px] font-medium transition-colors ${
          supported
            ? "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/55 hover:text-[var(--foreground)]"
            : "cursor-not-allowed text-[var(--muted-foreground)]/45"
        }`}
      >
        {supported ? (
          <Brain size={15} strokeWidth={1.7} />
        ) : (
          <CircleSlash size={14} strokeWidth={1.7} />
        )}
        <span className="hidden max-w-[150px] truncate sm:inline">
          {supported
            ? t(label)
            : explicit
              ? t(label)
              : t("Reasoning unavailable")}
        </span>
        {canOpen ? (
          <ChevronDown
            size={13}
            className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          />
        ) : null}
      </button>

      {open && canOpen && (
        <div
          role="menu"
          data-testid="reasoning-menu"
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
          }}
          className={`absolute right-0 z-50 ${placementClass} w-[min(260px,calc(100vw-32px))] overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--popover)] shadow-lg backdrop-blur-md`}
        >
          <div className="border-b border-[var(--border)]/50 px-3 py-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]/70">
              {t("Reasoning strength")}
            </div>
            <div className="mt-0.5 text-[10.5px] leading-snug text-[var(--muted-foreground)]">
              {effectiveControls?.control === "budget"
                ? t(
                    "Budget presets map to this model's thinking budget; they are not extra native effort levels.",
                  )
                : t(
                    "Only levels published by the backend for this exact model are listed.",
                  )}
            </div>
          </div>
          <div className="max-h-[300px] overflow-y-auto py-1">
            {choices.map((choice) => {
              const selected = reasoningOverrideKey(choice.override) === selectedKey;
              return (
                <button
                  key={choice.value}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  data-testid="reasoning-option"
                  data-value={choice.value}
                  data-unsupported={choice.unsupported ? "true" : "false"}
                  onClick={() => {
                    onChange(choice.override);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] transition-colors ${
                    selected
                      ? "bg-[var(--primary)]/[0.06] text-[var(--foreground)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/45 hover:text-[var(--foreground)]"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {t(choice.label)}
                  </span>
                  {choice.mappedTo ? (
                    <span className="shrink-0 text-[10px] text-amber-600 dark:text-amber-400">
                      {t("mapped")}
                    </span>
                  ) : null}
                  {selected && (
                    <Check
                      size={14}
                      className="shrink-0 text-[var(--primary)]"
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

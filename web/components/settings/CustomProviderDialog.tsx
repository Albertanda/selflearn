"use client";

import { useState } from "react";
import { AlertCircle, Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import {
  BUILTIN_ICON_VALUES,
  cleanCustomProviderName,
  validateCustomProviderIcon,
  validateCustomProviderName,
  type CustomProviderDefinition,
  type CustomProviderProtocol,
  type CustomProviderService,
  type ProviderIconSpec,
} from "@/lib/custom-providers";

const ICON_LABELS: Record<string, string> = {
  bot: "Bot",
  server: "Server",
  school: "School",
  flask: "Flask",
  cloud: "Cloud",
  network: "Network",
};

export interface CustomProviderDialogValue {
  name: string;
  binding: string;
  icon: ProviderIconSpec | null;
}

export default function CustomProviderDialog({
  service,
  mode,
  initial,
  protocols,
  definitions,
  onCancel,
  onSave,
}: {
  service: CustomProviderService;
  mode: "create" | "edit";
  initial?: CustomProviderDefinition | null;
  protocols: CustomProviderProtocol[];
  definitions: readonly CustomProviderDefinition[];
  onCancel: () => void;
  onSave: (value: CustomProviderDialogValue) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? "");
  const [binding, setBinding] = useState(
    initial?.binding ?? protocols[0]?.value ?? "custom",
  );
  const [icon, setIcon] = useState<ProviderIconSpec | null>(
    initial?.icon ?? null,
  );
  const [iconKind, setIconKind] = useState<"builtin" | "emoji">(
    initial?.icon?.kind === "emoji" ? "emoji" : "builtin",
  );
  const [emoji, setEmoji] = useState(
    initial?.icon?.kind === "emoji" ? initial.icon.value : "",
  );
  const [touched, setTouched] = useState(false);

  const nameError = validateCustomProviderName(
    name,
    definitions,
    service,
    initial?.id,
  );
  const iconError = validateCustomProviderIcon(icon);
  const error = nameError || iconError;

  const chooseBuiltin = (value: (typeof BUILTIN_ICON_VALUES)[number]) => {
    setIconKind("builtin");
    setIcon({ kind: "builtin", value });
  };

  const chooseEmoji = (value: string) => {
    setIconKind("emoji");
    setEmoji(value);
    setIcon({ kind: "emoji", value });
  };

  const submit = () => {
    setTouched(true);
    if (error) return;
    if (mode === "edit" && initial) {
      onSave({ name: cleanCustomProviderName(name), binding: initial.binding, icon });
      return;
    }
    onSave({
      name: cleanCustomProviderName(name),
      binding,
      icon: iconError ? null : icon,
    });
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/35 p-4 backdrop-blur-[2px]"
      data-testid="custom-provider-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="custom-provider-title"
    >
      <div className="w-full max-w-[480px] rounded-2xl border border-[var(--border)] bg-[var(--popover)] p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              id="custom-provider-title"
              className="text-[15px] font-semibold text-[var(--foreground)]"
            >
              {mode === "edit"
                ? t("Edit custom provider")
                : t("Create custom provider")}
            </h2>
            <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--muted-foreground)]">
              {t(
                "The name and icon describe this connection. The request protocol and credentials stay separate and are never inferred from the display name.",
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t("Cancel")}
            className="rounded-md p-1 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="mt-4 block text-[12px] font-medium text-[var(--foreground)]">
          {t("Provider name")}
          <input
            autoFocus
            data-testid="custom-provider-name"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setTouched(true);
            }}
            maxLength={80}
            placeholder={t("e.g. School gateway")}
            className="mt-1.5 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 text-[12.5px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
          />
        </label>

        <div className="mt-4">
          <div className="text-[12px] font-medium text-[var(--foreground)]">
            {t("Request protocol")}
          </div>
          {mode === "edit" ? (
            <div className="mt-1.5 rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 px-2.5 py-2 text-[12px] text-[var(--foreground)]">
              {protocols.find((item) => item.value === binding)?.label || binding}
              <span className="ml-2 text-[11px] text-[var(--muted-foreground)]">
                {t("Protocol is fixed after saving. Create a new provider to change it.")}
              </span>
            </div>
          ) : (
            <select
              data-testid="custom-provider-protocol"
              value={binding}
              onChange={(event) => setBinding(event.target.value)}
              className="mt-1.5 h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 text-[12.5px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
            >
              {protocols.map((protocol) => (
                <option key={protocol.value} value={protocol.value}>
                  {t(protocol.label)}
                </option>
              ))}
            </select>
          )}
          <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--muted-foreground)]">
            {t(protocols.find((item) => item.value === binding)?.description ?? "")}
          </p>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <div className="text-[12px] font-medium text-[var(--foreground)]">
              {t("Icon")}
            </div>
            <button
              type="button"
              data-testid="custom-provider-icon-default"
              onClick={() => setIcon(null)}
              className={`rounded-md px-2 py-1 text-[10.5px] ${
                icon === null
                  ? "bg-[var(--muted)] text-[var(--foreground)]"
                  : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50"
              }`}
            >
              {t("Default Bot")}
            </button>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {BUILTIN_ICON_VALUES.map((value) => {
              const selected =
                iconKind === "builtin" &&
                icon?.kind === "builtin" &&
                icon.value === value;
              return (
                <button
                  key={value}
                  type="button"
                  data-testid={`custom-provider-icon-${value}`}
                  aria-pressed={selected}
                  title={t(ICON_LABELS[value])}
                  onClick={() => chooseBuiltin(value)}
                  className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[11px] ${
                    selected
                      ? "border-[var(--ring)] bg-[var(--muted)] text-[var(--foreground)]"
                      : "border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/40"
                  }`}
                >
                  <ProviderIcon
                    provider={null}
                    icon={{ kind: "builtin", value }}
                    size={14}
                  />
                  {t(ICON_LABELS[value])}
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[11px] text-[var(--muted-foreground)]">
              {t("Emoji")}
            </span>
            <input
              data-testid="custom-provider-emoji"
              value={emoji}
              onChange={(event) => chooseEmoji(event.target.value)}
              maxLength={16}
              placeholder="🏫"
              className="h-8 w-24 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2 text-[13px] outline-none focus:border-[var(--ring)]"
            />
            <button
              type="button"
              onClick={() => chooseEmoji(emoji)}
              className="text-[11px] text-[var(--muted-foreground)] underline-offset-2 hover:underline"
            >
              {t("Use emoji")}
            </button>
            {icon && (
              <ProviderIcon provider={null} icon={icon} size={18} className="ml-auto" />
            )}
          </div>
        </div>

        {touched && error && (
          <div
            data-testid="custom-provider-error"
            className="mt-3 flex items-start gap-1.5 text-[11px] text-red-500"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{t(error)}</span>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            data-testid="custom-provider-cancel"
            onClick={onCancel}
            className="h-8 rounded-lg border border-[var(--border)] px-3 text-[12px] text-[var(--foreground)] hover:bg-[var(--muted)]/50"
          >
            {t("Cancel")}
          </button>
          <button
            type="button"
            data-testid="custom-provider-save"
            onClick={submit}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--foreground)] px-3 text-[12px] font-medium text-[var(--background)] hover:opacity-90"
          >
            <Check className="h-3.5 w-3.5" />
            {mode === "edit" ? t("Save provider") : t("Create provider")}
          </button>
        </div>
      </div>
    </div>
  );
}

import type { Catalog, CatalogProfile } from "@/components/settings/SettingsContext";

export const CUSTOM_PROVIDER_SENTINEL = "__create_custom_provider__";
export const CUSTOM_PROVIDER_SERVICES = [
  "llm",
  "embedding",
  "stt",
  "tts",
  "vision",
  "imagegen",
  "videogen",
] as const;

export type CustomProviderService = (typeof CUSTOM_PROVIDER_SERVICES)[number];

export type BuiltinProviderIcon =
  | "bot"
  | "server"
  | "school"
  | "flask"
  | "cloud"
  | "network";

export type ProviderIconSpec =
  | { kind: "builtin"; value: BuiltinProviderIcon }
  | { kind: "emoji"; value: string };

export interface CustomProviderDefinition {
  id: string;
  service: CustomProviderService;
  binding: string;
  name: string;
  icon?: ProviderIconSpec | null;
}

export interface CustomProviderProtocol {
  value: string;
  label: string;
  description: string;
}

export interface CustomProviderCapabilities {
  protocols: Record<CustomProviderService, CustomProviderProtocol[]>;
  icons: BuiltinProviderIcon[];
  max_name_length: number;
  max_providers: number;
}

export const BUILTIN_ICON_VALUES: BuiltinProviderIcon[] = [
  "bot",
  "server",
  "school",
  "flask",
  "cloud",
  "network",
];

export function customProviderDefinitions(
  catalog: Pick<Catalog, "custom_providers"> | null | undefined,
): CustomProviderDefinition[] {
  return Array.isArray(catalog?.custom_providers)
    ? catalog.custom_providers
    : [];
}

export function customProvidersForService(
  catalog: Pick<Catalog, "custom_providers"> | null | undefined,
  service: CustomProviderService,
): CustomProviderDefinition[] {
  return customProviderDefinitions(catalog)
    .filter((item) => item.service === service)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function customProviderById(
  catalog: Pick<Catalog, "custom_providers"> | null | undefined,
  id: string | null | undefined,
): CustomProviderDefinition | null {
  if (!id) return null;
  return customProviderDefinitions(catalog).find((item) => item.id === id) ?? null;
}

export function isAllowedCustomProviderBinding(
  service: CustomProviderService,
  binding: string,
  capabilities: CustomProviderCapabilities | null,
): boolean {
  return Boolean(
    capabilities?.protocols[service]?.some((item) => item.value === binding),
  );
}

export function customProviderSelectValue(profile: CatalogProfile): string {
  return profile.custom_provider_id
    ? `cp:${profile.custom_provider_id}`
    : profile.binding || "";
}

export function customProviderIdFromSelectValue(value: string): string | null {
  return value.startsWith("cp:") ? value.slice(3) : null;
}

export interface ProviderPresentation {
  providerLabel: string;
  providerIcon: ProviderIconSpec | null;
  customProviderId: string | null;
}

export function resolveProviderPresentation(
  catalog: Pick<Catalog, "custom_providers"> | null | undefined,
  service: CustomProviderService,
  profile: Pick<CatalogProfile, "binding" | "custom_provider_id" | "name">,
  fallbackLabel = "",
): ProviderPresentation {
  const definition = customProviderById(catalog, profile.custom_provider_id);
  if (definition && definition.service === service) {
    return {
      providerLabel: definition.name,
      providerIcon: definition.icon ?? null,
      customProviderId: definition.id,
    };
  }
  return {
    providerLabel: fallbackLabel || profile.binding || profile.name || "",
    providerIcon: null,
    customProviderId: null,
  };
}

export function cleanCustomProviderName(value: string): string {
  return value.trim();
}

export function validateCustomProviderName(
  value: string,
  definitions: readonly CustomProviderDefinition[],
  service: CustomProviderService,
  excludeId?: string,
): string | null {
  const name = cleanCustomProviderName(value);
  if (!name || Array.from(name).length > 80) {
    return "名称必须为 1–80 个字符";
  }
  if (/[\u0000-\u001f\u007f]/.test(name)) {
    return "名称不能包含控制字符";
  }
  const folded = name.toLocaleLowerCase();
  if (
    definitions.some(
      (item) =>
        item.id !== excludeId &&
        item.service === service &&
        item.name.trim().toLocaleLowerCase() === folded,
    )
  ) {
    return "同一服务内不能有重名供应商";
  }
  return null;
}

export function validateCustomProviderIcon(
  icon: ProviderIconSpec | null,
): string | null {
  if (!icon) return null;
  if (icon.kind === "builtin") {
    return BUILTIN_ICON_VALUES.includes(icon.value) ? null : "未知图标";
  }
  if (icon.kind === "emoji") {
    const points = Array.from(icon.value);
    if (points.length < 1 || points.length > 8) return "Emoji 必须为 1–8 个字符";
    if (/[\u0000-\u001f\u007f]/.test(icon.value)) return "Emoji 不能包含换行或控制字符";
    return null;
  }
  return "未知图标类型";
}

const CUSTOM_LABEL_KEYS: Record<string, string> = {
  Custom: "Custom (OpenAI-compatible)",
  "Custom (OpenAI API)": "Custom (OpenAI-compatible)",
  "Custom (Anthropic API)": "Custom (Anthropic Messages)",
};

/** Translate the two legacy anonymous custom labels without translating names. */
export function localizeProviderLabel(
  label: string,
  t: (key: string) => string,
  customProviderId?: string | null,
): string {
  if (customProviderId) return label;
  const key = CUSTOM_LABEL_KEYS[label.trim()];
  return key ? t(key) : label;
}

export function connectionLabelText(
  providerLabel: string,
  profileName: string,
  t: (key: string) => string,
  customProviderId?: string | null,
): string {
  const vendor = localizeProviderLabel(providerLabel, t, customProviderId);
  const profile = profileName.trim();
  if (!profile || profile === vendor) return vendor;
  return `${vendor} · ${profile}`;
}

export function protocolLabel(
  service: CustomProviderService,
  binding: string,
  capabilities: CustomProviderCapabilities | null,
): string {
  return (
    capabilities?.protocols[service]?.find((item) => item.value === binding)
      ?.label || binding
  );
}

export function newCustomProviderId(): string {
  const cryptoObject = globalThis.crypto;
  const uuid =
    cryptoObject && typeof cryptoObject.randomUUID === "function"
      ? cryptoObject.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `cp_${uuid}`;
}

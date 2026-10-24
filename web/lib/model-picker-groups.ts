import {
  llmOptionLabel,
  llmSelectionKey,
  type LLMOption,
} from "@/lib/llm-options";
import type { LLMSelection } from "@/lib/unified-ws";
import type { ProviderIconSpec } from "@/lib/custom-providers";

/**
 * Pure grouping for the two-layer chat picker.
 *
 * The stable key is the authorised profile id.  Two connections for the same
 * vendor remain separate even when their model names are identical; model id
 * prefixes and ``owned_by`` are never used to guess a service origin.
 */

export interface LLMOptionGroup {
  profileId: string;
  profileName: string;
  provider: string;
  providerLabel: string;
  providerIcon?: ProviderIconSpec | null;
  customProviderId?: string | null;
  /** Provider + connection name, used as the first-layer heading. */
  connectionLabel: string;
  options: LLMOption[];
  hiddenOptions: LLMOption[];
  count: number;
}

export function modelOptionSource(option: LLMOption): string {
  return (
    option.provider_label ||
    option.provider ||
    option.profile_name ||
    "LLM"
  );
}

function connectionLabel(option: LLMOption, _duplicateVendor: boolean): string {
  const vendor = modelOptionSource(option);
  const profile = (option.profile_name || "").trim();
  if (!profile || profile === vendor) return vendor;
  return `${vendor} · ${profile}`;
}

export function groupLLMOptions(
  options: readonly LLMOption[],
  hiddenOptions: readonly LLMOption[] = [],
): LLMOptionGroup[] {
  const all = [...options, ...hiddenOptions];
  const profilesByVendor = new Map<string, Set<string>>();
  for (const option of all) {
    const vendor = modelOptionSource(option);
    const set = profilesByVendor.get(vendor) ?? new Set<string>();
    set.add(option.profile_id);
    profilesByVendor.set(vendor, set);
  }
  const groups = new Map<string, LLMOptionGroup>();
  for (const option of all) {
    if (!option.profile_id) continue;
    let group = groups.get(option.profile_id);
    if (!group) {
      const vendor = modelOptionSource(option);
      group = {
        profileId: option.profile_id,
        profileName: option.profile_name || option.profile_id,
        provider: option.provider || "",
        providerLabel: vendor,
        providerIcon: option.provider_icon ?? null,
        customProviderId: option.custom_provider_id ?? null,
        connectionLabel: connectionLabel(
          option,
          (profilesByVendor.get(vendor)?.size ?? 0) > 1,
        ),
        options: [],
        hiddenOptions: [],
        count: 0,
      };
      groups.set(option.profile_id, group);
    }
    if (option.hidden || hiddenOptions.includes(option)) {
      group.hiddenOptions.push(option);
    } else {
      group.options.push(option);
    }
    group.count += 1;
  }
  return [...groups.values()].sort((a, b) =>
    `${a.providerLabel}\u0000${a.profileName}\u0000${a.profileId}`.localeCompare(
      `${b.providerLabel}\u0000${b.profileName}\u0000${b.profileId}`,
    ),
  );
}

export function findOptionGroup(
  groups: readonly LLMOptionGroup[],
  selection: LLMSelection | null | undefined,
): LLMOptionGroup | null {
  const key = llmSelectionKey(selection);
  if (!key) return null;
  return (
    groups.find((group) =>
      [...group.options, ...group.hiddenOptions].some(
        (option) => llmSelectionKey(option) === key,
      ),
    ) ?? null
  );
}

export interface ModelSearchHit {
  option: LLMOption;
  group: LLMOptionGroup;
  source: string;
  hidden: boolean;
}

export function searchLLMOptions(
  groups: readonly LLMOptionGroup[],
  query: string,
): ModelSearchHit[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const hits: ModelSearchHit[] = [];
  for (const group of groups) {
    for (const [options, hidden] of [
      [group.options, false],
      [group.hiddenOptions, true],
    ] as const) {
      for (const option of options) {
        const haystack = [
          llmOptionLabel(option),
          option.model,
          option.profile_name,
          option.provider_label,
          option.provider,
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(needle)) continue;
        hits.push({
          option,
          group,
          source: modelOptionSource(option),
          hidden,
        });
      }
    }
  }
  return hits.sort((a, b) => {
    const labelA = llmOptionLabel(a.option).toLowerCase();
    const labelB = llmOptionLabel(b.option).toLowerCase();
    return (
      labelA.localeCompare(labelB) ||
      a.source.localeCompare(b.source) ||
      a.option.profile_id.localeCompare(b.option.profile_id)
    );
  });
}

import type { LLMOption, LLMOptionsResponse } from "@/lib/llm-options";
import type { LLMSelection } from "@/lib/unified-ws";

export type LLMOptionsStatus = "loading" | "ready" | "error";

export interface LLMOptionsState {
  options: LLMOption[];
  hiddenOptions: LLMOption[];
  hasUsableModels: boolean;
  activeDefault: LLMSelection | null;
  status: LLMOptionsStatus;
}

export type LLMOptionsAction =
  | { type: "refresh-started"; background: boolean }
  | { type: "refresh-succeeded"; payload: LLMOptionsResponse }
  | { type: "refresh-failed" };

export const INITIAL_LLM_OPTIONS_STATE: LLMOptionsState = {
  options: [],
  hiddenOptions: [],
  hasUsableModels: false,
  activeDefault: null,
  status: "loading",
};

/**
 * State transitions for the model selector's stale-while-revalidate behavior.
 *
 * A page-return refresh is a catalog synchronization, not a model startup. It
 * therefore keeps the last usable catalog visible and only replaces it after a
 * successful response. Initial loading still has an explicit loading/error
 * state because there is no usable catalog to fall back to yet.
 */
export function reduceLLMOptionsState(
  state: LLMOptionsState,
  action: LLMOptionsAction,
): LLMOptionsState {
  switch (action.type) {
    case "refresh-started":
      return action.background ? state : { ...state, status: "loading" };
    case "refresh-succeeded": {
      const hiddenOptions = action.payload.hidden_options ?? [];
      return {
        options: action.payload.options,
        hiddenOptions,
        hasUsableModels:
          action.payload.has_usable_models ??
          (action.payload.options.length > 0 || hiddenOptions.length > 0),
        activeDefault: action.payload.active,
        status: "ready",
      };
    }
    case "refresh-failed":
      return state.options.length > 0 || state.hiddenOptions.length > 0
        ? { ...state, status: "ready" }
        : { ...state, status: "error" };
  }
}

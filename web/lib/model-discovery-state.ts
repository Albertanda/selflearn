/**
 * Pure state transitions for the discovery panel.
 *
 * The request key includes the service, profile, and connection identity.  It
 * is intentionally checked in the reducer, not only with a loading flag: a
 * late A response must not replace B's candidates, draft, or cache badge.
 */

import type { DiscoveryResponse } from "./model-discovery";

export interface ModelDiscoveryState {
  requestKey: string;
  response: DiscoveryResponse | null;
  loading: boolean;
  error: string | null;
}

export type ModelDiscoveryAction =
  | { type: "reset" }
  | { type: "request-started"; requestKey: string }
  | { type: "request-succeeded"; requestKey: string; response: DiscoveryResponse }
  | { type: "request-failed"; requestKey: string; message: string };

export const INITIAL_MODEL_DISCOVERY_STATE: ModelDiscoveryState = {
  requestKey: "",
  response: null,
  loading: false,
  error: null,
};

export function reduceModelDiscoveryState(
  state: ModelDiscoveryState,
  action: ModelDiscoveryAction,
): ModelDiscoveryState {
  switch (action.type) {
    case "reset":
      return INITIAL_MODEL_DISCOVERY_STATE;
    case "request-started":
      return {
        requestKey: action.requestKey,
        response: state.response,
        loading: true,
        error: null,
      };
    case "request-succeeded":
      if (action.requestKey !== state.requestKey) return state;
      return {
        requestKey: state.requestKey,
        response:
          action.response.status === "error" && action.response.models.length === 0 && state.response?.models.length
            ? { ...action.response, models: state.response.models }
            : action.response,
        loading: false,
        error: null,
      };
    case "request-failed":
      if (action.requestKey !== state.requestKey) return state;
      return {
        ...state,
        loading: false,
        error: action.message,
      };
    default:
      return state;
  }
}

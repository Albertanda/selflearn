"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import type { CatalogProfile, ServiceName } from "@/components/settings/SettingsContext";
import { apiFetch, apiUrl } from "@/lib/api";
import {
  autoDiscoveryAllowed,
  connectionIdentity,
  isDiscoveryService,
  parseDiscoveryResponse,
  savedConnectionRevision,
  type DiscoveryConnection,
  type DiscoveryMode,
  type DiscoveryResponse,
} from "@/lib/model-discovery";
import {
  INITIAL_MODEL_DISCOVERY_STATE,
  reduceModelDiscoveryState,
} from "@/lib/model-discovery-state";

const AUTO_REQUESTS = new Map<string, Promise<DiscoveryResponse>>();

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      detail?: unknown;
      error?: { message?: unknown };
    };
    if (payload.error && typeof payload.error.message === "string") {
      return payload.error.message;
    }
    if (typeof payload.detail === "string") return payload.detail;
  } catch {
    // Fall through to the HTTP status only.
  }
  return `目录查询失败 (HTTP ${response.status})`;
}

function parseHeaders(profile: CatalogProfile): Record<string, string> | string | undefined {
  const raw = profile.extra_headers;
  if (raw === undefined) return undefined;
  if (typeof raw !== "string") return raw;
  if (raw === "***") return raw;
  if (!raw.trim()) return {};
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("附加请求头必须是 JSON 对象。");
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [
      key,
      String(value ?? ""),
    ]),
  );
}

function connectionBody(profile: CatalogProfile): DiscoveryConnection {
  return {
    binding: profile.binding ?? "",
    base_url: profile.base_url ?? "",
    api_key: profile.api_key ?? "",
    api_version: profile.api_version ?? "",
    extra_headers: parseHeaders(profile),
    model_directory_url: profile.model_directory_url ?? "",
  };
}

function postDiscovery(
  body: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<DiscoveryResponse> {
  return apiFetch(apiUrl("/api/v1/settings/model-discovery"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal,
  }).then(async (response) => {
    if (!response.ok) throw new Error(await readError(response));
    return parseDiscoveryResponse(await response.json());
  });
}

function requestAuto(key: string, body: Record<string, unknown>): Promise<DiscoveryResponse> {
  const existing = AUTO_REQUESTS.get(key);
  if (existing) return existing;
  const promise = postDiscovery(body);
  AUTO_REQUESTS.set(key, promise);
  const clear = () => {
    if (AUTO_REQUESTS.get(key) === promise) AUTO_REQUESTS.delete(key);
  };
  promise.then(clear, clear);
  return promise;
}

/**
 * Owns one profile's candidate directory.
 *
 * Automatic cache-first reads happen only for the active *saved* profile and
 * only while the draft still matches that saved connection.  A draft edit
 * invalidates any in-flight response and never causes a request by itself.
 */
export function useModelDiscovery(options: {
  service: ServiceName;
  profile: CatalogProfile | null;
  savedProfile: CatalogProfile | null;
}) {
  const { service, profile, savedProfile } = options;
  const [state, dispatch] = useReducer(
    reduceModelDiscoveryState,
    INITIAL_MODEL_DISCOVERY_STATE,
  );
  const latestTokenRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const latestProfileRef = useRef(profile);
  latestProfileRef.current = profile;

  const savedIdentity = connectionIdentity(savedProfile);
  const draftIdentity = connectionIdentity(profile);
  const savedRevision = savedConnectionRevision(savedProfile);
  const latestSavedRevisionRef = useRef(savedRevision);
  latestSavedRevisionRef.current = savedRevision;
  const matchesSaved =
    Boolean(savedProfile && profile && savedProfile.id === profile.id) &&
    savedIdentity === draftIdentity;
  const identity = isDiscoveryService(service)
    ? `${service}:${profile?.id ?? ""}:${draftIdentity}:${savedRevision}`
    : "";
  const previousIdentityRef = useRef(identity);

  useEffect(() => {
    if (previousIdentityRef.current === identity) return;
    previousIdentityRef.current = identity;
    latestTokenRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    dispatch({ type: "reset" });
  }, [identity]);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const query = useCallback(
    async (mode: DiscoveryMode = "cache_first") => {
      const current = latestProfileRef.current;
      if (!current || !isDiscoveryService(service)) return;
      const token = ++latestTokenRef.current;
      const requestRevision = savedRevision;
      const requestIdentity = `${service}:${current.id}:${connectionIdentity(current)}`;
      const requestKey = `${requestIdentity}#${token}`;
      const saved = savedProfile;
      const sameAsSaved =
        Boolean(saved && saved.id === current.id) &&
        connectionIdentity(saved) === connectionIdentity(current);
      let body: Record<string, unknown>;
      try {
        body = {
          service,
          mode,
          ...(sameAsSaved && saved
            ? { profile_id: saved.id }
            : {
                ...(saved && saved.id === current.id
                  ? { profile_id: saved.id }
                  : {}),
                connection: connectionBody(current),
              }),
        };
      } catch (error) {
        dispatch({ type: "request-started", requestKey });
        dispatch({
          type: "request-failed",
          requestKey,
          message: error instanceof Error ? error.message : String(error),
        });
        return;
      }
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      dispatch({ type: "request-started", requestKey });
      try {
        const response = await postDiscovery(body, controller.signal);
        if (
          token !== latestTokenRef.current ||
          requestRevision !== latestSavedRevisionRef.current ||
          requestIdentity !==
            `${service}:${latestProfileRef.current?.id ?? ""}:${connectionIdentity(
              latestProfileRef.current,
            )}`
        ) {
          return;
        }
        dispatch({
          type: "request-succeeded",
          requestKey,
          response,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (token !== latestTokenRef.current) return;
        dispatch({
          type: "request-failed",
          requestKey,
          message: error instanceof Error ? error.message : String(error),
        });
      } finally {
        if (controllerRef.current === controller) controllerRef.current = null;
      }
    },
    [savedProfile, service, savedRevision],
  );

  const autoKey =
    isDiscoveryService(service) &&
    autoDiscoveryAllowed(profile, savedProfile) &&
    matchesSaved
      ? `${service}:${savedProfile?.id ?? ""}:${savedIdentity}:${savedRevision}`
      : "";

  useEffect(() => {
    if (!autoKey || !savedProfile) return;
    let active = true;
    const token = ++latestTokenRef.current;
    const requestIdentity = `${service}:${savedProfile.id}:${savedIdentity}`;
    dispatch({
      type: "request-started",
      requestKey: `${requestIdentity}#${token}`,
    });
    requestAuto(autoKey, {
      service,
      profile_id: savedProfile.id,
      mode: "cache_first",
    })
      .then((response) => {
        if (!active || token !== latestTokenRef.current || savedRevision !== latestSavedRevisionRef.current) return;
        if (
          requestIdentity !==
          `${service}:${latestProfileRef.current?.id ?? ""}:${connectionIdentity(
            latestProfileRef.current,
          )}`
        ) {
          return;
        }
        dispatch({
          type: "request-succeeded",
          requestKey: `${requestIdentity}#${token}`,
          response,
        });
      })
      .catch((error: unknown) => {
        if (!active || token !== latestTokenRef.current) return;
        dispatch({
          type: "request-failed",
          requestKey: `${requestIdentity}#${token}`,
          message: error instanceof Error ? error.message : String(error),
        });
      });
    return () => {
      active = false;
    };
  }, [autoKey, savedIdentity, savedProfile, service, savedRevision]);

  const refresh = useCallback(() => query("refresh"), [query]);
  const retry = useCallback(() => query("refresh"), [query]);
  const reset = useCallback(() => {
    latestTokenRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  return {
    ...state,
    identity,
    matchesSaved,
    query,
    refresh,
    retry,
    reset,
  };
}

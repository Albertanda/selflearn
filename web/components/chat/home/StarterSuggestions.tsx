"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { apiFetch, apiUrl } from "@/lib/api";

interface Suggestion {
  /** The line the learner reads — names the specific thing worth doing next. */
  label: string;
  /** What gets sent as the learner's own message when they click. */
  prompt: string;
}

interface SuggestionPayload {
  suggestions: Suggestion[];
  /** True when the backend is regenerating this set behind the request. */
  stale: boolean;
}

/**
 * How long to wait before re-reading a set the backend said was stale.
 *
 * The backend answers instantly with the previous set and regenerates behind
 * the request, so a fresh one exists a moment later. One delayed re-read picks
 * it up without polling.
 */
const RESETTLE_MS = 3500;

/**
 * Shown when memory has nothing to suggest from — a new install, or a learner
 * who has not started anything yet. Fixed product copy rather than a generated
 * line: with no history there is nothing to ground a suggestion in, and asking
 * a model anyway would only produce invention.
 *
 * Still written to propose something specific. These cannot name the learner's
 * own material, but they can name a concrete first move rather than a category
 * of activity — "find where a shaky concept breaks down" instead of "explain a
 * topic".
 */
const FALLBACK: Suggestion[] = [
  {
    label: "Start with the concept you're least sure of",
    prompt:
      "I want to start with a concept I'm shaky on — ask me a few questions to find where it breaks down.",
  },
  {
    label: "Ten questions to find my gaps",
    prompt:
      "Give me ten questions on a subject I name, easy to hard, and tell me where my gaps are.",
  },
  {
    label: "Turn a document into something I can explain",
    prompt:
      "I have a document I need to be able to explain in my own words. Where do we start?",
  },
];

/**
 * The three starting points under the home composer.
 *
 * Each line shows its ``label`` and sends its ``prompt`` — the full sentence
 * the learner would have typed — so a click starts a real conversation rather
 * than prefilling something they still have to finish. Generation, caching and
 * staleness live on the backend; this renders the result and offers a reroll.
 *
 * One per line, left-aligned to the composer's own edge, with no border or
 * fill: the lines name specific things, and a specific sentence in a pill
 * reads as a tag rather than as an invitation. The arrow carries the
 * invitation instead, and is the only coloured element at rest.
 *
 * Renders nothing until the first response lands: lines appearing a beat late
 * is calmer than fixed copy visibly swapping for generated copy.
 */
export default function StarterSuggestions({
  onPick,
  disabled = false,
}: {
  /** Send this text as the learner's message, starting the session. */
  onPick: (prompt: string) => void;
  disabled?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.language?.toLowerCase().startsWith("zh") ? "zh" : "en";
  /**
   * Generated lines are already in the learner's language and must not go
   * through the i18n table — a generated label that happened to match a key
   * would be silently replaced by an unrelated translation. Only the fixed
   * starters are keys.
   */
  const [starters, setStarters] = useState<{
    items: Suggestion[];
    source: "generated" | "fixed";
  } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal): Promise<SuggestionPayload | null> => {
      try {
        const response = await apiFetch(
          apiUrl(`/api/v1/dashboard/suggestions?language=${language}`),
          { signal, cache: "no-store" },
        );
        if (!response.ok) return null;
        return (await response.json()) as SuggestionPayload;
      } catch {
        return null;
      }
    },
    [language],
  );

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const payload = await load(controller.signal);
      // A failed read falls back rather than leaving the list empty — the
      // fixed starters are useful on their own.
      if (!payload?.suggestions.length) {
        setStarters({ items: FALLBACK, source: "fixed" });
        if (!payload?.stale) return;
      } else {
        setStarters({ items: payload.suggestions, source: "generated" });
        if (!payload.stale) return;
      }
      // A fresher set is being generated; collect it once rather than poll.
      timerRef.current = setTimeout(() => {
        void load(controller.signal).then((next) => {
          if (next?.suggestions.length) {
            setStarters({ items: next.suggestions, source: "generated" });
          }
        });
      }, RESETTLE_MS);
    })();
    return () => {
      controller.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [load]);

  const reroll = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await apiFetch(
        apiUrl(`/api/v1/dashboard/suggestions/refresh?language=${language}`),
        { method: "POST" },
      );
      if (response.ok) {
        const payload = (await response.json()) as SuggestionPayload;
        // Keep what is on screen when the reroll came back empty: replacing
        // three usable lines with nothing is worse than not rerolling.
        if (payload.suggestions.length) {
          setStarters({ items: payload.suggestions, source: "generated" });
        }
      }
    } catch {
      // A failed reroll is not worth an error message.
    } finally {
      setRefreshing(false);
    }
  }, [language]);

  if (!starters?.items.length) return null;
  const text = (value: string) => (starters.source === "fixed" ? t(value) : value);

  return (
    // max-w-[768px] + px-6 mirrors ChatComposer's own empty-state container, so
    // the lines start exactly at the composer's left edge rather than floating
    // near it.
    <div className="group/starters mx-auto w-full max-w-[768px] px-6 pb-6 animate-fade-in">
      <ul className="flex flex-col items-start">
        {starters.items.map((item) => (
          <li key={item.label} className="max-w-full">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(text(item.prompt))}
              title={text(item.prompt)}
              className="group/line flex max-w-full items-baseline gap-2 py-[5px] text-left font-serif text-[15.5px] leading-[1.45] tracking-[-0.005em] text-[color-mix(in_srgb,var(--foreground)_72%,transparent)] transition-colors duration-200 hover:text-[var(--primary)] focus-visible:text-[var(--primary)] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="truncate">{text(item.label)}</span>
              {/* The arrow is the invitation: coloured at rest so the line
                  reads as something to click, and it steps right on hover. */}
              <span
                aria-hidden="true"
                className="shrink-0 text-[color-mix(in_srgb,var(--primary)_65%,transparent)] transition-all duration-200 ease-out group-hover/line:translate-x-1 group-hover/line:text-[var(--primary)] group-focus-visible/line:translate-x-1"
              >
                →
              </span>
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => void reroll()}
        disabled={refreshing || disabled}
        title={t("Suggest something else")}
        className="mt-1.5 inline-flex items-center gap-1.5 text-[11.5px] text-[color-mix(in_srgb,var(--muted-foreground)_55%,transparent)] opacity-0 transition-all duration-200 hover:text-[var(--foreground)] focus-visible:opacity-100 disabled:opacity-30 group-hover/starters:opacity-100"
      >
        <RefreshCw
          size={11}
          strokeWidth={1.8}
          className={refreshing ? "animate-spin" : ""}
        />
        {t("Suggest something else")}
      </button>
    </div>
  );
}

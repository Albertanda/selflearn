"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { apiFetch, apiUrl } from "@/lib/api";

interface Suggestion {
  /** What the chip says — a few words. */
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
 */
const FALLBACK: Suggestion[] = [
  {
    label: "Explain a topic",
    prompt:
      "I want to learn a new topic — start me off with the big picture, then go deeper.",
  },
  {
    label: "Quiz me",
    prompt:
      "Give me five questions on a topic I choose, easy to hard, and explain after I answer.",
  },
  {
    label: "Work through a document",
    prompt: "I have a document I want to understand. How should we start?",
  },
];

/**
 * The three starter chips under the home composer.
 *
 * Each chip shows its ``label`` and sends its ``prompt`` — the full sentence
 * the learner would have typed — so a click starts a real conversation rather
 * than prefilling something they still have to finish. Generation, caching and
 * staleness live on the backend; this renders the result and offers a reroll.
 *
 * Renders nothing until the first response lands: chips appearing a beat late
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
   * Generated chips are already in the learner's language and must not go
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
      // A failed read falls back rather than leaving the row empty — the
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
        // three usable chips with nothing is worse than not rerolling.
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
    <div className="group/starters mx-auto flex w-full max-w-[960px] flex-wrap items-center justify-center gap-2 px-6 pb-3 animate-fade-in">
      {starters.items.map((item) => (
        <button
          key={item.label}
          type="button"
          disabled={disabled}
          onClick={() => onPick(text(item.prompt))}
          title={text(item.prompt)}
          className="max-w-full truncate rounded-full border border-[var(--border)] bg-[var(--background)] px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--muted-foreground)] transition-colors hover:border-[var(--foreground)]/20 hover:bg-[var(--secondary)] hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {text(item.label)}
        </button>
      ))}
      <button
        type="button"
        onClick={() => void reroll()}
        disabled={refreshing || disabled}
        title={t("Suggest something else")}
        aria-label={t("Suggest something else")}
        className="shrink-0 rounded-full p-1.5 text-[var(--muted-foreground)]/40 opacity-0 transition-all hover:bg-[var(--secondary)] hover:text-[var(--foreground)] focus-visible:opacity-100 disabled:opacity-30 group-hover/starters:opacity-100"
      >
        <RefreshCw
          size={13}
          strokeWidth={1.8}
          className={refreshing ? "animate-spin" : ""}
        />
      </button>
    </div>
  );
}

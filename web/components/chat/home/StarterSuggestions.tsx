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
 * How long to wait before re-reading a set the backend said was stale, and how
 * many times.
 *
 * The backend answers instantly and regenerates behind the request, so the
 * fresh set exists a moment later — but "a moment" is a model call, which on a
 * cold provider is comfortably longer than one interval. A few spaced re-reads
 * cover that without turning into a poll; they stop as soon as something
 * arrives, and the first visit of a session is the only time they all run.
 */
const RESETTLE_MS = 3500;
const RESETTLE_ATTEMPTS = 4;

/**
 * The three things worth exploring next, under the home composer.
 *
 * Each line shows its ``label`` — a specific thing worth understanding, drawn
 * from what this learner has actually been working on — and sends its
 * ``prompt`` as their own message, so a click starts a real conversation
 * rather than prefilling something they still have to finish. Generation,
 * caching and staleness live on the backend; this renders the result and
 * offers a reroll.
 *
 * There is no fixed fallback, and that is deliberate. The whole value of these
 * lines is that they are about *this* learner's material; generic copy in the
 * same slot would teach them to ignore it. With nothing in memory to draw on,
 * the component renders nothing at all and the home screen looks exactly as it
 * did before.
 *
 * One per line, left-aligned to the composer's own edge, with no border or
 * fill: these name specific ideas, and a specific sentence in a pill reads as
 * a tag rather than as an invitation. The arrow carries the invitation
 * instead, and is the only coloured element at rest.
 */
export default function StarterSuggestions({
  onPick,
  disabled = false,
}: {
  /** Send this text as the learner's message, starting the session. */
  onPick: (prompt: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  // Everything rendered here is generated, already in the learner's chosen
  // output language (resolved server-side from their model-output setting),
  // and never goes through the i18n table — a label that happened to match a
  // key would be silently replaced by an unrelated translation.
  const [items, setItems] = useState<Suggestion[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal): Promise<SuggestionPayload | null> => {
      try {
        const response = await apiFetch(
          apiUrl("/api/v1/dashboard/suggestions"),
          { signal, cache: "no-store" },
        );
        if (!response.ok) return null;
        return (await response.json()) as SuggestionPayload;
      } catch {
        return null;
      }
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const payload = await load(controller.signal);
      if (!payload) return;
      setItems(payload.suggestions);
      if (!payload.stale) return;
      // A fresher set is being generated — which is also the ordinary first
      // visit, where memory has material but nothing has been generated from
      // it yet. Collect it as it lands rather than poll: the first look is
      // early enough for a cache hit, the later ones cover a slow model.
      let attempt = 0;
      const collect = () => {
        void load(controller.signal).then((next) => {
          if (next?.suggestions.length) {
            setItems(next.suggestions);
            return;
          }
          if (++attempt < RESETTLE_ATTEMPTS && !controller.signal.aborted) {
            timerRef.current = setTimeout(collect, RESETTLE_MS);
          }
        });
      };
      timerRef.current = setTimeout(collect, RESETTLE_MS);
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
        apiUrl("/api/v1/dashboard/suggestions/refresh"),
        { method: "POST" },
      );
      if (response.ok) {
        const payload = (await response.json()) as SuggestionPayload;
        // Keep what is on screen when the reroll came back empty: replacing
        // three usable lines with nothing is worse than not rerolling.
        if (payload.suggestions.length) setItems(payload.suggestions);
      }
    } catch {
      // A failed reroll is not worth an error message.
    } finally {
      setRefreshing(false);
    }
  }, []);

  if (!items.length) return null;

  return (
    // max-w-[768px] + px-6 mirrors ChatComposer's own empty-state container, so
    // the lines start exactly at the composer's left edge rather than floating
    // near it.
    <div className="group/starters mx-auto w-full max-w-[768px] px-6 pb-6 animate-fade-in">
      <ul className="flex flex-col items-start">
        {items.map((item) => (
          <li key={item.label} className="max-w-full">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(item.prompt)}
              title={item.prompt}
              className="group/line flex max-w-full items-baseline gap-2 py-[5px] text-left font-serif text-[15.5px] leading-[1.45] tracking-[-0.005em] text-[color-mix(in_srgb,var(--foreground)_72%,transparent)] transition-colors duration-200 hover:text-[var(--primary)] focus-visible:text-[var(--primary)] focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="truncate">{item.label}</span>
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

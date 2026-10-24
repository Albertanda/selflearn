"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

export type SubjectOption = { id: string; name: string };

/**
 * Subject selector (composer toolbar). Picks the subject-scoped context for
 * this session: knowledge index + exam points + wrong book + profile are
 * injected server-side on every turn.
 *
 * "无科目" is a real, selectable option — not just the empty-state label. A
 * learner whose saved subject was deleted must be able to clear the scope
 * explicitly and keep chatting (C08/C13); before this the only way back was
 * editing the session out of band. ``onChange("")`` is that explicit clear, and
 * the caller maps it to an explicit ``null`` on the wire.
 */
export default function SubjectSelector({
  subjects,
  value,
  onChange,
  placement = "top",
}: {
  subjects: SubjectOption[];
  value: string;
  onChange: (id: string) => void;
  /**
   * Which way the menu opens. The composer toolbar sits at the bottom of the
   * window, so the shared default is "top" (open upward) — the same convention
   * ModelSelector / PersonaSelector / KnowledgeSelector use. Opening downward
   * put this menu past the viewport edge, where it was clipped and the last
   * entries could not be clicked.
   */
  placement?: "top" | "bottom";
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = subjects.find((s) => s.id === value);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  // With no subjects available the trigger still renders when a value is set:
  // the learner's subject may have just been deleted, and the only way back to a
  // usable session is the explicit "无科目" entry below. Hiding the control made
  // that clear unreachable (the session stayed scoped to a subject that no
  // longer exists).
  if (subjects.length === 0 && !value) return null;

  // Same placement + viewport-safe width contract as the other composer
  // selectors, so a long subject name cannot push the menu off-screen either.
  const menuPlacementClass =
    placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={
          "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs " +
          (current
            ? "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400"
            : "border-border/40 text-muted-foreground")
        }
        title={t("Subject context", "科目上下文")}
      >
        <BookOpen size={13} strokeWidth={1.8} />
        <span className="max-w-[9rem] truncate">
          {current ? current.name : t("无科目", "无科目")}
        </span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div
          className={`absolute left-0 z-50 ${menuPlacementClass} max-h-72 w-[min(240px,calc(100vw-32px))] overflow-y-auto rounded-lg border bg-background p-1 shadow-lg`}
        >
          <button
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
            className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/5"
          >
            <span className="truncate text-muted-foreground">
              {t("无科目", "No subject")}
            </span>
            {!current && <Check size={14} className="text-emerald-600" />}
          </button>
          {subjects.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                onChange(s.id);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/5"
            >
              <span className="truncate">{s.name}</span>
              {s.id === value && <Check size={14} className="text-emerald-600" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

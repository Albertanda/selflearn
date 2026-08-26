"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

export type SubjectOption = { id: string; name: string };

/**
 * Subject selector (composer toolbar). Picks the subject-scoped context for
 * this session: knowledge index + exam points + wrong book + profile are
 * injected server-side on every turn.
 */
export default function SubjectSelector({
  subjects,
  value,
  onChange,
}: {
  subjects: SubjectOption[];
  value: string;
  onChange: (id: string) => void;
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

  if (subjects.length === 0) return null;

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
        <div className="absolute left-0 top-full z-50 mt-1 max-h-72 w-56 overflow-y-auto rounded-lg border bg-background p-1 shadow-lg">
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

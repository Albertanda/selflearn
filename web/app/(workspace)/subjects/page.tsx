"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch } from "@/lib/api";
import AsrJobPanel from "@/components/subjects/AsrJobPanel";
import {
  createSubjectAction,
  deleteSubjectAction,
  loadSubjectsView,
  uploadSubjectMaterialAction,
  type KnowledgeProjection,
} from "@/lib/subject-results";

type Subject = {
  id: string;
  name: string;
  description: string;
  term: string;
  created_at: number;
};

type KbStatus = {
  status: string;
  progress?: { percent?: number; message?: string };
};

type KnowledgeRecord = {
  kb_name: string;
  type: string;
  documents: number;
  status: KbStatus;
};

export default function SubjectsPage() {
  const { t } = useTranslation();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [knowledge, setKnowledge] = useState<Record<string, KnowledgeRecord[]>>({});
  const [name, setName] = useState("");
  const [term, setTerm] = useState("");
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const mounted = useRef(true);
  const loadGeneration = useRef(0);
  const isCurrent = () => mounted.current;

  async function load(notify: boolean) {
    const generation = ++loadGeneration.current;
    const view = await loadSubjectsView({
      request: apiFetch,
      isCurrent: () => mounted.current && generation === loadGeneration.current,
      notify,
      onError: setMsg,
      onLoaded: (loaded) => {
        const rows = loaded.subjects as unknown as Subject[];
        setSubjects(rows);
        setKnowledge((previous) => {
          const next: Record<string, KnowledgeRecord[]> = {};
          for (const subject of rows) {
            next[subject.id] =
              (loaded.knowledge[subject.id] as unknown as
                | KnowledgeRecord[]
                | undefined) ?? previous[subject.id] ?? [];
          }
          return next;
        });
      },
    });
    return view?.knowledge ?? {};
  }
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    mounted.current = true;
    void loadRef.current(true);
    const timer = setInterval(() => void loadRef.current(false), 5000);
    return () => {
      mounted.current = false;
      loadGeneration.current += 1;
      clearInterval(timer);
    };
  }, []);

  async function createSubject(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await createSubjectAction({
      request: apiFetch,
      isCurrent,
      name,
      term,
      setBusy,
      onError: setMsg,
      onSuccess: () => {
        setMsg("创建成功");
        void loadRef.current(false);
      },
      clearInputs: () => {
        setName("");
        setTerm("");
      },
    });
  }

  async function uploadFiles(subjectId: string, files: FileList | null, type: string) {
    if (!files || files.length === 0) return;
    const rows = Array.from(files);
    const audio = rows.some((file) => /\.(?:mp3|m4a|wav|flac|ogg|oga|opus|aac|amr|wma)$/i.test(file.name));
    if (audio) {
      setMsg("课堂录音请使用该科目的“课堂录音”入口；文档与录音不能混在同一批。");
      return;
    }
    await uploadSubjectMaterialAction({
      request: apiFetch,
      isCurrent,
      subjectId,
      files: Array.from(files),
      type,
      setBusy: (value) => setUploading((u) => ({ ...u, [subjectId]: value })),
      onError: setMsg,
      onSuccess: setMsg,
      reloadKnowledge: async () => {
        const knowledgeMap = await loadRef.current(false);
        return (knowledgeMap[subjectId] ?? []) as KnowledgeProjection[];
      },
    });
  }

  async function deleteSubject(id: string) {
    if (!confirm(`删除科目 ${id}？将同时删除其全部数据`)) return;
    await deleteSubjectAction({
      request: apiFetch,
      isCurrent,
      subjectId: id,
      setBusy,
      onError: setMsg,
      onSuccess: () => {
        setMsg("科目已删除。");
        void loadRef.current(false);
      },
    });
  }

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable]">
      <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold">科目（Subjects）</h1>
      <p className="mt-1 text-sm opacity-70">
        每科独立管理对话、知识库与错题集；模型配置全局共享。
      </p>

      <form onSubmit={createSubject} className="mt-6 flex flex-wrap gap-3 rounded-xl border p-4">
        <input
          className="rounded-md border bg-transparent px-3 py-1.5 text-sm outline-none"
          placeholder="科目名称（如：常微分方程）"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="rounded-md border bg-transparent px-3 py-1.5 text-sm outline-none"
          placeholder="学期（可选，如 2026秋）"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
        <button
          className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
          type="submit"
          disabled={busy}
        >
          {busy ? "创建中…" : "新建科目"}
        </button>
        {msg && <span className="self-center text-sm text-amber-600">{msg}</span>}
      </form>

      <div className="mt-6 space-y-4">
        {subjects.map((s) => (
          <div key={s.id} className="rounded-xl border p-4">
            <div className="flex items-center justify-between">
              <div>
                <a href={`/subjects/${s.id}`} className="font-semibold text-blue-600 hover:underline">
                  {s.name}
                </a>
                {s.term && <span className="ml-2 text-sm opacity-60">{s.term}</span>}
                <span className="ml-2 text-xs opacity-40">id: {s.id}</span>
              </div>
              <div className="flex gap-2">
                <input
                  type="file"
                  multiple
                  disabled={busy || uploading[s.id]}
                  accept=".pdf,.epub,.ppt,.pptx,.png,.jpg,.jpeg,.docx,.md,.txt"
                  className="hidden"
                  id={`file-${s.id}`}
                  onChange={(e) => uploadFiles(s.id, e.target.files, "auto")}
                />
                <label
                  htmlFor={`file-${s.id}`}
                  className={
                    uploading[s.id] || busy
                      ? "cursor-not-allowed rounded-md bg-emerald-600/60 px-3 py-1 text-sm text-white"
                      : "cursor-pointer rounded-md bg-emerald-600 px-3 py-1 text-sm text-white"
                  }
                >
                  {uploading[s.id] ? "上传中…" : "上传材料"}
                </label>
                <button
                  className="rounded-md bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
                  onClick={() => deleteSubject(s.id)}
                  disabled={busy || uploading[s.id]}
                >
                  {busy ? "处理中…" : "删除"}
                </button>
              </div>
            </div>
            <AsrJobPanel request={apiFetch} subjectId={s.id} compact label="课堂录音" />
            <div className="mt-3 space-y-1 text-sm">
              {(knowledge[s.id] ?? []).length === 0 && (
                <div className="opacity-50">暂无知识库，上传文档后自动创建；课堂录音仅转写。</div>
              )}
              {(knowledge[s.id] ?? []).map((kb) => (
                <div key={kb.kb_name} className="flex items-center gap-2 rounded-lg bg-black/5 px-3 py-1.5">
                  <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-xs text-blue-600">
                    {kb.type}
                  </span>
                  <span className="font-mono text-xs">{kb.kb_name}</span>
                  <span className="text-xs opacity-60">documents: {kb.documents}</span>
                  <span
                    className={
                      kb.status?.status === "ready"
                        ? "text-xs text-emerald-600"
                        : "text-xs text-amber-600"
                    }
                  >
                    {kb.status?.status}
                    {kb.status?.progress?.percent != null
                      ? ` ${kb.status.progress.percent}%`
                      : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
        {subjects.length === 0 && (
          <div className="rounded-xl border border-dashed p-8 text-center text-sm opacity-50">
            还没有科目——先新建一个吧。
          </div>
        )}
      </div>
    </div>
    </div>
  );
}

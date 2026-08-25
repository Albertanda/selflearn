"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch } from "@/lib/api";

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
  const [msg, setMsg] = useState("");

  const refresh = useCallback(async () => {
    const res = await apiFetch("/api/v1/subjects");
    if (res.ok) {
      const data = await res.json();
      setSubjects(data.subjects ?? []);
      const kb: Record<string, KnowledgeRecord[]> = {};
      await Promise.all(
        (data.subjects ?? []).map(async (s: Subject) => {
          const kr = await apiFetch(`/api/v1/subjects/${s.id}/knowledge`);
          if (kr.ok) kb[s.id] = (await kr.json()).knowledge ?? [];
        }),
      );
      setKnowledge(kb);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function createSubject(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const body = new FormData();
    body.append("name", name);
    body.append("term", term);
    const res = await apiFetch("/api/v1/subjects", { method: "POST", body });
    setMsg(res.ok ? "创建成功" : await res.text());
    setName("");
    setTerm("");
    await refresh();
  }

  async function uploadFiles(subjectId: string, files: FileList | null, type: string) {
    if (!files || files.length === 0) return;
    setUploading((u) => ({ ...u, [subjectId]: true }));
    try {
      const body = new FormData();
      body.append("type", type);
      for (const f of Array.from(files)) body.append("files", f);
      const res = await apiFetch(`/api/v1/subjects/${subjectId}/knowledge/upload`, {
        method: "POST",
        body,
      });
      setMsg(res.ok ? "上传成功，正在建索引…" : await res.text());
      await refresh();
    } finally {
      setUploading((u) => ({ ...u, [subjectId]: false }));
    }
  }

  async function deleteSubject(id: string) {
    if (!confirm(`删除科目 ${id}？将同时删除其全部数据`)) return;
    await apiFetch(`/api/v1/subjects/${id}`, { method: "DELETE" });
    await refresh();
  }

  return (
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
        <button className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white" type="submit">
          新建科目
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
                  accept=".pdf,.epub,.ppt,.pptx,.png,.jpg,.jpeg,.mp3,.m4a,.docx,.md,.txt"
                  className="hidden"
                  id={`file-${s.id}`}
                  onChange={(e) => uploadFiles(s.id, e.target.files, "auto")}
                />
                <label
                  htmlFor={`file-${s.id}`}
                  className="cursor-pointer rounded-md bg-emerald-600 px-3 py-1 text-sm text-white"
                >
                  {uploading[s.id] ? "上传中…" : "上传材料"}
                </label>
                <button
                  className="rounded-md bg-red-600 px-3 py-1 text-sm text-white"
                  onClick={() => deleteSubject(s.id)}
                >
                  删除
                </button>
              </div>
            </div>
            <div className="mt-3 space-y-1 text-sm">
              {(knowledge[s.id] ?? []).length === 0 && (
                <div className="opacity-50">暂无知识库，上传材料后自动创建（默认按文件类型归类）。</div>
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
  );
}

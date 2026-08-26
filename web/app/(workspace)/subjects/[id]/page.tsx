"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "react-i18next";

import { apiFetch } from "@/lib/api";

type WrongEntry = {
  id: string;
  kp: string;
  question: string;
  answer: string;
  status: string;
  mastery: number;
  attempts: { correct: boolean }[];
  archived: boolean;
};

type ExamPoint = {
  id: string;
  content: string;
  level: string;
  evidence: string;
  kp: string;
  term: string;
  confirmed: boolean;
};

type KnowledgeRecord = {
  kb_name: string;
  type: string;
  status: { status: string; progress?: { message?: string } };
};

const STATUS_LABEL: Record<string, string> = {
  repeated: "反复错",
  missed: "错过",
  basic: "基本掌握",
  mastered: "已掌握",
  untracked: "未标记",
};

const LEVEL_LABEL: Record<string, string> = {
  explicit: "明示考点",
  emphasis: "强调考点",
  inferred: "推断考点",
};

export default function SubjectDetailPage() {
  const { id: rawSubjectId } = useParams<{ id: string }>();
  const subjectId = (() => {
    try {
      return decodeURIComponent(rawSubjectId ?? "");
    } catch {
      return rawSubjectId ?? "";
    }
  })();
  const { t } = useTranslation();
  const [tab, setTab] = useState("knowledge");
  const [knowledge, setKnowledge] = useState<KnowledgeRecord[]>([]);
  const [wrongs, setWrongs] = useState<WrongEntry[]>([]);
  const [wrongStatus, setWrongStatus] = useState("");
  const [points, setPoints] = useState<ExamPoint[]>([]);
  const [profile, setProfile] = useState({ explanation_style: "balanced", goals: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [kr, wr, er, pr] = await Promise.all([
      apiFetch(`/api/v1/subjects/${subjectId}/knowledge`),
      apiFetch(`/api/v1/subjects/${subjectId}/wrong-book`),
      apiFetch(`/api/v1/subjects/${subjectId}/exam-points`),
      apiFetch(`/api/v1/subjects/${subjectId}/profile`),
    ]);
    if (kr.ok) setKnowledge((await kr.json()).knowledge ?? []);
    if (wr.ok) setWrongs((await wr.json()).entries ?? []);
    if (er.ok) setPoints((await er.json()).points ?? []);
    if (pr.ok) setProfile((await pr.json()).profile ?? profile);
  }, [subjectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const post = async (path: string, fields: Record<string, string>) => {
    const body = new FormData();
    Object.entries(fields).forEach(([k, v]) => body.append(k, v));
    return apiFetch(`/api/v1/subjects/${subjectId}${path}`, { method: "POST", body });
  };

  async function recordAttempt(entryId: string, correct: boolean) {
    await post(`/wrong-book/${entryId}/attempt`, { correct: String(correct) });
    await refresh();
  }

  async function archiveEntry(entryId: string) {
    await post(`/wrong-book/${entryId}/archive`, {});
    await refresh();
  }

  function filteredWrongs() {
    return wrongStatus ? wrongs.filter((w) => w.status === wrongStatus) : wrongs;
  }

  const tabs = [
    ["knowledge", "知识库"],
    ["wrong", "错题集"],
    ["exam", "期末考点"],
    ["profile", "画像"],
    ["review", "复习包"],
  ] as const;

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable]">
      <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Link href="/subjects" className="text-sm text-blue-600 hover:underline">
          ← 科目列表
        </Link>
        <h1 className="text-2xl font-semibold">{subjectId}</h1>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 border-b pb-2">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={
              tab === key
                ? "rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white"
                : "rounded-md px-3 py-1.5 text-sm hover:bg-black/5"
            }
          >
            {label}
          </button>
        ))}
      </div>
      {msg && <div className="mt-2 text-sm text-amber-600">{msg}</div>}

      {tab === "knowledge" && (
        <div className="mt-4 space-y-3">
          <div className="rounded-xl border p-4">
            <div className="text-sm font-medium">知识库</div>
            <div className="mt-2 space-y-1">
              {knowledge.length === 0 && (
                <div className="text-sm opacity-50">暂无知识库，请在左侧列表页上传材料。</div>
              )}
              {knowledge.map((kb) => (
                <div key={kb.kb_name} className="flex items-center gap-2 rounded-lg bg-black/5 px-3 py-1.5 text-sm">
                  <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-xs text-blue-600">{kb.type}</span>
                  <span className="font-mono text-xs">{kb.kb_name}</span>
                  <span className={kb.status?.status === "ready" ? "text-xs text-emerald-600" : "text-xs text-amber-600"}>
                    {kb.status?.status}
                    {kb.status?.progress?.message ? `（${kb.status.progress.message}）` : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "wrong" && (
        <div className="mt-4">
          <div className="mb-3 flex gap-2">
            {["", "repeated", "missed", "basic", "mastered"].map((s) => (
              <button
                key={s || "all"}
                onClick={() => setWrongStatus(s)}
                className={wrongStatus === s ? "rounded-md bg-blue-600 px-2.5 py-1 text-xs text-white" : "rounded-md bg-black/5 px-2.5 py-1 text-xs"}
              >
                {s ? STATUS_LABEL[s] : "全部"}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            {filteredWrongs().map((w) => (
              <div key={w.id} className="rounded-xl border p-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-mono text-xs text-gray-500">{w.kp || "未标注知识点"}</span>
                  <span className="text-xs">
                    <span className={w.status === "repeated" ? "text-red-600" : w.status === "mastered" ? "text-emerald-600" : "text-amber-600"}>
                      {STATUS_LABEL[w.status]}
                    </span>
                    <span className="ml-2 opacity-50">掌握度 {w.mastery}</span>
                    <span className="ml-2 opacity-40">
                      作答 {w.attempts.filter((a) => a.correct).length}✓/{w.attempts.length}
                    </span>
                  </span>
                </div>
                <div className="mt-1 text-sm">{w.question}</div>
                {w.answer && <div className="mt-1 text-xs opacity-60">答案：{w.answer}</div>}
                <div className="mt-2 flex gap-2">
                  <button onClick={() => recordAttempt(w.id, true)} className="rounded bg-emerald-600 px-2 py-0.5 text-xs text-white">记录答对</button>
                  <button onClick={() => recordAttempt(w.id, false)} className="rounded bg-red-600 px-2 py-0.5 text-xs text-white">记录答错</button>
                  {!w.archived && (
                    <button onClick={() => archiveEntry(w.id)} className="rounded bg-gray-500 px-2 py-0.5 text-xs text-white">归档</button>
                  )}
                </div>
              </div>
            ))}
            {filteredWrongs().length === 0 && <div className="text-sm opacity-50">暂无错题</div>}
          </div>
        </div>
      )}

      {tab === "exam" && (
        <div className="mt-4 space-y-4">
          <ExamPointDetect subjectId={subjectId} onDone={refresh} />
          <div className="space-y-2">
            {points.map((p) => (
              <div key={p.id} className="rounded-xl border p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs text-amber-600">{LEVEL_LABEL[p.level]}</span>
                  <span className="flex gap-2">
                    {!p.confirmed && (
                      <button onClick={async () => { await post(`/exam-points/${p.id}/confirm`, {}); await refresh(); }} className="rounded bg-emerald-600 px-2 py-0.5 text-xs text-white">确认</button>
                    )}
                    <span className={p.confirmed ? "text-xs text-emerald-600" : "text-xs text-gray-400"}>
                      {p.confirmed ? "已确认" : "待确认"}
                    </span>
                  </span>
                </div>
                <div className="mt-1">{p.content}</div>
                {p.evidence && <div className="mt-1 text-xs opacity-60">证据："{p.evidence}"</div>}
              </div>
            ))}
            {points.length === 0 && <div className="text-sm opacity-50">暂无考点，可粘贴课堂转写文字进行检测</div>}
          </div>
        </div>
      )}

      {tab === "profile" && (
        <div className="mt-4 max-w-lg space-y-4 rounded-xl border p-4">
          <div>
            <div className="text-sm font-medium">回答方式偏好</div>
            <select
              value={profile.explanation_style}
              onChange={(e) => setProfile({ ...profile, explanation_style: e.target.value })}
              className="mt-2 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
            >
              <option value="examples">偏好例子与实际应用</option>
              <option value="theory">偏好先讲透理论推导</option>
              <option value="balanced">两者兼顾</option>
            </select>
          </div>
          <div>
            <div className="text-sm font-medium">学习目标</div>
            <textarea
              value={profile.goals}
              onChange={(e) => setProfile({ ...profile, goals: e.target.value })}
              className="mt-2 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
              rows={2}
            />
          </div>
          <button
            onClick={async () => {
              setBusy(true);
              await post("/profile", { goals: profile.goals, explanation_style: profile.explanation_style });
              setMsg("画像已保存");
              setBusy(false);
            }}
            disabled={busy}
            className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
          >
            保存画像
          </button>
        </div>
      )}

      {tab === "review" && (
        <div className="mt-4 max-w-lg space-y-3 rounded-xl border p-4">
          <div className="text-sm">
            基于期末考点 + 错题集 + 知识点索引生成复习指南。
          </div>
          <div className="flex gap-2">
            {["pdf", "docx"].map((fmt) => (
              <button
                key={fmt}
                onClick={async () => {
                  setBusy(true);
                  const res = await post("/review-pack", { format: fmt, term: "" });
                  if (res.ok) {
                    const data = await res.json();
                    setMsg(`已生成：${decodeURIComponent(data.url)}`);
                    setBusy(false);
                    window.open(data.url, "_blank");
                  } else {
                    setMsg(await res.text());
                    setBusy(false);
                  }
                }}
                disabled={busy}
                className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
              >
                生成 {fmt === "pdf" ? "PDF" : "Word"}
              </button>
            ))}
          </div>
        </div>
      )}

      </div>
    </div>
  );
}

function ExamPointDetect({ subjectId, onDone }: { subjectId: string; onDone: () => void }) {
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");
  const [asrMsg, setAsrMsg] = useState("");

  async function uploadAudio(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setAsrMsg("正在上传录音并转写（ASR）…");
    const body = new FormData();
    body.append("type", "lecture");
    for (const f of Array.from(files)) body.append("files", f);
    const res = await apiFetch(`/api/v1/subjects/${subjectId}/knowledge/upload`, {
      method: "POST",
      body,
    });
    if (res.ok) {
      const data = await res.json();
      const pieces = (data.transcripts ?? []).map((t: { text: string }) => t.text);
      const joined = pieces.join("\n\n");
      if (joined) {
        setTranscript((prev) => (prev ? prev + "\n\n" + joined : joined));
        setAsrMsg(`转写完成（${(data.transcripts ?? []).length} 段，已填入下方检测框）`);
      } else {
        setAsrMsg("转写完成但没有文本内容，请检查录音。");
      }
    } else {
      setAsrMsg(await res.text());
    }
    setBusy(false);
  }

  async function run() {
    if (!transcript.trim()) return;
    setBusy(true);
    const body = new FormData();
    body.append("transcript", transcript);
    body.append("term", "");
    const res = await apiFetch(`/api/v1/subjects/${subjectId}/exam-points/detect`, {
      method: "POST",
      body,
    });
    if (res.ok) {
      const data = await res.json();
      setResult(`检出 ${data.detected} 条候选考点（明示已自动确认，其余请在列表中确认）`);
      onDone();
    } else {
      setResult(await res.text());
    }
    setBusy(false);
  }

  return (
    <div className="rounded-xl border p-4">
      <div className="text-sm font-medium">课堂考点检测</div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs opacity-70">
        <label className="cursor-pointer rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white">
          {busy ? "处理中…" : "上传录音（mp3/m4a/wav）"}
          <input type="file" multiple accept=".mp3,.m4a,.wav,.flac,.ogg,.aac" className="hidden" onChange={(e) => uploadAudio(e.target.files)} />
        </label>
        <span>或直接粘贴讲课转写文字：</span>
      </div>
      {asrMsg && <div className="mt-1 text-xs text-emerald-600">{asrMsg}</div>}
      <textarea
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        rows={4}
        placeholder="粘贴教师讲课转写文本（模拟 ASR 输出）…"
        className="mt-2 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
      />
      <button onClick={run} disabled={busy} className="mt-2 rounded-md bg-amber-600 px-4 py-1.5 text-sm text-white disabled:opacity-50">
        {busy ? "检测中…" : "检测考点"}
      </button>
      {result && <div className="mt-2 text-sm text-amber-600">{result}</div>}
    </div>
  );
}

"use client";

import { useId, useState } from "react";

import { useSubjectAsrJobs } from "@/hooks/useSubjectAsrJobs";
import {
  isActiveJob,
  jobStatusCopy,
  progressPercent,
  type AsrResult,
} from "@/lib/asr-jobs";
import type { SubjectRequest } from "@/lib/subject-results";

const AUDIO_ACCEPT = ".mp3,.m4a,.wav,.flac,.ogg,.oga,.opus,.aac,.amr,.wma";
const AUDIO_EXTENSIONS = new Set(
  AUDIO_ACCEPT.split(",").map((item) => item.toLowerCase()),
);

type Props = {
  request: SubjectRequest;
  subjectId: string;
  isCurrent?: () => boolean;
  onCompleted?: (result: AsrResult, text: string) => void;
  compact?: boolean;
  label?: string;
  title?: string;
};

export default function AsrJobPanel({
  request,
  subjectId,
  isCurrent,
  onCompleted,
  compact = false,
  label = "上传录音（mp3/m4a/wav）",
  title = "课堂录音转写",
}: Props) {
  const inputId = useId();
  const [localError, setLocalError] = useState("");
  const { job, uploading, busy, resultLoading, error, notice, pollWarning, resultConsumed, start, cancel, retry, loadResult } =
    useSubjectAsrJobs({ request, subjectId, isCurrent, onCompleted });

  function choose(files: FileList | null) {
    setLocalError("");
    if (!files || files.length === 0) return;
    const rows = Array.from(files);
    if (rows.length > 16) {
      setLocalError("一次最多上传 16 个录音文件。");
      return;
    }
    for (const file of rows) {
      const dot = file.name.lastIndexOf(".");
      const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
      if (!AUDIO_EXTENSIONS.has(extension)) {
        setLocalError("仅支持 mp3、m4a、wav、flac、ogg、opus、aac、amr、wma 录音。");
        return;
      }
    }
    void start(rows);
  }

  const active = job ? isActiveJob(job) : false;
  const shownError = localError || error;
  const percent = job ? progressPercent(job) : 0;
  const status = job ? jobStatusCopy(job) : "";

  return (
    <div className={compact ? "mt-2 rounded-lg border p-3" : "mt-2 rounded-lg border p-3"}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{title}</span>
        <label
          htmlFor={inputId}
          className={
            uploading || busy || active
              ? "cursor-not-allowed rounded-md bg-blue-600/60 px-3 py-1.5 text-xs text-white"
              : "cursor-pointer rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white"
          }
        >
          {uploading ? "上传中…" : busy ? "处理中…" : label}
          <input
            id={inputId}
            type="file"
            multiple
            accept={AUDIO_ACCEPT}
            className="hidden"
            disabled={uploading || busy || active}
            onChange={(event) => {
              choose(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
        <span className="text-xs opacity-60">
          按时间连续切片；全部片段完成后才发布正式转写。
        </span>
      </div>

      {job && (
        <div className="mt-2 space-y-1" data-asr-job-id={job.job_id} data-asr-status={job.status}>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono opacity-50">{job.job_id.slice(0, 8)}</span>
            <span className={job.status === "failed" ? "text-red-600" : "text-amber-600"}>
              {status}
            </span>
            {job.progress.chunks_total > 0 && (
              <span className="opacity-60">
                片段 {job.progress.chunks_completed}/{job.progress.chunks_total}
              </span>
            )}
          </div>
          {active && (
            <div className="h-1.5 overflow-hidden rounded bg-black/10" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
              <div className="h-full bg-blue-600 transition-all" style={{ width: `${percent}%` }} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {job.can_cancel && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void cancel()}
                className="rounded border px-2 py-1 text-xs disabled:opacity-50"
              >
                取消转写
              </button>
            )}
            {job.can_retry && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void retry()}
                className="rounded border border-amber-500 px-2 py-1 text-xs text-amber-700 disabled:opacity-50"
              >
                继续未完成片段
              </button>
            )}
            {job.status === "completed" && !resultConsumed && (
              <button
                type="button"
                disabled={resultLoading}
                onClick={() => void loadResult()}
                className="rounded border border-emerald-500 px-2 py-1 text-xs text-emerald-700 disabled:opacity-50"
              >
                {resultLoading ? "读取中…" : "使用转写结果"}
              </button>
            )}
          </div>
        </div>
      )}

      {notice && !shownError && notice !== status && (
        <div className="mt-1 text-xs text-emerald-700">{notice}</div>
      )}
      {shownError && <div className="mt-1 text-xs text-red-600">{shownError}</div>}
      {pollWarning && <div className="mt-1 text-xs text-amber-700">{pollWarning}</div>}
    </div>
  );
}

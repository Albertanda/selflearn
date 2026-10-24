"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ASR_JOB_ACCEPTED,
  ASR_JOB_POLL_WARNING,
  ASR_JOB_RECOVERED,
  cancelAsrJob,
  createAsrJob,
  fetchAsrResult,
  getAsrJob,
  isActiveJob,
  jobStatusCopy,
  listAsrJobs,
  mergeTranscriptText,
  retryAsrJob,
  type AsrJobView,
  type AsrResult,
} from "@/lib/asr-jobs";
import {
  SubjectActionError,
  safeThrownMessage,
  type SubjectRequest,
} from "@/lib/subject-results";

export type UseSubjectAsrJobsOptions = {
  request: SubjectRequest;
  subjectId: string;
  isCurrent?: () => boolean;
  onCompleted?: (result: AsrResult, text: string) => void;
};

export type UseSubjectAsrJobs = {
  job: AsrJobView | null;
  jobs: AsrJobView[];
  uploading: boolean;
  busy: boolean;
  resultLoading: boolean;
  error: string;
  notice: string;
  pollWarning: string;
  resultConsumed: boolean;
  start: (files: File[], requestId?: string) => Promise<boolean>;
  cancel: () => Promise<void>;
  retry: () => Promise<void>;
  loadResult: () => Promise<void>;
  refresh: () => Promise<void>;
  reset: () => void;
};

function errorMessage(error: unknown): string {
  return error instanceof SubjectActionError ? error.message : safeThrownMessage(error);
}

function retryablePollFailure(error: unknown): boolean {
  if (!(error instanceof SubjectActionError)) return true;
  if (error.kind === "network") return true;
  return error.status === undefined || error.status === 502 || error.status === 503 || error.status === 504 || error.status === 500;
}

export function useSubjectAsrJobs(options: UseSubjectAsrJobsOptions): UseSubjectAsrJobs {
  const { request, subjectId, isCurrent, onCompleted } = options;
  const [job, setJob] = useState<AsrJobView | null>(null);
  const [jobs, setJobs] = useState<AsrJobView[]>([]);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resultLoading, setResultLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pollWarning, setPollWarning] = useState("");
  const [resultConsumed, setResultConsumed] = useState(false);

  const requestRef = useRef(request);
  const currentRef = useRef(isCurrent);
  const completedRef = useRef(onCompleted);
  const generationRef = useRef(0);
  const jobRef = useRef<AsrJobView | null>(null);
  const deliveredRef = useRef<string | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  requestRef.current = request;
  currentRef.current = isCurrent;
  completedRef.current = onCompleted;

  const current = useCallback(
    (generation?: number) =>
      currentRef.current?.() !== false &&
      (generation === undefined || generation === generationRef.current),
    [],
  );

  const setCurrentJob = useCallback((next: AsrJobView) => {
    const previous = jobRef.current;
    if (previous && previous.job_id === next.job_id && next.revision < previous.revision) {
      return false;
    }
    jobRef.current = next;
    setJob(next);
    return true;
  }, []);

  const deliver = useCallback(
    async (target: AsrJobView, generation: number, force = false) => {
      if (!current(generation) || target.status !== "completed") return;
      if (!force && deliveredRef.current === target.job_id) return;
      deliveredRef.current = target.job_id;
      setResultLoading(true);
      try {
        const result = await fetchAsrResult(requestRef.current, target.subject_id, target.job_id);
        if (!current(generation) || jobRef.current?.job_id !== target.job_id) return;
        const text = mergeTranscriptText(result.transcripts);
        setResultConsumed(true);
        setError("");
        setNotice(jobStatusCopy(target));
        completedRef.current?.(result, text);
      } catch (exc) {
        if (!current(generation)) return;
        deliveredRef.current = null;
        setError(errorMessage(exc));
      } finally {
        if (current(generation)) setResultLoading(false);
      }
    },
    [current],
  );

  const poll = useCallback(
    async (generation: number) => {
      const target = jobRef.current;
      if (!target || !isActiveJob(target) || !current(generation) || inFlightRef.current) return;
      inFlightRef.current = true;
      const controller = new AbortController();
      pollAbortRef.current = controller;
      try {
        const next = await getAsrJob(
          requestRef.current,
          target.subject_id,
          target.job_id,
          controller.signal,
        );
        if (!current(generation)) return;
        if (!setCurrentJob(next)) return;
        setPollWarning("");
        if (next.status === "completed") {
          await deliver(next, generation);
        } else if (next.status === "failed") {
          setError(next.error?.message ?? "转写失败，请重试。");
        } else if (next.status === "interrupted") {
          setNotice(jobStatusCopy(next));
        } else {
          setNotice(jobStatusCopy(next));
        }
      } catch (exc) {
        if (controller.signal.aborted || !current(generation)) return;
        if (exc instanceof SubjectActionError && (exc.status === 404 || exc.status === 409 || exc.status === 401 || exc.status === 403)) {
          setError(errorMessage(exc));
          return;
        }
        if (retryablePollFailure(exc)) {
          // A poll failure is not a job failure.  Keep the last known job and
          // keep polling; only explicit job state ends the task.
          setPollWarning(ASR_JOB_POLL_WARNING);
        } else {
          setError(errorMessage(exc));
        }
      } finally {
        if (pollAbortRef.current === controller) pollAbortRef.current = null;
        inFlightRef.current = false;
      }
    },
    [current, deliver, setCurrentJob],
  );

  const refresh = useCallback(async () => {
    const generation = generationRef.current;
    const controller = new AbortController();
    pollAbortRef.current?.abort();
    pollAbortRef.current = controller;
    try {
      const rows = await listAsrJobs(requestRef.current, subjectId, 20, controller.signal);
      if (!current(generation)) return;
      setJobs(rows);
      const active = rows.find(isActiveJob);
      const latest = active ?? rows[0] ?? null;
      if (latest) {
        setCurrentJob(latest);
        setNotice(active ? ASR_JOB_RECOVERED : jobStatusCopy(latest));
        if (latest.status === "failed") setError(latest.error?.message ?? "转写失败，请重试。");
      }
    } catch (exc) {
      if (controller.signal.aborted || !current(generation)) return;
      if (retryablePollFailure(exc)) setPollWarning(ASR_JOB_POLL_WARNING);
      else setError(errorMessage(exc));
    } finally {
      if (pollAbortRef.current === controller) pollAbortRef.current = null;
    }
  }, [current, setCurrentJob, subjectId]);

  const reset = useCallback(() => {
    generationRef.current += 1;
    pollAbortRef.current?.abort();
    pollAbortRef.current = null;
    inFlightRef.current = false;
    jobRef.current = null;
    deliveredRef.current = null;
    setJob(null);
    setJobs([]);
    setUploading(false);
    setBusy(false);
    setResultLoading(false);
    setError("");
    setNotice("");
    setPollWarning("");
    setResultConsumed(false);
  }, []);

  useEffect(() => {
    reset();
    void refresh();
    return () => {
      generationRef.current += 1;
      pollAbortRef.current?.abort();
    };
    // `refresh` is intentionally keyed by subject; resetting state when the
    // subject changes is the safety boundary against late cross-subject data.
  }, [subjectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const jobId = job?.job_id;
  const jobStatus = job?.status;
  const jobRevision = job?.revision;

  useEffect(() => {
    if (!jobId || !jobStatus || !["queued", "running", "cancelling"].includes(jobStatus)) return;
    const generation = generationRef.current;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (cancelled || !current(generation)) return;
      await poll(generation);
      if (cancelled || !current(generation)) return;
      if (jobRef.current && isActiveJob(jobRef.current)) {
        timer = setTimeout(tick, 1200);
      }
    };
    timer = setTimeout(tick, 700);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      pollAbortRef.current?.abort();
    };
  }, [jobId, jobStatus, jobRevision, poll, current]);

  const start = useCallback(
    async (files: File[], requestId?: string) => {
      if (files.length === 0 || uploading || busy || isActiveJob(jobRef.current)) return false;
      generationRef.current += 1;
      const generation = generationRef.current;
      pollAbortRef.current?.abort();
      setUploading(true);
      setResultLoading(false);
      setError("");
      setPollWarning("");
      setResultConsumed(false);
      setNotice("正在上传录音…");
      try {
        const next = await createAsrJob({
          request: requestRef.current,
          subjectId,
          files,
          requestId,
        });
        if (!current(generation)) return false;
        setCurrentJob(next);
        deliveredRef.current = null;
        setNotice(ASR_JOB_ACCEPTED);
        if (next.status === "completed") {
          await deliver(next, generation);
        }
        return true;
      } catch (exc) {
        if (!current(generation)) return false;
        setError(errorMessage(exc));
        setNotice("");
        return false;
      } finally {
        if (current(generation)) setUploading(false);
      }
    },
    [busy, current, deliver, setCurrentJob, subjectId, uploading],
  );

  const cancel = useCallback(async () => {
    const target = jobRef.current;
    if (!target || busy) return;
    const generation = generationRef.current;
    setBusy(true);
    setError("");
    try {
      const next = await cancelAsrJob(requestRef.current, target.subject_id, target.job_id);
      if (!current(generation)) return;
      setCurrentJob(next);
      setNotice(jobStatusCopy(next));
    } catch (exc) {
      if (current(generation)) setError(errorMessage(exc));
    } finally {
      if (current(generation)) setBusy(false);
    }
  }, [busy, current, setCurrentJob]);

  const retry = useCallback(async () => {
    const target = jobRef.current;
    if (!target || busy) return;
    const generation = generationRef.current;
    setBusy(true);
    setError("");
    setResultConsumed(false);
    try {
      const next = await retryAsrJob(requestRef.current, target.subject_id, target.job_id);
      if (!current(generation)) return;
      setCurrentJob(next);
      setNotice(ASR_JOB_ACCEPTED);
    } catch (exc) {
      if (current(generation)) setError(errorMessage(exc));
    } finally {
      if (current(generation)) setBusy(false);
    }
  }, [busy, current, setCurrentJob]);

  const loadResult = useCallback(async () => {
    const target = jobRef.current;
    if (!target || target.status !== "completed" || resultLoading) return;
    await deliver(target, generationRef.current, true);
  }, [deliver, resultLoading]);

  return {
    job,
    jobs,
    uploading,
    busy,
    resultLoading,
    error,
    notice,
    pollWarning,
    resultConsumed,
    start,
    cancel,
    retry,
    loadResult,
    refresh,
    reset,
  };
}

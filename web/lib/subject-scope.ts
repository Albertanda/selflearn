/**
 * Subject scope of a chat session (C08 three-state semantics), as pure
 * functions.
 *
 * The composer's SubjectSelector, the session reducer and the WS payload
 * builder all need the same answers, and they must agree — a "clear" that one
 * layer treats as "no value" while another treats as "keep the old one" is
 * exactly how a turn silently ends up scoped to the wrong subject. So the rules
 * live here, once:
 *
 * * **omitted** keeps what the session has,
 * * **explicit null / ""** clears it,
 * * **a non-empty string** sets it.
 *
 * Two things this module is careful about:
 *
 * * `null` is a *value* ("the learner chose 无科目"), not "absent". Helpers that
 *   produce the wire request therefore preserve key presence and never use a
 *   truthiness check.
 * * a session's scope is not known until its stored preferences have been
 *   applied (`hydrated`). Until then nothing may be sent, because the choice
 *   between "keep" and "clear" cannot be made yet.
 */

export type SubjectScope = string | null;

export interface SubjectSessionScope {
  /** The session's current choice; `null` means 无科目 (no subject). */
  subjectId: SubjectScope;
  /**
   * Whether this session's stored preferences have been applied yet. `false`
   * means "we do not know this session's subject" — sending is blocked.
   *
   * Named to match the session entry it is stored on, so a session *is* a
   * scope and no adapter (and no chance of a silent mismatch) sits between them.
   */
  subjectHydrated: boolean;
}

export interface SnapshotScope {
  /** Whether the snapshot recorded a scope at all. */
  hasScope: boolean;
  /** The recorded value (`null` = the turn explicitly had no subject). */
  value: SubjectScope;
}

/** A brand-new session: nothing to restore, so it is usable immediately. */
export function newSessionScope(): SubjectSessionScope {
  return { subjectId: null, subjectHydrated: true };
}

/**
 * A session whose preferences are being fetched. The scope is reset to 无科目
 * *and* marked unhydrated: the previous scope must not survive a switch, and
 * nothing may be sent until the stored one arrives.
 */
export function pendingSessionScope(): SubjectSessionScope {
  return { subjectId: null, subjectHydrated: false };
}

/** Normalize one raw value; `null`, `""` and whitespace all mean 无科目. */
export function normalizeSubject(value: unknown): SubjectScope {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

/** The session scope implied by a session's stored preferences. */
export function scopedFromPreferences(preferences: unknown): SubjectSessionScope {
  const record =
    preferences && typeof preferences === "object"
      ? (preferences as Record<string, unknown>)
      : {};
  // A missing key means "no subject stored" — which for a session is the same
  // observable value as an explicit clear: 无科目. It is *not* "keep whatever
  // this tab had", because the session is the authority.
  return {
    subjectId: normalizeSubject(record.subject_id),
    subjectHydrated: true,
  };
}

/** Apply the learner's explicit choice to a hydrated scope. */
export function selectSubject(
  scope: SubjectSessionScope,
  value: SubjectScope,
): SubjectSessionScope {
  return {
    subjectId: normalizeSubject(value),
    subjectHydrated: scope.subjectHydrated,
  };
}

/** May this session send a turn right now? */
export function subjectSendable(scope: SubjectSessionScope | undefined): boolean {
  return Boolean(scope?.subjectHydrated);
}

/**
 * The `subject_id` to put on the wire. Always returns a value — including
 * `null` — because the key is what tells the backend "clear it"; the caller
 * must keep the key present.
 */
export function subjectForRequest(scope: SubjectSessionScope): string | null {
  return normalizeSubject(scope.subjectId);
}

/**
 * Read the scope recorded on a request snapshot.
 *
 * Two real shapes carry it, and both must be understood or a replay silently
 * loses its scope:
 *
 * * the **server** snapshot (what ``request_snapshot`` stores) puts it at the
 *   top level as ``subject_id``;
 * * the **optimistic local** snapshot the composer builds for a turn still in
 *   flight keeps it inside the capability ``config`` (that is where
 *   ``mergeSubjectIntoConfig`` writes it).
 *
 * The top level wins when both exist — it is the server's own record.
 */
export function readSnapshotScope(snapshot: unknown): SnapshotScope {
  const record =
    snapshot && typeof snapshot === "object"
      ? (snapshot as Record<string, unknown>)
      : {};
  for (const key of ["subject_id", "subjectId"] as const) {
    if (key in record) {
      return { hasScope: true, value: normalizeSubject(record[key]) };
    }
  }
  return subjectFromConfig(record.config);
}

/**
 * The `subject_id` a retry / edit / replay must send.
 *
 * The original turn is the authority: an explicit value (including `null`) is
 * replayed as-is, and a legacy snapshot that never recorded a scope replays as
 * 无科目 — inheriting the *current* preference would rewrite history (the
 * backend applies the same rule, so both ends agree).
 */
export function subjectForReplay(snapshot: unknown): string | null {
  const recorded = readSnapshotScope(snapshot);
  return recorded.hasScope ? recorded.value : null;
}

/**
 * Merge the subject into an already-built capability config.
 *
 * Capability fields (quiz / visualize / research …) are built first and stay
 * untouched; `subject_id` is written last and **always present**, so clearing it
 * produces an explicit `null` instead of a dropped key. A `null`/`undefined`
 * config becomes a fresh object for the same reason.
 */
export function mergeSubjectIntoConfig(
  config: Record<string, unknown> | null | undefined,
  value: SubjectScope,
): Record<string, unknown> {
  return { ...(config ?? {}), subject_id: normalizeSubject(value) };
}

/**
 * The subject carried by a config object, when it carries one at all.
 * (Kept for readers that must not confuse "absent" with "cleared".)
 */
export function subjectFromConfig(config: unknown): SnapshotScope {
  const record =
    config && typeof config === "object"
      ? (config as Record<string, unknown>)
      : {};
  if ("subject_id" in record) {
    return { hasScope: true, value: normalizeSubject(record.subject_id) };
  }
  return { hasScope: false, value: null };
}

/**
 * The `subject_id` to send for one turn, given the session scope and an
 * optional replayed snapshot. One decision point, used by every send path.
 */
export function resolveSendSubject(
  scope: SubjectSessionScope | undefined,
  snapshot?: unknown,
): string | null {
  if (snapshot !== undefined && snapshot !== null) return subjectForReplay(snapshot);
  return subjectForRequest(scope ?? newSessionScope());
}

/**
 * Apply one scope event to a session's scope.
 *
 * This *is* the reducer's subject logic (``MARK_SESSION_LOADING`` /
 * ``LOAD_SESSION`` / ``SET_SUBJECT_ID`` call it), so the rules cannot drift
 * between the state store and the tests:
 *
 * * ``loading`` — entering a session: forget the previous scope, close the gate.
 * * ``load`` — the session's stored preferences are the authority; the value
 *   they imply (including 无科目) replaces whatever this tab held.
 * * ``select`` — the learner's explicit choice, applied without reopening a
 *   closed gate.
 */
export type SessionScopeEvent =
  | { type: "loading" }
  | { type: "load"; preferences: unknown }
  | { type: "select"; value: SubjectScope };

export function applySessionScope(
  scope: SubjectSessionScope,
  event: SessionScopeEvent,
): SubjectSessionScope {
  switch (event.type) {
    case "loading":
      return pendingSessionScope();
    case "load":
      return scopedFromPreferences(event.preferences);
    case "select":
      return selectSubject(scope, event.value);
  }
}

/**
 * Background refresh: fill in a scope that is not known yet, never overwrite a
 * known one.
 *
 * A revalidate runs on a session that is already on screen, where the learner
 * may have just picked a subject in the composer and not sent it yet. Replacing
 * that choice with the (older) stored value would silently change the scope of
 * the next turn. A superseded initial load is the other case: its entry is still
 * unhydrated, and filling it in is what lets the send gate ever open again.
 */
export function revalidatedScope(
  scope: SubjectSessionScope,
  preferences: unknown,
): SubjectSessionScope {
  return scope.subjectHydrated
    ? scope
    : applySessionScope(scope, { type: "load", preferences });
}

/**
 * One "this attached library is not usable this turn" notice.
 *
 * The server owns the text (the fixed C02 projection) and the identity; the
 * client only bounds and validates it before showing it.
 */
export interface SubjectKbWarning {
  kbRef: string;
  status: string;
  code: string;
  message: string;
}

/** Upper bound on how many notices the UI holds/renders for one turn. */
export const MAX_SUBJECT_KB_WARNINGS = 20;
const MAX_WARNING_FIELD = 512;

function boundedText(value: unknown): string {
  if (typeof value !== "string") return "";
  // eslint-disable-next-line no-control-regex
  const cleaned = value.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  return cleaned.length > MAX_WARNING_FIELD ? cleaned.slice(0, MAX_WARNING_FIELD) : cleaned;
}

/**
 * Validate the ``subject_kb_warnings`` payload from a DONE event (or a replayed
 * one) into the shape the UI renders.
 *
 * Anything without a usable ``kb_ref`` is dropped, counts are bounded, and only
 * the four known fields survive — an event can never smuggle extra server
 * diagnostics into the banner.
 */
export function normalizeSubjectKbWarnings(value: unknown): SubjectKbWarning[] {
  if (!Array.isArray(value)) return [];
  const out: SubjectKbWarning[] = [];
  for (const item of value) {
    if (out.length >= MAX_SUBJECT_KB_WARNINGS) break;
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const kbRef = boundedText(record.kb_ref ?? record.kbRef);
    if (!kbRef) continue;
    out.push({
      kbRef,
      status: boundedText(record.status),
      code: boundedText(record.code),
      message: boundedText(record.message),
    });
  }
  return out;
}

/**
 * Apply one turn's warnings to a session entry.
 *
 * ``warnings`` is the payload of the turn that just finished: a new turn always
 * replaces the previous list (an empty/absent payload clears it), because a
 * stale notice about a library that is ready again is worse than no notice.
 * The state lives on the *session*, so switching conversations cannot show one
 * session's degradation on another.
 */
export function applySubjectWarnings<T extends { subjectKbWarnings?: SubjectKbWarning[] }>(
  entry: T,
  warnings: unknown,
): T {
  return { ...entry, subjectKbWarnings: normalizeSubjectKbWarnings(warnings) };
}

/** The notices the UI may render for the session currently on screen. */
export function visibleSubjectWarnings(entry: unknown): SubjectKbWarning[] {
  const record =
    entry && typeof entry === "object" ? (entry as Record<string, unknown>) : {};
  return normalizeSubjectKbWarnings(record.subjectKbWarnings);
}

"""Partner visibility guards for non-admin users.

Partners are admin-managed, process-wide resources: the whole
``/api/v1/partners`` CRUD router is admin-gated, and a partner runs in its own
isolated workspace scope (``data/partners/{id}/``), never the caller's. A
non-admin can't create or manage partners, but an admin can *assign* specific
partners to specific users through the grant system — the same mechanism that
shares knowledge bases and skills.

An assigned user may then see the partner, connect it as a subagent, and
consult it in chat; the consult still drives the partner in its own scope, so
the user only ever exchanges messages with it — exactly as when an admin
consults it. This module is the read-side counterpart of ``skill_access``.
"""

from __future__ import annotations

from fastapi import HTTPException

from .context import get_current_user
from .grants import load_grant


def assigned_partner_ids(user_id: str | None = None) -> set[str]:
    """The partner ids an admin has assigned to the user (empty for admins)."""
    user = get_current_user()
    uid = user_id or user.id
    return {
        str(item.get("partner_id") or item.get("id") or "").strip()
        for item in load_grant(uid).get("partners", []) or []
        if str(item.get("partner_id") or item.get("id") or "").strip()
    }


def assert_partner_allowed(partner_id: str, user_id: str | None = None) -> None:
    """Raise 403 when a non-admin tries to use a partner not assigned to them.

    Admins may use any partner; this is a no-op for them (and for single-user
    deployments, where the current user resolves to the local admin).
    """
    user = get_current_user()
    if user.is_admin:
        return
    if str(partner_id or "").strip() not in assigned_partner_ids(user_id or user.id):
        raise HTTPException(status_code=403, detail="Partner is not assigned to you")


# NOTE: upstream also exposed ``visible_partner_cards()`` here (plus the
# ``_CARD_FIELDS`` / ``_project_card`` helpers it needed). Partners were removed
# by the M0 fork trim along with ``deeptutor.services.partners``, so the function
# could only ever raise ``ModuleNotFoundError`` — and it had no callers. The
# grant helpers above stay: they read the grant store and are still used by the
# memory snapshot adapters.

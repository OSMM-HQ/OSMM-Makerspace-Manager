"""Readable requester display labels for STAFF-facing surfaces.

Self-checkout / public shadow users carry the privacy hash username
``checkin_<sha256>`` (see ``workflow_utils.requester_username``). Showing that raw
hash in reports/queues is useless to staff. This module resolves a human-readable
label — the Check-In email/phone (``external_checkin_user_id`` / the request's
contact fields) — skipping the internal hash, with a generic ``"Member"`` fallback.

This is a PII display: the returned label can be a check-in email/phone. It is only
appropriate on staff/superadmin surfaces that are RBAC-action-gated and tenant-scoped
(the same data the operations ledger already shows staff). Public surfaces must NOT
use this — they use ``inventory.public_stats.public_display_name`` ("Member").
"""


def clean_label(value):
    return str(value or "").strip()


def looks_like_email(value):
    return "@" in value


def is_internal_checkin_username(value):
    # Mirrors the operations-ledger guard: a ``checkin_<sha256>`` shadow username
    # (the local-part before any ``@``) is the internal privacy hash, never a name.
    local_part = value.split("@", 1)[0]
    return local_part.startswith("checkin_") and len(local_part) > 32


def requester_label(request, *, fallback="Member", allow_internal_fallback=False):
    """Readable label for a HardwareRequest/PrintRequest-like row.

    Prefers the captured requester name, then a real email (contact email → account
    email → username → external id), then any non-hash identifier (contact phone →
    username → external id → account username). ``allow_internal_fallback=True``
    reproduces the ledger's last-resort behaviour of returning the raw value (even
    the hash) before the fallback.
    """
    requester = getattr(request, "requester", None)

    name = clean_label(getattr(request, "requester_name", ""))
    if name:
        return name

    email_candidates = [
        getattr(request, "requester_contact_email", ""),
        getattr(requester, "email", ""),
        getattr(request, "requester_username", ""),
        getattr(requester, "external_checkin_user_id", ""),
    ]
    for value in email_candidates:
        label = clean_label(value)
        if looks_like_email(label) and not is_internal_checkin_username(label):
            return label

    candidates = [
        getattr(request, "requester_contact_phone", ""),
        getattr(request, "requester_username", ""),
        getattr(requester, "external_checkin_user_id", ""),
        getattr(requester, "username", ""),
    ]
    for value in candidates:
        label = clean_label(value)
        if label and not is_internal_checkin_username(label):
            return label

    if allow_internal_fallback:
        for value in candidates:
            label = clean_label(value)
            if label:
                return label
    return fallback


def label_from_candidates(*values, fallback="Member"):
    """First non-empty, non-hash candidate (in priority order), else ``fallback``.

    For surfaces whose field names don't match :func:`requester_label` (e.g. a
    PrintRequest, which carries ``requester_name``/``contact_email``/``contact_phone``).
    """
    for value in values:
        label = clean_label(value)
        if label and not is_internal_checkin_username(label):
            return label
    return fallback


def requester_label_for_user(*, username="", external_checkin_user_id="", fallback="Member"):
    """Readable label when only the requester User's fields are available.

    Used by per-requester aggregates (top borrowers / top print requesters) where the
    grouping carries ``requester__username`` + ``requester__external_checkin_user_id``
    but not the per-request contact fields. Prefers the external Check-In id (the
    email/phone) over the possibly-hashed username.
    """
    for value in (external_checkin_user_id, username):
        label = clean_label(value)
        if label and not is_internal_checkin_username(label):
            return label
    return fallback

"""What a credential's `hmac_signature` attests to, and how it is checked.

Until now that column was written in two places and read in none. Both writers
signed `hmac_sign(public_id)` — the identifier and nothing else — so even a
reader would have learned only that this ID was once minted by us. Change the
recipient name, the title or the issue date in the database and the signature
still matched, because the signature had never seen those fields. A column
named for integrity that provides none is worse than no column: it reads, in
review and to a customer, as a guarantee.

This module is the join that was missing. `sign_credential` and
`credential_signature_status` are inverses of each other, one is called on
every write path and the other on every public read path, and neither works
without the other.

## What is signed

Everything the credential asserts about the world at the moment it was issued:
the ID, the issuing org, who it names, what it says, when, and the metadata
that renders onto the document.

## What is deliberately NOT signed, and why

`status`, `revoked_at`, `claimed_by_user_id`, `claimed_at` and every
`delivery_*` column. These change by design over a credential's life — issue,
claim, revoke, retry an email — and an immutable signature cannot cover a
mutable field without invalidating itself the first time the product works
normally. The signature answers "is this what was issued?", not "is this still
valid?"; `status` answers the second, and the read paths already gate on it.

`template_id` and `pdf_url` are excluded for a different reason: they select
how the credential is drawn, not what it claims.

## Versioning

`signature_version` records which rule produced the signature, rather than the
verifier guessing from the shape of the data:

- `2` — canonical, this module. Verified on every public read; a mismatch is
  refused.
- `NULL` — predates canonical signing. **Unverifiable, and reported as such.**
  We do not re-sign these: the only record of what they originally said is the
  row itself, so a backfill would sign whatever the row says today and call
  that evidence. That is the mistake `delivery_status = "unknown"` exists to
  avoid, and it is the same mistake here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from api.core.crypto import hmac_sign, hmac_verify

#: Bump only alongside a new branch in `canonical_payload`. Rows signed under
#: an older version keep verifying under the rule that made them.
CURRENT_VERSION = 2

VALID = "valid"
INVALID = "invalid"
UNVERIFIED = "unverified"


def _iso(value: datetime | None) -> str:
    """A timestamp that survives a database round-trip byte-identically.

    SQLite hands back naive datetimes for a TIMESTAMP(timezone=True) column
    while Postgres hands back aware ones, so signing `dt.isoformat()` directly
    would produce a signature that verifies on one backend and fails on the
    other — a bug that would pass every test and refuse real credentials in
    production. Naive means UTC here, because that is what every writer stores.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def canonical_payload(
    *,
    public_id: str,
    org_id: Any,
    recipient_name: str,
    recipient_email: str,
    title: str,
    issued_at: datetime | None,
    metadata: dict | None,
) -> str:
    """Serialize the signed fields unambiguously.

    JSON with sorted keys rather than a delimiter-joined string, because the
    values are attacker-supplied: with `name|title` a recipient named
    `Alice|Advanced` and a title of `Widgetry` would sign identically to
    `Alice` / `Advanced|Widgetry`, and one signature would authenticate two
    different credentials. JSON escaping removes that whole class.
    """
    body = {
        "public_id": public_id or "",
        "org_id": str(org_id) if org_id is not None else "",
        "recipient_name": recipient_name or "",
        "recipient_email": recipient_email or "",
        "title": title or "",
        "issued_at": _iso(issued_at),
        "metadata": metadata or {},
    }
    return "certforge.credential.v2:" + json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def credential_payload(credential) -> str:
    """The canonical payload for a Credential row, at its current values."""
    return canonical_payload(
        public_id=credential.public_id,
        org_id=credential.org_id,
        recipient_name=credential.recipient_name,
        recipient_email=credential.recipient_email,
        title=credential.title,
        issued_at=credential.issued_at,
        metadata=credential.metadata_,
    )


def sign_credential(credential) -> str:
    """Sign a credential in place. Call this after its fields are final.

    Bulk issuance signs twice on purpose: once when the pending row is staged,
    and again in the worker, which rewrites `issued_at` when the render
    succeeds. Signing only at staging would leave every bulk credential
    permanently invalid — the signature would attest to a timestamp the row no
    longer carries.
    """
    credential.hmac_signature = hmac_sign(credential_payload(credential))
    credential.signature_version = CURRENT_VERSION
    return credential.hmac_signature


def credential_signature_status(credential) -> str:
    """One of VALID, INVALID, UNVERIFIED.

    UNVERIFIED is not a pass. It means this row predates canonical signing and
    nothing can be said about its integrity either way — callers that gate on
    the answer must decide what to do with it, and the decision is different
    for a printed certificate than for a new API response.
    """
    version = getattr(credential, "signature_version", None)
    if version is None:
        return UNVERIFIED
    if version != CURRENT_VERSION:
        # A version this build does not know how to check. Fail closed: an
        # unknown rule is not a passing one.
        return INVALID
    return VALID if hmac_verify(credential_payload(credential), credential.hmac_signature or "") else INVALID


def signature_state(credential) -> dict:
    """The signature as an API caller sees it."""
    status = credential_signature_status(credential)
    return {
        "status": status,
        "scheme": "credential_row",
        "version": getattr(credential, "signature_version", None),
        "covers": [
            "public_id",
            "org_id",
            "recipient_name",
            "recipient_email",
            "title",
            "issued_at",
            "metadata",
        ],
    }

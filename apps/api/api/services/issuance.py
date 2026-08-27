"""Issuing a credential — the one implementation.

Route handlers are adapters: they translate a request into an IssueRequest, call
`issue_credential`, and translate the result back. Nothing here knows about
FastAPI, Clerk, or CSV, so the same function can serve the v1 API, the bulk CSV
path, and eventually the frozen legacy endpoint without any of them drifting
apart. `index.py` and `api/core/` already show what happens when that discipline
is missing: two implementations of the same thing, only one of which gets fixed.

Quota is enforced here rather than in a route, because it is a property of
issuing, not of one entrypoint. Until now `UsageLedger` was read in studio.py
and written nowhere, so `used` was always 0 and `monthly_quota` never bound.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from api.core.crypto import generate_credential_id, hmac_sign
from api.models import get_db
from api.models.credential import Credential
from api.models.organization import Organization
from api.models.usage import UsageLedger
from api.services.delivery import (
    deliver_credential_email,
    delivery_state,
    mark_not_requested,
)

logger = logging.getLogger(__name__)

UNLIMITED = -1


class IssuanceError(Exception):
    """Something the caller can fix. `code` maps to an HTTP status."""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


class QuotaExceeded(IssuanceError):
    def __init__(self, limit: int, used: int, requested: int):
        super().__init__(
            f"Monthly quota exceeded: {used}/{limit} used, {requested} requested",
            code=402,
        )
        self.limit = limit
        self.used = used
        self.requested = requested


@dataclass
class IssueRequest:
    """What a caller must supply to issue one credential."""

    recipient_name: str
    title: str
    recipient_email: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    template_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    #: Opt-in. Defaults off so that every caller written against the version of
    #: this API that could not send email keeps behaving exactly as it did.
    send_email: bool = False


@dataclass
class IssuedCredential:
    """What issuing produced. Plain data — no ORM objects escape the session."""

    public_id: str
    org_slug: str
    recipient_name: str
    recipient_email: str
    title: str
    status: str
    issued_at: datetime
    metadata: dict[str, Any]
    verify_url: str
    badge_url: str
    #: What happened to the email, always — including "we did not try", which is
    #: a recorded outcome here rather than an absence.
    delivery: dict[str, Any]
    quota_limit: int
    quota_remaining: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.public_id,
            "org": self.org_slug,
            "recipient_name": self.recipient_name,
            "recipient_email": self.recipient_email,
            "title": self.title,
            "status": self.status,
            "issued_at": self.issued_at.isoformat(),
            "metadata": self.metadata,
            "verify_url": self.verify_url,
            "badge_url": self.badge_url,
            "delivery": self.delivery,
        }


def _public_urls(public_id: str) -> tuple[str, str]:
    """Human-facing verify page and machine-facing badge document."""
    from api.core.config import CERTFORGE_API_URL, CERTFORGE_WEB_URL

    return (
        f"{CERTFORGE_WEB_URL}/verify/{public_id}",
        f"{CERTFORGE_API_URL}/credentials/{public_id}/badge.json",
    )


def quota_state(session, org: Organization) -> tuple[int, int]:
    """Return (limit, used) for this org in the current period."""
    period = UsageLedger.current_period()
    ledger = session.query(UsageLedger).filter_by(org_id=org.id, period=period).first()
    return org.monthly_quota, (ledger.credentials_issued if ledger else 0)


def _consume_quota(session, org: Organization, count: int) -> tuple[int, int]:
    """Reserve `count` issuances, or raise QuotaExceeded. Returns (limit, remaining)."""
    limit, used = quota_state(session, org)

    if limit != UNLIMITED and used + count > limit:
        raise QuotaExceeded(limit=limit, used=used, requested=count)

    period = UsageLedger.current_period()
    ledger = session.query(UsageLedger).filter_by(org_id=org.id, period=period).first()
    if ledger is None:
        ledger = UsageLedger(org_id=org.id, period=period, credentials_issued=0)
        session.add(ledger)
    ledger.credentials_issued = used + count

    remaining = UNLIMITED if limit == UNLIMITED else max(0, limit - ledger.credentials_issued)
    return limit, remaining


def _unique_public_id(session) -> str:
    """A credential id nothing else holds.

    generate_credential_id has roughly a 1-in-20-billion collision chance per
    year, which is small but not zero, and the column is unique — so a blind
    insert would surface as a 500 rather than a retry.
    """
    for _ in range(5):
        candidate = generate_credential_id()
        if session.query(Credential).filter_by(public_id=candidate).first() is None:
            return candidate
    raise IssuanceError("Could not allocate a credential id", code=500)


def issue_credential(
    org_slug: str,
    request: IssueRequest,
    *,
    is_test: bool = False,
) -> IssuedCredential:
    """Issue one credential for `org_slug`.

    `is_test` marks issuance from a cf_test_ key: the row is written exactly as
    a live one, but nothing is emailed and nothing is billed, so the API can be
    exercised end to end without side effects reaching a real recipient.
    """
    name = (request.recipient_name or "").strip()
    title = (request.title or "").strip()
    if not name:
        raise IssuanceError("recipient_name is required")
    if not title:
        raise IssuanceError("title is required")

    with get_db() as session:
        org = session.query(Organization).filter_by(slug=org_slug).first()
        if org is None:
            raise IssuanceError("Organization not found", code=404)

        limit, remaining = _consume_quota(session, org, 1)

        public_id = _unique_public_id(session)
        metadata = dict(request.metadata or {})
        if is_test:
            # Recorded on the row itself so a test credential is identifiable
            # long after the key that made it has been revoked.
            metadata["_test"] = True

        credential = Credential(
            public_id=public_id,
            org_id=org.id,
            batch_id=request.batch_id,
            template_id=request.template_id,
            recipient_name=name,
            recipient_email=(request.recipient_email or "").strip(),
            title=title,
            metadata_=metadata,
            hmac_signature=hmac_sign(public_id),
            status="issued",
            issued_at=datetime.now(timezone.utc),
        )
        session.add(credential)
        session.flush()

        verify_url, badge_url = _public_urls(public_id)

        # Delivery goes through services/delivery.py — the same function bulk
        # issuance calls. The TODO this closes asked for the state shape to be
        # settled before this path grew its own sender, precisely so there
        # would not be two email bodies and two ways of recording an outcome.
        #
        # Every branch writes a terminal state. "Nobody asked us to send" and
        # "we sent and it was rejected" must never again be the same row.
        if is_test:
            mark_not_requested(
                credential,
                "Test credential; a cf_test_ key never sends email.",
            )
        elif not request.send_email:
            mark_not_requested(
                credential,
                "Delivery not requested (send_email was not set).",
            )
        else:
            deliver_credential_email(credential, verify_url=verify_url)

        delivery = delivery_state(credential)

        result = IssuedCredential(
            public_id=public_id,
            org_slug=org.slug,
            recipient_name=credential.recipient_name,
            recipient_email=credential.recipient_email,
            title=credential.title,
            status=credential.status,
            issued_at=credential.issued_at,
            metadata=metadata,
            verify_url=verify_url,
            badge_url=badge_url,
            delivery=delivery,
            quota_limit=limit,
            quota_remaining=remaining,
        )

    if is_test:
        logger.info("Issued TEST credential %s for %s (no email, not billed)", public_id, org_slug)
    else:
        logger.info("Issued credential %s for %s", public_id, org_slug)

    return result


def revoke_credential(org_slug: str, public_id: str) -> dict[str, Any]:
    """Revoke a credential. Revocation is terminal and does not restore quota.

    A revoked credential keeps its row: verification has to be able to answer
    "this existed and was revoked", which is a different and more useful answer
    than "no such credential".
    """
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=org_slug).first()
        if org is None:
            raise IssuanceError("Organization not found", code=404)

        credential = (
            session.query(Credential)
            .filter_by(public_id=public_id, org_id=org.id)
            .first()
        )
        if credential is None:
            raise IssuanceError("Credential not found", code=404)
        if credential.status == "revoked":
            return {"id": public_id, "status": "revoked", "already_revoked": True}

        credential.status = "revoked"
        credential.revoked_at = datetime.now(timezone.utc)
        return {
            "id": public_id,
            "status": "revoked",
            "already_revoked": False,
            "revoked_at": credential.revoked_at.isoformat(),
        }

"""The credentials resource — what an API key holder actually calls.

Until now the only way to create a CertForge credential was a multipart CSV
upload at POST /orgs/{slug}/credentials/bulk. A CSV-upload-only issuance path is
a dashboard feature wearing an API costume; this is the endpoint the SDK, a
curl, and the dashboard all use.

Every handler here is thin on purpose: validate, call api.services.issuance,
shape the response. The rules — quota, id allocation, signing — live in the
service so the bulk path and the eventual legacy adapter cannot drift from it.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.core.envelope import ApiResponse
from api.core.principal import Principal, require_org_access, resolve_principal
from api.core.rate_limit import rate_limit
from api.models import get_db
from api.models.credential import Credential
from api.models.organization import Organization
from api.services.delivery import delivery_state
from api.services.issuance import (
    UNLIMITED,
    IssuanceError,
    IssueRequest,
    issue_credential,
    quota_state,
    revoke_credential,
)

router = APIRouter(prefix="/orgs/{slug}/credentials", tags=["Credentials"])


class CredentialCreate(BaseModel):
    recipient_name: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    recipient_email: str = Field("", max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    #: Documented in the B1 plan and never implemented until now. Off by default
    #: so no existing caller starts sending mail it did not ask to send.
    send_email: bool = False
    template_id: Optional[str] = None


def _quota_headers(response: Response, limit: int, remaining: int) -> None:
    """Tell the caller where they stand without making them ask.

    An API-first product should not require a second request to discover it is
    about to be refused.
    """
    response.headers["X-Quota-Limit"] = "unlimited" if limit == UNLIMITED else str(limit)
    response.headers["X-Quota-Remaining"] = (
        "unlimited" if remaining == UNLIMITED else str(remaining)
    )


def _authorise(slug: str, principal: Principal, roles=("owner", "admin", "issuer")):
    """Resolve the org and check the caller may act on it. Returns its UUID."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        org_id = org.id
    require_org_access(principal, org_id, allowed_roles=roles)
    return org_id


@router.post(
    "",
    response_model=ApiResponse[dict],
    status_code=201,
    # Rate limited because this is the most expensive thing the process does —
    # it renders a PDF. Quota bounds the month; this bounds the minute, which
    # nothing did before. Keyed on the calling principal, so one noisy
    # integration cannot spend another org's budget.
    dependencies=[Depends(rate_limit())],
)
def create_credential(
    slug: str,
    payload: CredentialCreate,
    response: Response,
    principal: Principal = Depends(resolve_principal),
    idempotency_key: Optional[str] = Header(
        None,
        alias="Idempotency-Key",
        description=(
            "Repeat this key to retry safely: the original credential is "
            "returned instead of a second one being issued, and no quota is "
            "consumed. Reusing a key with a different body is a 409."
        ),
    ),
):
    """Issue a single credential.

    The header was advertised in the CORS allow-list long before anything read
    it, so a careful client could send it, believe a retry was safe, and get a
    duplicate credential plus a second quota charge.
    """
    _authorise(slug, principal)

    template_id: Optional[uuid.UUID] = None
    if payload.template_id:
        try:
            template_id = uuid.UUID(payload.template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid template_id")

    try:
        issued = issue_credential(
            slug,
            IssueRequest(
                recipient_name=payload.recipient_name,
                title=payload.title,
                recipient_email=payload.recipient_email,
                metadata=payload.metadata,
                send_email=payload.send_email,
                template_id=template_id,
                idempotency_key=idempotency_key,
            ),
            is_test=principal.is_test,
        )
    except IssuanceError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.message)

    _quota_headers(response, issued.quota_limit, issued.quota_remaining)
    return ApiResponse.ok(issued.as_dict())


@router.get("", response_model=ApiResponse[dict])
def list_credentials(
    slug: str,
    response: Response,
    principal: Principal = Depends(resolve_principal),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(
        None, description="public_id of the last item from the previous page."
    ),
    offset: Optional[int] = Query(
        None, ge=0, description="Deprecated. Prefer cursor; see below."
    ),
    status: Optional[str] = Query(None, pattern="^(issued|revoked|pending|claimed)$"),
):
    """List credentials, newest first.

    Two paginations, deliberately. `cursor` is the correct one for an issuance
    log: an offset page silently skips or repeats rows when something is issued
    mid-listing, and a caller cannot detect that it happened. `offset` exists
    because the dashboard already ships against it, and breaking a deployed
    client to tidy an interface is the wrong trade. Cursor wins if both arrive.
    """
    org_id = _authorise(slug, principal)

    with get_db() as session:
        base = session.query(Credential).filter_by(org_id=org_id)
        if status:
            base = base.filter(Credential.status == status)

        total = base.count()
        query = base.order_by(Credential.issued_at.desc(), Credential.public_id.desc())

        if cursor:
            anchor = (
                session.query(Credential)
                .filter_by(public_id=cursor, org_id=org_id)
                .first()
            )
            if anchor is None:
                raise HTTPException(status_code=400, detail="Unknown cursor")
            query = query.filter(Credential.issued_at < anchor.issued_at)
        elif offset:
            query = query.offset(offset)

        rows = query.limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [
            {
                "id": c.public_id,
                "recipient_name": c.recipient_name,
                "recipient_email": c.recipient_email,
                "title": c.title,
                "status": c.status,
                "issued_at": c.issued_at.isoformat(),
                "batch_id": str(c.batch_id) if c.batch_id else None,
                # The status only, not the full delivery object: a list wants to
                # flag which rows need attention, and the detail route carries
                # the error text and attempt count for when one does.
                "delivery_status": c.delivery_status,
            }
            for c in rows
        ]

        org = session.query(Organization).filter_by(id=org_id).first()
        limit_v, used = quota_state(session, org)

    _quota_headers(
        response, limit_v, UNLIMITED if limit_v == UNLIMITED else max(0, limit_v - used)
    )
    return ApiResponse.ok(
        {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset or 0,
            "has_more": has_more,
            "next_cursor": items[-1]["id"] if (items and has_more) else None,
        }
    )


@router.get("/{public_id}", response_model=ApiResponse[dict])
def get_credential(
    slug: str,
    public_id: str,
    principal: Principal = Depends(resolve_principal),
):
    """Fetch one credential belonging to this organization."""
    org_id = _authorise(slug, principal)

    with get_db() as session:
        c = (
            session.query(Credential)
            .filter_by(public_id=public_id, org_id=org_id)
            .first()
        )
        if c is None:
            raise HTTPException(status_code=404, detail="Credential not found")

        from api.services.issuance import _public_urls

        verify_url, badge_url, pdf_url = _public_urls(c.public_id)
        return ApiResponse.ok(
            {
                "id": c.public_id,
                "recipient_name": c.recipient_name,
                "recipient_email": c.recipient_email,
                "title": c.title,
                "status": c.status,
                "metadata": c.metadata_,
                "issued_at": c.issued_at.isoformat(),
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
                "claimed_at": c.claimed_at.isoformat() if c.claimed_at else None,
                "verify_url": verify_url,
                "badge_url": badge_url,
                "pdf_url": pdf_url,
                # So support can answer "did they get the email?" from the API
                # instead of from a Fly log buffer that holds ~100 lines.
                "delivery": delivery_state(c),
            }
        )


@router.post("/{public_id}/revoke", response_model=ApiResponse[dict])
def revoke(
    slug: str,
    public_id: str,
    principal: Principal = Depends(resolve_principal),
):
    """Revoke a credential. Requires more than issuer rights."""
    _authorise(slug, principal, roles=("owner", "admin"))

    try:
        return ApiResponse.ok(revoke_credential(slug, public_id))
    except IssuanceError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.message)

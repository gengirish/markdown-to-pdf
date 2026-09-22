"""Operator endpoints for CertForge organizations.

Checkout is still mocked (`create_checkout_session` in routes/billing.py), so
an org that hits a tier gate has no self-serve way up — the 402 body and the
pricing page both say it "can only be moved by hand". Before this module,
"by hand" meant SQL against production, and SQL has to remember two columns:
the gates read `organizations.tier`, the credential meter reads
`organizations.monthly_quota`. Update one and not the other and the org is
paid by one lookup and free by another.

This is that door, with the two columns written together from BILLING_TIERS.
It is authenticated by `X-Admin-Key`, not a Clerk session: an operator is not
a member of the org they are moving, and org roles (`owner`, `admin`) are
exactly the people who must not be able to grant themselves a plan.
"""

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.core import config
from api.core.config import BILLING_TIERS, get_tier_quota
from api.core.envelope import ApiException, ApiResponse
from api.models import get_db
from api.models.organization import Organization
from api.services.issuance import UNLIMITED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_key(request: Request) -> None:
    """Fail closed. An unset ADMIN_KEY answers 503 rather than accepting an
    empty header — `compare_digest("", "")` is True, which would make an
    unconfigured production deploy an open door to every paid plan.

    Read through the module rather than imported by name so the value is the
    one config holds at request time.
    """
    expected = config.ADMIN_KEY
    if not expected:
        raise HTTPException(status_code=503, detail="Admin access not configured")
    supplied = request.headers.get("X-Admin-Key", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin key")


class TierChange(BaseModel):
    tier: str
    #: Why the org was moved — a trial, an invoice paid offline, a support
    #: goodwill grant. Logged with the change, since there is no audit table.
    reason: Optional[str] = Field(default=None, max_length=500)


def _wire_quota(value: int) -> Optional[int]:
    return None if value == UNLIMITED else value


def _org_plan(org: Organization) -> dict:
    return {
        "slug": org.slug,
        "tier": org.tier,
        "tier_known": org.tier in BILLING_TIERS,
        "monthly_quota": _wire_quota(org.monthly_quota),
        "razorpay_sub_id": org.razorpay_sub_id,
    }


def _get_org(session, slug: str) -> Organization:
    org = session.query(Organization).filter_by(slug=slug).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get(
    "/orgs/{slug}",
    response_model=ApiResponse[dict],
    dependencies=[Depends(require_admin_key)],
)
def get_org_plan(slug: str):
    """What plan an org is on, as the two columns actually read — including
    a `tier` BILLING_TIERS does not know (`tier_known: false`)."""
    with get_db() as session:
        return ApiResponse.ok(_org_plan(_get_org(session, slug)))


@router.put(
    "/orgs/{slug}/tier",
    response_model=ApiResponse[dict],
    dependencies=[Depends(require_admin_key)],
)
def set_org_tier(slug: str, change: TierChange):
    """Move an org to any tier in BILLING_TIERS, up or down, without payment.

    `monthly_quota` is taken from the tier table, never from the request, so
    the two columns cannot be set out of step. A quota previously hand-edited
    to something else is overwritten — the table is the definition of a plan.

    Nothing already acquired is taken away on a downgrade: the entitlement
    gates run where a capability is acquired, not where it is used, so an
    org's existing artwork, templates and API keys keep working.
    """
    if change.tier not in BILLING_TIERS:
        raise ApiException(
            422,
            f"Unknown tier {change.tier!r}",
            error_type="unknown_tier",
            details={"tiers": list(BILLING_TIERS)},
        )

    with get_db() as session:
        org = _get_org(session, slug)
        previous = _org_plan(org)

        org.tier = change.tier
        org.monthly_quota = get_tier_quota(change.tier)
        session.commit()

        logger.warning(
            "Operator tier change: org=%s %s(quota=%s) -> %s(quota=%s) reason=%r",
            org.slug,
            previous["tier"],
            previous["monthly_quota"],
            org.tier,
            _wire_quota(org.monthly_quota),
            change.reason,
        )

        return ApiResponse.ok({
            **_org_plan(org),
            "previous_tier": previous["tier"],
            "previous_monthly_quota": previous["monthly_quota"],
        })

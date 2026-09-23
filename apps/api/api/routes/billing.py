import hashlib
import hmac
import logging
import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func

from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template
from api.models.usage import UsageLedger
from api.core.envelope import ApiResponse
from api.core.principal import Principal, require_user, require_org_access
from api.core.config import (
    BILLING_TIERS,
    DEFAULT_TIER,
    RAZORPAY_SECRET,
    VISION_IMPORTS_PER_MONTH,
    get_tier_template_limit,
    tier_catalog,
)
from api.services.issuance import UNLIMITED, credential_quota_source, quota_state
from api.services.plans import change_tier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs", tags=["billing"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
#: The plan catalog is public and org-independent, so it does not belong
#: under /orgs/{slug}. The pricing page is served to signed-out visitors.
plans_router = APIRouter(tags=["billing"])


@plans_router.get("/tiers", response_model=ApiResponse[list])
def list_tiers():
    """Every plan CertForge sells, in display order. No auth.

    This is the only source of plan names, prices and limits that reaches
    a browser. apps/web renders /pricing from it rather than keeping a
    second table in TypeScript, because a price maintained in two places
    is a price that will disagree with the quota the API actually grants.

    Deliberately not in `_build_llms_txt` or `_build_sitemap_xml`: those
    describe the legacy product on SITE_URL, and this is CertForge.
    """
    return ApiResponse.ok(tier_catalog())

@router.post("/{slug}/checkout", response_model=ApiResponse[dict])
def create_checkout_session(
    slug: str,
    payload: Dict[str, Any],
    principal: Principal = Depends(require_user)
):
    """Create a Razorpay checkout session for upgrading org tier."""
    # In a real app, integrate with razorpay python SDK
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        tier = payload.get("tier", "pro")
        
        # Mocking a Razorpay session URL for Phase 2 demo
        checkout_url = f"https://rzp.io/i/mock_{org.id}_{tier}"
        
        return ApiResponse.ok({
            "checkout_url": checkout_url,
            "tier": tier
        })

def _meter(used: int, limit: int) -> dict:
    """Shape one counter for the wire. `None` means unlimited, never `-1` —
    the sentinel is an internal detail (`UNLIMITED`); a JSON consumer should
    not have to know it."""
    unlimited = limit == UNLIMITED
    return {
        "used": used,
        "limit": None if unlimited else limit,
        "remaining": None if unlimited else max(0, limit - used),
    }


@router.get("/{slug}/usage", response_model=ApiResponse[dict])
def get_usage(
    slug: str,
    principal: Principal = Depends(require_user),
):
    """This org's quota standing for the current billing period.

    Reads the same ledger `consume_quota()` and the vision-import counter in
    `routes/templates.py` write — never creates or mutates a row, so checking
    usage cannot itself consume any. Written for the CertForge dashboard's
    plan card, which previously had no endpoint to call and said so.
    """
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))

        period = UsageLedger.current_period()
        cred_limit, cred_used = quota_state(session, org)

        ledger = (
            session.query(UsageLedger)
            .filter_by(org_id=org.id, period=period)
            .first()
        )
        vision_used = (ledger.vision_imports or 0) if ledger else 0

        # A stock, not a flow: the live row count, so deleting a template
        # frees the slot. Counted here rather than read off the ledger for the
        # same reason routes/templates.py gates on it — see
        # docs/billing-and-template-quota-plan.md, "a stock, not a flow".
        template_used = (
            session.query(func.count(Template.id)).filter_by(org_id=org.id).scalar() or 0
        )

        return ApiResponse.ok({
            "period": period,
            "tier": org.tier,
            # The tier column is free text and has held values BILLING_TIERS
            # does not know (the Razorpay webhook still writes "pro"). Report
            # the row the limits were actually read from, so a dashboard
            # showing "Community" and a gate enforcing Community's limits can
            # never disagree.
            "tier_name": BILLING_TIERS.get(org.tier, BILLING_TIERS[DEFAULT_TIER])["name"],
            "tier_known": org.tier in BILLING_TIERS,
            # `source` lets the plan card say "custom limit" rather than show
            # 1,000 beside a Community plan the pricing page says allows 50.
            "credentials": {
                **_meter(cred_used, cred_limit),
                "source": credential_quota_source(org),
            },
            "templates": _meter(template_used, get_tier_template_limit(org.tier)),
            "vision_imports": _meter(vision_used, VISION_IMPORTS_PER_MONTH),
        })


@webhooks_router.post("/razorpay", response_model=ApiResponse[dict])
async def razorpay_webhook(request: Request):
    """Handle Razorpay webhooks to update org tiers."""
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Fail closed when unconfigured. This handler grants paid tiers, so an
    # unset secret must reject rather than fall back to a shared default value
    # that anyone could HMAC against.
    # ApiResponse.fail() alone would answer 200 with an error body, which tells
    # Razorpay the hook succeeded. Raise so the rejection is a real HTTP status.
    if not RAZORPAY_SECRET:
        logger.error("Razorpay webhook received but RAZORPAY_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook signing is not configured")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    expected = hmac.new(RAZORPAY_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("Rejected Razorpay webhook with an invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = await request.json()
    event = data.get("event")

    if event == "subscription.activated":
        # Walk the payload defensively — Razorpay sends several event shapes and
        # a KeyError here would 500 on a request we have already authenticated.
        entity = (
            data.get("payload", {})
            .get("subscription", {})
            .get("entity", {})
        )
        # Parsed rather than passed through: the column is a UUID, and a raw
        # string reaches the driver unconverted. No test had ever delivered
        # this event for a real org, so the lookup had never run.
        try:
            org_id = uuid.UUID(str((entity.get("notes") or {}).get("org_id")))
        except ValueError:
            org_id = None
        if org_id:
            with get_db() as session:
                org = session.query(Organization).filter_by(id=org_id).first()
                if org:
                    # "pro" is not a key in BILLING_TIERS, so every lookup —
                    # quota, template limit, the dashboard's plan name — fell
                    # back to Community while the column read paid. Grant a
                    # tier the table knows, and take the quota from the table
                    # rather than a literal that can drift from it.
                    #
                    # Which tier is still a guess: checkout is mocked, so there
                    # is no plan_id to map from. That mapping is P1 of
                    # docs/billing-and-template-quota-plan.md.
                    #
                    # Through change_tier(), never by writing the columns: a
                    # plan change clears an operator's quota override and logs
                    # it, and a retried delivery for the plan the org already
                    # has must change nothing.
                    change_tier(session, org, "starter", actor="razorpay-webhook")
                    org.razorpay_sub_id = entity.get("id")
                    session.commit()
                    
    return ApiResponse.ok({"status": "received"})

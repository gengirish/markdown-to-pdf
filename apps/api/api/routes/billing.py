import logging
import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from api.models import get_db
from api.models.billing_event import BillingEvent
from api.models.organization import Organization
from api.models.template import Template
from api.models.usage import UsageLedger
from api.core.envelope import ApiException, ApiResponse
from api.core.principal import Principal, require_user, require_org_access
from api.core.config import (
    BILLING_TIERS,
    DEFAULT_TIER,
    VISION_IMPORTS_PER_MONTH,
    canonical_tier,
    get_tier,
    get_tier_csv_batch_limit,
    get_tier_template_limit,
    is_known_tier,
    tier_catalog,
)
from api.services import billing
from api.services.entitlements import csv_batches_this_month
from api.services.issuance import UNLIMITED, credential_quota_source, quota_state

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

def _billing_unavailable(exc: Exception) -> ApiException:
    logger.error("Billing is unavailable: %s", exc)
    return ApiException(
        503,
        "Billing is not available right now. Nothing was charged.",
        error_type="billing_unavailable",
    )


def _provider_error() -> ApiException:
    return ApiException(
        502,
        "The payment provider could not start this request. Nothing was charged; try again.",
        error_type="billing_provider_error",
    )


def _owned_org(session, slug: str, principal: Principal) -> Organization:
    org = session.query(Organization).filter_by(slug=slug).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Owner only. Starting a subscription commits the org to paying, and
    # before this check any signed-in user could do it to any org's slug.
    require_org_access(principal, str(org.id), allowed_roles=("owner",))
    return org


@router.post("/{slug}/checkout", response_model=ApiResponse[dict])
def create_checkout_session(
    slug: str,
    payload: Dict[str, Any],
    principal: Principal = Depends(require_user)
):
    """Start a Dodo Payments checkout that subscribes this org to `tier`.

    Returns the hosted checkout URL. The tier does not change here, nor when
    the browser comes back: only the signed webhook moves it, once Dodo says
    the subscription is active.
    """
    with get_db() as session:
        org = _owned_org(session, slug, principal)

        # Resolved first, so a client holding a retired plan name — the
        # pricing page it loaded this morning, a saved link — checks out on
        # the plan that replaced it rather than being told it does not exist.
        tier = canonical_tier(payload.get("tier") or "")
        if tier not in BILLING_TIERS or tier == DEFAULT_TIER:
            raise ApiException(
                400,
                "Choose a paid plan to check out.",
                error_type="invalid_tier",
                details={"tier": payload.get("tier"), "paid_tiers": [
                    key for key, info in BILLING_TIERS.items()
                    if key != DEFAULT_TIER and info["listed"]
                ]},
            )
        if billing.holds_live_subscription(org):
            # A second checkout would create a second subscription, billed in
            # parallel with the first. Changing plan is a different operation.
            raise ApiException(
                409,
                "This organization already has an active subscription. "
                "Change plan from the billing portal instead.",
                error_type="already_subscribed",
                details={"tier": org.tier},
            )

        try:
            started = billing.create_checkout(org, tier, principal.email)
        except billing.BillingUnavailable as exc:
            raise _billing_unavailable(exc)
        except billing.BillingProviderError:
            raise _provider_error()

        return ApiResponse.ok({
            "checkout_url": started["checkout_url"],
            "session_id": started["session_id"],
            "tier": tier,
        })


@router.post("/{slug}/billing/portal", response_model=ApiResponse[dict])
def create_billing_portal_session(
    slug: str,
    principal: Principal = Depends(require_user),
):
    """A link to Dodo's customer portal: card, cancellation, invoices, and
    recovering a subscription whose renewal failed. Links expire after 24
    hours, so one is minted per request."""
    with get_db() as session:
        org = _owned_org(session, slug, principal)
        if not org.dodo_customer_id:
            raise ApiException(
                409,
                "This organization has no billing account yet. Subscribe to a plan first.",
                error_type="no_billing_account",
            )
        try:
            link = billing.create_portal_link(org)
        except billing.BillingUnavailable as exc:
            raise _billing_unavailable(exc)
        except billing.BillingProviderError:
            raise _provider_error()
        return ApiResponse.ok({"portal_url": link})

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
            # does not know (the old Razorpay webhook wrote "pro"). Report
            # the row the limits were actually read from, so a dashboard
            # showing "Community" and a gate enforcing Community's limits can
            # never disagree.
            "tier_name": get_tier(org.tier)["name"],
            "tier_known": is_known_tier(org.tier),
            # `source` lets the plan card say "custom limit" rather than show
            # 1,000 beside a Community plan the pricing page says allows 50.
            "credentials": {
                **_meter(cred_used, cred_limit),
                "source": credential_quota_source(org),
            },
            "templates": _meter(template_used, get_tier_template_limit(org.tier)),
            "vision_imports": _meter(vision_used, VISION_IMPORTS_PER_MONTH),
            # The same count services/entitlements.py gates bulk uploads on.
            "csv_batches": _meter(
                csv_batches_this_month(session, org),
                get_tier_csv_batch_limit(org.tier),
            ),
            # None for an org that has never subscribed, including every org
            # whose tier was set by hand.
            "subscription": billing.subscription_summary(org),
        })


#: Subscription events the handler reconciles. Every one is handled the same
#: way — by reading the subscription's state — so this list only decides which
#: payloads carry a subscription, not what happens to the org.
SUBSCRIPTION_EVENT_PREFIX = "subscription."


@webhooks_router.post("/dodo", response_model=ApiResponse[dict])
async def dodo_webhook(request: Request):
    """Apply a Dodo Payments webhook to the organization it concerns.

    Register this at the API host, not the dashboard's:
    https://api.certforge.intelliforge.tech/api/v1/webhooks/dodo. That host
    reaches Fly directly, so no vercel.json rewrite is involved.

    Status codes are how Dodo decides whether to retry, so they are chosen for
    it: 401 for an unverifiable delivery, 503 when unconfigured, 500 when
    applying failed (the transaction rolled back, so the retry can apply it),
    and 200 for everything Dodo should stop sending — including every event
    recorded as deliberately ignored.
    """
    raw_body = await request.body()

    try:
        event = billing.verify_webhook(raw_body, request.headers)
    except billing.BillingUnavailable as exc:
        # Fail closed. This handler grants paid tiers; an unset or unusable
        # key must reject rather than accept anything.
        logger.error("Dodo webhook received but cannot be verified: %s", exc)
        raise HTTPException(status_code=503, detail="Webhook signing is not configured")
    except billing.InvalidWebhook as exc:
        logger.warning("Rejected a Dodo webhook that failed verification: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Verified, so the header is present — verification signs over it.
    webhook_id = request.headers["webhook-id"]
    event_type = str(event.get("type") or "")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}

    try:
        with get_db() as session:
            # The replay guard. Checked first to answer a retry cheaply, and
            # enforced by the unique constraint for two deliveries that race.
            if session.query(BillingEvent.id).filter_by(webhook_id=webhook_id).first():
                return ApiResponse.ok({"status": "duplicate"})

            if event_type.startswith(SUBSCRIPTION_EVENT_PREFIX):
                outcome, org = billing.reconcile_subscription(session, data)
            else:
                # Payments, refunds, disputes: nothing here moves a tier.
                # Recorded so the trail is complete; refunds and disputes are
                # logged louder because a person may need to act on them.
                outcome, org = billing.IGNORED_EVENT_TYPE, None
                log = logger.warning if event_type.startswith(("refund.", "dispute.")) else logger.info
                log("Dodo %s event %s received; no entitlement change", event_type, webhook_id)

            # Same transaction as the change it records. If anything above or
            # the commit fails, both roll back and Dodo's retry starts clean.
            session.add(BillingEvent(
                webhook_id=webhook_id,
                event_type=event_type or "unknown",
                subscription_id=data.get("subscription_id"),
                org_id=org.id if org is not None else None,
                outcome=outcome,
            ))
    except IntegrityError:
        # A concurrent delivery of the same webhook-id committed first. Its
        # transaction applied the event; this one rolled back having done
        # nothing, which is the correct result.
        return ApiResponse.ok({"status": "duplicate"})

    return ApiResponse.ok({"status": "received", "outcome": outcome})

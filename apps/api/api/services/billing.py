"""Dodo Payments: the only module that talks to the billing provider.

Two halves, and both have to stay here:

- **Outbound** — `create_checkout` and `create_portal_link`. The only place a
  Dodo client is constructed, the same rule `services/vision.py` keeps for
  Anthropic. Unconfigured raises `BillingUnavailable`, which routes turn into a
  503; it never degrades into a placeholder URL, which is what the Razorpay
  stub did for months.
- **Inbound** — `verify_webhook` and `reconcile_subscription`. What a webhook
  is allowed to do to an organization's tier.

The rule the inbound half is built on: **an org's tier is derived from the
governing subscription's current state, never from the event's name.** Dodo
does not order deliveries, and every delivery carries the subscription as it
is at delivery time. A handler written as "on `active` grant, on `expired`
revoke" re-grants a dead subscription the first time a retried `active` lands
after its `expired`. Reading `status` off the payload cannot be fooled that way.
See docs/dodo-payments-integration-plan.md, decisions 1–3.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from api.core import config
from api.core.config import (
    CERTFORGE_WEB_URL,
    DEFAULT_TIER,
    product_for_tier,
    tier_for_product,
)
from api.models.organization import Organization
from api.services.plans import change_tier

logger = logging.getLogger(__name__)


class BillingUnavailable(Exception):
    """Billing is not configured or its SDK is missing. Routes answer 503."""


class BillingProviderError(Exception):
    """Dodo refused or failed a request. Routes answer 502."""


class InvalidWebhook(Exception):
    """The delivery is not provably from Dodo. The route answers 401."""


# ── Outcomes recorded on billing_events ────────────────────────────────────

APPLIED = "applied"
#: A duplicate delivery is never written — the unique webhook_id is what
#: detects it — so it has no outcome of its own.
IGNORED_EVENT_TYPE = "ignored_event_type"
IGNORED_UNKNOWN_ORG = "ignored_unknown_org"
IGNORED_UNKNOWN_PRODUCT = "ignored_unknown_product"
IGNORED_UNKNOWN_STATUS = "ignored_unknown_status"
IGNORED_NOT_CURRENT = "ignored_not_current"
IGNORED_STALE = "ignored_stale"


# ── Subscription states, and what each grants ──────────────────────────────

#: The subscription is paid for, or inside Dodo's recovery window. `on_hold`
#: and `past_due` keep the paid tier as a grace period while Dodo retries the
#: renewal; the dashboard warns, and `failed` or `cancelled` ends it.
GRANTING = frozenset({"active", "on_hold", "past_due"})
#: Paid for by nobody. `paused` included: a paused subscription is not
#: collecting, and `subscription.unpaused` brings it back to `active`.
REVOKING = frozenset({"expired", "failed", "paused"})
#: A governing subscription in one of these can never grant again. Guards the
#: case the payload-freshness guarantee is meant to rule out, cheaply.
TERMINAL = frozenset({"expired", "failed"})


# ── Outbound ───────────────────────────────────────────────────────────────


def _client():
    if not config.DODO_PAYMENTS_API_KEY:
        raise BillingUnavailable("DODO_PAYMENTS_API_KEY is not configured")
    try:
        from dodopayments import DodoPayments
    except ImportError as exc:  # pragma: no cover - pinned in requirements.txt
        raise BillingUnavailable("the dodopayments package is not installed") from exc
    return DodoPayments(
        bearer_token=config.DODO_PAYMENTS_API_KEY,
        environment=config.DODO_PAYMENTS_ENVIRONMENT,
    )


def _provider_errors() -> tuple[type[BaseException], ...]:
    try:
        from dodopayments import APIError
    except ImportError:  # pragma: no cover
        return ()
    return (APIError,)


def checkout_return_url(org: Organization) -> str:
    """Where Dodo sends the browser afterwards. The page it lands on polls the
    usage endpoint for the new tier and grants nothing itself — the browser
    arrives here before Dodo has necessarily finished the mandate, so only the
    webhook may move a tier (plan decision 8)."""
    return f"{CERTFORGE_WEB_URL}/org/{org.slug}/dashboard?checkout=complete"


def create_checkout(org: Organization, tier: str, email: Optional[str]) -> dict:
    """Start a hosted checkout for `tier`. The caller has already authorised
    the owner and validated the tier; this only talks to Dodo."""
    product_id = product_for_tier(tier)
    if not product_id:
        raise BillingUnavailable(f"no Dodo product is configured for tier {tier!r}")

    if org.dodo_customer_id:
        customer: Optional[dict] = {"customer_id": org.dodo_customer_id}
    elif email:
        customer = {"email": email, "name": org.name}
    else:
        # Clerk's default session token carries no email. Omitting the
        # customer lets Dodo's hosted page collect it, rather than refusing a
        # checkout over a claim we do not control.
        customer = None

    kwargs: dict[str, Any] = {
        "product_cart": [{"product_id": product_id, "quantity": 1}],
        # How the webhook finds the org again. `tier` rides along for
        # debugging only: the webhook derives the tier from `product_id`,
        # because metadata is written by us before payment and proves nothing.
        "metadata": {"org_id": str(org.id), "tier": tier},
        "return_url": checkout_return_url(org),
    }
    if customer:
        kwargs["customer"] = customer

    client = _client()
    try:
        session = client.checkout_sessions.create(**kwargs)
    except _provider_errors() as exc:
        logger.error("Dodo refused a checkout session for org %s: %s", org.id, exc)
        raise BillingProviderError(str(exc)) from exc

    if not session.checkout_url:
        raise BillingProviderError("Dodo returned a checkout session with no URL")
    return {"checkout_url": session.checkout_url, "session_id": session.session_id}


def create_portal_link(org: Organization) -> str:
    """A fresh customer-portal link. They expire after 24 hours, so one is made
    per click and never stored."""
    if not org.dodo_customer_id:
        raise ValueError("organization has no Dodo customer")
    client = _client()
    try:
        portal = client.customers.customer_portal.create(
            org.dodo_customer_id,
            return_url=f"{CERTFORGE_WEB_URL}/org/{org.slug}/dashboard",
        )
    except _provider_errors() as exc:
        logger.error("Dodo refused a portal session for org %s: %s", org.id, exc)
        raise BillingProviderError(str(exc)) from exc
    return portal.link


# ── Inbound ────────────────────────────────────────────────────────────────


def verify_webhook(raw_body: bytes, headers: Mapping[str, str]) -> dict:
    """Verify a delivery against DODO_PAYMENTS_WEBHOOK_KEY and return its body.

    Uses `standardwebhooks` directly — exactly what the SDK's
    `webhooks.unwrap` does — so verification needs only the webhook key, not
    the API key, and hands back the raw dict rather than a typed model that
    would have to be re-read field by field.

    The signed message is `webhook-id.webhook-timestamp.body` over the raw
    bytes, and the timestamp must be within five minutes, which is what makes
    a captured delivery useless for replay after that.
    """
    if not config.DODO_PAYMENTS_WEBHOOK_KEY:
        raise BillingUnavailable("DODO_PAYMENTS_WEBHOOK_KEY is not configured")
    try:
        from standardwebhooks import Webhook
    except ImportError as exc:  # pragma: no cover - pulled in by dodopayments[webhooks]
        raise BillingUnavailable("the standardwebhooks package is not installed") from exc

    try:
        verifier = Webhook(config.DODO_PAYMENTS_WEBHOOK_KEY)
    except Exception as exc:
        # A key that is not valid base64 is a configuration fault, not a bad
        # delivery. Say so, rather than 401-ing every legitimate webhook.
        raise BillingUnavailable("DODO_PAYMENTS_WEBHOOK_KEY is not a valid webhook secret") from exc

    try:
        # Any failure is a refusal. A malformed signature header makes the
        # library raise ValueError or binascii.Error rather than its own
        # WebhookVerificationError, and that must be a 401, not a 500.
        body = verifier.verify(raw_body, dict(headers))
    except Exception as exc:
        raise InvalidWebhook(str(exc)) from exc

    if not isinstance(body, dict):
        raise InvalidWebhook("webhook body is not a JSON object")
    return body


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    # SQLite hands back naive datetimes for timezone-aware columns.
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _resolve_org(session: Session, data: dict) -> Optional[Organization]:
    """Checkout metadata first, then the governing subscription id.

    Metadata is set by our own checkout, so it is how a *new* subscription is
    matched to its org. The subscription id covers events for a subscription
    whose metadata did not carry through (plan open question 2).
    """
    org_id = (data.get("metadata") or {}).get("org_id")
    if org_id:
        try:
            org = session.get(Organization, uuid.UUID(str(org_id)))
        except (TypeError, ValueError):
            org = None
        if org is not None:
            return org

    subscription_id = data.get("subscription_id")
    if subscription_id:
        return (
            session.query(Organization)
            .filter_by(dodo_subscription_id=subscription_id)
            .first()
        )
    return None


def holds_live_subscription(org: Organization) -> bool:
    """Whether the org's governing subscription still stands in the way of a
    new one. A subscription the owner has cancelled at period end does not —
    resubscribing before it lapses is a legitimate thing to do."""
    return (
        org.dodo_subscription_id is not None
        and org.subscription_status in GRANTING
        and not org.cancel_at_period_end
    )


def _target_tier(data: dict, now: datetime) -> tuple[Optional[str], Optional[str]]:
    """(tier the org should hold, or None; outcome if the event is to be ignored).

    Reads state only. `tier_for_product` is consulted solely where the answer
    is a paid tier; a revocation goes to Community whatever the product, so a
    misconfigured product id can never keep a lapsed org on a paid plan.
    """
    status = data.get("status")
    paid = tier_for_product(data.get("product_id"))

    def grant():
        if paid is None:
            return None, IGNORED_UNKNOWN_PRODUCT
        return paid, None

    if status in GRANTING:
        return grant()
    if status == "cancelled":
        period_end = _parse_time(data.get("next_billing_date"))
        if data.get("cancel_at_next_billing_date") and period_end and period_end > now:
            # Cancelled at period end: paid until then. `expired` follows.
            return grant()
        return DEFAULT_TIER, None
    if status in REVOKING:
        return DEFAULT_TIER, None
    if status == "pending":
        return None, None  # nothing to grant yet, nothing to take away
    return None, IGNORED_UNKNOWN_STATUS


def reconcile_subscription(
    session: Session, data: dict, *, now: Optional[datetime] = None
) -> tuple[str, Optional[Organization]]:
    """Bring an org in line with one subscription payload. Returns the outcome.

    Runs inside the caller's transaction, beside the billing_events insert, so
    a failure here rolls both back and Dodo's retry can apply the event.
    """
    now = now or datetime.now(timezone.utc)
    subscription_id = data.get("subscription_id")
    status = data.get("status")

    org = _resolve_org(session, data)
    if org is None:
        logger.warning("Dodo subscription %s names no organization we know", subscription_id)
        return IGNORED_UNKNOWN_ORG, None

    # Decision 2: only the governing subscription may move an org. A different
    # subscription takes over only by arriving `active` while nothing live
    # stands in its way. This one rule is what keeps an old subscription's late
    # `expired` from downgrading an org that has since resubscribed — and, since
    # a hand-set tier has no governing subscription, what keeps a stray event
    # from touching one unless it is a genuine new subscription for that org.
    if org.dodo_subscription_id != subscription_id:
        if status != "active":
            return IGNORED_NOT_CURRENT, org
        if holds_live_subscription(org):
            logger.error(
                "Org %s already has live subscription %s; a second one, %s, is "
                "active. Left in place for a person to resolve — possibly a "
                "double checkout that needs a refund.",
                org.id, org.dodo_subscription_id, subscription_id,
            )
            return IGNORED_NOT_CURRENT, org
    elif org.subscription_status in TERMINAL and status in GRANTING:
        # A terminal subscription never grants again. Dodo sends current
        # state, so this should not arrive; if it does, it is stale.
        return IGNORED_STALE, org

    tier, ignored = _target_tier(data, now)
    if ignored:
        if ignored == IGNORED_UNKNOWN_PRODUCT:
            logger.error(
                "Dodo subscription %s is for product %r, which no tier is sold "
                "as. Check the DODO_PRODUCT_* settings. Org %s left unchanged.",
                subscription_id, data.get("product_id"), org.id,
            )
        return ignored, org

    org.dodo_subscription_id = subscription_id
    org.subscription_status = status
    org.current_period_end = _parse_time(data.get("next_billing_date"))
    org.cancel_at_period_end = bool(data.get("cancel_at_next_billing_date"))
    customer_id = (data.get("customer") or {}).get("customer_id")
    if customer_id:
        org.dodo_customer_id = customer_id
    if tier is not None:
        # Through change_tier(), the only writer of org.tier
        # (docs/operator-quota-overrides-plan.md, Decision 4). A real change
        # clears any operator credential override and logs that it did. The
        # same tier changes nothing — Dodo redelivers, and an override set
        # since must survive. An org hand-set to Starter that then buys
        # Starter therefore keeps an override an operator gave it; the plan
        # accepts that, and the operator screen shows it.
        change_tier(
            session, org, tier,
            actor="dodo-webhook",
            reason=f"Dodo subscription {subscription_id} is {status}",
        )
    return APPLIED, org


def subscription_summary(org: Organization) -> Optional[dict]:
    """The dashboard's view of the governing subscription, or None."""
    if not org.dodo_subscription_id:
        return None
    period_end = _aware(org.current_period_end)
    return {
        "status": org.subscription_status,
        "current_period_end": period_end.isoformat() if period_end else None,
        "cancel_at_period_end": bool(org.cancel_at_period_end),
        "manageable": bool(org.dodo_customer_id),
    }


# ── Recovering a subscription whose webhook never arrived ──────────────────


def fetch_subscription(subscription_id: str) -> dict:
    """A subscription as Dodo holds it now, shaped as a subscription webhook's
    `data` — the same object, which is what lets `reconcile_subscription`
    apply it unchanged.

    For a delivery that never happened (no endpoint in that mode, a key that
    did not match). Dodo can only resend a delivery it attempted, so without
    this a paid org waits for next month's renewal event to be upgraded.
    """
    client = _client()
    try:
        subscription = client.subscriptions.retrieve(subscription_id)
    except _provider_errors() as exc:
        raise BillingProviderError(str(exc)) from exc
    # JSON mode, so timestamps arrive as the ISO strings a webhook carries.
    return subscription.to_dict(mode="json")


# ── The join between Dodo and this API ─────────────────────────────────────

#: Where Dodo must deliver. The API host, never the dashboard's: that one
#: reaches Fly directly, so no Vercel rewrite sits between Dodo and the handler.
WEBHOOK_PATH = "/api/v1/webhooks/dodo"

#: The subscription events the handler reconciles, as
#: `scripts/provision_dodo_webhook.py` registers them. An endpoint filtered to
#: fewer misses the transitions it leaves out — a cancellation that never
#: arrives keeps a lapsed org on a paid plan.
REQUIRED_WEBHOOK_EVENTS = (
    "subscription.active",
    "subscription.renewed",
    "subscription.on_hold",
    "subscription.paused",
    "subscription.unpaused",
    "subscription.past_due",
    "subscription.cancelled",
    "subscription.failed",
    "subscription.expired",
    "subscription.plan_changed",
)


def webhook_url() -> str:
    return f"{config.CERTFORGE_API_URL}{WEBHOOK_PATH}"


def webhook_readiness() -> list[str]:
    """Whatever stands between a payment and a tier change, or [] if nothing.

    Checks the join, not either half: an endpoint in *the API key's mode*
    pointing at this host, enabled, subscribed to every event the handler
    reconciles, and signing with the key this process verifies against.
    Each half was correct on its own when a live payment succeeded and the
    org stayed on Community — the endpoint existed in test mode only, so the
    live payment notified nobody, and nothing had checked the two together.

    Raises BillingUnavailable or BillingProviderError when it cannot ask.
    Never includes a secret in what it returns.
    """
    mode = config.DODO_PAYMENTS_ENVIRONMENT
    url = webhook_url()
    fix = "Run scripts/provision_dodo_webhook.py --apply" + (" --live" if mode == "live_mode" else "")

    client = _client()
    try:
        endpoints = [
            endpoint for endpoint in client.webhooks.list()
            if (endpoint.url or "").rstrip("/") == url
        ]
    except _provider_errors() as exc:
        raise BillingProviderError(str(exc)) from exc

    if not endpoints:
        return [
            f"No {mode} webhook endpoint in Dodo delivers to {url}. Payments will "
            f"succeed and no tier will ever change. {fix}."
        ]
    enabled = [endpoint for endpoint in endpoints if not endpoint.disabled]
    if not enabled:
        return [f"The {mode} webhook endpoint for {url} is disabled in Dodo. Re-enable it."]

    problems = []
    # An empty filter is Dodo's "every event".
    if not any(
        not endpoint.filter_types or set(REQUIRED_WEBHOOK_EVENTS) <= set(endpoint.filter_types)
        for endpoint in enabled
    ):
        missing = sorted(set(REQUIRED_WEBHOOK_EVENTS) - set(enabled[0].filter_types or []))
        problems.append(
            f"The {mode} webhook endpoint for {url} does not subscribe to "
            f"{', '.join(missing)}. Those transitions will never reach the handler."
        )

    if not config.DODO_PAYMENTS_WEBHOOK_KEY:
        problems.append("DODO_PAYMENTS_WEBHOOK_KEY is not set, so every delivery is refused 503.")
    else:
        try:
            secrets = [
                getattr(client.webhooks.retrieve_secret(endpoint.id), "secret", None)
                for endpoint in enabled
            ]
        except _provider_errors() as exc:
            raise BillingProviderError(str(exc)) from exc
        if config.DODO_PAYMENTS_WEBHOOK_KEY not in secrets:
            problems.append(
                f"DODO_PAYMENTS_WEBHOOK_KEY is not the signing secret of the {mode} "
                f"endpoint for {url}, so every delivery is refused 401. {fix} and set "
                f"the key it prints."
            )
    return problems

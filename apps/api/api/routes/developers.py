import uuid
import logging
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from api.models import get_db
from api.models.organization import Organization
from api.models.api_key import ApiKey, WebhookDelivery, WebhookEndpoint
from api.core.envelope import ApiException, ApiResponse
from api.core.principal import LIVE_PREFIX, TEST_PREFIX
from api.core.principal import Principal, require_user, require_org_access
from api.services.entitlements import require_grant
from api.services.webhooks import (
    STATUS_ABANDONED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCEEDED,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs/{slug}", tags=["developers"])

#: How many deliveries the per-endpoint list returns, newest first.
DELIVERY_LIST_LIMIT = 50

#: A ``pending`` delivery whose ``next_attempt_at`` is further in the past than
#: this has lost its job — a deploy or idle stop took it, and B-core has no
#: sweep that would find it. A fresher pending row is refused: its own job is
#: still coming, and a redeliver would only double it.
STRANDED_PENDING_AFTER = timedelta(minutes=15)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _as_utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; Postgres hands back aware ones.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _delivery_dict(row: WebhookDelivery) -> dict:
    """The Delivery object (docs/build-plan-2026-11.md). Never the payload."""
    return {
        "id": str(row.id),
        "event": row.event,
        "status": row.status,
        "attempts": row.attempts or 0,
        "last_status_code": row.last_status_code,
        "last_error": row.last_error,
        "next_attempt_at": _iso(row.next_attempt_at),
        "created_at": _iso(row.created_at),
        "delivered_at": _iso(row.delivered_at),
    }


def _redeliver_refusal(row: WebhookDelivery, now: datetime) -> Optional[str]:
    """Why this delivery cannot be redelivered, or None when it can."""
    if row.status in (STATUS_FAILED, STATUS_ABANDONED):
        return None
    if row.status == STATUS_PENDING:
        if (
            row.next_attempt_at is not None
            and _as_utc(row.next_attempt_at) < now - STRANDED_PENDING_AFTER
        ):
            return None
        return "This delivery is still queued; its first attempt has not run yet."
    if row.status == STATUS_SUCCEEDED:
        return "This delivery already succeeded."
    return f"A delivery in status '{row.status}' cannot be redelivered."


def _parse_uuid(value: str, what: str) -> uuid.UUID:
    # A malformed id names nothing, so it is a 404 like any other missing row.
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise ApiException(404, f"{what} not found")


def _managed_endpoint(session, slug: str, webhook_id: str, principal: Principal):
    """The org and endpoint a delivery route acts on, behind webhook management's checks.

    The endpoint is looked up by id **and** org, so another org's endpoint id
    is a 404 here, never a 403 that would confirm it exists.
    """
    org = session.query(Organization).filter_by(slug=slug).first()
    if not org:
        raise ApiException(404, "Organization not found")
    require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
    require_grant(org, "api_access")
    endpoint = (
        session.query(WebhookEndpoint)
        .filter_by(id=_parse_uuid(webhook_id, "Webhook"), org_id=org.id)
        .first()
    )
    if not endpoint:
        raise ApiException(404, "Webhook not found")
    return org, endpoint

def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

@router.post("/api-keys", response_model=ApiResponse[dict])
def create_api_key(
    slug: str,
    payload: Dict[str, Any],
    principal: Principal = Depends(require_user)
):
    """Generate a new API key for the organization."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
        # Gated on creation only. A key made before the org's plan changed
        # keeps authenticating — see require_grant.
        require_grant(org, "api_access")

        label = payload.get("label", "Default Key")

        # Test keys authenticate exactly like live ones and write to the same
        # database, but never send email and never bill — so the API can be
        # explored before anyone is ready to spend money. The distinction lives
        # in the prefix because the raw key is shown once and never stored.
        kind = str(payload.get("kind", "live")).lower()
        if kind not in ("live", "test"):
            raise HTTPException(status_code=400, detail="kind must be 'live' or 'test'")
        prefix = TEST_PREFIX if kind == "test" else LIVE_PREFIX

        raw_key = f"{prefix}{secrets.token_urlsafe(32)}"
        key_hash = _hash_key(raw_key)
        
        api_key = ApiKey(
            org_id=org.id,
            key_hash=key_hash,
            label=label
        )
        session.add(api_key)
        session.commit()
        
        return ApiResponse.ok({
            "id": str(api_key.id),
            "label": api_key.label,
            "kind": kind,
            "raw_key": raw_key,
            "created_at": api_key.created_at.isoformat()
        })

@router.get("/api-keys", response_model=ApiResponse[List[dict]])
def list_api_keys(
    slug: str,
    principal: Principal = Depends(require_user)
):
    """List active API keys."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        keys = session.query(ApiKey).filter_by(org_id=org.id, revoked_at=None).all()
        return ApiResponse.ok([
            {
                "id": str(k.id),
                "label": k.label,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat()
            } for k in keys
        ])

@router.delete("/api-keys/{key_id}", response_model=ApiResponse[dict])
def revoke_api_key(
    slug: str,
    key_id: str,
    principal: Principal = Depends(require_user)
):
    """Revoke an API key."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
        
        key = session.query(ApiKey).filter_by(id=uuid.UUID(key_id), org_id=org.id).first()
        if not key or not key.is_active:
            return ApiResponse.fail("Key not found or already revoked", code=404)
            
        key.revoked_at = datetime.now(timezone.utc)
        session.commit()
        
        return ApiResponse.ok({"status": "revoked"})

@router.post("/webhooks", response_model=ApiResponse[dict])
def create_webhook(
    slug: str,
    payload: Dict[str, Any],
    principal: Principal = Depends(require_user)
):
    """Register a new webhook endpoint."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
        require_grant(org, "api_access")

        url = payload.get("url")
        if not url:
            return ApiResponse.fail("Webhook URL is required", code=400)
            
        events = payload.get("events", ["batch.completed"])
        secret = f"whsec_{secrets.token_hex(16)}"
        
        webhook = WebhookEndpoint(
            org_id=org.id,
            url=url,
            secret=secret,
            events=events
        )
        session.add(webhook)
        session.commit()
        
        return ApiResponse.ok({
            "id": str(webhook.id),
            "url": webhook.url,
            "secret": secret,
            "events": webhook.events,
            "created_at": webhook.created_at.isoformat()
        })

@router.get("/webhooks", response_model=ApiResponse[List[dict]])
def list_webhooks(
    slug: str,
    principal: Principal = Depends(require_user)
):
    """List webhook endpoints."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        webhooks = session.query(WebhookEndpoint).filter_by(org_id=org.id, active=True).all()

        # The newest delivery per endpoint in two queries, not one per endpoint:
        # each endpoint's max(created_at), joined back to its row.
        last: Dict[uuid.UUID, WebhookDelivery] = {}
        if webhooks:
            newest = (
                session.query(
                    WebhookDelivery.endpoint_id.label("endpoint_id"),
                    func.max(WebhookDelivery.created_at).label("created_at"),
                )
                .filter(
                    WebhookDelivery.endpoint_id.in_([w.id for w in webhooks]),
                    WebhookDelivery.org_id == org.id,
                )
                .group_by(WebhookDelivery.endpoint_id)
                .subquery()
            )
            rows = (
                session.query(WebhookDelivery)
                .join(
                    newest,
                    (WebhookDelivery.endpoint_id == newest.c.endpoint_id)
                    & (WebhookDelivery.created_at == newest.c.created_at),
                )
                .all()
            )
            # Two rows can share a timestamp; pick one deterministically.
            for row in sorted(rows, key=lambda r: str(r.id)):
                last.setdefault(row.endpoint_id, row)

        return ApiResponse.ok([
            {
                "id": str(w.id),
                "url": w.url,
                "events": w.events,
                "created_at": w.created_at.isoformat(),
                "last_delivery": _delivery_dict(last[w.id]) if w.id in last else None,
            } for w in webhooks
        ])


@router.get("/webhooks/{webhook_id}/deliveries", response_model=ApiResponse[List[dict]])
def list_webhook_deliveries(
    slug: str,
    webhook_id: str,
    principal: Principal = Depends(require_user),
):
    """The most recent deliveries to one endpoint, newest first."""
    with get_db() as session:
        org, endpoint = _managed_endpoint(session, slug, webhook_id, principal)
        rows = (
            session.query(WebhookDelivery)
            .filter_by(endpoint_id=endpoint.id, org_id=org.id)
            .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
            .limit(DELIVERY_LIST_LIMIT)
            .all()
        )
        return ApiResponse.ok([_delivery_dict(r) for r in rows])


@router.post(
    "/webhooks/{webhook_id}/deliveries/{delivery_id}/redeliver",
    response_model=ApiResponse[dict],
)
async def redeliver_webhook_delivery(
    slug: str,
    webhook_id: str,
    delivery_id: str,
    principal: Principal = Depends(require_user),
):
    """Queue one more attempt at a delivery, under the same event id.

    No new row and no reset: ``attempts`` keeps counting, and the automatic
    schedule is left as it is. On an abandoned row the queued attempt is
    final whichever way it goes, because ``next_delay`` is already exhausted.
    """
    # Imported here so this module does not pull the worker in at import time.
    from api.core.worker import deliver_webhook

    with get_db() as session:
        org, endpoint = _managed_endpoint(session, slug, webhook_id, principal)
        row = (
            session.query(WebhookDelivery)
            .filter_by(
                id=_parse_uuid(delivery_id, "Delivery"),
                endpoint_id=endpoint.id,
                org_id=org.id,
            )
            .first()
        )
        if not row:
            raise ApiException(404, "Delivery not found")
        refusal = _redeliver_refusal(row, datetime.now(timezone.utc))
        if refusal:
            raise ApiException(
                409,
                refusal,
                error_type="delivery_not_redeliverable",
                details={"status": row.status},
            )
        row_id = row.id

    try:
        await deliver_webhook.defer_async(delivery_id=str(row_id))
    except Exception:
        logger.exception("Could not queue a redelivery of webhook %s", row_id)
        raise ApiException(503, "Could not queue the redelivery. Try again shortly.")

    # Read again so the response is the row as it stands once the job is queued.
    with get_db() as session:
        row = session.get(WebhookDelivery, row_id)
        if not row:
            raise ApiException(404, "Delivery not found")
        return ApiResponse.ok(_delivery_dict(row))

@router.delete("/webhooks/{webhook_id}", response_model=ApiResponse[dict])
def delete_webhook(
    slug: str,
    webhook_id: str,
    principal: Principal = Depends(require_user)
):
    """Delete/Deactivate a webhook endpoint."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            return ApiResponse.fail("Organization not found", code=404)
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
        
        webhook = session.query(WebhookEndpoint).filter_by(id=uuid.UUID(webhook_id), org_id=org.id).first()
        if not webhook:
            return ApiResponse.fail("Webhook not found", code=404)
            
        webhook.active = False
        session.commit()
        
        return ApiResponse.ok({"status": "deleted"})

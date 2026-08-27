import uuid
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException

from api.models import get_db
from api.models.organization import Organization
from api.models.api_key import ApiKey, WebhookEndpoint
from api.core.envelope import ApiResponse
from api.core.principal import LIVE_PREFIX, TEST_PREFIX
from api.core.principal import Principal, require_user, require_org_access

router = APIRouter(prefix="/orgs/{slug}", tags=["developers"])

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
        return ApiResponse.ok([
            {
                "id": str(w.id),
                "url": w.url,
                "events": w.events,
                "created_at": w.created_at.isoformat()
            } for w in webhooks
        ])

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

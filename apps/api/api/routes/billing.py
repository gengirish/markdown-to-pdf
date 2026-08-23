import hashlib
import hmac
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request

from api.models import get_db
from api.models.organization import Organization
from api.core.envelope import ApiResponse
from api.core.auth import get_current_user, AuthenticatedUser
from api.core.config import RAZORPAY_SECRET

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs", tags=["billing"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/{slug}/checkout", response_model=ApiResponse[dict])
def create_checkout_session(
    slug: str,
    payload: Dict[str, Any],
    user: AuthenticatedUser = Depends(get_current_user)
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
        org_id = (entity.get("notes") or {}).get("org_id")
        if org_id:
            with get_db() as session:
                org = session.query(Organization).filter_by(id=org_id).first()
                if org:
                    org.tier = "pro"
                    org.monthly_quota = 500
                    org.razorpay_sub_id = entity.get("id")
                    session.commit()
                    
    return ApiResponse.ok({"status": "received"})

import hmac
import hashlib
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request

from api.models import get_db
from api.models.organization import Organization
from api.core.envelope import ApiResponse
from api.core.auth import get_current_user, AuthenticatedUser
from api.core.config import RAZORPAY_SECRET

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
            return ApiResponse.fail("Organization not found", code=404)
            
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
    signature = request.headers.get("X-Razorpay-Signature")
    
    if not signature or not RAZORPAY_SECRET:
        return ApiResponse.fail("Missing signature or secret", code=400)
        
    expected = hmac.new(RAZORPAY_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return ApiResponse.fail("Invalid signature", code=400)
        
    data = await request.json()
    event = data.get("event")
    
    if event == "subscription.activated":
        # Extract org_id from notes/metadata (mocked)
        org_id = data["payload"]["subscription"]["entity"]["notes"].get("org_id")
        if org_id:
            with get_db() as session:
                org = session.query(Organization).filter_by(id=org_id).first()
                if org:
                    org.tier = "pro"
                    org.monthly_quota = 500
                    org.razorpay_sub_id = data["payload"]["subscription"]["entity"]["id"]
                    session.commit()
                    
    return ApiResponse.ok({"status": "received"})

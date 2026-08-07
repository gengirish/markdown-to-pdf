import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from api.models import get_db
from api.models.credential import Credential
from api.models.passport import Passport, PassportCredential
from api.core.envelope import ApiResponse
from api.core.auth import get_current_user, AuthenticatedUser

router = APIRouter(prefix="/passports", tags=["passports"])
claims_router = APIRouter(prefix="/claims", tags=["claims"])

@claims_router.post("/{credential_id}", response_model=ApiResponse[dict])
def claim_credential(
    credential_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Claim a credential using its public ID."""
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=credential_id).first()
        if not cred:
            return ApiResponse.fail("Credential not found", code=404)
            
        if cred.claimed_by_user_id and cred.claimed_by_user_id != user.clerk_user_id:
            return ApiResponse.fail("Credential already claimed by another user", code=403)
            
        # Ensure passport exists
        passport = session.query(Passport).filter_by(clerk_user_id=user.clerk_user_id).first()
        if not passport:
            # Generate a username base from email
            base_username = user.email.split("@")[0].lower()
            passport = Passport(
                clerk_user_id=user.clerk_user_id,
                username=f"{base_username}-{str(uuid.uuid4())[:8]}",
                display_name=base_username,
                bio="",
                is_public=True
            )
            session.add(passport)
            session.flush()
            
        # Link credential
        existing_link = session.query(PassportCredential).filter_by(
            passport_id=passport.id,
            credential_id=cred.id
        ).first()
        
        if not existing_link:
            link = PassportCredential(
                passport_id=passport.id,
                credential_id=cred.id,
                display_order=0,
                pinned=False
            )
            session.add(link)
            
        # Update credential claimed_by
        cred.claimed_by_user_id = user.clerk_user_id
        session.commit()
        
        return ApiResponse.ok({
            "username": passport.username,
            "credential_id": cred.public_id
        })

@router.get("/{username}", response_model=ApiResponse[dict])
def get_passport(username: str):
    """Fetch public passport profile and its credentials."""
    with get_db() as session:
        passport = session.query(Passport).filter_by(username=username).first()
        if not passport:
            return ApiResponse.fail("Passport not found", code=404)
            
        if not passport.is_public:
            return ApiResponse.fail("Passport is private", code=403)
            
        links = session.query(PassportCredential).filter_by(passport_id=passport.id).all()
        
        creds = []
        for link in links:
            # Re-fetch credential to get full details
            cred = session.query(Credential).filter_by(id=link.credential_id).first()
            if cred and cred.status != "revoked":
                creds.append({
                    "id": cred.public_id,
                    "title": cred.title,
                    "recipient_name": cred.recipient_name,
                    "issued_at": cred.issued_at.isoformat(),
                    "metadata": cred.metadata,
                    "pinned": link.pinned
                })
                
        return ApiResponse.ok({
            "profile": {
                "username": passport.username,
                "display_name": passport.display_name,
                "bio": passport.bio
            },
            "credentials": creds
        })

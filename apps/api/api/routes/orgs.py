"""Organization API endpoints."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from api.core.envelope import ApiResponse
from api.core.auth import AuthenticatedUser, get_current_user, require_org_role
from api.models import get_db
from api.models.organization import Organization, OrgMember

# Mounted under /api/v1 by api/index.py — the prefix here must NOT repeat it,
# or every path ends up served at /api/v1/api/v1/...
router = APIRouter(prefix="/orgs", tags=["Organizations"])

class OrgCreate(BaseModel):
    clerk_org_id: str
    slug: str
    name: str
    logo_url: str | None = None

class OrgUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None

@router.post("", response_model=ApiResponse[dict])
def create_org(
    payload: OrgCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Create a new organization. Usually called by Clerk webhooks, but available via API."""
    with get_db() as session:
        existing = session.query(Organization).filter_by(slug=payload.slug).first()
        if existing:
            raise HTTPException(status_code=409, detail="Organization slug already in use")

        # This endpoint has always *required* clerk_org_id and then discarded it,
        # leaving no way to tell which Clerk org a row mirrored. Persist it, and
        # reject a second CertForge org claiming the same Clerk org rather than
        # letting the unique index surface as a 500.
        clashing = (
            session.query(Organization)
            .filter_by(clerk_org_id=payload.clerk_org_id)
            .first()
        )
        if clashing:
            raise HTTPException(
                status_code=409,
                detail=f"Clerk organization already linked to '{clashing.slug}'",
            )

        org = Organization(
            clerk_org_id=payload.clerk_org_id,
            slug=payload.slug,
            name=payload.name,
            logo_url=payload.logo_url,
            tier="community"
        )
        session.add(org)
        session.flush() # flush to get org.id

        member = OrgMember(
            org_id=org.id,
            clerk_user_id=user.clerk_user_id,
            role="owner"
        )
        session.add(member)
        
        return ApiResponse.ok({
            "id": str(org.id),
            "slug": org.slug,
            "name": org.name
        })

@router.get("/{slug}", response_model=ApiResponse[dict])
def get_org(slug: str):
    """Public organization profile."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        return ApiResponse.ok({
            "id": str(org.id),
            "slug": org.slug,
            "name": org.name,
            "logo_url": org.logo_url,
            "tier": org.tier
        })

@router.patch("/{slug}", response_model=ApiResponse[dict])
def update_org(
    slug: str,
    payload: OrgUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Update organization details. Requires owner or admin role."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_role(user, str(org.id), allowed_roles=("owner", "admin"))
        
        if payload.name is not None:
            org.name = payload.name
        if payload.logo_url is not None:
            org.logo_url = payload.logo_url
            
        return ApiResponse.ok({
            "id": str(org.id),
            "slug": org.slug,
            "name": org.name,
            "logo_url": org.logo_url
        })

@router.get("/{slug}/members", response_model=ApiResponse[list[dict]])
def list_org_members(
    slug: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """List members of an organization."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_role(user, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        members = session.query(OrgMember).filter_by(org_id=org.id).all()
        
        data = [{
            "clerk_user_id": m.clerk_user_id,
            "role": m.role,
            "joined_at": m.created_at.isoformat()
        } for m in members]
        
        return ApiResponse.ok(data)

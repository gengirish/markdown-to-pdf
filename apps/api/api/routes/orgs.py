"""Organization API endpoints."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from api.core.envelope import ApiResponse
from api.core.principal import Principal, require_user, require_org_access
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
    primary_color: str | None = None
    accent_color: str | None = None
    footer_text: str | None = None

class OrgUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    footer_text: str | None = None

@router.post("", response_model=ApiResponse[dict])
def create_org(
    payload: OrgCreate,
    principal: Principal = Depends(require_user)
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
            primary_color=payload.primary_color,
            accent_color=payload.accent_color,
            footer_text=payload.footer_text,
            tier="community"
        )
        session.add(org)
        session.flush() # flush to get org.id

        member = OrgMember(
            org_id=org.id,
            clerk_user_id=principal.clerk_user_id,
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
            # The dashboard decides between "Upload a logo" and "Replace" on
            # this, and the certificate prints the asset rather than the URL.
            # Without it the card cannot tell an org that has a printable logo
            # from one that has only a link.
            "logo_asset_id": str(org.logo_asset_id) if org.logo_asset_id else None,
            "primary_color": org.primary_color,
            "accent_color": org.accent_color,
            "footer_text": org.footer_text,
            "tier": org.tier
        })

@router.patch("/{slug}", response_model=ApiResponse[dict])
def update_org(
    slug: str,
    payload: OrgUpdate,
    principal: Principal = Depends(require_user)
):
    """Update organization details. Requires owner or admin role."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin"))
        
        if payload.name is not None:
            org.name = payload.name
        if payload.logo_url is not None:
            org.logo_url = payload.logo_url
        if payload.primary_color is not None:
            org.primary_color = payload.primary_color
        if payload.accent_color is not None:
            org.accent_color = payload.accent_color
        if payload.footer_text is not None:
            org.footer_text = payload.footer_text

        return ApiResponse.ok({
            "id": str(org.id),
            "slug": org.slug,
            "name": org.name,
            "logo_url": org.logo_url,
            # The dashboard decides between "Upload a logo" and "Replace" on
            # this, and the certificate prints the asset rather than the URL.
            # Without it the card cannot tell an org that has a printable logo
            # from one that has only a link.
            "logo_asset_id": str(org.logo_asset_id) if org.logo_asset_id else None,
            "primary_color": org.primary_color,
            "accent_color": org.accent_color,
            "footer_text": org.footer_text
        })

@router.get("/{slug}/members", response_model=ApiResponse[list[dict]])
def list_org_members(
    slug: str,
    principal: Principal = Depends(require_user)
):
    """List members of an organization."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        members = session.query(OrgMember).filter_by(org_id=org.id).all()
        
        data = [{
            "clerk_user_id": m.clerk_user_id,
            "role": m.role,
            "joined_at": m.created_at.isoformat()
        } for m in members]
        
        return ApiResponse.ok(data)

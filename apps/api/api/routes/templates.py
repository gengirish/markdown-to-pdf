"""Templates API endpoints."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.core.envelope import ApiResponse
from api.core.auth import AuthenticatedUser, get_current_user, get_optional_user, require_org_role
from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template

# Mounted under /api/v1 by api/index.py — the prefix here must NOT repeat it,
# or every path ends up served at /api/v1/api/v1/...
router = APIRouter(tags=["Templates"])

class TemplateUpload(BaseModel):
    name: str
    html_source: str
    variables: list[str]

@router.get("/templates", response_model=ApiResponse[list[dict]])
def list_global_templates(
    user: AuthenticatedUser | None = Depends(get_optional_user)
):
    """List globally available default templates."""
    with get_db() as session:
        templates = session.query(Template).filter_by(org_id=None, is_default=True).all()
        data = [{
            "id": str(t.id),
            "name": t.name,
            "variables": t.variables,
            "is_default": t.is_default
        } for t in templates]
        return ApiResponse.ok(data)

@router.get("/orgs/{slug}/templates", response_model=ApiResponse[list[dict]])
def list_org_templates(
    slug: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """List custom templates for an organization."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_role(user, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        templates = session.query(Template).filter_by(org_id=org.id).all()
        data = [{
            "id": str(t.id),
            "name": t.name,
            "variables": t.variables,
            "is_default": t.is_default
        } for t in templates]
        return ApiResponse.ok(data)

@router.post("/orgs/{slug}/templates", response_model=ApiResponse[dict])
def upload_org_template(
    slug: str,
    payload: TemplateUpload,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Upload a custom template for an organization (Paid feature)."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_role(user, str(org.id), allowed_roles=("owner", "admin"))
        
        # In a real app we'd enforce the tier checks here
        if org.tier == "community":
            raise HTTPException(status_code=403, detail="Custom templates require a paid plan")
            
        template = Template(
            org_id=org.id,
            name=payload.name,
            html_source=payload.html_source,
            variables=payload.variables,
            is_default=False
        )
        session.add(template)
        session.flush()
        
        return ApiResponse.ok({
            "id": str(template.id),
            "name": template.name,
            "variables": template.variables
        })

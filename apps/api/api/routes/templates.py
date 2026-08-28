"""Templates API endpoints.

A template is authored one of two ways and stored as one thing. `html_source` is
what issuance renders; `config` is the guided form's settings, kept so the form
can be reopened, and dropped the moment the HTML is edited by hand.

Template HTML is customer-supplied and goes into a PDF renderer, so every write
path runs it through `services/templates.py`'s validator first. See
`core/pdf_renderer.py`'s link callback for the other half of that boundary.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.core.envelope import ApiResponse
from api.core.auth import AuthenticatedUser, get_optional_user
from api.core.pdf_renderer import render_credential_pdf
from api.core.principal import Principal, resolve_principal, require_org_access
from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template
from api.services.templates import (
    build_html_from_config,
    custom_placeholders,
    normalise_config,
    sample_variables,
    validate_template_html,
)

# Mounted under /api/v1 by api/index.py — the prefix here must NOT repeat it,
# or every path ends up served at /api/v1/api/v1/...
router = APIRouter(tags=["Templates"])

WRITE_ROLES = ("owner", "admin")
READ_ROLES = ("owner", "admin", "issuer")


class TemplateWrite(BaseModel):
    """Create or replace a template.

    Exactly one of `html_source` or `config` — a request carrying both is
    ambiguous about which one wins, and guessing is how the two drift apart.
    """

    name: str = Field(..., min_length=1, max_length=255)
    html_source: str | None = None
    config: dict[str, Any] | None = None


class TemplatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    html_source: str | None = None
    config: dict[str, Any] | None = None


class TemplatePreview(BaseModel):
    html_source: str | None = None
    config: dict[str, Any] | None = None


def _summary(t: Template) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "variables": t.variables,
        "is_default": t.is_default,
        # Whether the guided form can reopen this one. The UI needs to know
        # before offering an editor that would overwrite hand-written HTML.
        "is_guided": t.config is not None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _detail(t: Template) -> dict:
    return {**_summary(t), "html_source": t.html_source, "config": t.config}


def _org_or_404(session, slug: str) -> Organization:
    org = session.query(Organization).filter_by(slug=slug).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _owned_template(session, org: Organization, template_id: str) -> Template:
    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    # Filtered by org_id, not just id: without it, any member of any org could
    # read or delete another org's template by guessing a UUID.
    template = session.query(Template).filter_by(id=tid, org_id=org.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


def _resolve_source(
    html_source: str | None, config: dict[str, Any] | None
) -> tuple[str, dict[str, Any] | None]:
    """Turn a write request into (html_source, config), or raise 400.

    The guided path generates HTML and keeps the config. The raw path stores the
    HTML and sets config to None, which is what tells every later reader that
    the guided form must not reopen against it.
    """
    if html_source is not None and config is not None:
        raise HTTPException(
            status_code=400,
            detail="Send either html_source or config, not both — they would disagree.",
        )

    if config is not None:
        normalised = normalise_config(config)
        return build_html_from_config(normalised), normalised

    if html_source is not None:
        errors = validate_template_html(html_source)
        if errors:
            raise HTTPException(status_code=400, detail=" ".join(errors))
        return html_source, None

    raise HTTPException(status_code=400, detail="Provide html_source or config.")


# -- reading ------------------------------------------------------------------

@router.get("/templates", response_model=ApiResponse[list[dict]])
def list_global_templates(user: AuthenticatedUser | None = Depends(get_optional_user)):
    """List globally available default templates."""
    with get_db() as session:
        templates = session.query(Template).filter_by(org_id=None, is_default=True).all()
        return ApiResponse.ok([_summary(t) for t in templates])


@router.get("/orgs/{slug}/templates", response_model=ApiResponse[list[dict]])
def list_org_templates(slug: str, principal: Principal = Depends(resolve_principal)):
    """List an organization's own templates."""
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=READ_ROLES)
        templates = session.query(Template).filter_by(org_id=org.id).all()
        return ApiResponse.ok([_summary(t) for t in templates])


@router.get("/orgs/{slug}/templates/{template_id}", response_model=ApiResponse[dict])
def get_org_template(
    slug: str, template_id: str, principal: Principal = Depends(resolve_principal)
):
    """One template, including its source.

    The list deliberately omits html_source — it can be 256 KB per row. This is
    the route an editor opens with, and until it existed there was no way to
    read back what you had uploaded.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=READ_ROLES)
        return ApiResponse.ok(_detail(_owned_template(session, org, template_id)))


# -- writing ------------------------------------------------------------------

@router.post("/orgs/{slug}/templates", response_model=ApiResponse[dict], status_code=201)
def create_org_template(
    slug: str, payload: TemplateWrite, principal: Principal = Depends(resolve_principal)
):
    """Create a template, from raw HTML or from guided settings.

    The tier gate that used to sit here (403 for `community`) is gone. It made
    the feature unreachable for everyone rather than only for free orgs: billing
    is still mocked, so no customer could reach a paid tier to satisfy it. Re-add
    it when Razorpay actually works.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)

        html_source, config = _resolve_source(payload.html_source, payload.config)

        template = Template(
            org_id=org.id,
            name=payload.name,
            html_source=html_source,
            config=config,
            variables=sorted(custom_placeholders(html_source)),
            is_default=False,
        )
        session.add(template)
        session.flush()
        return ApiResponse.ok(_detail(template))


@router.patch("/orgs/{slug}/templates/{template_id}", response_model=ApiResponse[dict])
def update_org_template(
    slug: str,
    template_id: str,
    payload: TemplatePatch,
    principal: Principal = Depends(resolve_principal),
):
    """Rename a template, or replace its source.

    Sending `html_source` on a guided template clears its config — the HTML is
    now hand-authored and the form would otherwise regenerate over the edit.
    That is a one-way door, and the response says so through `is_guided`.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)
        template = _owned_template(session, org, template_id)

        if payload.name is not None:
            template.name = payload.name

        if payload.html_source is not None or payload.config is not None:
            html_source, config = _resolve_source(payload.html_source, payload.config)
            template.html_source = html_source
            template.config = config
            template.variables = sorted(custom_placeholders(html_source))

        template.updated_at = datetime.now(timezone.utc)
        session.flush()
        return ApiResponse.ok(_detail(template))


@router.delete("/orgs/{slug}/templates/{template_id}", response_model=ApiResponse[dict])
def delete_org_template(
    slug: str, template_id: str, principal: Principal = Depends(resolve_principal)
):
    """Delete a template.

    Credentials keep a template_id, and deleting the row a past credential
    points at would break re-rendering its PDF. Refused rather than cascaded:
    losing the ability to reproduce an issued certificate is not something to
    do on someone's behalf.
    """
    from api.models.credential import Credential

    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)
        template = _owned_template(session, org, template_id)

        in_use = session.query(Credential).filter_by(template_id=template.id).count()
        if in_use:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{in_use} credential(s) were issued with this template. "
                    f"Deleting it would break re-rendering their PDFs."
                ),
            )

        session.delete(template)
        return ApiResponse.ok({"id": template_id, "deleted": True})


@router.post(
    "/orgs/{slug}/templates/{template_id}/default", response_model=ApiResponse[dict]
)
def set_default_template(
    slug: str, template_id: str, principal: Principal = Depends(resolve_principal)
):
    """Make this the template issuance picks when none is named.

    Exclusive: the flag is cleared on the org's other templates in the same
    transaction. resolve_template_id takes the *first* org default it finds, so
    two of them would make the choice depend on row order.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)
        template = _owned_template(session, org, template_id)

        session.query(Template).filter_by(org_id=org.id).update({"is_default": False})
        template.is_default = True
        session.flush()
        return ApiResponse.ok(_summary(template))


@router.post(
    "/orgs/{slug}/templates/import/{global_id}",
    response_model=ApiResponse[dict],
    status_code=201,
)
def import_global_template(
    slug: str, global_id: str, principal: Principal = Depends(resolve_principal)
):
    """Copy a global template into this org as an editable starting point.

    A copy, not a reference: editing must never reach back into a template every
    other org renders from.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)

        try:
            gid = uuid.UUID(global_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid template ID")

        source = session.query(Template).filter_by(id=gid, org_id=None).first()
        if not source:
            raise HTTPException(status_code=404, detail="Global template not found")

        copy = Template(
            org_id=org.id,
            name=f"{source.name} (copy)",
            html_source=source.html_source,
            # Not carried over: a seeded template's config, if it ever gains
            # one, describes the global original. The copy is hand-editable
            # HTML from here.
            config=None,
            variables=sorted(custom_placeholders(source.html_source)),
            is_default=False,
        )
        session.add(copy)
        session.flush()
        return ApiResponse.ok(_detail(copy))


# -- preview ------------------------------------------------------------------

@router.post("/orgs/{slug}/templates/preview")
def preview_template(
    slug: str, payload: TemplatePreview, principal: Principal = Depends(resolve_principal)
):
    """Render a template against sample data and return the PDF.

    Deliberately a PDF and not HTML. The dashboard must never inject
    customer-authored markup into its own document to show a preview — that is
    a stored-XSS hole dressed as a feature. A PDF is inert, and it is also the
    only artefact that proves the template survives xhtml2pdf's narrow CSS
    subset, which an HTML preview would not.

    Nothing is persisted, so this works before a template is saved.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)

        html_source, _ = _resolve_source(payload.html_source, payload.config)

        variables = sample_variables()
        variables["issuer_name"] = org.name
        variables["logo_url"] = org.logo_url or ""
        variables["primary_color"] = org.primary_color or variables["primary_color"]
        variables["accent_color"] = org.accent_color or variables["accent_color"]

    try:
        pdf_bytes = render_credential_pdf(html_source, variables)
    except Exception as exc:
        # The renderer's own failure is the most useful thing an author can be
        # told here — it is usually unsupported CSS, and a generic 500 would
        # send them hunting.
        raise HTTPException(status_code=400, detail=f"Template did not render: {exc}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="template-preview.pdf"'},
    )

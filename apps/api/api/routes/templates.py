"""Templates API endpoints.

A template is authored one of two ways and stored as one thing. `html_source` is
what issuance renders; `config` is the guided form's settings, kept so the form
can be reopened, and dropped the moment the HTML is edited by hand.

Template HTML is customer-supplied and goes into a PDF renderer, so every write
path runs it through `services/templates.py`'s validator first. See
`core/pdf_renderer.py`'s link callback for the other half of that boundary.
"""

import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from api.core.envelope import ApiResponse
from api.core.auth import AuthenticatedUser, get_optional_user
from api.core.pdf_renderer import render_credential_pdf
from api.core.principal import Principal, resolve_principal, require_org_access
from api.core.config import VISION_IMPORTS_PER_MONTH
from api.core.rate_limit import rate_limit
from api.core.storage import StorageError, put_object, storage_available
from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template
from api.models.template_asset import TemplateAsset
from api.services.backgrounds import background_data_uri
from api.services.templates import (
    KIND_TRACED,
    build_html_from_config,
    config_kind,
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

# -- template artwork limits --------------------------------------------------

#: The most we will read off the wire. Enforced by reading one byte past it,
#: never by trusting Content-Length or UploadFile.size, both of which are
#: claims made by the client.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

#: The most we will store after re-encoding. A background is embedded in every
#: PDF rendered from its template, so this is a per-certificate cost, not a
#: one-off.
MAX_STORED_BYTES = 2 * 1024 * 1024

#: A4's long edge at 300dpi. Beyond this is invisible in a PDF and costs bytes
#: on every render.
MAX_STORED_EDGE_PX = 2480

#: Refused before Pillow decodes. Pillow's own decompression-bomb guard is left
#: on as well; this one exists to give a message that names the limit.
MAX_SOURCE_PIXELS = 40_000_000

#: Per org, because an image is not a credential and consume_quota counts
#: credentials. Charging artwork against a certificate allowance would make the
#: two paths disagree about what a quota is.
MAX_ASSETS_PER_ORG = 25
MAX_ASSET_BYTES_PER_ORG = 50 * 1024 * 1024

#: Magic bytes, checked before anything decodes. SVG is deliberately absent: it
#: is markup, it can carry script, and admitting it would defeat the argument
#: that an uploaded image is inert.
_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def _sniff(raw: bytes) -> str | None:
    """The format these bytes actually are, whatever the filename claims."""
    for prefix, mime in _MAGIC:
        if raw.startswith(prefix):
            return mime
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


class TemplateWrite(BaseModel):
    """Create or replace a template.

    Exactly one of `html_source` or `config` — a request carrying both is
    ambiguous about which one wins, and guessing is how the two drift apart.
    """

    name: str = Field(..., min_length=1, max_length=255)
    html_source: str | None = None
    config: dict[str, Any] | None = None
    #: The uploaded artwork this template is drawn on. Must belong to the same
    #: org; see _owned_asset.
    background_asset_id: str | None = None


class TemplatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    html_source: str | None = None
    config: dict[str, Any] | None = None
    background_asset_id: str | None = None


class TemplatePreview(BaseModel):
    html_source: str | None = None
    config: dict[str, Any] | None = None
    background_asset_id: str | None = None


def _summary(t: Template) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "variables": t.variables,
        "is_default": t.is_default,
        # Whether the guided form can reopen this one. The UI needs to know
        # before offering an editor that would overwrite hand-written HTML.
        "is_guided": t.config is not None,
        "background_asset_id": (
            str(t.background_asset_id) if t.background_asset_id else None
        ),
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


def _owned_asset(session, org: Organization, asset_id: str) -> TemplateAsset:
    """Resolve an asset id within this org, or 404.

    Scoped by org_id for the same reason _owned_template is: without it, org A
    could point a template at org B's artwork by guessing a UUID, and every
    certificate it issued would render someone else's design. 404 rather than
    403 — a wrong-org id must not confirm that the asset exists.
    """
    try:
        aid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    asset = session.query(TemplateAsset).filter_by(id=aid, org_id=org.id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Template asset not found")
    return asset


def _check_background_binding(
    html_source: str, config: dict[str, Any] | None, background_asset_id
) -> None:
    """The template's artwork and its HTML must agree that it has artwork.

    Two ways they can disagree, both of which render silently wrong:

      - an asset is bound but the HTML never references {{background}}, so the
        image is stored, paid for, and drawn nowhere;
      - the config says `traced` with no asset, so the generated CSS carries
        `background-image: url("")` and the certificate prints on blank paper.

    Neither raises anywhere downstream. This is the check that makes them an
    error at the moment someone can still fix it.
    """
    has_placeholder = "{{background}}" in html_source

    if background_asset_id is not None and not has_placeholder:
        raise HTTPException(
            status_code=400,
            detail=(
                "This template has background artwork but its HTML never uses "
                "{{background}}, so the image would never be drawn."
            ),
        )

    if config_kind(config) == KIND_TRACED and background_asset_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "A traced template is drawn on uploaded artwork. Upload an "
                "image first and send its background_asset_id."
            ),
        )


def _resolve_source(
    html_source: str | None,
    config: dict[str, Any] | None,
    has_background: bool = False,
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
        generated = build_html_from_config(normalised, has_background)
        # Validated even though we generated it. That was pointless while the
        # generator was a fixed string with a handful of escaped fields; a
        # traced spec carries customer-supplied colours, coordinates and
        # labels, and the generator is now the code most likely to grow a bug
        # that emits a URL or breaks out of a style attribute. The check is
        # free and it fails loudly.
        errors = validate_template_html(generated)
        if errors:
            raise HTTPException(
                status_code=400,
                detail="The generated template is not valid: " + " ".join(errors),
            )
        return generated, normalised

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

        asset = (
            _owned_asset(session, org, payload.background_asset_id)
            if payload.background_asset_id
            else None
        )

        html_source, config = _resolve_source(
            payload.html_source, payload.config, asset is not None
        )
        _check_background_binding(
            html_source, config, asset.id if asset else None
        )

        template = Template(
            org_id=org.id,
            name=payload.name,
            html_source=html_source,
            config=config,
            background_asset_id=asset.id if asset else None,
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

        # An empty string means "unbind"; omitting the field leaves whatever is
        # already there. Distinguishing the two matters — a rename must not
        # silently drop a template's artwork.
        if payload.background_asset_id is not None:
            template.background_asset_id = (
                _owned_asset(session, org, payload.background_asset_id).id
                if payload.background_asset_id
                else None
            )

        if payload.html_source is not None or payload.config is not None:
            html_source, config = _resolve_source(
                payload.html_source,
                payload.config,
                template.background_asset_id is not None,
            )
            template.html_source = html_source
            template.config = config
            template.variables = sorted(custom_placeholders(html_source))

        _check_background_binding(
            template.html_source, template.config, template.background_asset_id
        )

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

        asset = (
            _owned_asset(session, org, payload.background_asset_id)
            if payload.background_asset_id
            else None
        )

        html_source, _ = _resolve_source(
            payload.html_source, payload.config, asset is not None
        )

        # The org goes in whole rather than as four hand-copied keys: branding
        # the preview does not carry is branding the author cannot check, and a
        # field added to build_render_variables would not have reached a copy
        # list here. The artwork is the real artwork for the same reason — a
        # preview drawn on a blank page cannot answer the only question a
        # traced template raises, whether the fields land where the design has
        # room for them.
        background = (
            background_data_uri(_StubTemplate(asset.id, asset))
            if asset is not None
            else ""
        )
        variables = sample_variables(org, background)

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


# -- template artwork ---------------------------------------------------------


class _StubTemplate:
    """Just enough of a Template for background_data_uri to resolve an asset.

    Used by the preview route, which renders artwork that no template row
    references yet. Avoids a second code path for turning an asset into a data
    URI — that function owns the cache, and a bypass around it would not share
    it.
    """

    def __init__(self, asset_id, asset):
        self.id = None
        self.background_asset_id = asset_id
        self.background_asset = asset


def _asset_json(asset: TemplateAsset) -> dict:
    return {
        "id": str(asset.id),
        "mime": asset.mime,
        "width_px": asset.width_px,
        "height_px": asset.height_px,
        "byte_size": asset.byte_size,
        "checksum": asset.checksum,
        # So the canvas can size its page before it has loaded the image.
        "aspect_ratio": round(asset.width_px / asset.height_px, 4)
        if asset.height_px
        else 1.0,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _reencode(raw: bytes) -> tuple[bytes, int, int]:
    """Decode, normalise and re-encode an upload. Raises HTTPException.

    Only the OUTPUT of this function is ever stored, and that is the security
    argument for the whole feature: the stored file is a JPEG this process
    wrote, not a file a stranger uploaded. EXIF, ICC, XMP, PNG ancillary
    chunks, trailing archives and polyglot payloads do not survive a decode and
    re-encode, so none of them reach a PDF we hand to a third party — or an
    <img> tag in the dashboard.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()          # structural check; consumes the file object
        image = Image.open(io.BytesIO(raw))   # so it must be reopened to use
    except UnidentifiedImageError:
        raise HTTPException(status_code=415, detail="That file is not a readable image.")
    except Image.DecompressionBombError:
        raise HTTPException(
            status_code=413, detail="That image is too large to process safely."
        )
    except Exception:
        raise HTTPException(status_code=415, detail="That image could not be read.")

    if image.width * image.height > MAX_SOURCE_PIXELS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"That image is {image.width}x{image.height}. The limit is "
                f"{MAX_SOURCE_PIXELS // 1_000_000} megapixels."
            ),
        )

    if getattr(image, "n_frames", 1) > 1:
        raise HTTPException(
            status_code=415,
            detail="Animated images are not supported — a certificate is one page.",
        )

    # A photo of a printed certificate carries its rotation in EXIF. Applying it
    # here means what the canvas shows and what the PDF prints are the same
    # picture; leaving it means they differ by 90 degrees.
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((MAX_STORED_EDGE_PX, MAX_STORED_EDGE_PX), Image.LANCZOS)

    for quality in (82, 70, 60):
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()
        if len(data) <= MAX_STORED_BYTES:
            return data, image.width, image.height

    raise HTTPException(
        status_code=413,
        detail=(
            f"That image is still over {MAX_STORED_BYTES // (1024 * 1024)} MB after "
            f"compression. Try a smaller or less detailed file."
        ),
    )


@router.post(
    "/orgs/{slug}/template-assets",
    response_model=ApiResponse[dict],
    status_code=201,
    # Its own bucket: this route decodes an image and writes to object storage,
    # which is far more expensive than the rest of the template surface.
    dependencies=[Depends(rate_limit(limit=6, window=60))],
)
async def upload_template_asset(
    slug: str,
    file: UploadFile = File(...),
    principal: Principal = Depends(resolve_principal),
):
    """Upload the artwork a template is drawn on.

    Nothing is stored until every check below has passed.

    The object is written INSIDE the transaction that inserts the row, and
    before it. What actually prevents a row pointing at a missing object is the
    rollback — `get_db` rolls back on any exception, so a failed put can never
    leave a committed row behind. The ordering matters for the narrower case
    the rollback does not cover: writing the object after the transaction
    commits would leave exactly that orphan. Keeping the put inside is the
    whole guarantee; keeping it first is cheap and makes the intent legible.
    """
    if not storage_available():
        raise HTTPException(
            status_code=503,
            detail="Image upload is not available: object storage is not configured.",
        )

    # One byte past the limit, so an oversize file is refused on the strength of
    # what actually arrived rather than what the client said would arrive.
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Images must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    sniffed = _sniff(raw)
    if sniffed is None:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG and WebP images are accepted. SVG is not.",
        )

    stored, width, height = _reencode(raw)
    checksum = hashlib.sha256(stored).hexdigest()

    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)

        existing = (
            session.query(TemplateAsset)
            .filter_by(org_id=org.id, checksum=checksum)
            .first()
        )
        if existing:
            # A double-clicked upload, or the same design re-uploaded. Returning
            # the existing row keeps one asset per image, which is what makes
            # deleting artwork a decidable question.
            return ApiResponse.ok(_asset_json(existing))

        count = session.query(TemplateAsset).filter_by(org_id=org.id).count()
        if count >= MAX_ASSETS_PER_ORG:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This organization already has {count} template images "
                    f"(limit {MAX_ASSETS_PER_ORG}). Delete one first."
                ),
            )
        total = (
            sum(
                a.byte_size
                for a in session.query(TemplateAsset).filter_by(org_id=org.id).all()
            )
            + len(stored)
        )
        if total > MAX_ASSET_BYTES_PER_ORG:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This would exceed the "
                    f"{MAX_ASSET_BYTES_PER_ORG // (1024 * 1024)} MB image allowance."
                ),
            )

        asset_id = uuid.uuid4()
        storage_key = f"orgs/{org.id}/templates/{asset_id}.jpg"

        try:
            put_object(storage_key, stored, "image/jpeg")
        except StorageError as exc:
            raise HTTPException(status_code=502, detail=f"Could not store the image: {exc}")

        asset = TemplateAsset(
            id=asset_id,
            org_id=org.id,
            storage_key=storage_key,
            mime="image/jpeg",
            width_px=width,
            height_px=height,
            byte_size=len(stored),
            checksum=checksum,
            created_by=(
                principal.clerk_user_id
                if not principal.is_api_key
                else f"api_key:{principal.api_key_id}"
            ),
        )
        session.add(asset)
        session.flush()
        return ApiResponse.ok(_asset_json(asset))


@router.get("/orgs/{slug}/template-assets", response_model=ApiResponse[list])
def list_template_assets(slug: str, principal: Principal = Depends(resolve_principal)):
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=READ_ROLES)
        assets = (
            session.query(TemplateAsset)
            .filter_by(org_id=org.id)
            .order_by(TemplateAsset.created_at.desc())
            .all()
        )
        return ApiResponse.ok([_asset_json(a) for a in assets])


@router.get("/orgs/{slug}/template-assets/{asset_id}/image")
def get_template_asset_image(
    slug: str, asset_id: str, principal: Principal = Depends(resolve_principal)
):
    """The stored image, for the canvas to draw fields on.

    Served through the API rather than as a presigned URL: presigning leaks the
    bucket's topology, cannot be revoked once handed out, and makes the browser
    authenticate a second way. The bytes are a JPEG this process re-encoded, and
    `nosniff` with an explicit image content type is what keeps that true for a
    browser that opens the URL directly.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=READ_ROLES)
        asset = _owned_asset(session, org, asset_id)
        storage_key, mime = asset.storage_key, asset.mime

    from api.core.storage import get_object

    try:
        data = get_object(storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the image: {exc}")

    return Response(
        content=data,
        media_type=mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
            # Private: this is one org's artwork behind an auth check, and a
            # shared cache must not hold it.
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/orgs/{slug}/template-assets/{asset_id}", response_model=ApiResponse[dict])
def delete_template_asset(
    slug: str, asset_id: str, principal: Principal = Depends(resolve_principal)
):
    """Delete artwork, unless a template is drawn on it.

    Same rule as delete_org_template, for the same reason: a credential issued
    from a traced template re-renders its PDF on demand, and deleting the image
    would turn every one of those into a blank page.

    The row goes first and the object second. If the object delete fails the row
    is already gone, which leaves an orphan nobody references — the harmless
    direction. Deleting the object first would leave a row pointing at nothing.
    """
    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)
        asset = _owned_asset(session, org, asset_id)

        in_use = (
            session.query(Template).filter_by(background_asset_id=asset.id).count()
        )
        if in_use:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{in_use} template(s) are drawn on this image. "
                    f"Deleting it would break re-rendering their certificates."
                ),
            )

        storage_key = asset.storage_key
        session.delete(asset)
        session.flush()

    from api.core.storage import delete_object

    try:
        delete_object(storage_key)
    except StorageError:
        # Logged by the storage layer. The row is gone, which is what the caller
        # asked for; an object nobody references costs pennies and can be swept.
        pass

    return ApiResponse.ok({"id": asset_id, "deleted": True})


# -- reading a design -----------------------------------------------------------


class TemplateFromImage(BaseModel):
    asset_id: str
    name: str = Field(..., min_length=1, max_length=255)


def _consume_vision_import(session, org: Organization) -> int:
    """Count one design-reading call against this org's month. Returns what is left.

    Its own meter, not `consume_quota`. That one counts credentials; a vision
    call is a paid API request with a different unit and a different cost, and
    putting both through one counter would make "quota exceeded" mean two
    things. A NULL count is a row written before this column existed — read as
    zero, never backfilled, because the row did not count imports rather than
    counting none.
    """
    from api.models.usage import UsageLedger

    period = UsageLedger.current_period()
    ledger = session.query(UsageLedger).filter_by(org_id=org.id, period=period).first()
    if ledger is None:
        ledger = UsageLedger(org_id=org.id, period=period, credentials_issued=0)
        session.add(ledger)
        session.flush()

    used = ledger.vision_imports or 0
    if used >= VISION_IMPORTS_PER_MONTH:
        raise HTTPException(
            status_code=429,
            detail=(
                f"This organization has used its {VISION_IMPORTS_PER_MONTH} design "
                f"readings for this month. You can still place the fields yourself."
            ),
        )

    ledger.vision_imports = used + 1
    return VISION_IMPORTS_PER_MONTH - ledger.vision_imports


@router.post(
    "/orgs/{slug}/templates/from-image",
    response_model=ApiResponse[dict],
    status_code=201,
    # Tighter than the upload it follows: every call is a paid model request.
    dependencies=[Depends(rate_limit(limit=3, window=60))],
)
def create_template_from_image(
    slug: str,
    payload: TemplateFromImage,
    principal: Principal = Depends(resolve_principal),
):
    """Read an uploaded design and create a template with the fields placed.

    Synchronous, and it can take most of a minute. Deferring it to Procrastinate
    would buy a batch table, a polling endpoint and a state machine for a single
    interactive call — worth doing if this routinely exceeds the timeout, not
    before.

    The result is a starting point, never a finished template: everything the
    model returns is clamped by normalise_traced_config and then corrected on
    the canvas. `needs_review` says when the model itself was unsure, which is
    the difference between someone checking every box and someone trusting a
    name printed in the wrong place.
    """
    from api.core.storage import get_object
    from api.services.vision import VisionError, read_layout

    with get_db() as session:
        org = _org_or_404(session, slug)
        require_org_access(principal, str(org.id), allowed_roles=WRITE_ROLES)
        asset = _owned_asset(session, org, payload.asset_id)
        storage_key = asset.storage_key
        # Metered before the call, not after: a failed call still cost money if
        # it reached the model, and a counter that only counts successes is a
        # counter an error loop can walk straight past.
        remaining = _consume_vision_import(session, org)

    try:
        raw = get_object(storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the image: {exc}")

    try:
        result = read_layout(raw)
    except VisionError as exc:
        # No Template row is written on any of these paths. A half-made
        # template that nobody asked for is worse than an error.
        raise HTTPException(status_code=exc.code, detail=exc.message)

    with get_db() as session:
        org = _org_or_404(session, slug)
        asset = _owned_asset(session, org, payload.asset_id)

        html_source, config = _resolve_source(None, result["config"], True)
        _check_background_binding(html_source, config, asset.id)

        template = Template(
            org_id=org.id,
            name=payload.name,
            html_source=html_source,
            config=config,
            background_asset_id=asset.id,
            variables=sorted(custom_placeholders(html_source)),
            is_default=False,
        )
        session.add(template)
        session.flush()

        return ApiResponse.ok(
            {
                **_detail(template),
                "needs_review": result["needs_review"],
                "confidence": result["confidence"],
                "notes": result["notes"],
                "dropped_fields": result["dropped_fields"],
                "imports_remaining": remaining,
            }
        )

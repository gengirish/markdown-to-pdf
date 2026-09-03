"""Verification API endpoints (Public)."""

import base64
import html
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from api.core.config import (
    CERT_BRAND_NAME,
    CERT_ORG_TAGLINE,
    CERTFORGE_API_URL,
    CERTFORGE_WEB_URL,
)
from api.core.credential_signature import (
    INVALID,
    VALID,
    credential_signature_status,
    signature_state,
)
from api.core.envelope import ApiResponse
from api.core.qr import generate_qr_data_uri
from api.core.legacy_tokens import decode_legacy_token, legacy_cert_id
from api.core.crypto import is_certforge_id
from api.core.pdf_renderer import render_credential_pdf
from api.models import get_db
from api.models.credential import Credential, PUBLICLY_VERIFIABLE
from api.models.organization import Organization
from api.models.template import Template
from api.services.issuance import resolve_template_id
from api.services.rendering import build_render_variables
from api.viewer_templates import render_credential_viewer, safe_public_url

logger = logging.getLogger(__name__)

# Mounted under /api/v1 by api/index.py — paths here must NOT repeat that prefix.
router = APIRouter(tags=["Verification"])

# Mounted at the site root: these are the URLs printed on certificates and
# embedded in QR codes, so they must stay short and stable.
public_router = APIRouter(tags=["Verification"])


SIGNATURE_MISMATCH_MESSAGE = (
    "This credential's contents do not match the signature it was issued with."
)


class SignatureMismatch(Exception):
    """A credential whose stored fields no longer match its own signature.

    Deliberately not folded into the "not found" path. A 404 says the ID is
    unknown; this says the ID is known and what the database now holds is not
    what was issued, which is the one outcome an integrity check exists to
    report. Collapsing the two would mean the check ran and told nobody.
    """

    def __init__(self, public_id: str):
        super().__init__(SIGNATURE_MISMATCH_MESSAGE)
        self.public_id = public_id


def _check_signature(cred) -> str:
    """Verify a credential before anything renders it. Returns its status.

    UNVERIFIED passes: those rows predate canonical signing and their
    certificates are already in the world with QR codes on them. They are
    reported as unverified rather than shown as verified — see
    api/core/credential_signature.py.
    """
    status = credential_signature_status(cred)
    if status == INVALID:
        # Worth a log line on its own: reaching here means a credential's row
        # was changed by something that could not re-sign it.
        logger.warning(
            "Credential %s failed signature verification; refusing to serve it.",
            cred.public_id,
        )
        raise SignatureMismatch(cred.public_id)
    return status


def _verified_or_409(cred) -> None:
    """_check_signature for the routes that answer with the bare error body."""
    try:
        _check_signature(cred)
    except SignatureMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _get_credential_data(credential_id: str) -> dict | None:
    """Resolve a credential ID into its data payload (handles legacy and new)."""
    # 1. Check if it's a new DB-backed CertForge credential
    if is_certforge_id(credential_id):
        with get_db() as session:
            cred = session.query(Credential).filter_by(public_id=credential_id).first()
            # Not `== issued`: a claimed credential is still live, and the QR
            # code printed on the certificate must keep resolving after its
            # recipient claims it.
            if not cred or cred.status not in PUBLICLY_VERIFIABLE:
                return None

            signature = signature_state(cred)
            _check_signature(cred)

            # The issuing organization's branding travels with the credential:
            # CertForge is multi-tenant, so the viewer renders the org that
            # issued this credential, never the single CERT_* brand the legacy
            # product reads from the environment.
            org = session.query(Organization).filter_by(id=cred.org_id).first()

            return {
                "source": "database",
                "id": cred.public_id,
                "name": cred.recipient_name,
                "title": cred.title,
                "issued_at": cred.issued_at.isoformat(),
                # What was actually checked, in the caller's own words rather
                # than implied by a 200. `unverified` is not `valid`.
                "signature": signature,
                "pdf_url": f"{CERTFORGE_API_URL}/credentials/{cred.public_id}/pdf",
                "metadata": cred.metadata_,
                "issuer": {
                    "name": org.name if org else None,
                    "slug": org.slug if org else None,
                    "logo_url": org.logo_url if org else None,
                    "primary_color": org.primary_color if org else None,
                    "accent_color": org.accent_color if org else None,
                    "footer_text": org.footer_text if org else None,
                },
            }

    # 2. Check if it's a legacy token payload
    # Legacy routes used the raw HMAC token directly in the URL instead of the short ID.
    # If the credential_id contains a dot, it might be a legacy token.
    if "." in credential_id:
        decoded = decode_legacy_token(credential_id)
        if decoded:
            cid = legacy_cert_id(decoded)
            return {
                "source": "legacy",
                # A legacy certificate is its token: decode_legacy_token
                # returns None unless the HMAC over the whole payload checks
                # out, so reaching this line IS the verification. Reported in
                # the same field as a row signature so a client has one place
                # to look, with the scheme named rather than implied.
                "signature": {
                    "status": VALID,
                    "scheme": "legacy_url_token",
                    "version": None,
                    "covers": ["the entire token payload"],
                },
                "id": cid,
                "name": decoded.get("n", "Unknown"),
                "title": decoded.get("c", decoded.get("r", "Participation Certificate")),
                "issued_at": decoded.get("d", ""),
                "metadata": decoded
            }

    return None

@router.get("/verify/{credential_id}", response_model=ApiResponse[dict])
def verify_api(credential_id: str):
    """JSON API to verify a credential."""
    try:
        data = _get_credential_data(credential_id)
    except SignatureMismatch as exc:
        # Returned here rather than raised as an HTTPException so the reason is
        # machine-readable: the shared handler derives `type` from the status
        # code alone, and "conflict" does not tell an integration that the
        # credential failed verification.
        return JSONResponse(
            status_code=409,
            content=ApiResponse.fail(
                str(exc), code=409, error_type="signature_mismatch"
            ).model_dump(),
        )
    if not data:
        raise HTTPException(status_code=404, detail="Credential not found or invalid signature")
    return ApiResponse.ok(data)

@public_router.get("/credentials/{public_id}/badge.json", response_model=dict)
def get_open_badge_json(public_id: str):
    """Export the credential in Open Badges 3.0 JSON-LD format."""
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=public_id).first()
        # Not `!= revoked`: a pending credential is one the worker has not
        # finished, and it must not export a public Open Badge before it
        # exists as far as the viewer is concerned.
        if not cred or cred.status not in PUBLICLY_VERIFIABLE:
            raise HTTPException(status_code=404, detail="Credential not found or revoked")

        # An Open Badge is the machine-readable assertion itself. Exporting one
        # from a row that does not match its signature would hand a verifier a
        # document saying we vouch for contents we never signed.
        _verified_or_409(cred)

        org = session.query(Organization).filter_by(id=cred.org_id).first()

        # Every URL below addresses CertForge, never the legacy product. This
        # route only ever serves DB-backed CertForge credentials — the query
        # above runs against the Credential table, and a legacy certificate has
        # no row there — so SITE_URL (certs.intelliforge.tech, frozen because
        # every certificate issued under it carries a printed QR code) was the
        # wrong host for both of them.
        #
        # CERTFORGE_WEB_URL rather than CERTFORGE_API_URL because an Open Badges
        # consumer dereferences these to show a person the issuer and the
        # achievement; both are pages on the dashboard, not API resources.
        # achievement.id used to point at /api/v1/credentials/{id}, a route that
        # exists on neither host.

        # Construct Open Badges 3.0 JSON-LD Document
        return {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://purl.imsglobal.org/spec/ob/v3p0/context.json"
            ],
            "id": f"urn:uuid:{cred.public_id}",
            "type": ["VerifiableCredential", "OpenBadgeCredential"],
            "issuer": {
                "id": f"{CERTFORGE_WEB_URL}/orgs/{org.slug}",
                "type": "Profile",
                "name": org.name,
            },
            "issuanceDate": cred.issued_at.isoformat() if cred.issued_at else None,
            "credentialSubject": {
                "type": "AchievementSubject",
                "achievement": {
                    "id": f"{CERTFORGE_WEB_URL}/verify/{cred.public_id}",
                    "type": "Achievement",
                    "name": cred.title,
                    "description": cred.metadata_.get("description", f"Credential for {cred.title}"),
                }
            }
        }

@public_router.get("/credentials/{public_id}/pdf")
def get_credential_pdf(public_id: str):
    """Render a credential's certificate PDF on demand.

    Nothing is stored: every request re-renders from the template and the
    credential's own data, the same way badge.json is generated fresh rather
    than cached. This is what makes the viewer's "Download PDF" button work —
    it used to link at cred.pdf_url, a column nothing has ever populated.
    """
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=public_id).first()
        if not cred or cred.status not in PUBLICLY_VERIFIABLE:
            raise HTTPException(status_code=404, detail="Credential not found or revoked")

        # The PDF is the artefact people print and hand over. It is the last
        # place to serve unverified contents.
        _verified_or_409(cred)

        org = session.query(Organization).filter_by(id=cred.org_id).first()

        template_id = cred.template_id or resolve_template_id(session, org, None)
        if template_id is None:
            raise HTTPException(status_code=404, detail="No template available")
        template = session.query(Template).filter_by(id=template_id).first()
        if template is None:
            raise HTTPException(status_code=404, detail="No template available")

        # metadata_ wins for custom keys, same precedence as bulk issuance in
        # api/core/worker.py — the two must never again build this dict two
        # different ways.
        variables = dict(cred.metadata_)
        # `template` is passed because the variable builder needs it to resolve
        # the traced-template artwork. The bulk worker passes it too; a
        # credential must not carry its background through one path and lose it
        # through the other — this route is the one a printed QR code reaches.
        variables.update(build_render_variables(cred, org, template))

        pdf_bytes = render_credential_pdf(template.html_source, variables)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{public_id}.pdf"'},
    )


@public_router.get("/credentials/{public_id}/qr.png")
def get_credential_qr_png(public_id: str):
    """The verification QR as a fetchable PNG.

    The viewer embeds the same QR as a data: URI, which is fine for a browser
    and useless to a link crawler — LinkedIn, WhatsApp and Slack fetch og:image
    over HTTP. This is that URL, and it is a real image of this credential
    rather than a placeholder pointing at a file nobody serves.

    Sits under /credentials/ deliberately: that prefix is already in
    vercel.json's rewrite list and already excluded from the dashboard's Clerk
    middleware, so it needs no routing change to work in production.
    """
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=public_id).first()
        if not cred or cred.status not in PUBLICLY_VERIFIABLE:
            raise HTTPException(status_code=404, detail="Credential not found or revoked")

    data_uri = generate_qr_data_uri(f"{CERTFORGE_WEB_URL}/verify/{public_id}")
    png = base64.b64decode(data_uri.split(",", 1)[1])
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@public_router.get("/orgs/{slug}")
def issuer_profile(slug: str, request: Request):
    """Public issuer profile — the target of every badge's `issuer.id`.

    Open Badges 3.0 treats `issuer.id` as a dereferenceable URL: a consumer
    fetches it to find out who issued the thing. Until this existed the badge
    validated structurally and failed in use, because nothing served the URL it
    named — on this host or any other. A rewrite could not fix that; there was
    no target to rewrite to.

    Deliberately NOT `/org/{slug}`. That namespace is the signed-in dashboard
    and `apps/web/proxy.ts` protects it, so an issuer.id there would answer a
    badge consumer with a sign-in redirect. Plural is public, singular is
    private, and the two must not be merged.

    Content-negotiated because both kinds of client dereference this same URL:
    a validator sends `Accept: application/json` and needs the Profile, a person
    follows the link from a certificate and needs a page.
    """
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        profile_id = f"{CERTFORGE_WEB_URL}/orgs/{org.slug}"
        name = org.name
        logo_url = org.logo_url

    accept = request.headers.get("accept", "")
    wants_json = ("json" in accept) and ("text/html" not in accept)

    if wants_json:
        profile = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://purl.imsglobal.org/spec/ob/v3p0/context.json",
            ],
            "id": profile_id,
            "type": "Profile",
            "name": name,
        }
        # Omitted rather than sent as null: an Open Badges consumer renders an
        # `image` key if it is present, and a null one is a broken image.
        if logo_url:
            profile["image"] = logo_url
        return JSONResponse(profile, media_type="application/ld+json")

    # Organization names are customer-supplied and land on a public page, so
    # they are escaped for the same reason recipient names are below.
    safe_name = html.escape(str(name))
    safe_slug = html.escape(str(slug))

    logo_img = ""
    if logo_url and str(logo_url).startswith(("https://", "http://", "/")):
        logo_img = (
            f'<img src="{html.escape(str(logo_url))}" alt="" class="logo">'
        )

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{safe_name} - Credential Issuer</title>
        <link rel="alternate" type="application/ld+json" href="{html.escape(profile_id)}">
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; margin: 0; padding: 2rem; color: #0f172a; text-align: center; }}
            .card {{ background: white; max-width: 600px; margin: 0 auto; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border: 1px solid #e2e8f0; }}
            .logo {{ max-height: 64px; max-width: 200px; margin-bottom: 1rem; }}
            h1 {{ color: #1e293b; font-size: 1.5rem; margin-bottom: 0.5rem; }}
            .badge {{ display: inline-flex; align-items: center; background: #e0f2fe; color: #075985; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; margin-bottom: 1.5rem; border: 1px solid #bae6fd; }}
            .field {{ margin-bottom: 1rem; text-align: left; }}
            .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; margin-bottom: 0.25rem; }}
            .value {{ font-size: 1.125rem; font-weight: 500; color: #0f172a; }}
            .note {{ font-size: 0.8125rem; color: #64748b; margin-top: 1.5rem; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            {logo_img}
            <div class="badge">Credential Issuer</div>
            <h1>{safe_name}</h1>
            <div class="field">
                <div class="label">Issuer ID</div>
                <div class="value" style="font-family: monospace; font-size: 0.9375rem; word-break: break-all;">{safe_slug}</div>
            </div>
            <p class="note">
                This organization issues verifiable credentials. Each one carries a
                link that confirms it against this issuer.
            </p>
        </div>
    </body>
    </html>
    """)


@public_router.get("/verify/{credential_id}", response_class=HTMLResponse)
async def verify_page(credential_id: str, request: Request):
    """HTML public viewer for a credential."""
    try:
        data = _get_credential_data(credential_id)
    except SignatureMismatch:
        # A person is reading this one, so it answers in HTML — and says which
        # of the two failures happened, rather than the generic 404 below.
        return HTMLResponse(
            "<h1>Credential Could Not Be Verified</h1>"
            f"<p>{html.escape(SIGNATURE_MISMATCH_MESSAGE)}</p>",
            status_code=409,
        )
    if not data:
        return HTMLResponse(
            "<h1>Invalid or Revoked Credential</h1><p>This credential could not be verified.</p>",
            status_code=404,
        )

    # Legacy tokens already have a full viewer at /certificate/{token} — QR
    # codes, share links, JSON-LD, branding and per-kind layouts. Render through
    # that instead of re-formatting the templates here: the local copy passed a
    # different set of placeholders than the templates declare and raised
    # KeyError('meta_description') on every legacy internship certificate.
    if data["source"] == "legacy":
        from api.index import view_certificate

        return await view_certificate(credential_id, request)

    # Recipient names and credential titles arrive from customer-uploaded CSVs
    # and land on a public page, so they are attacker-controlled. Escaping —
    # along with the URL scheme check that escaping cannot do, and the colour
    # allowlist that protects the <style> block — all lives in
    # api/viewer_templates.py, so there is one place to audit it rather than
    # one per interpolation.
    cred_id = str(data["id"])
    page_url = f"{CERTFORGE_WEB_URL}/verify/{cred_id}"
    issuer = data.get("issuer") or {}
    issuer_slug = issuer.get("slug")

    # Multi-tenant: the header carries the issuing organization. CERT_BRAND_NAME
    # / CERT_ORG_TAGLINE are the legacy product's single brand and are used only
    # when a credential has no org at all.
    issuer_name = issuer.get("name") or CERT_BRAND_NAME

    # og:image has to be a URL a crawler can fetch, so a data: URI is no use
    # here even though the page itself embeds the QR that way. An org logo is
    # the best unfurl image when there is one; otherwise the QR PNG endpoint
    # below, which is a real image of this specific credential rather than a
    # link to something that does not exist.
    og_image = (
        safe_public_url(issuer.get("logo_url"))
        or f"{CERTFORGE_API_URL}/credentials/{cred_id}/qr.png"
    )

    return HTMLResponse(
        render_credential_viewer(
            recipient_name=str(data["name"]),
            title=str(data["title"]),
            issued_at=str(data["issued_at"]),
            credential_id=cred_id,
            page_url=page_url,
            badge_url=f"{CERTFORGE_API_URL}/credentials/{cred_id}/badge.json",
            qr_data_uri=generate_qr_data_uri(page_url),
            issuer_name=issuer_name,
            issuer_url=f"{CERTFORGE_WEB_URL}/orgs/{issuer_slug}" if issuer_slug else "",
            # Only the legacy single-brand case has an eyebrow line. When a
            # real organization issued the credential this used to be the
            # literal "Verified Credential" — the same words as the badge two
            # rows below it, so every org's page said it twice. Empty drops
            # the row.
            issuer_tagline=CERT_ORG_TAGLINE if not issuer.get("name") else "",
            pdf_url=data.get("pdf_url") or "",
            og_image=og_image,
            logo_url=issuer.get("logo_url"),
            primary_color=issuer.get("primary_color"),
            accent_color=issuer.get("accent_color"),
            footer_text=issuer.get("footer_text"),
        )
    )

"""Verification API endpoints (Public)."""

import html

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.core.config import CERTFORGE_WEB_URL
from api.core.envelope import ApiResponse
from api.core.legacy_tokens import decode_legacy_token, legacy_cert_id
from api.core.crypto import is_certforge_id
from api.models import get_db
from api.models.credential import Credential, PUBLICLY_VERIFIABLE
from api.models.organization import Organization

# Mounted under /api/v1 by api/index.py — paths here must NOT repeat that prefix.
router = APIRouter(tags=["Verification"])

# Mounted at the site root: these are the URLs printed on certificates and
# embedded in QR codes, so they must stay short and stable.
public_router = APIRouter(tags=["Verification"])


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

            return {
                "source": "database",
                "id": cred.public_id,
                "name": cred.recipient_name,
                "title": cred.title,
                "issued_at": cred.issued_at.isoformat(),
                "pdf_url": cred.pdf_url,
                "metadata": cred.metadata_
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
    data = _get_credential_data(credential_id)
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
    data = _get_credential_data(credential_id)
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
    # and land on a public page, so they are attacker-controlled and every one
    # of them is escaped before it reaches the markup. This stays an f-string
    # rather than becoming a Jinja2 template with autoescaping: Jinja2 is not in
    # requirements.txt and the container installs nothing beyond it, so
    # templating would mean taking on a runtime dependency for a page that is
    # one card with four fields.
    name = html.escape(str(data["name"]))
    title = html.escape(str(data["title"]))
    issued_at = html.escape(str(data["issued_at"]))
    cred_id = html.escape(str(data["id"]))

    # The button used to link to /api/v1/verify/{id}/download, a route that has
    # never existed and 404s. A credential carries the URL of its rendered PDF
    # once one has been stored; with nothing stored there is nothing to offer,
    # so the button is omitted rather than pointed at a dead end. The scheme
    # check does what escaping cannot: html.escape would pass a `javascript:`
    # URL straight through into the href.
    pdf_url = data.get("pdf_url") or ""
    download_btn = ""
    if pdf_url.startswith(("https://", "http://", "/")):
        download_btn = f'<a href="{html.escape(pdf_url)}" class="download-btn">Download PDF</a>'

    # Generic viewer for new templates
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Verified Credential</title>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; margin: 0; padding: 2rem; color: #0f172a; text-align: center; }}
            .card {{ background: white; max-width: 600px; margin: 0 auto; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border: 1px solid #e2e8f0; }}
            h1 {{ color: #1e293b; font-size: 1.5rem; margin-bottom: 0.5rem; }}
            .verified {{ display: inline-flex; align-items: center; background: #dcfce7; color: #166534; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; margin-bottom: 1.5rem; border: 1px solid #bbf7d0; }}
            .field {{ margin-bottom: 1rem; text-align: left; }}
            .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; margin-bottom: 0.25rem; }}
            .value {{ font-size: 1.125rem; font-weight: 500; color: #0f172a; }}
            .download-btn {{ display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 0.75rem 1.5rem; border-radius: 8px; font-weight: 600; margin-top: 1.5rem; transition: background 0.2s; }}
            .download-btn:hover {{ background: #2563eb; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="verified">
                <svg style="width: 16px; height: 16px; margin-right: 4px;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                Verified Authentic
            </div>
            <h1>{name}</h1>
            <div class="field">
                <div class="label">Credential Name</div>
                <div class="value">{title}</div>
            </div>
            <div class="field">
                <div class="label">Issued Date</div>
                <div class="value">{issued_at}</div>
            </div>
            <div class="field">
                <div class="label">Credential ID</div>
                <div class="value" style="font-family: monospace;">{cred_id}</div>
            </div>

            {download_btn}
        </div>
    </body>
    </html>
    """)

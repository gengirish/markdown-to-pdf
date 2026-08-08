"""Verification API endpoints (Public)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.core.envelope import ApiResponse
from api.core.legacy_tokens import decode_legacy_token, legacy_cert_id, is_internship_payload, is_appreciation_payload
from api.core.crypto import is_certforge_id
from api.core.pdf_renderer import render_credential_pdf
from api.models import get_db
from api.models.credential import Credential
from api.certificate_templates import VIEWER_INTERNSHIP_HTML, VIEWER_APPRECIATION_HTML

router = APIRouter(tags=["Verification"])

def _get_credential_data(credential_id: str) -> dict | None:
    """Resolve a credential ID into its data payload (handles legacy and new)."""
    # 1. Check if it's a new DB-backed CertForge credential
    if is_certforge_id(credential_id):
        with get_db() as session:
            cred = session.query(Credential).filter_by(public_id=credential_id).first()
            if not cred or cred.status != "issued":
                return None
                
            return {
                "source": "database",
                "id": cred.public_id,
                "name": cred.recipient_name,
                "title": cred.title,
                "issued_at": cred.issued_at.isoformat(),
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

@router.get("/api/v1/verify/{credential_id}", response_model=ApiResponse[dict])
def verify_api(credential_id: str):
    """JSON API to verify a credential."""
    data = _get_credential_data(credential_id)
    if not data:
        raise HTTPException(status_code=404, detail="Credential not found or invalid signature")
    return ApiResponse.ok(data)

@router.get("/credentials/{public_id}/badge.json", response_model=dict)
def get_open_badge_json(public_id: str):
    """Export the credential in Open Badges 3.0 JSON-LD format."""
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=public_id).first()
        if not cred or cred.status == "revoked":
            raise HTTPException(status_code=404, detail="Credential not found or revoked")
            
        org = session.query(Organization).filter_by(id=cred.org_id).first()
        
        # Construct Open Badges 3.0 JSON-LD Document
        return {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://purl.imsglobal.org/spec/ob/v3p0/context.json"
            ],
            "id": f"urn:uuid:{cred.public_id}",
            "type": ["VerifiableCredential", "OpenBadgeCredential"],
            "issuer": {
                "id": f"https://certs.intelliforge.tech/orgs/{org.slug}",
                "type": "Profile",
                "name": org.name,
            },
            "issuanceDate": cred.issued_at.isoformat() if cred.issued_at else None,
            "credentialSubject": {
                "type": "AchievementSubject",
                "achievement": {
                    "id": f"https://certs.intelliforge.tech/api/v1/credentials/{cred.public_id}",
                    "type": "Achievement",
                    "name": cred.title,
                    "description": cred.metadata_.get("description", f"Credential for {cred.title}"),
                }
            }
        }

@router.get("/verify/{credential_id}", response_class=HTMLResponse)
def verify_page(credential_id: str):
    """HTML public viewer for a credential."""
    data = _get_credential_data(credential_id)
    if not data:
        return HTMLResponse("<h1>Invalid or Revoked Credential</h1><p>This credential could not be verified.</p>", status_code=404)
        
    # Phase 1: Simple HTML viewer
    # We use legacy viewer templates for legacy credentials if we can
    if data["source"] == "legacy":
        meta = data["metadata"]
        if is_internship_payload(meta):
            from api.index import _generate_qr_data_uri, _internship_pdf_signatures_block, FOUNDER_NAME
            verify_url = f"https://certs.intelliforge.tech/verify/{credential_id}"
            
            return HTMLResponse(VIEWER_INTERNSHIP_HTML.format(
                participant_name=meta.get("n", ""),
                course_name=meta.get("c", ""),
                completion_date=meta.get("d", ""),
                instructor_name=meta.get("i", ""),
                mentor_name=meta.get("m", ""),
                usn=meta.get("u", ""),
                duration_text=meta.get("w", ""),
                hours_text=meta.get("h", ""),
                certificate_id=data["id"],
                download_url=f"/certificate/{credential_id}/download",
            ))
        elif is_appreciation_payload(meta):
            return HTMLResponse(VIEWER_APPRECIATION_HTML.format(
                participant_name=meta.get("n", ""),
                recognition_text=meta.get("r", ""),
                completion_date=meta.get("d", ""),
                certificate_id=data["id"],
                download_url=f"/certificate/{credential_id}/download",
            ))

    # Generic viewer for new templates
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{data['title']} - Verified Credential</title>
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
            <h1>{data['name']}</h1>
            <div class="field">
                <div class="label">Credential Name</div>
                <div class="value">{data['title']}</div>
            </div>
            <div class="field">
                <div class="label">Issued Date</div>
                <div class="value">{data['issued_at']}</div>
            </div>
            <div class="field">
                <div class="label">Credential ID</div>
                <div class="value" style="font-family: monospace;">{data['id']}</div>
            </div>
            
            <a href="/api/v1/verify/{data['id']}/download" class="download-btn">Download PDF</a>
        </div>
    </body>
    </html>
    """)

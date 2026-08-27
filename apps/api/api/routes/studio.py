"""Credential Studio API endpoints."""

import csv
import uuid
import codecs
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from api.core.envelope import ApiResponse
from api.core.principal import Principal, resolve_principal, require_org_access
from api.core.crypto import generate_credential_id, hmac_sign
from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template
from api.models.credential import Credential, CredentialBatch
from api.core.worker import process_batch

# Mounted under /api/v1 by api/index.py — the prefix here must NOT repeat it,
# or every path ends up served at /api/v1/api/v1/...
router = APIRouter(prefix="/orgs", tags=["Studio"])

@router.post("/{slug}/credentials/bulk", response_model=ApiResponse[dict])
async def upload_bulk_csv(
    slug: str,
    template_id: str = Form(...),
    file: UploadFile = File(...),
    principal: Principal = Depends(resolve_principal)
):
    """Upload a CSV to bulk-issue credentials."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        try:
            tid = uuid.UUID(template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid template ID")
            
        template = session.query(Template).filter(
            Template.id == tid,
            (Template.org_id == org.id) | (Template.org_id == None)
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found or not accessible")

        # Parse CSV
        content = await file.read()
        try:
            reader = csv.DictReader(codecs.iterdecode(content.splitlines(), 'utf-8'))
            rows = list(reader)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid CSV format")
            
        if not rows:
            raise HTTPException(status_code=400, detail="CSV is empty")

        # Basic validation
        for i, row in enumerate(rows):
            if "name" not in row or not row["name"].strip():
                raise HTTPException(status_code=400, detail=f"Row {i+1} is missing 'name'")
            if "title" not in row or not row["title"].strip():
                raise HTTPException(status_code=400, detail=f"Row {i+1} is missing 'title'")

        # Create batch
        from datetime import datetime
        from api.models.usage import UsageLedger
        current_period = datetime.utcnow().strftime("%Y-%m")
        ledger = session.query(UsageLedger).filter_by(org_id=org.id, period=current_period).first()
        used = ledger.credentials_issued if ledger else 0
        if used + len(rows) > org.monthly_quota:
            raise HTTPException(status_code=402, detail=f"Quota exceeded. Available: {org.monthly_quota - used}, Requested: {len(rows)}")

        batch = CredentialBatch(
            org_id=org.id,
            template_id=template.id,
            csv_filename=file.filename or "upload.csv",
            total=len(rows),
            status="pending",
            # An API key has no person behind it, so record the key instead
            # of inventing a user id. Either way the batch is attributable.
            created_by=(
                principal.clerk_user_id
                if not principal.is_api_key
                else f"api_key:{principal.api_key_id}"
            )
        )
        session.add(batch)
        session.flush()

        # Insert pending credentials
        creds = []
        for row in rows:
            public_id = generate_credential_id()
            # Sign the basic payload to ensure authenticity if verified via legacy ways,
            # though new credentials should be verified by DB lookup.
            # We still need a signature per DB schema.
            signature = hmac_sign(public_id)
            
            cred = Credential(
                public_id=public_id,
                org_id=org.id,
                batch_id=batch.id,
                template_id=template.id,
                recipient_name=row["name"].strip(),
                recipient_email=row.get("email", "").strip(),
                title=row["title"].strip(),
                metadata_=dict(row),
                hmac_signature=signature,
                status="pending"
            )
            creds.append(cred)
            
        session.bulk_save_objects(creds)
        
    # Trigger background worker task
    # We must await the task dispatch
    import asyncio
    asyncio.create_task(process_batch.defer_async(batch_id_str=str(batch.id)))

    return ApiResponse.ok({
        "batch_id": str(batch.id),
        "total": batch.total,
        "status": batch.status
    })

@router.get("/{slug}/batches/{batch_id}", response_model=ApiResponse[dict])
def get_batch_status(
    slug: str,
    batch_id: str,
    principal: Principal = Depends(resolve_principal)
):
    """Check the status of a bulk issuance batch."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        try:
            bid = uuid.UUID(batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid batch ID")
            
        batch = session.query(CredentialBatch).filter_by(id=bid, org_id=org.id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        return ApiResponse.ok({
            "id": str(batch.id),
            "status": batch.status,
            "total": batch.total,
            "succeeded": batch.succeeded,
            "failed": batch.failed,
            "error_report": batch.error_report,
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None
        })

@router.get("/{slug}/credentials", response_model=ApiResponse[dict])
def list_org_credentials(
    slug: str,
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(resolve_principal)
):
    """List credentials issued by the organization."""
    with get_db() as session:
        org = session.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        require_org_access(principal, str(org.id), allowed_roles=("owner", "admin", "issuer"))
        
        query = session.query(Credential).filter_by(org_id=org.id).order_by(Credential.issued_at.desc())
        total = query.count()
        creds = query.limit(limit).offset(offset).all()
        
        data = [{
            "id": c.public_id,
            "recipient_name": c.recipient_name,
            "recipient_email": c.recipient_email,
            "title": c.title,
            "status": c.status,
            "issued_at": c.issued_at.isoformat(),
            "batch_id": str(c.batch_id) if c.batch_id else None
        } for c in creds]
        
        return ApiResponse.ok({
            "items": data,
            "total": total,
            "limit": limit,
            "offset": offset
        })

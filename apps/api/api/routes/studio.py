"""Credential Studio API endpoints."""

import csv
import uuid
import codecs
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from api.core.envelope import ApiResponse
from api.core.principal import Principal, resolve_principal, require_org_access
from api.core.credential_signature import sign_credential
from api.core.crypto import generate_credential_id
from api.models import get_db
from api.models.organization import Organization
from api.models.template import Template
from api.models.credential import Credential, CredentialBatch
from api.core.worker import process_batch
from api.services.issuance import QuotaExceeded, consume_quota

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

        # Quota is CONSUMED here, not merely inspected. This read the ledger and
        # never wrote it back, so bulk issuance was unmetered: fifty credentials
        # against a fifty quota left the counter at zero and you could do it
        # again immediately. Single issuance metered correctly the whole time,
        # which made it worse — the two paths disagreed about what a quota was.
        #
        # Through consume_quota rather than a second inline implementation, for
        # the same reason both issuance paths now share one email sender. It
        # also retires a duplicate period calculation: this used
        # datetime.utcnow().strftime("%Y-%m") while the ledger's own writer uses
        # UsageLedger.current_period(), and nothing kept the two in step.
        try:
            consume_quota(session, org, len(rows))
        except QuotaExceeded as exc:
            raise HTTPException(status_code=exc.code, detail=exc.message)

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

            cred = Credential(
                public_id=public_id,
                org_id=org.id,
                batch_id=batch.id,
                template_id=template.id,
                recipient_name=row["name"].strip(),
                recipient_email=row.get("email", "").strip(),
                title=row["title"].strip(),
                metadata_=dict(row),
                hmac_signature="",
                status="pending",
                # Set explicitly rather than left to the column default: the
                # signature covers issued_at, and a default applied at flush
                # time would land after signing, so the staged row would carry
                # a signature over a timestamp it does not have.
                issued_at=datetime.now(timezone.utc),
            )
            # Signed here and signed again in the worker, which rewrites
            # issued_at when the render succeeds. Signing only once, in either
            # place, leaves a window where the row's signature does not match
            # its own fields.
            sign_credential(cred)
            creds.append(cred)
            
        session.bulk_save_objects(creds)

        # Queued INSIDE the transaction and awaited, so a batch row cannot be
        # committed without a job to run it.
        #
        # This was asyncio.create_task(...) after the commit, which fails three
        # ways: the task is never awaited so its exception is swallowed, the
        # task object is unreferenced so it can be garbage-collected mid-flight,
        # and the Fly machine scales to zero after the response — potentially
        # before an un-awaited coroutine ever reaches Postgres. Any of those
        # left a committed batch with status="pending" and no job, and nothing
        # reconciles that: there is no reaper, and a batch that will never run
        # is indistinguishable from one about to start.
        #
        # Ordering is deliberate. If the enqueue raises, this propagates and
        # get_db rolls the batch back, so the caller gets an error and can
        # retry against a clean slate. The opposite failure — job queued, then
        # the commit fails — leaves an orphan job, which the worker already
        # handles by logging "not found or not pending" and returning. An
        # orphan job is recoverable noise; an orphan batch is a silent hang.
        await process_batch.defer_async(batch_id_str=str(batch.id))

        # Read while the row is still attached to a live session.
        result = {
            "batch_id": str(batch.id),
            "total": batch.total,
            "status": batch.status,
        }

    return ApiResponse.ok(result)

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
            # succeeded/failed count RENDERS. Reading them as "people who got
            # their credential" is how a batch that emailed nobody was reported
            # as a complete success. delivery answers the other question.
            "succeeded": batch.succeeded,
            "failed": batch.failed,
            "delivery": {
                "delivered": batch.delivered,
                "failed": batch.delivery_failed,
                # Neither delivered nor failed: no address on the row, or the
                # upload did not ask for delivery. Stated rather than left to be
                # inferred from a subtraction.
                "not_requested": max(
                    0, batch.succeeded - batch.delivered - batch.delivery_failed
                ),
            },
            "error_report": batch.error_report,
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None
        })

# GET /orgs/{slug}/credentials now lives in routes/credentials.py, alongside
# issuing and revoking. It was defined here as well, and FastAPI silently served
# whichever router registered first — so the endpoint you got depended on import
# order in index.py. One resource, one handler.

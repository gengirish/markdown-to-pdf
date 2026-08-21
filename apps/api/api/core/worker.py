"""
Procrastinate background worker setup for CertForge.

Handles asynchronous bulk certificate issuance.
Runs embedded inside the FastAPI lifespan so it scales alongside the webserver.
"""

import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
import logging
import os
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import procrastinate

from api.core.config import DATABASE_URL
from api.models import get_db
from api.models.credential import CredentialBatch, Credential
from api.models.template import Template
from api.core.pdf_renderer import render_credential_pdf
from api.core.crypto import hmac_sign, generate_credential_id
from api.core.email import agentmail_deliver

logger = logging.getLogger(__name__)

# Initialize Procrastinate App
worker_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=DATABASE_URL)
)

# Applying the queue schema is DDL. It belongs in the once-per-deploy release
# step (api/release.py), not on a wake path that runs every time Fly autostarts
# the machine. Set PROCRASTINATE_APPLY_SCHEMA=1 only for local/dev bootstraps.
APPLY_SCHEMA_ON_BOOT = os.environ.get("PROCRASTINATE_APPLY_SCHEMA", "0") == "1"

# Without DATABASE_URL there is nothing to connect to, and opening the app would
# raise on boot. Keep the API serving its stateless routes instead.
WORKER_ENABLED = bool(os.environ.get("DATABASE_URL", ""))


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan to manage Procrastinate worker."""
    if not WORKER_ENABLED:
        logger.warning("DATABASE_URL not set — background worker disabled.")
        yield
        return

    async with worker_app.open_async():
        if APPLY_SCHEMA_ON_BOOT:
            logger.info("PROCRASTINATE_APPLY_SCHEMA=1 — applying queue schema on boot.")
            await worker_app.schema_manager.apply_schema_async()

        # Start the worker in the background.
        #
        # procrastinate.Worker is not part of the public API (it moved out of the
        # top-level namespace and importing it raised AttributeError on boot).
        # run_worker_async is the supported in-process entry point. Signal
        # handlers stay off because uvicorn owns SIGINT/SIGTERM here — letting
        # procrastinate install its own would swallow Fly's shutdown signal.
        worker_task = asyncio.create_task(
            worker_app.run_worker_async(
                name="fastapi_worker",
                install_signal_handlers=False,
            )
        )
        logger.info("Procrastinate background worker started in FastAPI lifespan")

        try:
            yield
        finally:
            # This runs when Fly stops the machine on idle. Closing cleanly drops
            # the LISTEN/NOTIFY connection to Neon, which is what lets Neon
            # compute autosuspend instead of billing around the clock.
            logger.info("Stopping Procrastinate worker...")
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


@worker_app.task(queue="issuance")
async def process_batch(batch_id_str: str):
    """Background task to process a CredentialBatch."""
    # We must run DB synchronous code in a thread pool since this task is async,
    # or just use loop.run_in_executor
    import uuid

    batch_id = uuid.UUID(batch_id_str)
    
    # Run sync code in thread
    await asyncio.to_thread(_process_batch_sync, batch_id)


def _process_batch_sync(batch_id: uuid.UUID):
    """Synchronous core logic for processing a batch."""
    logger.info(f"Processing batch {batch_id}")
    import csv
    from io import StringIO
    import time
    
    with get_db() as session:
        batch = session.query(CredentialBatch).filter_by(id=batch_id).first()
        if not batch or batch.status != "pending":
            logger.warning(f"Batch {batch_id} not found or not pending.")
            return

        batch.status = "processing"
        session.commit()

        template = session.query(Template).filter_by(id=batch.template_id).first()
        if not template:
            batch.status = "failed"
            batch.error_report = {"error": "Template not found"}
            session.commit()
            return

        # Fetch pending credentials for this batch
        # Wait, in the studio, the user uploads CSV, we can either parse it in the route
        # and create `Credential` rows with status="pending", OR we store the CSV in S3
        # and process it here. Since Phase 1 focuses on infrastructure, and we don't have
        # S3 set up, storing pending `Credential` rows during the route upload is best.
        
        pending_creds = session.query(Credential).filter_by(batch_id=batch.id, status="pending").all()
        
        success_count = 0
        failed_count = 0
        errors = {}

        for cred in pending_creds:
            try:
                # 1. Render PDF
                variables = dict(cred.metadata_)
                variables["name"] = cred.recipient_name
                variables["title"] = cred.title
                variables["credential_id"] = cred.public_id
                
                # We need the verify URL for the QR code
                verify_url = f"https://certs.intelliforge.tech/verify/{cred.public_id}"
                from api.core.qr import generate_qr_data_uri
                variables["qr"] = generate_qr_data_uri(verify_url)
                
                pdf_bytes = render_credential_pdf(template.html_source, variables)
                
                # 2. Upload PDF (mocked for now since R2/S3 is deferred to later)
                # In Phase 1 we might still just serve it dynamically or store temporarily.
                # Actually, CertForge generates PDFs on the fly for verification. 
                # For now, we leave pdf_url as None and generate on-the-fly.
                
                # 3. Send Email
                if cred.recipient_email:
                    # In Phase 1, we use AgentMail
                    from api.core.config import CERT_BRAND_NAME
                    
                    # Very simple email template for Phase 1
                    html_content = f"""
                    <h2>Your Credential from {CERT_BRAND_NAME}</h2>
                    <p>Hi {cred.recipient_name},</p>
                    <p>Your credential for <strong>{cred.title}</strong> is ready.</p>
                    <p>View it here: <a href="{verify_url}">{verify_url}</a></p>
                    """
                    
                    success, msg = agentmail_deliver(
                        to_email=cred.recipient_email,
                        subject=f"Your credential for {cred.title}",
                        text=f"Your credential is ready. View it here: {verify_url}",
                        html=html_content
                    )
                    if not success:
                        logger.warning(f"Email failed for {cred.recipient_email}: {msg}")
                
                cred.status = "issued"
                cred.issued_at = datetime.now(timezone.utc)
                success_count += 1
                
            except Exception as e:
                logger.error(f"Error processing credential {cred.id}: {e}")
                cred.status = "failed"
                errors[cred.public_id] = str(e)
                failed_count += 1
            
            # Commit every 10 credentials to show progress
            if (success_count + failed_count) % 10 == 0:
                batch.succeeded = success_count
                batch.failed = failed_count
                session.commit()
                # small delay to prevent DB hammering
                time.sleep(0.1)

        batch.succeeded = success_count
        batch.failed = failed_count
        batch.status = "completed" if failed_count == 0 else "completed_with_errors"
        batch.completed_at = datetime.now(timezone.utc)
        batch.error_report = errors if errors else None
        session.commit()
        
        logger.info(f"Batch {batch_id} completed: {success_count} succeeded, {failed_count} failed.")

        # Dispatch Webhooks
        try:
            from api.models.api_key import WebhookEndpoint
            import httpx
            import hmac
            import hashlib
            import json

            webhooks = session.query(WebhookEndpoint).filter_by(org_id=batch.org_id, active=True).all()
            if webhooks:
                payload = {
                    "event": "batch.completed",
                    "data": {
                        "batch_id": str(batch.id),
                        "status": batch.status,
                        "succeeded": batch.succeeded,
                        "failed": batch.failed,
                        "completed_at": batch.completed_at.isoformat()
                    }
                }
                payload_bytes = json.dumps(payload).encode('utf-8')
                
                with httpx.Client(timeout=5.0) as client:
                    for wh in webhooks:
                        if "batch.completed" in wh.events:
                            signature = hmac.new(wh.secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
                            headers = {
                                "Content-Type": "application/json",
                                "x-certforge-signature": signature
                            }
                            try:
                                client.post(wh.url, content=payload_bytes, headers=headers)
                                logger.info(f"Webhook dispatched to {wh.url}")
                            except Exception as e:
                                logger.warning(f"Failed to dispatch webhook to {wh.url}: {e}")
        except Exception as e:
            logger.error(f"Webhook dispatch error: {e}")

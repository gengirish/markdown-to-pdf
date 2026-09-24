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
from datetime import datetime, timedelta, timezone

import procrastinate

from api.core.config import CERTFORGE_WEB_URL, DATABASE_URL
from api.models import get_db
from api.models.credential import CredentialBatch, Credential
from api.models.organization import Organization
from api.models.template import Template
from api.core.pdf_renderer import render_credential_pdf
from api.core.credential_signature import sign_credential
from api.models.credential import DELIVERY_FAILED
from api.services.delivery import deliver_credential_email, may_retry
from api.services.backgrounds import background_data_uri
from api.services.rendering import build_render_variables

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
#
# Postgres specifically, not merely "a database": Procrastinate's connector is
# psycopg, so pointing this at SQLite — which local development and the E2E
# suite both do — makes `open_async()` wait out its 30-second pool timeout and
# then fail application startup entirely. Gating on truthiness alone meant the
# API could not boot at all against a URL it otherwise serves perfectly.
WORKER_ENABLED = os.environ.get("DATABASE_URL", "").startswith("postgres")


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


# How long process_batch waits for its batch row to become visible. The upload
# route defers the job inside its own transaction, on Procrastinate's separate
# connection, so the job is committed — and the worker woken — before the
# batch is. Reading "not found" at that moment used to end the job as a
# success and leave the batch pending with nothing left to run it.
BATCH_VISIBLE_ATTEMPTS = 10
BATCH_VISIBLE_WAIT_SECONDS = 1.0


@worker_app.task(queue="issuance")
async def process_batch(batch_id_str: str):
    """Background task to process a CredentialBatch."""
    batch_id = uuid.UUID(batch_id_str)

    for _ in range(BATCH_VISIBLE_ATTEMPTS):
        retry_ids = await asyncio.to_thread(_process_batch_sync, batch_id)
        if retry_ids is not None:
            break
        await asyncio.sleep(BATCH_VISIBLE_WAIT_SECONDS)
    else:
        # The upload rolled back after queueing: an orphan job, not a batch.
        logger.warning("Batch %s never became visible; nothing to process.", batch_id)
        return

    # Deferred rather than retried inline: a provider outage would otherwise
    # stall the whole batch behind one address, and Procrastinate already gives
    # us the scheduling. Failing to queue a retry must not fail the batch —
    # the credentials are issued and verifiable either way.
    for public_id in retry_ids:
        try:
            await retry_delivery.defer_async(public_id=public_id)
        except Exception:
            logger.exception("Could not queue a delivery retry for %s", public_id)


# A batch still pending this long after upload has probably lost its job.
# Probably: the worker runs one job at a time, so a batch queued behind a large
# one waits legitimately. Re-queueing that one is harmless — whichever job
# claims it first processes it and the other finds it taken — and the queueing
# lock keeps the sweep to one extra job per batch however many minutes it waits.
STRANDED_BATCH_AFTER_SECONDS = 120


@worker_app.periodic(cron="* * * * *")
@worker_app.task(queue="issuance")
async def recover_batches(timestamp: int):
    """Put stuck batches back on the queue.

    Two ways a batch used to hang at "0 of N" forever, both silent:

    - The machine stopped mid-batch — a deploy replaces it, and Fly stops it
      on idle. The job stays ``doing`` under a worker that no longer exists,
      and the batch stays ``processing``. Nothing retried it, and a retry
      would have refused a batch that was not ``pending``.
    - The batch was committed but its job was lost.

    Runs only while the machine is up, which it is whenever anyone is
    watching a batch; it adds no inbound traffic, so it does not hold the
    machine awake.
    """
    job_manager = worker_app.job_manager
    for job in await job_manager.get_stalled_jobs(task_name=process_batch.name):
        batch_id = (job.task_kwargs or {}).get("batch_id_str")
        if batch_id:
            await asyncio.to_thread(_release_batch, uuid.UUID(batch_id))
        logger.warning("Retrying stalled job %s (batch %s)", job.id, batch_id)
        await job_manager.retry_job(job)

    for batch_id in await asyncio.to_thread(_stranded_batch_ids):
        try:
            await process_batch.configure(
                queueing_lock=f"recover-batch:{batch_id}"
            ).defer_async(batch_id_str=batch_id)
            logger.warning("Re-queued stranded batch %s", batch_id)
        except procrastinate.exceptions.AlreadyEnqueued:
            pass


def _release_batch(batch_id: uuid.UUID) -> None:
    """Hand a batch whose worker died back to ``pending`` so it can be claimed."""
    with get_db() as session:
        session.query(CredentialBatch).filter_by(
            id=batch_id, status="processing"
        ).update({"status": "pending"}, synchronize_session=False)


def _stranded_batch_ids() -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STRANDED_BATCH_AFTER_SECONDS)
    with get_db() as session:
        rows = session.query(CredentialBatch.id).filter(
            CredentialBatch.status == "pending",
            CredentialBatch.created_at < cutoff,
        ).all()
        return [str(row.id) for row in rows]


@worker_app.task(queue="issuance", retry=False)
async def retry_delivery(public_id: str):
    """Re-attempt one credential's email.

    Procrastinate's own retry is off. This task manages attempts itself, on the
    credential row, so the count survives a worker restart and so support can
    see how many times we tried without reading the queue. MAX_DELIVERY_ATTEMPTS
    is a hard stop: every AgentMail failure seen so far has been a configuration
    error, which retrying does not fix, and an unbounded retry would mail the
    same person on a loop.
    """
    await asyncio.to_thread(_retry_delivery_sync, public_id)


def _retry_delivery_sync(public_id: str) -> None:
    with get_db() as session:
        cred = session.query(Credential).filter_by(public_id=public_id).first()
        if not cred:
            logger.warning("Delivery retry: no credential %s", public_id)
            return
        # Re-checked here rather than trusted from the queue: the row may have
        # been delivered, or revoked, between queueing and running.
        if not may_retry(cred):
            logger.info(
                "Delivery retry skipped for %s (status=%s, attempts=%s)",
                public_id, cred.delivery_status, cred.delivery_attempts,
            )
            return
        deliver_credential_email(cred)


def _process_batch_sync(batch_id: uuid.UUID) -> list[str] | None:
    """Synchronous core logic for processing a batch.

    Returns the public IDs whose delivery failed and is still worth retrying.
    The caller defers those; queueing from here would mean reaching into the
    async Procrastinate app from inside a worker thread.

    Returns None when the batch row is not visible yet, so the caller can tell
    "not committed yet" apart from "already handled".
    """
    logger.info(f"Processing batch {batch_id}")
    import csv
    from io import StringIO
    import time
    
    with get_db() as session:
        # Claimed with a conditional UPDATE rather than read-then-write, so two
        # jobs for one batch — a recovery sweep racing the original — cannot
        # both process it.
        claimed = session.query(CredentialBatch).filter_by(
            id=batch_id, status="pending"
        ).update({"status": "processing"}, synchronize_session=False)
        session.commit()
        batch = session.query(CredentialBatch).filter_by(id=batch_id).first()
        if not batch:
            return None
        if not claimed:
            logger.warning(f"Batch {batch_id} is {batch.status}, not pending; skipping.")
            return []

        template = session.query(Template).filter_by(id=batch.template_id).first()
        if not template:
            batch.status = "failed"
            batch.error_report = {"error": "Template not found"}
            session.commit()
            return []

        org = session.query(Organization).filter_by(id=batch.org_id).first()

        # Fetch pending credentials for this batch
        # Wait, in the studio, the user uploads CSV, we can either parse it in the route
        # and create `Credential` rows with status="pending", OR we store the CSV in S3
        # and process it here. Since Phase 1 focuses on infrastructure, and we don't have
        # S3 set up, storing pending `Credential` rows during the route upload is best.
        
        pending_creds = session.query(Credential).filter_by(batch_id=batch.id, status="pending").all()
        
        # Resolved once for the whole batch rather than per credential: the
        # artwork is ~1 MB and every row of this batch renders the same
        # template, so re-reading it per row would be N round trips to object
        # storage for one image. The LRU in services/backgrounds.py would
        # mostly absorb that, but "mostly" is not a plan for a 500-row batch.
        batch_background = background_data_uri(template)

        # Started from the batch's own counts, not zero: a batch resumed after
        # its machine died has already committed some rows, and only the
        # still-pending ones are processed again. Rows and counts are committed
        # together, so the two agree at every commit.
        success_count = batch.succeeded
        failed_count = batch.failed
        # Counted apart from success/failed, which measure RENDERS. A batch that
        # rendered 30 PDFs and delivered none of them used to report "30
        # succeeded" and nothing else.
        delivered_count = batch.delivered
        delivery_failed_count = batch.delivery_failed
        retry_ids: list[str] = []
        errors = {}

        for cred in pending_creds:
            try:
                # 1. Render PDF
                #
                # metadata_ is the base so customer-supplied custom keys survive;
                # build_render_variables always wins on top of it, exactly as
                # name/title/credential_id/qr always used to override metadata
                # here. Shared with the single-issue PDF endpoint
                # (routes/verify.py) so bulk and single-issue can never again
                # build this dict two different ways.
                variables = dict(cred.metadata_)
                variables.update(
                    build_render_variables(cred, org, template, batch_background)
                )

                # This URL is rendered into the QR code and baked into the PDF, so
                # it is unfixable once a credential is printed. It was hardcoded to
                # certs.intelliforge.tech — the legacy product — which meant every
                # CertForge credential shipped pointing at someone else's brand.
                verify_url = f"{CERTFORGE_WEB_URL}/verify/{cred.public_id}"

                pdf_bytes = render_credential_pdf(template.html_source, variables)
                
                # 2. Upload PDF (mocked for now since R2/S3 is deferred to later)
                # In Phase 1 we might still just serve it dynamically or store temporarily.
                # Actually, CertForge generates PDFs on the fly for verification. 
                # For now, we leave pdf_url as None and generate on-the-fly.
                
                # 3. Send Email
                #
                # Through services/delivery.py rather than inline, so that this
                # and single issuance cannot drift into two different email
                # bodies and two different ways of recording an outcome. Every
                # path through it writes a terminal delivery state onto the row,
                # including the no-address case, which previously wrote nothing
                # and was indistinguishable afterwards from a rejected send.
                if deliver_credential_email(cred, verify_url=verify_url, org=org):
                    delivered_count += 1
                elif cred.delivery_status == DELIVERY_FAILED:
                    delivery_failed_count += 1
                    # Retryable failures are handed to a deferred job rather
                    # than retried here: a provider outage would otherwise stall
                    # the whole batch behind one address.
                    if may_retry(cred):
                        retry_ids.append(cred.public_id)

                cred.status = "issued"
                cred.issued_at = datetime.now(timezone.utc)
                # Re-signed because issued_at just changed, and the signature
                # covers it. The staged signature was over the timestamp the
                # row had when the batch was uploaded; leaving it would make
                # every bulk-issued credential verify as tampered.
                sign_credential(cred)
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
                batch.delivered = delivered_count
                batch.delivery_failed = delivery_failed_count
                session.commit()
                # small delay to prevent DB hammering
                time.sleep(0.1)

        batch.succeeded = success_count
        batch.failed = failed_count
        batch.delivered = delivered_count
        batch.delivery_failed = delivery_failed_count
        # Delivery failures do NOT make the batch failed: the credentials exist,
        # verify, and can be shared by link. Reporting the batch as failed would
        # hide 30 perfectly good credentials behind an email problem.
        batch.status = "completed" if failed_count == 0 else "completed_with_errors"
        batch.completed_at = datetime.now(timezone.utc)
        batch.error_report = errors if errors else None
        session.commit()
        
        logger.info(
            f"Batch {batch_id} completed: {success_count} rendered, {failed_count} failed, "
            f"{delivered_count} delivered, {delivery_failed_count} delivery failures."
        )

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
                        # A subscriber reading only succeeded/failed would
                        # conclude every recipient was emailed. These say
                        # otherwise when they were not.
                        "delivered": batch.delivered,
                        "delivery_failed": batch.delivery_failed,
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

    return retry_ids

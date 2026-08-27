"""Credential email delivery, and the record of what happened.

There is exactly one sender in this file, and both issuance paths call it. That
is deliberate: bulk issuance had grown its own inline sender in `worker.py` and
single issuance was about to grow a second one. Two senders means two email
bodies, two ways of recording an outcome, and two places to fix the next bug.

The reason this module exists at all is that the first production batch could
not be explained. No email arrived, AgentMail was healthy, and the send branch
demonstrably ran — but a credential with an empty `recipient_email` and a
credential whose send was rejected wrote exactly the same thing to the database:
nothing. The only trace was a `logger.warning` that had rolled off the Fly log
buffer by the time anyone looked.

So every path through `deliver_credential_email` writes a terminal state onto
the credential. Not sending is a recorded outcome here, not an absence.
"""

import logging
from datetime import datetime, timezone

from api.core.config import CERT_BRAND_NAME, CERTFORGE_WEB_URL
from api.core.email import agentmail_deliver
from api.models.credential import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    NOT_REQUESTED,
    SENT,
)

logger = logging.getLogger(__name__)

#: Give up after this many attempts. Chosen low on purpose: AgentMail failures
#: seen so far are configuration errors (a bad key, a missing inbox), which no
#: amount of retrying fixes, and a hard cap keeps a broken config from mailing
#: the same person on a loop.
MAX_DELIVERY_ATTEMPTS = 3

#: Truncated before it is stored. Provider errors are usually short, but an
#: unexpected exception can carry a whole traceback, and this column is read by
#: support in a table view.
MAX_ERROR_LEN = 500


def verify_url_for(public_id: str) -> str:
    """The URL a recipient is sent to.

    CERTFORGE_WEB_URL, never SITE_URL: the second is the legacy product's
    domain, and mailing CertForge credentials under it is a bug that has been
    fixed once already in worker.py.
    """
    return f"{CERTFORGE_WEB_URL}/verify/{public_id}"


def build_credential_email(cred, verify_url: str) -> tuple[str, str, str]:
    """(subject, text, html) for a credential notification."""
    subject = f"Your credential for {cred.title}"
    text = (
        f"Hi {cred.recipient_name},\n\n"
        f"Your credential for {cred.title} is ready.\n\n"
        f"View it here: {verify_url}\n"
    )
    html = f"""
    <h2>Your Credential from {CERT_BRAND_NAME}</h2>
    <p>Hi {cred.recipient_name},</p>
    <p>Your credential for <strong>{cred.title}</strong> is ready.</p>
    <p>View it here: <a href="{verify_url}">{verify_url}</a></p>
    """
    return subject, text, html


def mark_not_requested(cred, reason: str) -> None:
    """Record that no send was attempted, and why.

    The `reason` goes in `delivery_error` even though nothing failed. It is the
    difference between "this org did not ask us to email" and "this row has no
    address", which is the first thing anyone asks when a recipient reports a
    missing email.
    """
    cred.delivery_status = NOT_REQUESTED
    cred.delivery_error = reason[:MAX_ERROR_LEN]
    cred.delivered_at = None


def deliver_credential_email(cred, *, verify_url: str | None = None) -> bool:
    """Send one credential's notification and record the outcome on the row.

    Returns True only when the provider accepted the message. Never raises:
    a delivery failure must not lose a credential that was otherwise issued
    correctly, so an unexpected exception is recorded as a failed delivery
    rather than propagated into the issuance path.
    """
    recipient = (cred.recipient_email or "").strip()
    if not recipient:
        mark_not_requested(cred, "No recipient email on this credential.")
        return False

    if verify_url is None:
        verify_url = verify_url_for(cred.public_id)

    subject, text, html = build_credential_email(cred, verify_url)

    cred.delivery_status = DELIVERY_PENDING
    cred.delivery_attempts = (cred.delivery_attempts or 0) + 1

    try:
        success, message = agentmail_deliver(
            to_email=recipient,
            subject=subject,
            text=text,
            html=html,
            link_hint="credential",
        )
    except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
        logger.exception("Delivery raised for %s", cred.public_id)
        cred.delivery_status = DELIVERY_FAILED
        cred.delivery_error = str(exc)[:MAX_ERROR_LEN]
        cred.delivered_at = None
        return False

    if success:
        cred.delivery_status = SENT
        cred.delivered_at = datetime.now(timezone.utc)
        cred.delivery_error = None
        logger.info("Delivered %s to %s", cred.public_id, recipient)
        return True

    cred.delivery_status = DELIVERY_FAILED
    cred.delivery_error = (message or "Delivery failed.")[:MAX_ERROR_LEN]
    cred.delivered_at = None
    logger.warning(
        "Delivery failed for %s to %s (attempt %s): %s",
        cred.public_id, recipient, cred.delivery_attempts, cred.delivery_error,
    )
    return False


def may_retry(cred) -> bool:
    """Whether a failed delivery is still worth another attempt."""
    from api.models.credential import DELIVERY_RETRYABLE

    return (
        cred.delivery_status in DELIVERY_RETRYABLE
        and (cred.delivery_attempts or 0) < MAX_DELIVERY_ATTEMPTS
    )


def delivery_state(cred) -> dict:
    """The delivery half of a credential's API representation."""
    return {
        "status": cred.delivery_status,
        "delivered_at": cred.delivered_at.isoformat() if cred.delivered_at else None,
        "error": cred.delivery_error,
        "attempts": cred.delivery_attempts or 0,
        "may_retry": may_retry(cred),
    }

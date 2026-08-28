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

import html as html_mod
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


def _esc(value) -> str:
    """Escape a value for the HTML body."""
    return html_mod.escape(str(value or ''))

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


#: Ported from the legacy CERT_EMAIL_HTML (api/index.py, frozen). Copied rather
#: than imported: index.py is the frozen legacy surface, importing from it into
#: a service would invert the dependency, and the two carry different fields —
#: legacy has an instructor and a certificate kind, CertForge has an issuing
#: organization and a credential id.
#:
#: The first CertForge version of this was four lines of bare HTML. It delivered
#: fine and looked nothing like the product, which is the same mistake the
#: certificate generator made: writing something generic instead of reading what
#: already existed.
CREDENTIAL_EMAIL_HTML = """
<div style="font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;background:#0f0f23;padding:24px;border-radius:16px;">
  <div style="background:linear-gradient(135deg,{primary} 0%,#1e1e6e 50%,#2a1a5e 100%);padding:28px 32px 24px;text-align:center;border-radius:12px 12px 0 0;">
    <div style="font-size:11px;letter-spacing:4px;text-transform:uppercase;color:{accent};font-weight:600;">Verified Credential</div>
    <div style="font-size:24px;font-weight:700;color:#fff;margin:8px 0 12px;">{issuer}</div>
    <div style="display:inline-block;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{accent};font-weight:600;border:1px solid rgba(139,125,60,0.6);padding:6px 18px;border-radius:20px;">{title}</div>
  </div>
  <div style="background:#ffffff;padding:32px;text-align:center;">
    <div style="display:inline-block;background:#f0fff4;border:1px solid #68d391;color:#276749;font-size:12px;font-weight:600;padding:5px 14px;border-radius:20px;margin-bottom:20px;">&#10003; Verified &amp; Authentic</div>
    <p style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#a0aec0;margin:0 0 6px;">This Credential is Awarded To</p>
    <h1 style="font-size:28px;font-weight:700;color:#1a202c;margin:0 0 4px;">{name}</h1>
    <div style="height:2px;background:linear-gradient(to right,transparent,#d4af37,transparent);margin:8px auto 16px;width:60%;"></div>
    <p style="font-size:16px;font-weight:600;color:#553c9a;margin:0 0 24px;">{title}</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #edf2f7;border-bottom:1px solid #edf2f7;margin-bottom:24px;">
      <tr>
        <td style="text-align:center;padding:14px 8px;width:33%;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;">{date}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Date</div>
        </td>
        <td style="text-align:center;padding:14px 8px;width:34%;border-left:1px solid #edf2f7;border-right:1px solid #edf2f7;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;">{issuer}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Issued By</div>
        </td>
        <td style="text-align:center;padding:14px 8px;width:33%;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;font-family:monospace;">{credential_id}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Credential ID</div>
        </td>
      </tr>
    </table>
    <a href="{verify_url}" style="display:inline-block;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:14px 36px;border-radius:12px;font-size:16px;font-weight:600;text-decoration:none;margin-bottom:12px;">View Your Credential</a>
    <p style="font-size:12px;color:#a0aec0;margin:12px 0 0;">Or download the PDF directly: <a href="{pdf_url}" style="color:#667eea;text-decoration:none;font-weight:500;">Download PDF</a></p>
  </div>
  <div style="background:#f8fafc;padding:16px 32px;text-align:center;border-radius:0 0 12px 12px;border-top:1px solid #edf2f7;">
    <p style="font-size:12px;color:#a0aec0;margin:0;">{footer}</p>
  </div>
</div>
"""


def pdf_url_for(public_id: str) -> str:
    """The on-demand PDF for a credential, on the machine-facing host."""
    from api.core.config import CERTFORGE_API_URL

    return f"{CERTFORGE_API_URL}/credentials/{public_id}/pdf"


def build_credential_email(cred, verify_url: str, org=None) -> tuple[str, str, str]:
    """(subject, text, html) for a credential notification.

    `org` is optional so a retry can rebuild the message from the credential
    alone: the retry task loads a row, not a request context, and an email that
    cannot be rebuilt is an email that can never be retried.
    """
    issuer = getattr(org, "name", None) or CERT_BRAND_NAME
    primary = getattr(org, "primary_color", None) or "#12124a"
    accent = getattr(org, "accent_color", None) or "#d4af37"
    footer = getattr(org, "footer_text", None) or f"Issued by {issuer}"
    issued = cred.issued_at.strftime("%Y-%m-%d") if cred.issued_at else ""

    subject = f"Your credential for {cred.title}"
    text = (
        f"Hi {cred.recipient_name},\n\n"
        f"Your credential for {cred.title} is ready.\n\n"
        f"View it here: {verify_url}\n"
        f"Download the PDF: {pdf_url_for(cred.public_id)}\n"
    )

    # Escaped: recipient names and credential titles arrive from customer CSVs,
    # and this markup lands in someone's mail client.
    html = CREDENTIAL_EMAIL_HTML.format(
        primary=_esc(primary),
        accent=_esc(accent),
        issuer=_esc(issuer),
        name=_esc(cred.recipient_name),
        title=_esc(cred.title),
        date=_esc(issued),
        credential_id=_esc(cred.public_id),
        verify_url=_esc(verify_url),
        pdf_url=_esc(pdf_url_for(cred.public_id)),
        footer=_esc(footer),
    )
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


def deliver_credential_email(cred, *, verify_url: str | None = None, org=None) -> bool:
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

    subject, text, html = build_credential_email(cred, verify_url, org)

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

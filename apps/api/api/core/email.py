"""
Email delivery module using AgentMail.

Handles background warm-up of the inbox ID and asynchronous delivery
of certificate and invoice notification emails.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

from api.core.config import AGENTMAIL_API_KEY, AGENTMAIL_INBOX_ID

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────

EMAIL_SEND_TIMEOUT_SEC = 20.0
AGENTMAIL_HTTP_TIMEOUT_SEC = 10.0

_agentmail_client = None
_agentmail_ready = False
_agentmail_inbox_cached: str = ""
_agentmail_inbox_lock = threading.Lock()
_email_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cert-email")

if AGENTMAIL_API_KEY:
    try:
        from agentmail import AgentMail as AgentMailClient
        _agentmail_client = AgentMailClient(
            api_key=AGENTMAIL_API_KEY,
            timeout=AGENTMAIL_HTTP_TIMEOUT_SEC,
        )
        logger.info("AgentMail client configured (inbox warm-up in background)")
    except Exception as e:
        logger.warning(f"AgentMail initialization failed: {e}")


# ── Core Delivery Logic ────────────────────────────────────────────────────

def _agentmail_error_message(exc: Exception) -> str:
    """Turn AgentMail failures into a short UI-safe message."""
    try:
        from agentmail.core.api_error import ApiError as AgentMailApiError

        if isinstance(exc, AgentMailApiError):
            body = exc.body
            if isinstance(body, dict):
                msg = body.get("message") or body.get("name")
                if msg:
                    return str(msg)
            if exc.status_code == 403:
                return (
                    "AgentMail rejected the request (403). Check AGENTMAIL_API_KEY on the server — "
                    "remove any trailing \\r\\n from the value in Vercel env settings."
                )
            if exc.status_code == 404:
                return (
                    f"AgentMail inbox not found ({AGENTMAIL_INBOX_ID!r}). "
                    "Set AGENTMAIL_INBOX_ID to your inbox id from the AgentMail console."
                )
    except Exception:
        pass
    if isinstance(exc, KeyError):
        return "Email template error — contact support@intelliforge.tech."
    text = str(exc).strip()
    return text[:240] if text else "Could not deliver email."


def _get_agentmail_inbox_id() -> str:
    if _agentmail_inbox_cached:
        return _agentmail_inbox_cached
    return AGENTMAIL_INBOX_ID if _agentmail_client else ""


def _refresh_agentmail_inbox_from_api(*, force: bool = False) -> str:
    global _agentmail_inbox_cached, _agentmail_ready
    if not _agentmail_client:
        return ""
    configured = AGENTMAIL_INBOX_ID
    with _agentmail_inbox_lock:
        if _agentmail_inbox_cached and not force:
            return _agentmail_inbox_cached
        if force:
            _agentmail_inbox_cached = ""
        try:
            from agentmail.core.api_error import ApiError as AgentMailApiError
            page = _agentmail_client.inboxes.list(limit=50)
            inboxes = page.inboxes or []
            if not inboxes:
                _agentmail_inbox_cached = configured
                return configured
            by_email = {ib.email.strip().lower(): ib.inbox_id for ib in inboxes if getattr(ib, "email", None)}
            by_id = {ib.inbox_id: ib.inbox_id for ib in inboxes}
            key = configured.strip().lower()
            if key in by_email:
                _agentmail_inbox_cached = by_email[key]
                _agentmail_ready = True
                return _agentmail_inbox_cached
            if configured in by_id:
                _agentmail_inbox_cached = configured
                _agentmail_ready = True
                return configured
            if len(inboxes) == 1:
                _agentmail_inbox_cached = inboxes[0].inbox_id
                _agentmail_ready = True
                return _agentmail_inbox_cached
        except AgentMailApiError:
            pass
        except Exception as e:
            logger.warning(f"AgentMail inbox lookup failed: {e}")
        _agentmail_inbox_cached = configured
        return configured


def _warm_agentmail_inbox():
    try:
        inbox_id = _refresh_agentmail_inbox_from_api()
        if inbox_id:
            logger.info(f"AgentMail inbox ready ({inbox_id})")
    except Exception as e:
        logger.warning(f"AgentMail inbox warm-up failed: {e}")


def _is_agentmail_inbox_not_found(exc: Exception) -> bool:
    try:
        from agentmail.core.api_error import ApiError as AgentMailApiError
        if isinstance(exc, AgentMailApiError) and exc.status_code == 404:
            return True
    except Exception:
        pass
    return False


if _agentmail_client:
    threading.Thread(
        target=_warm_agentmail_inbox,
        daemon=True,
        name="agentmail-warm",
    ).start()


def _run_with_timeout(fn, timeout_sec: float, timeout_message: str):
    future = _email_executor.submit(fn)
    try:
        return future.result(timeout=timeout_sec)
    except FuturesTimeoutError:
        logger.warning(timeout_message)
        return None


def agentmail_deliver(
    *, to_email: str, subject: str, text: str, html: str, link_hint: str = "certificate"
) -> tuple[bool, str]:
    """Synchronously send an email using AgentMail with fallback logic."""
    if not _agentmail_client:
        return False, "Email service is not configured on this server."
    recipient = to_email.strip()
    if not recipient:
        return False, "Recipient email is required."
    inbox_id = _get_agentmail_inbox_id()
    if not inbox_id:
        return False, "AgentMail inbox is not configured. Set AGENTMAIL_INBOX_ID."
    
    fallback = f"Could not deliver email. Share the {link_hint} link instead."
    try:
        _agentmail_client.inboxes.messages.send(
            inbox_id,
            to=recipient,
            subject=subject,
            text=text,
            html=html,
        )
        logger.info(f"AgentMail sent to {recipient} from inbox {inbox_id}")
        return True, ""
    except Exception as e:
        if _is_agentmail_inbox_not_found(e):
            resolved = _refresh_agentmail_inbox_from_api(force=True)
            if resolved and resolved != inbox_id:
                try:
                    _agentmail_client.inboxes.messages.send(
                        resolved,
                        to=recipient,
                        subject=subject,
                        text=text,
                        html=html,
                    )
                    logger.info(f"AgentMail sent to {recipient} from inbox {resolved}")
                    return True, ""
                except Exception as retry_exc:
                    e = retry_exc
        err = _agentmail_error_message(e)
        logger.warning(f"AgentMail send to {recipient} failed: {e}")
        if err and "Could not deliver" not in err:
            return False, f"{err} Share the {link_hint} link instead."
        return False, fallback

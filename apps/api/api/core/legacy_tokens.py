"""
Legacy stateless HMAC-SHA256 token encoder/decoder.

Preserves the exact encoding format from certs.intelliforge.tech so that
all existing certificate URLs remain permanently valid. New CertForge
credentials use the DB-backed `credentials` table, but legacy tokens
are still decoded on-the-fly by these functions.

Token format: {base64url_payload}.{hmac_sha256_hex}
Payload: compact JSON with single-letter keys (n=name, c=course, etc.)
"""

import base64
import hashlib
import hmac as hmac_mod
import json
import logging
from typing import Optional

from api.core.config import CERT_SECRET

logger = logging.getLogger(__name__)


def encode_legacy_token(data: dict) -> str:
    """Encode certificate data into a URL-safe token with full HMAC-SHA256 signature.

    This is the original encoding used by certs.intelliforge.tech.
    """
    compact = json.dumps(data, separators=(",", ":"), sort_keys=True)
    payload = base64.urlsafe_b64encode(compact.encode()).decode().rstrip("=")
    sig = hmac_mod.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def decode_legacy_token(token: str) -> Optional[dict]:
    """Decode and verify a legacy certificate token.

    Returns the decoded payload dict if valid, None if invalid or tampered.
    Tries the primary secret first, then any rotated secrets.
    """
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)

    # Try primary secret
    expected = hmac_mod.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if hmac_mod.compare_digest(sig, expected):
        return _decode_payload(payload)

    # Try rotated secrets
    import os
    rotated_raw = os.environ.get("CERT_ROTATED_SECRET_KEYS", "").strip()
    if rotated_raw:
        for key in rotated_raw.split(","):
            key = key.strip()
            if not key or key == CERT_SECRET:
                continue
            expected = hmac_mod.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if hmac_mod.compare_digest(sig, expected):
                return _decode_payload(payload)

    return None


def _decode_payload(payload: str) -> Optional[dict]:
    """Decode a base64url payload string into a dict."""
    try:
        padded = payload + "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        return json.loads(raw)
    except Exception:
        return None


def legacy_cert_id(data: dict) -> str:
    """Generate the deterministic CERT-XXXXXXXXXXXX ID from a legacy payload.

    This is a SHA-256 hash of the payload, truncated to 12 hex chars.
    Identical to the original `_cert_id()` in index.py.
    """
    if data.get("k") in ("i", "a"):
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True)
    else:
        raw = f"{data['n']}-{data['c']}-{data['d']}"
    return "CERT-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def token_hash(token: str) -> str:
    """SHA-256 hash of a token for DB storage/lookup (same as db.token_hash)."""
    return hashlib.sha256(token.encode()).hexdigest()


def is_internship_payload(data: dict) -> bool:
    """Check if payload is a VTU internship certificate."""
    return data.get("k") == "i"


def is_appreciation_payload(data: dict) -> bool:
    """Check if payload is an appreciation certificate."""
    return data.get("k") == "a"


def is_invoice_payload(data: dict) -> bool:
    """Check if payload is an invoice."""
    return data.get("k") == "inv"


def certificate_kind_from_payload(data: dict) -> str:
    """Return the credential kind string from a decoded legacy payload."""
    if is_internship_payload(data):
        return "internship"
    if is_appreciation_payload(data):
        return "appreciation"
    return "participation"

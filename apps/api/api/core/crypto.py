"""
Cryptographic utilities for CertForge:
- Credential ID generation: CF-{year}-{base32(8)}
- HMAC-SHA256 signing with per-environment secret rotation support
- API key generation and hashing (SHA-256, stored hashed at rest)
"""

import hashlib
import hmac as hmac_mod
import secrets
from datetime import datetime, timezone
from typing import Optional

from api.core.config import CERT_SECRET

# Crockford-style Base32 (excludes 0, 1, I, O, L to avoid ambiguity)
_BASE32_CHARSET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


# ── Credential IDs ─────────────────────────────────────────────────────────

def generate_credential_id(year: Optional[int] = None) -> str:
    """Generate a unique credential ID: CF-{year}-{base32(8)}.

    Example: CF-2026-K7M2P9QX

    Collision probability is ~1 in 29^8 ≈ 20 billion per year.
    Callers must collision-check against the database before committing.
    """
    yr = year or datetime.now(timezone.utc).year
    random_part = "".join(secrets.choice(_BASE32_CHARSET) for _ in range(8))
    return f"CF-{yr}-{random_part}"


def is_legacy_cert_id(public_id: str) -> bool:
    """Check if a credential ID uses the legacy CERT-XXXXXXXXXXXX format."""
    return public_id.startswith("CERT-") and len(public_id) == 17


def is_certforge_id(public_id: str) -> bool:
    """Check if a credential ID uses the new CF-YYYY-XXXXXXXX format."""
    if not public_id.startswith("CF-"):
        return False
    parts = public_id.split("-", 2)
    return len(parts) == 3 and len(parts[1]) == 4 and len(parts[2]) == 8


# ── HMAC signing ───────────────────────────────────────────────────────────

def _get_signing_secrets() -> list[str]:
    """Return list of HMAC secrets: primary first, then any rotated keys.

    Supports secret rotation: set CERT_ROTATED_SECRET_KEYS as comma-separated
    old keys. Verification tries all keys; signing always uses primary.
    """
    import os
    primary = CERT_SECRET
    rotated_raw = os.environ.get("CERT_ROTATED_SECRET_KEYS", "").strip()
    keys = [primary]
    if rotated_raw:
        for k in rotated_raw.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)
    return keys


def hmac_sign(payload: str, secret: Optional[str] = None) -> str:
    """Generate HMAC-SHA256 hex digest for a payload string."""
    key = secret or CERT_SECRET
    return hmac_mod.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def hmac_verify(payload: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature against primary and any rotated secrets.

    Returns True if the signature matches any known secret key.
    """
    if not signature:
        return False
    for key in _get_signing_secrets():
        expected = hmac_mod.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac_mod.compare_digest(signature, expected):
            return True
    return False


# ── API key management ─────────────────────────────────────────────────────

def hash_api_key(api_key: str) -> str:
    """Hash an API key with SHA-256 for secure storage at rest."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key(prefix: str = "cf_live") -> tuple[str, str]:
    """Generate a new API key and its hash.

    Returns (raw_key, key_hash). The raw key is shown once to the user;
    only the hash is stored in the database.
    """
    raw_key = f"{prefix}_{secrets.token_urlsafe(32)}"
    return raw_key, hash_api_key(raw_key)


def generate_webhook_secret() -> str:
    """Generate a secret for webhook signature verification."""
    return f"whsec_{secrets.token_urlsafe(32)}"

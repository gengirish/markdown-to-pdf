"""
CertForge configuration — environment variables, branding constants, and runtime settings.

All env vars are loaded once at import time. Branding is exposed via `certificate_branding()`
for use in templates, emails, and API responses.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv(".env.vercel.local")

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _sanitize_env(value: str) -> str:
    """Strip whitespace and accidental literal \\r\\n suffixes from env copy-paste."""
    if not value:
        return ""
    v = value.strip()
    while v.endswith("\\r\\n"):
        v = v[:-4].rstrip()
    return v


def _env(key: str, default: str = "") -> str:
    """Read and sanitize an environment variable."""
    return _sanitize_env(os.environ.get(key, default)) or default


# ── Core secrets ───────────────────────────────────────────────────────────

IS_PROD = os.environ.get("VERCEL_ENV") == "production" or os.environ.get("ENV") == "production"

CERT_SECRET = _sanitize_env(os.environ.get("CERT_SECRET_KEY", ""))

# Razorpay webhook signing secret. Deliberately has NO default: the webhook
# handler upgrades an org's tier on a valid signature, so a known fallback
# value would let anyone forge that request. Unset means the webhook rejects
# every call (see routes/billing.py).
RAZORPAY_SECRET = _env("RAZORPAY_WEBHOOK_SECRET") or _env("RAZORPAY_SECRET_KEY")
if not RAZORPAY_SECRET:
    logger.warning(
        "RAZORPAY_WEBHOOK_SECRET not set — Razorpay webhooks will be rejected."
    )

if not CERT_SECRET:
    if IS_PROD:
        raise RuntimeError("CERT_SECRET_KEY environment variable is required in production")
    CERT_SECRET = "pdfcert-dev-secret-local-only"
    logger.warning("CERT_SECRET_KEY not set — using insecure dev default. Set it before deploying.")

CERT_API_KEYS: set[str] = set()
_raw_keys = _env("CERT_API_KEYS")
if _raw_keys:
    CERT_API_KEYS = {_sanitize_env(k) for k in _raw_keys.split(",") if _sanitize_env(k)}

ADMIN_KEY = _env("ADMIN_KEY")
if not ADMIN_KEY and not IS_PROD:
    ADMIN_KEY = "admin-dev-key"

DATABASE_URL = _env("DATABASE_URL")

# ── Clerk ──────────────────────────────────────────────────────────────────

CLERK_SECRET_KEY = _env("CLERK_SECRET_KEY")
CLERK_WEBHOOK_SECRET = _env("CLERK_WEBHOOK_SECRET")
CLERK_PUBLISHABLE_KEY = _env("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")

# Optional explicit override. When unset, api/core/auth.py derives the Frontend
# API JWKS URL from the publishable key.
CLERK_JWKS_URL = _env("CLERK_JWKS_URL")

# ── AgentMail ──────────────────────────────────────────────────────────────

AGENTMAIL_API_KEY = _env("AGENTMAIL_API_KEY")
AGENTMAIL_INBOX_ID = _env("AGENTMAIL_INBOX_ID", "support@intelliforge.tech")

# ── Email settings ─────────────────────────────────────────────────────────

EMAIL_SEND_TIMEOUT_SEC = 20.0
AGENTMAIL_HTTP_TIMEOUT_SEC = 10.0

# ── Branding ───────────────────────────────────────────────────────────────

SITE_URL = _env("SITE_URL").rstrip("/")
CONTACT_EMAIL = _env("CONTACT_EMAIL", "support@intelliforge.tech")
FOUNDER_NAME = _env("FOUNDER_NAME", "Girish Hiremath")
FOUNDER_TITLE = _env("FOUNDER_TITLE", "Founder, Intelliforge AI")
CERT_ORG_TAGLINE = _env("CERT_ORG_TAGLINE", "AN INTELLIFORGE AI INITIATIVE")
CERT_BRAND_NAME = _env("CERT_BRAND_NAME", "IntelliForge Learning")
CERT_PARTICIPATION_TITLE = _env("CERT_PARTICIPATION_TITLE", "Certificate of Participation")
CERT_ISSUED_BY = _env("CERT_ISSUED_BY") or CERT_BRAND_NAME
CERT_WEBSITE = _env("CERT_WEBSITE", "learning.intelliforge.tech")
CERT_INTERNSHIP_ORG = _env("CERT_INTERNSHIP_ORG", "Intelliforge Digital Services")
CERT_INTERNSHIP_BRAND_PREFIX = _env("CERT_INTERNSHIP_BRAND_PREFIX", "IntelliForge")
CERT_INTERNSHIP_BRAND_ACCENT = _env("CERT_INTERNSHIP_BRAND_ACCENT", "Forge")

# Appreciation branding
CERT_APPRECIATION_ORG = _env("CERT_APPRECIATION_ORG", "IntelliForge AI")
CERT_APPRECIATION_ORG_BOLD = _env("CERT_APPRECIATION_ORG_BOLD", "IntelliForge")
CERT_APPRECIATION_ORG_LIGHT = _env("CERT_APPRECIATION_ORG_LIGHT", "AI")
CERT_APPRECIATION_PARTNER_ORG = _env("CERT_APPRECIATION_PARTNER_ORG", "maidaan.academy")
CERT_APPRECIATION_TITLE_LINE1 = _env("CERT_APPRECIATION_TITLE_LINE1", "CERTIFICATE")
CERT_APPRECIATION_TITLE_LINE2 = _env("CERT_APPRECIATION_TITLE_LINE2", "OF APPRECIATION")
CERT_APPRECIATION_PRESENTED_LABEL = _env(
    "CERT_APPRECIATION_PRESENTED_LABEL",
    "This certificate is proudly presented to",
)

# Appreciation color scheme — imported defaults from appreciation_assets
from api.appreciation_assets import (
    APPRECIATION_ACCENT_COLOR,
    APPRECIATION_HEADER_BG,
    APPRECIATION_HOST_NAME_DEFAULT,
    APPRECIATION_HOST_ORGANIZER_DEFAULT,
    APPRECIATION_SECONDARY_COLOR,
    APPRECIATION_SIDEBAR_COLOR,
)

CERT_APPRECIATION_ACCENT = _env("CERT_APPRECIATION_ACCENT", APPRECIATION_ACCENT_COLOR)
CERT_APPRECIATION_SIDEBAR_COLOR = _env("CERT_APPRECIATION_SIDEBAR_COLOR", APPRECIATION_SIDEBAR_COLOR)
CERT_APPRECIATION_SECONDARY_COLOR = _env("CERT_APPRECIATION_SECONDARY_COLOR", APPRECIATION_SECONDARY_COLOR)
CERT_APPRECIATION_HEADER_BG = _env("CERT_APPRECIATION_HEADER_BG", APPRECIATION_HEADER_BG)
CERT_APPRECIATION_EVENT_COLOR = _env("CERT_APPRECIATION_EVENT_COLOR", APPRECIATION_SECONDARY_COLOR)
CERT_APPRECIATION_AI_COLOR = _env("CERT_APPRECIATION_AI_COLOR", "#7B6FFF")
CERT_APPRECIATION_HOST_NAME = _env("CERT_APPRECIATION_HOST_NAME", APPRECIATION_HOST_NAME_DEFAULT)
CERT_APPRECIATION_HOST_ORGANIZER = _env("CERT_APPRECIATION_HOST_ORGANIZER", APPRECIATION_HOST_ORGANIZER_DEFAULT)

# ── Rate limiting ──────────────────────────────────────────────────────────

RATE_LIMIT = int(_env("RATE_LIMIT_MAX_REQUESTS", "10") or "10")
RATE_WINDOW = int(_env("RATE_LIMIT_WINDOW_SECONDS", "60") or "60")

# Number of trusted reverse proxies in front of this app, counted from the app
# outwards. Requests reach us as browser -> Vercel edge -> Fly proxy -> uvicorn,
# so X-Forwarded-For arrives as "<client>, <vercel-edge>" (Fly appends the peer
# it saw) and the real client is the 2nd entry from the right. Set to 0 to
# ignore forwarding headers entirely and trust the socket peer.
TRUSTED_PROXY_HOPS = int(_env("TRUSTED_PROXY_HOPS", "2") or "2")

# ── Billing tiers ──────────────────────────────────────────────────────────

BILLING_TIERS = {
    "community": {"name": "Community", "price_paise": 0, "monthly_quota": 50},
    "starter": {"name": "Starter", "price_paise": 299900, "monthly_quota": 500},
    "growth": {"name": "Growth", "price_paise": 999900, "monthly_quota": 2000},
    "scale": {"name": "Scale", "price_paise": 2499900, "monthly_quota": -1},  # -1 = unlimited
}


def get_tier_quota(tier: str) -> int:
    """Return monthly credential quota for a billing tier. -1 means unlimited."""
    info = BILLING_TIERS.get(tier, BILLING_TIERS["community"])
    return info["monthly_quota"]

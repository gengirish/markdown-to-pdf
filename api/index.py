"""
FastAPI backend for PDF Cert Generator.
Handles certificate creation, verification, and PDF certificate generation.

Certificates use stateless HMAC-SHA256 signed tokens encoded in the URL itself,
so no database is needed and certificates are permanent and tamper-proof.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, model_validator
from xhtml2pdf import pisa
from io import BytesIO
import logging
import hashlib
import hmac as hmac_mod
import json
import os
import base64
import time
import math
from collections import defaultdict
from urllib.parse import urlencode
from typing import Literal
import html as html_mod

from api.appreciation_assets import (
    APPRECIATION_ACCENT_COLOR,
    APPRECIATION_HEADER_BG,
    APPRECIATION_HOST_NAME_DEFAULT,
    APPRECIATION_HOST_ORGANIZER_DEFAULT,
    APPRECIATION_SECONDARY_COLOR,
    APPRECIATION_SIDEBAR_COLOR,
    appreciation_event_footer_html,
    appreciation_header_html_from_branding,
    appreciation_header_stripe_html,
    appreciation_host_strip_from_branding,
    appreciation_pdf_accent_rail,
    appreciation_pdf_sidebar_stripes,
    appreciation_pdf_tricolor_footer,
    appreciation_sport_seal_html,
    resolve_appreciation_host_name,
)
from api.certificate_templates import (
    CERTIFICATE_APPRECIATION_HTML,
    CERTIFICATE_INTERNSHIP_VTU_HTML,
    CERTIFICATE_PARTICIPATION_HTML,
    CERT_EMAIL_INTERNSHIP_HTML,
    VIEWER_APPRECIATION_HTML,
    VIEWER_INTERNSHIP_HTML,
)
from api.invoice_brand import invoice_brand_colors
from api.invoice_utils import (
    amount_in_words_inr,
    build_invoice_pdf,
    build_line_items_rows,
    compact_invoice_token_payload,
    default_invoice_number,
    expand_invoice_token_payload,
    format_inr,
    format_usd,
)

import uuid as uuid_mod
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import qrcode
from qrcode.image.pil import PilImage
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_AVAILABLE = bool(os.environ.get("DATABASE_URL", ""))
db = None
_db_ready = False
if DB_AVAILABLE:
    from api import db as _db_mod
    db = _db_mod


def _ensure_db_ready() -> bool:
    """Lazy DB init so cold starts and requests are not blocked at import time."""
    global DB_AVAILABLE, db, _db_ready
    if not DB_AVAILABLE or _db_ready:
        return DB_AVAILABLE
    try:
        db.init_schema()
        _db_ready = True
        logger.info("Database connected and schema initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed, running without DB: {e}")
        DB_AVAILABLE = False
        db = None
    return DB_AVAILABLE

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _sanitize_env(value: str) -> str:
    """Strip whitespace and accidental literal \\r\\n suffixes from env copy-paste."""
    if not value:
        return ""
    v = value.strip()
    while v.endswith("\\r\\n"):
        v = v[:-4].rstrip()
    return v


IS_PROD = os.environ.get("VERCEL_ENV") == "production" or os.environ.get("ENV") == "production"
CERT_SECRET = _sanitize_env(os.environ.get("CERT_SECRET_KEY", ""))
if not CERT_SECRET:
    if IS_PROD:
        raise RuntimeError("CERT_SECRET_KEY environment variable is required in production")
    CERT_SECRET = "pdfcert-dev-secret-local-only"
    logger.warning("CERT_SECRET_KEY not set — using insecure dev default. Set it before deploying.")

CERT_API_KEYS: set[str] = set()
_raw_keys = _sanitize_env(os.environ.get("CERT_API_KEYS", ""))
if _raw_keys:
    CERT_API_KEYS = {_sanitize_env(k) for k in _raw_keys.split(",") if _sanitize_env(k)}

ADMIN_KEY = _sanitize_env(os.environ.get("ADMIN_KEY", ""))
if not ADMIN_KEY and not IS_PROD:
    ADMIN_KEY = "admin-dev-key"

AGENTMAIL_API_KEY = _sanitize_env(os.environ.get("AGENTMAIL_API_KEY", ""))
AGENTMAIL_INBOX_ID = _sanitize_env(
    os.environ.get("AGENTMAIL_INBOX_ID", "support@intelliforge.tech")
) or "support@intelliforge.tech"
_agentmail_client = None
_agentmail_ready = False
_agentmail_inbox_cached: str = ""
_agentmail_inbox_lock = threading.Lock()
EMAIL_SEND_TIMEOUT_SEC = 20.0
AGENTMAIL_HTTP_TIMEOUT_SEC = 10.0
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



# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP, resets on cold start)
# ---------------------------------------------------------------------------
_rate_buckets: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10
RATE_WINDOW = 60


def _check_rate_limit(client_ip: str) -> tuple[bool, dict[str, str]]:
    """Return (allowed, rate-limit headers) for the client IP."""
    now = time.time()
    bucket = _rate_buckets[client_ip]
    _rate_buckets[client_ip] = [t for t in bucket if now - t < RATE_WINDOW]
    bucket = _rate_buckets[client_ip]

    def _reset_seconds(ts_list: list[float]) -> int:
        if not ts_list:
            return int(RATE_WINDOW)
        oldest = min(ts_list)
        return max(1, int(math.ceil(RATE_WINDOW - (now - oldest))))

    if len(bucket) >= RATE_LIMIT:
        return False, {
            "X-RateLimit-Limit": str(RATE_LIMIT),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(_reset_seconds(bucket)),
        }

    _rate_buckets[client_ip].append(now)
    nb = _rate_buckets[client_ip]
    remaining = RATE_LIMIT - len(nb)
    return True, {
        "X-RateLimit-Limit": str(RATE_LIMIT),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Reset": str(_reset_seconds(nb)),
    }


# ---------------------------------------------------------------------------
# Idempotency cache (in-memory, TTL 1 hour, resets on cold start)
# ---------------------------------------------------------------------------
_idempotency_cache: dict[str, dict] = {}
_IDEMPOTENCY_TTL = 3600


def _check_idempotency(key: str) -> dict | None:
    """Return cached response if key exists and hasn't expired."""
    entry = _idempotency_cache.get(key)
    if entry and time.time() - entry["ts"] < _IDEMPOTENCY_TTL:
        return entry["response"]
    return None


def _store_idempotency(key: str, response: dict):
    _idempotency_cache[key] = {"response": response, "ts": time.time()}
    if len(_idempotency_cache) > 10000:
        cutoff = time.time() - _IDEMPOTENCY_TTL
        expired = [k for k, v in _idempotency_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _idempotency_cache.pop(k, None)


# ---------------------------------------------------------------------------
# Webhook / callback helper
# ---------------------------------------------------------------------------
def _is_browser_same_origin(req: Request) -> bool:
    """Allow browser UI requests without an API key when they come from this deployment."""
    base = str(req.base_url).rstrip("/")
    origin = req.headers.get("origin", "").rstrip("/")
    referer = req.headers.get("referer", "").rstrip("/")
    if origin and (origin == base or origin.startswith(base + "/")):
        return True
    if referer and (referer == base or referer.startswith(base + "/")):
        return True
    return False


def _fire_webhook(callback_url: str, payload: dict):
    """POST payload to callback_url in a background thread. Best-effort."""
    def _do():
        try:
            with httpx.Client(timeout=10) as client:
                client.post(callback_url, json=payload)
            logger.info(f"Webhook delivered to {callback_url}")
        except Exception as e:
            logger.warning(f"Webhook delivery failed to {callback_url}: {e}")
    threading.Thread(target=_do, daemon=True).start()


API_TAGS = [
    {"name": "Certificates", "description": "Create, view, download, and verify tamper-proof certificates"},
    {"name": "Invoices", "description": "Generate tax invoices as downloadable PDFs"},
    {"name": "Verification", "description": "Verify certificate authenticity (single and batch)"},
    {"name": "Courses", "description": "List available courses"},
    {"name": "Admin", "description": "Admin endpoints for certificate and course management (requires X-Admin-Key)"},
    {"name": "System", "description": "Health checks and API metadata"},
]

app = FastAPI(
    title="PDF Cert Generator API",
    description=(
        "**API-first PDF certificate generation.**\n\n"
        "Generate tamper-proof participation and VTU-style internship completion certificates as downloadable PDFs with shareable URLs. "
        "All certificate data is encoded in the URL itself — signed with HMAC-SHA256, "
        "cryptographically verifiable without a database.\n\n"
        "## Authentication\n"
        "- **Certificate creation:** `X-API-Key` header (if `CERT_API_KEYS` is configured)\n"
        "- **Admin endpoints:** `X-Admin-Key` header\n"
        "- **Public endpoints:** No auth required (view, download, verify)\n\n"
        "## Agent / Automation Integration\n"
        "- OpenAPI spec: `GET /openapi.json`\n"
        "- Agent discovery: `GET /llms.txt`\n"
        "- Webhook callbacks: pass `callback_url` to receive async notifications\n"
        "- Idempotency: pass `idempotency_key` to prevent duplicate certificates\n"
        "- Batch verification: `POST /api/certificates/verify`\n"
    ),
    version="2.0.0",
    openapi_tags=API_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_type(status_code: int) -> str:
    mapping = {
        400: "validation_error",
        401: "authentication_error",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        503: "service_unavailable",
    }
    if status_code in mapping:
        return mapping[status_code]
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "internal_error"
    return "error"


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    kwargs: dict = {
        "status_code": exc.status_code,
        "content": {
            "error": {
                "code": exc.status_code,
                "message": message,
                "type": _error_type(exc.status_code),
            }
        },
    }
    if exc.headers:
        kwargs["headers"] = dict(exc.headers)
    return JSONResponse(**kwargs)


# ---------------------------------------------------------------------------
# Stateless certificate tokens (HMAC-SHA256 signed, no database required)
# ---------------------------------------------------------------------------


def _encode_cert(data: dict) -> str:
    """Encode certificate data into a URL-safe token with full HMAC-SHA256 signature."""
    compact = json.dumps(data, separators=(",", ":"), sort_keys=True)
    payload = base64.urlsafe_b64encode(compact.encode()).decode().rstrip("=")
    sig = hmac_mod.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _decode_cert(token: str) -> dict | None:
    """Decode and verify a certificate token. Returns None if invalid/tampered."""
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac_mod.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac_mod.compare_digest(sig, expected):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        return json.loads(raw)
    except Exception:
        return None


def _cert_id(data: dict) -> str:
    """Generate a short deterministic certificate ID for display."""
    if data.get("k") in ("i", "a"):
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True)
    else:
        raw = f"{data['n']}-{data['c']}-{data['d']}"
    return "CERT-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _is_internship_payload(data: dict) -> bool:
    return data.get("k") == "i"


def _is_appreciation_payload(data: dict) -> bool:
    return data.get("k") == "a"


def _certificate_kind_from_payload(data: dict) -> str:
    if _is_internship_payload(data):
        return "internship"
    if _is_appreciation_payload(data):
        return "appreciation"
    return "participation"


def _institution_clause_for_pdf(inst: str) -> str:
    t = (inst or "").strip()
    if not t:
        return ""
    return f"who is enrolled at <strong>{html_mod.escape(t)}</strong>, "


def _certificate_is_revoked(token: str) -> bool:
    """True if the token exists in the DB and is revoked. False if not revoked or not in DB."""
    if not _ensure_db_ready() or not db:
        return False
    try:
        with db.get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT revoked FROM certificates WHERE token_hash = %s",
                (db.token_hash(token),),
            )
            row = cur.fetchone()
            if row is None:
                return False
            return bool(row["revoked"])
    except Exception as e:
        logger.warning(f"Revocation check failed: {e}")
        return False


def _generate_qr_data_uri(url: str) -> str:
    """Generate a QR code as a base64-encoded PNG data URI."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


FOUNDER_NAME = os.environ.get("FOUNDER_NAME", "Girish Hiremath").strip()
FOUNDER_TITLE = os.environ.get("FOUNDER_TITLE", "Founder, Intelliforge AI").strip()
CERT_ORG_TAGLINE = _sanitize_env(
    os.environ.get("CERT_ORG_TAGLINE", "AN INTELLIFORGE AI INITIATIVE")
) or "AN INTELLIFORGE AI INITIATIVE"
CERT_BRAND_NAME = _sanitize_env(os.environ.get("CERT_BRAND_NAME", "IntelliForge Learning")) or "IntelliForge Learning"
CERT_PARTICIPATION_TITLE = _sanitize_env(
    os.environ.get("CERT_PARTICIPATION_TITLE", "Certificate of Participation")
) or "Certificate of Participation"
CERT_ISSUED_BY = _sanitize_env(os.environ.get("CERT_ISSUED_BY", "")) or CERT_BRAND_NAME
CERT_WEBSITE = _sanitize_env(os.environ.get("CERT_WEBSITE", "learning.intelliforge.tech")) or "learning.intelliforge.tech"
CERT_INTERNSHIP_ORG = _sanitize_env(
    os.environ.get("CERT_INTERNSHIP_ORG", "Intelliforge Digital Services")
) or "Intelliforge Digital Services"
CERT_INTERNSHIP_BRAND_PREFIX = _sanitize_env(
    os.environ.get("CERT_INTERNSHIP_BRAND_PREFIX", "IntelliForge")
) or "IntelliForge"
CERT_INTERNSHIP_BRAND_ACCENT = _sanitize_env(
    os.environ.get("CERT_INTERNSHIP_BRAND_ACCENT", "Forge")
) or "Forge"
CERT_APPRECIATION_ORG = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_ORG", "IntelliForge AI")
) or "IntelliForge AI"
CERT_APPRECIATION_ORG_BOLD = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_ORG_BOLD", "IntelliForge")
) or "IntelliForge"
CERT_APPRECIATION_ORG_LIGHT = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_ORG_LIGHT", "AI")
) or "AI"
CERT_APPRECIATION_PARTNER_ORG = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_PARTNER_ORG", "maidaan.academy")
) or "maidaan.academy"
CERT_APPRECIATION_TITLE_LINE1 = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_TITLE_LINE1", "CERTIFICATE")
) or "CERTIFICATE"
CERT_APPRECIATION_TITLE_LINE2 = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_TITLE_LINE2", "OF APPRECIATION")
) or "OF APPRECIATION"
CERT_APPRECIATION_PRESENTED_LABEL = _sanitize_env(
    os.environ.get(
        "CERT_APPRECIATION_PRESENTED_LABEL",
        "This certificate is proudly presented to",
    )
) or "This certificate is proudly presented to"
CERT_APPRECIATION_ACCENT = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_ACCENT", APPRECIATION_ACCENT_COLOR)
) or APPRECIATION_ACCENT_COLOR
CERT_APPRECIATION_SIDEBAR_COLOR = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_SIDEBAR_COLOR", APPRECIATION_SIDEBAR_COLOR)
) or APPRECIATION_SIDEBAR_COLOR
CERT_APPRECIATION_SECONDARY_COLOR = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_SECONDARY_COLOR", APPRECIATION_SECONDARY_COLOR)
) or APPRECIATION_SECONDARY_COLOR
CERT_APPRECIATION_HEADER_BG = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_HEADER_BG", APPRECIATION_HEADER_BG)
) or APPRECIATION_HEADER_BG
CERT_APPRECIATION_EVENT_COLOR = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_EVENT_COLOR", APPRECIATION_SECONDARY_COLOR)
) or APPRECIATION_SECONDARY_COLOR
CERT_APPRECIATION_AI_COLOR = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_AI_COLOR", "#7B6FFF")
) or "#7B6FFF"
CERT_APPRECIATION_HOST_NAME = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_HOST_NAME", APPRECIATION_HOST_NAME_DEFAULT)
) or APPRECIATION_HOST_NAME_DEFAULT
CERT_APPRECIATION_HOST_ORGANIZER = _sanitize_env(
    os.environ.get("CERT_APPRECIATION_HOST_ORGANIZER", APPRECIATION_HOST_ORGANIZER_DEFAULT)
) or APPRECIATION_HOST_ORGANIZER_DEFAULT
SITE_URL = _sanitize_env(os.environ.get("SITE_URL", "")).rstrip("/")
CONTACT_EMAIL = _sanitize_env(os.environ.get("CONTACT_EMAIL", "support@intelliforge.tech")) or "support@intelliforge.tech"
_signature_cache: dict[str, str] = {}


def _generate_signature_data_uri(name: str | None = None) -> str:
    """Render a signature as a base64 PNG data URI with a handwriting aesthetic."""
    signer = name or FOUNDER_NAME
    if signer in _signature_cache:
        return _signature_cache[signer]

    from PIL import Image, ImageDraw, ImageFont

    width, height = 360, 120
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default(size=36)

    bbox = draw.textbbox((0, 0), signer, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = (height - th) // 2 - 10

    draw.text((x, y), signer, fill=(26, 32, 44), font=font)

    shear = 0.15
    img = img.transform(
        (width, height), Image.AFFINE, (1, shear, -shear * height / 2, 0, 1, 0),
        resample=Image.BICUBIC, fillcolor=(255, 255, 255),
    )
    draw = ImageDraw.Draw(img)

    line_y = y + th + 12
    draw.line([(x - 10, line_y), (x + tw + 10, line_y)], fill=(80, 80, 100), width=1)

    buf = BytesIO()
    img.save(buf, format="PNG")
    data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
    _signature_cache[signer] = data_uri
    return data_uri


def certificate_branding() -> dict:
    """Branding shown on certificates, viewer pages, and the UI (via /api/info)."""
    return {
        "org_tagline": CERT_ORG_TAGLINE,
        "brand_name": CERT_BRAND_NAME,
        "participation_title": CERT_PARTICIPATION_TITLE,
        "issued_by": CERT_ISSUED_BY,
        "website": CERT_WEBSITE,
        "internship_org": CERT_INTERNSHIP_ORG,
        "internship_brand_prefix": CERT_INTERNSHIP_BRAND_PREFIX,
        "internship_brand_accent": CERT_INTERNSHIP_BRAND_ACCENT,
        "appreciation_org": CERT_APPRECIATION_ORG,
        "appreciation_org_bold": CERT_APPRECIATION_ORG_BOLD,
        "appreciation_org_light": CERT_APPRECIATION_ORG_LIGHT,
        "appreciation_partner_org": CERT_APPRECIATION_PARTNER_ORG,
        "appreciation_title_line1": CERT_APPRECIATION_TITLE_LINE1,
        "appreciation_title_line2": CERT_APPRECIATION_TITLE_LINE2,
        "appreciation_presented_label": CERT_APPRECIATION_PRESENTED_LABEL,
        "appreciation_accent": CERT_APPRECIATION_ACCENT,
        "appreciation_sidebar_color": CERT_APPRECIATION_SIDEBAR_COLOR,
        "appreciation_secondary_color": CERT_APPRECIATION_SECONDARY_COLOR,
        "appreciation_header_bg": CERT_APPRECIATION_HEADER_BG,
        "appreciation_event_color": CERT_APPRECIATION_EVENT_COLOR,
        "appreciation_ai_color": CERT_APPRECIATION_AI_COLOR,
        "appreciation_host_name": CERT_APPRECIATION_HOST_NAME,
        "appreciation_host_organizer": CERT_APPRECIATION_HOST_ORGANIZER,
        "founder_name": FOUNDER_NAME,
        "founder_title": FOUNDER_TITLE,
        "founder_signature_data_uri": _generate_signature_data_uri(FOUNDER_NAME),
    }


def _participation_branding_html() -> dict[str, str]:
    """Escaped branding fields for participation certificate HTML/PDF templates."""
    b = certificate_branding()
    return {
        "org_tagline": html_mod.escape(b["org_tagline"]),
        "brand_name": html_mod.escape(b["brand_name"]),
        "participation_title": html_mod.escape(b["participation_title"]),
        "participation_title_upper": html_mod.escape(b["participation_title"].upper()),
        "issued_by": html_mod.escape(b["issued_by"]),
        "website": html_mod.escape(b["website"]),
    }


def _internship_branding_html() -> dict[str, str]:
    b = certificate_branding()
    return {
        "internship_org": html_mod.escape(b["internship_org"]),
        "internship_brand_prefix": html_mod.escape(b["internship_brand_prefix"]),
        "internship_brand_accent": html_mod.escape(b["internship_brand_accent"]),
        "issued_by": html_mod.escape(b["issued_by"]),
        "website": html_mod.escape(b["website"]),
    }


def _appreciation_branding_html() -> dict[str, str]:
    b = certificate_branding()
    return {
        "appreciation_org": html_mod.escape(b["appreciation_org"]),
        "appreciation_org_bold": html_mod.escape(b["appreciation_org_bold"]),
        "appreciation_org_light": html_mod.escape(b["appreciation_org_light"]),
        "appreciation_partner_org": html_mod.escape(b["appreciation_partner_org"]),
        "title_line1": html_mod.escape(b["appreciation_title_line1"]),
        "title_line2": html_mod.escape(b["appreciation_title_line2"]),
        "presented_label": html_mod.escape(b["appreciation_presented_label"]),
        "issued_by": html_mod.escape(b["issued_by"]),
        "website": html_mod.escape(b["website"]),
        "accent_color": b["appreciation_accent"],
        "sidebar_color": b["appreciation_sidebar_color"],
        "secondary_color": b["appreciation_secondary_color"],
        "header_bg": b["appreciation_header_bg"],
        "event_color": b["appreciation_event_color"],
        "ai_color": b["appreciation_ai_color"],
    }


def _stacked_vertical_letters(word: str) -> str:
    return "<br/>".join(html_mod.escape(ch) for ch in word.upper() if ch != " ")


def _appreciation_pdf_sidebar(line1: str, line2: str, brand: dict | None = None) -> str:
    parts1 = _stacked_vertical_letters(line1)
    parts2 = "<br/><br/>".join(_stacked_vertical_letters(w) for w in line2.upper().split())
    gold = (brand or {}).get("appreciation_secondary_color", APPRECIATION_SECONDARY_COLOR)
    return (
        f'<table width="100%" height="100%"><tr><td align="center" valign="middle" '
        f'style="text-align:center;vertical-align:middle;border-left:3pt solid {gold};padding-top:8pt;">'
        f'<div style="color:#ffffff;font-weight:bold;font-size:11pt;line-height:1.12;">{parts1}</div>'
        f'<div style="color:#ffffff;font-size:5.5pt;letter-spacing:1pt;margin-top:14pt;line-height:1.2;">'
        f"{parts2}</div></td></tr></table>"
    )


def _appreciation_pdf_event_footer(
    event_name: str,
    host_name: str,
    brand: dict,
) -> str:
    return appreciation_event_footer_html(
        event_name,
        host_name,
        accent=brand.get("appreciation_accent", APPRECIATION_ACCENT_COLOR),
        secondary=brand.get("appreciation_secondary_color", APPRECIATION_SECONDARY_COLOR),
        sidebar_color=brand.get("appreciation_sidebar_color", APPRECIATION_SIDEBAR_COLOR),
        show_host=False,
    )


def _appreciation_viewer_event_block(event_name: str, host_name: str, brand: dict) -> str:
    if not event_name:
        return ""
    return (
        f'<div class="event-block">'
        f'<div class="event-bib">'
        f'<div class="event-label">&#9654; Event</div>'
        f'<div class="event-name">{html_mod.escape(event_name)}</div>'
        f"</div></div>"
    )


def _appreciation_auto_print_script(enable: bool) -> str:
    if not enable:
        return ""
    return """
    (function () {
        if (new URLSearchParams(location.search).get('print') !== '1') return;
        async function go() {
            if (document.fonts && document.fonts.ready) {
                try { await document.fonts.ready; } catch (e) {}
            }
            setTimeout(function () { window.print(); }, 400);
        }
        if (document.readyState === 'complete') go();
        else window.addEventListener('load', go);
    })();
    """


def _appreciation_host_for_payload(data: dict, brand: dict) -> str:
    return resolve_appreciation_host_name(
        (data.get("v") or "").strip(),
        (data.get("p") or "").strip(),
        brand.get("appreciation_host_name", CERT_APPRECIATION_HOST_NAME),
    )


def _default_appreciation_recognition(venue_name: str) -> str:
    venue = venue_name.strip()
    if not venue:
        return ""
    return (
        f"For your commendable participation in sports events organized by "
        f"{CERT_APPRECIATION_ORG} at {venue}."
    )


def _resolve_site_url(req: Request | None = None) -> str:
    if SITE_URL:
        return SITE_URL
    if req is not None:
        return str(req.base_url).rstrip("/")
    return "https://certs.intelliforge.tech"


def _json_ld_script(payload: dict) -> str:
    return (
        '<script type="application/ld+json">'
        f"{json.dumps(payload, ensure_ascii=False)}"
        "</script>"
    )


def _participation_json_ld(
    *,
    participant_name: str,
    course_name: str,
    completion_date: str,
    cert_id: str,
    page_url: str,
    brand_name: str,
    participation_title: str,
) -> str:
    return _json_ld_script(
        {
            "@context": "https://schema.org",
            "@type": "EducationalOccupationalCredential",
            "name": participation_title,
            "credentialCategory": "certificate",
            "identifier": cert_id,
            "url": page_url,
            "dateCreated": completion_date,
            "recognizedBy": {"@type": "Organization", "name": brand_name},
            "awardedTo": {"@type": "Person", "name": participant_name},
            "about": {"@type": "Course", "name": course_name},
        }
    )


def _internship_json_ld(
    *,
    participant_name: str,
    course_name: str,
    completion_date: str,
    cert_id: str,
    page_url: str,
    org_name: str,
    usn: str,
    duration_text: str,
    hours_text: str,
) -> str:
    return _json_ld_script(
        {
            "@context": "https://schema.org",
            "@type": "EducationalOccupationalCredential",
            "name": "Certificate of Internship Completion",
            "credentialCategory": "internship certificate",
            "identifier": cert_id,
            "url": page_url,
            "dateCreated": completion_date,
            "recognizedBy": {"@type": "Organization", "name": org_name},
            "awardedTo": {
                "@type": "Person",
                "name": participant_name,
                "identifier": usn,
            },
            "about": {
                "@type": "Course",
                "name": course_name,
                "timeRequired": duration_text,
                "educationalCredentialAwarded": f"{hours_text} internship hours",
            },
        }
    )


def _norm_signatory(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def _unique_signatory_roles(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Merge duplicate names; combine roles for the same signatory."""
    order: list[str] = []
    roles_by_key: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    for name, role in entries:
        n = (name or "").strip()
        if not n:
            continue
        key = _norm_signatory(n)
        if key not in roles_by_key:
            order.append(key)
            display[key] = n
            roles_by_key[key] = []
        r = (role or "").strip()
        if r and r not in roles_by_key[key]:
            roles_by_key[key].append(r)
    return [(display[k], " / ".join(roles_by_key[k])) for k in order]


def _same_signatory(a: str, b: str) -> bool:
    key = _norm_signatory(a)
    return bool(key) and key == _norm_signatory(b)


def _participation_viewer_meta_html(completion_date: str, instructor_name: str, cert_id: str) -> str:
    items = [
        (
            f'<div class="meta-item"><div class="meta-val">{html_mod.escape(completion_date)}</div>'
            f'<div class="meta-lbl">Date</div></div>'
        ),
    ]
    if not _same_signatory(instructor_name, FOUNDER_NAME):
        items.append(
            f'<div class="meta-item"><div class="meta-val">{html_mod.escape(instructor_name)}</div>'
            f'<div class="meta-lbl">Instructor</div></div>'
        )
    items.append(
        f'<div class="meta-item"><div class="meta-val">{html_mod.escape(cert_id)}</div>'
        f'<div class="meta-lbl">Certificate ID</div></div>'
    )
    return f'<div class="meta">{"".join(items)}</div>'


def _participation_pdf_meta_block(completion_date: str, instructor_name: str, certificate_id: str) -> str:
    if _same_signatory(instructor_name, FOUNDER_NAME):
        return f"""
        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="50%" align="center" style="text-align: center; padding: 12pt 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{html_mod.escape(completion_date)}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="50%" align="center" style="text-align: center; padding: 12pt 8pt; border-left: 1px solid #edf2f7;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{html_mod.escape(certificate_id)}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CERTIFICATE ID</td></tr>
                    </table>
                </td>
            </tr>
        </table>"""
    return f"""
        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="33%" align="center" style="text-align: center; padding: 12pt 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{html_mod.escape(completion_date)}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="34%" align="center" style="text-align: center; padding: 12pt 8pt; border-left: 1px solid #edf2f7; border-right: 1px solid #edf2f7;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{html_mod.escape(instructor_name)}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">INSTRUCTOR</td></tr>
                    </table>
                </td>
                <td width="33%" align="center" style="text-align: center; padding: 12pt 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{html_mod.escape(certificate_id)}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CERTIFICATE ID</td></tr>
                    </table>
                </td>
            </tr>
        </table>"""


def _viewer_signatures_html(signatories: list[tuple[str, str]]) -> str:
    blocks: list[str] = []
    for name, role in _unique_signatory_roles(signatories):
        blocks.append(
            f'<div class="sig-block">'
            f'<div class="sig-hand">{html_mod.escape(name)}</div>'
            f'<div class="sig-line"></div>'
            f'<div class="sig-role">{html_mod.escape(role)}</div>'
            f'</div>'
        )
    return f'<div class="signatures">{"".join(blocks)}</div>'


def _pdf_signature_cell(name: str, role: str, signature_uri: str, width_pct: int) -> str:
    return (
        f'<td width="{width_pct}%" align="center" style="text-align: center; padding: 8pt 12pt; vertical-align: bottom;">'
        f'<img src="{signature_uri}" width="150" height="50" />'
        f'<table width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td align="center" style="border-top: 1px solid #c4b5fd; font-size: 8pt; color: #553c9a; font-weight: bold; padding-top: 4pt; text-align: center;">'
        f'{html_mod.escape(name)}</td></tr>'
        f'<tr><td align="center" style="font-size: 6pt; color: #a0aec0; text-align: center; letter-spacing: 1pt;">'
        f'{html_mod.escape(role)}</td></tr>'
        f'</table></td>'
    )


def _pdf_internship_signature_cell(name: str, role: str, signature_uri: str, width_pct: int) -> str:
    return (
        f'<td width="{width_pct}%" align="center" style="vertical-align: bottom; padding: 6pt 8pt;">'
        f'<img src="{signature_uri}" width="130" height="44" />'
        f'<table width="100%"><tr><td style="border-top: 1px solid #cbd5e0; padding-top: 3pt; font-size: 7.5pt; font-weight: bold; color: #553c9a; text-align: center;">'
        f'{html_mod.escape(name)}</td></tr>'
        f'<tr><td style="font-size: 6pt; color: #718096; text-align: center; letter-spacing: 0.5pt;">'
        f'{html_mod.escape(role)}</td></tr></table></td>'
    )


def _participation_pdf_signatures_block(
    founder_name: str, founder_title: str, instructor_name: str, founder_sig: str, instructor_sig: str
) -> str:
    sig_by_key = {
        _norm_signatory(founder_name): founder_sig,
        _norm_signatory(instructor_name): instructor_sig,
    }
    entries = [(founder_name, founder_title), (instructor_name, "COURSE INSTRUCTOR")]
    unique = _unique_signatory_roles(entries)
    width = max(1, 100 // len(unique))
    cells = []
    for name, role in unique:
        uri = sig_by_key.get(_norm_signatory(name), founder_sig)
        cells.append(_pdf_signature_cell(name, role, uri, width))
    return f'<table width="70%" align="center" cellspacing="0" cellpadding="0"><tr>{"".join(cells)}</tr></table>'


def _internship_pdf_signatures_block(
    founder_name: str,
    mentor_name: str,
    instructor_name: str,
    founder_sig: str,
    mentor_sig: str,
    instructor_sig: str,
) -> str:
    sig_by_key = {
        _norm_signatory(founder_name): founder_sig,
        _norm_signatory(mentor_name): mentor_sig,
        _norm_signatory(instructor_name): instructor_sig,
    }
    entries = [
        (founder_name, "Authorised Signatory"),
        (mentor_name, "Industry Mentor"),
        (instructor_name, "Program Lead"),
    ]
    unique = _unique_signatory_roles(entries)
    width = max(1, 100 // len(unique))
    cells = []
    for name, role in unique:
        uri = sig_by_key.get(_norm_signatory(name), founder_sig)
        cells.append(_pdf_internship_signature_cell(name, role, uri, width))
    return f'<table width="88%" align="center" cellspacing="0" cellpadding="0"><tr>{"".join(cells)}</tr></table>'


class CertificateRequest(BaseModel):
    participant_name: str
    course_name: str = ""
    completion_date: str
    instructor_name: str = "Certificate Team"
    participant_email: str = ""
    callback_url: str = ""
    idempotency_key: str = ""
    certificate_kind: Literal["participation", "internship", "appreciation"] = "participation"
    usn: str = ""
    internship_duration: str = ""
    internship_hours: str = ""
    mentor_name: str = ""
    institution_name: str = ""
    recognition_text: str = ""
    event_name: str = ""
    venue_name: str = ""
    sponsor_label: str = ""

    @model_validator(mode="after")
    def _kind_required_fields(self):
        if self.certificate_kind == "internship":
            missing: list[str] = []
            if not self.usn.strip():
                missing.append("usn")
            if not self.internship_duration.strip():
                missing.append("internship_duration")
            if not self.internship_hours.strip():
                missing.append("internship_hours")
            if not self.mentor_name.strip():
                missing.append("mentor_name")
            if missing:
                raise ValueError(
                    "Internship certificates require non-empty: " + ", ".join(missing)
                )
        elif self.certificate_kind == "appreciation":
            if not self.recognition_text.strip() and not self.venue_name.strip():
                raise ValueError(
                    "Appreciation certificates require recognition_text or venue_name"
                )
        elif not self.course_name.strip():
            raise ValueError("course_name is required for participation certificates")
        return self


class InvoiceLineItemRequest(BaseModel):
    description: str
    rate: float
    rate_label: str = ""
    quantity: float
    quantity_label: str = ""


class InvoiceRequest(BaseModel):
    invoice_number: str = ""
    invoice_date: str
    bill_from_name: str
    bill_from_address: str = ""
    bill_from_email: str = ""
    bill_from_pan: str = ""
    bill_to_name: str
    bill_to_address: str = ""
    bill_to_gstin: str = ""
    bill_to_email: str = ""
    exchange_rate: float = 90.0
    signature_name: str = ""
    line_items: list[InvoiceLineItemRequest]
    idempotency_key: str = ""

    @model_validator(mode="after")
    def _invoice_required_fields(self):
        if not self.bill_from_name.strip():
            raise ValueError("bill_from_name is required")
        if not self.bill_to_name.strip():
            raise ValueError("bill_to_name is required")
        if not self.invoice_date.strip():
            raise ValueError("invoice_date is required")
        if not self.line_items:
            raise ValueError("At least one line item is required")
        for idx, item in enumerate(self.line_items, start=1):
            if not item.description.strip():
                raise ValueError(f"line_items[{idx}].description is required")
            if item.rate < 0 or item.quantity < 0:
                raise ValueError(f"line_items[{idx}] rate and quantity must be non-negative")
        if self.exchange_rate <= 0:
            raise ValueError("exchange_rate must be positive")
        return self


def _is_invoice_payload(data: dict) -> bool:
    return data.get("k") == "inv"


def _invoice_request_to_dict(request: InvoiceRequest) -> dict:
    invoice_number = request.invoice_number.strip() or default_invoice_number()
    signature_name = request.signature_name.strip() or request.bill_from_name.strip()
    items = []
    for item in request.line_items:
        items.append(
            {
                "description": item.description.strip(),
                "rate": float(item.rate),
                "rate_label": item.rate_label.strip(),
                "quantity": float(item.quantity),
                "quantity_label": item.quantity_label.strip(),
            }
        )
    return {
        "invoice_number": invoice_number,
        "invoice_date": request.invoice_date.strip(),
        "bill_from_name": request.bill_from_name.strip(),
        "bill_from_address": request.bill_from_address.strip(),
        "bill_from_email": request.bill_from_email.strip(),
        "bill_from_pan": request.bill_from_pan.strip(),
        "bill_to_name": request.bill_to_name.strip(),
        "bill_to_address": request.bill_to_address.strip(),
        "bill_to_gstin": request.bill_to_gstin.strip(),
        "bill_to_email": request.bill_to_email.strip(),
        "exchange_rate": float(request.exchange_rate),
        "signature_name": signature_name,
        "items": items,
    }


def _invoice_totals(data: dict) -> dict:
    _, total_usd = build_line_items_rows(data.get("items") or [])
    exchange_rate = float(data.get("exchange_rate") or 90)
    total_inr = int(round(total_usd * exchange_rate))
    return {
        "total_usd": total_usd,
        "total_inr": total_inr,
        "amount_in_words": amount_in_words_inr(total_inr),
        "total_usd_formatted": format_usd(total_usd),
        "total_inr_formatted": format_inr(total_inr),
    }


def _escape(value: str) -> str:
    return html_mod.escape(value or "", quote=True)



@app.get("/", tags=["System"])
async def root():
    """API root with version and available endpoints."""
    return {
        "status": "ok",
        "message": "PDF Cert Generator API is running",
        "version": "2.0.0",
        "endpoints": {
            "certificate": "/api/certificate",
            "invoice": "/api/invoice",
            "courses": "/api/courses",
            "health": "/api/health",
        }
    }


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check. Returns 200 if the service is running."""
    return {
        "status": "healthy",
        "service": "pdf-cert-generator-api",
        "version": "2.0.0",
        "dependencies": {
            "database": "connected" if DB_AVAILABLE else "not_configured",
            "email": "ready" if _agentmail_ready else ("configured" if _agentmail_client else "not_configured"),
        },
    }


@app.get("/api/info", tags=["System"])
async def get_info():
    """API metadata including version, features, branding, and tech stack."""
    return {
        "name": "PDF Cert Generator API",
        "version": "2.0.0",
        "description": "Generate and verify tamper-proof PDF certificates with shareable URLs",
        "branding": certificate_branding(),
        "invoice_brand": invoice_brand_colors(),
        "features": [
            "HMAC-SHA256 signed certificate tokens",
            "Stateless verification (no database)",
            "Public shareable certificate pages",
            "PDF certificate generation with QR codes",
            "VTU-style internship completion (USN, hours, mentor)",
            "Sports/event appreciation certificates (IntelliForge / maidaan poster theme)",
            "Tax invoice PDF generation (USD line items with INR conversion)",
            "LinkedIn and X social sharing",
        ],
        "tech_stack": {
            "framework": "FastAPI",
            "language": "Python",
            "pdf": "xhtml2pdf (certificate and invoice PDFs)",
            "crypto": "HMAC-SHA256",
        }
    }


@app.get("/api/preview/qr", tags=["System"])
async def preview_qr(url: str = ""):
    """Generate a QR code data URI for UI previews (does not create credentials)."""
    sample = url.strip() or "https://example.com/certificate/preview"
    return {"qr_data_uri": _generate_qr_data_uri(sample), "url": sample}


COURSES_FALLBACK = [
    "AI Product Development Fundamentals",
    "Building AI-Powered Applications",
    "Prompt Engineering & LLM Integration",
    "Full-Stack AI Development",
    "AI Product Design & UX",
    "Digital Profile Creation",
    "Deploying AI Solutions",
    "AI Code Reviewer Course",
    "VTU Industry Internship – IntelliForge AI Programme",
    "RAG Systems & Architecture Masterclass",
]


def _get_course_names() -> list[str]:
    if _ensure_db_ready() and db:
        try:
            return db.get_active_course_names()
        except Exception as e:
            logger.warning(f"DB course fetch failed, using fallback: {e}")
    return COURSES_FALLBACK


@app.get("/api/courses", tags=["Courses"])
async def get_courses():
    """List all active courses available for certificate generation."""
    return {"courses": _get_course_names()}


# ---------------------------------------------------------------------------
# Serif display font for the participation certificate (EB Garamond, SIL OFL).
# Bundled as a subset TTF under api/fonts/. xhtml2pdf embeds it via @font-face;
# if the file is missing at runtime (e.g. pruned from a deploy), the template
# falls back to Helvetica rather than failing. Family name must be a single
# unquoted token — xhtml2pdf does not strip quotes from a td's font-family, so
# a quoted name silently falls back to the body font.
# ---------------------------------------------------------------------------
_CERT_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "EBGaramond-SemiBold.ttf")
_CERT_DISPLAY_FONT_FAMILY = "GaramondPDF"
_CERT_FONT_AVAILABLE = os.path.exists(_CERT_FONT_PATH)

if _CERT_FONT_AVAILABLE:
    try:
        from reportlab.pdfbase import pdfmetrics as _pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont as _RLTTFont

        _pdfmetrics.registerFont(_RLTTFont(_CERT_DISPLAY_FONT_FAMILY, _CERT_FONT_PATH))
    except Exception as e:  # pragma: no cover - non-fatal, degrades to Helvetica
        logger.warning("Certificate display font registration failed: %s", e)
        _CERT_FONT_AVAILABLE = False


def _participation_font_face() -> str:
    """@font-face CSS registering the serif under both weights (name/brand/course
    tds carry font-weight:bold, so a normal-only face would fall back to bold
    Helvetica). Empty string when the font is unavailable."""
    if not _CERT_FONT_AVAILABLE:
        return ""
    url = _CERT_FONT_PATH.replace("\\", "/")
    return (
        f"@font-face {{ font-family: {_CERT_DISPLAY_FONT_FAMILY}; font-weight: normal;"
        f' src: url("{url}"); }}'
        f"@font-face {{ font-family: {_CERT_DISPLAY_FONT_FAMILY}; font-weight: bold;"
        f' src: url("{url}"); }}'
    )


def _pdf_link_callback(uri: str, rel: str) -> str:
    """Resolve local file paths (bundled fonts) for xhtml2pdf; pass through the
    base64 data: URIs used for QR codes and signatures unchanged."""
    if uri.startswith("data:"):
        return uri
    path = uri[7:] if uri.startswith("file://") else uri
    return path if os.path.isfile(path) else uri


def _build_cert_pdf(data: dict, verify_url: str = "") -> bytes:
    """Render certificate compact data into PDF bytes."""
    qr_data_uri = _generate_qr_data_uri(verify_url) if verify_url else ""
    cert_id = _cert_id(data)
    if _is_internship_payload(data):
        inst = (data.get("s") or "").strip()
        institution_clause = _institution_clause_for_pdf(inst)
        full_html = CERTIFICATE_INTERNSHIP_VTU_HTML.format(
            participant_name=html_mod.escape(data["n"]),
            course_name=html_mod.escape(data["c"]),
            completion_date=html_mod.escape(data["d"]),
            instructor_name=html_mod.escape(data["i"]),
            mentor_name=html_mod.escape(data["m"]),
            usn=html_mod.escape(data["u"]),
            duration_text=html_mod.escape(data["w"]),
            hours_text=html_mod.escape(data["h"]),
            certificate_id=html_mod.escape(cert_id),
            institution_clause=institution_clause,
            qr_data_uri=qr_data_uri,
            signatures_block=_internship_pdf_signatures_block(
                FOUNDER_NAME,
                data["m"],
                data["i"],
                _generate_signature_data_uri(),
                _generate_signature_data_uri(data["m"]),
                _generate_signature_data_uri(data["i"]),
            ),
        )
    elif _is_appreciation_payload(data):
        brand = certificate_branding()
        event_name = (data.get("e") or "").strip()
        host_name = _appreciation_host_for_payload(data, brand)
        venue = (data.get("v") or "").strip()
        sponsor = (data.get("p") or "").strip()
        full_html = CERTIFICATE_APPRECIATION_HTML.format(
            participant_name=html_mod.escape(data["n"]),
            recognition_text=html_mod.escape(data["r"]),
            completion_date=html_mod.escape(data["d"]),
            certificate_id=html_mod.escape(cert_id),
            qr_data_uri=qr_data_uri,
            presented_label=html_mod.escape(brand["appreciation_presented_label"]),
            accent_color=brand["appreciation_accent"],
            secondary_color=brand["appreciation_secondary_color"],
            sidebar_color=brand["appreciation_sidebar_color"],
            header_bg=brand["appreciation_header_bg"],
            event_color=brand["appreciation_event_color"],
            header_block=appreciation_header_html_from_branding(brand),
            header_stripe=appreciation_header_stripe_html(accent=brand["appreciation_accent"]),
            host_strip=appreciation_host_strip_from_branding(brand, venue, sponsor),
            accent_rail=appreciation_pdf_accent_rail(
                accent=brand["appreciation_accent"],
                secondary=brand["appreciation_secondary_color"],
            ),
            sport_seal=appreciation_sport_seal_html(
                accent=brand["appreciation_accent"],
                secondary=brand["appreciation_secondary_color"],
                sidebar_color=brand["appreciation_sidebar_color"],
            ),
            tricolor_footer=appreciation_pdf_tricolor_footer(),
            sidebar_stripes=appreciation_pdf_sidebar_stripes(
                accent=brand["appreciation_accent"],
                secondary=brand["appreciation_secondary_color"],
            ),
            sidebar_block=_appreciation_pdf_sidebar(
                brand["appreciation_title_line1"],
                brand["appreciation_title_line2"],
                brand,
            ),
            event_footer=_appreciation_pdf_event_footer(event_name, host_name, brand),
        )
    else:
        full_html = CERTIFICATE_PARTICIPATION_HTML.format(
            participant_name=data["n"],
            course_name=data["c"],
            completion_date=data["d"],
            instructor_name=data["i"],
            certificate_id=cert_id,
            meta_block=_participation_pdf_meta_block(data["d"], data["i"], cert_id),
            qr_data_uri=qr_data_uri,
            signatures_block=_participation_pdf_signatures_block(
                FOUNDER_NAME,
                FOUNDER_TITLE,
                data["i"],
                _generate_signature_data_uri(),
                _generate_signature_data_uri(data["i"]),
            ),
            font_face=_participation_font_face(),
            display_font=_CERT_DISPLAY_FONT_FAMILY if _CERT_FONT_AVAILABLE else "Helvetica",
            **_participation_branding_html(),
        )
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(
        src=full_html, dest=pdf_buffer, encoding="UTF-8", link_callback=_pdf_link_callback
    )
    if pisa_status.err:
        logging.error("PDF generation failed: %s", pisa_status.log)
        raise Exception("Error generating certificate PDF")
    if pisa_status.log:
        logging.warning("PDF generation warnings: %s", pisa_status.log)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


CERT_EMAIL_HTML = """
<div style="font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;background:#0f0f23;padding:24px;border-radius:16px;">
  <div style="background:linear-gradient(135deg,#12124a 0%,#1e1e6e 50%,#2a1a5e 100%);padding:28px 32px 24px;text-align:center;border-radius:12px 12px 0 0;">
    <div style="font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#d4af37;font-weight:600;">{org_tagline}</div>
    <div style="font-size:24px;font-weight:700;color:#fff;margin:8px 0 12px;">{brand_name}</div>
    <div style="display:inline-block;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#d4af37;font-weight:600;border:1px solid rgba(139,125,60,0.6);padding:6px 18px;border-radius:20px;">{participation_title}</div>
  </div>
  <div style="background:#ffffff;padding:32px;text-align:center;">
    <div style="display:inline-block;background:#f0fff4;border:1px solid #68d391;color:#276749;font-size:12px;font-weight:600;padding:5px 14px;border-radius:20px;margin-bottom:20px;">&#10003; Verified &amp; Authentic</div>
    <p style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#a0aec0;margin:0 0 6px;">This Certificate is Awarded To</p>
    <h1 style="font-size:28px;font-weight:700;color:#1a202c;margin:0 0 4px;">{participant_name}</h1>
    <div style="height:2px;background:linear-gradient(to right,transparent,#d4af37,transparent);margin:8px auto 16px;width:60%;"></div>
    <p style="font-size:16px;font-weight:600;color:#553c9a;margin:0 0 24px;">{course_name}</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #edf2f7;border-bottom:1px solid #edf2f7;margin-bottom:24px;">
      <tr>
        <td style="text-align:center;padding:14px 8px;width:33%;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;">{completion_date}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Date</div>
        </td>
        <td style="text-align:center;padding:14px 8px;width:34%;border-left:1px solid #edf2f7;border-right:1px solid #edf2f7;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;">{instructor_name}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Instructor</div>
        </td>
        <td style="text-align:center;padding:14px 8px;width:33%;">
          <div style="font-size:14px;font-weight:600;color:#2d3748;font-family:monospace;">{certificate_id}</div>
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Certificate ID</div>
        </td>
      </tr>
    </table>
    <a href="{view_url}" style="display:inline-block;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:14px 36px;border-radius:12px;font-size:16px;font-weight:600;text-decoration:none;margin-bottom:12px;">View Your Certificate</a>
    <p style="font-size:12px;color:#a0aec0;margin:12px 0 0;">Or download the PDF directly: <a href="{download_url}" style="color:#667eea;text-decoration:none;font-weight:500;">Download PDF</a></p>
  </div>
  <div style="background:#f8fafc;padding:16px 32px;text-align:center;border-radius:0 0 12px 12px;border-top:1px solid #edf2f7;">
    <p style="font-size:12px;color:#a0aec0;margin:0;">Issued by <a href="/" style="color:#667eea;text-decoration:none;">{issued_by}</a> &middot; <a href="mailto:support@example.com" style="color:#667eea;text-decoration:none;">support@example.com</a></p>
  </div>
</div>
"""


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
    """Return cached inbox id, or the configured default without an API round-trip."""
    if _agentmail_inbox_cached:
        return _agentmail_inbox_cached
    return AGENTMAIL_INBOX_ID if _agentmail_client else ""


def _refresh_agentmail_inbox_from_api(*, force: bool = False) -> str:
    """Resolve inbox id via AgentMail list API and cache the result."""
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
    """Background warm-up so the first certificate email does not pay for inbox lookup."""
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


def _agentmail_send_message(
    inbox_id: str, *, recipient: str, subject: str, text: str, html: str
) -> None:
    _agentmail_client.inboxes.messages.send(
        inbox_id,
        to=recipient,
        subject=subject,
        text=text,
        html=html,
    )


def _agentmail_deliver(
    *, to_email: str, subject: str, text: str, html: str, link_hint: str = "certificate"
) -> tuple[bool, str]:
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
        _agentmail_send_message(
            inbox_id,
            recipient=recipient,
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
                    _agentmail_send_message(
                        resolved,
                        recipient=recipient,
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


def _send_certificate_email(
    to_email: str,
    participant_name: str,
    course_name: str,
    completion_date: str,
    instructor_name: str,
    certificate_id: str,
    view_url: str,
    download_url: str,
) -> tuple[bool, str]:
    """Send certificate notification email via AgentMail."""
    html = CERT_EMAIL_HTML.format(
        participant_name=participant_name,
        course_name=course_name,
        completion_date=completion_date,
        instructor_name=instructor_name,
        certificate_id=certificate_id,
        view_url=view_url,
        download_url=download_url,
        **_participation_branding_html(),
    )
    brand = CERT_BRAND_NAME
    title = CERT_PARTICIPATION_TITLE
    return _agentmail_deliver(
        to_email=to_email,
        subject=f"Your Certificate – {course_name}",
        text=(
            f"Congratulations {participant_name}!\n\n"
            f"You have been awarded a {title} for completing "
            f"{course_name} at {brand}.\n\n"
            f"Certificate ID: {certificate_id}\n"
            f"View your certificate: {view_url}\n"
            f"Download PDF: {download_url}\n\n"
            f"Share this achievement on LinkedIn or X!\n\n"
            f"– {brand} Team"
        ),
        html=html,
    )


def _send_internship_certificate_email(
    to_email: str,
    participant_name: str,
    course_name: str,
    completion_date: str,
    instructor_name: str,
    mentor_name: str,
    usn: str,
    duration_text: str,
    hours_text: str,
    certificate_id: str,
    view_url: str,
    download_url: str,
) -> tuple[bool, str]:
    """Send VTU-style internship certificate email via AgentMail."""
    html = CERT_EMAIL_INTERNSHIP_HTML.format(
        participant_name=participant_name,
        course_name=course_name,
        completion_date=completion_date,
        instructor_name=instructor_name,
        mentor_name=mentor_name,
        usn=usn,
        duration_text=duration_text,
        hours_text=hours_text,
        certificate_id=certificate_id,
        view_url=view_url,
        download_url=download_url,
    )
    return _agentmail_deliver(
        to_email=to_email,
        subject=f"Your internship certificate – {course_name}",
        text=(
            f"Congratulations {participant_name} (USN {usn})!\n\n"
            f"Your industry internship completion certificate for {course_name} is ready.\n"
            f"Duration: {duration_text} · Contact hours: {hours_text}\n"
            f"Mentor: {mentor_name} · Program lead: {instructor_name}\n\n"
            f"Certificate ID: {certificate_id}\n"
            f"View: {view_url}\n"
            f"Download PDF: {download_url}\n\n"
            f"– PDF Cert Generator"
        ),
        html=html,
    )


@app.post("/api/certificate", tags=["Certificates"])
async def generate_certificate(request: CertificateRequest, req: Request):
    """
    Generate a signed certificate and return shareable URL + PDF download URL.

    **Participation (default):** `certificate_kind` omitted or `"participation"` — standard course certificate.

    **Internship (VTU / college records):** set `certificate_kind` to `"internship"` and include
    `usn`, `internship_duration`, `internship_hours`, and `mentor_name` (plus optional `institution_name`).

    **Appreciation (sports / events):** set `certificate_kind` to `"appreciation"` with
    `recognition_text` (or `venue_name` for auto-generated copy), plus optional `event_name`,
    `sponsor_label`, and `venue_name`. Course list validation is skipped; PDF uses the landscape
    appreciation layout with verifiable QR.

    **Idempotency:** Pass `idempotency_key` to safely retry without creating duplicates.
    The cached result is returned for 1 hour.

    **Webhook:** Pass `callback_url` to receive an async POST with the certificate data
    after creation. Useful for automation pipelines.

    **Email:** Pass `participant_email` to automatically email the certificate to the participant.
    """
    try:
        if request.idempotency_key:
            cached = _check_idempotency(request.idempotency_key)
            if cached:
                return JSONResponse(cached)

        if CERT_API_KEYS:
            api_key = req.headers.get("X-API-Key", "")
            if not _is_browser_same_origin(req) and api_key not in CERT_API_KEYS:
                raise HTTPException(status_code=401, detail="Invalid or missing API key")

        client_ip = req.client.host if req.client else "unknown"
        allowed, rate_headers = _check_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers=rate_headers,
            )

        valid_courses = _get_course_names() if request.certificate_kind != "appreciation" else []
        name = request.participant_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Participant name is required")

        lead = request.instructor_name.strip() or "IntelliForge AI Team"

        if request.certificate_kind == "appreciation":
            recognition = request.recognition_text.strip()
            if not recognition:
                recognition = _default_appreciation_recognition(request.venue_name)
            if not recognition:
                raise HTTPException(
                    status_code=400,
                    detail="recognition_text or venue_name is required for appreciation certificates",
                )
            program = (
                request.event_name.strip()
                or request.course_name.strip()
                or "Sports Event"
            )
            course_for_db = program
            cert_data: dict = {
                "k": "a",
                "n": name,
                "c": program,
                "d": request.completion_date,
                "r": recognition,
                "i": lead,
            }
            if request.event_name.strip():
                cert_data["e"] = request.event_name.strip()
            if request.venue_name.strip():
                cert_data["v"] = request.venue_name.strip()
            if request.sponsor_label.strip():
                cert_data["p"] = request.sponsor_label.strip()
        else:
            if request.course_name not in valid_courses:
                raise HTTPException(status_code=400, detail=f"Unknown course: {request.course_name}")
            course_for_db = request.course_name
            cert_data = {
                "n": name,
                "c": request.course_name,
                "d": request.completion_date,
                "i": lead,
            }
            if request.certificate_kind == "internship":
                cert_data["k"] = "i"
                cert_data["u"] = request.usn.strip()
                cert_data["w"] = request.internship_duration.strip()
                cert_data["h"] = request.internship_hours.strip()
                cert_data["m"] = request.mentor_name.strip()
                if request.institution_name.strip():
                    cert_data["s"] = request.institution_name.strip()
        token = _encode_cert(cert_data)
        cert_id = _cert_id(cert_data)

        participant_email = request.participant_email.strip() if request.participant_email else ""

        if _ensure_db_ready() and db:
            try:
                db.store_certificate(
                    certificate_id=cert_id,
                    token=token,
                    participant_name=name,
                    course_name=course_for_db,
                    completion_date=request.completion_date,
                    instructor_name=lead,
                    client_ip=client_ip,
                    participant_email=participant_email,
                )
            except Exception as e:
                logger.warning(f"Failed to store certificate in DB (cert still valid): {e}")

        base_url = str(req.base_url).rstrip("/")
        shareable_url = f"{base_url}/certificate/{token}"
        download_url = f"{shareable_url}/download"

        email_sent = False
        email_error = ""
        if participant_email:
            def _send_email():
                if request.certificate_kind == "internship":
                    return _send_internship_certificate_email(
                        to_email=participant_email,
                        participant_name=name,
                        course_name=course_for_db,
                        completion_date=request.completion_date,
                        instructor_name=lead,
                        mentor_name=request.mentor_name.strip(),
                        usn=request.usn.strip(),
                        duration_text=request.internship_duration.strip(),
                        hours_text=request.internship_hours.strip(),
                        certificate_id=cert_id,
                        view_url=shareable_url,
                        download_url=download_url,
                    )
                email_label = (
                    recognition[:80] + "…"
                    if request.certificate_kind == "appreciation" and len(recognition) > 80
                    else course_for_db
                )
                return _send_certificate_email(
                    to_email=participant_email,
                    participant_name=name,
                    course_name=email_label,
                    completion_date=request.completion_date,
                    instructor_name=lead,
                    certificate_id=cert_id,
                    view_url=shareable_url,
                    download_url=download_url,
                )

            email_result = _run_with_timeout(
                _send_email,
                EMAIL_SEND_TIMEOUT_SEC,
                f"Email delivery timed out for {participant_email}",
            )
            if email_result is None:
                email_sent = False
                email_error = "Email delivery timed out. Share the certificate link instead."
            else:
                email_sent, email_error = email_result

        logger.info(f"Certificate issued for {name} – {course_for_db}")

        response_data = {
            "certificate_id": cert_id,
            "token": token,
            "url": shareable_url,
            "download_url": download_url,
            "participant_name": name,
            "course_name": course_for_db,
            "certificate_kind": request.certificate_kind,
            "email_sent": email_sent,
            "email_error": email_error,
            "request_id": str(uuid_mod.uuid4()),
        }
        if request.certificate_kind == "internship":
            response_data["usn"] = request.usn.strip()
            response_data["internship_duration"] = request.internship_duration.strip()
            response_data["internship_hours"] = request.internship_hours.strip()
            response_data["mentor_name"] = request.mentor_name.strip()
            if request.institution_name.strip():
                response_data["institution_name"] = request.institution_name.strip()
        elif request.certificate_kind == "appreciation":
            response_data["recognition_text"] = recognition
            if request.event_name.strip():
                response_data["event_name"] = request.event_name.strip()
            if request.venue_name.strip():
                response_data["venue_name"] = request.venue_name.strip()
            if request.sponsor_label.strip():
                response_data["sponsor_label"] = request.sponsor_label.strip()

        if request.idempotency_key:
            _store_idempotency(request.idempotency_key, response_data)

        if request.callback_url:
            _fire_webhook(request.callback_url, {
                "event": "certificate.created",
                "data": response_data,
            })

        return JSONResponse(response_data, headers=rate_headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating certificate: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {e}")


@app.post("/api/invoice", tags=["Invoices"])
async def generate_invoice(request: InvoiceRequest, req: Request):
    """
    Generate a signed tax invoice and return shareable download URL + totals.

    Line items are priced in USD; INR total uses `exchange_rate` (default 90).
    Pass `idempotency_key` to safely retry without creating duplicate tokens.
    """
    try:
        if request.idempotency_key:
            cached = _check_idempotency(request.idempotency_key)
            if cached:
                return JSONResponse(cached)

        if CERT_API_KEYS:
            api_key = req.headers.get("X-API-Key", "")
            if not _is_browser_same_origin(req) and api_key not in CERT_API_KEYS:
                raise HTTPException(status_code=401, detail="Invalid or missing API key")

        client_ip = req.client.host if req.client else "unknown"
        allowed, rate_headers = _check_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers=rate_headers,
            )

        invoice_data = _invoice_request_to_dict(request)
        compact = compact_invoice_token_payload(invoice_data)
        token = _encode_cert(compact)
        base_url = str(req.base_url).rstrip("/")
        download_url = f"{base_url}/invoice/{token}/download"
        totals = _invoice_totals(invoice_data)

        response_data = {
            "invoice_number": invoice_data["invoice_number"],
            "token": token,
            "download_url": download_url,
            "bill_from_name": invoice_data["bill_from_name"],
            "bill_to_name": invoice_data["bill_to_name"],
            "invoice_date": invoice_data["invoice_date"],
            "exchange_rate": invoice_data["exchange_rate"],
            "total_usd": totals["total_usd"],
            "total_inr": totals["total_inr"],
            "total_usd_formatted": totals["total_usd_formatted"],
            "total_inr_formatted": totals["total_inr_formatted"],
            "amount_in_words": totals["amount_in_words"],
            "request_id": str(uuid_mod.uuid4()),
        }

        if request.idempotency_key:
            _store_idempotency(request.idempotency_key, response_data)

        logger.info(
            f"Invoice issued {invoice_data['invoice_number']} — "
            f"{invoice_data['bill_to_name']} ({totals['total_inr_formatted']})"
        )
        return JSONResponse(response_data, headers=rate_headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating invoice: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate invoice: {e}")


@app.get("/invoice/{token}/download", tags=["Invoices"])
async def download_invoice(token: str):
    """Download a tax invoice PDF from a signed token."""
    data = _decode_cert(token)
    if not data or not _is_invoice_payload(data):
        raise HTTPException(status_code=404, detail="Invoice not found or invalid token")

    invoice_data = expand_invoice_token_payload(data)
    pdf_bytes = build_invoice_pdf(invoice_data)
    safe_number = invoice_data["invoice_number"].replace(" ", "_").replace("/", "-")
    filename = f"Invoice_{safe_number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ---------------------------------------------------------------------------
# Public certificate viewer page (server-rendered HTML)
# ---------------------------------------------------------------------------
VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{participant_name} – Certificate</title>
    <meta name="description" content="{meta_description}" />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="{page_url}" />
    <meta property="og:title" content="{participant_name} – {participation_title}" />
    <meta property="og:description" content="{meta_description}" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="{page_url}" />
    <meta property="og:site_name" content="{brand_name}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{participant_name} – {participation_title}" />
    <meta name="twitter:description" content="{meta_description}" />
    {json_ld}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600;700&family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
    <style>
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#0f0f23;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem}}
        .bg-glow{{position:fixed;inset:0;background:radial-gradient(ellipse at 30% 20%,rgba(102,126,234,.18) 0%,transparent 50%),radial-gradient(ellipse at 70% 80%,rgba(118,75,162,.15) 0%,transparent 50%);pointer-events:none}}
        .card{{position:relative;background:#fff;border-radius:24px;box-shadow:0 30px 100px rgba(0,0,0,.35);max-width:560px;width:100%;overflow:hidden;animation:up .6s ease-out}}
        @keyframes up{{from{{opacity:0;transform:translateY(40px)}}to{{opacity:1;transform:translateY(0)}}}}

        .card-header{{background:linear-gradient(135deg,#12124a 0%,#1e1e6e 50%,#2a1a5e 100%);padding:2.2rem 2.5rem 2rem;text-align:center;position:relative;overflow:hidden}}
        .card-header::before{{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle,rgba(212,175,55,.06) 0%,transparent 60%);pointer-events:none}}
        .hdr-org{{font-size:.6rem;letter-spacing:4px;text-transform:uppercase;color:#d4af37;margin-bottom:.35rem;font-weight:500}}
        .hdr-brand{{font-family:'Playfair Display',serif;font-size:1.5rem;color:#fff;font-weight:700;margin-bottom:.8rem}}
        .hdr-badge{{display:inline-block;background:rgba(212,175,55,.12);border:1px solid rgba(212,175,55,.4);color:#d4af37;font-size:.6rem;font-weight:600;letter-spacing:2.5px;text-transform:uppercase;padding:.35rem 1.2rem;border-radius:20px}}

        .card-body{{padding:2.5rem 2.5rem 2rem;text-align:center}}
        .verified{{display:inline-flex;align-items:center;gap:.4rem;background:#f0fff4;border:1px solid #68d391;color:#22543d;font-size:.7rem;font-weight:600;padding:.3rem .9rem;border-radius:20px;margin-bottom:1.6rem}}
        .verified svg{{width:14px;height:14px}}
        .label{{font-size:.7rem;letter-spacing:2.5px;text-transform:uppercase;color:#a0aec0;margin-bottom:.4rem}}
        .name{{font-family:'Playfair Display',serif;font-size:2.1rem;font-weight:700;color:#1a202c;line-height:1.15;margin-bottom:.15rem}}
        .divider{{height:1px;background:linear-gradient(to right,transparent,#d4af37,transparent);margin:.8rem 2rem 1rem}}
        .course{{font-size:.95rem;color:#553c9a;font-weight:600;margin-bottom:1.6rem}}

        .meta{{display:flex;justify-content:center;gap:1.8rem;margin-bottom:2rem;flex-wrap:wrap}}
        .meta-item{{text-align:center}}
        .meta-val{{font-size:.82rem;color:#2d3748;font-weight:500}}
        .meta-lbl{{font-size:.6rem;color:#a0aec0;text-transform:uppercase;letter-spacing:1px;margin-top:.15rem}}

        .actions{{display:flex;flex-direction:column;gap:.7rem;align-items:center}}
        .btn-download{{display:inline-flex;align-items:center;gap:.6rem;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;padding:.85rem 2.2rem;border-radius:12px;font-size:.95rem;font-weight:600;cursor:pointer;text-decoration:none;transition:all .3s;box-shadow:0 4px 20px rgba(102,126,234,.35)}}
        .btn-download:hover{{transform:translateY(-2px);box-shadow:0 8px 30px rgba(102,126,234,.5)}}
        .btn-download svg{{width:18px;height:18px}}
        .share-row{{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:center}}
        .btn-share{{display:inline-flex;align-items:center;gap:.45rem;padding:.55rem 1.1rem;border-radius:8px;font-size:.78rem;font-weight:600;text-decoration:none;transition:all .2s;border:1.5px solid #e2e8f0;color:#4a5568;background:#fff}}
        .btn-share:hover{{border-color:#a0aec0;background:#f7fafc}}
        .btn-linkedin{{border-color:#0077b5;color:#0077b5}}
        .btn-linkedin:hover{{background:#f0f7ff;border-color:#005e93}}
        .btn-twitter{{border-color:#1da1f2;color:#1da1f2}}
        .btn-twitter:hover{{background:#f0f9ff;border-color:#0c85d0}}
        .btn-share svg{{width:15px;height:15px}}

        .signatures{{display:flex;justify-content:center;gap:3rem;margin-bottom:1.8rem;flex-wrap:wrap}}
        .sig-block{{text-align:center;min-width:140px}}
        .sig-hand{{font-family:'Dancing Script',cursive;font-size:1.5rem;color:#1a202c;margin-bottom:.2rem;opacity:.85}}
        .sig-line{{height:1px;background:#c4b5fd;margin:.25rem 0}}
        .sig-name{{font-size:.75rem;color:#553c9a;font-weight:600;margin-top:.3rem}}
        .sig-role{{font-size:.6rem;color:#a0aec0;letter-spacing:1px;text-transform:uppercase;margin-top:.1rem}}

        .qr-section{{display:flex;align-items:center;justify-content:center;gap:.8rem;margin-top:1.2rem;padding-top:1.2rem;border-top:1px solid #f0f0f0}}
        .qr-section img{{border-radius:6px;border:1px solid #e2e8f0}}
        .qr-text{{font-size:.65rem;color:#a0aec0;text-align:left;line-height:1.5}}
        .qr-text strong{{color:#4a5568;display:block;font-size:.7rem}}

        .card-footer{{background:#f8fafc;border-top:1px solid #edf2f7;padding:1rem 2.5rem;text-align:center}}
        .card-footer p{{font-size:.7rem;color:#a0aec0;line-height:1.6}}
        .card-footer a{{color:#667eea;text-decoration:none}}
        .card-footer a:hover{{text-decoration:underline}}

        @media(max-width:480px){{
            body{{padding:1rem}}
            .card-body{{padding:1.5rem}}
            .name{{font-size:1.5rem}}
            .meta{{gap:1rem}}
            .share-row{{flex-direction:column;align-items:stretch}}
        }}
    </style>
</head>
<body>
    <div class="bg-glow"></div>
    <div class="card">
        <div class="card-header">
            <div class="hdr-org">{org_tagline}</div>
            <div class="hdr-brand">{brand_name}</div>
            <div class="hdr-badge">{participation_title}</div>
        </div>
        <div class="card-body">
            <div class="verified">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified &amp; Authentic
            </div>
            <div class="label">This certificate is awarded to</div>
            <div class="name">{participant_name}</div>
            <div class="divider"></div>
            <div class="course">{course_name}</div>
            {meta_html}
            {signatures_html}
            <div class="actions">
                <a class="btn-download" href="{download_url}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Download Certificate
                </a>
                <div class="share-row">
                    <a class="btn-share btn-linkedin" href="{linkedin_url}" target="_blank" rel="noopener noreferrer">
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.5 2h-17A1.5 1.5 0 002 3.5v17A1.5 1.5 0 003.5 22h17a1.5 1.5 0 001.5-1.5v-17A1.5 1.5 0 0020.5 2zM8 19H5v-9h3zM6.5 8.25A1.75 1.75 0 118.3 6.5a1.78 1.78 0 01-1.8 1.75zM19 19h-3v-4.74c0-1.42-.6-1.93-1.38-1.93A1.74 1.74 0 0013 14.19V19h-3v-9h2.9v1.3a3.11 3.11 0 012.7-1.4c1.55 0 3.36.86 3.36 3.66z"/></svg>
                        Share on LinkedIn
                    </a>
                    <a class="btn-share btn-twitter" href="{twitter_url}" target="_blank" rel="noopener noreferrer">
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                        Share on X
                    </a>
                </div>
            </div>
            <div class="qr-section">
                <img src="{qr_data_uri}" alt="QR Code" width="80" height="80" />
                <div class="qr-text"><strong>Scan to Verify</strong>This QR code links to this certificate's<br/>permanent verification page.</div>
            </div>
        </div>
        <div class="card-footer">
            <p>
                Issued by <a href="/" target="_blank" rel="noopener">{issued_by}</a>
                &nbsp;&middot;&nbsp; {website}
            </p>
        </div>
    </div>
</body>
</html>"""


def _resolve_cert(token: str):
    """Decode a certificate token or raise 404."""
    data = _decode_cert(token)
    if data is None:
        raise HTTPException(status_code=404, detail="Invalid or tampered certificate")
    return data


@app.get("/certificate/{token}", tags=["Certificates"], include_in_schema=False)
async def view_certificate(token: str, req: Request):
    """Public certificate viewer – serves a styled HTML page."""
    data = _resolve_cert(token)

    base_url = str(req.base_url).rstrip("/")
    page_url = f"{base_url}/certificate/{token}"
    download_url = f"{page_url}/download"
    auto_print = req.query_params.get("print") == "1"

    linkedin_params = urlencode({"url": page_url})
    linkedin_url = f"https://www.linkedin.com/sharing/share-offsite/?{linkedin_params}"

    if _is_internship_payload(data):
        cert_desc = (
            f"I completed my industry internship ({data['c']}) — USN {data['u']}!"
        )
        twitter_params = urlencode({"text": cert_desc, "url": page_url})
        twitter_url = f"https://twitter.com/intent/tweet?{twitter_params}"
        inst = (data.get("s") or "").strip()
        institution_block = (
            f'<div class="inst">{html_mod.escape(inst)}</div>' if inst else ""
        )
        cert_id = _cert_id(data)
        internship_brand = certificate_branding()
        meta_description = html_mod.escape(
            f"Verified VTU internship certificate: {data['n']} (USN {data['u']}) completed "
            f"{data['c']} at {internship_brand['internship_org']} — {data['w']}, {data['h']}."
        )
        html = VIEWER_INTERNSHIP_HTML.format(
            participant_name=html_mod.escape(data["n"]),
            usn=html_mod.escape(data["u"]),
            course_name=html_mod.escape(data["c"]),
            completion_date=html_mod.escape(data["d"]),
            instructor_name=html_mod.escape(data["i"]),
            mentor_name=html_mod.escape(data["m"]),
            duration_text=html_mod.escape(data["w"]),
            hours_text=html_mod.escape(data["h"]),
            cert_id=html_mod.escape(cert_id),
            institution_block=institution_block,
            page_url=page_url,
            download_url=download_url,
            linkedin_url=linkedin_url,
            twitter_url=twitter_url,
            qr_data_uri=_generate_qr_data_uri(page_url),
            meta_description=meta_description,
            json_ld=_internship_json_ld(
                participant_name=data["n"],
                course_name=data["c"],
                completion_date=data["d"],
                cert_id=cert_id,
                page_url=page_url,
                org_name=internship_brand["internship_org"],
                usn=data["u"],
                duration_text=data["w"],
                hours_text=data["h"],
            ),
            signatures_html=_viewer_signatures_html([
                (FOUNDER_NAME, "Authorised signatory"),
                (data["m"], "Industry mentor"),
                (data["i"], "Program lead"),
            ]),
            **_internship_branding_html(),
        )
    elif _is_appreciation_payload(data):
        cert_desc = f"I received a Certificate of Appreciation — {data['n']}!"
        twitter_params = urlencode({"text": cert_desc, "url": page_url})
        twitter_url = f"https://twitter.com/intent/tweet?{twitter_params}"
        cert_id = _cert_id(data)
        appreciation_brand = certificate_branding()
        event_name = (data.get("e") or "").strip()
        host_name = _appreciation_host_for_payload(data, appreciation_brand)
        venue = (data.get("v") or "").strip()
        sponsor = (data.get("p") or "").strip()
        meta_description = html_mod.escape(
            f"Verified Certificate of Appreciation for {data['n']}: {data['r'][:120]}"
        )
        html = VIEWER_APPRECIATION_HTML.format(
            participant_name=html_mod.escape(data["n"]),
            recognition_text=html_mod.escape(data["r"]),
            completion_date=html_mod.escape(data["d"]),
            cert_id=html_mod.escape(cert_id),
            event_block=_appreciation_viewer_event_block(
                event_name, host_name, appreciation_brand
            ),
            host_strip=appreciation_host_strip_from_branding(appreciation_brand, venue, sponsor),
            page_url=page_url,
            download_url=download_url,
            linkedin_url=linkedin_url,
            twitter_url=twitter_url,
            qr_data_uri=_generate_qr_data_uri(page_url),
            meta_description=meta_description,
            json_ld=_json_ld_script({
                "@context": "https://schema.org",
                "@type": "EducationalOccupationalCredential",
                "name": "Certificate of Appreciation",
                "credentialCategory": "certificate",
                "recognizedBy": {"@type": "Organization", "name": appreciation_brand["appreciation_org"]},
                "about": data["r"],
                "dateCreated": data["d"],
                "identifier": cert_id,
                "url": page_url,
            }),
            header_block=appreciation_header_html_from_branding(appreciation_brand),
            auto_print_script=_appreciation_auto_print_script(auto_print),
            **_appreciation_branding_html(),
        )
    else:
        cert_desc = f"I completed {data['c']} at {CERT_BRAND_NAME}!"
        twitter_params = urlencode({"text": cert_desc, "url": page_url})
        twitter_url = f"https://twitter.com/intent/tweet?{twitter_params}"
        brand_html = _participation_branding_html()
        cert_id = _cert_id(data)
        meta_description = html_mod.escape(
            f"Verified {CERT_PARTICIPATION_TITLE}: {data['n']} completed {data['c']} at {CERT_BRAND_NAME}."
        )
        html = VIEWER_HTML.format(
            participant_name=data["n"],
            course_name=data["c"],
            completion_date=data["d"],
            instructor_name=data["i"],
            cert_id=cert_id,
            meta_html=_participation_viewer_meta_html(data["d"], data["i"], cert_id),
            page_url=page_url,
            download_url=download_url,
            linkedin_url=linkedin_url,
            twitter_url=twitter_url,
            qr_data_uri=_generate_qr_data_uri(page_url),
            meta_description=meta_description,
            json_ld=_participation_json_ld(
                participant_name=data["n"],
                course_name=data["c"],
                completion_date=data["d"],
                cert_id=cert_id,
                page_url=page_url,
                brand_name=CERT_BRAND_NAME,
                participation_title=CERT_PARTICIPATION_TITLE,
            ),
            signatures_html=_viewer_signatures_html([
                (FOUNDER_NAME, FOUNDER_TITLE),
                (data["i"], "Course Instructor"),
            ]),
            **brand_html,
        )
    return HTMLResponse(content=html)


@app.get("/certificate/{token}/download", tags=["Certificates"])
async def download_certificate(token: str, req: Request):
    """Download a certificate. Appreciation certs open the viewer print dialog (WYSIWYG PDF)."""
    data = _resolve_cert(token)
    base_url = str(req.base_url).rstrip("/")

    if _is_appreciation_payload(data):
        return RedirectResponse(
            url=f"{base_url}/certificate/{token}?print=1",
            status_code=302,
        )

    verify_url = f"{base_url}/certificate/{token}"
    pdf_bytes = _build_cert_pdf(data, verify_url=verify_url)
    safe_name = data["n"].replace(" ", "_")
    if _is_internship_payload(data):
        filename = f"Internship_Certificate_{safe_name}.pdf"
    elif _is_appreciation_payload(data):
        filename = f"Appreciation_Certificate_{safe_name}.pdf"
    else:
        filename = f"Certificate_{safe_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )



def _certificate_verify_public(data: dict) -> dict:
    """Public fields returned by GET /certificate/{token}/verify (and batch verify)."""
    kind = _certificate_kind_from_payload(data)
    out = {
        "valid": True,
        "certificate_id": _cert_id(data),
        "participant_name": data["n"],
        "course_name": data["c"],
        "completion_date": data["d"],
        "instructor_name": data["i"],
        "certificate_kind": kind,
    }
    if _is_internship_payload(data):
        out["usn"] = data["u"]
        out["internship_duration"] = data["w"]
        out["internship_hours"] = data["h"]
        out["mentor_name"] = data["m"]
        if data.get("s"):
            out["institution_name"] = data["s"]
    elif _is_appreciation_payload(data):
        out["recognition_text"] = data["r"]
        if data.get("e"):
            out["event_name"] = data["e"]
        if data.get("v"):
            out["venue_name"] = data["v"]
        if data.get("p"):
            out["sponsor_label"] = data["p"]
    return out


@app.get("/certificate/{token}/verify", tags=["Verification"])
async def verify_certificate(token: str):
    """Verify a single certificate's authenticity by its token. Returns the decoded certificate data if valid."""
    data = _decode_cert(token)
    if data is None:
        return JSONResponse({"valid": False, "message": "Invalid or tampered certificate"}, status_code=400)
    if _certificate_is_revoked(token):
        return JSONResponse(
            {"valid": False, "revoked": True, "message": "Certificate has been revoked"},
        )
    return _certificate_verify_public(data)


class BatchVerifyRequest(BaseModel):
    tokens: list[str]


@app.post("/api/certificates/verify", tags=["Verification"])
async def batch_verify_certificates(request: BatchVerifyRequest):
    """
    Verify multiple certificates in a single request.
    Accepts up to 100 tokens. Returns verification result for each.
    """
    if len(request.tokens) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 tokens per batch")

    results = []
    for token in request.tokens:
        data = _decode_cert(token)
        if data is None:
            results.append({"token": token[:20] + "...", "valid": False})
        elif _certificate_is_revoked(token):
            results.append(
                {
                    "token": token[:20] + "...",
                    "valid": False,
                    "revoked": True,
                    "message": "Certificate has been revoked",
                }
            )
        else:
            results.append({"token": token[:20] + "...", **_certificate_verify_public(data)})
    valid_count = sum(1 for r in results if r["valid"])
    return {"total": len(request.tokens), "valid": valid_count, "invalid": len(request.tokens) - valid_count, "results": results}


# ---------------------------------------------------------------------------
# Agent / LLM discovery & SEO
# ---------------------------------------------------------------------------

_AI_CRAWLERS = (
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",
    "ClaudeBot", "Claude-Web", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "GoogleOther",
    "Applebot", "Applebot-Extended",
    "Bytespider", "CCBot", "cohere-ai", "Diffbot",
    "Meta-ExternalAgent", "Meta-ExternalFetcher", "FacebookBot",
    "DuckAssistBot", "Amazonbot", "MistralAI-User", "YouBot",
)


def _build_llms_txt(base_url: str) -> str:
    b = certificate_branding()
    brand = b["brand_name"]
    return f"""# {brand} Certificate Platform

> Issue and verify tamper-proof PDF certificates with HMAC-signed shareable URLs — course participation, VTU-style internship credentials, and sports/event appreciation certificates.

{brand} ({b['website']}) provides API-first certificate generation for training completions and industry internships. Each certificate is a cryptographically signed URL with a downloadable PDF and public verification page. No database is required for verification.

## Documentation

- [OpenAPI specification]({base_url}/openapi.json): Machine-readable API schema (v2.0.0).
- [Interactive API docs]({base_url}/docs): Swagger UI for trying endpoints.
- [API metadata]({base_url}/api/info): Version, branding, and feature list.

## Pages

- [Certificate generator]({base_url}/): Web UI to issue participation, internship, and appreciation certificates.
- [List courses]({base_url}/api/courses): Active courses available for certificate issuance.

## Verification

- `GET /certificate/{{token}}/verify` — JSON verification for a single certificate.
- `POST /api/certificates/verify` — Batch verify up to 100 tokens.
- `GET /certificate/{{token}}` — Public HTML certificate page (shareable).
- `GET /certificate/{{token}}/download` — Download certificate PDF.

## Create certificates

`POST /api/certificate` with `X-API-Key` when configured.

Participation body:
```json
{{"participant_name":"Jane Doe","course_name":"AI Product Development","completion_date":"2026-04-15","instructor_name":"Certificate Team","participant_email":"jane@example.com"}}
```

Internship body adds: `certificate_kind`, `usn`, `internship_duration`, `internship_hours`, `mentor_name`, `institution_name`.

Appreciation body adds: `certificate_kind` `"appreciation"`, `recognition_text` (or `venue_name`), optional `event_name`, `sponsor_label`, `venue_name`.

## Automation

- Webhooks: pass `callback_url` on create to receive `certificate.created` events.
- Idempotency: pass `idempotency_key` to prevent duplicate issuance.
- Bulk admin: `POST /api/admin/certificates/bulk` with `X-Admin-Key`.
- Email delivery: optional `participant_email` via AgentMail.

## Branding (env-configurable)

- Org tagline: {b['org_tagline']}
- Brand: {brand}
- Participation title: {b['participation_title']}
- Internship org: {b['internship_org']}
- Appreciation org: {b['appreciation_org']}
- Contact: {CONTACT_EMAIL}

## Optional

- [Sitemap]({base_url}/sitemap.xml)
- [Robots]({base_url}/robots.txt)
- [AI plugin manifest]({base_url}/.well-known/ai-plugin.json)
"""


def _build_robots_txt(base_url: str) -> str:
    lines = ["User-agent: *", "Allow: /", ""]
    for bot in _AI_CRAWLERS:
        lines.extend([f"User-agent: {bot}", "Allow: /", ""])
    lines.append(f"Sitemap: {base_url}/sitemap.xml")
    return "\n".join(lines) + "\n"


def _build_sitemap_xml(base_url: str) -> str:
    pages = ["/", "/docs", "/openapi.json", "/llms.txt", "/api/info", "/api/courses"]
    urls = "\n".join(
        f"  <url><loc>{base_url}{path}</loc><changefreq>weekly</changefreq></url>"
        for path in pages
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


@app.get("/llms.txt", tags=["System"], include_in_schema=False)
async def llms_txt(req: Request):
    """Agent/LLM discovery document (llmstxt.org format)."""
    return Response(content=_build_llms_txt(_resolve_site_url(req)), media_type="text/plain; charset=utf-8")


@app.get("/robots.txt", tags=["System"], include_in_schema=False)
async def robots_txt(req: Request):
    """Crawler rules including explicit AI bot allowances."""
    return Response(content=_build_robots_txt(_resolve_site_url(req)), media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml", tags=["System"], include_in_schema=False)
async def sitemap_xml(req: Request):
    """Sitemap for marketing and API discovery pages."""
    return Response(content=_build_sitemap_xml(_resolve_site_url(req)), media_type="application/xml; charset=utf-8")


@app.get("/.well-known/ai-plugin.json", tags=["System"], include_in_schema=False)
async def ai_plugin(req: Request):
    """OpenAI-compatible plugin manifest for agent discovery."""
    base = _resolve_site_url(req)
    b = certificate_branding()
    return JSONResponse({
        "schema_version": "v1",
        "name_for_human": f"{b['brand_name']} Certificates",
        "name_for_model": "intelliforge_certificates",
        "description_for_human": (
            f"Generate and verify tamper-proof course, internship, and appreciation certificates from {b['brand_name']}."
        ),
        "description_for_model": (
            f"API for HMAC-signed verifiable certificates at {base}. "
            "Use POST /api/certificate to create (participation, internship with USN/hours/mentor, "
            "or appreciation with recognition_text/venue/event). "
            "Use GET /certificate/{{token}}/verify or POST /api/certificates/verify for verification. "
            "Supports idempotency_key, callback_url webhooks, and email delivery. "
            "See /llms.txt and /openapi.json for full documentation."
        ),
        "auth": {"type": "service_http", "authorization_type": "bearer", "verification_tokens": {}},
        "api": {"type": "openapi", "url": f"{base}/openapi.json"},
        "logo_url": f"{base}/favicon.svg",
        "contact_email": CONTACT_EMAIL,
        "legal_info_url": base,
    })


# ---------------------------------------------------------------------------
# Admin API (requires X-Admin-Key header)
# ---------------------------------------------------------------------------

def _require_admin(req: Request):
    if not ADMIN_KEY:
        raise HTTPException(status_code=503, detail="Admin access not configured")
    key = req.headers.get("X-Admin-Key", "")
    if not hmac_mod.compare_digest(key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin key")


def _require_db():
    if not _ensure_db_ready() or not db:
        raise HTTPException(status_code=503, detail="Database not available")


@app.get("/api/admin/stats", tags=["Admin"])
async def admin_stats(req: Request):
    """Get certificate analytics: total, weekly, revoked counts and per-course breakdown."""
    _require_admin(req)
    _require_db()
    return db.get_stats()


@app.get("/api/admin/certificates", tags=["Admin"])
async def admin_list_certificates(
    req: Request, limit: int = 50, offset: int = 0, course: str | None = None
):
    _require_admin(req)
    _require_db()
    return db.list_certificates(limit=limit, offset=offset, course=course)


@app.post("/api/admin/certificates/{cert_db_id}/revoke", tags=["Admin"])
async def admin_revoke_certificate(cert_db_id: int, req: Request):
    _require_admin(req)
    _require_db()
    result = db.revoke_certificate(cert_db_id)
    if not result:
        raise HTTPException(status_code=404, detail="Certificate not found or already revoked")
    return result


class BulkCertificateEntry(BaseModel):
    participant_name: str
    course_name: str = ""
    completion_date: str
    instructor_name: str = "Certificate Team"
    participant_email: str = ""
    certificate_kind: Literal["participation", "internship", "appreciation"] = "participation"
    usn: str = ""
    internship_duration: str = ""
    internship_hours: str = ""
    mentor_name: str = ""
    institution_name: str = ""
    recognition_text: str = ""
    event_name: str = ""
    venue_name: str = ""
    sponsor_label: str = ""


class BulkCertificateRequest(BaseModel):
    entries: list[BulkCertificateEntry]


@app.post("/api/admin/certificates/bulk", tags=["Admin"])
async def admin_bulk_generate(request: BulkCertificateRequest, req: Request):
    """Generate up to 500 certificates in a single request. Each entry is validated independently."""
    _require_admin(req)
    _require_db()

    if not request.entries:
        raise HTTPException(status_code=400, detail="No entries provided")
    if len(request.entries) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 certificates per batch")

    valid_courses = set(_get_course_names())
    base_url = str(req.base_url).rstrip("/")
    client_ip = req.client.host if req.client else "admin-bulk"
    results = []

    for i, entry in enumerate(request.entries):
        recognition = ""
        name = entry.participant_name.strip()
        if not name:
            results.append({"index": i, "status": "error", "error": "Participant name is required"})
            continue

        if entry.certificate_kind == "appreciation":
            recognition = entry.recognition_text.strip()
            if not recognition:
                recognition = _default_appreciation_recognition(entry.venue_name)
            if not recognition:
                results.append({
                    "index": i,
                    "status": "error",
                    "error": "Appreciation entry requires recognition_text or venue_name",
                })
                continue
            course_for_db = (
                entry.event_name.strip()
                or entry.course_name.strip()
                or "Sports Event"
            )
        elif entry.course_name not in valid_courses:
            results.append({"index": i, "status": "error", "error": f"Unknown course: {entry.course_name}"})
            continue
        else:
            course_for_db = entry.course_name

        if entry.certificate_kind == "internship":
            miss = []
            if not entry.usn.strip():
                miss.append("usn")
            if not entry.internship_duration.strip():
                miss.append("internship_duration")
            if not entry.internship_hours.strip():
                miss.append("internship_hours")
            if not entry.mentor_name.strip():
                miss.append("mentor_name")
            if miss:
                results.append({
                    "index": i,
                    "status": "error",
                    "error": "Internship entry requires: " + ", ".join(miss),
                })
                continue

        try:
            lead = entry.instructor_name.strip() or "IntelliForge AI Team"
            if entry.certificate_kind == "appreciation":
                cert_data = {
                    "k": "a",
                    "n": name,
                    "c": course_for_db,
                    "d": entry.completion_date,
                    "r": recognition,
                    "i": lead,
                }
                if entry.event_name.strip():
                    cert_data["e"] = entry.event_name.strip()
                if entry.venue_name.strip():
                    cert_data["v"] = entry.venue_name.strip()
                if entry.sponsor_label.strip():
                    cert_data["p"] = entry.sponsor_label.strip()
            else:
                cert_data = {
                    "n": name,
                    "c": course_for_db,
                    "d": entry.completion_date,
                    "i": lead,
                }
                if entry.certificate_kind == "internship":
                    cert_data["k"] = "i"
                    cert_data["u"] = entry.usn.strip()
                    cert_data["w"] = entry.internship_duration.strip()
                    cert_data["h"] = entry.internship_hours.strip()
                    cert_data["m"] = entry.mentor_name.strip()
                    if entry.institution_name.strip():
                        cert_data["s"] = entry.institution_name.strip()
            token = _encode_cert(cert_data)
            cert_id = _cert_id(cert_data)
            p_email = entry.participant_email.strip() if entry.participant_email else ""

            try:
                db.store_certificate(
                    certificate_id=cert_id,
                    token=token,
                    participant_name=name,
                    course_name=course_for_db,
                    completion_date=entry.completion_date,
                    instructor_name=lead,
                    client_ip=client_ip,
                    participant_email=p_email,
                )
            except Exception as e:
                logger.warning(f"Bulk: DB store failed for {name} (cert still valid): {e}")

            shareable_url = f"{base_url}/certificate/{token}"
            download_url = f"{shareable_url}/download"

            email_sent = False
            email_error = ""
            if p_email:
                def _send_bulk_email():
                    if entry.certificate_kind == "internship":
                        return _send_internship_certificate_email(
                            to_email=p_email,
                            participant_name=name,
                            course_name=course_for_db,
                            completion_date=entry.completion_date,
                            instructor_name=lead,
                            mentor_name=entry.mentor_name.strip(),
                            usn=entry.usn.strip(),
                            duration_text=entry.internship_duration.strip(),
                            hours_text=entry.internship_hours.strip(),
                            certificate_id=cert_id,
                            view_url=shareable_url,
                            download_url=download_url,
                        )
                    email_label = (
                        recognition[:80] + "…"
                        if entry.certificate_kind == "appreciation" and len(recognition) > 80
                        else course_for_db
                    )
                    return _send_certificate_email(
                        to_email=p_email,
                        participant_name=name,
                        course_name=email_label,
                        completion_date=entry.completion_date,
                        instructor_name=lead,
                        certificate_id=cert_id,
                        view_url=shareable_url,
                        download_url=download_url,
                    )

                email_result = _run_with_timeout(
                    _send_bulk_email,
                    EMAIL_SEND_TIMEOUT_SEC,
                    f"Email delivery timed out for {p_email}",
                )
                if email_result is None:
                    email_sent = False
                    email_error = "Email delivery timed out. Share the certificate link instead."
                else:
                    email_sent, email_error = email_result

            row = {
                "index": i,
                "status": "success",
                "certificate_id": cert_id,
                "participant_name": name,
                "course_name": course_for_db,
                "certificate_kind": entry.certificate_kind,
                "url": shareable_url,
                "download_url": download_url,
                "email_sent": email_sent,
                "email_error": email_error,
            }
            if entry.certificate_kind == "internship":
                row["usn"] = entry.usn.strip()
            elif entry.certificate_kind == "appreciation":
                row["recognition_text"] = recognition
            results.append(row)
        except Exception as e:
            results.append({"index": i, "status": "error", "error": str(e)})

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    logger.info(f"Bulk generation: {succeeded} succeeded, {failed} failed out of {len(request.entries)} entries")

    return {"total": len(request.entries), "succeeded": succeeded, "failed": failed, "results": results}


@app.get("/api/admin/courses", tags=["Admin"])
async def admin_list_courses(req: Request):
    _require_admin(req)
    _require_db()
    return {"courses": db.get_courses(active_only=False)}


class CourseCreateRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/api/admin/courses", tags=["Admin"])
async def admin_add_course(request: CourseCreateRequest, req: Request):
    _require_admin(req)
    _require_db()
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Course name is required")
    try:
        return db.add_course(name, request.description)
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Course '{name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


class CourseToggleRequest(BaseModel):
    active: bool


@app.patch("/api/admin/courses/{course_id}", tags=["Admin"])
async def admin_toggle_course(course_id: int, request: CourseToggleRequest, req: Request):
    _require_admin(req)
    _require_db()
    result = db.toggle_course(course_id, request.active)
    if not result:
        raise HTTPException(status_code=404, detail="Course not found")
    return result


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

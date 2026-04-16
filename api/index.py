"""
FastAPI backend for the IntelliForge Certificate Platform API.
Handles certificate creation, verification, and certificate PDF generation.

Certificates use stateless HMAC-SHA256 signed tokens encoded in the URL itself,
so no database is needed and certificates are permanent and tamper-proof.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, JSONResponse
from pydantic import BaseModel
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

import uuid as uuid_mod
import threading

import qrcode
from qrcode.image.pil import PilImage
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_AVAILABLE = bool(os.environ.get("DATABASE_URL", ""))
db = None
if DB_AVAILABLE:
    from api import db as _db_mod
    db = _db_mod
    try:
        db.init_schema()
        logger.info("Database connected and schema initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed, running without DB: {e}")
        DB_AVAILABLE = False
        db = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IS_PROD = os.environ.get("VERCEL_ENV") == "production" or os.environ.get("ENV") == "production"
CERT_SECRET = os.environ.get("CERT_SECRET_KEY", "").strip()
if not CERT_SECRET:
    if IS_PROD:
        raise RuntimeError("CERT_SECRET_KEY environment variable is required in production")
    CERT_SECRET = "intelliforge-dev-secret-local-only"
    logger.warning("CERT_SECRET_KEY not set — using insecure dev default. Set it before deploying.")

CERT_API_KEYS: set[str] = set()
_raw_keys = os.environ.get("CERT_API_KEYS", "")
if _raw_keys:
    CERT_API_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

ADMIN_KEY = os.environ.get("ADMIN_KEY", "").strip()
if not ADMIN_KEY and not IS_PROD:
    ADMIN_KEY = "admin-dev-key"

AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY", "").strip()
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "support@intelliforge.tech").strip()
_agentmail_client = None
if AGENTMAIL_API_KEY:
    try:
        from agentmail import AgentMail as AgentMailClient
        _agentmail_client = AgentMailClient(api_key=AGENTMAIL_API_KEY)
        logger.info(f"AgentMail configured with inbox {AGENTMAIL_INBOX_ID}")
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
    {"name": "Verification", "description": "Verify certificate authenticity (single and batch)"},
    {"name": "Courses", "description": "List available courses"},
    {"name": "Admin", "description": "Admin endpoints for certificate and course management (requires X-Admin-Key)"},
    {"name": "System", "description": "Health checks and API metadata"},
]

app = FastAPI(
    title="IntelliForge Certificate API",
    description=(
        "**API-first verifiable credentials with zero vendor lock-in.**\n\n"
        "Generate tamper-proof participation certificates with shareable URLs. "
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
    raw = f"{data['n']}-{data['c']}-{data['d']}"
    return "IF-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _certificate_is_revoked(token: str) -> bool:
    """True if the token exists in the DB and is revoked. False if not revoked or not in DB."""
    if not DB_AVAILABLE or not db:
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
FOUNDER_TITLE = os.environ.get("FOUNDER_TITLE", "Founder & CEO, IntelliForge AI").strip()
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


class CertificateRequest(BaseModel):
    participant_name: str
    course_name: str
    completion_date: str
    instructor_name: str = "IntelliForge AI Team"
    participant_email: str = ""
    callback_url: str = ""
    idempotency_key: str = ""


@app.get("/", tags=["System"])
async def root():
    """API root with version and available endpoints."""
    return {
        "status": "ok",
        "message": "IntelliForge Certificate API is running",
        "version": "2.0.0",
        "endpoints": {
            "certificate": "/api/certificate",
            "courses": "/api/courses",
            "health": "/api/health",
        }
    }


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check. Returns 200 if the service is running."""
    return {
        "status": "healthy",
        "service": "intelliforge-certificate-api",
        "version": "2.0.0",
        "dependencies": {
            "database": "connected" if DB_AVAILABLE else "not_configured",
            "email": "configured" if _agentmail_client else "not_configured",
        },
    }


@app.get("/api/info", tags=["System"])
async def get_info():
    """API metadata including version, features, and tech stack."""
    return {
        "name": "IntelliForge Certificate API",
        "version": "2.0.0",
        "description": "Verifiable certificate generation with shareable URLs",
        "features": [
            "HMAC-SHA256 signed certificate tokens",
            "Stateless verification (no database)",
            "Public shareable certificate pages",
            "PDF certificate generation with QR codes",
            "LinkedIn and X social sharing",
        ],
        "tech_stack": {
            "framework": "FastAPI",
            "language": "Python",
            "pdf": "xhtml2pdf (certificate PDFs)",
            "crypto": "HMAC-SHA256",
        }
    }


COURSES_FALLBACK = [
    "AI Product Development Fundamentals",
    "Building AI-Powered Applications",
    "Prompt Engineering & LLM Integration",
    "Full-Stack AI Development",
    "AI Product Design & UX",
    "Digital Profile Creation",
    "Deploying AI Solutions",
    "AI Code Reviewer Course",
]


def _get_course_names() -> list[str]:
    if DB_AVAILABLE and db:
        try:
            return db.get_active_course_names()
        except Exception as e:
            logger.warning(f"DB course fetch failed, using fallback: {e}")
    return COURSES_FALLBACK


@app.get("/api/courses", tags=["Courses"])
async def get_courses():
    """List all active courses available for certificate generation."""
    return {"courses": _get_course_names()}


CERTIFICATE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: 842pt 595pt;
            margin: 0;
        }}
        body {{
            font-family: Helvetica, Arial, sans-serif;
            color: #2d3748;
            margin: 0;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
        }}
        td {{
            padding: 0;
        }}
    </style>
</head>
<body>

<!-- Full-page outer wrapper with dark background -->
<table width="100%" height="100%" style="background-color: #0f0f23;">
<tr><td style="padding: 24pt 32pt;">

<!-- Card with white background and rounded appearance -->
<table width="100%" style="background-color: #ffffff;">
<tr><td>

    <!-- ═══════════════ HEADER ═══════════════ -->
    <table width="100%" style="background-color: #15155e;">
    <tr><td style="padding: 30pt 40pt 26pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 4pt; color: #d4af37; font-weight: bold; padding-bottom: 4pt; text-align: center;">
                AN INTELLIFORGE AI INITIATIVE
            </td></tr>
            <tr><td align="center" style="font-size: 24pt; font-weight: bold; color: #ffffff; padding: 6pt 0 12pt; text-align: center;">
                IntelliForge Learning
            </td></tr>
            <tr><td align="center" style="text-align: center; padding: 0;">
                <table align="center" cellspacing="0" cellpadding="0" style="border: 2px solid #d4af37;">
                <tr><td align="center" style="padding: 6pt 30pt; font-size: 9pt; letter-spacing: 3pt; color: #d4af37; font-weight: bold; text-align: center;">
                    CERTIFICATE OF PARTICIPATION
                </td></tr>
                </table>
            </td></tr>
        </table>
    </td></tr>
    </table>

    <!-- ═══════════════ BODY ═══════════════ -->
    <table width="100%">
    <tr><td style="padding: 28pt 50pt 20pt;">

        <!-- Verified badge -->
        <table width="100%" cellspacing="0" cellpadding="0">
        <tr><td align="center" style="text-align: center; padding-bottom: 18pt;">
            <table align="center" cellspacing="0" cellpadding="0" style="border: 1px solid #68d391;">
            <tr><td align="center" style="padding: 4pt 14pt; font-size: 8pt; color: #276749; font-weight: bold; background-color: #f0fff4; text-align: center;">
                &#10003; &nbsp; Verified &amp; Authentic
            </td></tr>
            </table>
        </td></tr>
        </table>

        <!-- Award label + Name + Divider + Course -->
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 8pt; letter-spacing: 3pt; color: #a0aec0; padding-bottom: 6pt;">
                THIS CERTIFICATE IS AWARDED TO
            </td></tr>
            <tr><td align="center" style="text-align: center; font-size: 32pt; font-weight: bold; color: #1a202c; padding: 4pt 0 2pt;">
                {participant_name}
            </td></tr>
        </table>

        <!-- Gold divider -->
        <table width="60%" align="center" cellspacing="0" cellpadding="0"><tr>
            <td style="border-top: 2px solid #d4af37; font-size: 1pt;">&nbsp;</td>
        </tr></table>

        <!-- Course name -->
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 1pt; padding-top: 10pt;">&nbsp;</td></tr>
            <tr><td align="center" style="text-align: center; font-size: 15pt; font-weight: bold; color: #553c9a; padding-bottom: 20pt;">
                {course_name}
            </td></tr>
        </table>

        <!-- Metadata row -->
        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="33%" align="center" style="text-align: center; padding: 12pt 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{completion_date}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="34%" align="center" style="text-align: center; padding: 12pt 8pt; border-left: 1px solid #edf2f7; border-right: 1px solid #edf2f7;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{instructor_name}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">INSTRUCTOR</td></tr>
                    </table>
                </td>
                <td width="33%" align="center" style="text-align: center; padding: 12pt 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="text-align: center; font-size: 11pt; color: #2d3748; font-weight: bold; padding-bottom: 3pt;">{certificate_id}</td></tr>
                        <tr><td align="center" style="text-align: center; font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CERTIFICATE ID</td></tr>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>

        <!-- Signatures -->
        <table width="70%" align="center" cellspacing="0" cellpadding="0">
            <tr>
                <td width="50%" align="center" style="text-align: center; padding: 8pt 12pt; vertical-align: bottom;">
                    <img src="{signature_data_uri}" height="50" />
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="border-top: 1px solid #c4b5fd; font-size: 8pt; color: #553c9a; font-weight: bold; padding-top: 4pt; text-align: center;">
                            {founder_name}
                        </td></tr>
                        <tr><td align="center" style="font-size: 6pt; color: #a0aec0; text-align: center; letter-spacing: 1pt;">
                            {founder_title}
                        </td></tr>
                    </table>
                </td>
                <td width="50%" align="center" style="text-align: center; padding: 8pt 12pt; vertical-align: bottom;">
                    <img src="{instructor_signature_data_uri}" height="50" />
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td align="center" style="border-top: 1px solid #c4b5fd; font-size: 8pt; color: #553c9a; font-weight: bold; padding-top: 4pt; text-align: center;">
                            {instructor_name}
                        </td></tr>
                        <tr><td align="center" style="font-size: 6pt; color: #a0aec0; text-align: center; letter-spacing: 1pt;">
                            COURSE INSTRUCTOR
                        </td></tr>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>

        <!-- QR code + verify section -->
        <table width="100%" cellspacing="0" cellpadding="0">
        <tr><td align="center" style="text-align: center;">
            <table align="center" cellspacing="0" cellpadding="0">
            <tr>
                <td style="padding-right: 12pt; vertical-align: middle;">
                    <img src="{qr_data_uri}" width="70" height="70" />
                </td>
                <td style="vertical-align: middle; text-align: left;">
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 9pt; font-weight: bold; color: #2d3748; padding-bottom: 2pt;">Scan to Verify</td></tr></table>
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 7pt; color: #a0aec0; line-height: 1.5;">This QR code links to this certificate's<br/>permanent verification page.</td></tr></table>
                </td>
            </tr>
            </table>
        </td></tr>
        </table>

    </td></tr>
    </table>

    <!-- ═══════════════ FOOTER ═══════════════ -->
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-top: 1px solid #edf2f7;">
    <tr><td align="center" style="padding: 10pt 40pt; text-align: center; font-size: 7pt; color: #a0aec0;">
        Issued by IntelliForge Learning &nbsp;&middot;&nbsp; learning.intelliforge.tech &nbsp;&middot;&nbsp; support@intelliforge.tech
    </td></tr>
    </table>

</td></tr>
</table>
<!-- End card -->

</td></tr>
</table>
<!-- End outer wrapper -->

</body>
</html>
"""


def _build_cert_pdf(data: dict, verify_url: str = "") -> bytes:
    """Render certificate compact data into PDF bytes."""
    qr_data_uri = _generate_qr_data_uri(verify_url) if verify_url else ""
    full_html = CERTIFICATE_TEMPLATE.format(
        participant_name=data["n"],
        course_name=data["c"],
        completion_date=data["d"],
        instructor_name=data["i"],
        certificate_id=_cert_id(data),
        qr_data_uri=qr_data_uri,
        signature_data_uri=_generate_signature_data_uri(),
        instructor_signature_data_uri=_generate_signature_data_uri(data["i"]),
        founder_name=FOUNDER_NAME,
        founder_title=FOUNDER_TITLE,
    )
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=full_html, dest=pdf_buffer, encoding="UTF-8")
    if pisa_status.err:
        raise Exception("Error generating certificate PDF")
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


CERT_EMAIL_HTML = """
<div style="font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;background:#0f0f23;padding:24px;border-radius:16px;">
  <div style="background:linear-gradient(135deg,#12124a 0%,#1e1e6e 50%,#2a1a5e 100%);padding:28px 32px 24px;text-align:center;border-radius:12px 12px 0 0;">
    <div style="font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#d4af37;font-weight:600;">An IntelliForge AI Initiative</div>
    <div style="font-size:24px;font-weight:700;color:#fff;margin:8px 0 12px;">IntelliForge Learning</div>
    <div style="display:inline-block;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#d4af37;font-weight:600;border:1px solid rgba(139,125,60,0.6);padding:6px 18px;border-radius:20px;">Certificate of Participation</div>
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
    <p style="font-size:12px;color:#a0aec0;margin:0;">Issued by <a href="https://learning.intelliforge.tech/" style="color:#667eea;text-decoration:none;">IntelliForge Learning</a> &middot; <a href="mailto:support@intelliforge.tech" style="color:#667eea;text-decoration:none;">support@intelliforge.tech</a></p>
  </div>
</div>
"""


def _send_certificate_email(
    to_email: str,
    participant_name: str,
    course_name: str,
    completion_date: str,
    instructor_name: str,
    certificate_id: str,
    view_url: str,
    download_url: str,
):
    """Send certificate notification email via AgentMail. Non-blocking on failure."""
    if not _agentmail_client or not to_email:
        return
    try:
        html = CERT_EMAIL_HTML.format(
            participant_name=participant_name,
            course_name=course_name,
            completion_date=completion_date,
            instructor_name=instructor_name,
            certificate_id=certificate_id,
            view_url=view_url,
            download_url=download_url,
        )
        _agentmail_client.inboxes.messages.send(
            AGENTMAIL_INBOX_ID,
            to=to_email,
            subject=f"Your IntelliForge Certificate – {course_name}",
            text=(
                f"Congratulations {participant_name}!\n\n"
                f"You have been awarded a Certificate of Participation for completing "
                f"{course_name} at IntelliForge Learning.\n\n"
                f"Certificate ID: {certificate_id}\n"
                f"View your certificate: {view_url}\n"
                f"Download PDF: {download_url}\n\n"
                f"Share this achievement on LinkedIn or X!\n\n"
                f"– IntelliForge Learning Team"
            ),
            html=html,
        )
        logger.info(f"Certificate email sent to {to_email}")
    except Exception as e:
        logger.warning(f"Failed to send certificate email to {to_email}: {e}")


@app.post("/api/certificate", tags=["Certificates"])
async def generate_certificate(request: CertificateRequest, req: Request):
    """
    Generate a signed certificate and return shareable URL + PDF download URL.

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
            origin = req.headers.get("origin", "")
            base = str(req.base_url).rstrip("/")
            is_same_origin = origin and base.startswith(origin)
            if not is_same_origin and api_key not in CERT_API_KEYS:
                raise HTTPException(status_code=401, detail="Invalid or missing API key")

        client_ip = req.client.host if req.client else "unknown"
        allowed, rate_headers = _check_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers=rate_headers,
            )

        valid_courses = _get_course_names()
        if request.course_name not in valid_courses:
            raise HTTPException(status_code=400, detail=f"Unknown course: {request.course_name}")
        name = request.participant_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Participant name is required")

        cert_data = {
            "n": name,
            "c": request.course_name,
            "d": request.completion_date,
            "i": request.instructor_name,
        }
        token = _encode_cert(cert_data)
        cert_id = _cert_id(cert_data)

        participant_email = request.participant_email.strip() if request.participant_email else ""

        if DB_AVAILABLE and db:
            try:
                db.store_certificate(
                    certificate_id=cert_id,
                    token=token,
                    participant_name=name,
                    course_name=request.course_name,
                    completion_date=request.completion_date,
                    instructor_name=request.instructor_name,
                    client_ip=client_ip,
                    participant_email=participant_email,
                )
            except Exception as e:
                logger.warning(f"Failed to store certificate in DB (cert still valid): {e}")

        base_url = str(req.base_url).rstrip("/")
        shareable_url = f"{base_url}/certificate/{token}"
        download_url = f"{shareable_url}/download"

        if participant_email:
            _send_certificate_email(
                to_email=participant_email,
                participant_name=name,
                course_name=request.course_name,
                completion_date=request.completion_date,
                instructor_name=request.instructor_name,
                certificate_id=cert_id,
                view_url=shareable_url,
                download_url=download_url,
            )

        logger.info(f"Certificate issued for {name} – {request.course_name}")

        response_data = {
            "certificate_id": cert_id,
            "token": token,
            "url": shareable_url,
            "download_url": download_url,
            "participant_name": name,
            "course_name": request.course_name,
            "email_sent": bool(participant_email and _agentmail_client),
            "request_id": str(uuid_mod.uuid4()),
        }

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


# ---------------------------------------------------------------------------
# Public certificate viewer page (server-rendered HTML)
# ---------------------------------------------------------------------------
VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{participant_name} – IntelliForge Certificate</title>
    <meta property="og:title" content="{participant_name} – Certificate of Participation" />
    <meta property="og:description" content="{participant_name} successfully completed {course_name} at IntelliForge Learning." />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="{page_url}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{participant_name} – IntelliForge Certificate" />
    <meta name="twitter:description" content="Verified certificate for completing {course_name}" />
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
            <div class="hdr-org">An IntelliForge AI Initiative</div>
            <div class="hdr-brand">IntelliForge Learning</div>
            <div class="hdr-badge">Certificate of Participation</div>
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
            <div class="meta">
                <div class="meta-item"><div class="meta-val">{completion_date}</div><div class="meta-lbl">Date</div></div>
                <div class="meta-item"><div class="meta-val">{instructor_name}</div><div class="meta-lbl">Instructor</div></div>
                <div class="meta-item"><div class="meta-val">{cert_id}</div><div class="meta-lbl">Certificate ID</div></div>
            </div>
            <div class="signatures">
                <div class="sig-block">
                    <div class="sig-hand">{founder_name}</div>
                    <div class="sig-line"></div>
                    <div class="sig-name">{founder_name}</div>
                    <div class="sig-role">{founder_title}</div>
                </div>
                <div class="sig-block">
                    <div class="sig-hand">{instructor_name}</div>
                    <div class="sig-line"></div>
                    <div class="sig-name">{instructor_name}</div>
                    <div class="sig-role">Course Instructor</div>
                </div>
            </div>
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
                Issued by <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener">IntelliForge Learning</a>
                &nbsp;&middot;&nbsp; <a href="mailto:support@intelliforge.tech">support@intelliforge.tech</a>
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

    cert_desc = f"I completed {data['c']} at IntelliForge Learning!"

    linkedin_params = urlencode({"url": page_url})
    linkedin_url = f"https://www.linkedin.com/sharing/share-offsite/?{linkedin_params}"

    twitter_params = urlencode({"text": cert_desc, "url": page_url})
    twitter_url = f"https://twitter.com/intent/tweet?{twitter_params}"

    html = VIEWER_HTML.format(
        participant_name=data["n"],
        course_name=data["c"],
        completion_date=data["d"],
        instructor_name=data["i"],
        cert_id=_cert_id(data),
        page_url=page_url,
        download_url=download_url,
        linkedin_url=linkedin_url,
        twitter_url=twitter_url,
        qr_data_uri=_generate_qr_data_uri(page_url),
        founder_name=FOUNDER_NAME,
        founder_title=FOUNDER_TITLE,
    )
    return HTMLResponse(content=html)


@app.get("/certificate/{token}/download", tags=["Certificates"])
async def download_certificate(token: str, req: Request):
    """Download a certificate as a PDF file."""
    data = _resolve_cert(token)
    base_url = str(req.base_url).rstrip("/")
    verify_url = f"{base_url}/certificate/{token}"
    pdf_bytes = _build_cert_pdf(data, verify_url=verify_url)
    safe_name = data["n"].replace(" ", "_")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Certificate_{safe_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


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
    return {
        "valid": True,
        "certificate_id": _cert_id(data),
        "participant_name": data["n"],
        "course_name": data["c"],
        "completion_date": data["d"],
        "instructor_name": data["i"],
    }


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
            results.append({
                "token": token[:20] + "...",
                "valid": True,
                "certificate_id": _cert_id(data),
                "participant_name": data["n"],
                "course_name": data["c"],
                "completion_date": data["d"],
                "instructor_name": data["i"],
            })
    valid_count = sum(1 for r in results if r["valid"])
    return {"total": len(request.tokens), "valid": valid_count, "invalid": len(request.tokens) - valid_count, "results": results}


# ---------------------------------------------------------------------------
# Agent / LLM discovery
# ---------------------------------------------------------------------------
LLMS_TXT = """# IntelliForge Certificate API

> API-first verifiable credentials. Generate tamper-proof certificates with shareable URLs.

## Base URL
https://certs.intelliforge.tech

## Authentication
- Certificate creation: `X-API-Key: <key>` header
- Admin endpoints: `X-Admin-Key: <key>` header
- Public endpoints (view, download, verify): No auth required

## Endpoints

### Create Certificate
POST /api/certificate
Content-Type: application/json
X-API-Key: <key>

{
  "participant_name": "Jane Doe",
  "course_name": "AI Product Development Fundamentals",
  "completion_date": "2026-04-15",
  "instructor_name": "IntelliForge AI Team",
  "participant_email": "jane@example.com",
  "callback_url": "https://your-server.com/webhook",
  "idempotency_key": "unique-request-id"
}

Response: { certificate_id, token, url, download_url, email_sent, request_id }

### List Courses
GET /api/courses
Response: { courses: ["Course 1", "Course 2", ...] }

### Verify Certificate
GET /certificate/{token}/verify
Response: { valid: true, certificate_id, participant_name, course_name, ... }

### Batch Verify
POST /api/certificates/verify
{ "tokens": ["token1", "token2"] }
Response: { total, valid, invalid, results: [...] }

### Download PDF
GET /certificate/{token}/download
Response: application/pdf

### Bulk Generate (Admin)
POST /api/admin/certificates/bulk
X-Admin-Key: <key>
{ "entries": [{ participant_name, course_name, completion_date, participant_email }, ...] }

### OpenAPI Spec
GET /openapi.json

## Key Features
- Stateless HMAC-SHA256 signed tokens — no database needed for verification
- Idempotency keys to prevent duplicates
- Webhook callbacks for async automation
- Email delivery via AgentMail
- Bulk generation (up to 500 per batch)
- Batch verification (up to 100 per request)
"""


@app.get("/llms.txt", tags=["System"], include_in_schema=False)
async def llms_txt():
    """Agent/LLM discovery document describing available API capabilities."""
    return Response(content=LLMS_TXT, media_type="text/plain")


@app.get("/.well-known/ai-plugin.json", tags=["System"], include_in_schema=False)
async def ai_plugin():
    """OpenAI-compatible plugin manifest for agent discovery."""
    return JSONResponse({
        "schema_version": "v1",
        "name_for_human": "IntelliForge Certificates",
        "name_for_model": "intelliforge_certificates",
        "description_for_human": "Generate and verify tamper-proof participation certificates with shareable URLs.",
        "description_for_model": (
            "API for generating HMAC-signed verifiable certificates. "
            "Use POST /api/certificate to create, GET /certificate/{token}/verify to verify, "
            "POST /api/certificates/verify for batch verification. "
            "Supports idempotency_key, callback_url webhooks, and email delivery."
        ),
        "auth": {"type": "service_http", "authorization_type": "bearer", "verification_tokens": {}},
        "api": {"type": "openapi", "url": "https://certs.intelliforge.tech/openapi.json"},
        "logo_url": "https://www.intelliforge.tech/favicon.ico",
        "contact_email": "support@intelliforge.tech",
        "legal_info_url": "https://www.intelliforge.tech/",
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
    if not DB_AVAILABLE or not db:
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
    course_name: str
    completion_date: str
    instructor_name: str = "IntelliForge AI Team"
    participant_email: str = ""


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
        name = entry.participant_name.strip()
        if not name:
            results.append({"index": i, "status": "error", "error": "Participant name is required"})
            continue
        if entry.course_name not in valid_courses:
            results.append({"index": i, "status": "error", "error": f"Unknown course: {entry.course_name}"})
            continue

        try:
            cert_data = {"n": name, "c": entry.course_name, "d": entry.completion_date, "i": entry.instructor_name}
            token = _encode_cert(cert_data)
            cert_id = _cert_id(cert_data)
            p_email = entry.participant_email.strip() if entry.participant_email else ""

            try:
                db.store_certificate(
                    certificate_id=cert_id,
                    token=token,
                    participant_name=name,
                    course_name=entry.course_name,
                    completion_date=entry.completion_date,
                    instructor_name=entry.instructor_name,
                    client_ip=client_ip,
                    participant_email=p_email,
                )
            except Exception as e:
                logger.warning(f"Bulk: DB store failed for {name} (cert still valid): {e}")

            shareable_url = f"{base_url}/certificate/{token}"
            download_url = f"{shareable_url}/download"

            if p_email:
                _send_certificate_email(
                    to_email=p_email,
                    participant_name=name,
                    course_name=entry.course_name,
                    completion_date=entry.completion_date,
                    instructor_name=entry.instructor_name,
                    certificate_id=cert_id,
                    view_url=shareable_url,
                    download_url=download_url,
                )

            results.append({
                "index": i,
                "status": "success",
                "certificate_id": cert_id,
                "participant_name": name,
                "course_name": entry.course_name,
                "url": shareable_url,
                "download_url": download_url,
                "email_sent": bool(p_email and _agentmail_client),
            })
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

"""
FastAPI backend for Markdown to PDF Converter
Handles markdown parsing, PDF generation, and certificate creation.

Certificates use stateless HMAC-signed tokens encoded in the URL itself,
so no database is needed and certificates are permanent and tamper-proof.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, JSONResponse
from pydantic import BaseModel
import markdown
from xhtml2pdf import pisa
from io import BytesIO
import logging
import hashlib
import hmac
import json
import os
import base64
from urllib.parse import quote, urlencode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IntelliForge Certificate & PDF API",
    description="Certificate generation with shareable URLs and Markdown-to-PDF conversion",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Stateless certificate tokens (HMAC-signed, no database required)
# ---------------------------------------------------------------------------
CERT_SECRET = os.environ.get("CERT_SECRET_KEY", "intelliforge-dev-secret-change-in-prod")


def _encode_cert(data: dict) -> str:
    """Encode certificate data into a URL-safe token with HMAC signature."""
    compact = json.dumps(data, separators=(",", ":"), sort_keys=True)
    payload = base64.urlsafe_b64encode(compact.encode()).decode().rstrip("=")
    sig = hmac.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}.{sig}"


def _decode_cert(token: str) -> dict | None:
    """Decode and verify a certificate token. Returns None if invalid."""
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(CERT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
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


class MarkdownRequest(BaseModel):
    markdown: str
    filename: str = "document.pdf"


class CertificateRequest(BaseModel):
    participant_name: str
    course_name: str
    completion_date: str
    instructor_name: str = "IntelliForge AI Team"


# HTML template with styling
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
            line-height: 1.8;
            color: #2d3748;
            font-size: 11pt;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            font-weight: 600;
            line-height: 1.3;
            color: #1a202c;
        }}
        
        h1 {{
            font-size: 2em;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.3em;
        }}
        
        h2 {{
            font-size: 1.5em;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0.3em;
        }}
        
        h3 {{
            font-size: 1.25em;
        }}
        
        p {{
            margin: 1em 0;
        }}
        
        code {{
            background: #f7fafc;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 0.9em;
            color: #e53e3e;
            border: 1px solid #e2e8f0;
        }}
        
        pre {{
            background: #2d3748;
            color: #f7fafc;
            padding: 1em;
            border-radius: 6px;
            overflow-x: auto;
            margin: 1em 0;
        }}
        
        pre code {{
            background: transparent;
            padding: 0;
            border: none;
            color: inherit;
            font-size: 0.875em;
        }}
        
        blockquote {{
            border-left: 4px solid #667eea;
            padding-left: 1em;
            margin: 1em 0;
            color: #4a5568;
            font-style: italic;
            background: #f7fafc;
            padding: 1em;
            border-radius: 0 6px 6px 0;
        }}
        
        ul, ol {{
            padding-left: 2em;
            margin: 1em 0;
        }}
        
        li {{
            margin: 0.5em 0;
        }}
        
        a {{
            color: #667eea;
            text-decoration: none;
            border-bottom: 1px solid #667eea;
        }}
        
        hr {{
            border: none;
            border-top: 2px solid #e2e8f0;
            margin: 2em 0;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        
        th, td {{
            border: 1px solid #e2e8f0;
            padding: 0.75em;
            text-align: left;
        }}
        
        th {{
            background: #f7fafc;
            font-weight: 600;
        }}
        
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            margin: 1em 0;
        }}
    </style>
</head>
<body>
{content}
</body>
</html>
"""


@app.get("/")
async def root():
    """API health check endpoint"""
    return {
        "status": "ok",
        "message": "Markdown to PDF API is running",
        "version": "1.0.0",
        "endpoints": {
            "convert": "/api/convert",
            "health": "/api/health"
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "markdown-to-pdf",
        "version": "1.0.0"
    }


@app.post("/api/convert")
async def convert_markdown_to_pdf(request: MarkdownRequest):
    """
    Convert markdown to PDF
    
    Args:
        request: MarkdownRequest containing markdown text and optional filename
        
    Returns:
        PDF file as binary response
    """
    try:
        logger.info(f"Converting markdown to PDF (length: {len(request.markdown)} chars)")
        
        # Convert markdown to HTML
        md = markdown.Markdown(extensions=[
            'extra',      # Tables, fenced code blocks, etc.
            'codehilite', # Syntax highlighting
            'nl2br',      # Newline to <br>
            'sane_lists'  # Better list handling
        ])
        html_content = md.convert(request.markdown)
        
        # Wrap in styled HTML template
        full_html = HTML_TEMPLATE.format(content=html_content)
        
        # Convert HTML to PDF using xhtml2pdf
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(
            src=full_html,
            dest=pdf_buffer,
            encoding='UTF-8'
        )
        
        if pisa_status.err:
            raise Exception("Error generating PDF with xhtml2pdf")
        
        pdf_buffer.seek(0)
        
        # Get the PDF bytes
        pdf_bytes = pdf_buffer.getvalue()
        
        logger.info(f"PDF generated successfully (size: {len(pdf_bytes)} bytes)")
        
        # Return PDF as response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{request.filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
        
    except Exception as e:
        logger.error(f"Error converting markdown to PDF: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to convert markdown to PDF: {str(e)}"
        )


@app.get("/api/info")
async def get_info():
    """Get API information"""
    return {
        "name": "Markdown to PDF API",
        "version": "1.0.0",
        "description": "Convert Markdown to professionally formatted PDF documents",
        "features": [
            "Markdown parsing with extensions",
            "Beautiful PDF styling",
            "Tables and code blocks support",
            "Custom fonts and colors",
            "A4 page format",
            "Participation certificate generation"
        ],
        "tech_stack": {
            "framework": "FastAPI",
            "language": "Python",
            "markdown_parser": "markdown",
            "pdf_generator": "xhtml2pdf"
        }
    }


COURSES = [
    "AI Product Development Fundamentals",
    "Building AI-Powered Applications",
    "Prompt Engineering & LLM Integration",
    "Full-Stack AI Development",
    "AI Product Design & UX",
    "Digital Profile Creation",
    "Deploying AI Solutions",
    "AI Code Reviewer Course",
]


@app.get("/api/courses")
async def get_courses():
    """Return the list of available IntelliForge Learning courses"""
    return {"courses": COURSES}


CERTIFICATE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: 842pt 595pt;
            margin: 18pt 24pt;
        }}

        body {{
            font-family: Helvetica, Arial, sans-serif;
            color: #1a1a3e;
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

    <!-- Outer gold border -->
    <table width="100%" style="border: 3px solid #b8960c;">
    <tr><td style="padding: 4pt;">

    <!-- Navy inner border -->
    <table width="100%" style="border: 2px solid #1a1a6e;">
    <tr><td style="padding: 4pt;">

    <!-- Gold accent border -->
    <table width="100%" style="border: 1px solid #d4af37;">
    <tr><td style="padding: 16pt 36pt; text-align: center; background-color: #fffdf5;">

        <!-- Watermark pattern row -->
        <table width="100%"><tr><td style="text-align: center; font-size: 7pt; color: #f0e6c8;">
            &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670;
        </td></tr></table>

        <!-- Top ornament -->
        <table width="100%"><tr><td style="text-align: center; font-size: 14pt; color: #d4af37; padding: 2pt 0;">
            &#10022; &nbsp; &#10022; &nbsp; &#10022;
        </td></tr></table>

        <!-- Organization -->
        <table width="100%"><tr><td style="text-align: center; font-size: 8pt; color: #b8960c;">
            AN INTELLIFORGE AI INITIATIVE
        </td></tr></table>

        <table width="100%"><tr><td style="text-align: center; font-size: 18pt; font-weight: bold; color: #1a1a6e; padding-top: 2pt;">
            IntelliForge Learning
        </td></tr></table>

        <!-- Gold divider -->
        <table width="100%"><tr><td style="text-align: center; padding: 6pt 0;">
            <table width="200pt" align="center"><tr>
                <td width="40%" style="border-top: 1px solid #d4af37; font-size: 1pt;">&nbsp;</td>
                <td width="20%" style="text-align: center; font-size: 8pt; color: #d4af37;">&#9733;</td>
                <td width="40%" style="border-top: 1px solid #d4af37; font-size: 1pt;">&nbsp;</td>
            </tr></table>
        </td></tr></table>

        <!-- Certificate title -->
        <table width="100%"><tr><td style="text-align: center; font-size: 34pt; font-weight: bold; color: #1a1a6e;">
            CERTIFICATE
        </td></tr></table>

        <table width="100%"><tr><td style="text-align: center; font-size: 13pt; color: #8b7d3c; padding-top: 2pt;">
            of Participation
        </td></tr></table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 12pt;">&nbsp;</td></tr></table>

        <!-- Presented to -->
        <table width="100%"><tr><td style="text-align: center; font-size: 9pt; color: #8b8b8b;">
            THIS IS PROUDLY PRESENTED TO
        </td></tr></table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 6pt;">&nbsp;</td></tr></table>

        <!-- Participant name with gold underline -->
        <table width="80%" align="center"><tr><td style="text-align: center; font-size: 28pt; font-weight: bold; color: #1a1a3e; border-bottom: 2px solid #d4af37; padding-bottom: 4pt;">
            {participant_name}
        </td></tr></table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>

        <!-- Description -->
        <table width="100%"><tr><td style="text-align: center; font-size: 10pt; color: #4a4a6a;">
            for successfully completing the training program
        </td></tr></table>

        <table width="100%"><tr><td style="text-align: center; font-size: 14pt; font-weight: bold; color: #1a1a6e; padding: 4pt 0;">
            {course_name}
        </td></tr></table>

        <table width="100%"><tr><td style="text-align: center; font-size: 10pt; color: #4a4a6a;">
            conducted by IntelliForge Learning
        </td></tr></table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 10pt;">&nbsp;</td></tr></table>

        <!-- Details row with gold accents -->
        <table width="85%" align="center">
            <tr>
                <td width="30%" style="text-align: center; padding: 0 8pt;">
                    <table width="100%">
                        <tr><td style="text-align: center; font-size: 10pt; color: #1a1a3e; padding-bottom: 3pt;">{completion_date}</td></tr>
                        <tr><td style="border-top: 1px solid #d4af37; text-align: center; font-size: 7pt; color: #8b8b8b; padding-top: 3pt;">DATE</td></tr>
                    </table>
                </td>
                <td width="40%" style="text-align: center; padding: 0 8pt;">
                    <table width="100%">
                        <tr><td style="text-align: center; font-size: 10pt; color: #1a1a3e; padding-bottom: 3pt;">{instructor_name}</td></tr>
                        <tr><td style="border-top: 1px solid #d4af37; text-align: center; font-size: 7pt; color: #8b8b8b; padding-top: 3pt;">INSTRUCTOR</td></tr>
                    </table>
                </td>
                <td width="30%" style="text-align: center; padding: 0 8pt;">
                    <table width="100%">
                        <tr><td style="text-align: center; font-size: 10pt; color: #1a1a3e; padding-bottom: 3pt;">learning.intelliforge.tech</td></tr>
                        <tr><td style="border-top: 1px solid #d4af37; text-align: center; font-size: 7pt; color: #8b8b8b; padding-top: 3pt;">VERIFY AT</td></tr>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 6pt;">&nbsp;</td></tr></table>

        <!-- Seal -->
        <table width="100%"><tr><td style="text-align: center;">
            <table width="70pt" align="center" style="border: 2px solid #d4af37;">
            <tr><td style="text-align: center; padding: 6pt 4pt; background-color: #1a1a6e;">
                <table width="100%"><tr><td style="text-align: center; font-size: 7pt; color: #d4af37; font-weight: bold;">VERIFIED</td></tr></table>
                <table width="100%"><tr><td style="text-align: center; font-size: 5pt; color: #d4af37;">&#9733;</td></tr></table>
                <table width="100%"><tr><td style="text-align: center; font-size: 5pt; color: #d4af37;">IF</td></tr></table>
            </td></tr>
            </table>
        </td></tr></table>

        <!-- Spacer -->
        <table width="100%"><tr><td style="font-size: 4pt;">&nbsp;</td></tr></table>

        <!-- Certificate ID -->
        <table width="100%"><tr><td style="text-align: center; font-size: 7pt; color: #b8b8b8;">
            Certificate ID: {certificate_id}
        </td></tr></table>

        <!-- Bottom ornament -->
        <table width="100%"><tr><td style="text-align: center; font-size: 7pt; color: #f0e6c8; padding-top: 4pt;">
            &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670; &nbsp; &#9670;
        </td></tr></table>

    </td></tr>
    </table>
    <!-- End gold accent border -->

    </td></tr>
    </table>
    <!-- End navy border -->

    </td></tr>
    </table>
    <!-- End outer gold border -->

</body>
</html>
"""


def _build_cert_pdf(data: dict) -> bytes:
    """Render certificate compact data into PDF bytes."""
    full_html = CERTIFICATE_TEMPLATE.format(
        participant_name=data["n"],
        course_name=data["c"],
        completion_date=data["d"],
        instructor_name=data["i"],
        certificate_id=_cert_id(data),
    )
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=full_html, dest=pdf_buffer, encoding="UTF-8")
    if pisa_status.err:
        raise Exception("Error generating certificate PDF")
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


@app.post("/api/certificate")
async def generate_certificate(request: CertificateRequest, req: Request):
    """Generate a certificate and return shareable URL + PDF download URL."""
    try:
        if request.course_name not in COURSES:
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

        base_url = str(req.base_url).rstrip("/")
        shareable_url = f"{base_url}/certificate/{token}"

        logger.info(f"Certificate issued for {name} – {request.course_name}")

        return JSONResponse({
            "certificate_id": _cert_id(cert_data),
            "token": token,
            "url": shareable_url,
            "download_url": f"{shareable_url}/download",
            "participant_name": name,
            "course_name": request.course_name,
        })

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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
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
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&amp;data={qr_data}" alt="QR Code" width="80" height="80" />
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


@app.get("/certificate/{token}")
async def view_certificate(token: str, req: Request):
    """Public certificate viewer – serves a styled HTML page."""
    data = _resolve_cert(token)

    base_url = str(req.base_url).rstrip("/")
    page_url = f"{base_url}/certificate/{token}"
    download_url = f"{page_url}/download"

    cert_title = f"{data['n']} – Certificate for {data['c']}"
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
        qr_data=quote(page_url, safe=""),
    )
    return HTMLResponse(content=html)


@app.get("/certificate/{token}/download")
async def download_certificate(token: str):
    """Download the certificate as a PDF."""
    data = _resolve_cert(token)
    pdf_bytes = _build_cert_pdf(data)
    safe_name = data["n"].replace(" ", "_")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Certificate_{safe_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@app.get("/certificate/{token}/verify")
async def verify_certificate(token: str):
    """API endpoint to verify a certificate's authenticity."""
    data = _decode_cert(token)
    if data is None:
        return JSONResponse({"valid": False, "message": "Invalid or tampered certificate"}, status_code=400)
    return {
        "valid": True,
        "certificate_id": _cert_id(data),
        "participant_name": data["n"],
        "course_name": data["c"],
        "completion_date": data["d"],
        "instructor_name": data["i"],
    }


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

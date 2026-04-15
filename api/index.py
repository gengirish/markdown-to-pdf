"""
FastAPI backend for Markdown to PDF Converter
Handles markdown parsing, PDF generation, and certificate creation
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
import uuid
import json
import os
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Markdown to PDF API",
    description="Convert Markdown to PDF with Python backend",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Certificate store – JSON file for local dev, /tmp for serverless
# ---------------------------------------------------------------------------
CERT_STORE_PATH = Path(os.environ.get(
    "CERT_STORE_PATH",
    Path(__file__).resolve().parent.parent / "certificates.json",
))

_cert_cache: dict | None = None


def _load_certs() -> dict:
    global _cert_cache
    if _cert_cache is not None:
        return _cert_cache
    if CERT_STORE_PATH.exists():
        try:
            _cert_cache = json.loads(CERT_STORE_PATH.read_text(encoding="utf-8"))
            return _cert_cache
        except Exception:
            pass
    _cert_cache = {}
    return _cert_cache


def _save_certs(certs: dict) -> None:
    global _cert_cache
    _cert_cache = certs
    try:
        CERT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CERT_STORE_PATH.write_text(json.dumps(certs, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not persist certificate store: {exc}")


# Request models
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


def _build_cert_pdf(cert: dict) -> bytes:
    """Render a certificate dict into PDF bytes."""
    raw = f"{cert['participant_name']}-{cert['course_name']}-{cert['completion_date']}"
    certificate_id = "IF-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()

    full_html = CERTIFICATE_TEMPLATE.format(
        participant_name=cert["participant_name"],
        course_name=cert["course_name"],
        completion_date=cert["completion_date"],
        instructor_name=cert["instructor_name"],
        certificate_id=certificate_id,
    )

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=full_html, dest=pdf_buffer, encoding="UTF-8")
    if pisa_status.err:
        raise Exception("Error generating certificate PDF")
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


@app.post("/api/certificate")
async def generate_certificate(request: CertificateRequest, req: Request):
    """
    Generate a participation certificate, persist it, and return a shareable URL.
    """
    try:
        if request.course_name not in COURSES:
            raise HTTPException(status_code=400, detail=f"Unknown course: {request.course_name}")
        if not request.participant_name.strip():
            raise HTTPException(status_code=400, detail="Participant name is required")

        cert_uuid = str(uuid.uuid4())
        cert_data = {
            "id": cert_uuid,
            "participant_name": request.participant_name.strip(),
            "course_name": request.course_name,
            "completion_date": request.completion_date,
            "instructor_name": request.instructor_name,
            "created_at": datetime.utcnow().isoformat(),
        }

        certs = _load_certs()
        certs[cert_uuid] = cert_data
        _save_certs(certs)

        base_url = str(req.base_url).rstrip("/")
        shareable_url = f"{base_url}/certificate/{cert_uuid}"

        logger.info(f"Certificate created: {cert_uuid} for {request.participant_name}")

        return JSONResponse({
            "certificate_id": cert_uuid,
            "url": shareable_url,
            "download_url": f"{shareable_url}/download",
            "participant_name": cert_data["participant_name"],
            "course_name": cert_data["course_name"],
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating certificate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {str(e)}")


# ---------------------------------------------------------------------------
# Public certificate viewer page
# ---------------------------------------------------------------------------
VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{participant_name}'s IntelliForge Certificate</title>
    <meta property="og:title" content="{participant_name} – Certificate of Participation" />
    <meta property="og:description" content="{participant_name} successfully completed {course_name} at IntelliForge Learning." />
    <meta property="og:type" content="website" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }}

        .viewer-card {{
            background: #fff;
            border-radius: 20px;
            box-shadow: 0 25px 80px rgba(0, 0, 0, 0.25);
            max-width: 580px;
            width: 100%;
            overflow: hidden;
            animation: slideUp 0.5s ease-out;
        }}

        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}

        .viewer-header {{
            background: linear-gradient(135deg, #1a1a6e 0%, #2d2d8e 100%);
            padding: 2rem 2.5rem 1.8rem;
            text-align: center;
        }}

        .viewer-org {{
            font-size: 0.7rem;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #d4af37;
            margin-bottom: 0.4rem;
        }}

        .viewer-brand {{
            font-family: 'Playfair Display', serif;
            font-size: 1.4rem;
            color: #fff;
            font-weight: 700;
        }}

        .viewer-badge {{
            display: inline-block;
            background: rgba(212, 175, 55, 0.15);
            border: 1px solid #d4af37;
            color: #d4af37;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            padding: 0.3rem 1rem;
            border-radius: 20px;
            margin-top: 1rem;
        }}

        .viewer-body {{
            padding: 2.5rem;
            text-align: center;
        }}

        .viewer-label {{
            font-size: 0.75rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #a0aec0;
            margin-bottom: 0.5rem;
        }}

        .viewer-name {{
            font-family: 'Playfair Display', serif;
            font-size: 2rem;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 0.3rem;
            line-height: 1.2;
        }}

        .viewer-course {{
            font-size: 0.95rem;
            color: #553c9a;
            font-weight: 600;
            margin-bottom: 1.5rem;
        }}

        .viewer-meta {{
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}

        .viewer-meta-item {{
            text-align: center;
        }}

        .viewer-meta-value {{
            font-size: 0.85rem;
            color: #2d3748;
            font-weight: 500;
        }}

        .viewer-meta-label {{
            font-size: 0.65rem;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 0.2rem;
        }}

        .viewer-divider {{
            height: 1px;
            background: linear-gradient(to right, transparent, #e2e8f0, transparent);
            margin: 0.5rem 0 2rem;
        }}

        .download-btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.6rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            border: none;
            padding: 0.9rem 2rem;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }}

        .download-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(102, 126, 234, 0.6);
        }}

        .download-btn svg {{
            width: 18px;
            height: 18px;
        }}

        .viewer-footer {{
            background: #f7fafc;
            border-top: 1px solid #e2e8f0;
            padding: 1.2rem 2.5rem;
            text-align: center;
        }}

        .viewer-footer p {{
            font-size: 0.75rem;
            color: #a0aec0;
        }}

        .viewer-footer a {{
            color: #667eea;
            text-decoration: none;
        }}

        .viewer-footer a:hover {{
            text-decoration: underline;
        }}

        .verified-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            background: #f0fff4;
            border: 1px solid #68d391;
            color: #276749;
            font-size: 0.7rem;
            font-weight: 600;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            margin-bottom: 1.5rem;
        }}

        .verified-badge svg {{
            width: 14px;
            height: 14px;
        }}

        @media (max-width: 480px) {{
            body {{ padding: 1rem; }}
            .viewer-body {{ padding: 1.5rem; }}
            .viewer-name {{ font-size: 1.5rem; }}
            .viewer-meta {{ gap: 1rem; }}
        }}
    </style>
</head>
<body>
    <div class="viewer-card">
        <div class="viewer-header">
            <div class="viewer-org">An IntelliForge AI Initiative</div>
            <div class="viewer-brand">IntelliForge Learning</div>
            <div class="viewer-badge">Certificate of Participation</div>
        </div>

        <div class="viewer-body">
            <div class="verified-badge">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified Certificate
            </div>

            <div class="viewer-label">This certificate is awarded to</div>
            <div class="viewer-name">{participant_name}</div>
            <div class="viewer-divider"></div>
            <div class="viewer-course">{course_name}</div>

            <div class="viewer-meta">
                <div class="viewer-meta-item">
                    <div class="viewer-meta-value">{completion_date}</div>
                    <div class="viewer-meta-label">Date</div>
                </div>
                <div class="viewer-meta-item">
                    <div class="viewer-meta-value">{instructor_name}</div>
                    <div class="viewer-meta-label">Instructor</div>
                </div>
                <div class="viewer-meta-item">
                    <div class="viewer-meta-value">{certificate_id_short}</div>
                    <div class="viewer-meta-label">Certificate ID</div>
                </div>
            </div>

            <a class="download-btn" href="{download_url}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download Certificate
            </a>
        </div>

        <div class="viewer-footer">
            <p>
                Issued by <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener">IntelliForge Learning</a>
                &nbsp;&middot;&nbsp;
                For support, contact <a href="mailto:support@intelliforge.tech">support@intelliforge.tech</a>
            </p>
        </div>
    </div>
</body>
</html>"""


@app.get("/certificate/{cert_id}")
async def view_certificate(cert_id: str, req: Request):
    """Public certificate viewer – serves a styled HTML page."""
    certs = _load_certs()
    cert = certs.get(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    raw = f"{cert['participant_name']}-{cert['course_name']}-{cert['completion_date']}"
    short_id = "IF-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()

    base_url = str(req.base_url).rstrip("/")
    download_url = f"{base_url}/certificate/{cert_id}/download"

    html = VIEWER_HTML.format(
        participant_name=cert["participant_name"],
        course_name=cert["course_name"],
        completion_date=cert["completion_date"],
        instructor_name=cert["instructor_name"],
        certificate_id_short=short_id,
        download_url=download_url,
    )
    return HTMLResponse(content=html)


@app.get("/certificate/{cert_id}/download")
async def download_certificate(cert_id: str):
    """Download the certificate PDF."""
    certs = _load_certs()
    cert = certs.get(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    pdf_bytes = _build_cert_pdf(cert)
    safe_name = cert["participant_name"].replace(" ", "_")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Certificate_{safe_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@app.get("/certificate/{cert_id}/data")
async def certificate_data(cert_id: str):
    """Return certificate metadata as JSON (for API consumers)."""
    certs = _load_certs()
    cert = certs.get(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

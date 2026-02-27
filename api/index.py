"""
FastAPI backend for Markdown to PDF Converter
Handles markdown parsing, PDF generation, and certificate creation
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import markdown
from xhtml2pdf import pisa
from io import BytesIO
import logging
import hashlib
from datetime import datetime

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
            margin: 0;
        }}

        body {{
            margin: 0;
            padding: 0;
            font-family: Helvetica, Arial, sans-serif;
            color: #2d3748;
        }}

        .page {{
            width: 842pt;
            height: 595pt;
            padding: 20pt 28pt;
        }}

        .frame-outer {{
            border: 3pt solid #4338ca;
            padding: 8pt;
            height: 547pt;
        }}

        .frame-inner {{
            border: 1pt solid #a78bfa;
            height: 527pt;
            text-align: center;
            padding: 0 40pt;
        }}

        .spacer-top {{
            height: 30pt;
        }}

        .org-label {{
            font-size: 8pt;
            color: #7c3aed;
            text-transform: uppercase;
            margin: 0;
            padding: 0;
        }}

        .org-name {{
            font-size: 16pt;
            font-weight: bold;
            color: #4338ca;
            margin: 0;
            padding: 2pt 0 0 0;
        }}

        .divider {{
            border: none;
            border-top: 1pt solid #c4b5fd;
            width: 120pt;
            margin: 12pt auto;
        }}

        .cert-title {{
            font-size: 36pt;
            font-weight: bold;
            color: #4338ca;
            margin: 0;
            padding: 0;
        }}

        .cert-subtitle {{
            font-size: 14pt;
            color: #6b7280;
            margin: 0;
            padding: 4pt 0 0 0;
        }}

        .spacer-mid {{
            height: 20pt;
        }}

        .presented {{
            font-size: 9pt;
            color: #9ca3af;
            text-transform: uppercase;
            margin: 0;
            padding: 0;
        }}

        .spacer-name {{
            height: 10pt;
        }}

        .name {{
            font-size: 28pt;
            font-weight: bold;
            color: #1e1b4b;
            margin: 0;
            padding: 0 0 3pt 0;
            border-bottom: 2pt solid #4338ca;
        }}

        .spacer-desc {{
            height: 14pt;
        }}

        .desc {{
            font-size: 10pt;
            color: #4b5563;
            margin: 0;
            padding: 0;
        }}

        .course {{
            font-size: 13pt;
            font-weight: bold;
            color: #4338ca;
            margin: 0;
            padding: 4pt 0;
        }}

        .spacer-details {{
            height: 20pt;
        }}

        .info-table {{
            width: 600pt;
            margin-left: auto;
            margin-right: auto;
        }}

        .info-table td {{
            text-align: center;
            padding: 0 20pt;
            width: 33%;
        }}

        .info-val {{
            font-size: 10pt;
            color: #1f2937;
            padding-bottom: 4pt;
            margin: 0;
        }}

        .info-line {{
            border: none;
            border-top: 1pt solid #d1d5db;
            margin: 0 0 4pt 0;
        }}

        .info-lbl {{
            font-size: 7pt;
            color: #9ca3af;
            text-transform: uppercase;
            margin: 0;
        }}

        .cert-id {{
            font-size: 7pt;
            color: #d1d5db;
            margin: 0;
            padding: 14pt 0 0 0;
        }}

        .footer-note {{
            font-size: 7pt;
            color: #d1d5db;
            margin: 0;
            padding: 4pt 0 0 0;
        }}
    </style>
</head>
<body>
    <div class="page">
        <div class="frame-outer">
            <div class="frame-inner">

                <div class="spacer-top"></div>

                <p class="org-label">An IntelliForge AI Initiative</p>
                <p class="org-name">IntelliForge Learning</p>

                <hr class="divider" />

                <p class="cert-title">CERTIFICATE</p>
                <p class="cert-subtitle">of Participation</p>

                <div class="spacer-mid"></div>

                <p class="presented">This is proudly presented to</p>
                <div class="spacer-name"></div>
                <p class="name">{participant_name}</p>

                <div class="spacer-desc"></div>

                <p class="desc">for successfully completing the training program</p>
                <p class="course">{course_name}</p>
                <p class="desc">conducted by IntelliForge Learning</p>

                <div class="spacer-details"></div>

                <table class="info-table">
                    <tr>
                        <td>
                            <p class="info-val">{completion_date}</p>
                            <hr class="info-line" />
                            <p class="info-lbl">Date</p>
                        </td>
                        <td>
                            <p class="info-val">{instructor_name}</p>
                            <hr class="info-line" />
                            <p class="info-lbl">Instructor</p>
                        </td>
                        <td>
                            <p class="info-val">learning.intelliforge.tech</p>
                            <hr class="info-line" />
                            <p class="info-lbl">Verify At</p>
                        </td>
                    </tr>
                </table>

                <p class="cert-id">Certificate ID: {certificate_id}</p>
                <p class="footer-note">IntelliForge Learning &bull; AI Training &amp; Learning Platform</p>

            </div>
        </div>
    </div>
</body>
</html>
"""


@app.post("/api/certificate")
async def generate_certificate(request: CertificateRequest):
    """
    Generate a participation certificate PDF for an IntelliForge Learning course.
    """
    try:
        if request.course_name not in COURSES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown course: {request.course_name}"
            )

        if not request.participant_name.strip():
            raise HTTPException(status_code=400, detail="Participant name is required")

        raw = f"{request.participant_name}-{request.course_name}-{request.completion_date}"
        certificate_id = "IF-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()

        full_html = CERTIFICATE_TEMPLATE.format(
            participant_name=request.participant_name.strip(),
            course_name=request.course_name,
            completion_date=request.completion_date,
            instructor_name=request.instructor_name,
            certificate_id=certificate_id,
        )

        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(
            src=full_html,
            dest=pdf_buffer,
            encoding="UTF-8",
        )

        if pisa_status.err:
            raise Exception("Error generating certificate PDF")

        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.getvalue()
        safe_name = request.participant_name.strip().replace(" ", "_")
        filename = f"Certificate_{safe_name}.pdf"

        logger.info(f"Certificate generated for {request.participant_name} – {request.course_name}")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating certificate: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate certificate: {str(e)}",
        )


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

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
            size: A4 landscape;
            margin: 0;
        }}

        body {{
            margin: 0;
            padding: 0;
            font-family: 'Helvetica', 'Arial', sans-serif;
            color: #1a202c;
        }}

        .certificate {{
            width: 100%;
            height: 100%;
            padding: 40pt 60pt;
            position: relative;
        }}

        .border-outer {{
            border: 3pt solid #667eea;
            padding: 18pt;
            height: 100%;
        }}

        .border-inner {{
            border: 1pt solid #b794f4;
            padding: 30pt 40pt;
            height: 100%;
            text-align: center;
        }}

        .logo-line {{
            font-size: 11pt;
            letter-spacing: 3pt;
            color: #667eea;
            text-transform: uppercase;
            margin-bottom: 4pt;
        }}

        .org-name {{
            font-size: 20pt;
            font-weight: bold;
            color: #553c9a;
            margin-bottom: 18pt;
        }}

        .title {{
            font-size: 30pt;
            font-weight: bold;
            color: #667eea;
            letter-spacing: 4pt;
            text-transform: uppercase;
            margin-bottom: 6pt;
        }}

        .subtitle {{
            font-size: 13pt;
            color: #718096;
            margin-bottom: 22pt;
        }}

        .presented-to {{
            font-size: 11pt;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 2pt;
            margin-bottom: 8pt;
        }}

        .participant-name {{
            font-size: 28pt;
            font-weight: bold;
            color: #2d3748;
            border-bottom: 2pt solid #667eea;
            display: inline-block;
            padding: 0 30pt 6pt;
            margin-bottom: 16pt;
        }}

        .description {{
            font-size: 11pt;
            color: #4a5568;
            line-height: 1.7;
            max-width: 480pt;
            margin: 0 auto 24pt;
        }}

        .course-name {{
            font-weight: bold;
            color: #553c9a;
        }}

        .details-row {{
            margin-top: 18pt;
        }}

        .details-table {{
            width: 80%;
            margin: 0 auto;
            border: none;
        }}

        .details-table td {{
            border: none;
            padding: 8pt 16pt;
            vertical-align: top;
        }}

        .detail-label {{
            font-size: 8pt;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 1pt;
            border-top: 1pt solid #e2e8f0;
            padding-top: 6pt;
        }}

        .detail-value {{
            font-size: 11pt;
            color: #2d3748;
            padding-bottom: 4pt;
        }}

        .cert-id {{
            font-size: 8pt;
            color: #cbd5e0;
            margin-top: 12pt;
            letter-spacing: 1pt;
        }}
    </style>
</head>
<body>
    <div class="certificate">
        <div class="border-outer">
            <div class="border-inner">
                <div class="logo-line">An IntelliForge AI Initiative</div>
                <div class="org-name">IntelliForge Learning</div>

                <div class="title">Certificate</div>
                <div class="subtitle">of Participation</div>

                <div class="presented-to">This is proudly presented to</div>
                <div class="participant-name">{participant_name}</div>

                <div class="description">
                    For successfully participating in the training program
                    <br/>
                    <span class="course-name">{course_name}</span>
                    <br/>
                    conducted by IntelliForge Learning
                </div>

                <div class="details-row">
                    <table class="details-table">
                        <tr>
                            <td>
                                <div class="detail-value">{completion_date}</div>
                                <div class="detail-label">Date</div>
                            </td>
                            <td>
                                <div class="detail-value">{instructor_name}</div>
                                <div class="detail-label">Instructor</div>
                            </td>
                            <td>
                                <div class="detail-value">learning.intelliforge.tech</div>
                                <div class="detail-label">Platform</div>
                            </td>
                        </tr>
                    </table>
                </div>

                <div class="cert-id">Certificate ID: {certificate_id}</div>
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

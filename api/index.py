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

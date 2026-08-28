"""
Seed script for CertForge local development.

Creates:
- System organization (IntelliForge Learning) for legacy credentials
- 3 default certificate templates (Professional, Academic, Modern)
- Legacy course catalog entries

Usage: python -m api.seed
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── System organization ────────────────────────────────────────────────

SYSTEM_ORG = {
    "slug": "intelliforge-learning",
    "name": "IntelliForge Learning",
    "tier": "scale",
    "monthly_quota": -1,  # unlimited
}

# ── Default templates ──────────────────────────────────────────────────

DEFAULT_TEMPLATES = [
    {
        "name": "Professional",
        "is_default": True,
        "variables": [
            "name", "title", "date", "credential_id", "qr", "issuer_name",
            "logo_url", "primary_color", "accent_color", "footer_text",
        ],
        "html_source": """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page { size: 842pt 595pt; margin: 0; }
body { font-family: Helvetica, Arial, sans-serif; color: #2d3748; margin: 0; padding: 0; }
table { border-collapse: collapse; }
td { padding: 0; }
</style>
</head>
<body>
<table width="100%" height="100%" style="background-color: #0f172a;">
<tr><td style="padding: 24pt 32pt;">
<table width="100%" style="background-color: #ffffff;">
<tr><td>
    <table width="100%" style="background-color: {{primary_color}};">
    <tr><td style="padding: 30pt 40pt 26pt;" align="center">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 4pt; color: {{accent_color}}; font-weight: bold; padding-bottom: 4pt; text-align: center;">
                {{issuer_name}}
            </td></tr>
            <tr><td align="center" style="font-size: 9pt; letter-spacing: 3pt; color: #d4af37; font-weight: bold; text-align: center; padding-top: 8pt;">
                CERTIFICATE OF COMPLETION
            </td></tr>
        </table>
    </td></tr>
    </table>
    <table width="100%">
    <tr><td style="padding: 28pt 50pt 20pt;" align="center">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 3pt; color: #a0aec0; padding-bottom: 6pt;">THIS CERTIFICATE IS AWARDED TO</td></tr>
            <tr><td align="center" style="font-size: 34pt; font-weight: bold; color: #1a202c; padding: 4pt 0 2pt;">{{name}}</td></tr>
        </table>
        <table width="60%" align="center"><tr><td style="border-top: 2px solid #d4af37; font-size: 1pt;">&nbsp;</td></tr></table>
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 16pt; font-weight: bold; color: #3730a3; padding: 14pt 0 20pt;">{{title}}</td></tr>
        </table>
        <table width="85%" align="center" cellspacing="0" cellpadding="0" style="border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7;">
            <tr>
                <td width="50%" align="center" style="padding: 12pt 8pt;">
                    <table cellspacing="0" cellpadding="0"><tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{{date}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">DATE</td></tr></table>
                </td>
                <td width="50%" align="center" style="padding: 12pt 8pt; border-left: 1px solid #edf2f7;">
                    <table cellspacing="0" cellpadding="0"><tr><td align="center" style="font-size: 11pt; color: #2d3748; font-weight: bold;">{{credential_id}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #a0aec0; padding-top: 3pt;">CREDENTIAL ID</td></tr></table>
                </td>
            </tr>
        </table>
        <table width="100%" cellspacing="0" cellpadding="0" style="padding-top: 16pt;">
        <tr><td align="center">
            <table align="center" cellspacing="0" cellpadding="0"><tr>
                <td style="padding-right: 12pt; vertical-align: middle;"><img src="{{qr}}" width="70" height="70" /></td>
                <td style="vertical-align: middle; text-align: left;">
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 9pt; font-weight: bold; color: #2d3748;">Scan to Verify</td></tr></table>
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 7pt; color: #a0aec0;">This QR code links to the permanent<br/>verification page.</td></tr></table>
                </td>
            </tr></table>
        </td></tr>
        </table>
    </td></tr>
    </table>
    <table width="100%" style="background-color: #f8fafc; border-top: 1px solid #edf2f7;">
    <tr><td align="center" style="padding: 10pt 40pt; font-size: 7pt; color: #a0aec0;">
        {{footer_text}}
    </td></tr>
    </table>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>""",
    },
    {
        "name": "Academic",
        "is_default": True,
        "variables": [
            "name", "title", "date", "credential_id", "qr", "issuer_name",
            "logo_url", "primary_color", "accent_color", "footer_text",
        ],
        "html_source": """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page { size: 842pt 595pt; margin: 0; }
body { font-family: Helvetica, Arial, sans-serif; color: #1a202c; margin: 0; padding: 0; }
table { border-collapse: collapse; }
td { padding: 0; }
</style>
</head>
<body>
<table width="100%" height="100%" style="background-color: #0a0a18;">
<tr><td style="padding: 20pt 28pt;">
<table width="100%" style="background-color: #ffffff; border: 1.5pt solid #1e40af;">
<tr><td>
    <table width="100%" style="background-color: {{primary_color}};">
    <tr>
        <td style="padding: 0; width: 6pt; background-color: #1e40af;">&nbsp;</td>
        <td style="padding: 22pt 36pt 18pt;">
            <table cellspacing="0" cellpadding="0">
                <tr><td style="font-size: 7pt; letter-spacing: 2.5pt; color: {{accent_color}}; font-weight: bold;">{{issuer_name}}</td></tr>
                <tr><td style="font-size: 9pt; color: #d1d5db; padding-top: 4pt; letter-spacing: 1.5pt; font-weight: bold;">CERTIFICATE OF ACHIEVEMENT</td></tr>
            </table>
        </td>
    </tr>
    </table>
    <table width="100%">
    <tr><td style="padding: 20pt 44pt 14pt;" align="center">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 3pt; color: #718096; padding-bottom: 6pt;">THIS IS TO CERTIFY THAT</td></tr>
            <tr><td align="center" style="font-size: 28pt; font-weight: bold; color: #1a202c; padding-bottom: 4pt;">{{name}}</td></tr>
        </table>
        <table width="70%" align="center"><tr><td style="border-top: 2px solid #1e40af; font-size: 1pt;">&nbsp;</td></tr></table>
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 9pt; color: #4b5563; padding: 10pt 0 4pt;">has successfully completed</td></tr>
            <tr><td align="center" style="font-size: 18pt; font-weight: bold; color: #1e3a5f; padding-bottom: 14pt;">{{title}}</td></tr>
        </table>
        <table width="92%" align="center" cellspacing="0" cellpadding="0" style="border: 1px solid #e2e8f0;">
            <tr style="background-color: #f7fafc;">
                <td width="33%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0;">DATE</td>
                <td width="34%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0; border-left: 1px solid #e2e8f0;">CREDENTIAL ID</td>
                <td width="33%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0; border-left: 1px solid #e2e8f0;">VERIFY</td>
            </tr>
            <tr>
                <td style="padding: 9pt 6pt; font-size: 10pt; font-weight: bold; color: #1a202c; text-align: center;">{{date}}</td>
                <td style="padding: 9pt 6pt; font-size: 9pt; font-weight: bold; color: #1a202c; text-align: center; border-left: 1px solid #e2e8f0;">{{credential_id}}</td>
                <td align="center" style="padding: 6pt; border-left: 1px solid #e2e8f0;"><img src="{{qr}}" width="52" height="52" /></td>
            </tr>
        </table>
    </td></tr>
    </table>
    <table width="100%" style="background-color: #f8fafc; border-top: 1px solid #e2e8f0;">
    <tr><td align="center" style="padding: 8pt 32pt; font-size: 6.5pt; color: #718096;">
        {{footer_text}}
    </td></tr>
    </table>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>""",
    },
    {
        "name": "Modern",
        "is_default": True,
        "variables": [
            "name", "title", "date", "credential_id", "qr", "issuer_name",
            "logo_url", "primary_color", "accent_color", "footer_text",
        ],
        "html_source": """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page { size: 842pt 595pt; margin: 0; }
body { font-family: Helvetica, Arial, sans-serif; color: #1a202c; margin: 0; padding: 0; }
table { border-collapse: collapse; }
td { padding: 0; }
</style>
</head>
<body>
<table width="100%" height="100%" style="background-color: #18181b;">
<tr><td style="padding: 22pt 30pt;">
<table width="100%" style="background-color: #ffffff;">
<tr><td>
    <table width="100%" cellspacing="0" cellpadding="0">
    <tr>
        <td style="padding: 0; height: 4pt; background-color: {{primary_color}};">&nbsp;</td>
    </tr>
    </table>
    <table width="100%">
    <tr><td style="padding: 24pt 40pt 8pt;">
        <table cellspacing="0" cellpadding="0">
            <tr><td style="font-size: 7pt; letter-spacing: 3pt; color: {{accent_color}}; font-weight: bold; text-transform: uppercase;">{{issuer_name}}</td></tr>
        </table>
    </td></tr>
    </table>
    <table width="100%">
    <tr><td style="padding: 16pt 50pt 20pt;" align="center">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 7pt; letter-spacing: 4pt; color: #9ca3af; padding-bottom: 10pt; text-transform: uppercase;">CREDENTIAL AWARDED TO</td></tr>
            <tr><td align="center" style="font-size: 36pt; font-weight: bold; color: #18181b; padding: 0 0 6pt; letter-spacing: -0.5pt;">{{name}}</td></tr>
        </table>
        <table width="40%" align="center"><tr><td style="border-top: 3px solid #8b5cf6; font-size: 1pt;">&nbsp;</td></tr></table>
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 7pt; color: #9ca3af; padding: 12pt 0 4pt; letter-spacing: 2pt; text-transform: uppercase;">FOR COMPLETING</td></tr>
            <tr><td align="center" style="font-size: 18pt; font-weight: bold; color: #7c3aed; padding-bottom: 18pt;">{{title}}</td></tr>
        </table>
        <table width="70%" align="center" cellspacing="0" cellpadding="0">
            <tr>
                <td width="50%" align="center" style="padding: 10pt;">
                    <table cellspacing="0" cellpadding="0"><tr><td align="center" style="font-size: 12pt; font-weight: bold; color: #18181b;">{{date}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #9ca3af; padding-top: 4pt;">DATE ISSUED</td></tr></table>
                </td>
                <td width="50%" align="center" style="padding: 10pt; border-left: 1px solid #e5e7eb;">
                    <table cellspacing="0" cellpadding="0"><tr><td align="center" style="font-size: 10pt; font-weight: bold; color: #18181b;">{{credential_id}}</td></tr>
                    <tr><td align="center" style="font-size: 6pt; letter-spacing: 2pt; color: #9ca3af; padding-top: 4pt;">CREDENTIAL ID</td></tr></table>
                </td>
            </tr>
        </table>
        <table width="100%" cellspacing="0" cellpadding="0" style="padding-top: 16pt;">
        <tr><td align="center">
            <table align="center" cellspacing="0" cellpadding="0"><tr>
                <td style="padding-right: 10pt;"><img src="{{qr}}" width="60" height="60" /></td>
                <td style="vertical-align: middle; text-align: left;">
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 8pt; font-weight: bold; color: #18181b;">Verify this credential</td></tr></table>
                    <table cellspacing="0" cellpadding="0"><tr><td style="font-size: 6.5pt; color: #9ca3af;">Scan the QR code or visit the verification URL.</td></tr></table>
                </td>
            </tr></table>
        </td></tr>
        </table>
    </td></tr>
    </table>
    <table width="100%" cellspacing="0" cellpadding="0">
    <tr>
        <td style="padding: 0; height: 3pt; background: linear-gradient(to right, #8b5cf6, #ec4899, #f59e0b);">&nbsp;</td>
    </tr>
    </table>
    <table width="100%" style="background-color: #fafafa;">
    <tr><td align="center" style="padding: 10pt 40pt; font-size: 7pt; color: #9ca3af;">
        {{footer_text}}
    </td></tr>
    </table>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>""",
    },
]

# ── Seed courses (legacy) ──────────────────────────────────────────────

SEED_COURSES = [
    ("AI Product Development Fundamentals", "Learn the fundamentals of building AI-powered products"),
    ("Building AI-Powered Applications", "Hands-on course building real AI applications"),
    ("Prompt Engineering & LLM Integration", "Master prompt engineering and LLM API integration"),
    ("Full-Stack AI Development", "End-to-end AI application development"),
    ("AI Product Design & UX", "Design thinking for AI products"),
    ("Digital Profile Creation", "Build your professional digital presence"),
    ("Deploying AI Solutions", "Deploy and scale AI models in production"),
    ("AI Code Reviewer Course", "Learn systematic AI-assisted code review"),
    ("VTU Industry Internship – IntelliForge AI Programme", "Formal internship completion credential for VTU / college records"),
    ("RAG Systems & Architecture Masterclass", "Masterclass on retrieval-augmented generation (RAG) systems"),
]


def seed():
    """Run the seed script."""
    from api.models import get_db, init_db
    from api.models.organization import Organization, OrgMember
    from api.models.template import Template

    logger.info("Initializing database tables...")
    init_db()

    with get_db() as session:
        # ── System organization ────────────────────────────────────────
        org = session.query(Organization).filter_by(slug=SYSTEM_ORG["slug"]).first()
        if not org:
            org = Organization(**SYSTEM_ORG)
            session.add(org)
            session.flush()  # get the id
            logger.info(f"Created system org: {org.slug} (id={org.id})")
        else:
            logger.info(f"System org already exists: {org.slug}")

        # ── Default templates ──────────────────────────────────────────
        for tpl_data in DEFAULT_TEMPLATES:
            existing = session.query(Template).filter_by(
                name=tpl_data["name"], org_id=None, is_default=True
            ).first()
            if not existing:
                tpl = Template(
                    org_id=None,
                    name=tpl_data["name"],
                    html_source=tpl_data["html_source"],
                    variables=tpl_data["variables"],
                    is_default=True,
                )
                session.add(tpl)
                logger.info(f"Created default template: {tpl_data['name']}")
            else:
                logger.info(f"Default template already exists: {tpl_data['name']}")

    logger.info("Seed complete.")


if __name__ == "__main__":
    seed()

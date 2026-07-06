"""
HTML sources for certificate PDFs (xhtml2pdf).
Participation: general course completion.
Internship (VTU-style): formal fields for institutional records + verifiable QR.
Appreciation: sports / event participation (landscape, Decathlon Play-style layout).
"""

# Landscape A4-style (matches existing participation certificate)
CERTIFICATE_PARTICIPATION_HTML = """
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

<table width="100%" height="100%" style="background-color: #0f0f23;">
<tr><td style="padding: 24pt 32pt;">

<table width="100%" style="background-color: #ffffff;">
<tr><td>

    <table width="100%" style="background-color: #15155e;">
    <tr><td style="padding: 30pt 40pt 26pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 4pt; color: #d4af37; font-weight: bold; padding-bottom: 4pt; text-align: center;">
                {org_tagline}
            </td></tr>
            <tr><td align="center" style="font-size: 24pt; font-weight: bold; color: #ffffff; padding: 6pt 0 12pt; text-align: center;">
                {brand_name}
            </td></tr>
            <tr><td align="center" style="text-align: center; padding: 0;">
                <table align="center" cellspacing="0" cellpadding="0" style="border: 2px solid #d4af37;">
                <tr><td align="center" style="padding: 6pt 30pt; font-size: 9pt; letter-spacing: 3pt; color: #d4af37; font-weight: bold; text-align: center;">
                    {participation_title_upper}
                </td></tr>
                </table>
            </td></tr>
        </table>
    </td></tr>
    </table>

    <table width="100%">
    <tr><td style="padding: 28pt 50pt 20pt;">

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr><td align="center" style="text-align: center; padding-bottom: 18pt;">
            <table align="center" cellspacing="0" cellpadding="0" style="border: 1px solid #68d391;">
            <tr><td align="center" style="padding: 4pt 14pt; font-size: 8pt; color: #276749; font-weight: bold; background-color: #f0fff4; text-align: center;">
                &#10003; &nbsp; Verified &amp; Authentic
            </td></tr>
            </table>
        </td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 8pt; letter-spacing: 3pt; color: #a0aec0; padding-bottom: 6pt;">
                THIS CERTIFICATE IS AWARDED TO
            </td></tr>
            <tr><td align="center" style="text-align: center; font-size: 32pt; font-weight: bold; color: #1a202c; padding: 4pt 0 2pt;">
                {participant_name}
            </td></tr>
        </table>

        <table width="60%" align="center" cellspacing="0" cellpadding="0"><tr>
            <td style="border-top: 2px solid #d4af37; font-size: 1pt;">&nbsp;</td>
        </tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align: center; font-size: 1pt; padding-top: 10pt;">&nbsp;</td></tr>
            <tr><td align="center" style="text-align: center; font-size: 15pt; font-weight: bold; color: #553c9a; padding-bottom: 20pt;">
                {course_name}
            </td></tr>
        </table>

        {meta_block}

        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>

        {signatures_block}

        <table width="100%"><tr><td style="font-size: 8pt;">&nbsp;</td></tr></table>

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

    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-top: 1px solid #edf2f7;">
    <tr><td align="center" style="padding: 10pt 40pt; text-align: center; font-size: 7pt; color: #a0aec0;">
        Issued by {issued_by} &nbsp;&middot;&nbsp; {website}
    </td></tr>
    </table>

</td></tr>
</table>

</td></tr>
</table>

</body>
</html>
"""


CERTIFICATE_INTERNSHIP_VTU_HTML = """
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
            color: #1a202c;
            margin: 0;
            padding: 0;
        }}
        table {{ border-collapse: collapse; }}
        td {{ padding: 0; }}
    </style>
</head>
<body>

<table width="100%" height="100%" style="background-color: #0a0a18;">
<tr><td style="padding: 20pt 28pt;">

<table width="100%" style="background-color: #ffffff; border: 1.5pt solid #c9a227;">
<tr><td>

    <!-- Forge letterhead -->
    <table width="100%" style="background-color: #15155e;">
    <tr>
        <td style="padding: 0; width: 6pt; background-color: #d4af37;">&nbsp;</td>
        <td style="padding: 22pt 36pt 18pt;">
            <table width="100%" cellspacing="0" cellpadding="0">
                <tr>
                    <td style="vertical-align: middle;">
                        <table cellspacing="0" cellpadding="0">
                            <tr><td style="font-size: 7pt; letter-spacing: 2.5pt; color: #e8d48b; font-weight: bold;">INTELLIFORGE DIGITAL SERVICES</td></tr>
                            <tr><td style="font-size: 22pt; font-weight: bold; color: #ffffff; padding-top: 2pt; letter-spacing: 1pt;">
                                IntelliForge <span style="color: #d4af37;">Forge</span>
                            </td></tr>
                            <tr><td style="font-size: 7pt; color: #c6d2e3; padding-top: 3pt; letter-spacing: 1.2pt; font-weight: bold;">
                                ISSUED UNDER THE VTU INTERNSHIP FRAMEWORK
                            </td></tr>
                            <tr><td style="font-size: 7pt; color: #a0aec0; padding-top: 4pt; letter-spacing: 1.5pt;">
                                Verifiable credentials &middot; learning.intelliforge.tech &middot; Hyderabad, Telangana, India
                            </td></tr>
                        </table>
                    </td>
                    <td align="right" style="vertical-align: middle;">
                        <table align="right" cellspacing="0" cellpadding="0" style="border: 1.5pt solid #d4af37;">
                        <tr><td style="padding: 5pt 16pt; font-size: 7pt; letter-spacing: 2pt; color: #d4af37; font-weight: bold; text-align: center;">
                            INTERNSHIP<br/>COMPLETION
                        </td></tr>
                        </table>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
    </table>

    <table width="100%">
    <tr><td style="padding: 20pt 44pt 14pt;">

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr><td align="center" style="padding-bottom: 12pt;">
            <table align="center" cellspacing="0" cellpadding="0" style="border: 1px solid #68d391;">
            <tr><td align="center" style="padding: 3pt 12pt; font-size: 7pt; color: #276749; font-weight: bold; background-color: #f0fff4;">
                &#10003; VERIFIED DIGITAL RECORD &mdash; SCAN QR TO VALIDATE
            </td></tr>
            </table>
        </td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="font-size: 8pt; letter-spacing: 3pt; color: #718096; padding-bottom: 4pt;">CERTIFICATE OF INTERNSHIP COMPLETION</td></tr>
            <tr><td align="center" style="font-size: 7pt; color: #a0aec0; padding-bottom: 6pt; letter-spacing: 1pt;">Intelliforge Digital Services &middot; VTU-aligned industry internship</td></tr>
            <tr><td align="center" style="font-size: 26pt; font-weight: bold; color: #1a202c; padding-bottom: 2pt;">{participant_name}</td></tr>
            <tr><td align="center" style="font-size: 11pt; color: #4a5568; padding-bottom: 10pt;">
                University Seat Number (USN): <strong style="color: #2c5282;">{usn}</strong>
            </td></tr>
        </table>

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 12pt;">
            <tr><td style="font-size: 9.5pt; color: #2d3748; line-height: 1.55; text-align: justify;">
                This is to certify that <strong>{participant_name}</strong> (USN <strong>{usn}</strong>), {institution_clause}
                has successfully completed the industry internship programme
                <strong>{course_name}</strong> at <strong>Intelliforge Digital Services</strong>, during the period
                <strong>{duration_text}</strong>, logging <strong>{hours_text}</strong> of structured internship activity,
                in accordance with the Visvesvaraya Technological University (VTU) internship framework and the
                company&rsquo;s internship offer on file. This credential may be presented with the internship offer letter
                and institutional MoU pack for college / VTU records.
            </td></tr>
        </table>

        <table width="92%" align="center" cellspacing="0" cellpadding="0" style="border: 1px solid #e2e8f0; margin-bottom: 14pt;">
            <tr style="background-color: #f7fafc;">
                <td width="22%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0;">COMPLETION DATE</td>
                <td width="26%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0; border-left: 1px solid #e2e8f0;">DURATION</td>
                <td width="18%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0; border-left: 1px solid #e2e8f0;">HOURS</td>
                <td width="34%" style="padding: 8pt 6pt; font-size: 6.5pt; letter-spacing: 1.5pt; color: #718096; text-align: center; border-bottom: 1px solid #e2e8f0; border-left: 1px solid #e2e8f0;">CERTIFICATE ID</td>
            </tr>
            <tr>
                <td style="padding: 9pt 6pt; font-size: 10pt; font-weight: bold; color: #1a202c; text-align: center;">{completion_date}</td>
                <td style="padding: 9pt 6pt; font-size: 10pt; font-weight: bold; color: #1a202c; text-align: center; border-left: 1px solid #e2e8f0;">{duration_text}</td>
                <td style="padding: 9pt 6pt; font-size: 10pt; font-weight: bold; color: #1a202c; text-align: center; border-left: 1px solid #e2e8f0;">{hours_text}</td>
                <td style="padding: 9pt 6pt; font-size: 9pt; font-weight: bold; color: #1a202c; text-align: center; border-left: 1px solid #e2e8f0;">{certificate_id}</td>
            </tr>
        </table>

        {signatures_block}

        <table width="100%" cellspacing="0" cellpadding="0" style="margin-top: 12pt;">
        <tr><td align="center">
            <table align="center" cellspacing="0" cellpadding="0">
            <tr>
                <td style="padding-right: 10pt; vertical-align: middle;"><img src="{qr_data_uri}" width="64" height="64" /></td>
                <td style="vertical-align: middle; text-align: left;">
                    <span style="font-size: 8pt; font-weight: bold; color: #2d3748;">Verify this certificate</span><br/>
                    <span style="font-size: 6.5pt; color: #718096;">Permanent verification URL encoded in QR &mdash; tamper-evident HMAC token.</span>
                </td>
            </tr>
            </table>
        </td></tr>
        </table>

    </td></tr>
    </table>

    <table width="100%" style="background-color: #f8fafc; border-top: 1px solid #e2e8f0;">
    <tr><td align="center" style="padding: 8pt 32pt; font-size: 6.5pt; color: #718096;">
        Intelliforge Digital Services &middot; Forge credentialing &middot; learning.intelliforge.tech
    </td></tr>
    </table>

</td></tr>
</table>

</td></tr>
</table>

</body>
</html>
"""


VIEWER_INTERNSHIP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{participant_name} – Internship Certificate</title>
    <meta name="description" content="{meta_description}" />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="{page_url}" />
    <meta property="og:title" content="{participant_name} – Internship completion (VTU-ready)" />
    <meta property="og:description" content="{meta_description}" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="{page_url}" />
    <meta property="og:site_name" content="{internship_org}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{participant_name} – {internship_brand_prefix} {internship_brand_accent} Internship" />
    <meta name="twitter:description" content="{meta_description}" />
    {json_ld}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600;700&family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
    <style>
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a18;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem}}
        .bg-glow{{position:fixed;inset:0;background:radial-gradient(ellipse at 25% 15%,rgba(201,162,39,.12) 0%,transparent 45%),radial-gradient(ellipse at 75% 85%,rgba(102,126,234,.12) 0%,transparent 50%);pointer-events:none}}
        .card{{position:relative;background:#fff;border-radius:24px;box-shadow:0 30px 100px rgba(0,0,0,.45);max-width:600px;width:100%;overflow:hidden;animation:up .6s ease-out;border:1px solid rgba(201,162,39,.35)}}
        @keyframes up{{from{{opacity:0;transform:translateY(40px)}}to{{opacity:1;transform:translateY(0)}}}}
        .forge-bar{{position:absolute;left:0;top:0;bottom:0;width:5px;background:#d4af37}}
        .card-header{{background:#15155e;padding:2rem 2.5rem 1.8rem 2.8rem;text-align:left;position:relative}}
        .hdr-org{{font-size:.55rem;letter-spacing:3px;text-transform:uppercase;color:#e8d48b;margin-bottom:.25rem;font-weight:600}}
        .hdr-brand{{font-family:'Playfair Display',serif;font-size:1.45rem;color:#fff;font-weight:700}}
        .hdr-brand span{{color:#d4af37}}
        .hdr-sub{{font-size:.65rem;color:#a0aec0;margin-top:.4rem;letter-spacing:.5px}}
        .hdr-badge{{float:right;display:inline-block;border:1px solid #d4af37;color:#d4af37;font-size:.55rem;font-weight:600;letter-spacing:2px;text-transform:uppercase;padding:.35rem .75rem;margin-top:.2rem}}
        .card-body{{padding:2.2rem 2.5rem 2rem;text-align:center}}
        .verified{{display:inline-flex;align-items:center;gap:.4rem;background:#f0fff4;border:1px solid #68d391;color:#22543d;font-size:.68rem;font-weight:600;padding:.3rem .85rem;border-radius:20px;margin-bottom:1.4rem}}
        .verified svg{{width:14px;height:14px}}
        .label{{font-size:.65rem;letter-spacing:2.5px;text-transform:uppercase;color:#a0aec0;margin-bottom:.35rem}}
        .name{{font-family:'Playfair Display',serif;font-size:1.95rem;font-weight:700;color:#1a202c;line-height:1.15}}
        .usn{{font-size:.82rem;color:#4a5568;margin-top:.35rem;margin-bottom:.15rem}}
        .inst{{font-size:.72rem;color:#718096;margin-bottom:1rem}}
        .divider{{height:1px;background:linear-gradient(to right,transparent,#d4af37,transparent);margin:.7rem 2rem .9rem}}
        .course{{font-size:.9rem;color:#553c9a;font-weight:600;margin-bottom:1.4rem;line-height:1.35}}
        .meta{{display:flex;justify-content:center;gap:1.2rem;margin-bottom:1.6rem;flex-wrap:wrap}}
        .meta-item{{text-align:center;min-width:72px}}
        .meta-val{{font-size:.78rem;color:#2d3748;font-weight:500}}
        .meta-lbl{{font-size:.55rem;color:#a0aec0;text-transform:uppercase;letter-spacing:.8px;margin-top:.12rem}}
        .actions{{display:flex;flex-direction:column;gap:.65rem;align-items:center}}
        .btn-download{{display:inline-flex;align-items:center;gap:.55rem;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;padding:.8rem 2rem;border-radius:12px;font-size:.9rem;font-weight:600;cursor:pointer;text-decoration:none;box-shadow:0 4px 20px rgba(102,126,234,.35)}}
        .btn-download svg{{width:17px;height:17px}}
        .share-row{{display:flex;gap:.45rem;flex-wrap:wrap;justify-content:center}}
        .btn-share{{display:inline-flex;align-items:center;gap:.4rem;padding:.5rem 1rem;border-radius:8px;font-size:.74rem;font-weight:600;text-decoration:none;border:1.5px solid #e2e8f0;color:#4a5568;background:#fff}}
        .btn-linkedin{{border-color:#0077b5;color:#0077b5}}
        .btn-twitter{{border-color:#1da1f2;color:#1da1f2}}
        .btn-share svg{{width:14px;height:14px}}
        .signatures{{display:flex;justify-content:center;gap:1.5rem;margin-bottom:1.5rem;flex-wrap:wrap}}
        .sig-block{{text-align:center;min-width:120px;max-width:160px}}
        .sig-hand{{font-family:'Dancing Script',cursive;font-size:1.35rem;color:#1a202c;margin-bottom:.15rem;opacity:.88}}
        .sig-line{{height:1px;background:#c4b5fd;margin:.2rem 0}}
        .sig-name{{font-size:.7rem;color:#553c9a;font-weight:600;margin-top:.25rem}}
        .sig-role{{font-size:.55rem;color:#a0aec0;letter-spacing:.5px;text-transform:uppercase;margin-top:.08rem}}
        .qr-section{{display:flex;align-items:center;justify-content:center;gap:.75rem;margin-top:1.1rem;padding-top:1.1rem;border-top:1px solid #f0f0f0}}
        .qr-section img{{border-radius:6px;border:1px solid #e2e8f0}}
        .qr-text{{font-size:.62rem;color:#a0aec0;text-align:left;line-height:1.45}}
        .qr-text strong{{color:#4a5568;display:block;font-size:.68rem}}
        .card-footer{{background:#f8fafc;border-top:1px solid #edf2f7;padding:1rem 2.5rem;text-align:center}}
        .card-footer p{{font-size:.68rem;color:#a0aec0;line-height:1.55}}
        .card-footer a{{color:#667eea;text-decoration:none}}
        @media(max-width:520px){{body{{padding:1rem}}.card-body{{padding:1.4rem}}.name{{font-size:1.45rem}}.meta{{gap:.8rem}}}}
    </style>
</head>
<body>
    <div class="bg-glow"></div>
    <div class="card">
        <div class="forge-bar"></div>
        <div class="card-header">
            <div class="hdr-badge">Internship</div>
            <div class="hdr-org">{internship_org}</div>
            <div class="hdr-brand">{internship_brand_prefix} <span>{internship_brand_accent}</span></div>
            <div class="hdr-sub">VTU internship framework &middot; Verifiable credentials &middot; {website}</div>
        </div>
        <div class="card-body">
            <div class="verified">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified &amp; Authentic
            </div>
            <div class="label">Certificate of internship completion</div>
            <div class="name">{participant_name}</div>
            <div class="usn">USN <strong>{usn}</strong></div>
            {institution_block}
            <div class="divider"></div>
            <div class="course">{course_name}</div>
            <div class="meta">
                <div class="meta-item"><div class="meta-val">{completion_date}</div><div class="meta-lbl">Completion</div></div>
                <div class="meta-item"><div class="meta-val">{duration_text}</div><div class="meta-lbl">Duration</div></div>
                <div class="meta-item"><div class="meta-val">{hours_text}</div><div class="meta-lbl">Hours</div></div>
                <div class="meta-item"><div class="meta-val">{cert_id}</div><div class="meta-lbl">Certificate ID</div></div>
            </div>
            {signatures_html}
            <div class="actions">
                <a class="btn-download" href="{download_url}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Download certificate (PDF)
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
                <div class="qr-text"><strong>Scan to verify</strong>QR links to the permanent verification page for this credential (offer letter → MoU → certificate lifecycle).</div>
            </div>
        </div>
        <div class="card-footer">
            <p>
                Issued by <a href="https://learning.intelliforge.tech/" target="_blank" rel="noopener">{issued_by}</a>
                &nbsp;&middot;&nbsp; {website}
            </p>
        </div>
    </div>
</body>
</html>"""


CERT_EMAIL_INTERNSHIP_HTML = """
<div style="font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;background:#0a0a18;padding:22px;border-radius:16px;">
  <div style="border-left:4px solid #d4af37;background:#15155e;padding:24px 28px 20px;text-align:left;border-radius:12px 12px 0 0;">
    <div style="font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e8d48b;font-weight:600;">Intelliforge Digital Services</div>
    <div style="font-size:22px;font-weight:700;color:#fff;margin:6px 0 4px;">IntelliForge <span style="color:#d4af37;">Forge</span></div>
    <div style="display:inline-block;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#d4af37;font-weight:600;border:1px solid rgba(212,175,55,0.55);padding:5px 14px;border-radius:20px;margin-top:6px;">Internship completion</div>
  </div>
  <div style="background:#ffffff;padding:28px;text-align:center;">
    <div style="display:inline-block;background:#f0fff4;border:1px solid #68d391;color:#276749;font-size:11px;font-weight:600;padding:5px 12px;border-radius:20px;margin-bottom:16px;">&#10003; Verified &amp; authentic</div>
    <p style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#a0aec0;margin:0 0 6px;">Certificate issued to</p>
    <h1 style="font-size:24px;font-weight:700;color:#1a202c;margin:0 0 4px;">{participant_name}</h1>
    <p style="font-size:13px;color:#4a5568;margin:0 0 16px;">USN <strong>{usn}</strong></p>
    <div style="height:2px;background:linear-gradient(to right,transparent,#d4af37,transparent);margin:0 auto 14px;width:55%;"></div>
    <p style="font-size:15px;font-weight:600;color:#553c9a;margin:0 0 18px;">{course_name}</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #edf2f7;border-bottom:1px solid #edf2f7;margin-bottom:20px;font-size:13px;">
      <tr>
        <td style="text-align:center;padding:12px 6px;width:25%;">
          <div style="font-weight:600;color:#2d3748;">{completion_date}</div>
          <div style="font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Completion</div>
        </td>
        <td style="text-align:center;padding:12px 6px;width:25%;border-left:1px solid #edf2f7;">
          <div style="font-weight:600;color:#2d3748;">{duration_text}</div>
          <div style="font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Duration</div>
        </td>
        <td style="text-align:center;padding:12px 6px;width:25%;border-left:1px solid #edf2f7;">
          <div style="font-weight:600;color:#2d3748;">{hours_text}</div>
          <div style="font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Hours</div>
        </td>
        <td style="text-align:center;padding:12px 6px;width:25%;border-left:1px solid #edf2f7;">
          <div style="font-weight:600;color:#2d3748;font-family:monospace;font-size:12px;">{certificate_id}</div>
          <div style="font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#a0aec0;margin-top:4px;">Certificate ID</div>
        </td>
      </tr>
    </table>
    <p style="font-size:12px;color:#718096;margin:0 0 18px;text-align:left;line-height:1.5;">Industry mentor: <strong>{mentor_name}</strong><br/>Program lead: <strong>{instructor_name}</strong></p>
    <a href="{view_url}" style="display:inline-block;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:12px 32px;border-radius:12px;font-size:15px;font-weight:600;text-decoration:none;margin-bottom:10px;">View certificate</a>
    <p style="font-size:12px;color:#a0aec0;margin:10px 0 0;">Download PDF: <a href="{download_url}" style="color:#667eea;text-decoration:none;font-weight:500;">{download_url}</a></p>
  </div>
  <div style="background:#f8fafc;padding:14px 28px;text-align:center;border-radius:0 0 12px 12px;border-top:1px solid #edf2f7;">
    <p style="font-size:11px;color:#a0aec0;margin:0;">Intelliforge Digital Services &middot; <a href="mailto:support@intelliforge.tech" style="color:#667eea;text-decoration:none;">support@intelliforge.tech</a></p>
  </div>
</div>
"""

# Landscape appreciation certificate (sports / event participation)
CERTIFICATE_APPRECIATION_HTML = """
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
            color: #1a202c;
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

<table width="100%" height="100%" style="background-color: #ffffff;">
<tr>
    <td width="5%" style="vertical-align: middle; padding: 18pt 0 18pt 14pt;">
        {sports_icons}
    </td>
    <td width="70%" style="vertical-align: top; padding: 22pt 24pt 18pt 8pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td align="right" style="text-align: right; padding-bottom: 28pt;">
                    {logo_block}
                </td>
            </tr>
            <tr>
                <td style="padding-left: 8pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td style="font-size: 9pt; color: #2d3748; padding-bottom: 10pt;">
                            {presented_label}
                        </td></tr>
                        <tr><td style="font-size: 28pt; font-weight: bold; color: {accent_color}; padding: 2pt 0 6pt; border-bottom: 1px solid #cbd5e0;">
                            {participant_name}
                        </td></tr>
                        <tr><td style="font-size: 11pt; color: #2d3748; line-height: 1.55; padding-top: 18pt; max-width: 420pt;">
                            {recognition_text}
                        </td></tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="padding-top: 36pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                            <td width="40%" valign="bottom" style="vertical-align: bottom; padding-left: 8pt;">
                                <table cellspacing="0" cellpadding="0">
                                    <tr><td style="font-size: 12pt; color: {accent_color}; font-weight: bold; border-bottom: 1px solid #a0aec0; min-width: 100pt; padding-bottom: 2pt;">
                                        {completion_date}
                                    </td></tr>
                                    <tr><td style="font-size: 8pt; color: #718096; padding-top: 4pt;">Date</td></tr>
                                </table>
                            </td>
                            <td width="60%" align="right" valign="bottom" style="text-align: right; vertical-align: bottom; padding-right: 12pt;">
                                {event_footer}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td align="center" style="text-align: center; padding-top: 14pt;">
                    <table align="center" cellspacing="0" cellpadding="0">
                        <tr>
                            <td align="center" style="text-align: center;">
                                <img src="{qr_data_uri}" width="56" height="56" alt="QR" />
                            </td>
                            <td style="padding-left: 8pt; font-size: 7pt; color: #a0aec0; vertical-align: middle;">
                                Scan to verify<br/>
                                <span style="font-family: monospace; color: #718096;">{certificate_id}</span>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td>
    <td width="25%" style="background-color: {accent_color}; vertical-align: middle;">
        {sidebar_block}
    </td>
</tr>
</table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="border-top: 1px solid #e2e8f0; font-size: 1pt;">&nbsp;</td>
</tr>
<tr>
    <td style="border-top: 1px solid #e2e8f0; font-size: 1pt;">&nbsp;</td>
</tr>
<tr>
    <td style="border-top: 1px solid #e2e8f0; font-size: 1pt;">&nbsp;</td>
</tr>
</table>

</body>
</html>
"""

VIEWER_APPRECIATION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{participant_name} — Certificate of Appreciation</title>
    <meta name="description" content="{meta_description}" />
    <meta property="og:title" content="{participant_name} — Certificate of Appreciation" />
    <meta property="og:description" content="{meta_description}" />
    <meta property="og:url" content="{page_url}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{participant_name} — Certificate of Appreciation" />
    <meta name="twitter:description" content="{meta_description}" />
    {json_ld}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#f0f4f8;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem}}
        .card{{position:relative;background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.12);max-width:640px;width:100%;overflow:hidden;animation:up .5s ease-out}}
        @keyframes up{{from{{opacity:0;transform:translateY(30px)}}to{{opacity:1;transform:translateY(0)}}}}
        .layout{{display:flex;min-height:320px}}
        .main{{flex:1;padding:1.8rem 1.6rem 1.4rem 1.4rem;position:relative}}
        .sidebar{{width:72px;background:{accent_color};display:flex;align-items:center;justify-content:center;padding:.75rem .35rem}}
        .sidebar-text{{color:#fff;font-weight:700;font-size:.42rem;letter-spacing:.15em;text-transform:uppercase;writing-mode:vertical-rl;transform:rotate(180deg);line-height:1.6}}
        .logo-row{{display:flex;justify-content:flex-end;align-items:center;gap:.35rem;margin-bottom:1.2rem}}
        .logo-mark{{width:28px;height:28px;border-radius:50%;background:{accent_color};color:#fff;font-weight:700;font-size:.85rem;display:flex;align-items:center;justify-content:center}}
        .logo-text{{text-align:right;line-height:1.1}}
        .logo-bold{{font-weight:800;font-size:.72rem;color:{accent_color};letter-spacing:.5px}}
        .logo-light{{font-weight:500;font-size:.68rem;color:{accent_color}}}
        .verified{{display:inline-flex;align-items:center;gap:.35rem;background:#ebf8ff;border:1px solid #90cdf4;color:#2c5282;font-size:.62rem;font-weight:600;padding:.25rem .7rem;border-radius:20px;margin-bottom:.9rem}}
        .verified svg{{width:12px;height:12px}}
        .label{{font-size:.62rem;color:#4a5568;margin-bottom:.5rem}}
        .name{{font-size:1.65rem;font-weight:700;color:{accent_color};border-bottom:1px solid #cbd5e0;padding-bottom:.35rem;margin-bottom:.9rem;line-height:1.2}}
        .recognition{{font-size:.82rem;color:#2d3748;line-height:1.55;margin-bottom:1.2rem}}
        .footer-row{{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;margin-bottom:1rem;flex-wrap:wrap}}
        .date-val{{font-size:.9rem;font-weight:600;color:{accent_color};border-bottom:1px solid #a0aec0;padding-bottom:.15rem}}
        .date-lbl{{font-size:.55rem;color:#718096;margin-top:.2rem}}
        .event-block{{text-align:right}}
        .event-name{{font-size:.78rem;font-weight:700;color:#1a202c;letter-spacing:.5px}}
        .sponsor{{font-size:.58rem;color:#718096;margin-top:.15rem;letter-spacing:.3px}}
        .actions{{display:flex;flex-direction:column;gap:.55rem;align-items:center;padding-top:.5rem;border-top:1px solid #edf2f7}}
        .btn-download{{display:inline-flex;align-items:center;gap:.5rem;background:{accent_color};color:#fff;border:none;padding:.7rem 1.6rem;border-radius:10px;font-size:.85rem;font-weight:600;cursor:pointer;text-decoration:none}}
        .share-row{{display:flex;gap:.4rem;flex-wrap:wrap;justify-content:center}}
        .btn-share{{display:inline-flex;align-items:center;gap:.35rem;padding:.45rem .85rem;border-radius:8px;font-size:.7rem;font-weight:600;text-decoration:none;border:1.5px solid #e2e8f0;color:#4a5568;background:#fff}}
        .btn-linkedin{{border-color:#0077b5;color:#0077b5}}
        .btn-twitter{{border-color:#1da1f2;color:#1da1f2}}
        .qr-section{{display:flex;align-items:center;justify-content:center;gap:.65rem;margin-top:.9rem;padding-top:.9rem;border-top:1px solid #f0f0f0}}
        .qr-section img{{border-radius:6px;border:1px solid #e2e8f0}}
        .qr-text{{font-size:.58rem;color:#a0aec0;text-align:left;line-height:1.4}}
        .qr-text strong{{color:#4a5568;display:block;font-size:.64rem}}
        .card-footer{{background:#f8fafc;border-top:1px solid #edf2f7;padding:.85rem 1.5rem;text-align:center}}
        .card-footer p{{font-size:.62rem;color:#a0aec0}}
        .card-footer a{{color:{accent_color};text-decoration:none}}
        .sports-col{{position:absolute;left:.5rem;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:.35rem;opacity:.35}}
        .sport-dot{{width:8px;height:8px;border-radius:50%;background:{accent_color}}}
        @media(max-width:520px){{body{{padding:1rem}}.sidebar{{width:48px}}.main{{padding:1.2rem 1rem 1rem 1.2rem}}.name{{font-size:1.25rem}}}}
    </style>
</head>
<body>
    <div class="card">
        <div class="layout">
            <div class="main">
                <div class="sports-col" aria-hidden="true">
                    <div class="sport-dot"></div><div class="sport-dot"></div><div class="sport-dot"></div><div class="sport-dot"></div>
                </div>
                <div class="logo-row">
                    <div class="logo-text">
                        <div class="logo-bold">{appreciation_org_bold}</div>
                        <div class="logo-light">{appreciation_org_light}</div>
                    </div>
                    <div class="logo-mark">D</div>
                </div>
                <div class="verified">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                    Verified &amp; Authentic
                </div>
                <div class="label">{presented_label}</div>
                <div class="name">{participant_name}</div>
                <div class="recognition">{recognition_text}</div>
                <div class="footer-row">
                    <div>
                        <div class="date-val">{completion_date}</div>
                        <div class="date-lbl">Date</div>
                    </div>
                    {event_block}
                </div>
                <div class="qr-section">
                    <img src="{qr_data_uri}" width="72" height="72" alt="Verification QR code" />
                    <div class="qr-text">
                        <strong>Scan to verify</strong>
                        Certificate ID: {cert_id}
                    </div>
                </div>
                <div class="actions">
                    <a class="btn-download" href="{download_url}">Download PDF</a>
                    <div class="share-row">
                        <a class="btn-share btn-linkedin" href="{linkedin_url}" target="_blank" rel="noopener">LinkedIn</a>
                        <a class="btn-share btn-twitter" href="{twitter_url}" target="_blank" rel="noopener">Share</a>
                    </div>
                </div>
            </div>
            <div class="sidebar" aria-hidden="true">
                <div class="sidebar-text">{title_line1} {title_line2}</div>
            </div>
        </div>
        <div class="card-footer">
            <p>Issued by {issued_by} &middot; <a href="{page_url}">{website}</a></p>
        </div>
    </div>
</body>
</html>
"""

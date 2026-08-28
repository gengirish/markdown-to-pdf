"""The public CertForge credential viewer — the page a QR code lands on.

Ported from the legacy viewers (`VIEWER_HTML` in `api/index.py`,
`VIEWER_INTERNSHIP_HTML` / `VIEWER_APPRECIATION_HTML` in
`api/certificate_templates.py`), which carry Open Graph and Twitter card tags,
a meta description, schema.org JSON-LD, share actions, a download button and
the verification QR. The CertForge card had none of it, so a credential shared
to LinkedIn or WhatsApp unfurled as a bare URL.

The one thing that does NOT come across from the legacy design is its single
tenant. Legacy renders one brand read from `CERT_*` env vars; CertForge renders
whichever organization issued the credential, so every brand string and colour
below is a parameter. The env constants are a last-resort fallback for the case
where there is no org at all, and the caller passes them in.

Everything interpolated here is attacker-controlled: recipient names and
credential titles come out of customer-uploaded CSVs. Three separate rules
apply, and escaping alone satisfies none of them on its own:

* text and attribute values go through `html.escape`;
* URLs are additionally scheme-checked (`safe_public_url`), because `html.escape`
  passes `javascript:alert(1)` straight through into an `href`;
* colours are matched against a strict pattern (`_safe_color`), because they
  land inside a `<style>` block where escaping does nothing — `#fff;}
  body{background:url(...)` is not neutralised by entity encoding.

The JSON-LD payload additionally escapes `<`, `>` and `&` as `\\uXXXX`, since
inside a `<script>` element a recipient named `</script><script>…` would
otherwise close the block. `_json_ld_script` in `index.py` does not do this;
do not copy it back.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote

# Fallbacks for an org that has not set its branding. Same values as
# `build_render_variables` in api/services/rendering.py so the viewer and the
# rendered PDF are the same certificate.
DEFAULT_PRIMARY_COLOR = "#1e293b"
DEFAULT_ACCENT_COLOR = "#d4af37"
DEFAULT_FOOTER_TEXT = "Powered by CertForge · certforge.intelliforge.tech"

# Hex (#abc, #aabbcc, #aabbccdd), rgb()/rgba(), or a bare CSS colour keyword.
# Anything else is dropped rather than sanitised: a colour that does not match
# is not a colour.
_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|rgba?\([\d\s.,%]+\)|[a-zA-Z]{3,20})$"
)


def _safe_color(value: str | None, fallback: str) -> str:
    """Return `value` only if it is unmistakably a CSS colour."""
    if value and _COLOR_RE.match(str(value).strip()):
        return str(value).strip()
    return fallback


def safe_public_url(value: str | None) -> str:
    """Return `value` only if it is an http(s) or site-absolute URL.

    The scheme check is what escaping cannot do — see the module docstring.
    """
    if not value:
        return ""
    v = str(value).strip()
    if v.startswith(("https://", "http://", "/")):
        return v
    return ""


def _json_ld_script(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    raw = (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f'<script type="application/ld+json">{raw}</script>'


def credential_json_ld(
    *,
    recipient_name: str,
    title: str,
    issued_at: str,
    credential_id: str,
    page_url: str,
    issuer_name: str,
    issuer_url: str = "",
) -> str:
    """schema.org JSON-LD for one credential.

    Modelled on `_participation_json_ld` in `api/index.py`: same
    `EducationalOccupationalCredential` type, same identifier/url/recognizedBy/
    awardedTo shape, so a consumer that already reads legacy certificates reads
    these too.
    """
    issuer: dict[str, str] = {"@type": "Organization", "name": issuer_name}
    if issuer_url:
        issuer["url"] = issuer_url
    return _json_ld_script(
        {
            "@context": "https://schema.org",
            "@type": "EducationalOccupationalCredential",
            "name": title,
            "credentialCategory": "certificate",
            "identifier": credential_id,
            "url": page_url,
            "dateCreated": issued_at,
            "recognizedBy": issuer,
            "awardedTo": {"@type": "Person", "name": recipient_name},
        }
    )


# CSS is passed to `.format()` as a *value*, not formatted itself, so its
# braces stay single. Org colours arrive through custom properties in
# `{color_vars}` rather than being spliced through the rules one by one.
VIEWER_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f23;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2rem}
.bg-glow{position:fixed;inset:0;background:radial-gradient(ellipse at 30% 20%,rgba(102,126,234,.18) 0%,transparent 50%),radial-gradient(ellipse at 70% 80%,rgba(118,75,162,.15) 0%,transparent 50%);pointer-events:none}
.card{position:relative;background:#fff;border-radius:24px;box-shadow:0 30px 100px rgba(0,0,0,.35);max-width:560px;width:100%;overflow:hidden;animation:up .6s ease-out}
@keyframes up{from{opacity:0;transform:translateY(40px)}to{opacity:1;transform:translateY(0)}}

.card-header{background:var(--cf-primary);padding:2.2rem 2.5rem 2rem;text-align:center;position:relative;overflow:hidden}
.card-header::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle,rgba(255,255,255,.06) 0%,transparent 60%);pointer-events:none}
.hdr-logo{max-height:48px;max-width:190px;margin-bottom:.8rem}
.hdr-org{font-size:.6rem;letter-spacing:4px;text-transform:uppercase;color:var(--cf-accent);margin-bottom:.35rem;font-weight:500}
.hdr-brand{font-family:'Playfair Display',Georgia,serif;font-size:1.5rem;color:#fff;font-weight:700;margin-bottom:.8rem}
.hdr-badge{display:inline-block;background:rgba(255,255,255,.08);border:1px solid var(--cf-accent);color:var(--cf-accent);font-size:.6rem;font-weight:600;letter-spacing:2.5px;text-transform:uppercase;padding:.35rem 1.2rem;border-radius:20px}

.card-body{padding:2.5rem 2.5rem 2rem;text-align:center}
.verified{display:inline-flex;align-items:center;gap:.4rem;background:#f0fff4;border:1px solid #68d391;color:#22543d;font-size:.7rem;font-weight:600;padding:.3rem .9rem;border-radius:20px;margin-bottom:1.6rem}
.verified svg{width:14px;height:14px}
.label{font-size:.7rem;letter-spacing:2.5px;text-transform:uppercase;color:#a0aec0;margin-bottom:.4rem}
.name{font-family:'Playfair Display',Georgia,serif;font-size:2.1rem;font-weight:700;color:#1a202c;line-height:1.15;margin-bottom:.15rem}
.divider{height:1px;background:linear-gradient(to right,transparent,var(--cf-accent),transparent);margin:.8rem 2rem 1rem}
.course{font-size:.95rem;color:#553c9a;font-weight:600;margin-bottom:1.6rem}

.meta{display:flex;justify-content:center;gap:1.8rem;margin-bottom:2rem;flex-wrap:wrap}
.meta-item{text-align:center}
.meta-val{font-size:.82rem;color:#2d3748;font-weight:500}
.meta-lbl{font-size:.6rem;color:#a0aec0;text-transform:uppercase;letter-spacing:1px;margin-top:.15rem}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}

.actions{display:flex;flex-direction:column;gap:.7rem;align-items:center}
.btn-download{display:inline-flex;align-items:center;gap:.6rem;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;padding:.85rem 2.2rem;border-radius:12px;font-size:.95rem;font-weight:600;cursor:pointer;text-decoration:none;transition:all .3s;box-shadow:0 4px 20px rgba(102,126,234,.35)}
.btn-download:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(102,126,234,.5)}
.btn-download svg{width:18px;height:18px}
.share-row{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:center}
.btn-share{display:inline-flex;align-items:center;gap:.45rem;padding:.55rem 1.1rem;border-radius:8px;font-size:.78rem;font-weight:600;text-decoration:none;transition:all .2s;border:1.5px solid #e2e8f0;color:#4a5568;background:#fff}
.btn-share:hover{border-color:#a0aec0;background:#f7fafc}
.btn-linkedin{border-color:#0077b5;color:#0077b5}
.btn-linkedin:hover{background:#f0f7ff;border-color:#005e93}
.btn-twitter{border-color:#1da1f2;color:#1da1f2}
.btn-twitter:hover{background:#f0f9ff;border-color:#0c85d0}
.btn-share svg{width:15px;height:15px}

.qr-section{display:flex;align-items:center;justify-content:center;gap:.8rem;margin-top:1.4rem;padding-top:1.2rem;border-top:1px solid #f0f0f0}
.qr-section img{border-radius:6px;border:1px solid #e2e8f0}
.qr-text{font-size:.65rem;color:#a0aec0;text-align:left;line-height:1.5}
.qr-text strong{color:#4a5568;display:block;font-size:.7rem}

.card-footer{background:#f8fafc;border-top:1px solid #edf2f7;padding:1rem 2.5rem;text-align:center}
.card-footer p{font-size:.7rem;color:#a0aec0;line-height:1.6}
.card-footer a{color:#667eea;text-decoration:none}
.card-footer a:hover{text-decoration:underline}

@media(max-width:480px){
    body{padding:1rem}
    .card-body{padding:1.5rem}
    .name{font-size:1.5rem}
    .meta{gap:1rem}
    .share-row{flex-direction:column;align-items:stretch}
}
"""

CREDENTIAL_VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{recipient_name} – {title}</title>
    <meta name="description" content="{meta_description}" />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="{page_url}" />
    <meta property="og:title" content="{og_title}" />
    <meta property="og:description" content="{meta_description}" />
    <meta property="og:type" content="article" />
    <meta property="og:url" content="{page_url}" />
    <meta property="og:site_name" content="{issuer_name}" />
    <meta property="og:image" content="{og_image}" />
    <meta property="og:image:alt" content="{og_title}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{og_title}" />
    <meta name="twitter:description" content="{meta_description}" />
    <meta name="twitter:image" content="{og_image}" />
    {json_ld}
    <link rel="alternate" type="application/ld+json" href="{badge_url}" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
    <style>
{color_vars}
{css}
    </style>
</head>
<body>
    <div class="bg-glow"></div>
    <div class="card">
        <div class="card-header">
            {logo_html}
            <div class="hdr-org">{issuer_tagline}</div>
            <div class="hdr-brand">{issuer_name}</div>
            <div class="hdr-badge">Verified Credential</div>
        </div>
        <div class="card-body">
            <div class="verified">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified &amp; Authentic
            </div>
            <div class="label">This credential is awarded to</div>
            <div class="name">{recipient_name}</div>
            <div class="divider"></div>
            <div class="course">{title}</div>
            <div class="meta">
                <div class="meta-item">
                    <div class="meta-val">{issued_at}</div>
                    <div class="meta-lbl">Issued</div>
                </div>
                <div class="meta-item">
                    <div class="meta-val mono">{credential_id}</div>
                    <div class="meta-lbl">Credential ID</div>
                </div>
            </div>
            <div class="actions">
                {download_html}
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
                <img src="{qr_data_uri}" alt="QR code linking to this credential's verification page" width="80" height="80" />
                <div class="qr-text"><strong>Scan to Verify</strong>This QR code links to this credential's<br/>permanent verification page.</div>
            </div>
        </div>
        <div class="card-footer">
            <p>{footer_html}</p>
        </div>
    </div>
</body>
</html>"""


def render_credential_viewer(
    *,
    recipient_name: str,
    title: str,
    issued_at: str,
    credential_id: str,
    page_url: str,
    badge_url: str,
    qr_data_uri: str,
    issuer_name: str,
    issuer_url: str = "",
    issuer_tagline: str = "Verified Credential",
    pdf_url: str = "",
    og_image: str = "",
    logo_url: str | None = None,
    primary_color: str | None = None,
    accent_color: str | None = None,
    footer_text: str | None = None,
) -> str:
    """Render the public viewer page for one CertForge credential.

    Every string argument is treated as untrusted. Callers pass raw values;
    escaping happens here so there is exactly one place to check it.
    """
    safe_name = html.escape(str(recipient_name))
    safe_title = html.escape(str(title))
    safe_issued = html.escape(str(issued_at))
    safe_id = html.escape(str(credential_id))
    safe_issuer = html.escape(str(issuer_name))
    safe_tagline = html.escape(str(issuer_tagline))
    safe_page_url = html.escape(safe_public_url(page_url))
    safe_badge_url = html.escape(safe_public_url(badge_url))

    meta_description = html.escape(
        f"Verified credential: {recipient_name} was awarded "
        f"{title} by {issuer_name}. Credential ID {credential_id}."
    )
    og_title = html.escape(f"{recipient_name} – {title}")

    # The download button is omitted rather than pointed at a dead end when
    # there is no PDF URL, and the scheme is checked because html.escape would
    # let a `javascript:` href through untouched.
    download_html = ""
    safe_pdf = safe_public_url(pdf_url)
    if safe_pdf:
        download_html = (
            f'<a class="btn-download" href="{html.escape(safe_pdf)}">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
            '<polyline points="7 10 12 15 17 10"/>'
            '<line x1="12" y1="15" x2="12" y2="3"/></svg>'
            "Download PDF</a>"
        )

    logo_html = ""
    safe_logo = safe_public_url(logo_url)
    if safe_logo:
        logo_html = f'<img class="hdr-logo" src="{html.escape(safe_logo)}" alt="" />'

    color_vars = (
        ":root{"
        f"--cf-primary:{_safe_color(primary_color, DEFAULT_PRIMARY_COLOR)};"
        f"--cf-accent:{_safe_color(accent_color, DEFAULT_ACCENT_COLOR)};"
        "}"
    )

    footer = html.escape(str(footer_text or DEFAULT_FOOTER_TEXT))
    safe_issuer_url = safe_public_url(issuer_url)
    if safe_issuer_url:
        footer = (
            f'Issued by <a href="{html.escape(safe_issuer_url)}" rel="noopener">'
            f"{safe_issuer}</a> &middot; {footer}"
        )

    share_target = safe_public_url(page_url)
    linkedin_url = html.escape(
        "https://www.linkedin.com/sharing/share-offsite/?url=" + quote(share_target, safe="")
    )
    twitter_url = html.escape(
        "https://twitter.com/intent/tweet?text="
        + quote(f"I earned {title} from {issuer_name}!", safe="")
        + "&url="
        + quote(share_target, safe="")
    )

    return CREDENTIAL_VIEWER_HTML.format(
        recipient_name=safe_name,
        title=safe_title,
        issued_at=safe_issued,
        credential_id=safe_id,
        issuer_name=safe_issuer,
        issuer_tagline=safe_tagline,
        page_url=safe_page_url,
        badge_url=safe_badge_url,
        meta_description=meta_description,
        og_title=og_title,
        og_image=html.escape(safe_public_url(og_image)),
        json_ld=credential_json_ld(
            recipient_name=recipient_name,
            title=title,
            issued_at=str(issued_at),
            credential_id=str(credential_id),
            page_url=safe_public_url(page_url),
            issuer_name=issuer_name,
            issuer_url=safe_issuer_url,
        ),
        css=VIEWER_CSS,
        color_vars=color_vars,
        logo_html=logo_html,
        download_html=download_html,
        linkedin_url=linkedin_url,
        twitter_url=twitter_url,
        qr_data_uri=qr_data_uri,
        footer_html=footer,
    )

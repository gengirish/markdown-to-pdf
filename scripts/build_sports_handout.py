#!/usr/bin/env python3
"""Build the 2-page printable sports tournament handout.

Page 1 - blank Certificate of Appreciation (name + award/position written by
         hand at the tournament), using the appreciation brand system from
         api/appreciation_assets.py.
Page 2 - IntelliForge information and UpSkill bootcamp promotion, with QR codes.

Designed for duplex printing (flip on long edge) on A4 landscape.

Usage:
    python scripts/build_sports_handout.py
    python scripts/build_sports_handout.py --out ~/Desktop/handout.pdf
    python scripts/build_sports_handout.py --event "SDG Premier League 2026" \
        --date "15 August 2026"

Leave --event / --date unset to print blank rules for handwriting.

Note: the PDF font is Helvetica, which has no rupee glyph, so prices print as
"Rs." rather than a box.
"""

from __future__ import annotations

import argparse
import base64
import html as html_mod
import sys
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import qrcode  # noqa: E402
from qrcode.image.pil import PilImage  # noqa: E402
from xhtml2pdf import pisa  # noqa: E402

from api.appreciation_assets import (  # noqa: E402
    APPRECIATION_ACCENT_COLOR,
    APPRECIATION_GREEN_ACCENT,
    APPRECIATION_HEADER_BG,
    APPRECIATION_SECONDARY_COLOR,
    APPRECIATION_SIDEBAR_COLOR,
    appreciation_header_stripe_html,
    appreciation_pdf_accent_rail,
    appreciation_pdf_sidebar_stripes,
    appreciation_pdf_tricolor_footer,
    appreciation_sport_seal_html,
)

ACCENT = APPRECIATION_ACCENT_COLOR
SECONDARY = APPRECIATION_SECONDARY_COLOR
SIDEBAR = APPRECIATION_SIDEBAR_COLOR
HEADER_BG = APPRECIATION_HEADER_BG
GREEN = APPRECIATION_GREEN_ACCENT
AI_COLOR = "#7B6FFF"

# Ink scale tuned for >=4.5:1 contrast on the light page background (#f8faf9)
# and white cards, per the accessibility-first pass. The old #718096/#a0aec0
# label greys measured ~3.6:1 and ~1.9:1 respectively and failed WCAG AA for
# the small caption sizes used here.
INK = "#1a202c"       # primary text
MUTED = "#4a5568"     # section labels / secondary text  (~7:1)
CAPTION = "#5f6b7a"   # smallest sub-captions             (~5:1)

# Sobha Dream Gardens host brand. The wordmark is recreated typographically
# (SOBHA in a spaced serif, "dream" in the brand red, "gardens" in black) since
# no logo asset ships in the repo; swap in a base64 image here if one is added.
SDG_RED = "#E5322B"

URL_MAIN = "https://www.intelliforge.tech/"
URL_LEARNING = "https://learning.intelliforge.tech/"
URL_UPSKILL = "https://upskill.intelliforge.tech/"
URL_CERTS = "https://certs.intelliforge.tech/"

# A4 landscape, in points.
PAGE_W = 842
PAGE_H = 595

# Bottom padding that stretches each page's content down to the tricolor
# footer. xhtml2pdf ignores height:100% on a page-level table and silently
# spills a stray blank page the moment content exceeds the page box, so these
# are tuned by hand and sit ~5pt under a perfect fit. Re-measure by rendering
# with pdftoppm if the copy length changes; one point too many splits a page.
# The back page now nearly fills itself: its three info columns bottom-pin
# their QR CTAs, so only a few points of slack remain before the footer.
H_FRONT_FILL = 8
H_BACK_FILL = 6

RECOGNITION_TEXT = (
    "in recognition of outstanding participation, sportsmanship and team spirit "
    "demonstrated throughout the tournament."
)


def qr_data_uri(url: str, box_size: int = 4) -> str:
    """QR code as a base64 PNG data URI (xhtml2pdf cannot fetch remote images)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


FLAG_PATH = REPO_ROOT / "public" / "branding" / "india-flag.png"


def image_data_uri(path: Path) -> str:
    """Base64 PNG data URI (xhtml2pdf cannot fetch remote images)."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def esc(value: str) -> str:
    return html_mod.escape(value or "")


def blank_rule(width: str = "100%", height: str = "26pt", color: str = "#1a202c") -> str:
    """Handwriting rule - a bottom-bordered cell."""
    return (
        f'<table width="{width}" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="height:{height};border-bottom:1.5pt solid {color};'
        f'font-size:1pt;line-height:{height};">&nbsp;</td></tr></table>'
    )


def stacked_letters(word: str) -> str:
    return "<br/>".join(esc(ch) for ch in word.upper() if ch != " ")


def header_bar() -> str:
    """Sponsor header.

    Local copy rather than appreciation_header_html(). xhtml2pdf resolves
    align="right" against the enclosing cell rather than the table, so a
    right-hand group built from stacked tables comes apart - the label flies
    to the margin while the logo stays put. Instead the row is three columns
    with a narrow right-hand cell, and everything inside it aligns left.
    """
    label = (
        f"font-size:5.5pt;color:{ACCENT};letter-spacing:1.2pt;"
        f"text-transform:uppercase;font-weight:bold;"
    )
    # Underline sits in its own table - as a second row under the label it set
    # the shared column width and wrapped the label onto two lines.
    rule = f"border-top:1px solid {ACCENT};font-size:1pt;line-height:1pt;"
    return f"""
<table width="100%" cellspacing="0" cellpadding="0" style="background-color:{HEADER_BG};">
<tr>
    <td width="55%" style="padding:9pt 0 10pt 20pt;vertical-align:bottom;">
        <table cellspacing="0" cellpadding="0">
            <tr><td style="{label}">Sponsored by</td></tr>
        </table>
        <table width="46" cellspacing="0" cellpadding="0">
            <tr><td style="{rule}">&nbsp;</td></tr>
        </table>
        <table width="118" cellspacing="0" cellpadding="0" style="margin-top:5pt;"><tr>
            <td width="15" style="background-color:{AI_COLOR};color:#ffffff;font-weight:bold;
                       font-size:9pt;height:15pt;text-align:center;vertical-align:middle;">I</td>
            <td width="15" style="background-color:{ACCENT};color:#ffffff;font-weight:bold;
                       font-size:9pt;height:15pt;text-align:center;vertical-align:middle;">F</td>
            <td style="padding-left:6pt;vertical-align:middle;">
                <div style="font-size:10pt;font-weight:bold;color:#ffffff;line-height:1.15;">
                    IntelliForge <span style="color:{AI_COLOR};">AI</span></div>
            </td>
        </tr></table>
    </td>
    <td width="29%">&nbsp;</td>
    <td width="16%" style="padding:9pt 20pt 10pt 0;vertical-align:bottom;">
        <table cellspacing="0" cellpadding="0">
            <tr><td style="{label}">Event technology by</td></tr>
        </table>
        <table width="46" cellspacing="0" cellpadding="0">
            <tr><td style="{rule}">&nbsp;</td></tr>
        </table>
        <table width="112" cellspacing="0" cellpadding="0" style="margin-top:5pt;"><tr>
            <td width="15" style="background-color:{SECONDARY};color:{HEADER_BG};font-weight:bold;
                       font-size:9pt;height:15pt;text-align:center;vertical-align:middle;">M</td>
            <td style="padding-left:6pt;vertical-align:middle;">
                <div style="font-size:10pt;font-weight:bold;color:#ffffff;line-height:1.15;"
                    >maidaan<span style="color:{SECONDARY};">.academy</span></div>
            </td>
        </tr></table>
    </td>
</tr>
</table>
"""


def sidebar_block() -> str:
    """Vertical 'CERTIFICATE OF APPRECIATION' title (centered in the sidebar)."""
    line1 = stacked_letters("CERTIFICATE")
    line2 = "<br/><br/>".join(stacked_letters(w) for w in "OF APPRECIATION".split())
    return (
        f'<div style="color:#ffffff;font-weight:bold;font-size:11pt;line-height:1.12;">{line1}</div>'
        f'<div style="color:#ffffff;font-size:5.5pt;letter-spacing:1pt;margin-top:14pt;'
        f'line-height:1.2;">{line2}</div>'
    )


def india_independence_badge() -> str:
    """India Independence Day emblem for the dark sidebar foot: the real Flag
    of India PNG (24-spoke Ashoka Chakra, rendered by
    scripts/build_india_flag_asset.py) above a 'Celebrating Independence Day'
    caption. Falls back to a typographic tricolour with a chakra-stand-in glyph
    if the asset is missing (the true wheel U+2638 is tofu in xhtml2pdf's base
    fonts, so U+2742 — a circled spoked star — carries the wheel)."""
    saffron, green, navy = "#FF9933", "#138808", "#000080"
    if FLAG_PATH.exists():
        # Real Flag of India PNG (24-spoke Ashoka Chakra); see
        # scripts/build_india_flag_asset.py.
        flag = (
            f'<img src="{image_data_uri(FLAG_PATH)}" width="60" height="40" '
            f'alt="Flag of India"/>'
        )
    else:
        # Fallback: typographic tricolour with a chakra-stand-in glyph.
        flag = (
            f'<table width="58" align="center" cellspacing="0" cellpadding="0" '
            f'style="border:0.75pt solid #ffffff;">'
            f'<tr><td style="background-color:{saffron};height:10pt;font-size:1pt;'
            f'line-height:10pt;">&nbsp;</td></tr>'
            f'<tr><td align="center" style="background-color:#ffffff;height:14pt;'
            f'text-align:center;vertical-align:middle;color:{navy};font-size:12pt;'
            f'line-height:14pt;">&#10050;</td></tr>'
            f'<tr><td style="background-color:{green};height:10pt;font-size:1pt;'
            f'line-height:10pt;">&nbsp;</td></tr></table>'
        )
    return (
        f'{flag}'
        f'<div style="font-size:5.5pt;color:{saffron};letter-spacing:2.2pt;'
        f'font-weight:bold;text-transform:uppercase;padding-top:8pt;">Celebrating</div>'
        f'<div style="font-size:8.5pt;color:#ffffff;letter-spacing:0.8pt;font-weight:bold;'
        f'text-transform:uppercase;padding-top:2pt;line-height:1.15;">Independence<br/>Day</div>'
        f'<div style="font-size:6pt;color:{saffron};letter-spacing:1.4pt;font-weight:bold;'
        f'padding-top:5pt;">15 AUGUST</div>'
    )


def field_box(label: str, value: str, width: str) -> str:
    """Race-bib style field; renders a blank rule when the value is empty.

    Padding sits on an inner td - xhtml2pdf mis-measures padding applied
    directly to a <table>, which pushes the label out over its own border.
    """
    if value:
        inner = f'<div style="font-size:13pt;color:{INK};font-weight:bold;">{esc(value)}</div>'
    else:
        inner = blank_rule(width="100%", height="18pt", color="#4a5568")
    return (
        f'<table width="{width}" cellspacing="0" cellpadding="0" '
        f'style="background-color:#ffffff;border:1.5pt solid {ACCENT};'
        f'border-top:3pt solid {SECONDARY};">'
        f'<tr><td style="padding:8pt 12pt 9pt;">'
        f'<div style="font-size:8pt;color:{ACCENT};text-transform:uppercase;'
        f'letter-spacing:0.9pt;font-weight:bold;padding-bottom:5pt;">&#9654; {esc(label)}</div>'
        f"{inner}"
        f"</td></tr></table>"
    )


def sobha_wordmark(sobha_pt: float = 10.5, main_pt: float = 21) -> str:
    """Typographic recreation of the Sobha Dream Gardens wordmark.

    SOBHA sits above in spaced serif caps; "dream" (brand red, bold) runs into
    "gardens" (black) as one lowercase word, matching the logo lockup. Times is
    the only serif xhtml2pdf ships, so it stands in for the display serif.
    """
    return (
        f'<div style="font-family:Times,\'Times New Roman\',serif;font-size:{sobha_pt}pt;'
        f'color:{INK};letter-spacing:5pt;line-height:1;">SOBHA</div>'
        f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:{main_pt}pt;'
        f'line-height:1;padding-top:2pt;">'
        f'<span style="color:{SDG_RED};font-weight:bold;">dream</span>'
        f'<span style="color:{INK};">gardens</span></div>'
    )


def sobha_host_lockup() -> str:
    """'Tournament hosted at' host/venue endorsement for the certificate front."""
    return (
        f'<div style="font-size:7.5pt;color:{MUTED};letter-spacing:1.6pt;'
        f'text-transform:uppercase;font-weight:bold;padding-bottom:8pt;">'
        f"Tournament hosted at</div>"
        f"{sobha_wordmark()}"
    )


# ---------------------------------------------------------------------------
# Page 1 - blank certificate
# ---------------------------------------------------------------------------

def build_front(event_name: str, event_date: str) -> str:
    return f"""
<table width="100%" cellspacing="0" cellpadding="0" style="background-color:#ffffff;">
<tr><td colspan="3" style="padding:0;">{header_bar()}</td></tr>
<tr><td colspan="3" style="padding:0;">
    {appreciation_header_stripe_html(accent=ACCENT)}</td></tr>
<tr>
    <td width="3%" style="vertical-align:middle;padding:20pt 0 20pt 10pt;
               background-color:#f8faf9;">
        {appreciation_pdf_accent_rail(accent=ACCENT, secondary=SECONDARY)}
    </td>
    <td width="72%" style="vertical-align:top;padding:24pt 20pt {H_FRONT_FILL}pt 6pt;
               background-color:#f8faf9;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td width="40pt" valign="top" align="center"
                    style="vertical-align:top;text-align:center;padding-top:2pt;">
                    {appreciation_sport_seal_html(accent=ACCENT, secondary=SECONDARY,
                                                  sidebar_color=SIDEBAR)}
                </td>
                <td style="padding-left:8pt;border-left:2pt solid {SECONDARY};">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr><td style="font-size:9.5pt;color:{MUTED};letter-spacing:0.9pt;
                                       text-transform:uppercase;font-weight:bold;
                                       padding-bottom:6pt;">Presented to</td></tr>
                        <tr><td>{blank_rule(height="30pt", color=ACCENT)}</td></tr>
                        <tr><td style="font-size:7.5pt;color:{CAPTION};letter-spacing:0.6pt;
                                       padding-top:3pt;">FULL NAME OF PARTICIPANT</td></tr>
                        <tr><td style="font-size:9.5pt;color:{MUTED};letter-spacing:0.9pt;
                                       text-transform:uppercase;font-weight:bold;
                                       padding:14pt 0 4pt;">Award / Position</td></tr>
                        <tr><td>{blank_rule(width="70%", height="24pt", color=SIDEBAR)}</td></tr>
                        <tr><td style="font-size:13pt;color:#2d3748;line-height:1.6;
                                       padding-top:15pt;">{RECOGNITION_TEXT}</td></tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td colspan="2" style="padding-top:38pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                            <td width="40%" valign="bottom" style="vertical-align:bottom;">
                                {field_box("Date", event_date, "150pt")}
                            </td>
                            <td width="12%">&nbsp;</td>
                            <td width="48%" valign="bottom" style="vertical-align:bottom;">
                                {field_box("Event", event_name, "230pt")}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td colspan="2" style="padding-top:32pt;">
                    <table width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                            <td width="44%" valign="bottom" style="vertical-align:bottom;">
                                <div style="padding-bottom:26pt;">{sobha_host_lockup()}</div>
                                {blank_rule(width="84%", height="22pt", color="#4a5568")}
                                <div style="font-size:8.5pt;color:{MUTED};letter-spacing:0.8pt;
                                            text-transform:uppercase;padding-top:4pt;
                                            font-weight:bold;">Authorised Signatory</div>
                            </td>
                            <td width="8%">&nbsp;</td>
                            <td width="48%" valign="bottom" style="vertical-align:bottom;">
                                <table cellspacing="0" cellpadding="0"
                                       style="border:1.5pt solid #e2e8f0;background-color:#ffffff;">
                                <tr>
                                    <td align="center" style="text-align:center;padding:6pt;">
                                        <img src="{qr_data_uri(URL_CERTS)}" width="50" height="50" alt="QR"/>
                                    </td>
                                    <td style="padding:6pt 12pt 6pt 2pt;font-size:8.5pt;color:{MUTED};
                                               vertical-align:middle;">
                                        Claim your <strong>verifiable</strong><br/>digital certificate<br/>
                                        <span style="font-family:monospace;font-size:7.5pt;
                                                     color:{ACCENT};">certs.intelliforge.tech</span>
                                    </td>
                                </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td>
    <td width="25%" style="background-color:{SIDEBAR};vertical-align:top;
               border-left:3pt solid {SECONDARY};">
        {appreciation_pdf_sidebar_stripes(accent=ACCENT, secondary=SECONDARY)}
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td align="center" style="text-align:center;
                       vertical-align:top;padding:20pt 6pt 0;">
                {sidebar_block()}
                <div style="height:30pt;font-size:1pt;line-height:30pt;">&nbsp;</div>
                {india_independence_badge()}
            </td></tr>
        </table>
    </td>
</tr>
<tr><td colspan="3" style="padding:0;">
    {appreciation_pdf_tricolor_footer()}</td></tr>
</table>
"""


# ---------------------------------------------------------------------------
# Page 2 - information and promotion
# ---------------------------------------------------------------------------

def bullet_list(items: list[str]) -> str:
    rows = "".join(
        f'<tr><td width="9pt" valign="top" style="vertical-align:top;color:{ACCENT};'
        f'font-size:7pt;font-weight:bold;padding-top:1.5pt;">&#9654;</td>'
        f'<td style="font-size:7.6pt;color:#2d3748;line-height:1.42;padding-bottom:4pt;">'
        f"{item}</td></tr>"
        for item in items
    )
    return f'<table width="100%" cellspacing="0" cellpadding="0">{rows}</table>'


def info_column(
    *,
    kicker: str,
    title: str,
    domain: str,
    url: str,
    blurb: str,
    items: list[str],
    accent: str,
) -> str:
    # Two-row column: the content cell claims full height (valign top) so the
    # QR footer (valign bottom) pins to a common baseline across all three
    # columns, regardless of how many bullets each carries.
    return f"""
<table width="100%" height="100%" cellspacing="0" cellpadding="0"
       style="background-color:#ffffff;border:1pt solid #e2e8f0;border-top:3.5pt solid {accent};">
<tr><td height="100%" style="padding:10pt 11pt 4pt;vertical-align:top;">
    <table width="100%" cellspacing="0" cellpadding="0">
        <tr><td style="font-size:6pt;color:{accent};letter-spacing:1.1pt;text-transform:uppercase;
                       font-weight:bold;padding-bottom:4pt;">{kicker}</td></tr>
        <tr><td style="font-size:11.5pt;font-weight:bold;color:{INK};line-height:1.15;
                       padding-bottom:4pt;">{esc(title)}</td></tr>
        <tr><td style="font-size:6.8pt;font-family:monospace;color:{accent};
                       padding-bottom:7pt;">{esc(domain)}</td></tr>
        <tr><td style="font-size:7.8pt;color:{MUTED};line-height:1.45;padding-bottom:8pt;">
            {blurb}</td></tr>
        <tr><td style="border-top:1pt solid #edf2f7;padding-top:7pt;">{bullet_list(items)}</td></tr>
    </table>
</td></tr>
<tr><td style="padding:6pt 11pt 11pt;vertical-align:bottom;text-align:center;
               border-top:1pt solid #edf2f7;">
    <img src="{qr_data_uri(url, box_size=3)}" width="58" height="58" alt="QR"/>
    <div style="font-size:5.6pt;color:{CAPTION};letter-spacing:0.7pt;padding-top:2pt;
                text-transform:uppercase;">Scan to open</div>
</td></tr></table>
"""


def build_back() -> str:
    col_main = info_column(
        kicker="The Company",
        title="IntelliForge AI",
        domain="intelliforge.tech",
        url=URL_MAIN,
        blurb=(
            "Hyderabad-based AI agent development and workflow automation studio. "
            "From prompt engineering and RAG pipelines to autonomous agents and "
            "full AI applications. Aligned with the Bharat AI Mission."
        ),
        items=[
            "Founded by <strong>Girish Hiremath</strong> &mdash; M.Tech Data Science "
            "&amp; AI, IIIT Dharwad",
            "Fortune 500 delivery across banking, pharma, telecom and IoT",
            "<strong>67+ AI products</strong> shipped to production",
            "A 5-level framework: AI foundations &rarr; full AI applications",
        ],
        accent=AI_COLOR,
    )

    col_learning = info_column(
        kicker="Learn",
        title="IntelliForge Learning",
        domain="learning.intelliforge.tech",
        url=URL_LEARNING,
        blurb=(
            "The complete AI learning platform. Register for live sessions, watch "
            "training videos, track your progress and earn shareable certificates."
        ),
        items=[
            "<strong>30+</strong> live training sessions",
            "Free demo sessions &mdash; no payment, no signup",
            "Courses, learning paths and a personal dashboard",
            "Shareable certificates issued via certs.intelliforge.tech",
        ],
        accent=GREEN,
    )

    col_upskill = info_column(
        kicker="Bootcamp &mdash; Now Enrolling",
        title="Ship Proof Before Your Interview",
        domain="upskill.intelliforge.tech",
        url=URL_UPSKILL,
        blurb=(
            "Ship two live AI products in 14 days and earn a credential recruiters "
            "can actually click and verify. Founder-taught, live on Zoom."
        ),
        items=[
            "<strong>2-Week Sprint &mdash; Rs.&nbsp;4,999</strong> &middot; two products deployed",
            "<strong>12-Week Bootcamp &mdash; Rs.&nbsp;49,999</strong> early bird "
            "(reg. Rs.&nbsp;74,999)",
            "Live weekend classes &middot; Sat &amp; Sun &middot; IST",
            "Build-alongside slots on real IntelliForge products",
            "15-day money-back guarantee &middot; 0% EMI available",
        ],
        accent=ACCENT,
    )

    return f"""
<table width="100%" cellspacing="0" cellpadding="0" style="background-color:#f8faf9;">
<tr><td style="padding:0;">{header_bar()}</td></tr>
<tr><td style="padding:0;">
    {appreciation_header_stripe_html(accent=ACCENT)}</td></tr>

<tr><td style="padding:0;">
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color:{SIDEBAR};">
    <tr>
        <td style="padding:14pt 18pt 14pt 26pt;vertical-align:middle;">
            <div style="font-size:6pt;color:{SECONDARY};letter-spacing:1.4pt;
                        text-transform:uppercase;font-weight:bold;">
                Beyond the field &mdash; build your career in AI
            </div>
            <div style="font-size:19pt;font-weight:bold;color:#ffffff;letter-spacing:0.3pt;
                        padding-top:5pt;line-height:1.15;">
                Interview in weeks, not months.
            </div>
            <div style="font-size:8.5pt;color:#cbd5e0;padding-top:6pt;line-height:1.45;">
                Ship two live AI products in 14 days for
                <span style="color:{SECONDARY};font-weight:bold;">Rs.&nbsp;4,999</span>.
                Or take the 12-week bootcamp and earn a credential recruiters can verify.
            </div>
        </td>
        <td width="140" align="right" style="padding:12pt 26pt 12pt 0;vertical-align:middle;
                   text-align:right;">
            <table width="86" align="right" cellspacing="0" cellpadding="0"
                   style="background-color:#ffffff;">
            <tr><td align="center" style="text-align:center;padding:5pt 5pt 4pt;">
                <img src="{qr_data_uri(URL_UPSKILL, box_size=4)}" width="62" height="62"
                     alt="UpSkill QR"/>
                <div style="font-size:4.6pt;color:{SIDEBAR};letter-spacing:0.3pt;
                            padding-top:2pt;font-weight:bold;">UPSKILL.INTELLIFORGE.TECH</div>
            </td></tr>
            </table>
        </td>
    </tr>
    </table>
</td></tr>

<tr><td style="padding:13pt 20pt {H_BACK_FILL}pt;vertical-align:top;">
    <table width="100%" height="100%" cellspacing="0" cellpadding="0">
    <tr>
        <td width="33%" valign="top" style="vertical-align:top;padding-right:8pt;">{col_main}</td>
        <td width="33%" valign="top" style="vertical-align:top;padding-right:8pt;">{col_learning}</td>
        <td width="34%" valign="top" style="vertical-align:top;">{col_upskill}</td>
    </tr>
    </table>
</td></tr>

<tr><td style="padding:0;">
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color:{HEADER_BG};">
    <tr>
        <td style="padding:10pt 26pt;font-size:7.5pt;color:#a0aec0;vertical-align:middle;">
            <span style="color:{SECONDARY};font-weight:bold;">alerts@intelliforge.tech</span>
            &nbsp;&middot;&nbsp; WhatsApp <span style="color:#ffffff;">+91 85559 60837</span>
            &nbsp;&middot;&nbsp; Hyderabad, Telangana, India
        </td>
        <td align="right" style="text-align:right;padding:10pt 26pt;font-size:7pt;
                   color:#718096;vertical-align:middle;">
            Event technology by <span style="color:#ffffff;">maidaan<span
                style="color:{SECONDARY};">.academy</span></span>
        </td>
    </tr>
    </table>
</td></tr>
<tr><td style="padding:0;">{appreciation_pdf_tricolor_footer()}</td></tr>
</table>
"""


# ---------------------------------------------------------------------------

DOCUMENT_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
    @page {{ size: {page_w}pt {page_h}pt; margin: 0; }}
    body {{ font-family: Helvetica, Arial, sans-serif; color:#1a202c; margin:0; padding:0; }}
    table {{ border-collapse: collapse; }}
    td {{ padding: 0; }}
</style>
</head>
<body>
{front}
<pdf:nextpage/>
{back}
</body>
</html>
"""


def build_pdf(event_name: str = "", event_date: str = "") -> bytes:
    html = DOCUMENT_HTML.format(
        page_w=PAGE_W,
        page_h=PAGE_H,
        front=build_front(event_name.strip(), event_date.strip()),
        back=build_back(),
    )
    buf = BytesIO()
    status = pisa.CreatePDF(src=html, dest=buf, encoding="UTF-8")
    if status.err:
        raise SystemExit(f"PDF generation failed: {status.log}")
    buf.seek(0)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="sports-tournament-handout.pdf",
                        help="output PDF path")
    parser.add_argument("--event", default="",
                        help="pre-printed event name (blank rule if omitted)")
    parser.add_argument("--date", default="",
                        help="pre-printed event date (blank rule if omitted)")
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    out.write_bytes(build_pdf(args.event, args.date))
    print(f"Wrote {out}  ({out.stat().st_size / 1024:.0f} KB, A4 landscape)")


if __name__ == "__main__":
    main()

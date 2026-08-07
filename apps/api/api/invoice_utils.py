"""Helpers for tax invoice PDF generation."""

from __future__ import annotations

import html as html_mod
import re
from datetime import datetime
from typing import Iterable

from api.invoice_brand import invoice_brand_colors, invoice_pdf_color_tokens


_ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return f"{_TENS[n // 10]} {_ONES[n % 10]}".strip()


def _three_digits(n: int) -> str:
    if n == 0:
        return ""
    if n < 100:
        return _two_digits(n)
    return f"{_ONES[n // 100]} Hundred {_two_digits(n % 100)}".strip()


def amount_in_words_inr(amount: int) -> str:
    """Convert integer INR amount to words (Indian English)."""
    if amount < 0:
        raise ValueError("Amount must be non-negative")
    if amount == 0:
        return "Zero Only"

    parts: list[str] = []
    crore = amount // 10_000_000
    amount %= 10_000_000
    lakh = amount // 100_000
    amount %= 100_000
    thousand = amount // 1_000
    amount %= 1_000
    hundred_rest = amount

    if crore:
        parts.append(f"{_two_digits(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if hundred_rest:
        parts.append(_three_digits(hundred_rest))

    return f"{' '.join(parts)} Only"


def format_inr(amount: float | int) -> str:
    n = int(round(float(amount)))
    return f"₹{n:,}"


def format_usd(amount: float | int) -> str:
    n = float(amount)
    if abs(n - round(n)) < 0.001:
        return f"${int(round(n)):,}"
    return f"${n:,.2f}"


def format_invoice_date(value: str) -> str:
    """Format YYYY-MM-DD or ISO datetime to 'July 9, 2026'."""
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except ValueError:
        return raw


def escape_text(value: str) -> str:
    return html_mod.escape(value or "", quote=False)


def party_address_html(lines: Iterable[str], *, muted: str = "#64748b") -> str:
    rows = []
    for line in lines:
        text = (line or "").strip()
        if text:
            rows.append(
                f'<tr><td style="font-size: 9pt; color: {muted}; line-height: 1.5; padding: 0;">'
                f"{escape_text(text)}</td></tr>"
            )
    return "".join(rows)


def line_item_amount_usd(rate: float, quantity: float) -> float:
    return round(float(rate) * float(quantity), 2)


def build_line_items_rows(items: list[dict], *, colors: dict | None = None) -> tuple[str, float]:
    """Return HTML rows and USD subtotal."""
    palette = colors or invoice_pdf_color_tokens()
    border = palette.get("color_table_border", "#e2e8f0")
    purple = palette.get("color_purple", "#4338ca")
    text = palette.get("color_text", "#1a202c")
    rows: list[str] = []
    subtotal = 0.0
    for item in items:
        rate = float(item["rate"])
        qty = float(item["quantity"])
        amount = line_item_amount_usd(rate, qty)
        subtotal += amount
        rate_label = (item.get("rate_label") or "").strip() or f"{format_usd(rate)}"
        qty_label = (item.get("quantity_label") or "").strip() or str(int(qty) if qty == int(qty) else qty)
        desc = escape_text(item["description"]).replace("\n", "<br/>")
        rows.append(
            f"""
            <tr>
                <td style="padding: 11pt 10pt; border-bottom: 1px solid {border}; font-size: 9pt; color: {text}; line-height: 1.45; vertical-align: top; width: 52%;">
                    {desc}
                </td>
                <td style="padding: 11pt 10pt; border-bottom: 1px solid {border}; font-size: 9pt; color: {text}; vertical-align: top; width: 16%;">
                    {escape_text(rate_label)}
                </td>
                <td style="padding: 11pt 10pt; border-bottom: 1px solid {border}; font-size: 9pt; color: {text}; vertical-align: top; width: 16%;">
                    {escape_text(qty_label)}
                </td>
                <td align="right" style="padding: 11pt 10pt; border-bottom: 1px solid {border}; font-size: 9pt; font-weight: bold; color: {purple}; vertical-align: top; width: 16%; text-align: right;">
                    {format_usd(amount)}
                </td>
            </tr>
            """
        )
    return "".join(rows), round(subtotal, 2)


def default_invoice_number(seq: int | None = None) -> str:
    year = datetime.now().year
    suffix = seq if seq is not None else 1
    return f"INV-{year}-{suffix}"


def split_address_lines(address: str) -> list[str]:
    return [ln.strip() for ln in re.split(r"[\r\n]+", address or "") if ln.strip()]


def _optional_party_row(label: str, value: str, *, prefix: str = "", muted: str = "#64748b") -> str:
    text = (value or "").strip()
    if not text:
        return ""
    display = f"{prefix}{escape_text(text)}" if prefix else escape_text(text)
    return (
        f'<tr><td style="font-size: 9.5pt; color: {muted}; line-height: 1.45; padding-top: 4pt;">'
        f"{escape_text(label)} {display}</td></tr>"
    )


def build_invoice_html(data: dict) -> str:
    """Render invoice dict into HTML for xhtml2pdf."""
    from api.invoice_templates import INVOICE_TAX_HTML

    brand = invoice_pdf_color_tokens()
    items = data.get("items") or []
    line_rows, total_usd = build_line_items_rows(items, colors=brand)
    exchange_rate = float(data.get("exchange_rate") or 90)
    total_inr = int(round(total_usd * exchange_rate))
    words = amount_in_words_inr(total_inr)

    bill_from_lines = split_address_lines(data.get("bill_from_address", ""))
    bill_to_lines = split_address_lines(data.get("bill_to_address", ""))

    signature_name = (data.get("signature_name") or data.get("bill_from_name") or "").strip()
    muted = brand["color_muted"]

    return INVOICE_TAX_HTML.format(
        invoice_number=escape_text(data.get("invoice_number", "")),
        invoice_date=escape_text(format_invoice_date(data.get("invoice_date", ""))),
        bill_from_name=escape_text(data.get("bill_from_name", "")),
        bill_from_address_rows=party_address_html(bill_from_lines, muted=muted),
        bill_from_email_row=_optional_party_row("Email:", data.get("bill_from_email", ""), muted=muted),
        bill_from_pan_row=_optional_party_row("PAN:", data.get("bill_from_pan", ""), muted=muted),
        bill_to_name=escape_text(data.get("bill_to_name", "")),
        bill_to_address_rows=party_address_html(bill_to_lines, muted=muted),
        bill_to_gstin_row=_optional_party_row("GSTIN:", data.get("bill_to_gstin", ""), muted=muted),
        bill_to_email_row=_optional_party_row("Email:", data.get("bill_to_email", ""), muted=muted),
        line_items_rows=line_rows,
        total_usd=format_usd(total_usd),
        total_inr=format_inr(total_inr),
        exchange_rate=escape_text(str(int(exchange_rate) if exchange_rate == int(exchange_rate) else exchange_rate)),
        amount_in_words=escape_text(words),
        total_inr_due=format_inr(total_inr),
        signature_name=escape_text(signature_name),
        **brand,
    )


def build_invoice_pdf(data: dict) -> bytes:
    """Render invoice dict into PDF bytes."""
    from io import BytesIO

    from xhtml2pdf import pisa

    html = build_invoice_html(data)
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=pdf_buffer, encoding="UTF-8")
    if pisa_status.err:
        raise RuntimeError("Error generating invoice PDF")
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def compact_invoice_token_payload(data: dict) -> dict:
    """Compact invoice fields for HMAC token encoding."""
    items = []
    for item in data.get("items") or []:
        compact = {
            "d": item["description"],
            "r": float(item["rate"]),
            "q": float(item["quantity"]),
        }
        if item.get("rate_label"):
            compact["rl"] = item["rate_label"]
        if item.get("quantity_label"):
            compact["ql"] = item["quantity_label"]
        items.append(compact)
    return {
        "k": "inv",
        "inv": data["invoice_number"],
        "dt": data["invoice_date"],
        "fn": data["bill_from_name"],
        "fa": data.get("bill_from_address", ""),
        "fe": data.get("bill_from_email", ""),
        "fp": data.get("bill_from_pan", ""),
        "tn": data["bill_to_name"],
        "ta": data.get("bill_to_address", ""),
        "tg": data.get("bill_to_gstin", ""),
        "te": data.get("bill_to_email", ""),
        "xr": float(data.get("exchange_rate") or 90),
        "sn": data.get("signature_name") or data["bill_from_name"],
        "items": items,
    }


def expand_invoice_token_payload(compact: dict) -> dict:
    """Expand compact token payload back to invoice render dict."""
    items = []
    for item in compact.get("items") or []:
        items.append(
            {
                "description": item["d"],
                "rate": item["r"],
                "quantity": item["q"],
                "rate_label": item.get("rl", ""),
                "quantity_label": item.get("ql", ""),
            }
        )
    return {
        "invoice_number": compact["inv"],
        "invoice_date": compact["dt"],
        "bill_from_name": compact["fn"],
        "bill_from_address": compact.get("fa", ""),
        "bill_from_email": compact.get("fe", ""),
        "bill_from_pan": compact.get("fp", ""),
        "bill_to_name": compact["tn"],
        "bill_to_address": compact.get("ta", ""),
        "bill_to_gstin": compact.get("tg", ""),
        "bill_to_email": compact.get("te", ""),
        "exchange_rate": compact.get("xr", 90),
        "signature_name": compact.get("sn") or compact["fn"],
        "items": items,
    }

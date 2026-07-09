"""
HTML source for tax invoice PDFs (xhtml2pdf).
Layout matches Example_Invoice_For_Reference_Only.pdf — Cognyzer billing format.
"""

INVOICE_TAX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4 portrait;
            margin: 28pt 32pt 32pt 32pt;
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

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="vertical-align: top; width: 55%;">&nbsp;</td>
    <td align="right" style="vertical-align: top; text-align: right; width: 45%;">
        <table cellspacing="0" cellpadding="0" align="right">
            <tr><td align="right" style="font-size: 22pt; font-weight: bold; color: #111827; letter-spacing: 0.5pt; text-align: right;">
                TAX INVOICE
            </td></tr>
            <tr><td style="font-size: 6pt; line-height: 8pt;">&nbsp;</td></tr>
            <tr>
                <td align="right" style="text-align: right;">
                    <table cellspacing="0" cellpadding="0" align="right">
                        <tr>
                            <td style="font-size: 9pt; color: #4a5568; padding-right: 10pt; text-align: right;">Invoice #</td>
                            <td style="font-size: 9.5pt; font-weight: bold; color: #111827; text-align: right;">{invoice_number}</td>
                        </tr>
                        <tr>
                            <td style="font-size: 9pt; color: #4a5568; padding-right: 10pt; padding-top: 4pt; text-align: right;">Invoice date</td>
                            <td style="font-size: 9.5pt; font-weight: bold; color: #111827; padding-top: 4pt; text-align: right;">{invoice_date}</td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td>
</tr>
</table>

<table width="100%"><tr><td style="font-size: 10pt; line-height: 10pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="vertical-align: top; width: 48%; padding-right: 12pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td style="font-size: 8.5pt; font-weight: bold; letter-spacing: 1pt; color: #4a5568; padding-bottom: 8pt;">
                BILL FROM:
            </td></tr>
            <tr><td style="font-size: 11pt; font-weight: bold; color: #111827; padding-bottom: 6pt;">
                {bill_from_name}
            </td></tr>
            {bill_from_address_rows}
            {bill_from_email_row}
            {bill_from_pan_row}
        </table>
    </td>
    <td style="vertical-align: top; width: 48%; padding-left: 12pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr><td style="font-size: 8.5pt; font-weight: bold; letter-spacing: 1pt; color: #4a5568; padding-bottom: 8pt;">
                BILL TO:
            </td></tr>
            <tr><td style="font-size: 11pt; font-weight: bold; color: #111827; padding-bottom: 6pt;">
                {bill_to_name}
            </td></tr>
            {bill_to_address_rows}
            {bill_to_gstin_row}
            {bill_to_email_row}
        </table>
    </td>
</tr>
</table>

<table width="100%"><tr><td style="font-size: 14pt; line-height: 14pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0" style="border: 1px solid #cbd5e0;">
<tr style="background-color: #f7fafc;">
    <td style="padding: 8pt; font-size: 8.5pt; font-weight: bold; color: #4a5568; border-bottom: 1px solid #cbd5e0; width: 52%;">Description</td>
    <td style="padding: 8pt; font-size: 8.5pt; font-weight: bold; color: #4a5568; border-bottom: 1px solid #cbd5e0; width: 16%;">Rate</td>
    <td style="padding: 8pt; font-size: 8.5pt; font-weight: bold; color: #4a5568; border-bottom: 1px solid #cbd5e0; width: 16%;">Quantity</td>
    <td align="right" style="padding: 8pt; font-size: 8.5pt; font-weight: bold; color: #4a5568; border-bottom: 1px solid #cbd5e0; width: 16%; text-align: right;">Amount</td>
</tr>
{line_items_rows}
</table>

<table width="100%"><tr><td style="font-size: 8pt; line-height: 8pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="vertical-align: top; width: 58%;">&nbsp;</td>
    <td style="vertical-align: top; width: 42%;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td style="font-size: 9.5pt; color: #4a5568; padding: 6pt 0;">Total in (USD)</td>
                <td align="right" style="font-size: 9.5pt; font-weight: bold; color: #111827; padding: 6pt 0; text-align: right;">{total_usd}</td>
            </tr>
            <tr>
                <td style="font-size: 9.5pt; color: #4a5568; padding: 6pt 0; vertical-align: top;">Total in (INR)<br/>
                    <span style="font-size: 8pt; color: #718096;">Exchange rate:<br/>1 USD = {exchange_rate} INR</span>
                </td>
                <td align="right" style="font-size: 11pt; font-weight: bold; color: #111827; padding: 6pt 0; text-align: right; vertical-align: top;">{total_inr}</td>
            </tr>
        </table>
    </td>
</tr>
</table>

<table width="100%"><tr><td style="font-size: 8pt; line-height: 8pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="font-size: 9pt; color: #4a5568;">
        Amount in words : <span style="color: #111827; font-weight: bold;">{amount_in_words}</span>
    </td>
</tr>
</table>

<table width="100%"><tr><td style="font-size: 16pt; line-height: 16pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="vertical-align: top; width: 55%;">&nbsp;</td>
    <td align="right" style="vertical-align: top; text-align: right; width: 45%;">
        <table cellspacing="0" cellpadding="0" align="right" style="border: 2px solid #111827;">
            <tr>
                <td align="center" style="padding: 12pt 24pt; text-align: center;">
                    <table cellspacing="0" cellpadding="0" align="center">
                        <tr><td align="center" style="font-size: 8.5pt; font-weight: bold; letter-spacing: 1.5pt; color: #4a5568; text-align: center; padding-bottom: 6pt;">
                            TOTAL DUE
                        </td></tr>
                        <tr><td align="center" style="font-size: 16pt; font-weight: bold; color: #111827; text-align: center;">
                            INR {total_inr_due}
                        </td></tr>
                    </table>
                </td>
            </tr>
        </table>
    </td>
</tr>
</table>

<table width="100%"><tr><td style="font-size: 24pt; line-height: 24pt;">&nbsp;</td></tr></table>

<table width="100%" cellspacing="0" cellpadding="0">
<tr>
    <td style="vertical-align: bottom;">
        <table cellspacing="0" cellpadding="0">
            <tr><td style="font-size: 9pt; color: #4a5568; padding-bottom: 28pt;">For: {signature_name}</td></tr>
            <tr><td style="font-size: 11pt; font-weight: bold; color: #111827; border-top: 1px solid #a0aec0; padding-top: 6pt; min-width: 180pt;">
                {signature_name}
            </td></tr>
        </table>
    </td>
</tr>
</table>

</body>
</html>
"""

"""
HTML source for tax invoice PDFs (xhtml2pdf).
IntelliForge-branded layout aligned with participation certificate styling.
"""

INVOICE_TAX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4 portrait;
            margin: 0;
        }}
        body {{
            font-family: Helvetica, Arial, sans-serif;
            color: {color_text};
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

<table width="100%" cellspacing="0" cellpadding="0" style="background-color: {color_frame};">
<tr><td style="padding: 18pt 22pt 22pt;">

<table width="100%" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
<tr><td>

    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: {color_header_bg};">
    <tr><td style="padding: 22pt 28pt 20pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td style="vertical-align: top; width: 58%;">
                    <table cellspacing="0" cellpadding="0">
                        <tr><td style="font-size: 7.5pt; letter-spacing: 3pt; color: {color_gold}; font-weight: bold; padding-bottom: 4pt;">
                            {org_tagline}
                        </td></tr>
                        <tr><td style="font-size: 18pt; font-weight: bold; color: #ffffff; padding-bottom: 10pt;">
                            {brand_name}
                        </td></tr>
                        <tr><td>
                            <table cellspacing="0" cellpadding="0" style="border: 2px solid {color_gold};">
                                <tr><td style="padding: 5pt 18pt; font-size: 8pt; letter-spacing: 2.5pt; color: {color_gold}; font-weight: bold;">
                                    TAX INVOICE
                                </td></tr>
                            </table>
                        </td></tr>
                    </table>
                </td>
                <td align="right" style="vertical-align: top; text-align: right; width: 42%;">
                    <table cellspacing="0" cellpadding="0" align="right">
                        <tr>
                            <td style="font-size: 8.5pt; color: #c7d2fe; padding-right: 10pt; text-align: right;">Invoice #</td>
                            <td style="font-size: 9.5pt; font-weight: bold; color: #ffffff; text-align: right;">{invoice_number}</td>
                        </tr>
                        <tr>
                            <td style="font-size: 8.5pt; color: #c7d2fe; padding-right: 10pt; padding-top: 5pt; text-align: right;">Invoice date</td>
                            <td style="font-size: 9.5pt; font-weight: bold; color: #ffffff; padding-top: 5pt; text-align: right;">{invoice_date}</td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td></tr>
    </table>

    <table width="100%"><tr><td style="height: 3pt; background-color: {color_gold}; font-size: 1pt;">&nbsp;</td></tr></table>

    <table width="100%">
    <tr><td style="padding: 20pt 28pt 18pt;">

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: top; width: 48%; padding-right: 12pt;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 8pt; font-weight: bold; letter-spacing: 1.2pt; color: {color_indigo}; padding-bottom: 8pt;">
                        BILL FROM:
                    </td></tr>
                    <tr><td style="font-size: 11pt; font-weight: bold; color: {color_header_bg}; padding-bottom: 6pt;">
                        {bill_from_name}
                    </td></tr>
                    {bill_from_address_rows}
                    {bill_from_email_row}
                    {bill_from_pan_row}
                </table>
            </td>
            <td style="vertical-align: top; width: 48%; padding-left: 12pt;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 8pt; font-weight: bold; letter-spacing: 1.2pt; color: {color_indigo}; padding-bottom: 8pt;">
                        BILL TO:
                    </td></tr>
                    <tr><td style="font-size: 11pt; font-weight: bold; color: {color_header_bg}; padding-bottom: 6pt;">
                        {bill_to_name}
                    </td></tr>
                    {bill_to_address_rows}
                    {bill_to_gstin_row}
                    {bill_to_email_row}
                </table>
            </td>
        </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 12pt; line-height: 12pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0" style="border: 1px solid {color_table_border};">
        <tr style="background-color: {color_table_header_bg};">
            <td style="padding: 8pt; font-size: 8pt; font-weight: bold; letter-spacing: 0.5pt; color: {color_header_bg}; border-bottom: 2px solid {color_gold}; width: 52%;">Description</td>
            <td style="padding: 8pt; font-size: 8pt; font-weight: bold; letter-spacing: 0.5pt; color: {color_header_bg}; border-bottom: 2px solid {color_gold}; width: 16%;">Rate</td>
            <td style="padding: 8pt; font-size: 8pt; font-weight: bold; letter-spacing: 0.5pt; color: {color_header_bg}; border-bottom: 2px solid {color_gold}; width: 16%;">Quantity</td>
            <td align="right" style="padding: 8pt; font-size: 8pt; font-weight: bold; letter-spacing: 0.5pt; color: {color_header_bg}; border-bottom: 2px solid {color_gold}; width: 16%; text-align: right;">Amount</td>
        </tr>
        {line_items_rows}
        </table>

        <table width="100%"><tr><td style="font-size: 8pt; line-height: 8pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: top; width: 55%;">&nbsp;</td>
            <td style="vertical-align: top; width: 45%;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr>
                        <td style="font-size: 9pt; color: {color_muted}; padding: 5pt 0;">Total in (USD)</td>
                        <td align="right" style="font-size: 9.5pt; font-weight: bold; color: {color_purple}; padding: 5pt 0; text-align: right;">{total_usd}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 9pt; color: {color_muted}; padding: 5pt 0; vertical-align: top;">Total in (INR)<br/>
                            <span style="font-size: 7.5pt; color: #94a3b8;">Exchange rate:<br/>1 USD = {exchange_rate} INR</span>
                        </td>
                        <td align="right" style="font-size: 11pt; font-weight: bold; color: {color_purple}; padding: 5pt 0; text-align: right; vertical-align: top;">{total_inr}</td>
                    </tr>
                </table>
            </td>
        </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 6pt; line-height: 6pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="font-size: 8.5pt; color: {color_muted};">
                Amount in words : <span style="color: {color_header_bg}; font-weight: bold;">{amount_in_words}</span>
            </td>
        </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 14pt; line-height: 14pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: top; width: 52%;">&nbsp;</td>
            <td align="right" style="vertical-align: top; text-align: right; width: 48%;">
                <table cellspacing="0" cellpadding="0" align="right" style="border: 2px solid {color_gold}; background-color: #fffdf5;">
                    <tr>
                        <td align="center" style="padding: 11pt 22pt; text-align: center;">
                            <table cellspacing="0" cellpadding="0" align="center">
                                <tr><td align="center" style="font-size: 8pt; font-weight: bold; letter-spacing: 1.5pt; color: {color_gold}; text-align: center; padding-bottom: 5pt;">
                                    TOTAL DUE
                                </td></tr>
                                <tr><td align="center" style="font-size: 15pt; font-weight: bold; color: {color_header_bg}; text-align: center;">
                                    INR {total_inr_due}
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 18pt; line-height: 18pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: bottom;">
                <table cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 8.5pt; color: {color_muted}; padding-bottom: 24pt;">For: {signature_name}</td></tr>
                    <tr><td style="font-size: 10.5pt; font-weight: bold; color: {color_header_bg}; border-top: 1px solid {color_gold}; padding-top: 6pt; min-width: 180pt;">
                        {signature_name}
                    </td></tr>
                </table>
            </td>
        </tr>
        </table>

    </td></tr>
    </table>

    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-top: 1px solid #edf2f7;">
    <tr><td align="center" style="padding: 9pt 28pt; text-align: center; font-size: 7pt; color: #a0aec0;">
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

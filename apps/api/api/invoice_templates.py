"""
HTML source for tax invoice PDFs (xhtml2pdf).
Visual system aligned with participation certificate PDFs (navy, gold, purple).
Vendor details come from the invoice form — no platform branding.
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
<tr><td style="padding: 20pt 24pt 24pt;">

<table width="100%" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
<tr><td>

    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: {color_header_bg};">
    <tr><td style="padding: 24pt 32pt 22pt;">
        <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td style="vertical-align: top; width: 58%;">
                    <table cellspacing="0" cellpadding="0">
                        <tr><td style="font-size: 7.5pt; letter-spacing: 3pt; color: {color_gold}; font-weight: bold; padding-bottom: 4pt;">
                            INVOICE
                        </td></tr>
                        <tr><td style="font-size: 18pt; font-weight: bold; color: {color_header_text}; padding-bottom: 10pt;">
                            {bill_from_name}
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
                            <td style="font-size: 8pt; letter-spacing: 1pt; color: {color_header_label}; padding-right: 10pt; text-align: right;">Invoice #</td>
                            <td style="font-size: 9pt; font-weight: bold; color: {color_header_text}; text-align: right;">{invoice_number}</td>
                        </tr>
                        <tr>
                            <td style="font-size: 8pt; letter-spacing: 1pt; color: {color_header_label}; padding-right: 10pt; padding-top: 5pt; text-align: right;">Invoice date</td>
                            <td style="font-size: 9pt; font-weight: bold; color: {color_header_text}; padding-top: 5pt; text-align: right;">{invoice_date}</td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td></tr>
    </table>

    <table width="100%">
    <tr><td style="padding: 22pt 32pt 24pt;">

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: top; width: 48%; padding-right: 10pt;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 7.5pt; font-weight: bold; letter-spacing: 2pt; color: {color_indigo}; padding-bottom: 8pt;">
                        BILL FROM
                    </td></tr>
                    <tr><td style="font-size: 10.5pt; font-weight: bold; color: #1a202c; padding-bottom: 5pt;">
                        {bill_from_name}
                    </td></tr>
                    {bill_from_address_rows}
                    {bill_from_email_row}
                    {bill_from_pan_row}
                </table>
            </td>
            <td style="vertical-align: top; width: 48%; padding-left: 10pt;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 7.5pt; font-weight: bold; letter-spacing: 2pt; color: {color_indigo}; padding-bottom: 8pt;">
                        BILL TO
                    </td></tr>
                    <tr><td style="font-size: 10.5pt; font-weight: bold; color: #1a202c; padding-bottom: 5pt;">
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

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr style="background-color: {color_table_header_bg};">
            <td style="padding: 8pt 10pt; font-size: 7.5pt; font-weight: bold; letter-spacing: 1pt; color: {color_indigo}; border-top: 1px solid {color_table_border}; border-bottom: 1px solid {color_table_border}; width: 52%;">DESCRIPTION</td>
            <td style="padding: 8pt 10pt; font-size: 7.5pt; font-weight: bold; letter-spacing: 1pt; color: {color_indigo}; border-top: 1px solid {color_table_border}; border-bottom: 1px solid {color_table_border}; width: 16%;">RATE</td>
            <td style="padding: 8pt 10pt; font-size: 7.5pt; font-weight: bold; letter-spacing: 1pt; color: {color_indigo}; border-top: 1px solid {color_table_border}; border-bottom: 1px solid {color_table_border}; width: 16%;">QTY</td>
            <td align="right" style="padding: 8pt 10pt; font-size: 7.5pt; font-weight: bold; letter-spacing: 1pt; color: {color_indigo}; border-top: 1px solid {color_table_border}; border-bottom: 1px solid {color_table_border}; width: 16%; text-align: right;">AMOUNT</td>
        </tr>
        {line_items_rows}
        </table>

        <table width="60%" align="center" cellspacing="0" cellpadding="0"><tr>
            <td style="border-top: 2px solid {color_gold}; font-size: 1pt; padding-top: 14pt;">&nbsp;</td>
        </tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: top; width: 52%; padding-top: 8pt;">
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 7.5pt; letter-spacing: 1.5pt; color: {color_indigo}; padding-bottom: 4pt;">AMOUNT IN WORDS</td></tr>
                    <tr><td style="font-size: 9pt; font-weight: bold; color: #1a202c; line-height: 1.45;">{amount_in_words}</td></tr>
                </table>
            </td>
            <td style="vertical-align: top; width: 48%; padding-top: 8pt;">
                <table width="100%" cellspacing="0" cellpadding="0" style="border-top: 1px solid {color_table_border}; border-bottom: 1px solid {color_table_border};">
                    <tr>
                        <td style="font-size: 8.5pt; color: {color_muted}; padding: 8pt 10pt;">Total (USD)</td>
                        <td align="right" style="font-size: 9.5pt; font-weight: bold; color: {color_purple}; padding: 8pt 10pt; text-align: right;">{total_usd}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 8.5pt; color: {color_muted}; padding: 8pt 10pt; vertical-align: top;">
                            Total (INR)<br/>
                            <span style="font-size: 7pt; color: {color_indigo};">1 USD = {exchange_rate} INR</span>
                        </td>
                        <td align="right" style="font-size: 11pt; font-weight: bold; color: {color_purple}; padding: 8pt 10pt; text-align: right; vertical-align: top;">{total_inr}</td>
                    </tr>
                </table>
            </td>
        </tr>
        </table>

        <table width="100%"><tr><td style="font-size: 16pt; line-height: 16pt;">&nbsp;</td></tr></table>

        <table width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td style="vertical-align: bottom; width: 48%;">
                <table cellspacing="0" cellpadding="0">
                    <tr><td style="font-size: 8pt; letter-spacing: 1pt; color: {color_indigo}; padding-bottom: 26pt;">AUTHORIZED SIGNATORY</td></tr>
                    <tr><td style="font-size: 10pt; font-weight: bold; color: #1a202c; border-top: 1px solid {color_gold}; padding-top: 6pt; min-width: 180pt;">
                        {signature_name}
                    </td></tr>
                </table>
            </td>
            <td align="right" style="vertical-align: bottom; text-align: right; width: 52%;">
                <table cellspacing="0" cellpadding="0" align="right" style="border: 2px solid {color_gold}; background-color: {color_due_bg};">
                    <tr>
                        <td align="center" style="padding: 11pt 22pt; text-align: center;">
                            <table cellspacing="0" cellpadding="0" align="center">
                                <tr><td align="center" style="font-size: 7.5pt; font-weight: bold; letter-spacing: 2pt; color: {color_gold}; text-align: center; padding-bottom: 4pt;">
                                    TOTAL DUE
                                </td></tr>
                                <tr><td align="center" style="font-size: 14pt; font-weight: bold; color: {color_header_bg}; text-align: center;">
                                    INR {total_inr_due}
                                </td></tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        </table>

    </td></tr>
    </table>

    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: {color_footer_bg}; border-top: 1px solid {color_table_border};">
    <tr><td align="center" style="padding: 9pt 32pt; text-align: center; font-size: 7pt; color: {color_indigo};">
        Invoice {invoice_number} &nbsp;&middot;&nbsp; {invoice_date}
    </td></tr>
    </table>

</td></tr>
</table>

</td></tr>
</table>

</body>
</html>
"""

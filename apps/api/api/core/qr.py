"""
QR code generation utility.

Generates QR codes as base64-encoded PNG data URIs for embedding in
certificate PDFs, viewer pages, and email templates.
"""

import base64
from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage


def generate_qr_data_uri(url: str) -> str:
    """Generate a QR code as a base64-encoded PNG data URI.

    The QR code uses error correction level M (15% recovery) and
    a compact 4px box size suitable for certificate embedding.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"

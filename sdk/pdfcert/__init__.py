"""PDF Cert Generator API — Python SDK (aligned with API v2.0.0)."""

from pdfcert.client import Admin, PdfCert
from pdfcert.exceptions import (
    AuthenticationError,
    PdfCertError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    "Admin",
    "AuthenticationError",
    "PdfCert",
    "PdfCertError",
    "RateLimitError",
    "ValidationError",
]

__version__ = "2.0.0"

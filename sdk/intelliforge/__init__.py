"""IntelliForge Certificate API — Python SDK (aligned with API v2.0.0)."""

from intelliforge.client import Admin, IntelliForge
from intelliforge.exceptions import (
    AuthenticationError,
    IntelliForgeError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    "Admin",
    "AuthenticationError",
    "IntelliForge",
    "IntelliForgeError",
    "RateLimitError",
    "ValidationError",
]

__version__ = "2.0.0"

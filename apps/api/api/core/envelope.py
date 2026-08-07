"""
Canonical API Response Envelope for CertForge.

All API endpoints return this shape:
{
    "success": bool,
    "data": T | null,
    "error": { "code": int, "message": str, "type": str, "details": any } | null,
    "meta": { ... } | null
}
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiError(BaseModel):
    """Structured error detail inside the envelope."""

    code: int
    message: str
    type: str = "api_error"
    details: Optional[Any] = None


class ApiResponse(BaseModel, Generic[T]):
    """Canonical API response wrapper used by all CertForge endpoints."""

    success: bool = True
    data: Optional[T] = None
    error: Optional[ApiError] = None
    meta: Optional[dict[str, Any]] = None

    @classmethod
    def ok(cls, data: T, meta: Optional[dict[str, Any]] = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None, meta=meta)

    @classmethod
    def fail(
        cls,
        message: str,
        code: int = 400,
        error_type: str = "validation_error",
        details: Optional[Any] = None,
    ) -> "ApiResponse":
        return cls(
            success=False,
            data=None,
            error=ApiError(code=code, message=message, type=error_type, details=details),
            meta=None,
        )


def error_type_for_status(status_code: int) -> str:
    """Map HTTP status codes to error type strings."""
    mapping = {
        400: "validation_error",
        401: "authentication_error",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        503: "service_unavailable",
    }
    if status_code in mapping:
        return mapping[status_code]
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "internal_error"
    return "error"

"""Exceptions raised by the IntelliForge SDK."""


class IntelliForgeError(Exception):
    """Base exception for all IntelliForge API errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(IntelliForgeError):
    """Raised when the API rejects credentials (401 / 403)."""


class RateLimitError(IntelliForgeError):
    """Raised when the API rate limit is exceeded (429)."""


class ValidationError(IntelliForgeError):
    """Raised when the request payload or parameters are invalid (400 / 422)."""

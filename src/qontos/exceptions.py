"""QONTOS SDK exceptions.

Hierarchy::

    QontosError
    +-- AuthenticationError      (401)
    +-- ForbiddenError           (403)
    +-- NotFoundError            (404)
    +-- ValidationError          (422)
    +-- RateLimitError           (429)
    +-- ServerError              (500+)
    +-- TimeoutError             (request timeout)
    +-- CircuitError             (invalid circuit)
"""

from __future__ import annotations


class QontosError(Exception):
    """Base exception for all QONTOS SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: dict | None = None,
        request_id: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.response_body = response_body or {}
        self.request_id = request_id
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"[HTTP {self.status_code}]")
        if self.request_id:
            parts.append(f"(request_id={self.request_id})")
        return " ".join(parts)


class AuthenticationError(QontosError):
    """Raised when the API key is missing, invalid, or expired (HTTP 401)."""
    pass


class ForbiddenError(QontosError):
    """Raised when the authenticated user lacks permission (HTTP 403)."""
    pass


class NotFoundError(QontosError):
    """Raised when the requested resource does not exist (HTTP 404)."""
    pass


class ValidationError(QontosError):
    """Raised when the request payload fails server-side validation (HTTP 422)."""

    def __init__(self, message: str, *, errors: list[dict] | None = None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(message, **kwargs)
        self.errors = errors or []


class RateLimitError(QontosError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(QontosError):
    """Raised for server-side errors (HTTP 5xx)."""
    pass


class TimeoutError(QontosError):
    """Raised when a request or polling operation times out."""
    pass


class CircuitError(QontosError):
    """Raised when a circuit is malformed or unsupported."""
    pass

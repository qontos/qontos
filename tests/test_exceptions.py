"""Tests for QONTOS exception hierarchy."""

from qontos.exceptions import (
    QontosError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    ServerError,
    TimeoutError,
    CircuitError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_qontos_error(self):
        for exc_cls in [
            AuthenticationError,
            ForbiddenError,
            NotFoundError,
            RateLimitError,
            ValidationError,
            ServerError,
            TimeoutError,
            CircuitError,
        ]:
            assert issubclass(exc_cls, QontosError)

    def test_qontos_error_attributes(self):
        err = QontosError(
            "test error",
            status_code=500,
            response_body={"detail": "internal"},
            request_id="req_abc123",
        )
        assert err.message == "test error"
        assert err.status_code == 500
        assert err.request_id == "req_abc123"
        assert "req_abc123" in str(err)

    def test_rate_limit_retry_after(self):
        err = RateLimitError("slow down", retry_after=30.0, status_code=429)
        assert err.retry_after == 30.0

    def test_validation_error_details(self):
        err = ValidationError(
            "invalid circuit",
            errors=[{"field": "circuit", "message": "empty"}],
            status_code=422,
        )
        assert len(err.errors) == 1
        assert err.errors[0]["field"] == "circuit"

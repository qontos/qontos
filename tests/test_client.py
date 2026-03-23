"""Behavioral tests for QontosClient and QontosConfig.

Tests configuration, client initialization, and exception hierarchy
without making real HTTP calls.
"""

from __future__ import annotations

import pytest

from qontos.client import QontosClient, QontosConfig, _DEFAULT_BASE_URL, _DEFAULT_TIMEOUT
from qontos.exceptions import (
    QontosError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
    RateLimitError,
    ServerError,
    TimeoutError,
    CircuitError,
)


# ---------------------------------------------------------------------------
# QontosConfig tests
# ---------------------------------------------------------------------------

class TestQontosConfig:
    """Test configuration creation and defaults."""

    def test_default_config(self) -> None:
        cfg = QontosConfig()
        assert cfg.api_key == ""
        assert cfg.base_url == _DEFAULT_BASE_URL
        assert cfg.timeout == _DEFAULT_TIMEOUT
        assert cfg.max_retries == 3
        assert cfg.api_version == "v1"
        assert cfg.extra_headers == {}

    def test_config_with_api_key(self) -> None:
        cfg = QontosConfig(api_key="qontos_sk_test_123")
        assert cfg.api_key == "qontos_sk_test_123"

    def test_config_with_custom_base_url(self) -> None:
        cfg = QontosConfig(base_url="https://staging.qontos.io")
        assert cfg.base_url == "https://staging.qontos.io"

    def test_config_with_custom_timeout(self) -> None:
        cfg = QontosConfig(timeout=30.0)
        assert cfg.timeout == 30.0

    def test_config_with_custom_retries(self) -> None:
        cfg = QontosConfig(max_retries=5)
        assert cfg.max_retries == 5

    def test_config_with_extra_headers(self) -> None:
        cfg = QontosConfig(extra_headers={"X-Custom": "value"})
        assert cfg.extra_headers == {"X-Custom": "value"}

    def test_config_is_frozen(self) -> None:
        cfg = QontosConfig(api_key="key")
        with pytest.raises(AttributeError):
            cfg.api_key = "new_key"  # type: ignore[misc]

    def test_config_with_api_version(self) -> None:
        cfg = QontosConfig(api_version="v2")
        assert cfg.api_version == "v2"


# ---------------------------------------------------------------------------
# QontosClient initialization tests
# ---------------------------------------------------------------------------

class TestQontosClientInit:
    """Test client construction and defaults."""

    def test_client_with_api_key(self) -> None:
        client = QontosClient(api_key="qontos_sk_test")
        assert client._cfg.api_key == "qontos_sk_test"
        client.close()

    def test_client_with_config(self) -> None:
        cfg = QontosConfig(api_key="sk_from_config", base_url="https://custom.api.io")
        client = QontosClient(config=cfg)
        assert client._cfg.api_key == "sk_from_config"
        assert "custom.api.io" in client._base
        client.close()

    def test_client_config_overrides_kwargs(self) -> None:
        """When config is provided, api_key/base_url kwargs are ignored."""
        cfg = QontosConfig(api_key="from_config")
        client = QontosClient(api_key="from_kwarg", config=cfg)
        assert client._cfg.api_key == "from_config"
        client.close()

    def test_client_base_url_construction(self) -> None:
        client = QontosClient(base_url="https://api.example.com")
        assert client._base == "https://api.example.com/api/v1"
        client.close()

    def test_client_strips_trailing_slash(self) -> None:
        client = QontosClient(base_url="https://api.example.com/")
        assert "//" not in client._base.replace("https://", "")
        client.close()

    def test_client_repr(self) -> None:
        client = QontosClient(base_url="https://api.test.io")
        r = repr(client)
        assert "QontosClient" in r
        assert "api.test.io" in r
        client.close()

    def test_client_context_manager(self) -> None:
        with QontosClient(api_key="test") as client:
            assert isinstance(client, QontosClient)
        # After context exit, client should be closed (no exception)

    def test_client_default_headers_include_user_agent(self) -> None:
        client = QontosClient(api_key="test")
        headers = client._default_headers()
        assert "User-Agent" in headers
        assert "qontos-python" in headers["User-Agent"]
        client.close()

    def test_client_default_headers_include_auth(self) -> None:
        client = QontosClient(api_key="sk_test_key")
        headers = client._default_headers()
        assert headers["Authorization"] == "Bearer sk_test_key"
        client.close()

    def test_client_no_auth_header_without_key(self) -> None:
        client = QontosClient()
        headers = client._default_headers()
        assert "Authorization" not in headers
        client.close()

    def test_client_extra_headers_included(self) -> None:
        cfg = QontosConfig(
            api_key="test",
            extra_headers={"X-Trace-Id": "abc123"},
        )
        client = QontosClient(config=cfg)
        headers = client._default_headers()
        assert headers["X-Trace-Id"] == "abc123"
        client.close()


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:
    """Verify the exception hierarchy and attributes."""

    def test_all_exceptions_inherit_from_qontos_error(self) -> None:
        exceptions = [
            AuthenticationError,
            ForbiddenError,
            NotFoundError,
            ValidationError,
            RateLimitError,
            ServerError,
            TimeoutError,
            CircuitError,
        ]
        for exc_cls in exceptions:
            assert issubclass(exc_cls, QontosError)

    def test_qontos_error_attributes(self) -> None:
        err = QontosError(
            "test error",
            status_code=500,
            response_body={"detail": "oops"},
            request_id="req-123",
        )
        assert err.message == "test error"
        assert err.status_code == 500
        assert err.response_body == {"detail": "oops"}
        assert err.request_id == "req-123"

    def test_qontos_error_str_format(self) -> None:
        err = QontosError("bad request", status_code=400, request_id="r-1")
        s = str(err)
        assert "bad request" in s
        assert "400" in s
        assert "r-1" in s

    def test_validation_error_has_errors_list(self) -> None:
        err = ValidationError(
            "invalid",
            errors=[{"field": "shots", "msg": "must be positive"}],
            status_code=422,
        )
        assert len(err.errors) == 1
        assert err.errors[0]["field"] == "shots"

    def test_rate_limit_error_has_retry_after(self) -> None:
        err = RateLimitError("slow down", retry_after=30.0, status_code=429)
        assert err.retry_after == 30.0

    def test_rate_limit_error_no_retry_after(self) -> None:
        err = RateLimitError("slow down", status_code=429)
        assert err.retry_after is None

    def test_qontos_error_default_response_body(self) -> None:
        err = QontosError("msg")
        assert err.response_body == {}

    def test_qontos_error_default_status_code(self) -> None:
        err = QontosError("msg")
        assert err.status_code is None

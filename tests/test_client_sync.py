"""QGH-3003: Sync QontosClient reliability tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from qontos.client import QontosClient, QontosConfig, _raise_for_status
from qontos.exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    QontosError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: dict | None = None, headers: dict | None = None) -> httpx.Response:
    """Create a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=body or {},
        headers=headers or {},
        request=httpx.Request("GET", "https://api.qontos.io/api/v1/test"),
    )
    return resp


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestClientInit:
    def test_init_with_api_key_and_base_url(self):
        client = QontosClient(api_key="sk-test", base_url="https://custom.api.io")
        assert client._cfg.api_key == "sk-test"
        assert "custom.api.io" in client._cfg.base_url
        client.close()

    def test_init_with_config_object(self):
        cfg = QontosConfig(api_key="sk-cfg", base_url="https://cfg.api.io", timeout=30.0)
        client = QontosClient(config=cfg)
        assert client._cfg.api_key == "sk-cfg"
        assert client._cfg.timeout == 30.0
        client.close()

    def test_init_default_base_url(self):
        client = QontosClient(api_key="sk-test")
        assert "api.qontos.io" in client._cfg.base_url
        client.close()

    def test_repr(self):
        client = QontosClient(api_key="sk-test")
        assert "QontosClient" in repr(client)
        client.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self):
        client = QontosClient(api_key="sk-test")
        assert client.__enter__() is client
        client.__exit__(None, None, None)

    def test_context_manager_protocol(self):
        with QontosClient(api_key="sk-test") as client:
            assert isinstance(client, QontosClient)
        # After exiting, the client should be closed (http pool closed)
        assert client._http.is_closed


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------


class TestSubmitJob:
    @patch.object(QontosClient, "_post")
    def test_submit_job_creates_proper_request(self, mock_post):
        mock_post.return_value = {
            "id": "job-001",
            "status": "queued",
            "num_qubits": 2,
            "shots": 4096,
        }
        client = QontosClient(api_key="sk-test")
        job = client.submit_job(circuit="OPENQASM 2.0;", shots=4096)
        assert job.id == "job-001"
        assert job.status == "queued"
        call_args = mock_post.call_args
        assert call_args[0][0] == "/jobs"
        payload = call_args[0][1]
        assert payload["circuit_source"] == "OPENQASM 2.0;"
        assert payload["shots"] == 4096
        client.close()

    @patch.object(QontosClient, "_post")
    def test_submit_job_with_constraints(self, mock_post):
        mock_post.return_value = {"id": "job-002", "status": "queued"}
        client = QontosClient(api_key="sk-test")
        job = client.submit_job(
            circuit="OPENQASM 2.0;",
            constraints={"preferred_backends": ["ibm-lagos"]},
            name="my-job",
            project_id="proj-1",
            priority=1,
            tags={"env": "test"},
        )
        payload = mock_post.call_args[0][1]
        assert payload["constraints"] == {"preferred_backends": ["ibm-lagos"]}
        assert payload["name"] == "my-job"
        assert payload["project_id"] == "proj-1"
        assert payload["priority"] == 1
        assert payload["tags"] == {"env": "test"}
        client.close()


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------


class TestGetJob:
    @patch.object(QontosClient, "_get")
    def test_get_job_returns_typed_result(self, mock_get):
        mock_get.return_value = {
            "id": "job-001",
            "status": "completed",
            "num_qubits": 4,
            "shots": 4096,
        }
        client = QontosClient(api_key="sk-test")
        job = client.get_job("job-001")
        assert job.id == "job-001"
        assert job.status == "completed"
        client.close()


# ---------------------------------------------------------------------------
# get_results / get_proof
# ---------------------------------------------------------------------------


class TestRunResults:
    @patch.object(QontosClient, "_get")
    def test_get_results_returns_run_result(self, mock_get):
        mock_get.return_value = {
            "id": "result-001",
            "run_id": "run-001",
            "counts": {"00": 2048, "11": 2048},
            "total_shots": 4096,
        }
        client = QontosClient(api_key="sk-test")
        result = client.get_results("run-001")
        assert result.counts == {"00": 2048, "11": 2048}
        assert result.total_shots == 4096
        client.close()

    @patch.object(QontosClient, "_get")
    def test_get_proof_returns_execution_proof(self, mock_get):
        mock_get.return_value = {
            "run_id": "run-001",
            "proof_hash": "sha256_abc123",
            "verifiable": True,
        }
        client = QontosClient(api_key="sk-test")
        proof = client.get_proof("run-001")
        assert proof.proof_hash == "sha256_abc123"
        assert proof.verifiable is True
        client.close()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_401_raises_authentication_error(self):
        resp = _mock_response(401, {"detail": "Invalid API key"})
        with pytest.raises(AuthenticationError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.status_code == 401

    def test_403_raises_forbidden_error(self):
        resp = _mock_response(403, {"detail": "Forbidden"})
        with pytest.raises(ForbiddenError):
            _raise_for_status(resp)

    def test_404_raises_not_found_error(self):
        resp = _mock_response(404, {"detail": "Not found"})
        with pytest.raises(NotFoundError):
            _raise_for_status(resp)

    def test_422_raises_validation_error_with_errors_list(self):
        resp = _mock_response(422, {"detail": "Invalid", "errors": [{"field": "shots"}]})
        with pytest.raises(ValidationError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.errors == [{"field": "shots"}]

    def test_429_raises_rate_limit_error_with_retry_after(self):
        resp = _mock_response(429, {"detail": "Rate limited"}, {"Retry-After": "5"})
        with pytest.raises(RateLimitError) as exc_info:
            _raise_for_status(resp)
        assert exc_info.value.retry_after == 5.0

    def test_500_raises_server_error(self):
        resp = _mock_response(500, {"detail": "Internal server error"})
        with pytest.raises(ServerError):
            _raise_for_status(resp)

    def test_generic_http_error_raises_qontos_error(self):
        resp = _mock_response(418, {"detail": "I'm a teapot"})
        with pytest.raises(QontosError):
            _raise_for_status(resp)


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    @patch("qontos.client.time.sleep")
    def test_retry_on_server_error(self, mock_sleep):
        """ServerError retries then raises after max_retries."""
        client = QontosClient(api_key="sk-test", config=QontosConfig(api_key="sk-test", max_retries=2))
        error_resp = _mock_response(500, {"detail": "Server error"})
        with patch.object(client._http, "request", return_value=error_resp):
            with pytest.raises(ServerError):
                client._request("GET", "/test")
        assert mock_sleep.call_count >= 1
        client.close()

    @patch("qontos.client.time.sleep")
    def test_retry_on_connect_error_raises_timeout(self, mock_sleep):
        """Connection errors retry then raise TimeoutError."""
        client = QontosClient(config=QontosConfig(api_key="sk-test", max_retries=2))
        with patch.object(client._http, "request", side_effect=httpx.ConnectError("fail")):
            with pytest.raises(TimeoutError, match="failed after"):
                client._request("GET", "/test")
        client.close()


# ---------------------------------------------------------------------------
# Timeout configuration
# ---------------------------------------------------------------------------


class TestTimeoutConfig:
    def test_custom_timeout(self):
        cfg = QontosConfig(api_key="sk-test", timeout=10.0)
        client = QontosClient(config=cfg)
        assert client._cfg.timeout == 10.0
        client.close()

    def test_default_timeout(self):
        client = QontosClient(api_key="sk-test")
        assert client._cfg.timeout == 120.0
        client.close()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_releases_resources(self):
        client = QontosClient(api_key="sk-test")
        assert not client._http.is_closed
        client.close()
        assert client._http.is_closed

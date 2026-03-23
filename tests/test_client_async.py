"""QGH-3003: Async QontosClient reliability tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from qontos.async_client import AsyncQontosClient
from qontos.client import QontosConfig
from qontos.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServerError,
    TimeoutError,
)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestAsyncClientInit:
    def test_init_with_api_key_and_base_url(self):
        client = AsyncQontosClient(api_key="sk-test", base_url="https://custom.api.io")
        assert client._cfg.api_key == "sk-test"
        assert "custom.api.io" in client._cfg.base_url

    def test_init_with_config(self):
        cfg = QontosConfig(api_key="sk-cfg", base_url="https://cfg.api.io", timeout=15.0)
        client = AsyncQontosClient(config=cfg)
        assert client._cfg.timeout == 15.0

    def test_repr(self):
        client = AsyncQontosClient(api_key="sk-test")
        assert "AsyncQontosClient" in repr(client)


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with AsyncQontosClient(api_key="sk-test") as client:
            assert isinstance(client, AsyncQontosClient)
        assert client._http.is_closed

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        client = AsyncQontosClient(api_key="sk-test")
        result = await client.__aenter__()
        assert result is client
        await client.close()


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------


class TestAsyncSubmitJob:
    @pytest.mark.asyncio
    async def test_submit_job_creates_proper_request(self):
        client = AsyncQontosClient(api_key="sk-test")
        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {
                "id": "job-async-001",
                "status": "queued",
            }
            job = await client.submit_job(circuit="OPENQASM 2.0;", shots=2048)
            assert job.id == "job-async-001"
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[0][1]
            assert payload["circuit_source"] == "OPENQASM 2.0;"
            assert payload["shots"] == 2048
        await client.close()


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------


class TestAsyncGetJob:
    @pytest.mark.asyncio
    async def test_get_job_returns_typed(self):
        client = AsyncQontosClient(api_key="sk-test")
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "job-001", "status": "completed"}
            job = await client.get_job("job-001")
            assert job.id == "job-001"
        await client.close()


# ---------------------------------------------------------------------------
# get_results / get_proof
# ---------------------------------------------------------------------------


class TestAsyncResults:
    @pytest.mark.asyncio
    async def test_get_results_returns_run_result(self):
        client = AsyncQontosClient(api_key="sk-test")
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "r-001",
                "run_id": "run-001",
                "counts": {"01": 1024, "10": 3072},
                "total_shots": 4096,
            }
            result = await client.get_results("run-001")
            assert result.total_shots == 4096
            assert "01" in result.counts
        await client.close()

    @pytest.mark.asyncio
    async def test_get_proof_returns_execution_proof(self):
        client = AsyncQontosClient(api_key="sk-test")
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "run_id": "run-001",
                "proof_hash": "sha_proof_001",
                "verifiable": True,
            }
            proof = await client.get_proof("run-001")
            assert proof.proof_hash == "sha_proof_001"
        await client.close()


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------


class TestAsyncClose:
    @pytest.mark.asyncio
    async def test_aclose_releases_resources(self):
        client = AsyncQontosClient(api_key="sk-test")
        assert not client._http.is_closed
        await client.close()
        assert client._http.is_closed


# ---------------------------------------------------------------------------
# Error handling (async)
# ---------------------------------------------------------------------------


class TestAsyncErrorHandling:
    @pytest.mark.asyncio
    async def test_401_raises_authentication_error(self):
        client = AsyncQontosClient(api_key="sk-test")
        error_resp = httpx.Response(
            status_code=401,
            json={"detail": "Bad key"},
            request=httpx.Request("GET", "https://api.qontos.io/api/v1/test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=error_resp):
            with pytest.raises(AuthenticationError):
                await client._request("GET", "/test")
        await client.close()

    @pytest.mark.asyncio
    async def test_500_raises_server_error_after_retries(self):
        cfg = QontosConfig(api_key="sk-test", max_retries=2)
        client = AsyncQontosClient(config=cfg)
        error_resp = httpx.Response(
            status_code=500,
            json={"detail": "Server error"},
            request=httpx.Request("GET", "https://api.qontos.io/api/v1/test"),
        )
        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=error_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ServerError):
                    await client._request("GET", "/test")
        await client.close()


# ---------------------------------------------------------------------------
# Retry behavior (async)
# ---------------------------------------------------------------------------


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_retry_on_connect_error(self):
        cfg = QontosConfig(api_key="sk-test", max_retries=2)
        client = AsyncQontosClient(config=cfg)
        with patch.object(client._http, "request", new_callable=AsyncMock, side_effect=httpx.ConnectError("fail")):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(TimeoutError, match="failed after"):
                    await client._request("GET", "/test")
        await client.close()


# ---------------------------------------------------------------------------
# Concurrent submissions
# ---------------------------------------------------------------------------


class TestConcurrentSubmissions:
    @pytest.mark.asyncio
    async def test_concurrent_job_submissions(self):
        """Multiple concurrent submit_job calls should all succeed."""
        client = AsyncQontosClient(api_key="sk-test")

        call_count = 0

        async def mock_post(path, json=None):
            nonlocal call_count
            call_count += 1
            return {"id": f"job-{call_count:03d}", "status": "queued"}

        with patch.object(client, "_post", side_effect=mock_post):
            tasks = [
                client.submit_job(circuit=f"OPENQASM 2.0; // circuit {i}", shots=4096)
                for i in range(5)
            ]
            results = await asyncio.gather(*tasks)
            assert len(results) == 5
            ids = {r.id for r in results}
            assert len(ids) == 5  # all unique
        await client.close()

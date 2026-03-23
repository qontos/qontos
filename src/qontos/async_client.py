"""QONTOS asynchronous SDK client.

Provides the same interface as :class:`QontosClient` but uses
``httpx.AsyncClient`` for non-blocking I/O, suitable for asyncio
applications and high-throughput batch submissions.

Example::

    import asyncio
    from qontos import AsyncQontosClient

    async def main():
        async with AsyncQontosClient(api_key="qontos_sk_...") as client:
            job = await client.submit_job(circuit="...", shots=4096)
            job = await client.wait_for_job(job.id)
            result = await client.get_results(job.runs[0].id)
            print(result.counts)

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from qontos.client import QontosConfig, _DEFAULT_BASE_URL, _SDK_VERSION, _raise_for_status
from qontos.exceptions import (
    RateLimitError,
    ServerError,
    TimeoutError,
)
from qontos.models import (
    Backend,
    CalibrationData,
    CompiledCircuit,
    ComparisonResult,
    EstimatorResult,
    ExecutionProof,
    Job,
    ResourceEstimate,
    Run,
    RunResult,
    SamplerResult,
    Session,
)

__all__ = ["AsyncQontosClient"]


class AsyncQontosClient:
    """Asynchronous client for the QONTOS quantum orchestration API.

    Parameters
    ----------
    api_key:
        API key (``qontos_sk_...``).
    base_url:
        Root URL of the QONTOS API.
    config:
        Optional :class:`QontosConfig`.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = _DEFAULT_BASE_URL,
        *,
        config: QontosConfig | None = None,
    ) -> None:
        if config is not None:
            self._cfg = config
        else:
            self._cfg = QontosConfig(api_key=api_key, base_url=base_url.rstrip("/"))

        self._base = f"{self._cfg.base_url}/api/{self._cfg.api_version}"
        self._http = httpx.AsyncClient(
            timeout=self._cfg.timeout,
            headers=self._default_headers(),
            follow_redirects=True,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": f"qontos-python/{_SDK_VERSION}",
            "Accept": "application/json",
        }
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"
        headers.update(self._cfg.extra_headers)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = await self._http.request(method, url, json=json, params=params)
                _raise_for_status(resp)
                if resp.status_code == 204:
                    return None
                return resp.json()
            except RateLimitError as exc:
                last_exc = exc
                wait = exc.retry_after if exc.retry_after else 2 ** attempt
                await asyncio.sleep(wait)
            except ServerError as exc:
                last_exc = exc
                if attempt < self._cfg.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self._cfg.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise TimeoutError(
                        f"Request failed after {self._cfg.max_retries} attempts: {exc}"
                    ) from exc

        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json=json or {})

    async def _put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("PUT", path, json=json or {})

    async def _delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # ── Jobs ──────────────────────────────────────────────────────────────

    async def submit_job(
        self,
        circuit: str,
        objective: str = "general",
        shots: int = 4096,
        constraints: dict[str, Any] | None = None,
        *,
        name: str = "",
        project_id: str | None = None,
        priority: int = 5,
        tags: dict[str, Any] | None = None,
    ) -> Job:
        payload: dict[str, Any] = {
            "circuit_source": circuit,
            "objective": objective,
            "shots": shots,
            "num_qubits": 0,
        }
        if name:
            payload["name"] = name
        if project_id:
            payload["project_id"] = project_id
        if constraints:
            payload["constraints"] = constraints
        if priority != 5:
            payload["priority"] = priority
        if tags:
            payload["tags"] = tags
        data = await self._post("/jobs", payload)
        return Job.model_validate(data)

    async def get_job(self, job_id: str) -> Job:
        data = await self._get(f"/jobs/{job_id}")
        return Job.model_validate(data)

    async def list_jobs(
        self,
        project_id: str | None = None,
        status: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status
        data = await self._get("/jobs", params=params)
        items = data if isinstance(data, list) else data.get("items", [])
        return [Job.model_validate(j) for j in items]

    async def cancel_job(self, job_id: str) -> bool:
        await self._post(f"/jobs/{job_id}/cancel")
        return True

    async def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ) -> Job:
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = await self.get_job(job_id)
            if job.status in ("completed", "failed", "cancelled"):
                return job
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    # ── Runs ──────────────────────────────────────────────────────────────

    async def get_run(self, run_id: str) -> Run:
        data = await self._get(f"/runs/{run_id}")
        return Run.model_validate(data)

    async def get_results(self, run_id: str) -> RunResult:
        data = await self._get(f"/runs/{run_id}/results")
        return RunResult.model_validate(data)

    async def get_proof(self, run_id: str) -> ExecutionProof:
        data = await self._get(f"/runs/{run_id}/proof")
        return ExecutionProof.model_validate(data)

    # ── Backends ──────────────────────────────────────────────────────────

    async def list_backends(self) -> list[Backend]:
        data = await self._get("/backends")
        items = data if isinstance(data, list) else data.get("items", [])
        return [Backend.model_validate(b) for b in items]

    async def get_backend(self, backend_id: str) -> Backend:
        data = await self._get(f"/backends/{backend_id}")
        return Backend.model_validate(data)

    async def get_calibration(self, backend_id: str) -> CalibrationData:
        data = await self._get(f"/backends/{backend_id}/calibration")
        return CalibrationData.model_validate(data)

    # ── Sessions ──────────────────────────────────────────────────────────

    async def create_session(
        self,
        backend_id: str,
        *,
        max_execution_time: int = 3600,
    ) -> Session:
        data = await self._post("/sessions", {
            "backend_id": backend_id,
            "max_execution_time": max_execution_time,
        })
        return Session.model_validate(data)

    async def close_session(self, session_id: str) -> None:
        await self._delete(f"/sessions/{session_id}")

    # ── Primitives ────────────────────────────────────────────────────────

    async def sampler(
        self,
        circuits: list[str],
        shots: int = 4096,
        *,
        backend_id: str | None = None,
        session_id: str | None = None,
    ) -> SamplerResult:
        payload: dict[str, Any] = {"circuits": circuits, "shots": shots}
        if backend_id:
            payload["backend_id"] = backend_id
        if session_id:
            payload["session_id"] = session_id
        data = await self._post("/primitives/sampler", payload)
        return SamplerResult.model_validate(data)

    async def estimator(
        self,
        circuits: list[str],
        observables: list[str],
        *,
        backend_id: str | None = None,
        session_id: str | None = None,
    ) -> EstimatorResult:
        payload: dict[str, Any] = {"circuits": circuits, "observables": observables}
        if backend_id:
            payload["backend_id"] = backend_id
        if session_id:
            payload["session_id"] = session_id
        data = await self._post("/primitives/estimator", payload)
        return EstimatorResult.model_validate(data)

    # ── Utilities ─────────────────────────────────────────────────────────

    async def estimate_resources(self, circuit: str) -> ResourceEstimate:
        data = await self._post("/utilities/estimate", {"circuit_source": circuit})
        return ResourceEstimate.model_validate(data)

    async def compile_circuit(
        self,
        circuit: str,
        backend_id: str,
        optimization_level: int = 1,
    ) -> CompiledCircuit:
        data = await self._post("/utilities/compile", {
            "circuit_source": circuit,
            "backend_id": backend_id,
            "optimization_level": optimization_level,
        })
        return CompiledCircuit.model_validate(data)

    # ── Comparison ────────────────────────────────────────────────────────

    async def compare_backends(
        self,
        circuit: str,
        backend_ids: list[str],
    ) -> ComparisonResult:
        data = await self._post("/utilities/compare", {
            "circuit_source": circuit,
            "backend_ids": backend_ids,
        })
        return ComparisonResult.model_validate(data)

    # ── Health ────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncQontosClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncQontosClient(base_url={self._cfg.base_url!r})"

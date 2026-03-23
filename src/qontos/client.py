"""QONTOS synchronous SDK client.

Provides a high-level, typed interface to the QONTOS quantum orchestration
API using ``httpx`` for HTTP transport and Pydantic models for response
parsing.

Example::

    from qontos import QontosClient

    client = QontosClient(api_key="qontos_sk_...")
    job = client.submit_job(
        circuit="OPENQASM 2.0; ...",
        objective="general",
        shots=4096,
    )
    run = job.runs[0]
    result = client.get_results(run.id)
    print(result.counts)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

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
from qontos.sdk_models import (
    Backend,
    CalibrationData,
    CompiledCircuit,
    ComparisonResult,
    EstimatorResult,
    ExecutionMetadata,
    ExecutionProof,
    Job,
    JobOutcomeMetadata,
    JobOutcomeReport,
    ResourceEstimate,
    Run,
    RunResult,
    SamplerResult,
    Session,
)

__all__ = ["QontosClient", "QontosConfig"]

_SDK_VERSION = "0.1.0"
_DEFAULT_BASE_URL = "https://api.qontos.io"
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QontosConfig:
    """Immutable configuration for a :class:`QontosClient`."""

    api_key: str = ""
    base_url: str = _DEFAULT_BASE_URL
    timeout: float = _DEFAULT_TIMEOUT
    max_retries: int = _DEFAULT_MAX_RETRIES
    api_version: str = "v1"
    extra_headers: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

def _raise_for_status(response: httpx.Response) -> None:
    """Map HTTP errors to typed SDK exceptions."""
    if response.is_success:
        return

    request_id = response.headers.get("X-Request-ID")
    try:
        body = response.json()
    except Exception:
        body = {"detail": response.text}

    message = body.get("detail", body.get("message", f"HTTP {response.status_code}"))
    kwargs: dict[str, Any] = {
        "status_code": response.status_code,
        "response_body": body,
        "request_id": request_id,
    }

    if response.status_code == 401:
        raise AuthenticationError(message, **kwargs)
    if response.status_code == 403:
        raise ForbiddenError(message, **kwargs)
    if response.status_code == 404:
        raise NotFoundError(message, **kwargs)
    if response.status_code == 422:
        raise ValidationError(message, errors=body.get("errors"), **kwargs)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise RateLimitError(
            message,
            retry_after=float(retry_after) if retry_after else None,
            **kwargs,
        )
    if response.status_code >= 500:
        raise ServerError(message, **kwargs)

    raise QontosError(message, **kwargs)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class QontosClient:
    """Synchronous client for the QONTOS quantum orchestration API.

    Parameters
    ----------
    api_key:
        API key (``qontos_sk_...``).  Required for authenticated endpoints.
    base_url:
        Root URL of the QONTOS API.  Defaults to ``https://api.qontos.io``.
    config:
        Optional :class:`QontosConfig` instance.  When provided, *api_key*
        and *base_url* are ignored.
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
        self._http = httpx.Client(
            timeout=self._cfg.timeout,
            headers=self._default_headers(),
            follow_redirects=True,
        )

    # -- internal helpers ---------------------------------------------------

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": f"qontos-python/{_SDK_VERSION}",
            "Accept": "application/json",
        }
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"
        headers.update(self._cfg.extra_headers)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request with automatic retries on transient errors."""
        url = f"{self._base}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._http.request(method, url, json=json, params=params)
                _raise_for_status(resp)
                if resp.status_code == 204:
                    return None
                return resp.json()
            except RateLimitError as exc:
                last_exc = exc
                wait = exc.retry_after if exc.retry_after else 2 ** attempt
                time.sleep(wait)
            except ServerError as exc:
                last_exc = exc
                if attempt < self._cfg.max_retries:
                    time.sleep(2 ** attempt)
                else:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self._cfg.max_retries:
                    time.sleep(2 ** attempt)
                else:
                    raise TimeoutError(
                        f"Request failed after {self._cfg.max_retries} attempts: {exc}"
                    ) from exc

        raise last_exc  # type: ignore[misc]

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json or {})

    def _put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json=json or {})

    def _delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ======================================================================
    # Jobs
    # ======================================================================

    def submit_job(
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
        """Submit a quantum job for orchestrated execution.

        Parameters
        ----------
        circuit : str
            QASM string or serialized circuit representation.
        objective : str
            Execution objective (``general``, ``fidelity``, ``speed``, ``cost``).
        shots : int
            Number of measurement shots.
        constraints : dict, optional
            Backend constraints (preferred backends, max cost, etc.).
        """
        payload: dict[str, Any] = {
            "circuit_source": circuit,
            "objective": objective,
            "shots": shots,
            "num_qubits": 0,  # server will infer from circuit
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

        data = self._post("/jobs", payload)
        return Job.model_validate(data)

    def get_job(self, job_id: str) -> Job:
        """Retrieve a job by ID."""
        data = self._get(f"/jobs/{job_id}")
        return Job.model_validate(data)

    def list_jobs(
        self,
        project_id: str | None = None,
        status: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status
        data = self._get("/jobs", params=params)
        items = data if isinstance(data, list) else data.get("items", [])
        return [Job.model_validate(j) for j in items]

    def get_job_outcome(self, job_id: str) -> JobOutcomeReport | None:
        """Retrieve the canonical outcome report for a completed/degraded job.

        QNT-506 / QNT-606: Ensures the SDK never hides degradation.
        Handles both legacy and new response formats.

        Returns ``None`` when the API response does not contain an outcome
        report (e.g. the job is still running).
        """
        data = self._get(f"/jobs/{job_id}")
        return JobOutcomeReport.from_api_response(data)

    def get_job_outcome_report(self, job_id: str) -> JobOutcomeReport | None:
        """Alias for :meth:`get_job_outcome` (backward compatibility)."""
        return self.get_job_outcome(job_id)

    @staticmethod
    def parse_outcome_report(api_response: dict[str, Any]) -> JobOutcomeReport | None:
        """Parse a ``JobOutcomeReport`` from a raw API response dict.

        Delegates to ``JobOutcomeReport.from_api_response`` which handles
        both nested (``outcome_report`` key) and flat response shapes.

        Returns ``None`` if the response contains no outcome information.
        """
        return JobOutcomeReport.from_api_response(api_response)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job.  Returns ``True`` on success."""
        self._post(f"/jobs/{job_id}/cancel")
        return True

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ) -> Job:
        """Block until a job reaches a terminal state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job.status in ("completed", "completed_with_failures", "failed", "cancelled"):
                return job
            time.sleep(poll_interval)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    # ======================================================================
    # Runs
    # ======================================================================

    def get_run(self, run_id: str) -> Run:
        """Retrieve a run by ID."""
        data = self._get(f"/runs/{run_id}")
        return Run.model_validate(data)

    def get_results(self, run_id: str) -> RunResult:
        """Retrieve the merged result for a completed run."""
        data = self._get(f"/runs/{run_id}/results")
        return RunResult.model_validate(data)

    def get_proof(self, run_id: str) -> ExecutionProof:
        """Retrieve the cryptographic execution proof for a run."""
        data = self._get(f"/runs/{run_id}/proof")
        return ExecutionProof.model_validate(data)

    # ======================================================================
    # Backends
    # ======================================================================

    def list_backends(self) -> list[Backend]:
        """List all available quantum backends."""
        data = self._get("/backends")
        items = data if isinstance(data, list) else data.get("items", [])
        return [Backend.model_validate(b) for b in items]

    def get_backend(self, backend_id: str) -> Backend:
        """Retrieve details for a specific backend."""
        data = self._get(f"/backends/{backend_id}")
        return Backend.model_validate(data)

    def get_calibration(self, backend_id: str) -> CalibrationData:
        """Retrieve the latest calibration data for a backend."""
        data = self._get(f"/backends/{backend_id}/calibration")
        return CalibrationData.model_validate(data)

    # ======================================================================
    # Sessions
    # ======================================================================

    def create_session(
        self,
        backend_id: str,
        *,
        max_execution_time: int = 3600,
    ) -> Session:
        """Create an interactive session on a specific backend."""
        data = self._post("/sessions", {
            "backend_id": backend_id,
            "max_execution_time": max_execution_time,
        })
        return Session.model_validate(data)

    def close_session(self, session_id: str) -> None:
        """Close an active session."""
        self._delete(f"/sessions/{session_id}")

    # ======================================================================
    # Primitives (IBM Qiskit Runtime-style)
    # ======================================================================

    def sampler(
        self,
        circuits: list[str],
        shots: int = 4096,
        *,
        backend_id: str | None = None,
        session_id: str | None = None,
    ) -> SamplerResult:
        """Run the Sampler primitive on one or more circuits."""
        payload: dict[str, Any] = {"circuits": circuits, "shots": shots}
        if backend_id:
            payload["backend_id"] = backend_id
        if session_id:
            payload["session_id"] = session_id
        data = self._post("/primitives/sampler", payload)
        return SamplerResult.model_validate(data)

    def estimator(
        self,
        circuits: list[str],
        observables: list[str],
        *,
        backend_id: str | None = None,
        session_id: str | None = None,
    ) -> EstimatorResult:
        """Run the Estimator primitive on circuits with observables."""
        payload: dict[str, Any] = {
            "circuits": circuits,
            "observables": observables,
        }
        if backend_id:
            payload["backend_id"] = backend_id
        if session_id:
            payload["session_id"] = session_id
        data = self._post("/primitives/estimator", payload)
        return EstimatorResult.model_validate(data)

    # ======================================================================
    # Utilities
    # ======================================================================

    def estimate_resources(self, circuit: str) -> ResourceEstimate:
        """Estimate the resources required to execute a circuit."""
        data = self._post("/utilities/estimate", {"circuit_source": circuit})
        return ResourceEstimate.model_validate(data)

    def compile_circuit(
        self,
        circuit: str,
        backend_id: str,
        optimization_level: int = 1,
    ) -> CompiledCircuit:
        """Compile a circuit for a specific backend."""
        data = self._post("/utilities/compile", {
            "circuit_source": circuit,
            "backend_id": backend_id,
            "optimization_level": optimization_level,
        })
        return CompiledCircuit.model_validate(data)

    # ======================================================================
    # Comparison
    # ======================================================================

    def compare_backends(
        self,
        circuit: str,
        backend_ids: list[str],
    ) -> ComparisonResult:
        """Compare estimated performance of a circuit across backends."""
        data = self._post("/utilities/compare", {
            "circuit_source": circuit,
            "backend_ids": backend_ids,
        })
        return ComparisonResult.model_validate(data)

    # ======================================================================
    # Health / info
    # ======================================================================

    def health(self) -> dict[str, Any]:
        """Check API health status."""
        return self._get("/health")

    def info(self) -> dict[str, Any]:
        """Retrieve platform information and version."""
        return self._request("GET", "/../")

    # ======================================================================
    # Lifecycle
    # ======================================================================

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> QontosClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"QontosClient(base_url={self._cfg.base_url!r})"

"""QONTOS SDK response models.

All models use Pydantic v2 for automatic validation, serialization, and
JSON Schema generation.  Fields use ``None`` defaults for optional data
that the API may omit depending on job state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Nested / shared models
# ---------------------------------------------------------------------------

class Partition(BaseModel):
    """A single partition of a distributed quantum circuit."""

    id: str
    partition_index: int
    num_qubits: int
    gate_count: int = 0
    depth: int = 0
    status: str = "pending"
    backend_id: str | None = None
    qubit_mapping: dict[str, Any] | None = None


class RunMetrics(BaseModel):
    """Aggregate metrics for a single run."""

    total_shots: int = 0
    fidelity_estimate: float | None = None
    cost_usd: float = 0.0
    latency_ms: float | None = None
    aggregation_method: str = "passthrough"


class ProviderSubmission(BaseModel):
    """Record of a submission to a quantum provider."""

    id: str
    provider: str
    provider_job_id: str | None = None
    submitted_at: datetime | None = None
    status: str = "submitted"


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------

class Run(BaseModel):
    """A single execution run within a job."""

    id: str
    job_id: str
    status: str = "created"
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    partitions: list[Partition] = Field(default_factory=list)
    metrics: RunMetrics | None = None


class JobOutcomeReport(BaseModel):
    """QNT-506 / QNT-606: Canonical outcome report for a job execution.

    Parsed from the API response so the SDK never hides degradation.
    Fields match ``packages.schemas.job_outcome.JobOutcomeReport`` exactly.
    """

    outcome: str = "pending"
    total_partitions: int = 0
    completed_partitions: int = 0
    failed_partitions: int = 0
    failed_partition_ids: list[str] = Field(default_factory=list)
    missing_partition_ids: list[str] = Field(default_factory=list)
    degradation_reason: str | None = None
    enriched_at: str | None = None
    enrichment_stage: str | None = None

    CANONICAL_FIELDS: ClassVar[list[str]] = [
        "outcome",
        "total_partitions",
        "completed_partitions",
        "failed_partitions",
        "failed_partition_ids",
        "missing_partition_ids",
        "degradation_reason",
    ]

    @model_validator(mode="after")
    def _derive_completed(self) -> "JobOutcomeReport":
        """QNT-1002: completed_partitions is always derived, never authoritative."""
        derived = (
            self.total_partitions
            - self.failed_partitions
            - len(self.missing_partition_ids)
        )
        object.__setattr__(self, "completed_partitions", max(derived, 0))
        return self

    @property
    def is_success(self) -> bool:
        return self.outcome == "completed"

    @property
    def is_degraded(self) -> bool:
        return self.outcome == "completed_with_failures"

    @property
    def is_failed(self) -> bool:
        return self.outcome == "failed"

    @property
    def has_missing_partitions(self) -> bool:
        return len(self.missing_partition_ids) > 0

    @property
    def is_terminal(self) -> bool:
        return self.outcome in (
            "completed",
            "completed_with_failures",
            "failed",
            "cancelled",
        )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobOutcomeReport":
        return cls.model_validate(data)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "JobOutcomeReport | None":
        """Construct from an API response, handling nested and flat formats.

        Returns ``None`` if the response contains no outcome information.
        """
        if not isinstance(data, dict):
            return None

        # Nested form (preferred): look for "outcome_report" key
        nested = data.get("outcome_report")
        if isinstance(nested, dict):
            return cls.model_validate(nested)

        # Flat form: synthesize from top-level keys
        outcome = data.get("outcome") or data.get("status")
        if outcome and outcome in (
            "completed", "completed_with_failures", "failed", "cancelled",
            "pending", "running",
        ):
            return cls(
                outcome=outcome,
                total_partitions=data.get("total_partitions", 0),
                completed_partitions=data.get("completed_partitions", 0),
                failed_partitions=data.get("failed_partitions", 0),
                failed_partition_ids=data.get("failed_partition_ids", []),
                missing_partition_ids=data.get("missing_partition_ids", []),
                degradation_reason=data.get("degradation_reason"),
                enriched_at=data.get("enriched_at"),
                enrichment_stage=data.get("enrichment_stage"),
            )

        return None


class Job(BaseModel):
    """A quantum computing job managed by the orchestration platform."""

    id: str
    project_id: str | None = None
    name: str = ""
    objective: str = "general"
    status: str = "queued"
    circuit_type: str = ""
    num_qubits: int = 0
    shots: int = 4096
    priority: int = 5
    tags: dict[str, Any] | None = None
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    runs: list[Run] = Field(default_factory=list)
    outcome_report: JobOutcomeReport | None = None

    @property
    def outcome(self) -> str:
        """Canonical outcome string. Never hides degradation."""
        if self.outcome_report is not None:
            return self.outcome_report.outcome
        return self.status

    @property
    def is_degraded(self) -> bool:
        """True when the job completed with partial failures."""
        if self.outcome_report is not None:
            return self.outcome_report.is_degraded
        return False

    @property
    def failed_partition_ids(self) -> list[str]:
        """Partition IDs that failed during execution."""
        if self.outcome_report is not None:
            return self.outcome_report.failed_partition_ids
        return []

    @property
    def is_success(self) -> bool:
        """True only when ALL partitions completed successfully."""
        if self.outcome_report is not None:
            return self.outcome_report.is_success
        return self.status == "completed"


class RunResult(BaseModel):
    """Final merged result for a completed run."""

    id: str
    run_id: str
    counts: dict[str, int] = Field(default_factory=dict)
    total_shots: int = 0
    fidelity_estimate: float | None = None
    cost_usd: float = 0.0
    latency_ms: float | None = None
    aggregation_method: str = "passthrough"
    proof_hash: str | None = None
    noise_profile: dict[str, Any] | None = None


class ExecutionProof(BaseModel):
    """Cryptographic proof of execution for audit and verification."""

    run_id: str
    proof_hash: str
    algorithm: str = "sha256"
    timestamp: datetime | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    backend_attestations: list[dict[str, Any]] = Field(default_factory=list)
    verifiable: bool = True


class BackendCapabilities(BaseModel):
    """Hardware capabilities of a quantum backend."""

    max_qubits: int = 0
    max_shots: int = 100000
    basis_gates: list[str] = Field(default_factory=list)
    fidelity_1q: float | None = None
    fidelity_2q: float | None = None
    is_modular: bool = False
    module_count: int = 1
    supports_midcircuit_measurement: bool = False
    supports_dynamic_circuits: bool = False


class Backend(BaseModel):
    """A quantum computing backend (hardware or simulator)."""

    id: str
    name: str
    provider: str
    backend_type: str = "simulator"
    status: str = "available"
    num_qubits: int = 0
    queue_depth: int = 0
    cost_per_shot: float = 0.0
    capabilities: BackendCapabilities = Field(default_factory=BackendCapabilities)


class CalibrationData(BaseModel):
    """Calibration snapshot for a specific backend."""

    backend_id: str
    timestamp: datetime | None = None
    qubit_properties: dict[str, Any] = Field(default_factory=dict)
    gate_properties: dict[str, Any] = Field(default_factory=dict)
    readout_errors: dict[str, float] = Field(default_factory=dict)
    t1_times_us: list[float] = Field(default_factory=list)
    t2_times_us: list[float] = Field(default_factory=list)


class Session(BaseModel):
    """An interactive session with a specific backend."""

    id: str
    backend_id: str
    status: str = "active"
    created_at: datetime | None = None
    expires_at: datetime | None = None
    max_execution_time: int = 3600
    jobs_submitted: int = 0


class ExecutionMetadata(BaseModel):
    """Standardized metadata indicating how an execution was performed.

    QNT-409: mirrors ``packages.schemas.api_metadata.ExecutionMetadata``.
    """

    runtime_backed: bool = False
    engine: str = "unknown"
    fallback_used: bool = False
    fallback_reason: str | None = None
    execution_time_ms: float | None = None
    provider_job_id: str | None = None

    # -- convenience properties ------------------------------------------

    @property
    def is_runtime_backed(self) -> bool:
        """True when the result was produced by an actual quantum runtime."""
        return self.runtime_backed

    @property
    def used_fallback(self) -> bool:
        """True when a fallback execution path was taken."""
        return self.fallback_used


class JobOutcomeMetadata(ExecutionMetadata):
    """Extended metadata for jobs that execute across partitions."""

    outcome: str = "completed"
    total_partitions: int = 0
    completed_partitions: int = 0
    failed_partitions: int = 0
    failed_partition_ids: list[str] = Field(default_factory=list)


class SamplerResult(BaseModel):
    """Result from the Sampler primitive (IBM-style)."""

    quasi_dists: list[dict[str, float]] = Field(default_factory=list)
    metadata: list[dict[str, Any]] = Field(default_factory=list)
    num_circuits: int = 0
    total_shots: int = 0

    # -- QNT-409 helpers -------------------------------------------------

    def execution_metadata(self, circuit_index: int = 0) -> ExecutionMetadata:
        """Return typed ExecutionMetadata for a given circuit index."""
        if circuit_index < len(self.metadata):
            return ExecutionMetadata.model_validate(self.metadata[circuit_index])
        return ExecutionMetadata()

    @property
    def is_runtime_backed(self) -> bool:
        return all(
            m.get("runtime_backed", False) for m in self.metadata
        ) if self.metadata else False

    @property
    def used_fallback(self) -> bool:
        return any(m.get("fallback_used", False) for m in self.metadata)

    @property
    def engine(self) -> str:
        if self.metadata:
            return self.metadata[0].get("engine", "unknown")
        return "unknown"


class EstimatorResult(BaseModel):
    """Result from the Estimator primitive (IBM-style)."""

    values: list[float] = Field(default_factory=list)
    variances: list[float] = Field(default_factory=list)
    metadata: list[dict[str, Any]] = Field(default_factory=list)
    num_circuits: int = 0

    # -- QNT-409 helpers -------------------------------------------------

    def execution_metadata(self, circuit_index: int = 0) -> ExecutionMetadata:
        """Return typed ExecutionMetadata for a given circuit index."""
        if circuit_index < len(self.metadata):
            return ExecutionMetadata.model_validate(self.metadata[circuit_index])
        return ExecutionMetadata()

    @property
    def is_runtime_backed(self) -> bool:
        return all(
            m.get("runtime_backed", False) for m in self.metadata
        ) if self.metadata else False

    @property
    def used_fallback(self) -> bool:
        return any(m.get("fallback_used", False) for m in self.metadata)

    @property
    def engine(self) -> str:
        if self.metadata:
            return self.metadata[0].get("engine", "unknown")
        return "unknown"


class ResourceEstimate(BaseModel):
    """Estimated resources required to execute a circuit."""

    num_qubits: int = 0
    gate_count: int = 0
    depth: int = 0
    num_partitions: int = 1
    estimated_time_s: float = 0.0
    estimated_cost_usd: float = 0.0
    recommended_backends: list[str] = Field(default_factory=list)
    transpiler_passes: int = 0
    # QNT-409: execution metadata
    runtime_backed: bool = False
    engine: str = "unknown"
    fallback_used: bool = False
    fallback_reason: str | None = None
    execution_time_ms: float | None = None


class CompiledCircuit(BaseModel):
    """A circuit compiled for a specific backend."""

    original_depth: int = 0
    compiled_depth: int = 0
    original_gate_count: int = 0
    compiled_gate_count: int = 0
    optimization_level: int = 1
    backend_id: str = ""
    qasm: str | None = None
    layout: dict[str, Any] | None = None
    # QNT-409: execution metadata
    runtime_backed: bool = False
    engine: str = "unknown"
    fallback_used: bool = False
    fallback_reason: str | None = None
    execution_time_ms: float | None = None


class BackendComparison(BaseModel):
    """Comparison result for a single backend."""

    backend_id: str
    backend_name: str
    fidelity_estimate: float | None = None
    estimated_time_s: float = 0.0
    estimated_cost_usd: float = 0.0
    queue_depth: int = 0
    compiled_depth: int = 0
    score: float = 0.0


class ComparisonResult(BaseModel):
    """Result of comparing multiple backends for a given circuit."""

    circuit_qubits: int = 0
    circuit_depth: int = 0
    backends: list[BackendComparison] = Field(default_factory=list)
    recommended: str | None = None

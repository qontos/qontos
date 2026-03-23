"""Run result — output of result_aggregator, the final product."""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime


class PartitionResult(BaseModel):
    """Result from a single partition execution."""
    partition_id: str
    partition_index: int
    backend_id: str
    backend_name: str
    provider: str

    counts: dict[str, int]
    shots_completed: int
    execution_time_ms: float
    cost_usd: float = 0.0

    # Provider-specific
    provider_job_id: str | None = None
    transpiled_depth: int | None = None
    transpiled_gate_count: int | None = None

    metadata: dict = Field(default_factory=dict)


class RunResult(BaseModel):
    """Unified result from the full pipeline — the final product.

    This is what the API returns and the dashboard visualizes.
    """
    job_id: str
    status: str  # completed, failed, partial

    # Merged output
    final_counts: dict[str, int]
    total_shots: int

    # Quality metrics
    fidelity_estimate: float | None = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0

    # Provenance
    partition_results: list[PartitionResult] = Field(default_factory=list)
    aggregation_method: str = "passthrough"
    proof_hash: str = ""  # SHA-256 execution integrity hash

    # Noise emulation data (if enabled)
    noise_emulation: dict | None = None

    # Timestamps
    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Lightweight summary for list views and analytics."""
    job_id: str
    name: str
    status: str
    num_qubits: int
    shots: int
    num_partitions: int
    cost_usd: float
    latency_ms: float
    fidelity_estimate: float | None
    proof_hash: str
    completed_at: datetime | None

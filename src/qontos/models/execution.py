"""Execution manifest — the contract between API and orchestration pipeline."""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ObjectiveType(str, Enum):
    GENERAL = "general"
    CHEMISTRY = "chemistry"
    OPTIMIZATION = "optimization"
    MACHINE_LEARNING = "machine_learning"
    BENCHMARK = "benchmark"
    ERROR_CORRECTION = "error_correction"


class ExecutionConstraints(BaseModel):
    """User-specified constraints on execution."""
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    preferred_backends: list[str] = Field(default_factory=list)
    required_fidelity: float | None = None
    partition_strategy: str = "auto"  # auto, greedy, spectral, manual
    num_partitions: int | None = None
    enable_noise_emulation: bool = False
    transduction_penalty: float = 0.0
    error_mitigation: str = "none"  # none, zne, pec, m3


class ExecutionManifest(BaseModel):
    """The single canonical job description flowing through the pipeline.

    Created by circuit_ingest, consumed by every downstream service.
    This is the contract: all services agree on this schema.
    """
    job_id: str
    user_id: str
    project_id: str | None = None
    experiment_id: str | None = None

    # Job metadata
    name: str
    description: str | None = None
    objective: ObjectiveType = ObjectiveType.GENERAL
    tags: dict = Field(default_factory=dict)

    # Circuit specification
    input_type: str  # qiskit, openqasm, pennylane
    circuit_hash: str  # deterministic hash for dedup and integrity
    num_qubits: int
    circuit_depth: int | None = None
    gate_count: int | None = None

    # Execution parameters
    shots: int = 4096
    optimization_level: int = 1
    constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)

    # Pipeline state
    created_at: datetime | None = None
    priority: int = 5  # 1-10, lower = higher priority

    # Reference to stored circuit (S3 key or inline)
    circuit_storage_key: str | None = None
    circuit_inline: str | None = None

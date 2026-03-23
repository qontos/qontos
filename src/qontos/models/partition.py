"""Partition plan — output of the partitioner, input to the scheduler.

QNT-404: Added PartitionState enum for durable dependency graph tracking.
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class PartitionState(str, Enum):
    """Lifecycle state of a single partition within a dependency graph.

    Used by the DependencyGraphRecord (QNT-404) to durably track which
    partitions are pending, running, completed, or failed.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PartitionEntry(BaseModel):
    """A single partition — a subset of qubits assigned to a virtual module."""
    partition_id: str
    partition_index: int
    qubit_indices: list[int]
    num_qubits: int
    gate_count: int
    depth: int
    qubit_mapping: dict[int, int] = Field(default_factory=dict)  # global -> local

    # Inter-module metrics
    inter_module_gates: int = 0
    boundary_qubits: list[int] = Field(default_factory=list)

    # Serialized sub-circuit for executor — the QASM (or other format) string
    # representing only the gates local to this partition, with qubits remapped
    # to local indices via qubit_mapping.
    circuit_data: str | None = None
    circuit_format: str = "openqasm2"  # format of circuit_data (openqasm2, openqasm3, json)


class DependencyEdge(BaseModel):
    """A dependency between two partitions (inter-module gate)."""
    from_partition: str
    to_partition: str
    dependency_type: str = "state_dependency"  # state_dependency, measurement_dependency
    gate_name: str | None = None
    shared_qubits: list[int] = Field(default_factory=list)
    estimated_latency_us: float = 0.0


class PartitionPlan(BaseModel):
    """Complete partition plan for a job — produced by the partitioner."""
    job_id: str
    strategy: str  # auto, greedy, spectral, manual
    partitions: list[PartitionEntry]
    dependencies: list[DependencyEdge] = Field(default_factory=list)

    # Quality metrics
    total_inter_module_gates: int = 0
    estimated_module_count: int = 1
    estimated_communication_overhead_us: float = 0.0
    partition_balance_score: float = 1.0  # 1.0 = perfectly balanced
    cut_ratio: float = 0.0  # fraction of gates that are inter-module

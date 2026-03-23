"""Local types for the partitioner service."""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field


class PartitionStrategy(str, Enum):
    """Supported partitioning strategies."""
    AUTO = "auto"
    GREEDY = "greedy"
    SPECTRAL = "spectral"
    MANUAL = "manual"


@dataclass
class PartitionConstraints:
    """User-supplied constraints for partitioning."""
    max_qubits_per_partition: int | None = None
    min_partitions: int = 1
    max_partitions: int | None = None
    target_partitions: int | None = None
    max_inter_module_gates: int | None = None
    preferred_strategy: PartitionStrategy = PartitionStrategy.AUTO


@dataclass
class CostEstimate:
    """Cost breakdown for a candidate partition."""
    inter_module_gates: int = 0
    communication_overhead_us: float = 0.0
    partition_balance_score: float = 1.0
    cut_ratio: float = 0.0


@dataclass
class QubitEdge:
    """A weighted edge between two qubits in the circuit graph."""
    qubit_a: int
    qubit_b: int
    weight: float = 1.0
    gate_names: list[str] = field(default_factory=list)

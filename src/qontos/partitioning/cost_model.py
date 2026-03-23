"""Cost model for evaluating partition quality.

Transduction parameters are taken from the distributed-QC whitepaper:
    - Bell pair generation rate:  ~3 kHz  (one pair every ~333 us)
    - Inter-module gate latency:  ~100 us per operation (including
      classical signalling, Bell state measurement, feed-forward)
    - Communication overhead per inter-module gate includes the Bell
      pair generation wait plus the gate execution latency.
"""

from __future__ import annotations

from qontos.partitioning.graph_model import CircuitGraph
from qontos.partitioning.models import CostEstimate


# --------------- Whitepaper transduction constants -------------------------
BELL_RATE_HZ: float = 3_000.0          # Bell pairs per second
BELL_PAIR_LATENCY_US: float = 1e6 / BELL_RATE_HZ  # ~333.3 us
INTER_MODULE_GATE_LATENCY_US: float = 100.0        # gate execution
PER_OP_OVERHEAD_US: float = BELL_PAIR_LATENCY_US + INTER_MODULE_GATE_LATENCY_US


class PartitionCostModel:
    """Estimate the cost of a proposed qubit partition.

    Accepts a CircuitGraph and a partition assignment (list of qubit sets)
    and computes four metrics:

    * inter_module_gates — number of multi-qubit gates whose qubits span
      more than one partition.
    * communication_overhead_us — estimated total latency for all inter-module
      operations based on transduction parameters.
    * partition_balance_score — ratio of smallest to largest partition size
      (1.0 = perfectly balanced, lower = more skewed).
    * cut_ratio — fraction of total multi-qubit gates that are inter-module.
    """

    def __init__(
        self,
        bell_rate_hz: float = BELL_RATE_HZ,
        inter_module_gate_latency_us: float = INTER_MODULE_GATE_LATENCY_US,
    ) -> None:
        self.bell_rate_hz = bell_rate_hz
        self.bell_pair_latency_us = 1e6 / bell_rate_hz
        self.inter_module_gate_latency_us = inter_module_gate_latency_us
        self.per_op_overhead_us = self.bell_pair_latency_us + inter_module_gate_latency_us

    def evaluate(
        self,
        graph: CircuitGraph,
        partitions: list[set[int]],
    ) -> CostEstimate:
        """Return a CostEstimate for the given partition assignment."""
        qubit_to_partition = self._build_lookup(partitions)
        edges = graph.get_edge_weights()

        total_multi_qubit_weight = 0.0
        inter_module_weight = 0.0

        for edge in edges:
            total_multi_qubit_weight += edge.weight
            p_a = qubit_to_partition.get(edge.qubit_a, -1)
            p_b = qubit_to_partition.get(edge.qubit_b, -1)
            if p_a != p_b:
                inter_module_weight += edge.weight

        inter_module_gates = int(inter_module_weight)

        # Communication overhead: each inter-module gate requires one Bell
        # pair plus a gate execution window.
        communication_overhead_us = inter_module_gates * self.per_op_overhead_us

        # Balance score: min_size / max_size (1.0 when all equal).
        sizes = [len(p) for p in partitions if len(p) > 0]
        if len(sizes) < 2:
            balance_score = 1.0
        else:
            balance_score = min(sizes) / max(sizes)

        # Cut ratio: fraction of multi-qubit gate interactions that cross
        # partition boundaries.
        if total_multi_qubit_weight > 0:
            cut_ratio = inter_module_weight / total_multi_qubit_weight
        else:
            cut_ratio = 0.0

        return CostEstimate(
            inter_module_gates=inter_module_gates,
            communication_overhead_us=communication_overhead_us,
            partition_balance_score=round(balance_score, 6),
            cut_ratio=round(cut_ratio, 6),
        )

    @staticmethod
    def _build_lookup(partitions: list[set[int]]) -> dict[int, int]:
        """Map each qubit to its partition index."""
        lookup: dict[int, int] = {}
        for idx, part in enumerate(partitions):
            for q in part:
                lookup[q] = idx
        return lookup

"""Backend scoring engine for the QONTOS scheduler.

Evaluates how well a backend fits a given partition under execution constraints.
Uses a weighted multi-criteria model: fidelity, queue_depth, cost, capacity_fit.
"""

from __future__ import annotations

import math

from qontos.models import BackendCapability, PartitionEntry, ExecutionConstraints
from qontos.scheduling.models import ScoringWeights


class BackendScorer:
    """Scores a backend for a given partition + constraints."""

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = (weights or ScoringWeights()).normalized()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        backend: BackendCapability,
        partition: PartitionEntry,
        constraints: ExecutionConstraints,
    ) -> tuple[float, dict]:
        """Return (score, reasoning_dict) for assigning *partition* to *backend*.

        Score is in [0, 1]; higher is better.
        """
        fidelity = self._score_fidelity(backend, partition, constraints)
        queue = self._score_queue_depth(backend)
        cost = self._score_cost(backend, partition, constraints)
        capacity = self._score_capacity_fit(backend, partition)

        penalties: dict[str, float] = {}

        # Penalize inter-module gates on modular backends
        if backend.is_modular and partition.inter_module_gates > 0:
            gate_penalty = self._inter_module_penalty(backend, partition)
            penalties["inter_module_gate_penalty"] = gate_penalty
            fidelity *= (1.0 - gate_penalty)

        w = self.weights
        total = (
            w.fidelity * fidelity
            + w.queue_depth * queue
            + w.cost * cost
            + w.capacity_fit * capacity
        )

        reasoning = {
            "fidelity_score": round(fidelity, 4),
            "queue_depth_score": round(queue, 4),
            "cost_score": round(cost, 4),
            "capacity_fit_score": round(capacity, 4),
            "penalties": penalties,
            "weights": w.model_dump(),
            "total_score": round(total, 4),
        }
        return round(total, 4), reasoning

    # ------------------------------------------------------------------
    # Component scorers (each returns value in [0, 1])
    # ------------------------------------------------------------------

    @staticmethod
    def _score_fidelity(
        backend: BackendCapability,
        partition: PartitionEntry,
        constraints: ExecutionConstraints,
    ) -> float:
        """Estimate execution fidelity for the partition on this backend."""
        if backend.backend_type == "simulator":
            # Simulators have perfect fidelity (or noise-model fidelity).
            return 1.0

        f1 = backend.avg_gate_fidelity_1q or 0.99
        f2 = backend.avg_gate_fidelity_2q or 0.98
        fr = backend.avg_readout_fidelity or 0.97

        # Rough circuit fidelity estimate: product of per-gate fidelities
        # Assume 70% single-qubit gates, 30% two-qubit gates as heuristic.
        g = partition.gate_count
        single_q_gates = int(g * 0.7)
        two_q_gates = g - single_q_gates

        gate_fidelity = (f1 ** single_q_gates) * (f2 ** two_q_gates)
        readout_fidelity = fr ** partition.num_qubits
        estimated = gate_fidelity * readout_fidelity

        # Clamp to [0, 1]
        return max(0.0, min(1.0, estimated))

    @staticmethod
    def _score_queue_depth(backend: BackendCapability) -> float:
        """Lower queue depth is better. Map to [0, 1] via exponential decay."""
        # score = e^(-0.1 * queue_depth)
        return math.exp(-0.1 * backend.queue_depth)

    @staticmethod
    def _score_cost(
        backend: BackendCapability,
        partition: PartitionEntry,
        constraints: ExecutionConstraints,
    ) -> float:
        """Lower cost is better. Normalized against max_cost if available."""
        if backend.cost_per_shot == 0.0:
            return 1.0  # free backend (simulator)

        shots = 4096  # default
        estimated_cost = backend.cost_per_shot * shots
        if constraints.max_cost_usd and constraints.max_cost_usd > 0:
            ratio = estimated_cost / constraints.max_cost_usd
            return max(0.0, 1.0 - ratio)

        # No budget constraint: use inverse scaling
        return 1.0 / (1.0 + estimated_cost)

    @staticmethod
    def _score_capacity_fit(
        backend: BackendCapability,
        partition: PartitionEntry,
    ) -> float:
        """How well the partition fits the backend's qubit capacity.

        Perfect fit = 1.0. Too small wastes resources; too large is impossible.
        """
        if partition.num_qubits > backend.num_qubits:
            return 0.0  # cannot fit

        utilization = partition.num_qubits / backend.num_qubits
        # Prefer ~50-90% utilization; penalize very low utilization
        if utilization >= 0.5:
            return 1.0
        return 0.3 + 0.7 * (utilization / 0.5)

    @staticmethod
    def _inter_module_penalty(
        backend: BackendCapability,
        partition: PartitionEntry,
    ) -> float:
        """Penalty for inter-module gates on modular architectures.

        Returns a value in [0, 1] representing the fraction of fidelity lost.
        """
        if not backend.is_modular or partition.inter_module_gates == 0:
            return 0.0

        inter_fidelity = backend.inter_module_fidelity or 0.90
        transduction = backend.transduction_efficiency or 0.95

        # Each inter-module gate suffers reduced fidelity
        per_gate_penalty = 1.0 - (inter_fidelity * transduction)
        total_penalty = per_gate_penalty * partition.inter_module_gates

        # Cap at 0.8 — never completely disqualify
        return min(0.8, total_penalty)

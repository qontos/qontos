"""Behavioral tests for the scheduling engine.

Tests the BackendScorer directly (scoring logic) and the Scheduler
with mock backends. The scorer is the core of scheduling decisions.
"""

from __future__ import annotations

import pytest

from qontos.models.backend import BackendCapability, BackendStatus
from qontos.models.partition import PartitionEntry
from qontos.models.execution import ExecutionConstraints
from qontos.scheduling.scoring import BackendScorer
from qontos.scheduling.models import ScoringWeights
from qontos.scheduling.policies import (
    FidelityFirstPolicy,
    SimulatorFirstPolicy,
    CostOptimizedPolicy,
    get_policy,
    POLICY_REGISTRY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simulator_backend() -> BackendCapability:
    return BackendCapability(
        id="sim-1",
        name="local_aer",
        provider="local_simulator",
        backend_type="simulator",
        status=BackendStatus.AVAILABLE,
        num_qubits=32,
        queue_depth=0,
        cost_per_shot=0.0,
    )


@pytest.fixture
def hardware_backend() -> BackendCapability:
    return BackendCapability(
        id="ibm-eagle-1",
        name="ibm_eagle",
        provider="ibm",
        backend_type="hardware",
        status=BackendStatus.AVAILABLE,
        num_qubits=127,
        max_circuit_depth=300,
        avg_gate_fidelity_1q=0.999,
        avg_gate_fidelity_2q=0.99,
        avg_readout_fidelity=0.98,
        queue_depth=5,
        cost_per_shot=0.001,
    )


@pytest.fixture
def small_backend() -> BackendCapability:
    """A backend with only 2 qubits — cannot fit larger partitions."""
    return BackendCapability(
        id="small-1",
        name="tiny_sim",
        provider="local_simulator",
        backend_type="simulator",
        status=BackendStatus.AVAILABLE,
        num_qubits=2,
        queue_depth=0,
        cost_per_shot=0.0,
    )


@pytest.fixture
def busy_backend() -> BackendCapability:
    return BackendCapability(
        id="busy-1",
        name="busy_backend",
        provider="ibm",
        backend_type="hardware",
        status=BackendStatus.BUSY,
        num_qubits=50,
        queue_depth=100,
        cost_per_shot=0.01,
    )


@pytest.fixture
def partition_2q() -> PartitionEntry:
    return PartitionEntry(
        partition_id="job-1-p0",
        partition_index=0,
        qubit_indices=[0, 1],
        num_qubits=2,
        gate_count=4,
        depth=3,
    )


@pytest.fixture
def partition_5q() -> PartitionEntry:
    return PartitionEntry(
        partition_id="job-1-p1",
        partition_index=1,
        qubit_indices=[0, 1, 2, 3, 4],
        num_qubits=5,
        gate_count=20,
        depth=10,
    )


@pytest.fixture
def default_constraints() -> ExecutionConstraints:
    return ExecutionConstraints()


# ---------------------------------------------------------------------------
# BackendScorer tests
# ---------------------------------------------------------------------------

class TestBackendScorer:
    """Test the multi-criteria scoring engine."""

    def test_simulator_gets_perfect_fidelity_score(
        self,
        simulator_backend: BackendCapability,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        scorer = BackendScorer()
        score, reasoning = scorer.score(simulator_backend, partition_2q, default_constraints)
        assert reasoning["fidelity_score"] == 1.0

    def test_hardware_fidelity_less_than_one(
        self,
        hardware_backend: BackendCapability,
        partition_5q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        scorer = BackendScorer()
        score, reasoning = scorer.score(hardware_backend, partition_5q, default_constraints)
        assert reasoning["fidelity_score"] < 1.0
        assert reasoning["fidelity_score"] > 0.0

    def test_free_backend_perfect_cost_score(
        self,
        simulator_backend: BackendCapability,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        scorer = BackendScorer()
        _, reasoning = scorer.score(simulator_backend, partition_2q, default_constraints)
        assert reasoning["cost_score"] == 1.0

    def test_zero_queue_perfect_queue_score(
        self,
        simulator_backend: BackendCapability,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        scorer = BackendScorer()
        _, reasoning = scorer.score(simulator_backend, partition_2q, default_constraints)
        assert reasoning["queue_depth_score"] == 1.0

    def test_high_queue_low_queue_score(
        self,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        backend = BackendCapability(
            id="q-100",
            name="queued",
            provider="ibm",
            backend_type="hardware",
            status=BackendStatus.AVAILABLE,
            num_qubits=50,
            queue_depth=50,
            avg_gate_fidelity_1q=0.99,
            avg_gate_fidelity_2q=0.98,
            avg_readout_fidelity=0.97,
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, default_constraints)
        assert reasoning["queue_depth_score"] < 0.1

    def test_score_in_zero_one_range(
        self,
        simulator_backend: BackendCapability,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        scorer = BackendScorer()
        score, _ = scorer.score(simulator_backend, partition_2q, default_constraints)
        assert 0.0 <= score <= 1.0

    def test_capacity_fit_good_for_matched_size(
        self,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        backend = BackendCapability(
            id="fit-1",
            name="good_fit",
            provider="local_simulator",
            backend_type="simulator",
            status=BackendStatus.AVAILABLE,
            num_qubits=3,  # 2/3 = 67% utilization — good fit
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, default_constraints)
        assert reasoning["capacity_fit_score"] == 1.0

    def test_capacity_fit_low_for_waste(
        self,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        backend = BackendCapability(
            id="waste-1",
            name="wasteful",
            provider="local_simulator",
            backend_type="simulator",
            status=BackendStatus.AVAILABLE,
            num_qubits=1000,  # 2/1000 = 0.2% utilization
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, default_constraints)
        assert reasoning["capacity_fit_score"] < 1.0


# ---------------------------------------------------------------------------
# ScoringWeights tests
# ---------------------------------------------------------------------------

class TestScoringWeights:
    """Test weight normalization."""

    def test_default_weights_sum_to_one(self) -> None:
        w = ScoringWeights().normalized()
        total = w.fidelity + w.queue_depth + w.cost + w.capacity_fit
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights_normalize(self) -> None:
        w = ScoringWeights(fidelity=2, queue_depth=1, cost=1, capacity_fit=0).normalized()
        total = w.fidelity + w.queue_depth + w.cost + w.capacity_fit
        assert abs(total - 1.0) < 1e-9
        assert w.fidelity == 0.5

    def test_zero_weights_fallback(self) -> None:
        w = ScoringWeights(fidelity=0, queue_depth=0, cost=0, capacity_fit=0).normalized()
        assert w.fidelity == 0.25
        assert w.queue_depth == 0.25

    def test_fidelity_first_policy_weights(self) -> None:
        policy = FidelityFirstPolicy()
        scorer = policy.build_scorer()
        # Fidelity-first should have highest fidelity weight
        w = scorer.weights
        assert w.fidelity > w.queue_depth
        assert w.fidelity > w.cost
        assert w.fidelity > w.capacity_fit

    def test_cost_optimized_policy_weights(self) -> None:
        policy = CostOptimizedPolicy()
        scorer = policy.build_scorer()
        w = scorer.weights
        assert w.cost > w.fidelity

    def test_simulator_first_policy_weights(self) -> None:
        policy = SimulatorFirstPolicy()
        scorer = policy.build_scorer()
        w = scorer.weights
        assert w.cost > w.fidelity


# ---------------------------------------------------------------------------
# Policy registry tests
# ---------------------------------------------------------------------------

class TestPolicyRegistry:
    """Test policy lookup."""

    def test_get_known_policy(self) -> None:
        policy = get_policy("fidelity_first")
        assert policy.name() == "fidelity_first"

    def test_get_unknown_defaults_to_fidelity(self) -> None:
        policy = get_policy("nonexistent")
        assert policy.name() == "fidelity_first"

    def test_all_policies_registered(self) -> None:
        assert "simulator_first" in POLICY_REGISTRY
        assert "fidelity_first" in POLICY_REGISTRY
        assert "cost_optimized" in POLICY_REGISTRY

    def test_each_policy_builds_scorer(self) -> None:
        for name, cls in POLICY_REGISTRY.items():
            policy = cls()
            scorer = policy.build_scorer()
            assert isinstance(scorer, BackendScorer)


# ---------------------------------------------------------------------------
# Comparative scoring tests
# ---------------------------------------------------------------------------

class TestComparativeScoring:
    """Test that scoring produces correct relative rankings."""

    def test_simulator_beats_queued_hardware(
        self,
        simulator_backend: BackendCapability,
        partition_2q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        """A free simulator with zero queue should outscore expensive queued hardware."""
        queued_hw = BackendCapability(
            id="hw-q",
            name="queued_hw",
            provider="ibm",
            backend_type="hardware",
            status=BackendStatus.AVAILABLE,
            num_qubits=50,
            queue_depth=30,
            cost_per_shot=0.01,
            avg_gate_fidelity_1q=0.99,
            avg_gate_fidelity_2q=0.95,
            avg_readout_fidelity=0.95,
        )
        scorer = BackendScorer()
        sim_score, _ = scorer.score(simulator_backend, partition_2q, default_constraints)
        hw_score, _ = scorer.score(queued_hw, partition_2q, default_constraints)
        assert sim_score > hw_score

    def test_higher_fidelity_hardware_scores_higher(
        self,
        partition_5q: PartitionEntry,
        default_constraints: ExecutionConstraints,
    ) -> None:
        good_hw = BackendCapability(
            id="good",
            name="high_fidelity",
            provider="ibm",
            backend_type="hardware",
            status=BackendStatus.AVAILABLE,
            num_qubits=20,
            avg_gate_fidelity_1q=0.9999,
            avg_gate_fidelity_2q=0.999,
            avg_readout_fidelity=0.999,
            queue_depth=0,
            cost_per_shot=0.001,
        )
        bad_hw = BackendCapability(
            id="bad",
            name="low_fidelity",
            provider="ibm",
            backend_type="hardware",
            status=BackendStatus.AVAILABLE,
            num_qubits=20,
            avg_gate_fidelity_1q=0.95,
            avg_gate_fidelity_2q=0.90,
            avg_readout_fidelity=0.85,
            queue_depth=0,
            cost_per_shot=0.001,
        )
        # Use fidelity-first scorer
        scorer = FidelityFirstPolicy().build_scorer()
        good_score, _ = scorer.score(good_hw, partition_5q, default_constraints)
        bad_score, _ = scorer.score(bad_hw, partition_5q, default_constraints)
        assert good_score > bad_score

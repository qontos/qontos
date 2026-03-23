"""QGH-3005: Scheduling behavior tests.

Tests the Scheduler end-to-end, BackendScorer component scores, policy
selection, hard filters, and multi-partition scheduling.
"""

from __future__ import annotations

import pytest

from qontos.models.backend import BackendCapability, BackendStatus
from qontos.models.partition import PartitionEntry
from qontos.models.execution import ExecutionConstraints
from qontos.scheduling.scheduler import Scheduler
from qontos.scheduling.scoring import BackendScorer
from qontos.scheduling.models import ScoringWeights
from qontos.scheduling.policies import (
    FidelityFirstPolicy,
    CostOptimizedPolicy,
    SimulatorFirstPolicy,
    get_policy,
    POLICY_REGISTRY,
)

from tests.fixtures import MOCK_BACKENDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simulator_backend():
    return BackendCapability(
        id="sim-1", name="local_aer", provider="local_simulator",
        backend_type="simulator", status=BackendStatus.AVAILABLE,
        num_qubits=32, queue_depth=0, cost_per_shot=0.0,
    )


@pytest.fixture
def high_fidelity_hw():
    return BackendCapability(
        id="hw-hifi", name="high_fid", provider="ibm",
        backend_type="hardware", status=BackendStatus.AVAILABLE,
        num_qubits=50,
        avg_gate_fidelity_1q=0.9999, avg_gate_fidelity_2q=0.999,
        avg_readout_fidelity=0.999, queue_depth=1, cost_per_shot=0.005,
    )


@pytest.fixture
def cheap_hw():
    return BackendCapability(
        id="hw-cheap", name="cheap_hw", provider="braket",
        backend_type="hardware", status=BackendStatus.AVAILABLE,
        num_qubits=30,
        avg_gate_fidelity_1q=0.995, avg_gate_fidelity_2q=0.98,
        avg_readout_fidelity=0.96, queue_depth=0, cost_per_shot=0.0001,
    )


@pytest.fixture
def small_backend():
    return BackendCapability(
        id="small-1", name="tiny", provider="local_simulator",
        backend_type="simulator", status=BackendStatus.AVAILABLE,
        num_qubits=2, queue_depth=0, cost_per_shot=0.0,
    )


@pytest.fixture
def offline_backend():
    return BackendCapability(
        id="offline-1", name="offline", provider="ibm",
        backend_type="hardware", status=BackendStatus.OFFLINE,
        num_qubits=50, queue_depth=0, cost_per_shot=0.001,
    )


@pytest.fixture
def partition_2q():
    return PartitionEntry(
        partition_id="job-1-p0", partition_index=0,
        qubit_indices=[0, 1], num_qubits=2, gate_count=4, depth=3,
    )


@pytest.fixture
def partition_5q():
    return PartitionEntry(
        partition_id="job-1-p1", partition_index=1,
        qubit_indices=list(range(5)), num_qubits=5, gate_count=20, depth=10,
    )


@pytest.fixture
def constraints():
    return ExecutionConstraints()


# ---------------------------------------------------------------------------
# 1. Fidelity-first policy selects highest fidelity backend
# ---------------------------------------------------------------------------


class TestFidelityFirstPolicy:
    def test_fidelity_first_selects_highest_fidelity(self, high_fidelity_hw, cheap_hw, partition_2q, constraints):
        scheduler = Scheduler(policy=FidelityFirstPolicy())
        tasks = scheduler.schedule(
            job_id="fid-test", partitions=[partition_2q],
            backends=[cheap_hw, high_fidelity_hw], constraints=constraints,
        )
        assert len(tasks) == 1
        assert tasks[0].backend_id == "hw-hifi"

    def test_fidelity_first_weights_dominated_by_fidelity(self):
        scorer = FidelityFirstPolicy().build_scorer()
        w = scorer.weights
        assert w.fidelity > w.queue_depth
        assert w.fidelity > w.cost
        assert w.fidelity > w.capacity_fit


# ---------------------------------------------------------------------------
# 2. Cost-aware policy selects cheapest adequate backend
# ---------------------------------------------------------------------------


class TestCostAwarePolicy:
    def test_cost_policy_prefers_cheaper(self, high_fidelity_hw, cheap_hw, partition_2q, constraints):
        scheduler = Scheduler(policy=CostOptimizedPolicy())
        tasks = scheduler.schedule(
            job_id="cost-test", partitions=[partition_2q],
            backends=[high_fidelity_hw, cheap_hw], constraints=constraints,
        )
        assert len(tasks) == 1
        # Cheap backend should win when cost is weighted highest
        assert tasks[0].backend_id == "hw-cheap"


# ---------------------------------------------------------------------------
# 3. Queue depth penalty applied
# ---------------------------------------------------------------------------


class TestQueueDepthPenalty:
    def test_high_queue_low_score(self, partition_2q, constraints):
        backend = BackendCapability(
            id="q-heavy", name="queued", provider="ibm",
            backend_type="hardware", status=BackendStatus.AVAILABLE,
            num_qubits=50, queue_depth=50,
            avg_gate_fidelity_1q=0.99, avg_gate_fidelity_2q=0.98,
            avg_readout_fidelity=0.97,
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, constraints)
        assert reasoning["queue_depth_score"] < 0.1

    def test_zero_queue_perfect_score(self, simulator_backend, partition_2q, constraints):
        scorer = BackendScorer()
        _, reasoning = scorer.score(simulator_backend, partition_2q, constraints)
        assert reasoning["queue_depth_score"] == 1.0


# ---------------------------------------------------------------------------
# 4. Capacity fit score prefers tighter fits
# ---------------------------------------------------------------------------


class TestCapacityFit:
    def test_good_fit_high_score(self, partition_2q, constraints):
        backend = BackendCapability(
            id="fit-3q", name="fit", provider="local_simulator",
            backend_type="simulator", status=BackendStatus.AVAILABLE,
            num_qubits=3,
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, constraints)
        assert reasoning["capacity_fit_score"] == 1.0

    def test_wasteful_fit_lower_score(self, partition_2q, constraints):
        backend = BackendCapability(
            id="fit-1000q", name="huge", provider="local_simulator",
            backend_type="simulator", status=BackendStatus.AVAILABLE,
            num_qubits=1000,
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_2q, constraints)
        assert reasoning["capacity_fit_score"] < 1.0

    def test_undersized_backend_zero_fit(self, partition_5q, constraints):
        backend = BackendCapability(
            id="tiny-2q", name="tiny", provider="local_simulator",
            backend_type="simulator", status=BackendStatus.AVAILABLE,
            num_qubits=2,
        )
        scorer = BackendScorer()
        _, reasoning = scorer.score(backend, partition_5q, constraints)
        assert reasoning["capacity_fit_score"] == 0.0


# ---------------------------------------------------------------------------
# 5. preferred_backends constraint filters correctly
# ---------------------------------------------------------------------------


class TestPreferredBackends:
    def test_preferred_backends_constraint(self, partition_2q):
        backends = [
            BackendCapability(
                id="sim-a", name="sim_a", provider="local_simulator",
                backend_type="simulator", status=BackendStatus.AVAILABLE, num_qubits=32,
            ),
            BackendCapability(
                id="sim-b", name="sim_b", provider="local_simulator",
                backend_type="simulator", status=BackendStatus.AVAILABLE, num_qubits=32,
            ),
        ]
        constraints = ExecutionConstraints(preferred_backends=["sim-b"])
        scheduler = Scheduler(policy=FidelityFirstPolicy())
        tasks = scheduler.schedule(
            job_id="pref-test", partitions=[partition_2q],
            backends=backends, constraints=constraints,
        )
        assert tasks[0].backend_id == "sim-b"


# ---------------------------------------------------------------------------
# 6. Hard filter excludes undersized backends
# ---------------------------------------------------------------------------


class TestHardFilter:
    def test_undersized_backend_excluded(self, small_backend, simulator_backend, partition_5q, constraints):
        scheduler = Scheduler()
        tasks = scheduler.schedule(
            job_id="filter-test", partitions=[partition_5q],
            backends=[small_backend, simulator_backend], constraints=constraints,
        )
        assert len(tasks) == 1
        assert tasks[0].backend_id == "sim-1"

    def test_no_compatible_backend_raises(self, small_backend, partition_5q, constraints):
        scheduler = Scheduler()
        with pytest.raises(ValueError, match="No compatible backend"):
            scheduler.schedule(
                job_id="fail-test", partitions=[partition_5q],
                backends=[small_backend], constraints=constraints,
            )

    def test_offline_backends_excluded(self, offline_backend, partition_2q, constraints):
        scheduler = Scheduler()
        with pytest.raises(ValueError, match="No available backends"):
            scheduler.schedule(
                job_id="offline-test", partitions=[partition_2q],
                backends=[offline_backend], constraints=constraints,
            )


# ---------------------------------------------------------------------------
# 7. scheduling_reasoning is populated
# ---------------------------------------------------------------------------


class TestSchedulingReasoning:
    def test_reasoning_populated(self, simulator_backend, partition_2q, constraints):
        scheduler = Scheduler()
        tasks = scheduler.schedule(
            job_id="reason-test", partitions=[partition_2q],
            backends=[simulator_backend], constraints=constraints,
        )
        reasoning = tasks[0].scheduling_reasoning
        assert "fidelity_score" in reasoning
        assert "queue_depth_score" in reasoning
        assert "cost_score" in reasoning
        assert "capacity_fit_score" in reasoning
        assert "total_score" in reasoning


# ---------------------------------------------------------------------------
# 8. Multi-partition scheduling assigns different backends when optimal
# ---------------------------------------------------------------------------


class TestMultiPartitionScheduling:
    def test_two_partitions_assigned(self, constraints):
        p0 = PartitionEntry(
            partition_id="mp-p0", partition_index=0,
            qubit_indices=[0, 1], num_qubits=2, gate_count=4, depth=3,
        )
        p1 = PartitionEntry(
            partition_id="mp-p1", partition_index=1,
            qubit_indices=[2, 3], num_qubits=2, gate_count=4, depth=3,
        )
        backends = MOCK_BACKENDS[:3]  # sim, ibm-lagos, ibm-brisbane (all available)
        scheduler = Scheduler()
        tasks = scheduler.schedule(
            job_id="multi-test", partitions=[p0, p1],
            backends=backends, constraints=constraints,
        )
        assert len(tasks) == 2
        assert tasks[0].partition_id == "mp-p0"
        assert tasks[1].partition_id == "mp-p1"


# ---------------------------------------------------------------------------
# Policy registry
# ---------------------------------------------------------------------------


class TestPolicyRegistry:
    def test_all_policies_registered(self):
        assert "simulator_first" in POLICY_REGISTRY
        assert "fidelity_first" in POLICY_REGISTRY
        assert "cost_optimized" in POLICY_REGISTRY

    def test_unknown_policy_defaults_to_fidelity(self):
        policy = get_policy("nonexistent")
        assert policy.name() == "fidelity_first"

    def test_each_policy_builds_scorer(self):
        for name, cls in POLICY_REGISTRY.items():
            scorer = cls().build_scorer()
            assert isinstance(scorer, BackendScorer)


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------


class TestScoringWeights:
    def test_default_weights_sum_to_one(self):
        w = ScoringWeights().normalized()
        total = w.fidelity + w.queue_depth + w.cost + w.capacity_fit
        assert abs(total - 1.0) < 1e-9

    def test_zero_weights_fallback(self):
        w = ScoringWeights(fidelity=0, queue_depth=0, cost=0, capacity_fit=0).normalized()
        assert w.fidelity == 0.25

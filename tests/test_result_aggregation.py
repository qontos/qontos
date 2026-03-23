"""QGH-3006: Results, Integrity, and Proof Story — Aggregation behavior tests.

Tests passthrough, independent tensor-product merge, entangled marginal
reconstruction with fidelity penalties, and edge cases.
"""

from __future__ import annotations

import pytest

from qontos.models.partition import PartitionPlan, PartitionEntry, DependencyEdge
from qontos.models.result import RunResult, PartitionResult
from qontos.results.aggregate import ResultAggregator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def aggregator():
    return ResultAggregator()


def _pr(
    partition_id: str = "job-p0",
    partition_index: int = 0,
    counts: dict[str, int] | None = None,
    shots: int = 1000,
    cost: float = 0.0,
) -> PartitionResult:
    counts = counts or {"00": 500, "11": 500}
    return PartitionResult(
        partition_id=partition_id,
        partition_index=partition_index,
        backend_id="sim-1",
        backend_name="local_aer",
        provider="local_simulator",
        counts=counts,
        shots_completed=shots,
        execution_time_ms=100.0,
        cost_usd=cost,
    )


def _independent_plan(job_id: str = "job-ind") -> PartitionPlan:
    return PartitionPlan(
        job_id=job_id,
        strategy="greedy",
        partitions=[
            PartitionEntry(
                partition_id=f"{job_id}-p0", partition_index=0,
                qubit_indices=[0, 1], num_qubits=2, gate_count=3, depth=2,
                qubit_mapping={0: 0, 1: 1},
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1", partition_index=1,
                qubit_indices=[2, 3], num_qubits=2, gate_count=3, depth=2,
                qubit_mapping={2: 0, 3: 1},
            ),
        ],
        dependencies=[],
        total_inter_module_gates=0,
    )


def _entangled_plan(job_id: str = "job-ent", num_cuts: int = 1) -> PartitionPlan:
    return PartitionPlan(
        job_id=job_id,
        strategy="spectral",
        partitions=[
            PartitionEntry(
                partition_id=f"{job_id}-p0", partition_index=0,
                qubit_indices=[0, 1], num_qubits=2, gate_count=5, depth=4,
                qubit_mapping={0: 0, 1: 1},
                inter_module_gates=num_cuts, boundary_qubits=[1],
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1", partition_index=1,
                qubit_indices=[2, 3], num_qubits=2, gate_count=5, depth=4,
                qubit_mapping={2: 0, 3: 1},
                inter_module_gates=num_cuts, boundary_qubits=[2],
            ),
        ],
        dependencies=[
            DependencyEdge(
                from_partition=f"{job_id}-p0", to_partition=f"{job_id}-p1",
                gate_name="cx", shared_qubits=[1, 2],
            )
        ],
        total_inter_module_gates=num_cuts,
    )


# ---------------------------------------------------------------------------
# 1. Passthrough aggregation for single partition
# ---------------------------------------------------------------------------


class TestPassthroughAggregation:
    def test_passthrough_status(self, aggregator):
        result = aggregator.aggregate("job-1", [_pr(counts={"00": 600, "11": 400})])
        assert result.status == "completed"

    def test_passthrough_counts_match(self, aggregator):
        counts = {"00": 600, "11": 400}
        result = aggregator.aggregate("job-1", [_pr(counts=counts)])
        assert result.final_counts == counts

    def test_passthrough_shots(self, aggregator):
        result = aggregator.aggregate("job-1", [_pr(shots=2048)])
        assert result.total_shots == 2048

    def test_passthrough_aggregation_method(self, aggregator):
        result = aggregator.aggregate("job-1", [_pr()])
        assert result.aggregation_method == "passthrough"

    def test_passthrough_fidelity_is_one(self, aggregator):
        result = aggregator.aggregate("job-1", [_pr()])
        assert result.fidelity_estimate == 1.0

    def test_passthrough_cost(self, aggregator):
        result = aggregator.aggregate("job-1", [_pr(cost=0.5)])
        assert result.cost_usd == 0.5


# ---------------------------------------------------------------------------
# 2. Independent merge (tensor product) for 2 partitions, no dependencies
# ---------------------------------------------------------------------------


class TestIndependentMerge:
    def test_independent_merge_method(self, aggregator):
        plan = _independent_plan()
        pr0 = _pr(partition_id="job-ind-p0", partition_index=0, counts={"0": 500, "1": 500})
        pr1 = _pr(partition_id="job-ind-p1", partition_index=1, counts={"0": 700, "1": 300})
        result = aggregator.aggregate("job-ind", [pr0, pr1], plan)
        assert result.aggregation_method == "tensor_product"

    def test_independent_merge_fidelity_is_one(self, aggregator):
        plan = _independent_plan()
        pr0 = _pr(partition_id="job-ind-p0", partition_index=0, counts={"0": 800, "1": 200})
        pr1 = _pr(partition_id="job-ind-p1", partition_index=1, counts={"0": 600, "1": 400})
        result = aggregator.aggregate("job-ind", [pr0, pr1], plan)
        assert result.fidelity_estimate == 1.0

    def test_independent_merge_deterministic_counts(self, aggregator):
        plan = _independent_plan()
        pr0 = _pr(partition_id="job-ind-p0", partition_index=0, counts={"0": 1000})
        pr1 = _pr(partition_id="job-ind-p1", partition_index=1, counts={"0": 1000})
        result = aggregator.aggregate("job-ind", [pr0, pr1], plan)
        assert "00" in result.final_counts
        assert result.final_counts["00"] == 1000

    def test_independent_merge_total_cost(self, aggregator):
        plan = _independent_plan()
        pr0 = _pr(partition_id="job-ind-p0", partition_index=0, cost=1.0, counts={"0": 100})
        pr1 = _pr(partition_id="job-ind-p1", partition_index=1, cost=2.0, counts={"0": 100})
        result = aggregator.aggregate("job-ind", [pr0, pr1], plan)
        assert result.cost_usd == 3.0


# ---------------------------------------------------------------------------
# 3. Entangled merge applies fidelity penalty per cut gate
# ---------------------------------------------------------------------------


class TestEntangledMerge:
    def test_entangled_merge_method(self, aggregator):
        plan = _entangled_plan(num_cuts=1)
        pr0 = _pr(partition_id="job-ent-p0", partition_index=0)
        pr1 = _pr(partition_id="job-ent-p1", partition_index=1)
        result = aggregator.aggregate("job-ent", [pr0, pr1], plan)
        assert result.aggregation_method == "marginal_reconstruction"

    def test_entangled_merge_fidelity_penalty_1_cut(self, aggregator):
        plan = _entangled_plan(num_cuts=1)
        pr0 = _pr(partition_id="job-ent-p0", partition_index=0)
        pr1 = _pr(partition_id="job-ent-p1", partition_index=1)
        result = aggregator.aggregate("job-ent", [pr0, pr1], plan)
        # 1 cut * 0.02 penalty => 0.98
        assert result.fidelity_estimate is not None
        assert result.fidelity_estimate < 1.0
        assert result.fidelity_estimate == pytest.approx(0.98, abs=0.01)

    def test_entangled_merge_fidelity_penalty_5_cuts(self, aggregator):
        plan = _entangled_plan(num_cuts=5)
        pr0 = _pr(partition_id="job-ent-p0", partition_index=0)
        pr1 = _pr(partition_id="job-ent-p1", partition_index=1)
        result = aggregator.aggregate("job-ent", [pr0, pr1], plan)
        # 5 cuts * 0.02 = 0.10 penalty => 0.90
        assert result.fidelity_estimate == pytest.approx(0.90, abs=0.01)

    def test_entangled_merge_metadata_warns(self, aggregator):
        plan = _entangled_plan()
        pr0 = _pr(partition_id="job-ent-p0", partition_index=0)
        pr1 = _pr(partition_id="job-ent-p1", partition_index=1)
        result = aggregator.aggregate("job-ent", [pr0, pr1], plan)
        assert result.metadata.get("fidelity_degraded") is True


# ---------------------------------------------------------------------------
# 4. Aggregation method recorded in RunResult
# ---------------------------------------------------------------------------


class TestAggregationMethodRecorded:
    def test_passthrough_recorded(self, aggregator):
        result = aggregator.aggregate("j1", [_pr()])
        assert result.aggregation_method == "passthrough"

    def test_tensor_product_recorded(self, aggregator):
        plan = _independent_plan("j2")
        pr0 = _pr(partition_id="j2-p0", partition_index=0, counts={"0": 500, "1": 500})
        pr1 = _pr(partition_id="j2-p1", partition_index=1, counts={"0": 500, "1": 500})
        result = aggregator.aggregate("j2", [pr0, pr1], plan)
        assert result.aggregation_method == "tensor_product"

    def test_marginal_reconstruction_recorded(self, aggregator):
        plan = _entangled_plan("j3")
        pr0 = _pr(partition_id="j3-p0", partition_index=0)
        pr1 = _pr(partition_id="j3-p1", partition_index=1)
        result = aggregator.aggregate("j3", [pr0, pr1], plan)
        assert result.aggregation_method == "marginal_reconstruction"


# ---------------------------------------------------------------------------
# 5. Fidelity estimate calculation
# ---------------------------------------------------------------------------


class TestFidelityEstimate:
    def test_single_partition_perfect_fidelity(self, aggregator):
        result = aggregator.aggregate("j", [_pr()])
        assert result.fidelity_estimate == 1.0

    def test_independent_perfect_fidelity(self, aggregator):
        plan = _independent_plan("jf")
        pr0 = _pr(partition_id="jf-p0", partition_index=0, counts={"0": 1000})
        pr1 = _pr(partition_id="jf-p1", partition_index=1, counts={"0": 1000})
        result = aggregator.aggregate("jf", [pr0, pr1], plan)
        assert result.fidelity_estimate == 1.0


# ---------------------------------------------------------------------------
# 6. Empty partition results handled gracefully
# ---------------------------------------------------------------------------


class TestEmptyResults:
    def test_no_results_returns_failed(self, aggregator):
        result = aggregator.aggregate("job-empty", [])
        assert result.status == "failed"
        assert result.total_shots == 0
        assert result.final_counts == {}

    def test_fallback_merge_no_plan(self, aggregator):
        pr0 = _pr(partition_id="p0", partition_index=0, counts={"0": 1000})
        pr1 = _pr(partition_id="p1", partition_index=1, counts={"0": 1000})
        result = aggregator.aggregate("job-fb", [pr0, pr1], partition_plan=None)
        assert result.fidelity_estimate is not None
        assert result.fidelity_estimate <= 0.5
        assert "fallback" in result.aggregation_method

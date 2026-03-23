"""Behavioral tests for ResultAggregator.

Tests passthrough for single-partition results, independent (tensor product)
merge of two non-entangled partitions, and fidelity estimation.
"""

from __future__ import annotations

import pytest

from qontos.models.partition import PartitionPlan, PartitionEntry, DependencyEdge
from qontos.models.result import RunResult, PartitionResult
from qontos.results.aggregate import ResultAggregator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aggregator() -> ResultAggregator:
    return ResultAggregator()


def make_partition_result(
    partition_id: str = "job-p0",
    partition_index: int = 0,
    counts: dict[str, int] | None = None,
    shots: int = 1000,
    exec_time: float = 100.0,
    cost: float = 0.0,
) -> PartitionResult:
    return PartitionResult(
        partition_id=partition_id,
        partition_index=partition_index,
        backend_id="sim-1",
        backend_name="local_aer",
        provider="local_simulator",
        counts=counts or {"00": 500, "11": 500},
        shots_completed=shots,
        execution_time_ms=exec_time,
        cost_usd=cost,
    )


def make_single_partition_plan(job_id: str = "job-1") -> PartitionPlan:
    return PartitionPlan(
        job_id=job_id,
        strategy="auto",
        partitions=[
            PartitionEntry(
                partition_id=f"{job_id}-p0",
                partition_index=0,
                qubit_indices=[0, 1],
                num_qubits=2,
                gate_count=4,
                depth=3,
            )
        ],
    )


def make_independent_two_partition_plan(job_id: str = "job-2") -> PartitionPlan:
    """Two partitions with NO dependencies (independent)."""
    return PartitionPlan(
        job_id=job_id,
        strategy="greedy",
        partitions=[
            PartitionEntry(
                partition_id=f"{job_id}-p0",
                partition_index=0,
                qubit_indices=[0, 1],
                num_qubits=2,
                gate_count=3,
                depth=2,
                qubit_mapping={0: 0, 1: 1},
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1",
                partition_index=1,
                qubit_indices=[2, 3],
                num_qubits=2,
                gate_count=3,
                depth=2,
                qubit_mapping={2: 0, 3: 1},
            ),
        ],
        dependencies=[],
        total_inter_module_gates=0,
    )


def make_entangled_two_partition_plan(job_id: str = "job-3") -> PartitionPlan:
    """Two partitions WITH dependency edges (entangled cut)."""
    return PartitionPlan(
        job_id=job_id,
        strategy="spectral",
        partitions=[
            PartitionEntry(
                partition_id=f"{job_id}-p0",
                partition_index=0,
                qubit_indices=[0, 1],
                num_qubits=2,
                gate_count=5,
                depth=4,
                qubit_mapping={0: 0, 1: 1},
                inter_module_gates=1,
                boundary_qubits=[1],
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1",
                partition_index=1,
                qubit_indices=[2, 3],
                num_qubits=2,
                gate_count=5,
                depth=4,
                qubit_mapping={2: 0, 3: 1},
                inter_module_gates=1,
                boundary_qubits=[2],
            ),
        ],
        dependencies=[
            DependencyEdge(
                from_partition=f"{job_id}-p0",
                to_partition=f"{job_id}-p1",
                gate_name="cx",
                shared_qubits=[1, 2],
            )
        ],
        total_inter_module_gates=1,
    )


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------

class TestEmptyResults:
    """Edge case: no partition results."""

    def test_no_results_returns_failed(self, aggregator: ResultAggregator) -> None:
        result = aggregator.aggregate("job-empty", [])
        assert result.status == "failed"
        assert result.total_shots == 0
        assert result.final_counts == {}


# ---------------------------------------------------------------------------
# Single partition passthrough
# ---------------------------------------------------------------------------

class TestSinglePartitionPassthrough:
    """Single partition result is passed through directly."""

    def test_passthrough_status(self, aggregator: ResultAggregator) -> None:
        pr = make_partition_result(counts={"00": 600, "11": 400})
        result = aggregator.aggregate("job-1", [pr])
        assert result.status == "completed"

    def test_passthrough_counts_match(self, aggregator: ResultAggregator) -> None:
        counts = {"00": 600, "11": 400}
        pr = make_partition_result(counts=counts)
        result = aggregator.aggregate("job-1", [pr])
        assert result.final_counts == counts

    def test_passthrough_shots(self, aggregator: ResultAggregator) -> None:
        pr = make_partition_result(shots=2048)
        result = aggregator.aggregate("job-1", [pr])
        assert result.total_shots == 2048

    def test_passthrough_aggregation_method(self, aggregator: ResultAggregator) -> None:
        pr = make_partition_result()
        result = aggregator.aggregate("job-1", [pr])
        assert result.aggregation_method == "passthrough"

    def test_passthrough_fidelity(self, aggregator: ResultAggregator) -> None:
        pr = make_partition_result()
        result = aggregator.aggregate("job-1", [pr])
        assert result.fidelity_estimate == 1.0

    def test_passthrough_cost(self, aggregator: ResultAggregator) -> None:
        pr = make_partition_result(cost=0.5)
        result = aggregator.aggregate("job-1", [pr])
        assert result.cost_usd == 0.5


# ---------------------------------------------------------------------------
# Independent merge (tensor product)
# ---------------------------------------------------------------------------

class TestIndependentMerge:
    """Two independent (non-entangled) partitions merged via tensor product."""

    def test_independent_merge_status(self, aggregator: ResultAggregator) -> None:
        plan = make_independent_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-2-p0", partition_index=0,
                                     counts={"00": 500, "11": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="job-2-p1", partition_index=1,
                                     counts={"00": 700, "11": 300}, shots=1000)
        result = aggregator.aggregate("job-2", [pr0, pr1], plan)
        assert result.status == "completed"

    def test_independent_merge_method(self, aggregator: ResultAggregator) -> None:
        plan = make_independent_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-2-p0", partition_index=0,
                                     counts={"0": 500, "1": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="job-2-p1", partition_index=1,
                                     counts={"0": 700, "1": 300}, shots=1000)
        result = aggregator.aggregate("job-2", [pr0, pr1], plan)
        assert result.aggregation_method == "tensor_product"

    def test_independent_merge_fidelity_is_one(self, aggregator: ResultAggregator) -> None:
        plan = make_independent_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-2-p0", partition_index=0,
                                     counts={"0": 800, "1": 200}, shots=1000)
        pr1 = make_partition_result(partition_id="job-2-p1", partition_index=1,
                                     counts={"0": 600, "1": 400}, shots=1000)
        result = aggregator.aggregate("job-2", [pr0, pr1], plan)
        assert result.fidelity_estimate == 1.0

    def test_independent_merge_counts_nonzero(self, aggregator: ResultAggregator) -> None:
        plan = make_independent_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-2-p0", partition_index=0,
                                     counts={"0": 1000}, shots=1000)
        pr1 = make_partition_result(partition_id="job-2-p1", partition_index=1,
                                     counts={"0": 1000}, shots=1000)
        result = aggregator.aggregate("job-2", [pr0, pr1], plan)
        # Only possible combined outcome is "00"
        assert "00" in result.final_counts
        assert result.final_counts["00"] == 1000

    def test_independent_merge_total_cost(self, aggregator: ResultAggregator) -> None:
        plan = make_independent_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-2-p0", partition_index=0,
                                     cost=1.0, shots=100, counts={"0": 100})
        pr1 = make_partition_result(partition_id="job-2-p1", partition_index=1,
                                     cost=2.0, shots=100, counts={"0": 100})
        result = aggregator.aggregate("job-2", [pr0, pr1], plan)
        assert result.cost_usd == 3.0


# ---------------------------------------------------------------------------
# Entangled merge
# ---------------------------------------------------------------------------

class TestEntangledMerge:
    """Two entangled partitions with cut gates — uses marginal reconstruction."""

    def test_entangled_merge_detects_strategy(self, aggregator: ResultAggregator) -> None:
        plan = make_entangled_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-3-p0", partition_index=0,
                                     counts={"00": 500, "11": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="job-3-p1", partition_index=1,
                                     counts={"00": 500, "11": 500}, shots=1000)
        result = aggregator.aggregate("job-3", [pr0, pr1], plan)
        assert result.aggregation_method == "marginal_reconstruction"

    def test_entangled_merge_degraded_fidelity(self, aggregator: ResultAggregator) -> None:
        plan = make_entangled_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-3-p0", partition_index=0,
                                     counts={"00": 500, "11": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="job-3-p1", partition_index=1,
                                     counts={"00": 500, "11": 500}, shots=1000)
        result = aggregator.aggregate("job-3", [pr0, pr1], plan)
        # 1 inter-module gate, penalty of 0.02 per gate
        assert result.fidelity_estimate is not None
        assert result.fidelity_estimate < 1.0
        assert result.fidelity_estimate == pytest.approx(0.98, abs=0.01)

    def test_entangled_merge_produces_counts(self, aggregator: ResultAggregator) -> None:
        plan = make_entangled_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-3-p0", partition_index=0,
                                     counts={"00": 800, "11": 200}, shots=1000)
        pr1 = make_partition_result(partition_id="job-3-p1", partition_index=1,
                                     counts={"00": 900, "11": 100}, shots=1000)
        result = aggregator.aggregate("job-3", [pr0, pr1], plan)
        assert len(result.final_counts) > 0
        assert result.total_shots > 0

    def test_entangled_merge_metadata_warns(self, aggregator: ResultAggregator) -> None:
        plan = make_entangled_two_partition_plan()
        pr0 = make_partition_result(partition_id="job-3-p0", partition_index=0,
                                     counts={"00": 500, "11": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="job-3-p1", partition_index=1,
                                     counts={"00": 500, "11": 500}, shots=1000)
        result = aggregator.aggregate("job-3", [pr0, pr1], plan)
        assert result.metadata.get("fidelity_degraded") is True


# ---------------------------------------------------------------------------
# Fallback merge (no plan)
# ---------------------------------------------------------------------------

class TestFallbackMerge:
    """Two partitions without a plan — conservative fallback."""

    def test_fallback_merge_low_fidelity(self, aggregator: ResultAggregator) -> None:
        pr0 = make_partition_result(partition_id="p0", partition_index=0,
                                     counts={"0": 1000}, shots=1000)
        pr1 = make_partition_result(partition_id="p1", partition_index=1,
                                     counts={"0": 1000}, shots=1000)
        result = aggregator.aggregate("job-fb", [pr0, pr1], partition_plan=None)
        assert result.fidelity_estimate is not None
        assert result.fidelity_estimate <= 0.5

    def test_fallback_merge_method(self, aggregator: ResultAggregator) -> None:
        pr0 = make_partition_result(partition_id="p0", partition_index=0,
                                     counts={"0": 500, "1": 500}, shots=1000)
        pr1 = make_partition_result(partition_id="p1", partition_index=1,
                                     counts={"0": 500, "1": 500}, shots=1000)
        result = aggregator.aggregate("job-fb", [pr0, pr1], partition_plan=None)
        assert "fallback" in result.aggregation_method

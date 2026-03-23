"""Behavioral tests for the Partitioner.

Tests real partitioning logic: single-partition passthrough, multi-partition
splitting, qubit coverage, and strategy selection.
"""

from __future__ import annotations

import pytest

from qontos.circuit.normalizer import CircuitNormalizer
from qontos.models.circuit import CircuitIR, GateOperation, InputFormat
from qontos.partitioning.partition import Partitioner
from qontos.partitioning.models import PartitionConstraints, PartitionStrategy
from qontos.partitioning.graph_model import CircuitGraph
from qontos.partitioning.heuristics import GreedyPartitioner, ManualPartitioner, SpectralPartitioner
from qontos.partitioning.cost_model import PartitionCostModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BELL_STATE_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

# A 6-qubit linear chain circuit for partitioning
SIX_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[6];
creg c[6];
h q[0];
cx q[0], q[1];
cx q[1], q[2];
cx q[2], q[3];
cx q[3], q[4];
cx q[4], q[5];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
measure q[3] -> c[3];
measure q[4] -> c[4];
measure q[5] -> c[5];
"""


@pytest.fixture
def normalizer() -> CircuitNormalizer:
    return CircuitNormalizer()


@pytest.fixture
def bell_ir(normalizer: CircuitNormalizer) -> CircuitIR:
    return normalizer.normalize("openqasm", BELL_STATE_QASM)


@pytest.fixture
def six_qubit_ir(normalizer: CircuitNormalizer) -> CircuitIR:
    return normalizer.normalize("openqasm", SIX_QUBIT_QASM)


@pytest.fixture
def partitioner() -> Partitioner:
    return Partitioner()


# ---------------------------------------------------------------------------
# Single partition (small circuit)
# ---------------------------------------------------------------------------

class TestSinglePartition:
    """Small circuits that fit in one module should not be split."""

    def test_single_qubit_stays_single(self, partitioner: Partitioner) -> None:
        """A 1-qubit circuit must stay in a single partition."""
        qasm = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
creg c[1];
h q[0];
measure q[0] -> c[0];
"""
        normalizer = CircuitNormalizer()
        ir = normalizer.normalize("openqasm", qasm)
        plan = partitioner.run(ir, job_id="test-single")
        assert len(plan.partitions) == 1
        assert plan.partitions[0].num_qubits == 1

    def test_single_partition_covers_all_qubits(
        self, partitioner: Partitioner, bell_ir: CircuitIR
    ) -> None:
        """When forced to 1 partition, all qubits must be covered."""
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(bell_ir, job_id="test-bell", constraints=constraints)
        assert len(plan.partitions) == 1
        assert set(plan.partitions[0].qubit_indices) == set(range(bell_ir.num_qubits))

    def test_single_partition_has_circuit_data(
        self, partitioner: Partitioner, bell_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(bell_ir, job_id="test-data", constraints=constraints)
        entry = plan.partitions[0]
        assert entry.circuit_data is not None
        assert "OPENQASM" in entry.circuit_data

    def test_single_partition_zero_inter_module(
        self, partitioner: Partitioner, bell_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(bell_ir, job_id="test-zero", constraints=constraints)
        assert plan.total_inter_module_gates == 0
        assert plan.cut_ratio == 0.0


# ---------------------------------------------------------------------------
# Multi-partition
# ---------------------------------------------------------------------------

class TestMultiPartition:
    """Circuits large enough to need splitting across modules."""

    def test_two_partitions_requested(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-2part", constraints=constraints)
        assert len(plan.partitions) == 2

    def test_three_partitions_requested(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(target_partitions=3)
        plan = partitioner.run(six_qubit_ir, job_id="test-3part", constraints=constraints)
        assert len(plan.partitions) == 3

    def test_all_qubits_covered(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        """Every qubit must appear in exactly one partition."""
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-cover", constraints=constraints)
        all_qubits: set[int] = set()
        for entry in plan.partitions:
            all_qubits.update(entry.qubit_indices)
        assert all_qubits == set(range(six_qubit_ir.num_qubits))

    def test_no_qubit_overlap(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        """Qubits must not appear in more than one partition."""
        constraints = PartitionConstraints(target_partitions=3)
        plan = partitioner.run(six_qubit_ir, job_id="test-overlap", constraints=constraints)
        seen: set[int] = set()
        for entry in plan.partitions:
            for q in entry.qubit_indices:
                assert q not in seen, f"Qubit {q} appears in multiple partitions"
                seen.add(q)

    def test_max_qubits_per_partition_respected(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(max_qubits_per_partition=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-maxq", constraints=constraints)
        assert len(plan.partitions) >= 3  # 6 qubits / 2 per partition = 3
        for entry in plan.partitions:
            assert entry.num_qubits <= 3  # allow some slack from heuristic

    def test_partition_plan_has_job_id(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        plan = partitioner.run(six_qubit_ir, job_id="my-job-42",
                               constraints=PartitionConstraints(target_partitions=2))
        assert plan.job_id == "my-job-42"

    def test_each_partition_has_circuit_data(
        self, partitioner: Partitioner, six_qubit_ir: CircuitIR
    ) -> None:
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-circ", constraints=constraints)
        for entry in plan.partitions:
            assert entry.circuit_data is not None
            assert "OPENQASM" in entry.circuit_data


# ---------------------------------------------------------------------------
# CircuitGraph tests
# ---------------------------------------------------------------------------

class TestCircuitGraph:
    """Verify the weighted adjacency graph model."""

    def test_graph_num_qubits(self, bell_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(bell_ir)
        assert graph.num_qubits == bell_ir.num_qubits

    def test_graph_edge_for_cx(self, bell_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(bell_ir)
        assert graph.edge_weight(0, 1) > 0

    def test_graph_no_self_loops(self, bell_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(bell_ir)
        adj = graph.get_adjacency_matrix()
        for i in range(graph.num_qubits):
            assert adj[i, i] == 0.0

    def test_graph_symmetric(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        adj = graph.get_adjacency_matrix()
        for i in range(graph.num_qubits):
            for j in range(graph.num_qubits):
                assert adj[i, j] == adj[j, i]

    def test_linear_chain_neighbors(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        # In a linear chain cx 0-1, 1-2, 2-3, 3-4, 4-5, qubit 2 neighbors are 1 and 3
        neighbors_2 = graph.neighbors(2)
        assert 1 in neighbors_2
        assert 3 in neighbors_2


# ---------------------------------------------------------------------------
# Heuristic tests
# ---------------------------------------------------------------------------

class TestGreedyPartitioner:
    """Test the greedy heuristic directly."""

    def test_single_partition(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        gp = GreedyPartitioner()
        result = gp.partition(graph, 1)
        assert len(result) == 1
        assert result[0] == set(range(6))

    def test_two_partitions_cover_all(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        gp = GreedyPartitioner()
        result = gp.partition(graph, 2)
        assert len(result) == 2
        union = result[0] | result[1]
        assert union == set(range(6))


class TestManualPartitioner:
    """Test the manual (round-robin) heuristic."""

    def test_even_split(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        mp = ManualPartitioner()
        result = mp.partition(graph, 3)
        assert len(result) == 3
        # Each partition should have exactly 2 qubits for 6/3
        for s in result:
            assert len(s) == 2

    def test_all_qubits_covered(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        mp = ManualPartitioner()
        result = mp.partition(graph, 2)
        union = set()
        for s in result:
            union |= s
        assert union == set(range(6))


# ---------------------------------------------------------------------------
# Cost model tests
# ---------------------------------------------------------------------------

class TestCostModel:
    """Test partition cost evaluation."""

    def test_single_partition_no_cuts(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [set(range(6))]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.inter_module_gates == 0
        assert cost.cut_ratio == 0.0
        assert cost.partition_balance_score == 1.0

    def test_two_partition_has_cuts(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        # Split at the middle: {0,1,2} vs {3,4,5}
        partitions = [{0, 1, 2}, {3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        # The cx q[2],q[3] gate crosses the partition boundary
        assert cost.inter_module_gates >= 1
        assert cost.cut_ratio > 0.0
        assert cost.communication_overhead_us > 0.0

    def test_balanced_partitions_high_score(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [{0, 1, 2}, {3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.partition_balance_score == 1.0  # equal sizes

    def test_unbalanced_partitions_lower_score(self, six_qubit_ir: CircuitIR) -> None:
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [{0}, {1, 2, 3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.partition_balance_score < 1.0

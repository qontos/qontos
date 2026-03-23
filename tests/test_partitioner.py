"""QGH-3005: Partitioning and Scheduling Proof Suite — Partitioner behavior tests.

Tests real partitioning logic: greedy, spectral, manual strategies,
qubit coverage, dependency tracking, cost model scoring, and sub-circuit extraction.
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

FOUR_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[4];
creg c[4];
h q[0];
cx q[0], q[1];
h q[2];
cx q[2], q[3];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
measure q[3] -> c[3];
"""

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

TEN_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[10];
creg c[10];
""" + "\n".join(f"h q[{i}];" for i in range(10)) + "\n" + "\n".join(f"cx q[{i}],q[{i+1}];" for i in range(9)) + "\n"


def _make_large_qasm(n: int) -> str:
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{n}];', f'creg c[{n}];']
    for i in range(n):
        lines.append(f"h q[{i}];")
    for i in range(n - 1):
        lines.append(f"cx q[{i}],q[{i+1}];")
    return "\n".join(lines) + "\n"


@pytest.fixture
def normalizer():
    return CircuitNormalizer()


@pytest.fixture
def bell_ir(normalizer):
    return normalizer.normalize("openqasm", BELL_STATE_QASM)


@pytest.fixture
def four_qubit_ir(normalizer):
    return normalizer.normalize("openqasm", FOUR_QUBIT_QASM)


@pytest.fixture
def six_qubit_ir(normalizer):
    return normalizer.normalize("openqasm", SIX_QUBIT_QASM)


@pytest.fixture
def ten_qubit_ir(normalizer):
    return normalizer.normalize("openqasm", TEN_QUBIT_QASM)


@pytest.fixture
def partitioner():
    return Partitioner()


# ---------------------------------------------------------------------------
# 1. Greedy partition on 4-qubit Bell circuit (expect 1 partition)
# ---------------------------------------------------------------------------


class TestGreedyBellCircuit:
    def test_greedy_on_bell_single_partition(self, partitioner, bell_ir):
        """A 2-qubit Bell circuit should stay in 1 partition (below split threshold)."""
        plan = partitioner.run(bell_ir, job_id="test-bell")
        assert len(plan.partitions) == 1
        assert plan.total_inter_module_gates == 0

    def test_greedy_on_4q_two_bells_single_partition(self, partitioner, four_qubit_ir):
        """A 4-qubit circuit with 2 independent Bell pairs, forced single partition."""
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(four_qubit_ir, job_id="test-4q-single", constraints=constraints)
        assert len(plan.partitions) == 1
        assert set(plan.partitions[0].qubit_indices) == set(range(four_qubit_ir.num_qubits))


# ---------------------------------------------------------------------------
# 2. Greedy partition on 10-qubit circuit with 2-module constraint
# ---------------------------------------------------------------------------


class TestGreedy10QubitSplit:
    def test_greedy_10q_two_modules(self, partitioner, ten_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(ten_qubit_ir, job_id="test-10q-2p", constraints=constraints)
        assert len(plan.partitions) == 2
        # All qubits covered
        all_qubits = set()
        for p in plan.partitions:
            all_qubits.update(p.qubit_indices)
        assert all_qubits == set(range(10))


# ---------------------------------------------------------------------------
# 3. Spectral partition selected for >= 20 qubits
# ---------------------------------------------------------------------------


class TestSpectralAutoSelection:
    def test_spectral_selected_for_20q(self, normalizer, partitioner):
        qasm = _make_large_qasm(25)
        ir = normalizer.normalize("openqasm", qasm)
        constraints = PartitionConstraints(preferred_strategy=PartitionStrategy.AUTO, target_partitions=3)
        plan = partitioner.run(ir, job_id="test-spectral", constraints=constraints)
        assert plan.strategy == "spectral"
        assert len(plan.partitions) == 3


# ---------------------------------------------------------------------------
# 4. Manual partition with explicit qubit mapping
# ---------------------------------------------------------------------------


class TestManualPartition:
    def test_manual_even_split(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        mp = ManualPartitioner()
        result = mp.partition(graph, 3)
        assert len(result) == 3
        for s in result:
            assert len(s) == 2

    def test_manual_all_qubits_covered(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        mp = ManualPartitioner()
        result = mp.partition(graph, 2)
        union = set()
        for s in result:
            union |= s
        assert union == set(range(6))


# ---------------------------------------------------------------------------
# 5. Partition plan has correct qubit assignments
# ---------------------------------------------------------------------------


class TestQubitAssignments:
    def test_all_qubits_covered(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-cover", constraints=constraints)
        all_qubits = set()
        for entry in plan.partitions:
            all_qubits.update(entry.qubit_indices)
        assert all_qubits == set(range(six_qubit_ir.num_qubits))

    def test_no_qubit_overlap(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=3)
        plan = partitioner.run(six_qubit_ir, job_id="test-overlap", constraints=constraints)
        seen = set()
        for entry in plan.partitions:
            for q in entry.qubit_indices:
                assert q not in seen
                seen.add(q)


# ---------------------------------------------------------------------------
# 6. Inter-module gates tracked correctly
# ---------------------------------------------------------------------------


class TestInterModuleGates:
    def test_linear_chain_split_has_inter_module_gates(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-inter", constraints=constraints)
        # A linear chain split must have at least 1 inter-module gate
        assert plan.total_inter_module_gates >= 1

    def test_single_partition_zero_inter_module(self, partitioner, bell_ir):
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(bell_ir, job_id="test-no-inter", constraints=constraints)
        assert plan.total_inter_module_gates == 0


# ---------------------------------------------------------------------------
# 7. Dependency edges for cross-partition entanglement
# ---------------------------------------------------------------------------


class TestDependencyEdges:
    def test_dependencies_created_for_split(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-deps", constraints=constraints)
        # At least one dependency edge should exist for the cut
        assert len(plan.dependencies) >= 1

    def test_dependency_has_partition_references(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-dep-refs", constraints=constraints)
        if plan.dependencies:
            dep = plan.dependencies[0]
            assert dep.from_partition.startswith("test-dep-refs")
            assert dep.to_partition.startswith("test-dep-refs")


# ---------------------------------------------------------------------------
# 8. Cost model scores partition balance
# ---------------------------------------------------------------------------


class TestCostModelBalance:
    def test_balanced_partition_score(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [{0, 1, 2}, {3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.partition_balance_score == 1.0

    def test_unbalanced_partition_lower_score(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [{0}, {1, 2, 3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.partition_balance_score < 1.0

    def test_cut_ratio_positive_for_split(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [{0, 1, 2}, {3, 4, 5}]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.cut_ratio > 0.0

    def test_single_partition_no_cuts(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        cost_model = PartitionCostModel()
        partitions = [set(range(6))]
        cost = cost_model.evaluate(graph, partitions)
        assert cost.inter_module_gates == 0
        assert cost.cut_ratio == 0.0


# ---------------------------------------------------------------------------
# 9. Sub-circuit QASM extraction preserves gate semantics
# ---------------------------------------------------------------------------


class TestSubcircuitExtraction:
    def test_subcircuit_has_openqasm_header(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-sub", constraints=constraints)
        for entry in plan.partitions:
            assert entry.circuit_data is not None
            assert "OPENQASM 2.0;" in entry.circuit_data
            assert "qreg" in entry.circuit_data

    def test_subcircuit_local_qubit_count(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=2)
        plan = partitioner.run(six_qubit_ir, job_id="test-local", constraints=constraints)
        for entry in plan.partitions:
            qasm = entry.circuit_data
            assert f"qreg q[{entry.num_qubits}];" in qasm

    def test_subcircuit_contains_gates(self, partitioner, six_qubit_ir):
        constraints = PartitionConstraints(target_partitions=1)
        plan = partitioner.run(six_qubit_ir, job_id="test-gates", constraints=constraints)
        qasm = plan.partitions[0].circuit_data
        assert "h " in qasm or "h q" in qasm
        assert "cx " in qasm or "cx q" in qasm


# ---------------------------------------------------------------------------
# CircuitGraph tests
# ---------------------------------------------------------------------------


class TestCircuitGraph:
    def test_graph_num_qubits(self, bell_ir):
        graph = CircuitGraph.from_circuit_ir(bell_ir)
        assert graph.num_qubits == bell_ir.num_qubits

    def test_graph_edge_for_cx(self, bell_ir):
        graph = CircuitGraph.from_circuit_ir(bell_ir)
        assert graph.edge_weight(0, 1) > 0

    def test_graph_symmetric(self, six_qubit_ir):
        graph = CircuitGraph.from_circuit_ir(six_qubit_ir)
        adj = graph.get_adjacency_matrix()
        for i in range(graph.num_qubits):
            for j in range(graph.num_qubits):
                assert adj[i, j] == adj[j, i]

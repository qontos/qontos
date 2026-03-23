"""Reusable test fixtures and sample data for the QONTOS test suite."""

from __future__ import annotations

from qontos.models.circuit import CircuitIR, GateOperation, InputFormat
from qontos.models.partition import PartitionPlan, PartitionEntry, DependencyEdge
from qontos.models.result import RunResult, PartitionResult
from qontos.models.backend import BackendCapability, BackendStatus
from qontos.models.execution import ExecutionManifest, ExecutionConstraints


# ---------------------------------------------------------------------------
# QASM Circuits
# ---------------------------------------------------------------------------

BELL_CIRCUIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

GHZ3_CIRCUIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
creg c[3];
h q[0];
cx q[0],q[1];
cx q[1],q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
"""

QASM3_BELL_CIRCUIT = """\
OPENQASM 3;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c[0] = measure q[0];
c[1] = measure q[1];
"""

PENNYLANE_BELL_JSON = '{"num_wires": 2, "operations": [{"name": "Hadamard", "wires": [0], "params": []}, {"name": "CNOT", "wires": [0, 1], "params": []}]}'

MALFORMED_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
INVALID_GATE q[0];
"""

# ---------------------------------------------------------------------------
# Sample CircuitIR instances
# ---------------------------------------------------------------------------


def make_bell_circuit_ir() -> CircuitIR:
    """A 2-qubit Bell state circuit IR."""
    return CircuitIR(
        num_qubits=2,
        num_clbits=2,
        depth=2,
        gate_count=4,
        gates=[
            GateOperation(name="h", qubits=[0]),
            GateOperation(name="cx", qubits=[0, 1]),
            GateOperation(name="measure", qubits=[0]),
            GateOperation(name="measure", qubits=[1]),
        ],
        qubit_connectivity=[(0, 1)],
        source_type=InputFormat.OPENQASM,
        circuit_hash="bell_hash_abc123",
        qasm_string=BELL_CIRCUIT_QASM,
    )


def make_ghz3_circuit_ir() -> CircuitIR:
    """A 3-qubit GHZ state circuit IR."""
    return CircuitIR(
        num_qubits=3,
        num_clbits=3,
        depth=3,
        gate_count=6,
        gates=[
            GateOperation(name="h", qubits=[0]),
            GateOperation(name="cx", qubits=[0, 1]),
            GateOperation(name="cx", qubits=[1, 2]),
            GateOperation(name="measure", qubits=[0]),
            GateOperation(name="measure", qubits=[1]),
            GateOperation(name="measure", qubits=[2]),
        ],
        qubit_connectivity=[(0, 1), (1, 2)],
        source_type=InputFormat.OPENQASM,
        circuit_hash="ghz3_hash_def456",
        qasm_string=GHZ3_CIRCUIT_QASM,
    )


def make_large_circuit_ir(num_qubits: int = 100) -> CircuitIR:
    """A large circuit with linear entanglement for stress testing."""
    gates = []
    connectivity = []
    for q in range(num_qubits):
        gates.append(GateOperation(name="h", qubits=[q]))
    for q in range(num_qubits - 1):
        gates.append(GateOperation(name="cx", qubits=[q, q + 1]))
        connectivity.append((q, q + 1))
    for q in range(num_qubits):
        gates.append(GateOperation(name="measure", qubits=[q]))
    return CircuitIR(
        num_qubits=num_qubits,
        num_clbits=num_qubits,
        depth=3,
        gate_count=len(gates),
        gates=gates,
        qubit_connectivity=connectivity,
        source_type=InputFormat.OPENQASM,
        circuit_hash=f"large_{num_qubits}_hash",
    )


def make_10q_linear_circuit_ir() -> CircuitIR:
    """A 10-qubit linearly entangled circuit."""
    return make_large_circuit_ir(10)


# ---------------------------------------------------------------------------
# Sample PartitionPlan
# ---------------------------------------------------------------------------


def make_sample_partition_plan(job_id: str = "job-test-01") -> PartitionPlan:
    """A 2-partition plan splitting a 4-qubit circuit into [0,1] and [2,3]."""
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
                circuit_data="OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\n",
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1",
                partition_index=1,
                qubit_indices=[2, 3],
                num_qubits=2,
                gate_count=3,
                depth=2,
                qubit_mapping={2: 0, 3: 1},
                circuit_data="OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\n",
            ),
        ],
        dependencies=[],
        total_inter_module_gates=0,
        estimated_module_count=2,
        partition_balance_score=1.0,
        cut_ratio=0.0,
    )


def make_entangled_partition_plan(job_id: str = "job-ent-01") -> PartitionPlan:
    """A 2-partition plan with inter-module dependencies (entangled)."""
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
                inter_module_gates=1,
                boundary_qubits=[1],
            ),
            PartitionEntry(
                partition_id=f"{job_id}-p1",
                partition_index=1,
                qubit_indices=[2, 3],
                num_qubits=2,
                gate_count=3,
                depth=2,
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
            ),
        ],
        total_inter_module_gates=1,
        estimated_module_count=2,
        partition_balance_score=1.0,
        cut_ratio=0.5,
    )


# ---------------------------------------------------------------------------
# Sample RunResult
# ---------------------------------------------------------------------------


def make_sample_run_result(job_id: str = "job-test-01") -> RunResult:
    """A completed RunResult with Bell-state counts."""
    return RunResult(
        job_id=job_id,
        status="completed",
        final_counts={"00": 2048, "11": 2048},
        total_shots=4096,
        fidelity_estimate=0.98,
        cost_usd=0.05,
        latency_ms=1200.0,
        partition_results=[
            PartitionResult(
                partition_id=f"{job_id}-p0",
                partition_index=0,
                backend_id="sim-1",
                backend_name="local-simulator",
                provider="local_simulator",
                counts={"00": 2048, "11": 2048},
                shots_completed=4096,
                execution_time_ms=1200.0,
                cost_usd=0.05,
            ),
        ],
        aggregation_method="passthrough",
        proof_hash="abc123",
    )


def make_partition_result(
    partition_id: str = "p0",
    partition_index: int = 0,
    counts: dict[str, int] | None = None,
) -> PartitionResult:
    """Create a single PartitionResult for testing."""
    return PartitionResult(
        partition_id=partition_id,
        partition_index=partition_index,
        backend_id="sim-1",
        backend_name="local-simulator",
        provider="local_simulator",
        counts=counts or {"00": 2048, "11": 2048},
        shots_completed=sum((counts or {"00": 2048, "11": 2048}).values()),
        execution_time_ms=500.0,
        cost_usd=0.01,
    )


# ---------------------------------------------------------------------------
# Mock Backends
# ---------------------------------------------------------------------------


MOCK_BACKENDS: list[BackendCapability] = [
    BackendCapability(
        id="sim-aer-32",
        name="Aer Simulator 32Q",
        provider="local_simulator",
        backend_type="simulator",
        status=BackendStatus.AVAILABLE,
        num_qubits=32,
        max_shots=100000,
        avg_gate_fidelity_1q=1.0,
        avg_gate_fidelity_2q=1.0,
        avg_readout_fidelity=1.0,
        queue_depth=0,
        cost_per_shot=0.0,
    ),
    BackendCapability(
        id="ibm-lagos-7",
        name="IBM Lagos 7Q",
        provider="ibm",
        backend_type="hardware",
        status=BackendStatus.AVAILABLE,
        num_qubits=7,
        max_shots=100000,
        avg_gate_fidelity_1q=0.9995,
        avg_gate_fidelity_2q=0.99,
        avg_readout_fidelity=0.97,
        queue_depth=3,
        cost_per_shot=0.001,
    ),
    BackendCapability(
        id="ibm-brisbane-127",
        name="IBM Brisbane 127Q",
        provider="ibm",
        backend_type="hardware",
        status=BackendStatus.AVAILABLE,
        num_qubits=127,
        max_shots=100000,
        avg_gate_fidelity_1q=0.999,
        avg_gate_fidelity_2q=0.985,
        avg_readout_fidelity=0.96,
        queue_depth=12,
        cost_per_shot=0.005,
    ),
    BackendCapability(
        id="braket-sv1-34",
        name="AWS Braket SV1",
        provider="braket",
        backend_type="simulator",
        status=BackendStatus.AVAILABLE,
        num_qubits=34,
        max_shots=100000,
        avg_gate_fidelity_1q=1.0,
        avg_gate_fidelity_2q=1.0,
        avg_readout_fidelity=1.0,
        queue_depth=0,
        cost_per_shot=0.0003,
    ),
    BackendCapability(
        id="ibm-offline-5",
        name="IBM Offline 5Q",
        provider="ibm",
        backend_type="hardware",
        status=BackendStatus.OFFLINE,
        num_qubits=5,
        max_shots=100000,
        avg_gate_fidelity_1q=0.998,
        avg_gate_fidelity_2q=0.97,
        avg_readout_fidelity=0.95,
        queue_depth=0,
        cost_per_shot=0.0008,
    ),
]


def make_sample_manifest(job_id: str = "job-test-01") -> ExecutionManifest:
    """Create a sample ExecutionManifest for testing."""
    return ExecutionManifest(
        job_id=job_id,
        user_id="user-001",
        name="Test Job",
        input_type="openqasm",
        circuit_hash="abc123def456",
        num_qubits=2,
        circuit_depth=2,
        gate_count=4,
        shots=4096,
        constraints=ExecutionConstraints(),
    )

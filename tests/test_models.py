"""Tests for QONTOS data models — ensures all public schemas import and validate."""

from qontos.models.circuit import CircuitIR, GateOperation, InputFormat


class TestCircuitIR:
    def test_create_minimal(self):
        ir = CircuitIR(
            num_qubits=2,
            depth=1,
            gate_count=1,
            gates=[GateOperation(name="h", qubits=[0])],
            source_type=InputFormat.OPENQASM,
        )
        assert ir.num_qubits == 2
        assert ir.depth == 1
        assert len(ir.gates) == 1

    def test_gate_operation(self):
        gate = GateOperation(name="cx", qubits=[0, 1])
        assert gate.name == "cx"
        assert gate.qubits == [0, 1]
        assert gate.params == []
        assert gate.is_inter_module is False

    def test_input_formats(self):
        assert InputFormat.QISKIT.value == "qiskit"
        assert InputFormat.OPENQASM.value == "openqasm"
        assert InputFormat.PENNYLANE.value == "pennylane"

    def test_circuit_hash_default_empty(self):
        ir = CircuitIR(
            num_qubits=1,
            depth=1,
            gate_count=1,
            gates=[GateOperation(name="h", qubits=[0])],
            source_type=InputFormat.QISKIT,
        )
        assert ir.circuit_hash == ""

    def test_qubit_connectivity(self):
        ir = CircuitIR(
            num_qubits=3,
            depth=2,
            gate_count=2,
            gates=[
                GateOperation(name="h", qubits=[0]),
                GateOperation(name="cx", qubits=[0, 1]),
            ],
            qubit_connectivity=[(0, 1)],
            source_type=InputFormat.OPENQASM,
        )
        assert ir.qubit_connectivity == [(0, 1)]

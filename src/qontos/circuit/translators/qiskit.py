"""Qiskit circuit translator — converts CircuitIR to/from Qiskit QuantumCircuit."""

from __future__ import annotations

from qiskit import QuantumCircuit, transpile

from qontos.models.circuit import CircuitIR


def circuit_ir_to_qiskit(circuit_ir: CircuitIR) -> QuantumCircuit:
    """Convert CircuitIR to Qiskit QuantumCircuit."""
    if circuit_ir.qasm_string:
        qc = QuantumCircuit.from_qasm_str(circuit_ir.qasm_string)
    else:
        qc = QuantumCircuit(circuit_ir.num_qubits)
        for gate in circuit_ir.gates:
            if hasattr(qc, gate.name):
                getattr(qc, gate.name)(*gate.params, *gate.qubits)
    return qc


def qiskit_to_circuit_ir(qc: QuantumCircuit) -> dict:
    """Extract gate-level info from a Qiskit QuantumCircuit."""
    gates = []
    connectivity = []
    for inst in qc.data:
        op = inst.operation
        qubits = [qc.qubits.index(q) for q in inst.qubits]
        gates.append({
            "name": op.name,
            "qubits": qubits,
            "params": [float(p) for p in op.params] if op.params else [],
        })
        if len(qubits) == 2:
            edge = tuple(sorted(qubits))
            if edge not in connectivity:
                connectivity.append(edge)
    return {
        "num_qubits": qc.num_qubits,
        "num_clbits": qc.num_clbits,
        "depth": qc.depth(),
        "gate_count": len(gates),
        "gates": gates,
        "connectivity": connectivity,
    }


def transpile_for_backend(qc: QuantumCircuit, backend, optimization_level: int = 1) -> QuantumCircuit:
    """Transpile circuit for a specific backend."""
    return transpile(qc, backend, optimization_level=optimization_level)

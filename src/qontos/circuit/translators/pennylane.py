"""PennyLane translator — converts CircuitIR to/from PennyLane tape format."""

from __future__ import annotations

import json
from qontos.models.circuit import CircuitIR

# Bidirectional gate name mapping
QISKIT_TO_PL = {
    "h": "Hadamard", "x": "PauliX", "y": "PauliY", "z": "PauliZ",
    "cx": "CNOT", "cz": "CZ", "swap": "SWAP",
    "rx": "RX", "ry": "RY", "rz": "RZ",
    "t": "T", "s": "S", "ccx": "Toffoli",
}

PL_TO_QISKIT = {v: k for k, v in QISKIT_TO_PL.items()}


def circuit_ir_to_pennylane_ops(circuit_ir: CircuitIR) -> list[dict]:
    """Convert CircuitIR gates to PennyLane operations format."""
    ops = []
    for gate in circuit_ir.gates:
        pl_name = QISKIT_TO_PL.get(gate.name, gate.name)
        ops.append({"name": pl_name, "wires": gate.qubits, "params": gate.params})
    return ops


def circuit_ir_to_pennylane_json(circuit_ir: CircuitIR) -> str:
    """Serialize CircuitIR to PennyLane JSON tape format."""
    return json.dumps({
        "num_wires": circuit_ir.num_qubits,
        "operations": circuit_ir_to_pennylane_ops(circuit_ir),
    })


def pennylane_json_to_gate_list(tape_json: str) -> tuple[int, list[dict]]:
    """Parse PennyLane JSON tape into (num_wires, gate_list)."""
    data = json.loads(tape_json)
    num_wires = data["num_wires"]
    gates = []
    for op in data.get("operations", []):
        gate_name = PL_TO_QISKIT.get(op["name"], op["name"].lower())
        gates.append({
            "name": gate_name,
            "qubits": op["wires"],
            "params": op.get("params", []),
        })
    return num_wires, gates

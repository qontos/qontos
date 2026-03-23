"""Metadata extraction — enriches CircuitIR with analysis metadata."""

from __future__ import annotations

from qontos.models.circuit import CircuitIR


def extract_metadata(circuit_ir: CircuitIR) -> dict:
    """Extract rich metadata from a circuit for downstream decisions."""
    single_q = sum(1 for g in circuit_ir.gates if len(g.qubits) == 1)
    two_q = sum(1 for g in circuit_ir.gates if len(g.qubits) == 2)
    multi_q = sum(1 for g in circuit_ir.gates if len(g.qubits) > 2)

    gate_types = {}
    for g in circuit_ir.gates:
        gate_types[g.name] = gate_types.get(g.name, 0) + 1

    # Entanglement density: fraction of 2Q gates
    entanglement_density = two_q / max(1, circuit_ir.gate_count)

    # Parallelism: gates_per_layer ratio
    parallelism = circuit_ir.gate_count / max(1, circuit_ir.depth)

    return {
        "single_qubit_gates": single_q,
        "two_qubit_gates": two_q,
        "multi_qubit_gates": multi_q,
        "gate_type_distribution": gate_types,
        "entanglement_density": round(entanglement_density, 4),
        "parallelism_ratio": round(parallelism, 4),
        "unique_gate_types": len(gate_types),
        "connectivity_edges": len(circuit_ir.qubit_connectivity),
        "has_measurements": any(g.name == "measure" for g in circuit_ir.gates),
    }

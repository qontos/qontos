"""Circuit validators — validates circuits before they enter the pipeline."""

from __future__ import annotations

from qontos.models.circuit import CircuitIR


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation error on '{field}': {message}")


class CircuitValidator:
    """Validates circuit IR against platform constraints."""

    def __init__(self, max_qubits: int = 10000, max_depth: int = 100000, max_gates: int = 1000000):
        self.max_qubits = max_qubits
        self.max_depth = max_depth
        self.max_gates = max_gates

    def validate(self, circuit: CircuitIR) -> list[str]:
        """Validate a circuit. Returns list of warnings. Raises on hard errors."""
        warnings = []

        if circuit.num_qubits < 1:
            raise ValidationError("num_qubits", "Must have at least 1 qubit")
        if circuit.num_qubits > self.max_qubits:
            raise ValidationError("num_qubits", f"Exceeds max {self.max_qubits}")
        if circuit.gate_count > self.max_gates:
            raise ValidationError("gate_count", f"Exceeds max {self.max_gates}")

        for gate in circuit.gates:
            for q in gate.qubits:
                if q < 0 or q >= circuit.num_qubits:
                    raise ValidationError("gate_qubits", f"Gate '{gate.name}' references invalid qubit {q}")

        if circuit.depth > 1000:
            warnings.append(f"High circuit depth ({circuit.depth}) — may decohere on real hardware")

        two_q = sum(1 for g in circuit.gates if len(g.qubits) >= 2)
        if two_q > circuit.gate_count * 0.7:
            warnings.append("Heavily entangled circuit (>70% two-qubit gates)")

        return warnings

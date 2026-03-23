"""Circuit Normalizer — the main entry point for circuit ingestion.

Converts any supported input format into a canonical CircuitIR + ExecutionManifest.
This is the gateway to the entire QONTOS pipeline.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from qiskit import QuantumCircuit

from qontos.models.circuit import CircuitIR, GateOperation, InputFormat
from qontos.models.execution import ExecutionManifest, ExecutionConstraints
from qontos.circuit.validators import CircuitValidator
from qontos.circuit.metadata import extract_metadata


class CircuitNormalizer:
    """Normalizes circuits from any supported format into CircuitIR."""

    def __init__(self):
        self.validator = CircuitValidator()

    def normalize(self, input_type: str, source: str) -> CircuitIR:
        """Universal entry point — normalizes any circuit format to CircuitIR."""
        if input_type in ("qiskit", "openqasm"):
            return self._from_qasm(source, input_type)
        elif input_type == "pennylane":
            return self._from_pennylane(source)
        else:
            raise ValueError(f"Unsupported input type: {input_type}")

    def normalize_to_manifest(
        self,
        input_type: str,
        source: str,
        user_id: str,
        name: str = "untitled",
        project_id: str | None = None,
        shots: int = 4096,
        constraints: ExecutionConstraints | None = None,
        objective: str = "general",
    ) -> tuple[CircuitIR, ExecutionManifest]:
        """Full ingest: normalize circuit + build ExecutionManifest."""
        circuit_ir = self.normalize(input_type, source)

        # Validate
        warnings = self.validator.validate(circuit_ir)

        # Build manifest
        manifest = ExecutionManifest(
            job_id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            name=name,
            objective=objective,
            input_type=input_type,
            circuit_hash=circuit_ir.circuit_hash,
            num_qubits=circuit_ir.num_qubits,
            circuit_depth=circuit_ir.depth,
            gate_count=circuit_ir.gate_count,
            shots=shots,
            constraints=constraints or ExecutionConstraints(),
            created_at=datetime.now(timezone.utc),
            circuit_inline=source,
        )

        # Attach metadata
        circuit_ir.metadata = extract_metadata(circuit_ir)
        if warnings:
            circuit_ir.metadata["validation_warnings"] = warnings

        return circuit_ir, manifest

    def _from_qasm(self, qasm_string: str, source_type: str) -> CircuitIR:
        """Parse QASM string into CircuitIR."""
        from qiskit.qasm3 import loads as qasm3_loads

        if qasm_string.strip().startswith("OPENQASM 3"):
            qc = qasm3_loads(qasm_string)
        else:
            qc = QuantumCircuit.from_qasm_str(qasm_string)
        return self._qiskit_to_ir(qc, source_type, qasm_string)

    def _from_pennylane(self, tape_json: str) -> CircuitIR:
        """Parse PennyLane JSON tape into CircuitIR."""
        from qontos.circuit.translators.pennylane import pennylane_json_to_gate_list

        num_wires, gates = pennylane_json_to_gate_list(tape_json)

        gate_ops = [GateOperation(name=g["name"], qubits=g["qubits"], params=g.get("params", [])) for g in gates]
        connectivity = []
        for g in gate_ops:
            if len(g.qubits) == 2:
                edge = tuple(sorted(g.qubits))
                if edge not in connectivity:
                    connectivity.append(edge)

        # Build Qiskit circuit for QASM generation
        qc = QuantumCircuit(num_wires)
        for g in gate_ops:
            if hasattr(qc, g.name):
                getattr(qc, g.name)(*g.params, *g.qubits)

        canonical = json.dumps(
            {"num_qubits": num_wires, "gates": [g.model_dump() for g in gate_ops]},
            sort_keys=True,
        )

        return CircuitIR(
            num_qubits=num_wires,
            num_clbits=0,
            depth=qc.depth(),
            gate_count=len(gate_ops),
            gates=gate_ops,
            qubit_connectivity=connectivity,
            source_type=InputFormat.PENNYLANE,
            circuit_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            qasm_string=qc.qasm(),
        )

    def _qiskit_to_ir(self, qc: QuantumCircuit, source_type: str, qasm_string: str | None = None) -> CircuitIR:
        """Convert Qiskit QuantumCircuit to CircuitIR."""
        gates = []
        connectivity = []

        for inst in qc.data:
            op = inst.operation
            qubits = [qc.qubits.index(q) for q in inst.qubits]
            gates.append(GateOperation(
                name=op.name,
                qubits=qubits,
                params=[float(p) for p in op.params] if op.params else [],
            ))
            if len(qubits) == 2:
                edge = tuple(sorted(qubits))
                if edge not in connectivity:
                    connectivity.append(edge)

        canonical = json.dumps(
            {"num_qubits": qc.num_qubits, "gates": [g.model_dump() for g in gates]},
            sort_keys=True,
        )

        return CircuitIR(
            num_qubits=qc.num_qubits,
            num_clbits=qc.num_clbits,
            depth=qc.depth(),
            gate_count=len(gates),
            gates=gates,
            qubit_connectivity=connectivity,
            source_type=InputFormat(source_type if source_type != "qiskit" else "openqasm"),
            circuit_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            qasm_string=qasm_string or qc.qasm(),
        )

"""QGH-3004: Circuit Ingest Excellence — comprehensive normalization tests.

Tests real circuit ingestion, metadata extraction, hash determinism,
error handling for malformed inputs, and large circuit stress testing.
"""

from __future__ import annotations

import pytest

from qontos.circuit.normalizer import CircuitNormalizer
from qontos.circuit.validators import CircuitValidator, ValidationError
from qontos.circuit.metadata import extract_metadata
from qontos.models.circuit import CircuitIR, GateOperation, InputFormat


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

GHZ_3_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
creg c[3];
h q[0];
cx q[0], q[1];
cx q[0], q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
"""

SINGLE_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
creg c[1];
h q[0];
measure q[0] -> c[0];
"""

NO_MEASURE_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
h q[0];
cx q[0],q[1];
"""

PENNYLANE_BELL_JSON = '{"num_wires": 2, "operations": [{"name": "Hadamard", "wires": [0], "params": []}, {"name": "CNOT", "wires": [0, 1], "params": []}]}'


@pytest.fixture
def normalizer() -> CircuitNormalizer:
    return CircuitNormalizer()


# ---------------------------------------------------------------------------
# 1. Normalize valid QASM 2.0 Bell circuit
# ---------------------------------------------------------------------------


class TestBellStateNormalization:
    def test_bell_state_num_qubits(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.num_qubits == 2

    def test_bell_state_gate_count(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.gate_count == 4  # h, cx, measure, measure

    def test_bell_state_depth_positive(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.depth >= 1

    def test_bell_state_source_type(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.source_type == InputFormat.OPENQASM

    def test_bell_state_connectivity(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert len(ir.qubit_connectivity) >= 1
        assert (0, 1) in ir.qubit_connectivity

    def test_bell_state_qasm_string_preserved(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.qasm_string is not None
        assert len(ir.qasm_string) > 0

    def test_bell_state_gate_names(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        gate_names = [g.name for g in ir.gates]
        assert "h" in gate_names
        assert "cx" in gate_names
        assert "measure" in gate_names


# ---------------------------------------------------------------------------
# 2. Normalize valid QASM 3.0 circuit
# ---------------------------------------------------------------------------


class TestQASM30Normalization:
    def test_normalize_qasm3_bell(self, normalizer):
        qasm3 = """\
OPENQASM 3;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c[0] = measure q[0];
c[1] = measure q[1];
"""
        ir = normalizer.normalize("openqasm", qasm3)
        assert ir.num_qubits == 2
        assert ir.gate_count > 0


# ---------------------------------------------------------------------------
# 3. Normalize from Qiskit QuantumCircuit dict (via 'qiskit' input_type)
# ---------------------------------------------------------------------------


class TestQiskitInputType:
    def test_qiskit_input_type_routes_through_qasm(self, normalizer):
        ir = normalizer.normalize("qiskit", BELL_STATE_QASM)
        assert ir.num_qubits == 2
        assert ir.gate_count > 0


# ---------------------------------------------------------------------------
# 4. Normalize from PennyLane tape dict
# ---------------------------------------------------------------------------


class TestPennyLaneNormalization:
    def test_normalize_pennylane_bell(self, normalizer):
        ir = normalizer.normalize("pennylane", PENNYLANE_BELL_JSON)
        assert ir.num_qubits == 2
        assert ir.source_type == InputFormat.PENNYLANE
        assert ir.gate_count == 2
        assert len(ir.qubit_connectivity) >= 1


# ---------------------------------------------------------------------------
# 5. Metadata extraction (num_qubits, depth, gate_count, connectivity)
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    def test_metadata_keys_present(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        expected_keys = {
            "single_qubit_gates", "two_qubit_gates", "multi_qubit_gates",
            "gate_type_distribution", "entanglement_density", "parallelism_ratio",
            "unique_gate_types", "connectivity_edges", "has_measurements",
        }
        assert expected_keys.issubset(set(meta.keys()))

    def test_bell_state_has_measurements(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        assert meta["has_measurements"] is True

    def test_two_qubit_gate_count(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        assert meta["two_qubit_gates"] >= 1

    def test_single_qubit_no_entanglement(self, normalizer):
        ir = normalizer.normalize("openqasm", SINGLE_QUBIT_QASM)
        meta = extract_metadata(ir)
        assert meta["two_qubit_gates"] == 0
        assert meta["entanglement_density"] == 0.0

    def test_gate_type_distribution(self, normalizer):
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        meta = extract_metadata(ir)
        dist = meta["gate_type_distribution"]
        assert "h" in dist
        assert "cx" in dist
        assert dist["cx"] == 2


# ---------------------------------------------------------------------------
# 6. Deterministic circuit_hash
# ---------------------------------------------------------------------------


class TestCircuitHashDeterminism:
    def test_same_circuit_same_hash(self, normalizer):
        ir1 = normalizer.normalize("openqasm", BELL_STATE_QASM)
        ir2 = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir1.circuit_hash == ir2.circuit_hash

    def test_different_circuits_different_hash(self, normalizer):
        ir1 = normalizer.normalize("openqasm", BELL_STATE_QASM)
        ir2 = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir1.circuit_hash != ir2.circuit_hash

    def test_hash_is_sha256_hex(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert len(ir.circuit_hash) == 64
        assert all(c in "0123456789abcdef" for c in ir.circuit_hash)


# ---------------------------------------------------------------------------
# 7. Malformed QASM raises CircuitValidationError
# ---------------------------------------------------------------------------


class TestMalformedQASM:
    def test_invalid_gate_raises(self, normalizer):
        malformed = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\nINVALID_GATE q[0];\n'
        with pytest.raises(Exception):
            normalizer.normalize("openqasm", malformed)


# ---------------------------------------------------------------------------
# 8. Unsupported gate raises
# ---------------------------------------------------------------------------


class TestUnsupportedInput:
    def test_unsupported_input_type_raises_value_error(self, normalizer):
        with pytest.raises(ValueError, match="Unsupported input type"):
            normalizer.normalize("cirq", "some circuit")


# ---------------------------------------------------------------------------
# 9. Empty circuit handling
# ---------------------------------------------------------------------------


class TestEmptyCircuit:
    def test_zero_qubit_circuit_raises(self, normalizer):
        empty_qasm = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[0];\n'
        with pytest.raises(Exception):
            normalizer.normalize("openqasm", empty_qasm)


# ---------------------------------------------------------------------------
# 10. Large circuit (100+ qubits) metadata
# ---------------------------------------------------------------------------


class TestLargeCircuit:
    def test_large_circuit_normalization(self, normalizer):
        lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', 'qreg q[120];', 'creg c[120];']
        for i in range(120):
            lines.append(f"h q[{i}];")
        for i in range(119):
            lines.append(f"cx q[{i}],q[{i+1}];")
        qasm = "\n".join(lines) + "\n"
        ir = normalizer.normalize("openqasm", qasm)
        assert ir.num_qubits == 120
        assert ir.gate_count >= 239  # 120 h + 119 cx
        meta = extract_metadata(ir)
        assert meta["single_qubit_gates"] == 120
        assert meta["two_qubit_gates"] == 119


# ---------------------------------------------------------------------------
# 11. Qubit index out of bounds
# ---------------------------------------------------------------------------


class TestQubitOutOfBounds:
    def test_validator_catches_out_of_bounds(self):
        bad_ir = CircuitIR(
            num_qubits=2, depth=1, gate_count=1,
            gates=[GateOperation(name="h", qubits=[5])],
            source_type=InputFormat.OPENQASM,
        )
        validator = CircuitValidator()
        with pytest.raises(ValidationError, match="invalid qubit"):
            validator.validate(bad_ir)


# ---------------------------------------------------------------------------
# 12. Measurement placement validation
# ---------------------------------------------------------------------------


class TestMeasurementPlacement:
    def test_measurements_detected_in_metadata(self, normalizer):
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        assert meta["has_measurements"] is True

    def test_no_measurements_circuit(self, normalizer):
        ir = normalizer.normalize("openqasm", NO_MEASURE_QASM)
        meta = extract_metadata(ir)
        assert meta["has_measurements"] is False


# ---------------------------------------------------------------------------
# normalize_to_manifest tests
# ---------------------------------------------------------------------------


class TestNormalizeToManifest:
    def test_returns_ir_and_manifest(self, normalizer):
        ir, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm", source=BELL_STATE_QASM, user_id="test-user", name="bell-test",
        )
        assert ir.num_qubits == 2
        assert manifest.user_id == "test-user"
        assert manifest.name == "bell-test"

    def test_manifest_circuit_hash_matches_ir(self, normalizer):
        ir, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm", source=GHZ_3_QASM, user_id="test-user",
        )
        assert manifest.circuit_hash == ir.circuit_hash

    def test_manifest_has_job_id(self, normalizer):
        _, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm", source=BELL_STATE_QASM, user_id="test-user",
        )
        assert manifest.job_id is not None and len(manifest.job_id) > 0

    def test_ir_metadata_populated(self, normalizer):
        ir, _ = normalizer.normalize_to_manifest(
            input_type="openqasm", source=GHZ_3_QASM, user_id="test-user",
        )
        assert "single_qubit_gates" in ir.metadata
        assert "entanglement_density" in ir.metadata

    def test_custom_max_qubits_raises_on_validation(self, normalizer):
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        validator = CircuitValidator(max_qubits=2)
        with pytest.raises(ValidationError, match="Exceeds max"):
            validator.validate(ir)

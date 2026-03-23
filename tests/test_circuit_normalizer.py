"""Behavioral tests for CircuitNormalizer.

Tests real circuit ingestion, metadata extraction, and hash determinism
using valid OpenQASM 2.0 circuits (Bell state, GHZ).
"""

from __future__ import annotations

import pytest

from qontos.circuit.normalizer import CircuitNormalizer
from qontos.circuit.validators import CircuitValidator, ValidationError
from qontos.circuit.metadata import extract_metadata
from qontos.models.circuit import CircuitIR, InputFormat


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


@pytest.fixture
def normalizer() -> CircuitNormalizer:
    return CircuitNormalizer()


# ---------------------------------------------------------------------------
# Bell state tests
# ---------------------------------------------------------------------------

class TestBellStateNormalization:
    """Verify normalization of a 2-qubit Bell state circuit."""

    def test_bell_state_num_qubits(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.num_qubits == 2

    def test_bell_state_gate_count(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        # h, cx, measure, measure = 4 gates
        assert ir.gate_count == 4

    def test_bell_state_depth_positive(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.depth >= 1

    def test_bell_state_source_type(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.source_type == InputFormat.OPENQASM

    def test_bell_state_has_connectivity(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        # cx q[0], q[1] should produce a connectivity edge
        assert len(ir.qubit_connectivity) >= 1
        assert (0, 1) in ir.qubit_connectivity

    def test_bell_state_has_qasm_string(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir.qasm_string is not None
        assert len(ir.qasm_string) > 0

    def test_bell_state_gate_names(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        gate_names = [g.name for g in ir.gates]
        assert "h" in gate_names
        assert "cx" in gate_names
        assert "measure" in gate_names


# ---------------------------------------------------------------------------
# GHZ circuit tests
# ---------------------------------------------------------------------------

class TestGHZNormalization:
    """Verify normalization of a 3-qubit GHZ circuit."""

    def test_ghz_num_qubits(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir.num_qubits == 3

    def test_ghz_gate_count(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        # h, cx, cx, measure, measure, measure = 6
        assert ir.gate_count == 6

    def test_ghz_depth_positive(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir.depth >= 1

    def test_ghz_connectivity(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        # cx q[0],q[1] and cx q[0],q[2] produce edges (0,1) and (0,2)
        assert (0, 1) in ir.qubit_connectivity
        assert (0, 2) in ir.qubit_connectivity

    def test_ghz_num_clbits(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir.num_clbits == 3


# ---------------------------------------------------------------------------
# Hash determinism tests
# ---------------------------------------------------------------------------

class TestCircuitHashDeterminism:
    """Verify circuit_hash is deterministic and collision-resistant."""

    def test_same_circuit_same_hash(self, normalizer: CircuitNormalizer) -> None:
        ir1 = normalizer.normalize("openqasm", BELL_STATE_QASM)
        ir2 = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert ir1.circuit_hash == ir2.circuit_hash

    def test_same_circuit_same_hash_ghz(self, normalizer: CircuitNormalizer) -> None:
        ir1 = normalizer.normalize("openqasm", GHZ_3_QASM)
        ir2 = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir1.circuit_hash == ir2.circuit_hash

    def test_different_circuits_different_hash(self, normalizer: CircuitNormalizer) -> None:
        ir_bell = normalizer.normalize("openqasm", BELL_STATE_QASM)
        ir_ghz = normalizer.normalize("openqasm", GHZ_3_QASM)
        assert ir_bell.circuit_hash != ir_ghz.circuit_hash

    def test_hash_is_sha256_hex(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        assert len(ir.circuit_hash) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in ir.circuit_hash)


# ---------------------------------------------------------------------------
# Metadata extraction tests
# ---------------------------------------------------------------------------

class TestMetadataExtraction:
    """Verify metadata extraction produces meaningful analysis."""

    def test_bell_state_metadata_keys(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        expected_keys = {
            "single_qubit_gates",
            "two_qubit_gates",
            "multi_qubit_gates",
            "gate_type_distribution",
            "entanglement_density",
            "parallelism_ratio",
            "unique_gate_types",
            "connectivity_edges",
            "has_measurements",
        }
        assert expected_keys.issubset(set(meta.keys()))

    def test_bell_state_has_measurements(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        assert meta["has_measurements"] is True

    def test_bell_state_two_qubit_gates(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        meta = extract_metadata(ir)
        assert meta["two_qubit_gates"] >= 1  # at least the cx gate

    def test_single_qubit_no_entanglement(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", SINGLE_QUBIT_QASM)
        meta = extract_metadata(ir)
        assert meta["two_qubit_gates"] == 0
        assert meta["entanglement_density"] == 0.0

    def test_gate_type_distribution(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        meta = extract_metadata(ir)
        dist = meta["gate_type_distribution"]
        assert "h" in dist
        assert "cx" in dist
        assert dist["h"] == 1
        assert dist["cx"] == 2


# ---------------------------------------------------------------------------
# normalize_to_manifest tests
# ---------------------------------------------------------------------------

class TestNormalizeToManifest:
    """Verify full ingest produces both CircuitIR and ExecutionManifest."""

    def test_returns_ir_and_manifest(self, normalizer: CircuitNormalizer) -> None:
        ir, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=BELL_STATE_QASM,
            user_id="test-user",
            name="bell-test",
        )
        assert ir.num_qubits == 2
        assert manifest.user_id == "test-user"
        assert manifest.name == "bell-test"

    def test_manifest_circuit_hash_matches_ir(self, normalizer: CircuitNormalizer) -> None:
        ir, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=GHZ_3_QASM,
            user_id="test-user",
        )
        assert manifest.circuit_hash == ir.circuit_hash

    def test_manifest_shots_default(self, normalizer: CircuitNormalizer) -> None:
        _, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=BELL_STATE_QASM,
            user_id="test-user",
        )
        assert manifest.shots == 4096

    def test_manifest_custom_shots(self, normalizer: CircuitNormalizer) -> None:
        _, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=BELL_STATE_QASM,
            user_id="test-user",
            shots=1024,
        )
        assert manifest.shots == 1024

    def test_manifest_has_job_id(self, normalizer: CircuitNormalizer) -> None:
        _, manifest = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=BELL_STATE_QASM,
            user_id="test-user",
        )
        assert manifest.job_id is not None
        assert len(manifest.job_id) > 0

    def test_ir_metadata_populated(self, normalizer: CircuitNormalizer) -> None:
        ir, _ = normalizer.normalize_to_manifest(
            input_type="openqasm",
            source=GHZ_3_QASM,
            user_id="test-user",
        )
        assert "single_qubit_gates" in ir.metadata
        assert "entanglement_density" in ir.metadata


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestCircuitValidator:
    """Verify validator catches bad circuits and produces warnings."""

    def test_valid_circuit_no_errors(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", BELL_STATE_QASM)
        validator = CircuitValidator()
        warnings = validator.validate(ir)
        # A simple 2-qubit circuit should have no warnings
        assert isinstance(warnings, list)

    def test_custom_max_qubits_raises(self, normalizer: CircuitNormalizer) -> None:
        ir = normalizer.normalize("openqasm", GHZ_3_QASM)
        validator = CircuitValidator(max_qubits=2)
        with pytest.raises(ValidationError, match="Exceeds max"):
            validator.validate(ir)

    def test_unsupported_input_type_raises(self, normalizer: CircuitNormalizer) -> None:
        with pytest.raises(ValueError, match="Unsupported input type"):
            normalizer.normalize("cirq", "some circuit")

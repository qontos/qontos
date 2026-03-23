"""QGH-3006: Results, Integrity, and Proof Story — Proof generation tests.

Tests hash determinism, collision resistance, field coverage, timestamp
inclusion, and master proof chain integrity.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from qontos.models.execution import ExecutionManifest, ExecutionConstraints
from qontos.models.partition import PartitionPlan, PartitionEntry, DependencyEdge
from qontos.models.result import RunResult, PartitionResult
from qontos.integrity.hashing import ExecutionHasher
from qontos.integrity.proof import ProofGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def hasher():
    return ExecutionHasher()


@pytest.fixture
def proof_gen():
    return ProofGenerator()


def _manifest(
    job_id: str = "job-100",
    circuit_hash: str = "abc123",
    num_qubits: int = 2,
    shots: int = 4096,
) -> ExecutionManifest:
    return ExecutionManifest(
        job_id=job_id, user_id="user-1", name="test-job",
        input_type="openqasm", circuit_hash=circuit_hash,
        num_qubits=num_qubits, shots=shots,
        created_at=datetime.now(timezone.utc),
    )


def _plan(
    job_id: str = "job-100",
    strategy: str = "auto",
    num_partitions: int = 1,
) -> PartitionPlan:
    partitions = [
        PartitionEntry(
            partition_id=f"{job_id}-p{i}", partition_index=i,
            qubit_indices=[i * 2, i * 2 + 1], num_qubits=2, gate_count=4, depth=3,
        )
        for i in range(num_partitions)
    ]
    return PartitionPlan(job_id=job_id, strategy=strategy, partitions=partitions)


def _result(
    job_id: str = "job-100",
    counts: dict[str, int] | None = None,
    shots: int = 4096,
) -> RunResult:
    return RunResult(
        job_id=job_id, status="completed",
        final_counts=counts or {"00": 2048, "11": 2048},
        total_shots=shots, aggregation_method="passthrough",
    )


# ---------------------------------------------------------------------------
# 1. Input digest covers manifest fields
# ---------------------------------------------------------------------------


class TestInputDigest:
    def test_input_digest_deterministic(self, hasher):
        m = _manifest()
        assert hasher.hash_manifest(m) == hasher.hash_manifest(m)

    def test_input_digest_changes_with_job_id(self, hasher):
        m1 = _manifest(job_id="j1")
        m2 = _manifest(job_id="j2")
        assert hasher.hash_manifest(m1) != hasher.hash_manifest(m2)

    def test_input_digest_changes_with_shots(self, hasher):
        m1 = _manifest(shots=1024)
        m2 = _manifest(shots=4096)
        assert hasher.hash_manifest(m1) != hasher.hash_manifest(m2)

    def test_input_digest_changes_with_circuit_hash(self, hasher):
        m1 = _manifest(circuit_hash="aaa")
        m2 = _manifest(circuit_hash="bbb")
        assert hasher.hash_manifest(m1) != hasher.hash_manifest(m2)

    def test_input_digest_is_sha256_hex(self, hasher):
        h = hasher.hash_manifest(_manifest())
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# 2. Execution digest covers partition plan
# ---------------------------------------------------------------------------


class TestExecutionDigest:
    def test_execution_digest_deterministic(self, hasher):
        p = _plan()
        assert hasher.hash_partition_plan(p) == hasher.hash_partition_plan(p)

    def test_execution_digest_changes_with_strategy(self, hasher):
        p1 = _plan(strategy="greedy")
        p2 = _plan(strategy="spectral")
        assert hasher.hash_partition_plan(p1) != hasher.hash_partition_plan(p2)

    def test_execution_digest_changes_with_num_partitions(self, hasher):
        p1 = _plan(num_partitions=1)
        p2 = _plan(num_partitions=2)
        assert hasher.hash_partition_plan(p1) != hasher.hash_partition_plan(p2)


# ---------------------------------------------------------------------------
# 3. Output digest covers run result
# ---------------------------------------------------------------------------


class TestOutputDigest:
    def test_output_digest_deterministic(self, hasher):
        r = _result()
        assert hasher.hash_result(r) == hasher.hash_result(r)

    def test_output_digest_changes_with_counts(self, hasher):
        r1 = _result(counts={"00": 1000, "11": 0})
        r2 = _result(counts={"00": 0, "11": 1000})
        assert hasher.hash_result(r1) != hasher.hash_result(r2)

    def test_output_digest_changes_with_shots(self, hasher):
        r1 = _result(shots=1024)
        r2 = _result(shots=4096)
        assert hasher.hash_result(r1) != hasher.hash_result(r2)


# ---------------------------------------------------------------------------
# 4. Master proof_hash combines all three digests
# ---------------------------------------------------------------------------


class TestMasterProofHash:
    def test_proof_hash_deterministic(self, hasher):
        m, p, r = _manifest(), _plan(), _result()
        h1 = hasher.compute_proof_hash(m, p, r)
        h2 = hasher.compute_proof_hash(m, p, r)
        assert h1 == h2

    def test_proof_hash_different_from_components(self, hasher):
        m, p, r = _manifest(), _plan(), _result()
        proof_h = hasher.compute_proof_hash(m, p, r)
        assert proof_h != hasher.hash_manifest(m)
        assert proof_h != hasher.hash_partition_plan(p)
        assert proof_h != hasher.hash_result(r)

    def test_proof_hash_is_sha256(self, hasher):
        h = hasher.compute_proof_hash(_manifest(), _plan(), _result())
        assert len(h) == 64


# ---------------------------------------------------------------------------
# 5. Proof is deterministic (same inputs = same hash)
# ---------------------------------------------------------------------------


class TestProofDeterminism:
    def test_proof_gen_deterministic(self, proof_gen):
        m, p, r = _manifest(), _plan(), _result()
        proof1 = proof_gen.generate(m, p, r)
        proof2 = proof_gen.generate(m, p, r)
        assert proof1.proof_hash == proof2.proof_hash
        assert proof1.input_digest == proof2.input_digest
        assert proof1.execution_digest == proof2.execution_digest
        assert proof1.output_digest == proof2.output_digest


# ---------------------------------------------------------------------------
# 6. Any field change produces different hash
# ---------------------------------------------------------------------------


class TestFieldChangeSensitivity:
    def test_manifest_change_changes_proof(self, proof_gen):
        p, r = _plan(), _result()
        m1 = _manifest(circuit_hash="aaa")
        m2 = _manifest(circuit_hash="bbb")
        assert proof_gen.generate(m1, p, r).proof_hash != proof_gen.generate(m2, p, r).proof_hash

    def test_plan_change_changes_proof(self, proof_gen):
        m, r = _manifest(), _result()
        p1 = _plan(strategy="greedy")
        p2 = _plan(strategy="spectral")
        assert proof_gen.generate(m, p1, r).proof_hash != proof_gen.generate(m, p2, r).proof_hash

    def test_result_change_changes_proof(self, proof_gen):
        m, p = _manifest(), _plan()
        r1 = _result(counts={"00": 4096})
        r2 = _result(counts={"11": 4096})
        assert proof_gen.generate(m, p, r1).proof_hash != proof_gen.generate(m, p, r2).proof_hash


# ---------------------------------------------------------------------------
# 7. Proof includes timestamps
# ---------------------------------------------------------------------------


class TestProofTimestamps:
    def test_proof_has_created_at(self, proof_gen):
        m, p, r = _manifest(), _plan(), _result()
        proof = proof_gen.generate(m, p, r)
        assert proof.created_at is not None
        assert isinstance(proof.created_at, datetime)

    def test_proof_created_at_is_utc(self, proof_gen):
        m, p, r = _manifest(), _plan(), _result()
        proof = proof_gen.generate(m, p, r)
        assert proof.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# ProofGenerator — full chain structure
# ---------------------------------------------------------------------------


class TestProofChainStructure:
    def test_proof_has_all_digests(self, proof_gen):
        m, p, r = _manifest(), _plan(), _result()
        proof = proof_gen.generate(m, p, r)
        assert proof.input_digest != ""
        assert proof.execution_digest != ""
        assert proof.output_digest != ""
        assert proof.proof_hash != ""

    def test_proof_job_id_matches(self, proof_gen):
        m = _manifest(job_id="job-xyz")
        p = _plan(job_id="job-xyz")
        r = _result(job_id="job-xyz")
        proof = proof_gen.generate(m, p, r)
        assert proof.job_id == "job-xyz"

    def test_proof_circuit_hash_matches_manifest(self, proof_gen):
        m = _manifest(circuit_hash="deadbeef")
        p, r = _plan(), _result()
        proof = proof_gen.generate(m, p, r)
        assert proof.circuit_hash == "deadbeef"

    def test_all_three_digests_distinct(self, proof_gen):
        m, p, r = _manifest(), _plan(), _result()
        proof = proof_gen.generate(m, p, r)
        digests = {proof.input_digest, proof.execution_digest, proof.output_digest}
        assert len(digests) == 3

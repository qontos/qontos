"""Behavioral tests for ExecutionHasher and ProofGenerator.

Tests hash determinism, collision resistance, and proof chain structure.
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hasher() -> ExecutionHasher:
    return ExecutionHasher()


@pytest.fixture
def proof_gen() -> ProofGenerator:
    return ProofGenerator()


def make_manifest(
    job_id: str = "job-100",
    circuit_hash: str = "abc123",
    num_qubits: int = 2,
    shots: int = 4096,
) -> ExecutionManifest:
    return ExecutionManifest(
        job_id=job_id,
        user_id="user-1",
        name="test-job",
        input_type="openqasm",
        circuit_hash=circuit_hash,
        num_qubits=num_qubits,
        shots=shots,
        created_at=datetime.now(timezone.utc),
    )


def make_partition_plan(
    job_id: str = "job-100",
    strategy: str = "auto",
    num_partitions: int = 1,
) -> PartitionPlan:
    partitions = []
    for i in range(num_partitions):
        partitions.append(
            PartitionEntry(
                partition_id=f"{job_id}-p{i}",
                partition_index=i,
                qubit_indices=[i * 2, i * 2 + 1],
                num_qubits=2,
                gate_count=4,
                depth=3,
            )
        )
    return PartitionPlan(
        job_id=job_id,
        strategy=strategy,
        partitions=partitions,
    )


def make_run_result(
    job_id: str = "job-100",
    counts: dict[str, int] | None = None,
    shots: int = 4096,
) -> RunResult:
    return RunResult(
        job_id=job_id,
        status="completed",
        final_counts=counts or {"00": 2048, "11": 2048},
        total_shots=shots,
        aggregation_method="passthrough",
    )


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------

class TestHashDeterminism:
    """Same inputs must always produce the same hash."""

    def test_manifest_hash_deterministic(self, hasher: ExecutionHasher) -> None:
        m = make_manifest()
        h1 = hasher.hash_manifest(m)
        h2 = hasher.hash_manifest(m)
        assert h1 == h2

    def test_partition_plan_hash_deterministic(self, hasher: ExecutionHasher) -> None:
        plan = make_partition_plan()
        h1 = hasher.hash_partition_plan(plan)
        h2 = hasher.hash_partition_plan(plan)
        assert h1 == h2

    def test_result_hash_deterministic(self, hasher: ExecutionHasher) -> None:
        result = make_run_result()
        h1 = hasher.hash_result(result)
        h2 = hasher.hash_result(result)
        assert h1 == h2

    def test_proof_hash_deterministic(self, hasher: ExecutionHasher) -> None:
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        h1 = hasher.compute_proof_hash(m, p, r)
        h2 = hasher.compute_proof_hash(m, p, r)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Hash collision resistance
# ---------------------------------------------------------------------------

class TestHashCollisionResistance:
    """Different inputs must produce different hashes."""

    def test_different_manifests_different_hash(self, hasher: ExecutionHasher) -> None:
        m1 = make_manifest(job_id="job-1", circuit_hash="aaa")
        m2 = make_manifest(job_id="job-2", circuit_hash="bbb")
        assert hasher.hash_manifest(m1) != hasher.hash_manifest(m2)

    def test_different_shots_different_hash(self, hasher: ExecutionHasher) -> None:
        m1 = make_manifest(shots=1024)
        m2 = make_manifest(shots=4096)
        assert hasher.hash_manifest(m1) != hasher.hash_manifest(m2)

    def test_different_plans_different_hash(self, hasher: ExecutionHasher) -> None:
        p1 = make_partition_plan(strategy="greedy")
        p2 = make_partition_plan(strategy="spectral")
        assert hasher.hash_partition_plan(p1) != hasher.hash_partition_plan(p2)

    def test_different_results_different_hash(self, hasher: ExecutionHasher) -> None:
        r1 = make_run_result(counts={"00": 1000, "11": 0})
        r2 = make_run_result(counts={"00": 0, "11": 1000})
        assert hasher.hash_result(r1) != hasher.hash_result(r2)

    def test_different_num_partitions_different_plan_hash(
        self, hasher: ExecutionHasher
    ) -> None:
        p1 = make_partition_plan(num_partitions=1)
        p2 = make_partition_plan(num_partitions=2)
        assert hasher.hash_partition_plan(p1) != hasher.hash_partition_plan(p2)


# ---------------------------------------------------------------------------
# Hash format
# ---------------------------------------------------------------------------

class TestHashFormat:
    """All hashes must be valid SHA-256 hex strings."""

    def test_manifest_hash_is_sha256(self, hasher: ExecutionHasher) -> None:
        h = hasher.hash_manifest(make_manifest())
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_plan_hash_is_sha256(self, hasher: ExecutionHasher) -> None:
        h = hasher.hash_partition_plan(make_partition_plan())
        assert len(h) == 64

    def test_result_hash_is_sha256(self, hasher: ExecutionHasher) -> None:
        h = hasher.hash_result(make_run_result())
        assert len(h) == 64

    def test_proof_hash_is_sha256(self, hasher: ExecutionHasher) -> None:
        h = hasher.compute_proof_hash(
            make_manifest(), make_partition_plan(), make_run_result()
        )
        assert len(h) == 64


# ---------------------------------------------------------------------------
# ProofGenerator
# ---------------------------------------------------------------------------

class TestProofGenerator:
    """Test full proof generation pipeline."""

    def test_proof_has_all_digests(self, proof_gen: ProofGenerator) -> None:
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        proof = proof_gen.generate(m, p, r)
        assert proof.input_digest != ""
        assert proof.execution_digest != ""
        assert proof.output_digest != ""
        assert proof.proof_hash != ""

    def test_proof_job_id_matches(self, proof_gen: ProofGenerator) -> None:
        m = make_manifest(job_id="job-xyz")
        p = make_partition_plan(job_id="job-xyz")
        r = make_run_result(job_id="job-xyz")
        proof = proof_gen.generate(m, p, r)
        assert proof.job_id == "job-xyz"

    def test_proof_circuit_hash_matches_manifest(
        self, proof_gen: ProofGenerator
    ) -> None:
        m = make_manifest(circuit_hash="deadbeef")
        p = make_partition_plan()
        r = make_run_result()
        proof = proof_gen.generate(m, p, r)
        assert proof.circuit_hash == "deadbeef"

    def test_proof_digests_are_different(self, proof_gen: ProofGenerator) -> None:
        """The three component digests should be distinct."""
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        proof = proof_gen.generate(m, p, r)
        digests = {proof.input_digest, proof.execution_digest, proof.output_digest}
        assert len(digests) == 3  # all three are different

    def test_proof_hash_combines_all_three(self, proof_gen: ProofGenerator) -> None:
        """The proof_hash should be different from any individual digest."""
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        proof = proof_gen.generate(m, p, r)
        assert proof.proof_hash != proof.input_digest
        assert proof.proof_hash != proof.execution_digest
        assert proof.proof_hash != proof.output_digest

    def test_proof_deterministic(self, proof_gen: ProofGenerator) -> None:
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        proof1 = proof_gen.generate(m, p, r)
        proof2 = proof_gen.generate(m, p, r)
        assert proof1.proof_hash == proof2.proof_hash

    def test_proof_has_created_at(self, proof_gen: ProofGenerator) -> None:
        m = make_manifest()
        p = make_partition_plan()
        r = make_run_result()
        proof = proof_gen.generate(m, p, r)
        assert proof.created_at is not None

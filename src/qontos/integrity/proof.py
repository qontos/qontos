"""Proof generation — builds ExecutionProof objects for audit trail."""

from __future__ import annotations

from datetime import datetime, timezone

from qontos.models.execution import ExecutionManifest
from qontos.models.partition import PartitionPlan
from qontos.models.result import RunResult
from qontos.models.proof import ExecutionProof
from qontos.integrity.hashing import ExecutionHasher


class ProofGenerator:
    """Generates complete execution proof objects."""

    def __init__(self):
        self.hasher = ExecutionHasher()

    def generate(
        self,
        manifest: ExecutionManifest,
        plan: PartitionPlan,
        result: RunResult,
    ) -> ExecutionProof:
        """Generate a complete execution proof."""
        input_digest = self.hasher.hash_manifest(manifest)
        execution_digest = self.hasher.hash_partition_plan(plan)
        output_digest = self.hasher.hash_result(result)
        proof_hash = self.hasher.compute_proof_hash(manifest, plan, result)

        return ExecutionProof(
            job_id=manifest.job_id,
            proof_hash=proof_hash,
            circuit_hash=manifest.circuit_hash,
            result_hash=output_digest,
            manifest_hash=input_digest,
            input_digest=input_digest,
            execution_digest=execution_digest,
            output_digest=output_digest,
            created_at=datetime.now(timezone.utc),
        )

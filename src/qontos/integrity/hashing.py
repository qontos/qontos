"""Execution hashing — cryptographic integrity for all pipeline artifacts.

Produces deterministic SHA-256 hashes of execution inputs, decisions, and outputs.
This is the foundation for the verification/audit-trail layer in the whitepaper.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from qontos.models.execution import ExecutionManifest
from qontos.models.partition import PartitionPlan
from qontos.models.result import RunResult


class ExecutionHasher:
    """Produces deterministic hashes for execution integrity verification."""

    @staticmethod
    def hash_manifest(manifest: ExecutionManifest) -> str:
        """Hash the execution manifest (input digest)."""
        canonical = json.dumps({
            "job_id": manifest.job_id,
            "input_type": manifest.input_type,
            "circuit_hash": manifest.circuit_hash,
            "num_qubits": manifest.num_qubits,
            "shots": manifest.shots,
            "optimization_level": manifest.optimization_level,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def hash_partition_plan(plan: PartitionPlan) -> str:
        """Hash the partition plan (execution decisions digest)."""
        canonical = json.dumps({
            "job_id": plan.job_id,
            "strategy": plan.strategy,
            "partitions": [
                {"id": p.partition_id, "qubits": sorted(p.qubit_indices), "gates": p.gate_count}
                for p in plan.partitions
            ],
            "dependencies": [
                {"from": d.from_partition, "to": d.to_partition}
                for d in plan.dependencies
            ],
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def hash_result(result: RunResult) -> str:
        """Hash the final result (output digest)."""
        canonical = json.dumps({
            "job_id": result.job_id,
            "counts": dict(sorted(result.final_counts.items())),
            "total_shots": result.total_shots,
            "aggregation_method": result.aggregation_method,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def compute_proof_hash(
        cls,
        manifest: ExecutionManifest,
        plan: PartitionPlan,
        result: RunResult,
    ) -> str:
        """Compute the master proof hash combining all three digests.

        This is the single hash that anchors the entire execution
        to the integrity layer (and eventually to Aethelred blockchain).
        """
        input_digest = cls.hash_manifest(manifest)
        execution_digest = cls.hash_partition_plan(plan)
        output_digest = cls.hash_result(result)

        master = json.dumps({
            "input_digest": input_digest,
            "execution_digest": execution_digest,
            "output_digest": output_digest,
        }, sort_keys=True)
        return hashlib.sha256(master.encode()).hexdigest()

"""Provenance tracking — records the lineage of each result."""

from __future__ import annotations

from datetime import datetime, timezone
from qontos.models.result import RunResult, PartitionResult
from qontos.models.proof import AuditEntry


class ProvenanceTracker:
    """Tracks the full lineage of a run result for audit purposes."""

    def build_provenance(self, result: RunResult) -> list[AuditEntry]:
        """Generate audit entries for a completed run."""
        now = datetime.now(timezone.utc)
        entries = []

        # Job completion entry
        entries.append(AuditEntry(
            job_id=result.job_id,
            event="result_aggregated",
            timestamp=now,
            service="result_aggregator",
            data={
                "aggregation_method": result.aggregation_method,
                "num_partitions": len(result.partition_results),
                "total_shots": result.total_shots,
                "num_unique_states": len(result.final_counts),
            },
        ))

        # Per-partition provenance
        for pr in result.partition_results:
            entries.append(AuditEntry(
                job_id=result.job_id,
                event="partition_executed",
                timestamp=now,
                service=f"executor_{pr.provider}",
                data={
                    "partition_id": pr.partition_id,
                    "backend": pr.backend_name,
                    "provider": pr.provider,
                    "shots": pr.shots_completed,
                    "execution_time_ms": pr.execution_time_ms,
                    "cost_usd": pr.cost_usd,
                    "provider_job_id": pr.provider_job_id,
                },
            ))

        return entries

    @staticmethod
    def attach_provenance(result: RunResult, entries: list[AuditEntry]) -> RunResult:
        """Attach provenance to the result metadata."""
        result.metadata["provenance"] = [e.model_dump(mode="json") for e in entries]
        return result

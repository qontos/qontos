"""Main scheduler — assigns partitions to optimal backends.

Takes a list of PartitionEntry + available BackendCapability + constraints
and produces a list of ScheduledTask ready for the backend_router.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from qontos.models import (
    BackendCapability,
    BackendStatus,
    PartitionEntry,
    ExecutionConstraints,
    ScheduledTask,
    TaskStatus,
)
from qontos.scheduling.scoring import BackendScorer
from qontos.scheduling.policies import SchedulingPolicy, FidelityFirstPolicy


# Map provider -> executor service name
_EXECUTOR_MAP: dict[str, str] = {
    "ibm": "executor_ibm",
    "braket": "executor_braket",
    "local_simulator": "executor_simulator",
}


def _resolve_executor(provider: str) -> str:
    return _EXECUTOR_MAP.get(provider, f"executor_{provider}")


class Scheduler:
    """Core scheduling engine.

    For each partition, scores every available backend and picks the best one.
    """

    def __init__(
        self,
        policy: SchedulingPolicy | None = None,
    ) -> None:
        self.policy = policy or FidelityFirstPolicy()
        self.scorer: BackendScorer = self.policy.build_scorer()

    def schedule(
        self,
        job_id: str,
        partitions: list[PartitionEntry],
        backends: list[BackendCapability],
        constraints: ExecutionConstraints,
        shots: int = 4096,
        priority: str = "normal",
    ) -> list[ScheduledTask]:
        """Assign each partition to the optimal backend.

        Returns a list of ScheduledTask objects ready for routing.
        Raises ValueError if any partition cannot be assigned.
        """
        available = [b for b in backends if b.status == BackendStatus.AVAILABLE]
        if not available:
            raise ValueError("No available backends for scheduling")

        # Honour preferred_backends constraint
        if constraints.preferred_backends:
            preferred = [
                b for b in available if b.id in constraints.preferred_backends
            ]
            if preferred:
                available = preferred

        tasks: list[ScheduledTask] = []

        for partition in partitions:
            best_backend, best_score, best_reasoning = self._pick_best(
                partition, available, constraints
            )
            if best_backend is None:
                raise ValueError(
                    f"No compatible backend for partition {partition.partition_id} "
                    f"(requires {partition.num_qubits} qubits)"
                )

            task = ScheduledTask(
                task_id=str(uuid.uuid4()),
                job_id=job_id,
                partition_id=partition.partition_id,
                backend_id=best_backend.id,
                backend_name=best_backend.name,
                executor=_resolve_executor(best_backend.provider),
                provider=best_backend.provider,
                priority=priority,
                scheduling_score=best_score,
                scheduling_reasoning=best_reasoning,
                shots=shots,
                optimization_level=constraints.partition_strategy != "auto" and 2 or 1,
                noise_model_config=best_backend.noise_model_config,
                error_mitigation=constraints.error_mitigation,
                status=TaskStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            tasks.append(task)

        return tasks

    def _pick_best(
        self,
        partition: PartitionEntry,
        backends: list[BackendCapability],
        constraints: ExecutionConstraints,
    ) -> tuple[BackendCapability | None, float, dict]:
        """Score all backends for a partition and return the best."""
        best_backend: BackendCapability | None = None
        best_score = -1.0
        best_reasoning: dict = {}

        for backend in backends:
            # Hard filter: backend must have enough qubits
            if backend.num_qubits < partition.num_qubits:
                continue

            # Hard filter: depth limit
            if (
                backend.max_circuit_depth is not None
                and partition.depth > backend.max_circuit_depth
            ):
                continue

            score, reasoning = self.scorer.score(backend, partition, constraints)

            if score > best_score:
                best_score = score
                best_backend = backend
                best_reasoning = reasoning

        return best_backend, best_score, best_reasoning

"""QONTOS data models — Pydantic v2 schemas for circuits, partitions, results, and proofs."""

from qontos.models.circuit import CircuitIR, GateOperation, InputFormat
from qontos.models.enums import (
    JobStatus,
    RunStatus,
    PartitionStrategy,
    Provider,
    ExecutorService,
    ErrorMitigation,
    ObjectiveType,
    SchedulingPolicy,
    CircuitType,
    BackendType,
    AggregationMethod,
)
from qontos.models.execution import ExecutionManifest, ExecutionConstraints
from qontos.models.partition import (
    PartitionEntry,
    PartitionPlan,
    PartitionState,
    DependencyEdge,
)
from qontos.models.result import RunResult, PartitionResult, RunSummary
from qontos.models.proof import ExecutionProof, AuditEntry
from qontos.models.backend import BackendCapability, BackendStatus
from qontos.models.job_outcome import JobOutcome, JobOutcomeReport
from qontos.models.scheduling import ScheduledTask, TaskStatus

__all__ = [
    # Circuit
    "CircuitIR",
    "GateOperation",
    "InputFormat",
    # Enums
    "JobStatus",
    "RunStatus",
    "PartitionStrategy",
    "Provider",
    "ExecutorService",
    "ErrorMitigation",
    "ObjectiveType",
    "SchedulingPolicy",
    "CircuitType",
    "BackendType",
    "AggregationMethod",
    # Execution
    "ExecutionManifest",
    "ExecutionConstraints",
    # Partition
    "PartitionEntry",
    "PartitionPlan",
    "PartitionState",
    "DependencyEdge",
    # Result
    "RunResult",
    "PartitionResult",
    "RunSummary",
    # Proof
    "ExecutionProof",
    "AuditEntry",
    # Backend
    "BackendCapability",
    "BackendStatus",
    # Job Outcome
    "JobOutcome",
    "JobOutcomeReport",
    # Scheduling
    "ScheduledTask",
    "TaskStatus",
]

"""QONTOS — Distributed quantum computing orchestration SDK.

Usage::

    from qontos import QontosClient

    client = QontosClient(api_key="qontos_sk_...")
    job = client.submit_job(circuit="OPENQASM 2.0; ...", shots=4096)
    result = client.get_results(job.runs[0].id)
    print(result.counts)

For circuit processing without the API client::

    from qontos.circuit import CircuitNormalizer
    from qontos.partitioning import Partitioner
    from qontos.scheduling import Scheduler
"""

# --- Client classes --------------------------------------------------------
from qontos.client import QontosClient, QontosConfig
from qontos.async_client import AsyncQontosClient

# --- Core models -----------------------------------------------------------
from qontos.models.circuit import CircuitIR, GateOperation
from qontos.models.partition import PartitionPlan, PartitionEntry
from qontos.models.scheduling import ScheduledTask
from qontos.models.result import RunResult, PartitionResult
PartialResult = PartitionResult  # public alias
from qontos.models.proof import ExecutionProof
from qontos.models.job_outcome import JobOutcomeReport

# --- Enums -----------------------------------------------------------------
from qontos.models.enums import (
    JobStatus,
    CircuitType,
    BackendType,
    PartitionStrategy,
    AggregationMethod,
)

# --- Exceptions ------------------------------------------------------------
from qontos.exceptions import (
    QontosError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    ServerError,
    TimeoutError,
    CircuitError,
)

__version__ = "0.2.0"

__all__ = [
    # Client classes
    "QontosClient",
    "AsyncQontosClient",
    # Core models
    "CircuitIR",
    "GateOperation",
    "PartitionPlan",
    "PartitionEntry",
    "ScheduledTask",
    "RunResult",
    "PartialResult",
    "ExecutionProof",
    "JobOutcomeReport",
    # Enums
    "JobStatus",
    "CircuitType",
    "BackendType",
    "PartitionStrategy",
    "AggregationMethod",
    # Exceptions
    "QontosError",
    "AuthenticationError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
    "ServerError",
    "TimeoutError",
    "CircuitError",
    # Version
    "__version__",
]

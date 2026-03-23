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

from qontos.client import QontosClient, QontosConfig
from qontos.async_client import AsyncQontosClient
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

__version__ = "0.1.0"

__all__ = [
    # Client
    "QontosClient",
    "QontosConfig",
    "AsyncQontosClient",
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

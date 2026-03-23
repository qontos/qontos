# QONTOS SDK 0.2 — Stable Public API Surface

This document defines the intentional public API for `qontos` version 0.2.
Only symbols listed here are considered stable. Everything else is internal.

---

## Client Classes

| Symbol | Module | Description |
|---|---|---|
| `QontosClient` | `qontos.client` | Synchronous HTTP client for the QONTOS API |
| `AsyncQontosClient` | `qontos.async_client` | Async (httpx) HTTP client for the QONTOS API |

## Core Models

| Symbol | Module | Description |
|---|---|---|
| `CircuitIR` | `qontos.models.circuit` | Provider-agnostic internal circuit representation |
| `GateOperation` | `qontos.models.circuit` | Single gate in a circuit |
| `PartitionPlan` | `qontos.models.partition` | Complete partitioning output for a job |
| `PartitionEntry` | `qontos.models.partition` | Single partition (qubit subset + sub-circuit) |
| `ScheduledTask` | `qontos.models.scheduling` | Partition assigned to a backend, ready for execution |
| `RunResult` | `qontos.models.result` | Final merged result from the full pipeline |
| `PartialResult` | `qontos.models.result` | Alias reference for single-partition result |
| `ExecutionProof` | `qontos.models.proof` | Three-layer SHA-256 integrity proof |
| `JobOutcomeReport` | `qontos.models.job_outcome` | Canonical job outcome with degradation tracking |

## Enums

| Symbol | Module | Values |
|---|---|---|
| `JobStatus` | `qontos.models.enums` | created, queued, ingesting, partitioning, scheduling, running, aggregating, finalizing, completed, failed, cancelled |
| `CircuitType` | `qontos.models.enums` | general, chemistry, optimization, machine_learning, benchmark, error_correction |
| `BackendType` | `qontos.models.enums` | simulator, hardware, emulator |
| `PartitionStrategy` | `qontos.models.enums` | auto, greedy, spectral, manual |
| `AggregationMethod` | `qontos.models.enums` | passthrough, tensor_product, marginal_reconstruction, marginal_reconstruction_fallback |

## Exceptions

All exceptions inherit from `QontosError`.

| Symbol | HTTP Code | Description |
|---|---|---|
| `QontosError` | — | Base exception for all SDK errors |
| `AuthenticationError` | 401 | Missing, invalid, or expired API key |
| `ForbiddenError` | 403 | Insufficient permissions |
| `NotFoundError` | 404 | Resource does not exist |
| `ValidationError` | 422 | Request payload validation failure |
| `RateLimitError` | 429 | Rate limit exceeded (includes `retry_after`) |
| `ServerError` | 5xx | Server-side error |
| `TimeoutError` | — | Request or polling timeout |
| `CircuitError` | — | Malformed or unsupported circuit |

## Version

| Symbol | Value |
|---|---|
| `__version__` | `"0.2.0"` |

---

## Import Patterns

```python
# Top-level convenience imports
from qontos import QontosClient, CircuitIR, JobStatus, QontosError, __version__

# Subpackage imports for pipeline internals
from qontos.circuit import CircuitNormalizer
from qontos.partitioning import Partitioner
from qontos.scheduling import Scheduler
from qontos.results import ResultAggregator
from qontos.integrity import ProofGenerator
```

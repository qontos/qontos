"""Shared enumerations used across all QONTOS services."""

from enum import Enum


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    INGESTING = "ingesting"
    PARTITIONING = "partitioning"
    SCHEDULING = "scheduling"
    RUNNING = "running"
    AGGREGATING = "aggregating"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class PartitionStrategy(str, Enum):
    AUTO = "auto"
    GREEDY = "greedy"
    SPECTRAL = "spectral"
    MANUAL = "manual"


class Provider(str, Enum):
    LOCAL_SIMULATOR = "local_simulator"
    IBM = "ibm"
    BRAKET = "braket"


class ExecutorService(str, Enum):
    SIMULATOR = "executor_simulator"
    IBM = "executor_ibm"
    BRAKET = "executor_braket"


class ErrorMitigation(str, Enum):
    NONE = "none"
    ZNE = "zne"  # Zero Noise Extrapolation
    PEC = "pec"  # Probabilistic Error Cancellation
    M3 = "m3"    # Matrix-free Measurement Mitigation


class ObjectiveType(str, Enum):
    GENERAL = "general"
    CHEMISTRY = "chemistry"
    OPTIMIZATION = "optimization"
    MACHINE_LEARNING = "machine_learning"
    BENCHMARK = "benchmark"
    ERROR_CORRECTION = "error_correction"


class SchedulingPolicy(str, Enum):
    SIMULATOR_FIRST = "simulator_first"
    CHEAPEST_AVAILABLE = "cheapest_available"
    HIGHEST_FIDELITY = "highest_fidelity"
    HYBRID_SPLIT = "hybrid_split"

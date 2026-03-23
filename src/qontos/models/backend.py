"""Backend capability and status models."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum


class BackendStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    SIMULATED = "simulated"


class BackendCapability(BaseModel):
    """What a backend can do — used by scheduler for scoring."""
    id: str
    name: str
    provider: str  # ibm, braket, local_simulator
    backend_type: str  # simulator, hardware

    status: BackendStatus = BackendStatus.AVAILABLE
    num_qubits: int
    max_shots: int = 100000
    max_circuit_depth: int | None = None
    basis_gates: list[str] = Field(default_factory=list)
    connectivity_map: dict | None = None

    # Performance characteristics
    avg_gate_fidelity_1q: float | None = None
    avg_gate_fidelity_2q: float | None = None
    avg_readout_fidelity: float | None = None
    avg_t1_us: float | None = None
    avg_t2_us: float | None = None
    queue_depth: int = 0

    # Cost
    cost_per_shot: float = 0.0
    cost_per_second: float = 0.0

    # Modular architecture emulation
    is_modular: bool = False
    module_count: int = 1
    qubits_per_module: int | None = None
    inter_module_fidelity: float | None = None
    transduction_efficiency: float | None = None

    # Noise model (for simulator configuration)
    noise_model_config: dict | None = None

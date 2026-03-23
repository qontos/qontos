"""Circuit internal representation — the normalized form every service uses."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum


class InputFormat(str, Enum):
    QISKIT = "qiskit"
    OPENQASM = "openqasm"
    PENNYLANE = "pennylane"


class GateOperation(BaseModel):
    """A single gate operation in the circuit."""
    name: str
    qubits: list[int]
    params: list[float] = Field(default_factory=list)
    is_inter_module: bool = False


class CircuitIR(BaseModel):
    """QONTOS internal circuit representation — provider-agnostic.

    This is the canonical form. All ingest paths produce this.
    All executors consume this (translating to their provider format).
    """
    num_qubits: int
    num_clbits: int = 0
    depth: int
    gate_count: int
    gates: list[GateOperation]
    qubit_connectivity: list[tuple[int, int]] = Field(default_factory=list)
    source_type: InputFormat
    circuit_hash: str = ""  # SHA-256 of canonical representation

    # Serialized form for executor consumption
    qasm_string: str | None = None
    serialized_circuit: str | None = None  # JSON blob for non-QASM formats

    metadata: dict = Field(default_factory=dict)

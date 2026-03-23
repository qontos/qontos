"""Circuit ingestion and normalization.

Accepts quantum circuits in OpenQASM 2.0/3.0, Qiskit, and PennyLane formats
and produces a canonical CircuitIR representation.
"""

from qontos.circuit.normalizer import CircuitNormalizer
from qontos.circuit.validators import CircuitValidator

__all__ = [
    "CircuitNormalizer",
    "CircuitValidator",
]

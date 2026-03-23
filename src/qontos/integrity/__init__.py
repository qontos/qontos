"""Cryptographic execution proofs.

Generates three-layer SHA-256 hash chains for tamper-evident execution records:
input digest -> execution digest -> output digest -> master proof hash.
"""

from qontos.integrity.hashing import ExecutionHasher
from qontos.integrity.proof import ProofGenerator

__all__ = [
    "ExecutionHasher",
    "ProofGenerator",
]

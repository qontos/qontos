"""Execution proof and audit trail models."""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime


class ExecutionProof(BaseModel):
    """Proof object for execution integrity verification.

    Maps to the whitepaper's blockchain verification layer.
    MVP: hash and store. Future: anchor to Aethelred chain.
    """
    job_id: str
    proof_hash: str  # SHA-256 of execution + results
    circuit_hash: str
    result_hash: str
    manifest_hash: str

    # Proof components
    input_digest: str  # hash of circuit + parameters
    execution_digest: str  # hash of partition plan + scheduling decisions
    output_digest: str  # hash of final merged results

    # Chain anchoring (future)
    chain_anchor: str | None = None  # tx hash on Aethelred
    anchor_timestamp: datetime | None = None

    created_at: datetime | None = None


class AuditEntry(BaseModel):
    """Single entry in the execution audit trail."""
    job_id: str
    event: str  # job_created, circuit_ingested, partitioned, scheduled, executed, aggregated, hashed
    timestamp: datetime
    service: str  # which service produced this entry
    data: dict = Field(default_factory=dict)
    actor: str | None = None  # user_id or system

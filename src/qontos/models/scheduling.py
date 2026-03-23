"""Scheduling models — ScheduledTask and TaskStatus used by the scheduler service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Lifecycle state of a scheduled task."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledTask(BaseModel):
    """A single partition assigned to a backend, ready for execution."""
    task_id: str
    job_id: str
    partition_id: str
    backend_id: str
    backend_name: str
    executor: str
    provider: str
    priority: str = "normal"

    # Scoring
    scheduling_score: float = 0.0
    scheduling_reasoning: dict = Field(default_factory=dict)

    # Execution parameters
    shots: int = 4096
    optimization_level: int = 1
    noise_model_config: dict | None = None
    error_mitigation: str = "none"

    # State
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None

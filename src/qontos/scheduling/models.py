"""Local types for the scheduler service."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum


class ScoringWeights(BaseModel):
    """Weights for the backend scoring model."""
    fidelity: float = 0.4
    queue_depth: float = 0.2
    cost: float = 0.2
    capacity_fit: float = 0.2

    def normalized(self) -> "ScoringWeights":
        """Return a copy with weights normalized to sum to 1.0."""
        total = self.fidelity + self.queue_depth + self.cost + self.capacity_fit
        if total == 0:
            return ScoringWeights(fidelity=0.25, queue_depth=0.25, cost=0.25, capacity_fit=0.25)
        return ScoringWeights(
            fidelity=self.fidelity / total,
            queue_depth=self.queue_depth / total,
            cost=self.cost / total,
            capacity_fit=self.capacity_fit / total,
        )


class SchedulingPolicyType(str, Enum):
    SIMULATOR_FIRST = "simulator_first"
    FIDELITY_FIRST = "fidelity_first"
    COST_OPTIMIZED = "cost_optimized"


class QuotaUsage(BaseModel):
    """Tracks a user's current resource usage."""
    user_id: str
    concurrent_jobs: int = 0
    shots_today: int = 0
    cost_today_usd: float = 0.0


class QuotaLimits(BaseModel):
    """Configurable quota limits per user."""
    max_concurrent_jobs: int = 5
    max_shots_per_day: int = 1_000_000
    cost_budget_usd: float = 100.0


class ScoringBreakdown(BaseModel):
    """Detailed breakdown of how a backend was scored."""
    backend_id: str
    total_score: float
    fidelity_score: float = 0.0
    queue_depth_score: float = 0.0
    cost_score: float = 0.0
    capacity_fit_score: float = 0.0
    penalties: dict = Field(default_factory=dict)
    weights_used: ScoringWeights = Field(default_factory=ScoringWeights)

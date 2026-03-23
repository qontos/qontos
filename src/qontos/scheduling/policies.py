"""Scheduling policies that adjust scorer weights for different optimization goals."""

from __future__ import annotations
from abc import ABC, abstractmethod

from qontos.scheduling.models import ScoringWeights
from qontos.scheduling.scoring import BackendScorer


class SchedulingPolicy(ABC):
    """Base class for scheduling policies."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def build_scorer(self) -> BackendScorer:
        """Return a BackendScorer configured with this policy's weights."""
        ...


class SimulatorFirstPolicy(SchedulingPolicy):
    """Prefer simulators for development / debugging.

    High weight on cost (simulators are free) and capacity_fit.
    Low weight on queue_depth (simulators rarely queue).
    """

    def name(self) -> str:
        return "simulator_first"

    def build_scorer(self) -> BackendScorer:
        return BackendScorer(
            weights=ScoringWeights(
                fidelity=0.1,
                queue_depth=0.1,
                cost=0.5,
                capacity_fit=0.3,
            )
        )


class FidelityFirstPolicy(SchedulingPolicy):
    """Maximize execution fidelity — pick the highest-quality hardware."""

    def name(self) -> str:
        return "fidelity_first"

    def build_scorer(self) -> BackendScorer:
        return BackendScorer(
            weights=ScoringWeights(
                fidelity=0.6,
                queue_depth=0.1,
                cost=0.1,
                capacity_fit=0.2,
            )
        )


class CostOptimizedPolicy(SchedulingPolicy):
    """Minimize cost while maintaining acceptable quality."""

    def name(self) -> str:
        return "cost_optimized"

    def build_scorer(self) -> BackendScorer:
        return BackendScorer(
            weights=ScoringWeights(
                fidelity=0.2,
                queue_depth=0.2,
                cost=0.4,
                capacity_fit=0.2,
            )
        )


# ------------------------------------------------------------------
# Convenience lookup
# ------------------------------------------------------------------

POLICY_REGISTRY: dict[str, type[SchedulingPolicy]] = {
    "simulator_first": SimulatorFirstPolicy,
    "fidelity_first": FidelityFirstPolicy,
    "cost_optimized": CostOptimizedPolicy,
}


def get_policy(name: str) -> SchedulingPolicy:
    """Return an instantiated policy by name. Defaults to FidelityFirstPolicy."""
    cls = POLICY_REGISTRY.get(name, FidelityFirstPolicy)
    return cls()

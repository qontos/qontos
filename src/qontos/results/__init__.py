"""Distributed result aggregation.

Merges partition results into unified run results using passthrough,
independent (tensor product), or entangled (marginal reconstruction) strategies.
"""

from qontos.results.aggregate import ResultAggregator

__all__ = [
    "ResultAggregator",
]

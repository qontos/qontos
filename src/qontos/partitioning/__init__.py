"""Circuit partitioning engine.

Splits large quantum circuits across quantum modules using graph-based
algorithms: greedy (fast), spectral (optimal cuts), or manual (user-specified).
"""

from qontos.partitioning.partition import Partitioner
from qontos.partitioning.heuristics import GreedyPartitioner, SpectralPartitioner
from qontos.partitioning.models import PartitionConstraints

__all__ = [
    "Partitioner",
    "GreedyPartitioner",
    "SpectralPartitioner",
    "PartitionConstraints",
]

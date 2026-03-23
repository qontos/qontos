"""Partitioning heuristics — three strategies for splitting qubit sets.

All partitioners share the same interface:
    partition(graph, num_partitions) -> list[set[int]]

Each returned set contains global qubit indices belonging to that partition.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from qontos.partitioning.graph_model import CircuitGraph


class BasePartitioner(ABC):
    """Common interface for all partitioning strategies."""

    @abstractmethod
    def partition(self, graph: CircuitGraph, num_partitions: int) -> list[set[int]]:
        """Split qubits into *num_partitions* groups.

        Returns a list of sets, each containing global qubit indices.
        """


# -----------------------------------------------------------------------
# 1. Greedy partitioner — grows from highest-degree seed nodes
# -----------------------------------------------------------------------

class GreedyPartitioner(BasePartitioner):
    """Grow partitions outward from the highest-degree seed qubits.

    Algorithm:
        1. Select *k* seed qubits with the highest weighted degree.
        2. Repeatedly assign the unassigned qubit most strongly connected
           to an existing partition member, choosing the partition with
           the fewest qubits (for balance).
        3. Continue until every qubit is assigned.
    """

    def partition(self, graph: CircuitGraph, num_partitions: int) -> list[set[int]]:
        n = graph.num_qubits
        k = min(num_partitions, n)

        if k <= 0:
            return []
        if k == 1:
            return [set(range(n))]
        if n == 0:
            return [set() for _ in range(k)]

        degrees = graph.get_degree_vector()
        adj = graph.get_adjacency_matrix()

        # --- seed selection: k highest-degree, spaced apart ---------------
        seeds = self._select_seeds(degrees, adj, k)

        assigned: dict[int, int] = {}  # qubit -> partition index
        partitions: list[set[int]] = [set() for _ in range(k)]
        for idx, seed in enumerate(seeds):
            partitions[idx].add(seed)
            assigned[seed] = idx

        # --- greedy expansion ---------------------------------------------
        while len(assigned) < n:
            best_qubit = -1
            best_part = -1
            best_score = -1.0

            for q in range(n):
                if q in assigned:
                    continue
                # For each partition, compute affinity = sum of edge weights
                # between q and members of that partition.
                for p_idx in range(k):
                    affinity = sum(adj[q, m] for m in partitions[p_idx])
                    # Tie-break: prefer the smaller partition (balance).
                    score = affinity * n + (n - len(partitions[p_idx]))
                    if score > best_score:
                        best_score = score
                        best_qubit = q
                        best_part = p_idx

            # If no affinity anywhere (disconnected qubit), assign to
            # smallest partition.
            if best_qubit == -1:
                # Should not happen if n > len(assigned), but be safe.
                break

            partitions[best_part].add(best_qubit)
            assigned[best_qubit] = best_part

        # Assign any truly unreachable qubits to the smallest partition.
        for q in range(n):
            if q not in assigned:
                smallest = min(range(k), key=lambda i: len(partitions[i]))
                partitions[smallest].add(q)

        return partitions

    @staticmethod
    def _select_seeds(
        degrees: np.ndarray, adj: np.ndarray, k: int
    ) -> list[int]:
        """Pick *k* high-degree seed qubits that are well-separated."""
        n = len(degrees)
        order = np.argsort(-degrees)  # descending degree
        seeds: list[int] = [int(order[0])]

        for candidate in order[1:]:
            if len(seeds) >= k:
                break
            candidate = int(candidate)
            # Accept if the candidate is not directly connected to all
            # existing seeds (heuristic for spread).
            connected_to_all = all(adj[candidate, s] > 0 for s in seeds)
            if not connected_to_all:
                seeds.append(candidate)

        # If we still need more seeds (dense graph), just take next highest.
        for candidate in order:
            if len(seeds) >= k:
                break
            candidate = int(candidate)
            if candidate not in seeds:
                seeds.append(candidate)

        return seeds


# -----------------------------------------------------------------------
# 2. Spectral partitioner — Fiedler-vector bisection (recursive)
# -----------------------------------------------------------------------

class SpectralPartitioner(BasePartitioner):
    """Spectral bisection using the Fiedler vector of the graph Laplacian.

    For k > 2 partitions the algorithm recursively bisects the largest
    partition until the target count is reached.
    """

    def partition(self, graph: CircuitGraph, num_partitions: int) -> list[set[int]]:
        n = graph.num_qubits
        k = min(num_partitions, n)

        if k <= 0:
            return []
        if k == 1:
            return [set(range(n))]
        if n == 0:
            return [set() for _ in range(k)]

        # Start with all qubits in one group, then recursively bisect.
        groups: list[set[int]] = [set(range(n))]

        while len(groups) < k:
            # Pick the largest group to split.
            largest_idx = max(range(len(groups)), key=lambda i: len(groups[i]))
            target = groups.pop(largest_idx)

            if len(target) < 2:
                # Cannot split a single qubit — put it back.
                groups.append(target)
                break

            a, b = self._bisect(graph, target)
            groups.append(a)
            groups.append(b)

        return groups

    @staticmethod
    def _bisect(graph: CircuitGraph, qubit_set: set[int]) -> tuple[set[int], set[int]]:
        """Split *qubit_set* into two halves via the Fiedler vector."""
        indices = sorted(qubit_set)
        m = len(indices)

        if m < 2:
            return (set(indices), set())

        # Build sub-Laplacian for the qubit subset.
        full_adj = graph.get_adjacency_matrix()
        sub_adj = np.zeros((m, m), dtype=np.float64)
        for i, qi in enumerate(indices):
            for j, qj in enumerate(indices):
                sub_adj[i, j] = full_adj[qi, qj]

        sub_deg = sub_adj.sum(axis=1)
        L_sub = np.diag(sub_deg) - sub_adj

        # Compute eigenvalues/vectors; second-smallest eigenvector = Fiedler.
        eigenvalues, eigenvectors = np.linalg.eigh(L_sub)

        # Fiedler vector is the eigenvector for the second-smallest eigenvalue.
        # eigh returns sorted eigenvalues so index 1 is what we want.
        fiedler_idx = 1 if m > 1 else 0
        fiedler = eigenvectors[:, fiedler_idx]

        part_a: set[int] = set()
        part_b: set[int] = set()
        for i, val in enumerate(fiedler):
            if val < 0:
                part_a.add(indices[i])
            else:
                part_b.add(indices[i])

        # Handle edge case: if Fiedler vector is constant (disconnected
        # subgraph) force an even split.
        if len(part_a) == 0 or len(part_b) == 0:
            half = m // 2
            part_a = set(indices[:half])
            part_b = set(indices[half:])

        return part_a, part_b


# -----------------------------------------------------------------------
# 3. Manual partitioner — even split by qubit index
# -----------------------------------------------------------------------

class ManualPartitioner(BasePartitioner):
    """Deterministic even split: qubits are distributed round-robin by index.

    Useful as a baseline or when the user explicitly wants a simple split
    that ignores gate connectivity.
    """

    def partition(self, graph: CircuitGraph, num_partitions: int) -> list[set[int]]:
        n = graph.num_qubits
        k = min(num_partitions, n)

        if k <= 0:
            return []
        if n == 0:
            return [set() for _ in range(k)]

        partitions: list[set[int]] = [set() for _ in range(k)]
        for q in range(n):
            partitions[q % k].add(q)
        return partitions

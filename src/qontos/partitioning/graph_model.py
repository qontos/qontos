"""Build weighted adjacency graphs from CircuitIR for partitioning analysis."""

from __future__ import annotations

import numpy as np

from qontos.models.circuit import CircuitIR, GateOperation
from qontos.partitioning.models import QubitEdge


class CircuitGraph:
    """Weighted adjacency graph derived from a quantum circuit.

    Nodes are qubits. An edge between two qubits exists when at least one
    multi-qubit gate acts on both. The edge weight equals the number of such
    gates (more shared gates => stronger coupling => higher cost to cut).
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        # Adjacency stored as dense matrix — circuits rarely exceed a few
        # thousand qubits so this is practical and fast for eigenvector work.
        self._adj: np.ndarray = np.zeros((num_qubits, num_qubits), dtype=np.float64)
        self._edge_gate_names: dict[tuple[int, int], list[str]] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_circuit_ir(cls, circuit_ir: CircuitIR) -> "CircuitGraph":
        """Create a CircuitGraph from a CircuitIR instance.

        Every multi-qubit gate contributes +1 weight to the edge between
        each pair of qubits it touches.
        """
        graph = cls(circuit_ir.num_qubits)

        for gate in circuit_ir.gates:
            if len(gate.qubits) < 2:
                continue
            # For each pair of qubits in this gate, increment the edge weight.
            qubits = sorted(gate.qubits)
            for i in range(len(qubits)):
                for j in range(i + 1, len(qubits)):
                    q_a, q_b = qubits[i], qubits[j]
                    graph._adj[q_a, q_b] += 1.0
                    graph._adj[q_b, q_a] += 1.0
                    key = (q_a, q_b)
                    graph._edge_gate_names.setdefault(key, []).append(gate.name)

        return graph

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_adjacency_matrix(self) -> np.ndarray:
        """Return the symmetric weighted adjacency matrix (n x n)."""
        return self._adj.copy()

    def get_degree_vector(self) -> np.ndarray:
        """Return the weighted degree of each qubit (row-sum of adjacency)."""
        return self._adj.sum(axis=1)

    def get_edge_weights(self) -> list[QubitEdge]:
        """Return all edges with non-zero weight as QubitEdge objects."""
        edges: list[QubitEdge] = []
        for i in range(self.num_qubits):
            for j in range(i + 1, self.num_qubits):
                w = self._adj[i, j]
                if w > 0:
                    names = self._edge_gate_names.get((i, j), [])
                    edges.append(QubitEdge(qubit_a=i, qubit_b=j, weight=w, gate_names=names))
        return edges

    def get_laplacian(self) -> np.ndarray:
        """Return the combinatorial graph Laplacian  L = D - A."""
        D = np.diag(self.get_degree_vector())
        return D - self._adj

    def edge_weight(self, q_a: int, q_b: int) -> float:
        """Return the weight of the edge between two qubits (0 if none)."""
        return float(self._adj[q_a, q_b])

    def neighbors(self, qubit: int) -> list[int]:
        """Return qubits connected to *qubit* by at least one gate."""
        return [int(j) for j in range(self.num_qubits) if self._adj[qubit, j] > 0]

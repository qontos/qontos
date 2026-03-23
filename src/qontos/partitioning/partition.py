"""Main Partitioner — orchestrates graph construction, heuristic selection,
cost evaluation, and PartitionPlan assembly.

Usage:
    from qontos.models.circuit import CircuitIR
    from qontos.partitioning.partition import Partitioner
    from qontos.partitioning.models import PartitionConstraints, PartitionStrategy

    plan = Partitioner().run(circuit_ir, job_id="job-42")
"""

from __future__ import annotations

import hashlib
import uuid

from qontos.models.circuit import CircuitIR, GateOperation
from qontos.models.partition import PartitionPlan, PartitionEntry, DependencyEdge

from qontos.partitioning.graph_model import CircuitGraph
from qontos.partitioning.heuristics import (
    BasePartitioner,
    GreedyPartitioner,
    ManualPartitioner,
    SpectralPartitioner,
)
from qontos.partitioning.cost_model import PartitionCostModel, PER_OP_OVERHEAD_US
from qontos.partitioning.models import (
    CostEstimate,
    PartitionConstraints,
    PartitionStrategy,
)


# Threshold: if a circuit has fewer qubits than this, skip partitioning.
_MIN_QUBITS_FOR_SPLIT = 2


class Partitioner:
    """Top-level entry point for the partitioner service.

    Accepts a CircuitIR and optional constraints, runs the requested (or
    auto-selected) strategy, evaluates the cost, and returns a fully
    populated PartitionPlan ready for the scheduler.
    """

    def __init__(self, cost_model: PartitionCostModel | None = None) -> None:
        self._cost_model = cost_model or PartitionCostModel()
        self._strategies: dict[PartitionStrategy, BasePartitioner] = {
            PartitionStrategy.GREEDY: GreedyPartitioner(),
            PartitionStrategy.SPECTRAL: SpectralPartitioner(),
            PartitionStrategy.MANUAL: ManualPartitioner(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        circuit_ir: CircuitIR,
        job_id: str = "",
        constraints: PartitionConstraints | None = None,
    ) -> PartitionPlan:
        """Partition *circuit_ir* and return a PartitionPlan."""
        constraints = constraints or PartitionConstraints()

        if not job_id:
            job_id = uuid.uuid4().hex[:12]

        num_partitions = self._resolve_partition_count(circuit_ir, constraints)
        graph = CircuitGraph.from_circuit_ir(circuit_ir)

        # --- trivial case: single partition --------------------------------
        if num_partitions <= 1 or circuit_ir.num_qubits < _MIN_QUBITS_FOR_SPLIT:
            return self._single_partition_plan(circuit_ir, job_id, constraints)

        # --- choose strategy -----------------------------------------------
        strategy = self._select_strategy(constraints, circuit_ir)
        heuristic = self._strategies[strategy]
        qubit_sets = heuristic.partition(graph, num_partitions)

        # --- evaluate cost -------------------------------------------------
        cost = self._cost_model.evaluate(graph, qubit_sets)

        # --- assemble plan -------------------------------------------------
        return self._build_plan(
            circuit_ir=circuit_ir,
            job_id=job_id,
            strategy=strategy,
            qubit_sets=qubit_sets,
            cost=cost,
            graph=graph,
        )

    # ------------------------------------------------------------------
    # Sub-circuit extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_subcircuit_qasm(
        circuit_ir: CircuitIR,
        qubit_indices: set[int],
        qubit_mapping: dict[int, int],
    ) -> str:
        """Extract an OpenQASM 2.0 string for the subcircuit on *qubit_indices*.

        Only gates whose qubits are ALL within *qubit_indices* are included
        (inter-module gates are excluded — they need special handling by the
        executor / linker).  Qubit indices are remapped to local numbering
        via *qubit_mapping* (global -> local).
        """
        local_num_qubits = len(qubit_indices)
        local_num_clbits = local_num_qubits  # 1 classical bit per qubit

        lines: list[str] = [
            "OPENQASM 2.0;",
            'include "qelib1.inc";',
            f"qreg q[{local_num_qubits}];",
            f"creg c[{local_num_clbits}];",
        ]

        for gate in circuit_ir.gates:
            gate_qubits = set(gate.qubits)
            # Only include gates entirely within this partition
            if not gate_qubits.issubset(qubit_indices):
                continue

            local_qubits = [qubit_mapping[q] for q in gate.qubits]

            if gate.params:
                param_str = ",".join(str(p) for p in gate.params)
                qubit_str = ",".join(f"q[{lq}]" for lq in local_qubits)
                lines.append(f"{gate.name}({param_str}) {qubit_str};")
            else:
                qubit_str = ",".join(f"q[{lq}]" for lq in local_qubits)
                lines.append(f"{gate.name} {qubit_str};")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_partition_count(
        self, circuit_ir: CircuitIR, constraints: PartitionConstraints
    ) -> int:
        """Determine how many partitions to create."""
        if constraints.target_partitions is not None:
            return max(1, constraints.target_partitions)

        if constraints.max_qubits_per_partition is not None:
            count = -(-circuit_ir.num_qubits // constraints.max_qubits_per_partition)  # ceil div
            return max(constraints.min_partitions, count)

        # Default: let the strategy decide — but respect min/max.
        # Heuristic default: 1 partition per ~10 qubits, minimum 2 if enough qubits.
        auto_count = max(2, circuit_ir.num_qubits // 10)
        auto_count = max(auto_count, constraints.min_partitions)
        if constraints.max_partitions is not None:
            auto_count = min(auto_count, constraints.max_partitions)
        return auto_count

    def _select_strategy(
        self, constraints: PartitionConstraints, circuit_ir: CircuitIR
    ) -> PartitionStrategy:
        """Pick a concrete strategy when AUTO is requested."""
        if constraints.preferred_strategy != PartitionStrategy.AUTO:
            return constraints.preferred_strategy

        # Heuristic: spectral for larger circuits, greedy for smaller ones.
        if circuit_ir.num_qubits >= 20:
            return PartitionStrategy.SPECTRAL
        return PartitionStrategy.GREEDY

    def _single_partition_plan(
        self, circuit_ir: CircuitIR, job_id: str, constraints: PartitionConstraints
    ) -> PartitionPlan:
        """Return a plan that keeps everything in one module."""
        all_qubits = set(range(circuit_ir.num_qubits))
        mapping = {q: q for q in range(circuit_ir.num_qubits)}
        qasm = self.extract_subcircuit_qasm(circuit_ir, all_qubits, mapping)

        entry = PartitionEntry(
            partition_id=f"{job_id}-p0",
            partition_index=0,
            qubit_indices=list(range(circuit_ir.num_qubits)),
            num_qubits=circuit_ir.num_qubits,
            gate_count=circuit_ir.gate_count,
            depth=circuit_ir.depth,
            qubit_mapping=mapping,
            circuit_data=qasm,
            circuit_format="openqasm2",
        )
        strategy_name = constraints.preferred_strategy.value
        return PartitionPlan(
            job_id=job_id,
            strategy=strategy_name,
            partitions=[entry],
            total_inter_module_gates=0,
            estimated_module_count=1,
            estimated_communication_overhead_us=0.0,
            partition_balance_score=1.0,
            cut_ratio=0.0,
        )

    def _build_plan(
        self,
        circuit_ir: CircuitIR,
        job_id: str,
        strategy: PartitionStrategy,
        qubit_sets: list[set[int]],
        cost: CostEstimate,
        graph: CircuitGraph,
    ) -> PartitionPlan:
        """Assemble a PartitionPlan from heuristic output + cost estimate."""

        qubit_to_part = _qubit_lookup(qubit_sets)
        entries: list[PartitionEntry] = []
        dependency_map: dict[tuple[str, str], DependencyEdge] = {}

        for p_idx, qset in enumerate(qubit_sets):
            sorted_qubits = sorted(qset)
            local_mapping = {g: l for l, g in enumerate(sorted_qubits)}

            # Count gates and depth local to this partition.
            local_gates = 0
            inter_module = 0
            boundary_qubits: set[int] = set()
            for gate in circuit_ir.gates:
                parts_touched = {qubit_to_part.get(q, -1) for q in gate.qubits}
                if p_idx in parts_touched:
                    if len(parts_touched) == 1:
                        local_gates += 1
                    else:
                        inter_module += 1
                        for q in gate.qubits:
                            if qubit_to_part.get(q) == p_idx:
                                boundary_qubits.add(q)

                        # Record dependency edges.
                        for other_part in parts_touched:
                            if other_part == p_idx or other_part == -1:
                                continue
                            key = (
                                f"{job_id}-p{min(p_idx, other_part)}",
                                f"{job_id}-p{max(p_idx, other_part)}",
                            )
                            if key not in dependency_map:
                                dependency_map[key] = DependencyEdge(
                                    from_partition=key[0],
                                    to_partition=key[1],
                                    gate_name=gate.name,
                                    shared_qubits=list(
                                        {q for q in gate.qubits if qubit_to_part.get(q) in (p_idx, other_part)}
                                    ),
                                    estimated_latency_us=PER_OP_OVERHEAD_US,
                                )
                            else:
                                dep = dependency_map[key]
                                dep.estimated_latency_us += PER_OP_OVERHEAD_US
                                for q in gate.qubits:
                                    if q not in dep.shared_qubits:
                                        dep.shared_qubits.append(q)

            p_id = f"{job_id}-p{p_idx}"
            qasm = self.extract_subcircuit_qasm(circuit_ir, qset, local_mapping)
            entries.append(
                PartitionEntry(
                    partition_id=p_id,
                    partition_index=p_idx,
                    qubit_indices=sorted_qubits,
                    num_qubits=len(sorted_qubits),
                    gate_count=local_gates + inter_module,
                    depth=circuit_ir.depth,  # conservative upper bound
                    qubit_mapping=local_mapping,
                    inter_module_gates=inter_module,
                    boundary_qubits=sorted(boundary_qubits),
                    circuit_data=qasm,
                    circuit_format="openqasm2",
                )
            )

        return PartitionPlan(
            job_id=job_id,
            strategy=strategy.value,
            partitions=entries,
            dependencies=list(dependency_map.values()),
            total_inter_module_gates=cost.inter_module_gates,
            estimated_module_count=len(entries),
            estimated_communication_overhead_us=cost.communication_overhead_us,
            partition_balance_score=cost.partition_balance_score,
            cut_ratio=cost.cut_ratio,
        )


def _qubit_lookup(qubit_sets: list[set[int]]) -> dict[int, int]:
    lookup: dict[int, int] = {}
    for idx, qs in enumerate(qubit_sets):
        for q in qs:
            lookup[q] = idx
    return lookup

"""Result aggregation — merges multi-partition execution results.

Combines outputs from distributed quantum execution into a unified RunResult.
Supports three aggregation strategies:

1. **Passthrough** — single partition, no merging needed.
2. **Independent merge (tensor product)** — valid ONLY when partitions have no
   inter-module gates (no entanglement across partition boundaries).
3. **Entangled merge (marginal reconstruction)** — for circuits that were cut
   across entangled qubits. Uses weighted marginal reconstruction and flags
   fidelity degradation from the partition cuts.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from qontos.models.partition import PartitionPlan
from qontos.models.result import RunResult, PartitionResult


# Fidelity penalty per inter-module gate that was cut.  This is a conservative
# classical estimate — real QPU fidelity depends on the gate error model.
_FIDELITY_PENALTY_PER_CUT = 0.02


class ResultAggregator:
    """Merges partition results into a unified RunResult."""

    def aggregate(
        self,
        job_id: str,
        partition_results: list[PartitionResult],
        partition_plan: PartitionPlan | None = None,
    ) -> RunResult:
        """Aggregate results from all partitions of a job.

        Parameters
        ----------
        job_id:
            Unique identifier for the job.
        partition_results:
            Execution results from each partition.
        partition_plan:
            Optional partition plan used to decide the merging strategy.
            When provided, the aggregator inspects dependency edges and
            inter-module gate counts to choose between tensor-product
            (independent) and marginal-reconstruction (entangled) merging.
        """
        if len(partition_results) == 0:
            return RunResult(
                job_id=job_id,
                status="failed",
                final_counts={},
                total_shots=0,
                proof_hash="",
            )

        if len(partition_results) == 1:
            return self._single_partition(job_id, partition_results[0])

        # Detect strategy from partition plan metadata
        strategy = self._detect_strategy(partition_results, partition_plan)

        if strategy == "independent":
            return self._independent_merge(job_id, partition_results, partition_plan)
        else:
            return self._entangled_merge(job_id, partition_results, partition_plan)

    # ------------------------------------------------------------------
    # Strategy detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_strategy(
        results: list[PartitionResult],
        plan: PartitionPlan | None,
    ) -> str:
        """Decide whether partitions are independent or entangled.

        Returns ``"independent"`` when tensor-product merging is physically
        valid, or ``"entangled"`` when marginal reconstruction is needed.
        """
        if plan is None:
            # Without a plan we cannot know — fall back to the safer strategy.
            return "entangled"

        # If ANY dependency edges exist, the partitions share entanglement.
        if plan.dependencies:
            return "entangled"

        # Also check per-partition inter-module gate counts.
        if any(p.inter_module_gates > 0 for p in plan.partitions):
            return "entangled"

        return "independent"

    # ------------------------------------------------------------------
    # Single partition — passthrough
    # ------------------------------------------------------------------

    def _single_partition(self, job_id: str, result: PartitionResult) -> RunResult:
        """Passthrough for single-partition jobs."""
        return RunResult(
            job_id=job_id,
            status="completed",
            final_counts=result.counts,
            total_shots=result.shots_completed,
            cost_usd=result.cost_usd,
            latency_ms=result.execution_time_ms,
            partition_results=[result],
            aggregation_method="passthrough",
            fidelity_estimate=1.0,
            metadata={"num_partitions": 1},
        )

    # ------------------------------------------------------------------
    # Independent merge — tensor product (no entanglement across cuts)
    # ------------------------------------------------------------------

    def _independent_merge(
        self,
        job_id: str,
        results: list[PartitionResult],
        plan: PartitionPlan | None,
    ) -> RunResult:
        """Tensor-product merge — valid when partitions share no entanglement.

        Each partition's probability distribution is independent, so the joint
        distribution is the Cartesian product of the marginals.
        """
        sorted_results = sorted(results, key=lambda r: r.partition_index)

        # Build per-partition probability distributions
        distributions: list[dict[str, float]] = []
        shot_counts: list[int] = []
        for r in sorted_results:
            total = sum(r.counts.values())
            dist = {k: v / total for k, v in r.counts.items()} if total > 0 else {}
            distributions.append(dist)
            shot_counts.append(total)

        # Tensor product
        merged_dist = distributions[0]
        for dist in distributions[1:]:
            new_merged: dict[str, float] = {}
            for key1, prob1 in merged_dist.items():
                for key2, prob2 in dist.items():
                    combined = key1 + key2
                    new_merged[combined] = prob1 * prob2
            merged_dist = new_merged

        # Convert probabilities back to counts
        min_shots = min(shot_counts)
        merged_counts: dict[str, int] = {}
        for key, prob in merged_dist.items():
            count = round(prob * min_shots)
            if count > 0:
                merged_counts[key] = count

        total_cost = sum(r.cost_usd for r in sorted_results)
        max_latency = max(r.execution_time_ms for r in sorted_results)

        return RunResult(
            job_id=job_id,
            status="completed",
            final_counts=merged_counts,
            total_shots=min_shots,
            cost_usd=total_cost,
            latency_ms=max_latency,
            partition_results=sorted_results,
            aggregation_method="tensor_product",
            fidelity_estimate=1.0,  # exact for independent partitions
            metadata={
                "num_partitions": len(sorted_results),
                "strategy": "independent",
            },
        )

    # ------------------------------------------------------------------
    # Entangled merge — marginal reconstruction with fidelity penalty
    # ------------------------------------------------------------------

    def _entangled_merge(
        self,
        job_id: str,
        results: list[PartitionResult],
        plan: PartitionPlan | None,
    ) -> RunResult:
        """Marginal reconstruction merge for entangled partitions.

        When a circuit is cut across entangled qubits the tensor-product
        assumption is invalid.  Instead we:

        1. Compute the total number of qubits across all partitions.
        2. Map each partition's local bitstrings back to global qubit positions.
        3. For each partition, build a marginal probability distribution over
           its qubits.
        4. Combine marginals via weighted voting: for every candidate global
           bitstring, its score is the product of consistent marginal
           probabilities (where available).  For qubits involved in cuts
           (boundary qubits), we average contributions from the partitions
           that share them.
        5. Apply a fidelity penalty proportional to the number of cut gates.

        This is a classical approximation — it does NOT recover the full
        quantum correlations lost by circuit cutting, but it produces the
        best classically-achievable reconstruction from the available
        marginal data.
        """
        sorted_results = sorted(results, key=lambda r: r.partition_index)

        # ----- build qubit mapping from plan -----
        if plan is None:
            # Fallback: assume partitions are concatenated in order
            return self._fallback_entangled_merge(job_id, sorted_results)

        partition_entries = sorted(plan.partitions, key=lambda p: p.partition_index)

        # Total number of global qubits
        all_global_qubits: set[int] = set()
        for entry in partition_entries:
            all_global_qubits.update(entry.qubit_indices)
        num_global_qubits = max(all_global_qubits) + 1 if all_global_qubits else 0

        # Build per-partition marginal distributions keyed by GLOBAL qubit index
        # Each marginal is: global_qubit -> {0: prob, 1: prob}
        partition_marginals: list[dict[int, dict[int, float]]] = []
        for entry, result in zip(partition_entries, sorted_results):
            total = sum(result.counts.values())
            if total == 0:
                partition_marginals.append({})
                continue

            # inverse mapping: local -> global
            local_to_global = {v: k for k, v in entry.qubit_mapping.items()}
            num_local = entry.num_qubits

            marginal: dict[int, dict[int, float]] = {}
            for gq in entry.qubit_indices:
                marginal[gq] = {0: 0.0, 1: 0.0}

            for bitstring, count in result.counts.items():
                prob = count / total
                # bitstring is MSB-first: bit 0 of string = highest qubit index
                for local_idx in range(min(len(bitstring), num_local)):
                    bit_val = int(bitstring[local_idx])
                    global_idx = local_to_global.get(local_idx, local_idx)
                    if global_idx in marginal:
                        marginal[global_idx][bit_val] += prob

            partition_marginals.append(marginal)

        # ----- combine marginals into global distribution -----
        # For each global qubit, average the marginal across all partitions
        # that include it (handles boundary qubits shared by multiple partitions).
        global_marginals: dict[int, dict[int, float]] = {}
        for gq in range(num_global_qubits):
            accum = {0: 0.0, 1: 0.0}
            contrib_count = 0
            for pm in partition_marginals:
                if gq in pm:
                    accum[0] += pm[gq][0]
                    accum[1] += pm[gq][1]
                    contrib_count += 1
            if contrib_count > 0:
                global_marginals[gq] = {
                    0: accum[0] / contrib_count,
                    1: accum[1] / contrib_count,
                }
            else:
                # Qubit not covered by any partition — assume uniform
                global_marginals[gq] = {0: 0.5, 1: 0.5}

        # ----- reconstruct global distribution from independent marginals -----
        # Build candidate bitstrings and score them by product of marginals.
        # For large qubit counts this is intractable; cap at 2^20 and sample.
        min_shots = min(sum(r.counts.values()) for r in sorted_results)
        merged_counts: dict[str, int] = {}

        if num_global_qubits <= 20:
            # Exact enumeration
            for i in range(2 ** num_global_qubits):
                bits = format(i, f"0{num_global_qubits}b")
                prob = 1.0
                for q_idx in range(num_global_qubits):
                    bit_val = int(bits[q_idx])
                    prob *= global_marginals.get(q_idx, {0: 0.5, 1: 0.5})[bit_val]
                count = round(prob * min_shots)
                if count > 0:
                    merged_counts[bits] = count
        else:
            # For large circuits: sample from marginals
            merged_counts = self._sample_from_marginals(
                global_marginals, num_global_qubits, min_shots
            )

        # ----- fidelity estimate -----
        total_cuts = plan.total_inter_module_gates
        fidelity = max(0.0, 1.0 - total_cuts * _FIDELITY_PENALTY_PER_CUT)

        total_cost = sum(r.cost_usd for r in sorted_results)
        max_latency = max(r.execution_time_ms for r in sorted_results)

        boundary_qubits_all: list[int] = []
        for entry in partition_entries:
            boundary_qubits_all.extend(entry.boundary_qubits)

        return RunResult(
            job_id=job_id,
            status="completed",
            final_counts=merged_counts,
            total_shots=min_shots,
            cost_usd=total_cost,
            latency_ms=max_latency,
            partition_results=sorted_results,
            aggregation_method="marginal_reconstruction",
            fidelity_estimate=fidelity,
            metadata={
                "num_partitions": len(sorted_results),
                "strategy": "entangled",
                "total_inter_module_gates": total_cuts,
                "boundary_qubits": sorted(set(boundary_qubits_all)),
                "fidelity_degraded": total_cuts > 0,
                "warning": (
                    "Fidelity is degraded due to partition cuts across entangled "
                    "qubits. The merged distribution is a classical approximation "
                    "reconstructed from marginal distributions."
                    if total_cuts > 0
                    else None
                ),
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fallback_entangled_merge(
        self, job_id: str, sorted_results: list[PartitionResult]
    ) -> RunResult:
        """Fallback entangled merge when no partition plan is available.

        Without qubit mapping metadata we cannot do proper marginal
        reconstruction. We concatenate bitstrings (like tensor product)
        but flag the result as low-fidelity.
        """
        distributions: list[dict[str, float]] = []
        shot_counts: list[int] = []
        for r in sorted_results:
            total = sum(r.counts.values())
            dist = {k: v / total for k, v in r.counts.items()} if total > 0 else {}
            distributions.append(dist)
            shot_counts.append(total)

        merged_dist = distributions[0]
        for dist in distributions[1:]:
            new_merged: dict[str, float] = {}
            for key1, prob1 in merged_dist.items():
                for key2, prob2 in dist.items():
                    new_merged[key1 + key2] = prob1 * prob2
            merged_dist = new_merged

        min_shots = min(shot_counts) if shot_counts else 0
        merged_counts: dict[str, int] = {}
        for key, prob in merged_dist.items():
            count = round(prob * min_shots)
            if count > 0:
                merged_counts[key] = count

        total_cost = sum(r.cost_usd for r in sorted_results)
        max_latency = max(r.execution_time_ms for r in sorted_results)

        return RunResult(
            job_id=job_id,
            status="completed",
            final_counts=merged_counts,
            total_shots=min_shots,
            cost_usd=total_cost,
            latency_ms=max_latency,
            partition_results=sorted_results,
            aggregation_method="marginal_reconstruction_fallback",
            fidelity_estimate=0.5,  # conservative — we have no plan metadata
            metadata={
                "num_partitions": len(sorted_results),
                "strategy": "entangled_fallback",
                "warning": (
                    "No partition plan provided — cannot perform proper marginal "
                    "reconstruction. Result uses tensor-product concatenation with "
                    "degraded fidelity estimate."
                ),
            },
        )

    @staticmethod
    def _sample_from_marginals(
        global_marginals: dict[int, dict[int, float]],
        num_qubits: int,
        num_samples: int,
    ) -> dict[str, int]:
        """Sample global bitstrings from independent marginals.

        Used when exact enumeration is intractable (>20 qubits).
        Uses deterministic sampling based on marginal probabilities
        to avoid requiring a random seed.
        """
        counts: dict[str, int] = defaultdict(int)

        # Deterministic approach: enumerate the most-probable bitstrings.
        # For each qubit, pick the more-probable value and compute the
        # probability of that "mode" bitstring, then distribute shots
        # proportionally around it using marginals.

        # Build the mode bitstring (most probable per qubit)
        mode_bits: list[int] = []
        for q in range(num_qubits):
            m = global_marginals.get(q, {0: 0.5, 1: 0.5})
            mode_bits.append(0 if m[0] >= m[1] else 1)

        # Generate bitstrings by flipping one qubit at a time from mode
        # and weighting by marginal probability ratio
        mode_str = "".join(str(b) for b in mode_bits)

        # Start with the mode string getting a base allocation
        candidates: dict[str, float] = {}

        # Mode bitstring probability
        mode_prob = 1.0
        for q in range(num_qubits):
            m = global_marginals.get(q, {0: 0.5, 1: 0.5})
            mode_prob *= m[mode_bits[q]]
        candidates[mode_str] = mode_prob

        # Single-bit flips from mode
        for q in range(num_qubits):
            flipped = list(mode_bits)
            flipped[q] = 1 - flipped[q]
            flip_str = "".join(str(b) for b in flipped)
            flip_prob = 1.0
            for q2 in range(num_qubits):
                m = global_marginals.get(q2, {0: 0.5, 1: 0.5})
                flip_prob *= m[flipped[q2]]
            if flip_prob > 0:
                candidates[flip_str] = flip_prob

        # Normalize and convert to counts
        total_prob = sum(candidates.values())
        if total_prob > 0:
            for bs, prob in candidates.items():
                count = round((prob / total_prob) * num_samples)
                if count > 0:
                    counts[bs] = count

        return dict(counts)

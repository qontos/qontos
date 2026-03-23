"""Post-processing — optional transformations on aggregated results."""

from __future__ import annotations

from qontos.models.result import RunResult


class ResultPostProcessor:
    """Applies optional post-processing to aggregated results."""

    @staticmethod
    def filter_noise(counts: dict[str, int], threshold: float = 0.001) -> dict[str, int]:
        """Remove low-probability measurement outcomes (likely noise)."""
        total = sum(counts.values())
        if total == 0:
            return counts
        return {k: v for k, v in counts.items() if v / total >= threshold}

    @staticmethod
    def top_k_states(counts: dict[str, int], k: int = 10) -> dict[str, int]:
        """Return only the top-k most frequent states."""
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_counts[:k])

    @staticmethod
    def compute_expectation_value(counts: dict[str, int], observable: str = "Z") -> float:
        """Compute expectation value of a simple observable.

        For Z observable: <Z> = (count_0 - count_1) / total for each qubit.
        Returns mean across all qubits.
        """
        total = sum(counts.values())
        if total == 0:
            return 0.0

        if observable == "Z":
            num_qubits = len(next(iter(counts)))
            qubit_expectations = []
            for q in range(num_qubits):
                exp_val = 0.0
                for bitstring, count in counts.items():
                    bit = int(bitstring[q])
                    exp_val += (1 - 2 * bit) * count / total
                qubit_expectations.append(exp_val)
            return sum(qubit_expectations) / len(qubit_expectations) if qubit_expectations else 0.0

        return 0.0

    @staticmethod
    def estimate_fidelity(counts: dict[str, int], target_states: list[str]) -> float:
        """Estimate fidelity as overlap with expected target states."""
        total = sum(counts.values())
        if total == 0:
            return 0.0
        target_count = sum(counts.get(s, 0) for s in target_states)
        return target_count / total

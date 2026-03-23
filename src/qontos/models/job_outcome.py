"""QNT-506: Canonical job outcome contract.
QNT-601: Canonical missing-partition reporting with enrichment tracking.
QNT-701: Separate failed vs missing partitions with disjoint invariant.
QNT-805: Canonical Outcome Contract Hardening -- enforced invariants with
         explicit error reporting and property-style verification.

Defines ``JobOutcome`` enum and ``JobOutcomeReport`` model as the single
source of truth for degraded-run semantics across worker, API, SDK,
dashboards, and replay.

No degraded run may ever be surfaced as plain "completed".

Partition categories (QNT-701 -- disjoint invariant):
  - completed: partitions that produced valid results
  - failed: partitions recorded in the ledger with status "failed"
  - missing: partitions expected but NEVER recorded in the ledger at all
  Invariants:
    failed ∩ missing == ∅
    completed + failed + len(missing) == total
    failed == len(failed_partition_ids)
    outcome matches actual counts

Enrichment lifecycle:
  - dispatch: initial report with best-effort missing/failed partition IDs
  - aggregate: CANONICAL stage -- refines missing/failed from actual results
  - finalize: adds proof/timestamps but NEVER overwrites aggregate partition data
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, model_validator

_logger = logging.getLogger(__name__)


class JobOutcome(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING = "pending"
    RUNNING = "running"


class JobOutcomeReport(BaseModel):
    outcome: JobOutcome
    total_partitions: int
    completed_partitions: int
    failed_partitions: int
    failed_partition_ids: list[str] = []
    missing_partition_ids: list[str] = []
    degradation_reason: Optional[str] = None
    enriched_at: Optional[str] = None
    enrichment_stage: Optional[str] = None

    _frozen: bool = False

    CANONICAL_FIELDS: ClassVar[list[str]] = [
        "outcome",
        "total_partitions",
        "completed_partitions",
        "failed_partitions",
        "failed_partition_ids",
        "missing_partition_ids",
        "degradation_reason",
    ]

    INTERNAL_FIELDS: ClassVar[set[str]] = {"_frozen"}

    @model_validator(mode="after")
    def _derive_and_check_invariants(self) -> "JobOutcomeReport":
        """QNT-805 / QNT-1002: Derive completed_partitions, then verify invariants.

        ``completed_partitions`` is ALWAYS derived from
        ``total_partitions - failed_partitions - len(missing_partition_ids)``.
        Any externally-provided value is silently overwritten so that the
        sum invariant can never be violated by stale/incorrect input.

        After derivation, logs any remaining violations but does NOT raise
        -- graceful degradation.
        """
        # QNT-1002: completed_partitions is always derived, never authoritative
        derived = (
            self.total_partitions
            - self.failed_partitions
            - len(self.missing_partition_ids)
        )
        object.__setattr__(self, "completed_partitions", max(derived, 0))

        valid, violations = self.verify_disjoint()
        if not valid:
            _logger.warning(
                "QNT-805 disjoint invariant violations detected on construction: %s",
                "; ".join(violations),
            )
        return self

    def freeze(self) -> JobOutcomeReport:
        """Return a frozen copy of this report.

        QNT-702: A frozen report's ``enrich()`` raises ``ValueError``
        to prevent post-finalize mutation of the canonical report.
        """
        copy = self.model_copy()
        object.__setattr__(copy, "_frozen", True)
        return copy

    def canonical_dict(self) -> dict:
        """Return ONLY the canonical fields -- no internal bookkeeping.

        QNT-702: This is the contract surface that all consumers
        (worker, API, SDK, dashboard, replay) agree on.
        """
        full = self.model_dump(mode="json")
        return {k: full[k] for k in self.CANONICAL_FIELDS if k in full}

    def verify_disjoint(self) -> tuple[bool, list[str]]:
        """QNT-701 / QNT-805: Verify all disjoint partition invariants.

        Four invariants are checked:
        1. ``failed_partition_ids ∩ missing_partition_ids == ∅``
        2. ``completed_partitions + failed_partitions + len(missing_partition_ids) == total_partitions``
        3. ``failed_partitions == len(failed_partition_ids)``
        4. outcome matches actual counts (e.g. failed>0 means not "completed")

        Returns
        -------
        tuple[bool, list[str]]
            ``(valid, violations)`` where *valid* is ``True`` when all
            invariants hold and *violations* is a list of human-readable
            violation descriptions (empty when valid).
        """
        violations: list[str] = []
        failed_set = set(self.failed_partition_ids)
        missing_set = set(self.missing_partition_ids)

        # Invariant 1: disjoint sets
        overlap = failed_set & missing_set
        if overlap:
            violations.append(
                f"failed ∩ missing != ∅: overlapping IDs {sorted(overlap)}"
            )

        # Invariant 2: sum invariant
        accounted = (
            self.completed_partitions
            + self.failed_partitions
            + len(self.missing_partition_ids)
        )
        if self.total_partitions > 0 and accounted != self.total_partitions:
            violations.append(
                f"completed({self.completed_partitions}) + "
                f"failed({self.failed_partitions}) + "
                f"missing({len(self.missing_partition_ids)}) = {accounted} "
                f"!= total_partitions({self.total_partitions})"
            )

        # Invariant 3: failed count matches ID list length
        if self.failed_partitions != len(self.failed_partition_ids):
            violations.append(
                f"failed_partitions({self.failed_partitions}) != "
                f"len(failed_partition_ids)({len(self.failed_partition_ids)})"
            )

        # Invariant 4: outcome consistency with actual counts
        if self.outcome == JobOutcome.COMPLETED:
            if self.failed_partitions > 0:
                violations.append(
                    f"outcome is 'completed' but failed_partitions={self.failed_partitions}"
                )
            if len(self.missing_partition_ids) > 0:
                violations.append(
                    f"outcome is 'completed' but {len(self.missing_partition_ids)} missing partitions"
                )
        elif self.outcome == JobOutcome.COMPLETED_WITH_FAILURES:
            if self.failed_partitions == 0 and len(self.missing_partition_ids) == 0:
                violations.append(
                    "outcome is 'completed_with_failures' but no failed or missing partitions"
                )

        return (len(violations) == 0, violations)

    def strict_verify(self) -> None:
        """QNT-805: Raise ``ValueError`` if any invariant is violated.

        Collects all violations from ``verify_disjoint()`` and raises a
        single ``ValueError`` listing every problem found.
        """
        valid, violations = self.verify_disjoint()
        if not valid:
            raise ValueError(
                f"QNT-805 outcome contract violations ({len(violations)}): "
                + "; ".join(violations)
            )

    def validate_completeness(self) -> list[str]:
        """Return a list of warnings if any field seems inconsistent.

        Examples of inconsistencies caught:
        - ``outcome`` is "completed" but ``failed_partitions`` > 0
        - ``failed_partitions`` count does not match ``failed_partition_ids`` length
        - ``completed_partitions + failed_partitions`` exceeds ``total_partitions``
        - QNT-701: disjoint invariant violated (failed ∩ missing != ∅)
        """
        warnings: list[str] = []

        if self.outcome == JobOutcome.COMPLETED and self.failed_partitions > 0:
            warnings.append(
                f"outcome is 'completed' but failed_partitions={self.failed_partitions}"
            )

        if self.outcome == JobOutcome.COMPLETED and len(self.missing_partition_ids) > 0:
            warnings.append(
                f"outcome is 'completed' but missing_partition_ids has "
                f"{len(self.missing_partition_ids)} entries"
            )

        if self.failed_partitions != len(self.failed_partition_ids):
            warnings.append(
                f"failed_partitions={self.failed_partitions} does not match "
                f"len(failed_partition_ids)={len(self.failed_partition_ids)}"
            )

        accounted = self.completed_partitions + self.failed_partitions + len(self.missing_partition_ids)
        if self.total_partitions > 0 and accounted > self.total_partitions:
            warnings.append(
                f"completed({self.completed_partitions}) + failed({self.failed_partitions}) "
                f"+ missing({len(self.missing_partition_ids)}) = {accounted} "
                f"exceeds total_partitions={self.total_partitions}"
            )

        if (
            self.outcome == JobOutcome.COMPLETED_WITH_FAILURES
            and self.failed_partitions == 0
            and len(self.missing_partition_ids) == 0
        ):
            warnings.append(
                "outcome is 'completed_with_failures' but no failed or missing partitions"
            )

        # QNT-701: Check disjoint invariant
        failed_set = set(self.failed_partition_ids)
        missing_set = set(self.missing_partition_ids)
        overlap = failed_set & missing_set
        if overlap:
            warnings.append(
                f"disjoint invariant violated: partitions {sorted(overlap)} "
                f"appear in both failed_partition_ids and missing_partition_ids"
            )

        if self.total_partitions > 0 and accounted != self.total_partitions:
            warnings.append(
                f"sum invariant violated: completed({self.completed_partitions}) + "
                f"failed({self.failed_partitions}) + missing({len(self.missing_partition_ids)}) "
                f"= {accounted} != total_partitions={self.total_partitions}"
            )

        return warnings

    @property
    def is_success(self) -> bool:
        return self.outcome == JobOutcome.COMPLETED

    @property
    def is_degraded(self) -> bool:
        return self.outcome == JobOutcome.COMPLETED_WITH_FAILURES

    @property
    def is_failed(self) -> bool:
        return self.outcome == JobOutcome.FAILED

    @property
    def is_terminal(self) -> bool:
        return self.outcome in (
            JobOutcome.COMPLETED,
            JobOutcome.COMPLETED_WITH_FAILURES,
            JobOutcome.FAILED,
            JobOutcome.CANCELLED,
        )

    def enrich(
        self,
        *,
        missing_partition_ids: list[str] | None = None,
        failed_partition_ids: list[str] | None = None,
        enrichment_stage: str,
        degradation_reason: str | None = None,
    ) -> JobOutcomeReport:
        """Return a new report enriched with refined partition data.

        This method merges new partition information with existing data
        rather than blindly overwriting it.  The ``enrichment_stage``
        records which pipeline stage performed the enrichment so that
        downstream stages know whether to trust the existing data.

        Parameters
        ----------
        missing_partition_ids : list[str] | None
            Refined list of missing partition IDs.  When provided,
            replaces the current value (aggregate is the canonical
            source, so its value wins).
        failed_partition_ids : list[str] | None
            Refined list of failed partition IDs.  When provided,
            replaces the current value.
        enrichment_stage : str
            Which stage performed this enrichment ("dispatch",
            "aggregate", or "finalize").
        degradation_reason : str | None
            Optional updated degradation reason.

        Returns
        -------
        JobOutcomeReport
            A new report instance with the enriched fields.

        Raises
        ------
        ValueError
            If the report has been frozen via ``freeze()``.
        """
        if self._frozen:
            raise ValueError(
                "Cannot enrich a frozen JobOutcomeReport. "
                "Frozen reports are immutable after finalization."
            )

        updates: dict = {
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "enrichment_stage": enrichment_stage,
        }

        if missing_partition_ids is not None:
            updates["missing_partition_ids"] = missing_partition_ids

        if failed_partition_ids is not None:
            updates["failed_partition_ids"] = failed_partition_ids
            updates["failed_partitions"] = len(failed_partition_ids)

        if degradation_reason is not None:
            updates["degradation_reason"] = degradation_reason

        # QNT-701: Enforce disjoint categories -- a partition in failed
        # CANNOT also be in missing.  Remove any overlap from missing.
        new_failed_ids = updates.get("failed_partition_ids", self.failed_partition_ids)
        new_missing_ids = updates.get("missing_partition_ids", self.missing_partition_ids)
        failed_set = set(new_failed_ids)
        # Strip any failed IDs that leaked into missing
        new_missing_ids = [pid for pid in new_missing_ids if pid not in failed_set]
        updates["missing_partition_ids"] = new_missing_ids

        new_failed_count = updates.get("failed_partitions", self.failed_partitions)

        # QNT-701: completed_partitions is DERIVED: total - failed - missing
        new_completed = self.total_partitions - new_failed_count - len(new_missing_ids)

        if new_completed <= 0 and self.total_partitions > 0:
            updates["outcome"] = JobOutcome.FAILED
        elif new_failed_count > 0 or len(new_missing_ids) > 0:
            updates["outcome"] = JobOutcome.COMPLETED_WITH_FAILURES
        else:
            updates["outcome"] = JobOutcome.COMPLETED

        updates["completed_partitions"] = max(new_completed, 0)

        enriched = self.model_copy(update=updates)

        # QNT-701 / QNT-805: Verify disjoint invariant -- raise if violated
        valid, violations = enriched.verify_disjoint()
        if not valid:
            raise ValueError(
                f"QNT-701 disjoint invariant violated after enrichment: "
                + "; ".join(violations)
            )

        return enriched

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON transport."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> JobOutcomeReport:
        """Deserialize from a plain dict (e.g. API response payload)."""
        return cls.model_validate(data)

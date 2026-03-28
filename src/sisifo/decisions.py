"""Decision types produced by the reconciliation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    """What action Sísifo should take for a workflow run."""

    WAIT = "wait"
    """The run is still in progress and conditions are not yet violated."""

    CANCEL_AND_RETRY_FAILED = "cancel_and_retry_failed"
    """At least one rule timed out; cancel the run and re-run failed jobs."""

    RETRY_FAILED = "retry_failed"
    """At least one job failed; re-run only the failed jobs without cancelling."""

    COMPLETE = "complete"
    """All rules are satisfied; no action needed."""


@dataclass
class Reconciliation:
    """Result of reconciling a workflow run against the configured rules."""

    decision: Decision
    rationale: str
    affected_job_ids: list[int] = field(default_factory=list)

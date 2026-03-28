"""Tests for the reconciler."""

from __future__ import annotations

import json

from gh_models.actions import Job, Step, WorkflowRun
from whenever import Instant, minutes

from sisifo.config import Rule
from sisifo.decisions import Decision
from sisifo.reconciler import Reconciler

# ---------------------------------------------------------------------------
# Helpers to build minimal WorkflowRun instances for testing
# ---------------------------------------------------------------------------


def _now() -> Instant:
    return Instant.now()


def _started() -> Instant:
    """Return a started_at 30 minutes ago."""
    return _now() - minutes(30)


def _completed() -> Instant:
    """Return a completed_at 5 minutes ago."""
    return _now() - minutes(5)


def _make_step(
    name: str,
    status: str = "completed",
    conclusion: str = "success",
    started_at: Instant | None = None,
    completed_at: Instant | None = None,
) -> Step:
    if started_at is None:
        started_at = _started()
    if completed_at is None and status == "completed":
        completed_at = _completed()
    return Step.model_validate(
        {
            "name": name,
            "number": 1,
            "status": status,
            "conclusion": conclusion,
            "startedAt": started_at.format_iso() if started_at else "",
            "completedAt": completed_at.format_iso() if completed_at else "",
        }
    )


def _make_job(
    name: str,
    database_id: int = 1,
    status: str = "completed",
    conclusion: str = "success",
    started_at: Instant | None = None,
    completed_at: Instant | None = None,
    steps: list[Step] | None = None,
) -> Job:
    if started_at is None:
        started_at = _started()
    if completed_at is None and status == "completed":
        completed_at = _completed()
    return Job.model_validate(
        {
            "databaseId": database_id,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "startedAt": started_at.format_iso() if started_at else "",
            "completedAt": completed_at.format_iso() if completed_at else "",
            "url": "https://example.com",
            "steps": [
                json.loads(s.model_dump_json(by_alias=True)) for s in (steps or [])
            ],
        }
    )


def _make_run(
    jobs: list[Job],
    workflow_name: str = "Pull request",
    status: str = "in_progress",
) -> WorkflowRun:
    return WorkflowRun.model_validate(
        {
            "databaseId": 99999,
            "name": workflow_name,
            "workflowName": workflow_name,
            "workflowDatabaseId": 1,
            "number": 1,
            "attempt": 1,
            "status": status,
            "conclusion": "",
            "headBranch": "main",
            "headSha": "abc123",
            "event": "pull_request",
            "displayTitle": "Test",
            "createdAt": _started().format_iso(),
            "startedAt": _started().format_iso(),
            "updatedAt": _now().format_iso(),
            "url": "https://example.com",
            "jobs": [json.loads(j.model_dump_json(by_alias=True)) for j in jobs],
        }
    )


# ---------------------------------------------------------------------------
# Reconciler: job-level rules
# ---------------------------------------------------------------------------


class TestReconcilerJobRules:
    """Tests for job-level reconciliation."""

    def _rules(
        self,
        *,
        max_duration_s: int = 3600,
        on_timeout: list[str] | None = None,
        on_failure: list[str] | None = None,
    ) -> list[Rule]:
        return [
            Rule.model_validate(
                {
                    "name": "Build jobs",
                    "selector": {
                        "workflow": "Pull request",
                        "job": {"pattern": r"Build charm .*"},
                    },
                    "conditions": {
                        "maxDuration": max_duration_s,
                        "state": "success",
                    },
                    "actions": {
                        "onTimeout": on_timeout or ["cancel", "retry-failed"],
                        "onFailure": on_failure or ["retry-failed"],
                    },
                }
            )
        ]

    def test_all_success_returns_complete(self) -> None:
        """When all matching jobs succeeded, decision should be COMPLETE."""
        job = _make_job("Build charm | kubernetes / Build charm | ubuntu@24.04:amd64")
        run = _make_run([job])
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.COMPLETE

    def test_in_progress_within_timeout_returns_wait(self) -> None:
        """In-progress jobs within duration limit should return WAIT."""
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            status="in_progress",
            conclusion="",
            completed_at=None,
        )
        run = _make_run([job])
        # 30 minutes elapsed < 60 minutes limit
        result = Reconciler(self._rules(max_duration_s=3600)).reconcile(run)
        assert result.decision == Decision.WAIT

    def test_in_progress_past_timeout_returns_cancel(self) -> None:
        """In-progress jobs past the duration limit should return CANCEL_AND_RETRY."""
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            status="in_progress",
            conclusion="",
            completed_at=None,
        )
        run = _make_run([job])
        # 30 minutes elapsed > 10 minute limit
        result = Reconciler(self._rules(max_duration_s=60)).reconcile(run)
        assert result.decision == Decision.CANCEL_AND_RETRY_FAILED

    def test_failed_job_returns_retry(self) -> None:
        """Failed jobs should return RETRY_FAILED_JOBS."""
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            conclusion="failure",
        )
        run = _make_run([job])
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.RETRY_FAILED

    def test_no_matching_jobs_returns_complete(self) -> None:
        """No matching jobs should not trigger any actions."""
        job = _make_job("Some Other Job")
        run = _make_run([job])
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.COMPLETE

    def test_wrong_workflow_skips_rule(self) -> None:
        """Rules for a different workflow should be skipped."""
        job = _make_job("Build charm | kubernetes / Build charm | ubuntu@24.04:amd64")
        run = _make_run([job], workflow_name="Different Workflow")
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.COMPLETE

    def test_timeout_wins_over_failure(self) -> None:
        """CANCEL_AND_RETRY takes priority over RETRY_FAILED_JOBS."""
        jobs = [
            _make_job(
                "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
                database_id=1,
                status="in_progress",
                conclusion="",
                completed_at=None,
            ),
            _make_job(
                "Build charm | machines / Build charm | ubuntu@24.04:amd64",
                database_id=2,
                conclusion="failure",
            ),
        ]
        run = _make_run(jobs)
        result = Reconciler(self._rules(max_duration_s=60)).reconcile(run)
        assert result.decision == Decision.CANCEL_AND_RETRY_FAILED


# ---------------------------------------------------------------------------
# Reconciler: step-level rules
# ---------------------------------------------------------------------------


class TestReconcilerStepRules:
    """Tests for step-level reconciliation."""

    def _rules(self, *, max_duration_s: int = 3000) -> list[Rule]:
        return [
            Rule.model_validate(
                {
                    "name": "Pack charm step",
                    "selector": {
                        "workflow": "Pull request",
                        "job": {"pattern": r"Build charm .* / Build charm .*"},
                        "step": "Pack charm",
                    },
                    "conditions": {
                        "maxDuration": max_duration_s,
                        "state": "success",
                    },
                    "actions": {
                        "onTimeout": ["cancel", "retry-failed"],
                        "onFailure": ["retry-failed"],
                    },
                }
            )
        ]

    def test_step_success_returns_complete(self) -> None:
        """When the target step succeeded, decision should be COMPLETE."""
        step = _make_step("Pack charm")
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            steps=[step],
        )
        run = _make_run([job])
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.COMPLETE

    def test_step_in_progress_returns_wait(self) -> None:
        """When the target step is in progress, should WAIT."""
        step = _make_step(
            "Pack charm",
            status="in_progress",
            conclusion="",
            completed_at=None,
        )
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            status="in_progress",
            conclusion="",
            completed_at=None,
            steps=[step],
        )
        run = _make_run([job])
        result = Reconciler(self._rules(max_duration_s=3600)).reconcile(run)
        assert result.decision == Decision.WAIT

    def test_step_timeout_returns_cancel(self) -> None:
        """When the target step exceeds max duration, should CANCEL_AND_RETRY."""
        step = _make_step(
            "Pack charm",
            status="in_progress",
            conclusion="",
            completed_at=None,
        )
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            status="in_progress",
            conclusion="",
            completed_at=None,
            steps=[step],
        )
        run = _make_run([job])
        # 30 minutes elapsed > 1 second limit
        result = Reconciler(self._rules(max_duration_s=1)).reconcile(run)
        assert result.decision == Decision.CANCEL_AND_RETRY_FAILED

    def test_step_failure_returns_retry(self) -> None:
        """When the target step failed, should RETRY_FAILED_JOBS."""
        step = _make_step("Pack charm", conclusion="failure")
        job = _make_job(
            "Build charm | kubernetes / Build charm | ubuntu@24.04:amd64",
            steps=[step],
        )
        run = _make_run([job])
        result = Reconciler(self._rules()).reconcile(run)
        assert result.decision == Decision.RETRY_FAILED

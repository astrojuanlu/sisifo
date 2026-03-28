"""Tests for the gh_models.actions module."""

from __future__ import annotations

import re
from pathlib import Path

from gh_models.actions import (
    Conclusion,
    JobStatus,
    RunStatus,
    Step,
    StepStatus,
    WorkflowRun,
)

EXAMPLE_DIR = Path(__file__).parent.parent / "example"


class TestWorkflowRunParsing:
    """Parse a real GitHub API response into a WorkflowRun."""

    def test_parses_example_run(self, example_run: WorkflowRun) -> None:
        """The example run should parse without errors."""
        assert example_run.database_id == 23680020976
        assert example_run.workflow_name == "Pull request"
        assert example_run.status == RunStatus.IN_PROGRESS
        assert example_run.conclusion is None
        assert example_run.attempt == 3

    def test_run_has_jobs(self, example_run: WorkflowRun) -> None:
        """The example run should contain 14 jobs."""
        assert len(example_run.jobs) == 14

    def test_completed_job_has_duration(self, example_run: WorkflowRun) -> None:
        """A completed job should report a positive duration."""
        completed = [j for j in example_run.jobs if j.is_done]
        assert completed, "Expected at least one completed job"
        job = completed[0]
        assert job.duration_seconds is not None
        assert job.duration_seconds > 0

    def test_in_progress_job_has_no_completed_at(
        self, example_run: WorkflowRun
    ) -> None:
        """In-progress jobs should have completed_at == None."""
        in_progress = [j for j in example_run.jobs if j.status == JobStatus.IN_PROGRESS]
        assert in_progress, "Expected at least one in-progress job"
        job = in_progress[0]
        assert job.completed_at is None
        assert job.conclusion is None

    def test_in_progress_job_has_elapsed_seconds(
        self, example_run: WorkflowRun
    ) -> None:
        """elapsed_seconds should return a value for in-progress jobs."""
        in_progress = [j for j in example_run.jobs if j.status == JobStatus.IN_PROGRESS]
        job = in_progress[0]
        assert job.elapsed_seconds is not None
        assert job.elapsed_seconds > 0

    def test_steps_parsed(self, example_run: WorkflowRun) -> None:
        """Jobs should contain parsed steps."""
        job = example_run.jobs[0]
        assert len(job.steps) > 0
        step = job.steps[0]
        assert isinstance(step, Step)
        assert step.name == "Set up job"
        assert step.status == StepStatus.COMPLETED
        assert step.conclusion == Conclusion.SUCCESS

    def test_pending_step_has_no_timestamps(self, example_run: WorkflowRun) -> None:
        """Pending steps should have None for started_at and completed_at."""
        in_progress_job = next(
            j for j in example_run.jobs if j.status == JobStatus.IN_PROGRESS
        )
        pending_steps = [
            s for s in in_progress_job.steps if s.status == StepStatus.PENDING
        ]
        assert pending_steps, "Expected pending steps in in-progress job"
        step = pending_steps[0]
        assert step.started_at is None
        assert step.completed_at is None

    def test_run_is_not_done(self, example_run: WorkflowRun) -> None:
        """An in-progress run should not be considered done."""
        assert not example_run.is_done
        assert not example_run.is_successful

    def test_successful_job_is_marked(self, example_run: WorkflowRun) -> None:
        """Completed successful jobs should be marked as successful."""
        success_jobs = [j for j in example_run.jobs if j.is_done and j.is_successful]
        assert success_jobs


class TestJobNameMatching:
    """Tests for Job.matches_name()."""

    def test_exact_match(self, example_run: WorkflowRun) -> None:
        """Exact job name should match."""
        job = example_run.jobs[0]
        assert job.matches_name(re_escape(job.name))

    def test_pattern_match(self, example_run: WorkflowRun) -> None:
        """Wildcard pattern should match multiple jobs."""
        build_jobs = example_run.get_jobs_matching(r"Build charm .* / Build charm .*")
        assert len(build_jobs) >= 1
        for job in build_jobs:
            assert re.fullmatch(r"Build charm .* / Build charm .*", job.name)

    def test_no_match_returns_empty(self, example_run: WorkflowRun) -> None:
        """Pattern with no match should return empty list."""
        result = example_run.get_jobs_matching(r"Nonexistent Job.*")
        assert result == []


class TestStepRetrieval:
    """Tests for Job.get_step()."""

    def test_get_existing_step(self, example_run: WorkflowRun) -> None:
        """Should return the named step when it exists."""
        in_progress_job = next(
            j for j in example_run.jobs if j.status == JobStatus.IN_PROGRESS
        )
        step = in_progress_job.get_step("Pack charm")
        assert step is not None
        assert step.name == "Pack charm"

    def test_get_missing_step_returns_none(self, example_run: WorkflowRun) -> None:
        """Should return None when the step does not exist."""
        job = example_run.jobs[0]
        assert job.get_step("Nonexistent Step") is None


def re_escape(s: str) -> str:
    """Escape a string for use as a regex literal."""
    return re.escape(s)

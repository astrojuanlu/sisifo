"""Pydantic models for GitHub Actions API responses."""

from __future__ import annotations

import datetime as dt
import re
import typing as t
from enum import StrEnum

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_GO_ZERO_TIME = dt.datetime(1, 1, 1, tzinfo=dt.UTC)

_ZERO_STR = {"", "0001-01-01T00:00:00Z"}


def _nullable_datetime(v: object) -> object:
    """Convert Go zero-time and empty strings to None."""
    if isinstance(v, str) and v in _ZERO_STR:
        return None
    return v


NullableDatetime = t.Annotated[dt.datetime | None, BeforeValidator(_nullable_datetime)]


def _nullable_str(v: object) -> object:
    """Convert empty strings to None."""
    if isinstance(v, str) and v == "":
        return None
    return v


NullableStr = t.Annotated[str | None, BeforeValidator(_nullable_str)]


class RunStatus(StrEnum):
    """Status of a workflow run."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    REQUESTED = "requested"
    PENDING = "pending"


class JobStatus(StrEnum):
    """Status of a job within a workflow run."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    REQUESTED = "requested"
    PENDING = "pending"


class StepStatus(StrEnum):
    """Status of a step within a job."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PENDING = "pending"


class Conclusion(StrEnum):
    """Conclusion of a completed run, job, or step."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    NEUTRAL = "neutral"
    STALE = "stale"
    STARTUP_FAILURE = "startup_failure"


class Step(BaseModel):
    """A single step within a GitHub Actions job."""

    model_config = ConfigDict(frozen=True)

    name: str
    number: int
    status: StepStatus
    conclusion: NullableStr = None
    started_at: t.Annotated[NullableDatetime, Field(None, alias="startedAt")]
    completed_at: t.Annotated[NullableDatetime, Field(None, alias="completedAt")]

    @property
    def duration_seconds(self) -> float | None:
        """Return step duration in seconds, or None if not completed."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def is_done(self) -> bool:
        """Return True if the step has reached a terminal state."""
        return self.status == StepStatus.COMPLETED

    @property
    def is_successful(self) -> bool:
        """Return True if the step completed successfully."""
        return self.conclusion == Conclusion.SUCCESS

    def matches_name(self, pattern: str) -> bool:
        """Return True if the step name matches the given regex pattern."""
        return bool(re.fullmatch(pattern, self.name))


class Job(BaseModel):
    """A single job within a GitHub Actions workflow run."""

    model_config = ConfigDict(frozen=True)

    database_id: t.Annotated[int, Field(alias="databaseId")]
    name: str
    status: JobStatus
    conclusion: NullableStr = None
    started_at: t.Annotated[NullableDatetime, Field(None, alias="startedAt")]
    completed_at: t.Annotated[NullableDatetime, Field(None, alias="completedAt")]
    url: str
    steps: t.Annotated[list[Step], Field(default_factory=list)]

    @property
    def duration_seconds(self) -> float | None:
        """Return job duration in seconds, or None if not completed."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def elapsed_seconds(self) -> float | None:
        """Return elapsed time since job started, in seconds.

        For completed jobs this equals duration_seconds. For in-progress jobs
        this is the time elapsed so far (using started_at and now).
        """
        if self.started_at is None:
            return None
        if self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds()
        return (dt.datetime.now(tz=dt.UTC) - self.started_at).total_seconds()

    @property
    def is_done(self) -> bool:
        """Return True if the job has reached a terminal state."""
        return self.status == JobStatus.COMPLETED

    @property
    def is_successful(self) -> bool:
        """Return True if the job completed successfully."""
        return self.conclusion == Conclusion.SUCCESS

    def matches_name(self, pattern: str) -> bool:
        """Return True if the job name matches the given regex pattern."""
        return bool(re.fullmatch(pattern, self.name))

    def get_step(self, name: str) -> Step | None:
        """Return the step with the given name, or None if not found."""
        return next((s for s in self.steps if s.name == name), None)


class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run, including all its jobs and steps."""

    model_config = ConfigDict(frozen=True)

    database_id: t.Annotated[int, Field(alias="databaseId")]
    name: str
    workflow_name: t.Annotated[str, Field(alias="workflowName")]
    workflow_database_id: t.Annotated[int, Field(alias="workflowDatabaseId")]
    number: int
    attempt: int
    status: RunStatus
    conclusion: NullableStr = None
    head_branch: t.Annotated[str, Field(alias="headBranch")]
    head_sha: t.Annotated[str, Field(alias="headSha")]
    event: str
    display_title: t.Annotated[str, Field(alias="displayTitle")]
    created_at: t.Annotated[dt.datetime, Field(alias="createdAt")]
    started_at: t.Annotated[NullableDatetime, Field(None, alias="startedAt")]
    updated_at: t.Annotated[dt.datetime, Field(alias="updatedAt")]
    url: str
    jobs: t.Annotated[list[Job], Field(default_factory=list)]

    @property
    def is_done(self) -> bool:
        """Return True if the workflow run has reached a terminal state."""
        return self.status == RunStatus.COMPLETED

    @property
    def is_successful(self) -> bool:
        """Return True if the workflow run completed successfully."""
        return self.conclusion == Conclusion.SUCCESS

    def get_jobs_matching(self, pattern: str) -> list[Job]:
        """Return all jobs whose names match the given regex pattern."""
        return [job for job in self.jobs if job.matches_name(pattern)]

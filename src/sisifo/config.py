"""Configuration models and loader for Sísifo."""

from __future__ import annotations

import json
import re
from pathlib import Path

import json5  # type: ignore[import-untyped]
import pytimeparse  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator, model_validator


class JobSelector(BaseModel):
    """Selector for jobs within a workflow."""

    pattern: str
    """A regular expression matched against the full job name."""

    @field_validator("pattern")
    @classmethod
    def _valid_pattern(cls, v: str) -> str:
        """Validate that pattern compiles as a regex."""
        try:
            re.compile(v)
        except re.error as exc:
            msg = f"Invalid regex pattern {v!r}: {exc}"
            raise ValueError(msg) from exc
        return v


class RuleSelector(BaseModel):
    """Selector for the GitHub Actions entities a rule monitors."""

    workflow: str
    """Name of the workflow (e.g. 'Pull request')."""

    job: JobSelector
    """Selector for jobs within the workflow."""

    step: str | None = None
    """Optional: only monitor a specific step name within matching jobs."""


class RuleConditions(BaseModel):
    """Desired-state conditions for a rule."""

    max_duration: int | None = Field(None, alias="maxDuration")
    """Maximum allowed duration in seconds, parsed from strings like '60m'."""

    state: str | None = None
    """Desired conclusion; typically 'success'."""

    @field_validator("max_duration", mode="before")
    @classmethod
    def _parse_duration(cls, v: object) -> int | None:
        """Parse human-readable duration strings like '60m' or '30s'."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            seconds = pytimeparse.parse(v)
            if seconds is None:
                msg = f"Cannot parse duration {v!r}"
                raise ValueError(msg)
            return int(seconds)
        msg = f"Expected str or int for duration, got {type(v)}"
        raise TypeError(msg)


class RuleActions(BaseModel):
    """Actions to take when conditions are violated."""

    on_timeout: list[str] = Field(default_factory=list, alias="onTimeout")
    """Actions when maxDuration is exceeded. E.g. ['cancel', 'retry-failed']."""

    on_failure: list[str] = Field(default_factory=list, alias="onFailure")
    """Actions when jobs/steps finish with a failure conclusion."""

    @model_validator(mode="after")
    def _validate_actions(self) -> RuleActions:
        """Check that only known action strings are used."""
        known = {"cancel", "retry-failed"}
        for action in self.on_timeout + self.on_failure:
            if action not in known:
                msg = f"Unknown action {action!r}. Valid actions: {sorted(known)}"
                raise ValueError(msg)
        return self


class Rule(BaseModel):
    """A monitoring rule combining selector, conditions, and actions."""

    name: str
    selector: RuleSelector
    conditions: RuleConditions
    actions: RuleActions


class SisifoConfig(BaseModel):
    """Top-level Sísifo configuration."""

    rules: list[Rule] = Field(default_factory=list)


class SisifoMeta(BaseModel):
    """Metadata written by ``sisifo bootstrap``."""

    pr: int
    repository: str
    """Owner/repo string, e.g. 'canonical/mysql-operators'."""

    @property
    def owner(self) -> str:
        """Return the repository owner."""
        return self.repository.split("/")[0]

    @property
    def repo(self) -> str:
        """Return the repository name."""
        return self.repository.split("/")[1]


def load_config(path: str | Path = Path("sisifo.json5")) -> SisifoConfig:
    """Load and parse a ``sisifo.json5`` configuration file."""
    with open(path) as fh:
        raw = json5.load(fh)
    return SisifoConfig.model_validate(raw)


def load_meta(path: str | Path = Path(".sisifo.meta.json")) -> SisifoMeta:
    """Load and parse the ``.sisifo.meta.json`` metadata file."""
    with open(path) as fh:
        raw = json.load(fh)
    return SisifoMeta.model_validate(raw)

"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gh_models.actions import WorkflowRun

EXAMPLE_DIR = Path(__file__).parent / "example"


@pytest.fixture()
def example_run() -> WorkflowRun:
    """Load the example workflow run from example/gh_run_view_*.json."""
    raw = json.loads((EXAMPLE_DIR / "gh_run_view_23680020976.json").read_text())
    return WorkflowRun.model_validate(raw)

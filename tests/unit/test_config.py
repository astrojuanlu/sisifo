"""Unit tests for the sisifo.config module."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from sisifo.config import (
    JobSelector,
    Rule,
    RuleActions,
    RuleConditions,
    RuleSelector,
    SisifoConfig,
    SisifoMeta,
    load_config,
    load_meta,
)


@pytest.fixture
def sisifo_config():
    return Path(__file__).parent.parent / "sisifo.json5"


# ---------------------------------------------------------------------------
# JobSelector
# ---------------------------------------------------------------------------


class TestJobSelector:
    def test_valid_pattern(self) -> None:
        sel = JobSelector(pattern=r"Build charm .* / Build charm .*")
        assert sel.pattern == r"Build charm .* / Build charm .*"

    def test_simple_literal_pattern(self) -> None:
        sel = JobSelector(pattern="My Job")
        assert sel.pattern == "My Job"

    def test_invalid_regex_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid regex pattern"):
            JobSelector(pattern="[unclosed")

    def test_empty_pattern_is_valid(self) -> None:
        # An empty pattern is a valid regex that matches empty strings
        sel = JobSelector(pattern="")
        assert sel.pattern == ""


# ---------------------------------------------------------------------------
# RuleSelector
# ---------------------------------------------------------------------------


class TestRuleSelector:
    def test_minimal_selector_no_step(self) -> None:
        sel = RuleSelector(
            workflow="Pull request",
            job=JobSelector(pattern=r"Build.*"),
        )
        assert sel.workflow == "Pull request"
        assert sel.step is None

    def test_selector_with_step(self) -> None:
        sel = RuleSelector(
            workflow="Pull request",
            job=JobSelector(pattern=r"Build.*"),
            step="Pack charm",
        )
        assert sel.step == "Pack charm"

    def test_selector_from_dict(self) -> None:
        sel = RuleSelector.model_validate(
            {"workflow": "CI", "job": {"pattern": r"Test.*"}, "step": None}
        )
        assert sel.workflow == "CI"
        assert sel.step is None


# ---------------------------------------------------------------------------
# RuleConditions
# ---------------------------------------------------------------------------


class TestRuleConditions:
    def test_duration_minutes(self) -> None:
        cond = RuleConditions.model_validate({"maxDuration": "60m"})
        assert cond.max_duration == 3600

    def test_duration_seconds(self) -> None:
        cond = RuleConditions.model_validate({"maxDuration": "30s"})
        assert cond.max_duration == 30

    def test_duration_hours(self) -> None:
        cond = RuleConditions.model_validate({"maxDuration": "2h"})
        assert cond.max_duration == 7200

    def test_duration_mixed(self) -> None:
        cond = RuleConditions.model_validate({"maxDuration": "1h30m"})
        assert cond.max_duration == 5400

    def test_duration_integer_passthrough(self) -> None:
        cond = RuleConditions.model_validate({"maxDuration": 120})
        assert cond.max_duration == 120

    def test_duration_none(self) -> None:
        cond = RuleConditions.model_validate({})
        assert cond.max_duration is None

    def test_duration_unparseable_raises(self) -> None:
        with pytest.raises(Exception, match="Cannot parse duration"):
            RuleConditions.model_validate({"maxDuration": "not-a-duration"})

    def test_state_field(self) -> None:
        cond = RuleConditions.model_validate({"state": "success"})
        assert cond.state == "success"

    def test_state_defaults_to_none(self) -> None:
        cond = RuleConditions.model_validate({})
        assert cond.state is None


# ---------------------------------------------------------------------------
# RuleActions
# ---------------------------------------------------------------------------


class TestRuleActions:
    def test_valid_on_timeout(self) -> None:
        actions = RuleActions.model_validate(
            {"onTimeout": ["cancel", "retry-failed"], "onFailure": []}
        )
        assert actions.on_timeout == ["cancel", "retry-failed"]

    def test_valid_on_failure(self) -> None:
        actions = RuleActions.model_validate(
            {"onTimeout": [], "onFailure": ["retry-failed"]}
        )
        assert actions.on_failure == ["retry-failed"]

    def test_empty_actions(self) -> None:
        actions = RuleActions.model_validate({})
        assert actions.on_timeout == []
        assert actions.on_failure == []

    def test_unknown_on_timeout_action_raises(self) -> None:
        with pytest.raises(Exception, match="Unknown action 'blast-it'"):
            RuleActions.model_validate({"onTimeout": ["blast-it"]})

    def test_unknown_on_failure_action_raises(self) -> None:
        with pytest.raises(Exception, match="Unknown action 'nuke'"):
            RuleActions.model_validate({"onFailure": ["nuke"]})

    def test_cancel_only(self) -> None:
        actions = RuleActions.model_validate({"onTimeout": ["cancel"]})
        assert actions.on_timeout == ["cancel"]

    def test_retry_only(self) -> None:
        actions = RuleActions.model_validate({"onFailure": ["retry-failed"]})
        assert actions.on_failure == ["retry-failed"]


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class TestRule:
    def _minimal_rule_dict(self) -> dict:
        return {
            "name": "My rule",
            "selector": {
                "workflow": "Pull request",
                "job": {"pattern": r"Build.*"},
            },
            "conditions": {"maxDuration": "10m", "state": "success"},
            "actions": {"onTimeout": ["cancel"], "onFailure": ["retry-failed"]},
        }

    def test_full_rule(self) -> None:
        rule = Rule.model_validate(self._minimal_rule_dict())
        assert rule.name == "My rule"
        assert rule.selector.workflow == "Pull request"
        assert rule.conditions.max_duration == 600
        assert rule.actions.on_timeout == ["cancel"]

    def test_rule_with_step(self) -> None:
        d = self._minimal_rule_dict()
        d["selector"]["step"] = "Pack charm"
        rule = Rule.model_validate(d)
        assert rule.selector.step == "Pack charm"

    def test_rule_without_conditions(self) -> None:
        d = self._minimal_rule_dict()
        d["conditions"] = {}
        rule = Rule.model_validate(d)
        assert rule.conditions.max_duration is None
        assert rule.conditions.state is None


# ---------------------------------------------------------------------------
# SisifoConfig
# ---------------------------------------------------------------------------


class TestSisifoConfig:
    def test_empty_config(self) -> None:
        config = SisifoConfig.model_validate({"rules": []})
        assert config.rules == []

    def test_config_defaults_to_empty_rules(self) -> None:
        config = SisifoConfig.model_validate({})
        assert config.rules == []

    def test_config_with_two_rules(self) -> None:
        config = SisifoConfig.model_validate(
            {
                "rules": [
                    {
                        "name": "Rule A",
                        "selector": {
                            "workflow": "CI",
                            "job": {"pattern": "Job.*"},
                        },
                        "conditions": {},
                        "actions": {},
                    },
                    {
                        "name": "Rule B",
                        "selector": {
                            "workflow": "CI",
                            "job": {"pattern": "Other.*"},
                            "step": "Some step",
                        },
                        "conditions": {"maxDuration": "5m"},
                        "actions": {"onTimeout": ["cancel"]},
                    },
                ]
            }
        )
        assert len(config.rules) == 2
        assert config.rules[0].name == "Rule A"
        assert config.rules[1].selector.step == "Some step"


# ---------------------------------------------------------------------------
# SisifoMeta
# ---------------------------------------------------------------------------


class TestSisifoMeta:
    def test_owner_property(self) -> None:
        meta = SisifoMeta(pr=42, repository="canonical/mysql-operators")
        assert meta.owner == "canonical"

    def test_repo_property(self) -> None:
        meta = SisifoMeta(pr=42, repository="canonical/mysql-operators")
        assert meta.repo == "mysql-operators"

    def test_pr_field(self) -> None:
        meta = SisifoMeta(pr=185, repository="org/repo")
        assert meta.pr == 185

    def test_from_dict(self) -> None:
        meta = SisifoMeta.model_validate({"pr": 10, "repository": "acme/widget"})
        assert meta.owner == "acme"
        assert meta.repo == "widget"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_project_sisifo_json5(self, sisifo_config) -> None:
        config = load_config(sisifo_config)
        assert isinstance(config, SisifoConfig)
        assert len(config.rules) == 2

    def test_first_rule_name(self, sisifo_config) -> None:
        config = load_config(sisifo_config)
        assert config.rules[0].name == "Build charm jobs should complete in 60 minutes"

    def test_second_rule_has_step(self, sisifo_config) -> None:
        config = load_config(sisifo_config)
        assert config.rules[1].selector.step == "Pack charm"

    def test_durations_are_parsed(self, sisifo_config) -> None:
        config = load_config(sisifo_config)
        assert config.rules[0].conditions.max_duration == 3600  # 60m
        assert config.rules[1].conditions.max_duration == 3000  # 50m

    def test_actions_are_parsed(self, sisifo_config) -> None:
        config = load_config(sisifo_config)
        rule = config.rules[0]
        assert "cancel" in rule.actions.on_timeout
        assert "retry-failed" in rule.actions.on_timeout
        assert "retry-failed" in rule.actions.on_failure

    def test_loads_inline_json5_file(self, tmp_path: Path) -> None:
        """load_config parses JSON5 features like comments and trailing commas."""
        f = tmp_path / "sisifo.json5"
        f.write_text(
            textwrap.dedent("""\
                // Sísifo config
                {
                  rules: [
                    {
                      name: "Test rule",
                      selector: {
                        workflow: "CI",
                        job: { pattern: "Job.*", },  // trailing comma
                      },
                      conditions: { maxDuration: "5m", },
                      actions: { onTimeout: ["cancel"], },
                    },
                  ],
                }
            """)
        )
        config = load_config(f)
        assert len(config.rules) == 1
        assert config.rules[0].conditions.max_duration == 300

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json5")

    def test_empty_rules_list(self, tmp_path: Path) -> None:
        f = tmp_path / "sisifo.json5"
        f.write_text("{ rules: [] }")
        config = load_config(f)
        assert config.rules == []


# ---------------------------------------------------------------------------
# load_meta
# ---------------------------------------------------------------------------


class TestLoadMeta:
    def _write_meta(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / ".sisifo.meta.json"
        p.write_text(json.dumps(data))
        return p

    def test_loads_meta(self, tmp_path: Path) -> None:
        p = self._write_meta(
            tmp_path, {"pr": 185, "repository": "canonical/mysql-operators"}
        )
        meta = load_meta(p)
        assert meta.pr == 185
        assert meta.repository == "canonical/mysql-operators"

    def test_owner_and_repo_derived(self, tmp_path: Path) -> None:
        p = self._write_meta(tmp_path, {"pr": 1, "repository": "acme/widget"})
        meta = load_meta(p)
        assert meta.owner == "acme"
        assert meta.repo == "widget"

    def test_extra_fields_ignored(self, tmp_path: Path) -> None:
        p = self._write_meta(
            tmp_path,
            {
                "pr": 7,
                "repository": "org/repo",
                "lastUpdated": "2026-01-01T00:00:00Z",
                "discovered": {"workflows": []},
            },
        )
        meta = load_meta(p)
        assert meta.pr == 7

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_meta(tmp_path / ".sisifo.meta.json")

"""Reconciliation engine: compare actual workflow state against desired rules."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from gh_models.actions import Job, JobStatus, StepStatus, WorkflowRun
from whenever import Instant

from .config import Rule, SisifoConfig
from .decisions import Decision, Reconciliation

logger = structlog.get_logger()


@dataclass
class Reconciler:
    """Evaluate a set of rules against a workflow run and produce a decision."""

    rules: list[Rule]

    @classmethod
    def from_config(cls, config: SisifoConfig) -> Reconciler:
        return cls(config.rules)

    def reconcile(self, run: WorkflowRun) -> Reconciliation:
        """Evaluate all rules and return the highest-priority decision.

        Priority order: CANCEL_AND_RETRY > RETRY_FAILED_JOBS > WAIT > COMPLETE.
        """
        if not self.rules:
            return Reconciliation(Decision.COMPLETE, "No rules configured.")

        rule_results: list[Reconciliation] = []
        for rule in self.rules:
            if rule.selector.workflow != run.workflow_name:
                logger.debug(
                    "Rule skipped: workflow mismatch",
                    rule=rule.name,
                    expected=rule.selector.workflow,
                    actual=run.workflow_name,
                )
                continue
            result = self._evaluate_rule(rule, run)
            logger.debug(
                "Rule evaluated",
                rule=rule.name,
                decision=result.decision,
                rationale=result.rationale,
            )
            rule_results.append(result)

        if not rule_results:
            return Reconciliation(Decision.COMPLETE, "No rules matched this workflow.")

        return _merge_decisions(rule_results)

    def _evaluate_rule(self, rule: Rule, run: WorkflowRun) -> Reconciliation:
        """Evaluate a single rule against the run and return a decision."""
        matching_jobs = run.get_jobs_matching(rule.selector.job.pattern)
        if not matching_jobs:
            return Reconciliation(
                Decision.COMPLETE,
                f"Rule '{rule.name}': no jobs matched pattern"
                f" {rule.selector.job.pattern!r}.",
            )

        if rule.selector.step is not None:
            return self._evaluate_step_rule(rule, matching_jobs)
        return self._evaluate_job_rule(rule, matching_jobs)

    def _evaluate_job_rule(self, rule: Rule, jobs: list[Job]) -> Reconciliation:
        """Evaluate a job-level rule (no step selector)."""
        now = Instant.now()
        failed_ids: list[int] = []
        timed_out_ids: list[int] = []
        in_progress: list[Job] = []

        for job in jobs:
            if job.status == JobStatus.COMPLETED:
                if not job.is_successful:
                    failed_ids.append(job.database_id)
            else:
                in_progress.append(job)
                elapsed = _elapsed_seconds(job.started_at, now)
                max_dur = rule.conditions.max_duration
                if max_dur is not None and elapsed is not None and elapsed > max_dur:
                    timed_out_ids.append(job.database_id)

        if timed_out_ids and "cancel" in rule.actions.on_timeout:
            ids_str = ", ".join(str(i) for i in timed_out_ids)
            result = Reconciliation(
                Decision.CANCEL_AND_RETRY_FAILED,
                f"Rule '{rule.name}': jobs {ids_str} exceeded"
                f" max duration of {rule.conditions.max_duration}s.",
                affected_job_ids=timed_out_ids,
            )
        elif failed_ids and "retry-failed" in rule.actions.on_failure:
            ids_str = ", ".join(str(i) for i in failed_ids)
            result = Reconciliation(
                Decision.RETRY_FAILED,
                f"Rule '{rule.name}': jobs {ids_str} failed.",
                affected_job_ids=failed_ids,
            )
        elif in_progress:
            result = Reconciliation(
                Decision.WAIT,
                f"Rule '{rule.name}': {len(in_progress)} job(s) still in progress.",
            )
        elif failed_ids:
            ids_str = ", ".join(str(i) for i in failed_ids)
            result = Reconciliation(
                Decision.WAIT,
                f"Rule '{rule.name}': jobs {ids_str} failed"
                " but no retry action configured.",
            )
        else:
            result = Reconciliation(
                Decision.COMPLETE,
                f"Rule '{rule.name}': all {len(jobs)} job(s) completed successfully.",
            )

        return result

    def _evaluate_step_rule(self, rule: Rule, jobs: list[Job]) -> Reconciliation:
        """Evaluate a step-level rule (step selector present)."""
        assert rule.selector.step is not None  # noqa: S101
        step_name = rule.selector.step
        now = Instant.now()

        failed_job_ids: list[int] = []
        timed_out_job_ids: list[int] = []
        in_progress_count = 0
        missing_step_count = 0

        for job in jobs:
            step = job.get_step(step_name)
            if step is None:
                # Step might not have started yet if job is still early
                if not job.is_done:
                    in_progress_count += 1
                else:
                    missing_step_count += 1
                continue

            if step.status == StepStatus.COMPLETED:
                if not step.is_successful:
                    failed_job_ids.append(job.database_id)
            else:
                in_progress_count += 1
                elapsed = _elapsed_seconds(step.started_at, now)
                max_dur = rule.conditions.max_duration
                if max_dur is not None and elapsed is not None and elapsed > max_dur:
                    timed_out_job_ids.append(job.database_id)

        if timed_out_job_ids and "cancel" in rule.actions.on_timeout:
            ids_str = ", ".join(str(i) for i in timed_out_job_ids)
            result = Reconciliation(
                Decision.CANCEL_AND_RETRY_FAILED,
                f"Rule '{rule.name}': step '{step_name}' in jobs {ids_str}"
                f" exceeded max duration of {rule.conditions.max_duration}s.",
                affected_job_ids=timed_out_job_ids,
            )
        elif failed_job_ids and "retry-failed" in rule.actions.on_failure:
            ids_str = ", ".join(str(i) for i in failed_job_ids)
            result = Reconciliation(
                Decision.RETRY_FAILED,
                f"Rule '{rule.name}': step '{step_name}' failed in jobs {ids_str}.",
                affected_job_ids=failed_job_ids,
            )
        elif in_progress_count > 0:
            result = Reconciliation(
                Decision.WAIT,
                f"Rule '{rule.name}': step '{step_name}' still in progress"
                f" in {in_progress_count} job(s).",
            )
        elif failed_job_ids:
            ids_str = ", ".join(str(i) for i in failed_job_ids)
            result = Reconciliation(
                Decision.WAIT,
                f"Rule '{rule.name}': step '{step_name}' failed in jobs {ids_str}"
                " but no retry action configured.",
            )
        else:
            result = Reconciliation(
                Decision.COMPLETE,
                f"Rule '{rule.name}': step '{step_name}' completed successfully"
                f" in all {len(jobs)} matching job(s).",
            )

        return result


def _elapsed_seconds(
    started_at: Instant | None,
    now: Instant,
) -> float | None:
    """Return seconds elapsed since *started_at*, or None if not started."""
    if started_at is None:
        return None
    return (now - started_at).in_seconds()


def _merge_decisions(results: list[Reconciliation]) -> Reconciliation:
    """Merge per-rule decisions into a single overall decision.

    Priority: CANCEL_AND_RETRY > RETRY_FAILED_JOBS > WAIT > COMPLETE.
    """
    priority = {
        Decision.CANCEL_AND_RETRY_FAILED: 4,
        Decision.RETRY_FAILED: 3,
        Decision.WAIT: 2,
        Decision.COMPLETE: 1,
    }
    results.sort(key=lambda r: priority.get(r.decision, 0), reverse=True)
    top = results[0]

    all_job_ids: list[int] = []
    for r in results:
        all_job_ids.extend(r.affected_job_ids)

    rationales = "; ".join(r.rationale for r in results)
    return Reconciliation(top.decision, rationales, affected_job_ids=all_job_ids)

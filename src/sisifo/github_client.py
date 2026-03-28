"""GitHub API client using gidgethub."""

from __future__ import annotations

import typing as t

import gidgethub.httpx as gh_httpx
import httpx
import structlog
from gh_models.actions import WorkflowRun

logger = structlog.get_logger()

_PAGE_SIZE = 100


class GitHubClient:
    """Thin wrapper around gidgethub for GitHub Actions operations."""

    def __init__(self, token: str, requester: str = "sisifo") -> None:
        """Create a client authenticated with the given GitHub token."""
        self._token = token
        self._requester = requester

    async def get_workflow_runs_for_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        workflow_name: str | None = None,
    ) -> list[WorkflowRun]:
        """Return all workflow runs associated with a pull request.

        Finds the PR's head SHA, then lists all workflow runs for that commit.
        If *workflow_name* is provided, only runs for that workflow are returned.
        """
        logger.debug(
            "Fetching PR head SHA",
            owner=owner,
            repo=repo,
            pr_number=pr_number,
        )
        async with httpx.AsyncClient() as http:
            gh = gh_httpx.GitHubAPI(http, self._requester, oauth_token=self._token)

            pr_data: dict[str, t.Any] = await gh.getitem(
                f"/repos/{owner}/{repo}/pulls/{pr_number}"
            )
            head_sha: str = pr_data["head"]["sha"]
            logger.debug("Fetched PR head SHA", sha=head_sha)

            runs: list[WorkflowRun] = []
            page = 1
            logger.debug(
                "Fetching workflow runs",
                owner=owner,
                repo=repo,
                head_sha=head_sha,
                workflow_name=workflow_name,
            )
            while True:
                data: dict[str, t.Any] = await gh.getitem(
                    f"/repos/{owner}/{repo}/actions/runs",
                    url_vars={
                        "head_sha": head_sha,
                        "event": "pull_request",
                        "per_page": str(_PAGE_SIZE),
                        "page": str(page),
                    },
                )
                batch = data.get("workflow_runs", [])
                if not batch:
                    break
                logger.debug(
                    "Processing workflow runs batch",
                    page=page,
                    batch_size=len(batch),
                )
                for raw in batch:
                    run = await self._enrich_run(gh, owner, repo, raw)
                    if workflow_name is None or run.workflow_name == workflow_name:
                        runs.append(run)
                if len(batch) < _PAGE_SIZE:
                    break
                page += 1

            logger.debug(
                "Finished fetching workflow runs",
                total_runs=len(runs),
                workflow_name=workflow_name,
            )
            return runs

    async def _enrich_run(
        self,
        gh: gh_httpx.GitHubAPI,
        owner: str,
        repo: str,
        raw_run: dict[str, t.Any],
    ) -> WorkflowRun:
        """Fetch jobs for a run and return a complete WorkflowRun model."""
        run_id = raw_run["id"]
        logger.debug("Enriching run with jobs", run_id=run_id)
        jobs: list[dict[str, t.Any]] = []
        page = 1
        while True:
            data: dict[str, t.Any] = await gh.getitem(
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
                url_vars={"per_page": str(_PAGE_SIZE), "page": str(page)},
            )
            batch = data.get("jobs", [])
            if not batch:
                break
            jobs.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
            page += 1

        normalized = _normalize_run(raw_run, jobs)
        return WorkflowRun.model_validate(normalized)

    async def cancel_run(self, owner: str, repo: str, run_id: int) -> None:
        """Cancel an in-progress workflow run."""
        logger.info("Cancelling run", run_id=run_id, owner=owner, repo=repo)
        async with httpx.AsyncClient() as http:
            gh = gh_httpx.GitHubAPI(http, self._requester, oauth_token=self._token)
            await gh.post(
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
                data={},
            )

    async def rerun_failed_jobs(self, owner: str, repo: str, run_id: int) -> None:
        """Re-run only the failed jobs in a workflow run."""
        logger.info("Re-running failed jobs", run_id=run_id, owner=owner, repo=repo)
        async with httpx.AsyncClient() as http:
            gh = gh_httpx.GitHubAPI(http, self._requester, oauth_token=self._token)
            await gh.post(
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
                data={},
            )

    async def get_pr_head_sha(self, owner: str, repo: str, pr_number: int) -> str:
        """Return the head SHA for a pull request."""
        async with httpx.AsyncClient() as http:
            gh = gh_httpx.GitHubAPI(http, self._requester, oauth_token=self._token)
            pr_data: dict[str, t.Any] = await gh.getitem(
                f"/repos/{owner}/{repo}/pulls/{pr_number}"
            )
            return pr_data["head"]["sha"]  # type: ignore[no-any-return]

    async def discover_workflows_for_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> list[dict[str, t.Any]]:
        """Return summarised workflow info for bootstrap metadata."""
        runs = await self.get_workflow_runs_for_pr(owner, repo, pr_number)
        seen: dict[int, dict[str, t.Any]] = {}
        for run in runs:
            wf_id = run.workflow_database_id
            if wf_id not in seen:
                seen[wf_id] = {
                    "name": run.workflow_name,
                    "id": wf_id,
                    "jobs": [
                        {"name": job.name, "id": job.database_id} for job in run.jobs
                    ],
                }
        return list(seen.values())


def _normalize_run(
    raw: dict[str, t.Any],
    jobs: list[dict[str, t.Any]],
) -> dict[str, t.Any]:
    """Translate GitHub REST API field names to those expected by WorkflowRun."""
    return {
        "databaseId": raw["id"],
        "name": raw.get("name", raw.get("display_title", "")),
        "workflowName": raw.get("name", ""),
        "workflowDatabaseId": raw.get("workflow_id", 0),
        "number": raw.get("run_number", 0),
        "attempt": raw.get("run_attempt", 1),
        "status": raw.get("status", ""),
        "conclusion": raw.get("conclusion") or "",
        "headBranch": raw.get("head_branch", ""),
        "headSha": raw.get("head_sha", ""),
        "event": raw.get("event", ""),
        "displayTitle": raw.get("display_title", ""),
        "createdAt": raw.get("created_at", ""),
        "startedAt": raw.get("run_started_at") or "",
        "updatedAt": raw.get("updated_at", ""),
        "url": raw.get("html_url", ""),
        "jobs": [_normalize_job(j) for j in jobs],
    }


def _normalize_job(raw: dict[str, t.Any]) -> dict[str, t.Any]:
    """Translate GitHub REST API job fields to those expected by Job."""
    return {
        "databaseId": raw["id"],
        "name": raw.get("name", ""),
        "status": raw.get("status", ""),
        "conclusion": raw.get("conclusion") or "",
        "startedAt": raw.get("started_at") or "",
        "completedAt": raw.get("completed_at") or "",
        "url": raw.get("html_url", ""),
        "steps": [_normalize_step(s) for s in raw.get("steps", [])],
    }


def _normalize_step(raw: dict[str, t.Any]) -> dict[str, t.Any]:
    """Translate GitHub REST API step fields to those expected by Step."""
    return {
        "name": raw.get("name", ""),
        "number": raw.get("number", 0),
        "status": raw.get("status", ""),
        "conclusion": raw.get("conclusion") or "",
        "startedAt": raw.get("started_at") or "",
        "completedAt": raw.get("completed_at") or "",
    }

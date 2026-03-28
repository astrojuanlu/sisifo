"""CLI for Sísifo."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import structlog

from .config import SisifoMeta, load_config
from .decisions import Decision
from .github_client import GitHubClient
from .reconciler import Reconciler

logger = structlog.get_logger()

_EMOJI_WAIT = "⌛"
_EMOJI_ACTION = "🪨"
_EMOJI_DONE = "🏆"


def _get_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "Error: GitHub token not found. Set GH_TOKEN or GITHUB_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def _load_meta_or_exit(meta_path: Path) -> SisifoMeta:
    if not meta_path.exists():
        print(
            f"Error: metadata file {meta_path} not found.\n"
            "Run 'sisifo bootstrap --pr <number>' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return SisifoMeta.model_validate(json.loads(meta_path.read_text()))


async def _cmd_check(
    pr: int,
    config_path: Path,
    meta_path: Path,
    fmt: str,
) -> None:
    """Check whether the PR's workflows satisfy all configured rules."""
    logger.info("Starting check command", pr=pr, config=str(config_path))

    meta = _load_meta_or_exit(meta_path)
    logger.debug("Loaded metadata", repository=meta.repository, pr=meta.pr)

    config = load_config(config_path)
    logger.debug("Loaded config", rules_count=len(config.rules))

    token = _get_token()
    logger.debug("GitHub token obtained")

    client = GitHubClient(token)
    reconciler = Reconciler.from_config(config)

    # Collect unique workflow names from rules
    workflow_names = {rule.selector.workflow for rule in config.rules}
    logger.info("Will check workflows", workflows=list(workflow_names))

    overall_decision = Decision.COMPLETE
    messages: list[str] = []

    for workflow_name in workflow_names:
        logger.info(
            "Fetching workflow runs from GitHub",
            workflow=workflow_name,
            owner=meta.owner,
            repo=meta.repo,
            pr=pr,
        )
        runs = await client.get_workflow_runs_for_pr(
            meta.owner, meta.repo, pr, workflow_name=workflow_name
        )
        if not runs:
            logger.warning("No runs found for workflow", workflow=workflow_name)
            messages.append(f"No runs found for workflow '{workflow_name}'.")
            overall_decision = Decision.WAIT
            continue

        # Use the most recent run (first in list from GitHub API)
        run = runs[0]
        logger.debug(
            "Evaluating most recent run",
            workflow=workflow_name,
            run_id=run.database_id,
            status=run.status,
        )
        result = reconciler.reconcile(run)
        messages.append(result.rationale)
        if result.decision != Decision.COMPLETE:
            overall_decision = result.decision

    success = overall_decision == Decision.COMPLETE
    message = (
        f"{_EMOJI_DONE} Workflows achieved desired state, well done!"
        if success
        else f"{_EMOJI_WAIT} Workflows not in desired state yet"
    )

    if fmt == "json":
        print(
            json.dumps(
                {"message": message, "success": success, "details": messages},
                indent=4,
            )
        )
    else:
        print(message)
        for m in messages:
            print(f"  {m}")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the Sísifo CLI."""
    parser = argparse.ArgumentParser(
        prog="sisifo",
        description="Monitor and auto-retry flaky GitHub Actions pipelines.",
    )
    parser.add_argument(
        "--config",
        default="sisifo.json5",
        metavar="PATH",
        help="Path to the sisifo.json5 config file (default: sisifo.json5).",
    )
    parser.add_argument(
        "--meta",
        default=".sisifo.meta.json",
        metavar="PATH",
        help="Path to the .sisifo.meta.json metadata file.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # check
    check_p = sub.add_parser("check", help="Check if workflows are in desired state.")
    check_p.add_argument("--pr", required=True, type=int, metavar="NUMBER")
    check_p.add_argument(
        "--format",
        dest="fmt",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )

    return parser


def run_cli(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, args.log_level)
        )
    )

    config_path = Path(args.config)
    meta_path = Path(args.meta)

    if args.command == "check":
        asyncio.run(_cmd_check(args.pr, config_path, meta_path, args.fmt))
    else:
        parser.print_help()
        sys.exit(1)

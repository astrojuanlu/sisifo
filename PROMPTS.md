# Prompts

## 2026-03-28

Look at the README of this project. I want to complete how the config file looks like.

You have a real-world example in `example/`. You can see the output of these commands:

```
gh pr checks 185 --json bucket,completedAt,description,event,link,name,startedAt,state,workflow > gh_pr_checks_185.json
gh workflow view "Pull request" > gh_workflow_view_pull_request.txt
gh run view 23680020976 --json attempt,conclusion,createdAt,databaseId,displayTitle,event,headBranch,headSha,jobs,name,number,startedAt,status,updatedAt,url,workflowDatabaseId,workflowName > gh_run_view_23680020976.json
gh run view --job 68996247327 > gh_run_view_job_68996247327.txt
```

You can run those commands, or similar, yourself if you need.

Now, I want my `sisifo.json5` config to express that

- The "Pack charm" step of the "Build charm" jobs of the "Pull request" workflow should finish successfully under 50 minutes
- The "Build charm" jobs of the "Pull request" workflow should finish successfully under 60 minutes

Note that this config should be amenable enough to be written by a human, but it is okay if it's a bit verbose because that's what the `sisifo bootstrap` command will do. Also, assume that, if a workflow or job or step is in the config but has no conditions attached, nothing should be done or checked. That also makes it easy for `sisifo bootstrap` to create something that works, yet checks nothing.

Write 3 different ways of configuring this to 3 different files, so I can pick the one that I like the most.

---

I love option 3. Tweaks:
- The "metadata" shouldn't be in the config file. Let's save it to `.sisifo.meta.json` (not JSON5 this time)
- I like the "discovered" idea of option 2, let's include it in the metadata.

Create the actual file `sisifo.json5` and adapt the README accordingly.

---

I want to create a system that can monitor my GitHub Actions and retry them if they don't achieve the desired state.

Look at the README and `sisifo.json5`. That's how it should work.

As you know, a pull request might trigger different GitHub workflows. I want to define some sort of state reconciliation loop, so that I can define a subset of the jobs and steps triggered by a pull request, with desired properties (in particular "finished successfully under 30 minutes") and, if those properties aren't achieved, it cancels the run (if necessary) and restarts the failed jobs.

For now, ignore `sisifo bootstrap`, assume the config is written by hand. Focus on `sisifo check`, we will take care of `sisifo fix` later.

I think I will need at least a few subsystems:
- A sans-io system that defines some GitHub Actions worflow, job, run, step with Pydantic models, with desired properties on top
- A system that pulls information from the GitHub API and builds those models
- A system that compares the desired properties with the actual properties and emits a verdict.

Prepare a plan for the implementation. If you see some subsystem missing, add it. Follow domain-driven design techniques, but keep it simple. Craft good abstractions, but don't go overboard. Assume modern Python (I already added some scaffolding).

Some notes:
- I want the Pydantic models for the GitHub API to be their own package, because I expect this to be fully reusable. I already created a `packages/gh-models` workspace member with uv.
- I don't want you to reinvent a GitHub API client. I added `gidgethub` as a dependency for that, you can read more at https://github.com/gidgethub/gidgethub

Include tests in the plan, as well as checks for `ruff format`, `ruff check`, `ty check` pass. You can use `uv run ruff format`, `uv run ...` for that. I added the necessary dev dependencies already.

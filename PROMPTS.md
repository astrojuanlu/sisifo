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

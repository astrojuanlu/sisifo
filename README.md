# Sísifo

> _You have already grasped that Sisyphus is the absurd hero.
> He is, as much through his passions as through his torture.
> His scorn of the gods, his hatred of death, and his passion for life
> won him that unspeakable penalty in which the whole being is exerted
> toward accomplishing nothing._
>
> —Albert Camus, "The Myth of Sisyphus"

Sísifo is a system to monitor and rerun your flaky GitHub Actions pipelines.

## Usage

> [!WARNING]
> The explanation below is an aspiration, not the current reality of the repository.
> Not all the commands below have been implemented yet. Use at your own risk.

(Optional) First, bootstrap the Sísifo configuration from an existing GitHub pull request.
This will scan your GitHub workflows and create a draft `sisifo.json5` config file
and a `.sisifo.meta.json` metadata file:

```bash
$ cd ~/your-project
$ export GH_TOKEN=...
$ sisifo bootstrap --pr 185
$ cat sisifo.json5
{
  rules: []
}
$ head .sisifo.meta.json
{
  "pr": 185,
  "repository": "canonical/mysql-operators",
  "lastUpdated": "2026-03-28T10:00:00Z",
  "discovered": {
    "workflows": [
      {
        "name": "Pull request",
        "id": 225616685,
        "jobs": [
```

The `.sisifo.meta.json` file contains discovered workflows and jobs for reference,
but you only need to edit `sisifo.json5`.

Next, adapt the `sisifo.json5` config. There are several conditions you can specify:
- "This check should be successful under N minutes, otherwise cancel (if not finished yet) and retry failed jobs"
- "This array should have 95 % of jobs passing under N minutes, otherwise cancel (if not finished yet) and retry failed jobs"

For example, this is how a real-world `sisifo.json5` configuration looks like:

```json5
{
  rules: [
    {
      name: "Build charm jobs should complete in 60 minutes",
      selector: {
        workflow: "Pull request",
        job: {
          pattern: "Build charm .* / Build charm .*",
        },
      },
      conditions: {
        maxDuration: "60m",
        state: "success",
      },
      actions: {
        onTimeout: ["cancel", "retry-failed"],
        onFailure: ["retry-failed"],
      },
    },
    {
      name: "Pack charm step should complete in 50 minutes",
      selector: {
        workflow: "Pull request",
        job: {
          pattern: "Build charm .* / Build charm .*",
        },
        step: "Pack charm",
      },
      conditions: {
        maxDuration: "50m",
        state: "success",
      },
      actions: {
        onTimeout: ["cancel", "retry-failed"],
        onFailure: ["retry-failed"],
      },
    },
  ],
}
```

To test that everything works, trigger `sisifo check` just once:

```bash
$ sisifo check --pr 185
...
⌛ Workflows not in desired state yet
$ sisifo check --pr 185 --format json
{
    ...
    "message": "⌛ Workflows not in desired state yet",
    "success": false
}
```

Finally, to trigger the actions defined in your config, run `sisifo fix`:

```
$ sisifo fix --pr 185
⌛ Workflows not in desired state yet
🪨 Triggering actions
- Cancelled job 68992754143
```

At some point you will get a successful result:

```
$ sisifo fix --pr 185
🏆 Worfklows achieved desired state, well done!
```

Use any monitoring tool of your liking to run this in a loop. For example:

```
$ watch -n600 sisifo fix --pr 185
...
```

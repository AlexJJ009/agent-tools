# ci-watch

`ci-watch` waits for the GitHub checks on one commit and exits with a verdict. An agent starts it in the
background after pushing a PR; the harness's completion notification wakes the session, so nobody polls.

```bash
ci-watch <PR number | --branch B | --sha S> [--repo OWNER/NAME] [--timeout MIN] [--grace-seconds SEC]
```

The installer links it to `~/.local/bin/ci-watch` next to `agent-wt` (`--no-agent-wt` skips both). It needs
`gh` (authenticated) and coreutils `timeout`.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Every check passed. | Nothing. |
| 1 | A check failed. Output: failed check names, run URLs, and the last 80 lines of `gh run view --log-failed` per failed job. Checks outside GitHub Actions get only name and link. | Fix the code from the printed failure. |
| 2 | No check appeared within the grace period (default 120 s). This is not a pass. | Find out whether the workflow should have run: trigger, path filters, workflow file on the base branch. |
| 3 | The overall timeout (default 60 min) expired. | Look at the run in the browser; it may be queued or stuck. |
| 4 | `ci-watch` or `gh` failed (authentication, network, unexpected output). No verdict about the code. | Read stderr. |

## Behaviour

- Waiting uses `gh pr checks --watch` (PR mode) or `gh run watch` (branch or sha without a PR). The only
  hand-written wait is the grace period before the first check shows up, probed every 10 s.
- `--branch` and `--sha` resolve to the PR whose head is that commit; without one, `ci-watch` watches the
  workflow runs for the commit, including runs that register while another is being watched.
- Output is bounded: no full logs.

## Agent usage

After `gh pr create` or a push to an open PR, start `ci-watch <PR> --repo OWNER/NAME` with `run_in_background`
and continue other work. Act on the notification: exit 1 output is the input for the fix; exit 2 means the
workflow did not run, which is a finding, not a green result.

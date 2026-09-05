# Isolation Policy

## Decision Matrix

| Situation | Mode | Reason |
|---|---|---|
| One task, clean checkout, no protected running process | branch | No second working directory is needed |
| Dirty checkout and a different task must start | worktree | Preserve the current index and files |
| Two agents or developers use different branches concurrently | worktree | Each task needs its own working directory |
| Long test, service, build, or training run must keep its checkout | worktree | `git switch` would change files under the process |
| Local PR review or urgent hotfix during active work | worktree | Keep both candidates available |
| Different trusted users share one Unix account and Git repository | worktree | Directory isolation helps, but is not a security boundary |
| Untrusted users or different Unix ownership domains | separate clone | Worktrees share Git metadata, refs, config, and hooks |

## Mental Model

A branch is a movable ref. It does not create another filesystem workspace.
A linked worktree adds a working directory with its own `HEAD` and index while
sharing the repository's object database and most refs/configuration.

Use worktrees when changing the current checkout would destroy or disturb useful
state. Do not use them as a ritual for every feature branch.

## Default Layout

Unless `--root` or `AGENT_WT_ROOT` overrides it, use:

```text
<repo-parent>/_worktrees/<repo>/<branch-slug>
<repo-parent>/_artifacts/<repo>/<branch-slug>
<repo-parent>/_cache/<tool>
```

This layout stays outside the repository, normally remains on the same mounted
filesystem, and groups managed workspaces without making recursive project tools
scan sibling worktrees.

Use a data-volume override on servers whose repository lives on a constrained
root filesystem. Reject low-space creation instead of silently falling back to
`/tmp`.

## Safety Boundary

The CLI does not provide:

- Unix permission or secret isolation;
- container or process isolation;
- automatic cleanup;
- protection from shared Git ref/config mutations;
- proof that two dependency trees are byte-identical.

Use separate clones for untrusted users, containers for runtime isolation, and
lockfile-aware package managers for dependency reproducibility.

---
name: manage-worktrees
description: Decide whether a coding task should use the current checkout, a branch, a managed Git worktree, or a separate clone; then inspect, create, list, and diagnose agent-safe server development workspaces with consistent paths, cache plans, artifact roots, and registry records. Use when Codex or another coding agent is about to start isolated or parallel repository work, mentions Git worktrees, needs a hotfix/review workspace, shares a development server, or needs to audit whether an existing worktree follows dependency and artifact hygiene.
---

# Manage Worktrees

Use the bundled CLI for deterministic inspection and creation. Keep judgment in
the agent and mutations in the CLI.

## Workflow

1. Prefer the installed launcher:

   ```bash
   command -v agent-wt
   ```

   If it is absent, resolve this `SKILL.md` from the active skill catalog and
   invoke its sibling `scripts/agent_wt.py` with Python 3.

2. Run `agent-wt inspect --json` before choosing an isolation mode.
3. Read [policies.md](references/policies.md), classify the task, and run
   `agent-wt decide` with the applicable intent flags.
4. If the result is `branch`, use `git switch -c <branch> <base>` in the current
   clean checkout. Do not create a worktree merely because a branch is new.
5. If the result is `separate-clone`, stop. A worktree is not a security or
   permission boundary between untrusted Unix users.
6. If the result is `worktree`, preview the operation:

   ```bash
   agent-wt create <branch> --base <ref> --task <task-id> --dry-run --json
   ```

   Review the selected path, filesystem, free-space gate, detected adapters,
   setup plan, and artifact root. Then rerun without `--dry-run`.
7. Do not pass `--setup` until the repository and lockfile are trusted. The flag
   may execute package lifecycle scripts. Without it, `create` only reports the
   reproducible setup command.
8. Run `agent-wt doctor <created-path> --json`. Treat errors as blocking. Explain
   warnings before development starts.

## Non-Negotiable Rules

- Never copy a repository with `cp -a` or `rsync` to simulate a worktree.
- Never place a managed worktree inside the repository it checks out.
- Never default to `/tmp` for persistent development work.
- Never symlink an entire mutable `node_modules`, `.venv`, or Conda environment
  merely to save space.
- Share content-addressed package caches; isolate branch-writable state.
- Keep logs, validation output, W&B runs, checkpoints, and generated datasets
  outside the source checkout. Read [adapters.md](references/adapters.md) when
  the project contains Node, Python, Conda, Docker, Hugging Face, or ML assets.
- Do not use worktrees as multi-user security isolation. Use separate clones and
  Unix ownership when users are not mutually trusted.
- Do not remove, prune, merge, push, or delete branches with this skill. Those
  lifecycle operations are intentionally outside the current CLI.

## Output Contract

Prefer `--json` when another agent consumes the output. Preserve and report:

- recommendation and reasons;
- repository root, common Git directory, base SHA, branch, and worktree path;
- project adapters and lockfiles;
- cache and artifact paths;
- registry status;
- doctor errors and warnings.

Do not claim dependency reuse merely because a cache path exists. `doctor`
reports configuration evidence, not byte-level deduplication.

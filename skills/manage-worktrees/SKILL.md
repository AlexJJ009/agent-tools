---
name: manage-worktrees
description: Decide whether a coding task should use the current checkout, a branch, or a managed Git worktree; return unsupported guidance for permission boundaries; then inspect, create, list, and diagnose agent-safe workspaces with consistent paths, cache plans, artifact roots, and registry records. Use when Codex is about to start isolated or parallel repository work, mentions Git worktrees, needs a hotfix/review workspace, or needs to audit dependency and artifact hygiene.
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
   Ask only when a missing fact would change the recommendation, base, branch,
   or target path. Do not require confirmation for a clear request.
4. If the result is `branch`, use `git switch -c <branch> <base>` in the current
   clean checkout. Do not create a worktree merely because a branch is new.
5. If the result is `unsupported`, stop and relay its separate-clone guidance.
   v1 does not create or migrate a clone, and a worktree is not a security or
   permission boundary between untrusted Unix users.
6. If the result is `worktree`, preview the operation:

   ```bash
   agent-wt create <branch> --base <ref> --task <task-id> --dry-run --json
   ```

   Review the selected path, filesystem, free-space gate, detected adapters,
   dependency guidance, and artifact root. Then rerun without `--dry-run`.
7. Never execute dependency installation through this workflow. v1 reports
   reproducible commands and cache guidance only.
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
- When `agent-wt` is available, never hand-build a worktree with ad hoc Git or
  filesystem commands.

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

Verified harness support is Codex only. Claude Code and other Agent Skills
harnesses are portability targets until their own installation and execution
evidence exists.

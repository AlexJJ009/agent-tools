# Agent Workflow Merge Review R1

Reviewed SHA: `df500bd4b4af9cb089c9d202728b305949aeef91`

Base reviewed against: `60d1721`

Branch: `codex/agent-workflow-suite`

Reviewer model/effort: Codex independent review agent; explicit model override not visible in-session, review performed at normal deep code-review effort.

## Verdict

No blocking findings for merging the reviewed Agent Workflow Suite branch into `main`, provided the planned PR required check completes on the same reviewed SHA and merge remains under human authority.

The branch-name versus commit-SHA behavior is intentional and safe for the stated deployment flow:

- Installed workflow sources are copied from the checkout that runs `scripts/install_agent_workflow.py`; installation is not bound to a branch name or a fixed commit.
- Formal-run task records bind approval to the current repository commit, command digest, config digest, agent evidence objects, and required human review.
- Renaming or deleting a branch while staying at the same commit preserves the authorized target.
- Creating a merge commit or squash commit changes the candidate SHA and correctly invalidates stale approval until fresh checks and fresh required human feedback are recorded.

## Findings

No blocking findings.

Non-blocking notes:

- `agent-workflow gate` is a voluntary local gate. It never launches the formal command itself and depends on the caller honoring a nonzero exit before protected work.
- The full GitHub required CI result was still running when this verdict was written. Merge should wait for the required `linear-workflow-runtime` PR check on PR #33 for `df500bd4b4af9cb089c9d202728b305949aeef91`; do not bypass protected checks.

## Evidence Reviewed

- Runtime binding path:
  - `agent_workflow/runtime.py:198` computes the formal target from current `HEAD`, command files, command digest, config digest, checked item digests, policy, class, and mode.
  - `agent_workflow/runtime.py:303` records the current target during `check` and invalidates existing human approval if candidate, command, or config digests changed.
  - `agent_workflow/runtime.py:382` rejects approval for the wrong candidate SHA.
  - `agent_workflow/runtime.py:430` through `agent_workflow/runtime.py:457` rejects stale target state and missing or stale human confirmation.
  - `agent_workflow/runtime.py:463` records that `gate` does not execute the protected command.
- CLI path:
  - `agent_workflow/cli.py:54` calls `runtime.gate`; no command execution path exists after a gate pass.
- Documentation:
  - `docs/AGENT_WORKFLOW.md:31` through `docs/AGENT_WORKFLOW.md:35` documents that deployment should use `main`, install is not branch-bound, and task approvals are commit-bound.
  - `docs/AGENT_WORKFLOW.md:56` through `docs/AGENT_WORKFLOW.md:62` documents the boundaries and formal-run binding.
  - `docs/AGENT_WORKFLOW.md:79` documents that projects must call the gate immediately before protected action and honor nonzero exits.
- Installer path:
  - `scripts/install_agent_workflow.py:18` resolves the repository root from the installer file path.
  - `scripts/install_agent_workflow.py:61` through `scripts/install_agent_workflow.py:75` runs `codex_target_guard.py` before writes.
  - `scripts/install_agent_workflow.py:103` through `scripts/install_agent_workflow.py:112` validates tracked skill and runtime sources.
  - `scripts/install_agent_workflow.py:189` through `scripts/install_agent_workflow.py:193` copies runtime files into the managed install.
  - `scripts/install_agent_workflow.py:242` through `scripts/install_agent_workflow.py:257` preflights staged runtime before publish.
- Regression tests:
  - `tests/test_agent_workflow.py:99` through `tests/test_agent_workflow.py:106` covers branch switch and deletion at the same SHA preserving the authorized target.
  - `tests/test_agent_workflow.py:108` through `tests/test_agent_workflow.py:125` covers a no-ff merge commit changing the candidate SHA, rejecting stale approval, rejecting fresh agent evidence without fresh human feedback, and passing after explicit fresh simulated feedback.
  - `tests/test_agent_workflow.py:315` through `tests/test_agent_workflow.py:318` covers wrong candidate SHA rejection.
  - `tests/test_agent_workflow.py:329` through `tests/test_agent_workflow.py:332` covers command change invalidation.
  - `tests/test_agent_workflow.py:334` through `tests/test_agent_workflow.py:340` covers changed relevant code invalidating checked evidence and human confirmation.
  - `tests/test_agent_workflow_portability.py:30` through `tests/test_agent_workflow_portability.py:77` covers tracked-source export, isolated HOME install, source relocation after install, launcher operation, record init/check, and expected negative gate.

## Validation

- `python3 -m unittest tests.test_agent_workflow tests.test_install_agent_workflow tests.test_agent_workflow_portability`
  - Result: `Ran 48 tests in 19.097s` / `OK`
- `.tmp/workflow-merge-repository-tests.log`
  - Result: `Ran 133 tests in 23.140s` / `OK`
  - The visible `CODEX_TARGET_GUARD=RED` lines are expected negative-control output inside passing tests.

## Merge Recommendation

Proceed with PR #33 after the required GitHub check completes on `df500bd4b4af9cb089c9d202728b305949aeef91`. Use the normal protected merge path; do not use an admin bypass.

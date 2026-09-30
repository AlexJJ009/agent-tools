# Scope Installed Workflows and Retire Unused Components

Date: 2026-09-30

Status: Accepted

## Context and Problem Statement

Duplicate Skill locations, broad legacy checklist instructions and automatic
maintenance during installation could reintroduce unwanted state or interfere
with ordinary work. Reinstallation also accumulated verified old package copies.
The user selected one Codex worktree Skill location, retired Experiment Registry
and the current context-sync schedule, and authorized installation-backup cleanup.

## Considered Options

- Keep broad installation defaults and repeatedly clean their output.
- Remove every legacy runtime and all automation.
- Narrow discovery and installation, preserve applicable legacy controls, and
  retire verified installation copies after successful publication.

## Decision Outcome

Use `.codex/skills/manage-worktrees` as the single Codex entry, migrating verified
`.agents` copies. Keep Context Sync callable; cron and provider-history migration
require explicit installation options. Retire Experiment Registry source and
installation wiring. Windows patch tooling is not a native Linux default;
WSL remains an applicable Windows maintenance host.

Current task state belongs in Task Runtime. Review and infrastructure Skills
consume the selected task interface without forcing a second legacy checklist.
Existing formal-run contracts retain their explicitly selected controls.
Upgrading the runtime does not retire live task bindings.

Unchanged package reinstalls keep existing files. Successful upgrades retire only
this installation's verified old package copies after readback; changed or
unrecognized copies remain visible for review. Publication failures still roll
back. This policy does not delete task data or unrelated application backups.

Work Report retains manual reporting and applicable existing automation. New
scheduling uses the selected lightweight timer; legacy cron is not a fallback
for new tasks. Structured response annotations are inspected through the user's
comments, while the complete original input remains available to the intent Judge.

### Consequences

- Ordinary installation has fewer side effects and does not continually grow
  verified package backups.
- Conflicting Skill copies and modified installation backups require specific
  resolution rather than silent replacement or deletion.
- Existing reporting obligations and legacy contracts still require explicit
  review before retirement; this decision does not cancel them.

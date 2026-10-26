# System Documentation

Use the guides below for implemented behavior. Repository code and its current
usage/interface documentation describe the system; task PRDs, checklists and
private reports describe bounded development work and are not deployment proof.

- [Project evaluation skills](PROJECT_EVAL_SKILLS.md): project-local build-eval and hillclimb using Codex subscription execution.
- [Learning and writing skills](LEARNING_WORKFLOW.md): the plain skills that remain, their ownership and installation.
- [Architecture decisions](decisions/README.md): adopted choices and their reasons.
- [Installation](INSTALLATION.md): general installers, target guards and machine defaults.
- [Context synchronization](CONTEXT_SYNC.md): bridge configuration, commands, conflicts and cron.
- [CLI server bootstrap](CLI_SERVER_BOOTSTRAP.md): server setup.
- [Claude Code adapter](CLAUDE_CODE_ADAPTER.md): context view and skill links on Linux/WSL (no hooks).
- [Repository overview](../README.md): other maintained tools and platform guides.

## Platform and operation guides

- [AutoDL bootstrap](AUTODL_AI_TOOLS_BOOTSTRAP.md): container/server tools and proxy inputs.
- [Codex defaults](CODEX_AUTOREVIEW_DEFAULT.md): approval posture, streams and configuration.
- [WSL2 proxy](CODEX_WSL2_PROXY.md): host-specific Windows proxy access.
- [Remote control](CODEX_REMOTE_CONTROL.md): standalone CLI and app-server setup.
- [Browser tools](CODEX_PLAYWRIGHT_TOOLS.md): machine-local Playwright/Chromium setup.
- [Managed worktrees](GIT_WORKTREE_AND_AGENT_WT_GUIDE.md): admission, layout and audit.
- [ci-watch](CI_WATCH.md): wait for a PR's GitHub checks in the background; exit codes.

## Documentation Responsibilities

The two README files serve different entry points; neither is a second progress
register. The [repository README](../README.md) introduces the tools, file map
and setup entry points. Detailed context-sync usage belongs in [its component guide](CONTEXT_SYNC.md). This README is the navigation index for
current component guides and architectural decisions; it does not repeat their
commands, behavior descriptions or decision status.

| Material | Maintained responsibility | Update when |
|---|---|---|
| Root `README.md` | Repository purpose, component inventory and setup entry points | Repository entry points or that component's usage change |
| `docs/README.md` | Links to current system guides and decisions | A guide is added, moved, replaced, or its responsibility changes |
| Component guides | Implemented usage, interfaces, operational steps and limitations | The corresponding behavior changes |
| `docs/decisions/NNNN-*.md` | Significant adopted choices, context, reasons and consequences | A material decision is adopted or superseded |
| Ignored `docs/_local/` | Task-specific requirements, one execution checklist, recovery points and private evidence | That task progresses or its agreement changes |

Keep each detailed fact in one maintained source and link to it from the entry
points. A component guide's ordinary edit does not require rewriting both
README files. Keep release/deployment claims tied to actual verification;
source implementation and historical acceptance do not establish installation
on another host. This division does not create a new document pack or ADR for every
documentation edit.

Private development material belongs in ignored `docs/_local/`,
created only when needed: `tasks/<task-id>/`, `reports/<task-id>/`, or `scratch/<task-id>/`.
Existing task identifiers and agreements remain valid. A handoff records the
recovery point and links these guides; it does not maintain a second user manual.

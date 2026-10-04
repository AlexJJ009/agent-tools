# Agent Tools

Tools for agent workflows, learning and writing, project context synchronization,
and machine setup. [System guides](docs/README.md) describe current interfaces;
[architecture decisions](docs/decisions/README.md) explain adopted boundaries.

## Setup

From the repository checkout, install for the intended Unix user:

```bash
./scripts/install.sh --root "$HOME/projects" --max-depth 3
./scripts/install.sh --check
```

Native Win11 uses `scripts/install-win11.ps1` from Windows PowerShell.
WSL installs target the Unix profile. Read [installation](docs/INSTALLATION.md)
for managed install/data roots, platform options, cron, guards and rollback;
[server bootstrap](docs/CLI_SERVER_BOOTSTRAP.md) installs the required CLIs and
configures per-server providers. Build a portable archive with
`./scripts/pack.sh`.

The development workflow suite has a separate Linux/WSL installer:

```bash
python3 scripts/install_agent_workflow.py
python3 scripts/install_agent_workflow.py --check
```

It installs skills under `~/.agents/skills/` and runtime under
`~/.local/share/agent-workflow/`; see [agent workflow](docs/AGENT_WORKFLOW.md).

## Components

| Component | Source and entry points | Guide |
|---|---|---|
| Project context sync | `scripts/sync_agent_context.py`, `scripts/sync_agent_context_cron.sh` | [Context synchronization](docs/CONTEXT_SYNC.md) |
| Project memory | `scripts/codex_project_memory.py` | [Memory sync and migration](docs/CODEX_PROJECT_MEMORY.md) |
| Task state and material inventory | `agent_workflow/`, installed `agent-workflow` | [Task runtime](docs/TASK_RUNTIME.md) |
| Development skills | `skills/{intent-to-contract,infra-verification,cleaner,acceptance-gate,reviewer-brief}/` | [Agent workflow](docs/AGENT_WORKFLOW.md) |
| Learning and writing | `learning_workflow/`, `skills/` | [Learning workflow](docs/LEARNING_WORKFLOW.md) |
| Work Report | `skills/work-report/` | [Reports](docs/WORK_REPORT.md), [timer](docs/WORK_REPORT_LIGHT_TIMER.md) |
| Managed worktrees | `bin/agent-wt`, `skills/manage-worktrees/` | [Worktrees](docs/GIT_WORKTREE_AND_AGENT_WT_GUIDE.md) |
| Claude Code adapter | `adapters/claude/`, `scripts/install_claude.py` | [Claude adapter](docs/CLAUDE_CODE_ADAPTER.md) |
| Win11 Codex patch safety | `skills/codex-win11-patch-safety/` | [Versioned patch workflow](skills/codex-win11-patch-safety/SKILL.md) |
| Codex setup and repair | `scripts/configure_codex_*.py`, `scripts/migrate_codex_provider_bucket.py` | [Platform guides](docs/README.md#platform-and-operation-guides) |
| Workspace launcher | `bin/codex-here` | [Remote control](docs/CODEX_REMOTE_CONTROL.md) |

Software installs under `~/.local/lib/agent-tools`; application data and logs
stay under `~/.local/share/agent-tools`. Reinstallation removes obsolete managed
software and keeps unrelated files. Machine-local configuration and private
outputs remain untracked. [CONTRIBUTING.md](CONTRIBUTING.md) defines repository
checks and [AGENTS.md](AGENTS.md) records project constraints.

Network proxy configurations are maintained in the separate `win11-v2rayn`
and `server-proxy-config` repositories. The retired Win11 relay is no longer
part of Agent Tools.

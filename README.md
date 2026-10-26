# Agent Tools

Tools for learning and writing skills, project context synchronization,
managed worktrees and machine setup. [System guides](docs/README.md) describe current interfaces;
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

The installer links the learning and writing skills from the install root into
`~/.agents/skills/`; `--claude-code existing` also links them into
`~/.claude/skills/`. Agent Tools registers no Codex or Claude hooks and keeps no
task state; see [ADR 0012](docs/decisions/0012-retire-workflow-runtime.md).

## Components

| Component | Source and entry points | Guide |
|---|---|---|
| Project context sync | `scripts/sync_agent_context.py`, `scripts/sync_agent_context_cron.sh` | [Context synchronization](docs/CONTEXT_SYNC.md) |
| Learning and writing skills | `skills/{academic-writing,teaching-reconstruction,evidence-anchor,retrieval-practice,teaching-dag-builder,learning-artifact-compiler,task-routing}/`, `shared/writing/` | [Learning skills](docs/LEARNING_WORKFLOW.md) |
| Managed worktrees | `bin/agent-wt`, `skills/manage-worktrees/` | [Worktrees](docs/GIT_WORKTREE_AND_AGENT_WT_GUIDE.md) |
| CI watcher | `bin/ci-watch` | [ci-watch](docs/CI_WATCH.md) |
| Claude Code adapter | `adapters/claude/`, `scripts/install_claude.py`, `scripts/install_skills.py` | [Claude adapter](docs/CLAUDE_CODE_ADAPTER.md) |
| Codex setup and repair | `scripts/migrate_codex_provider_bucket.py` | [Platform guides](docs/README.md#platform-and-operation-guides) |
| Workspace launcher | `bin/codex-here` | [Remote control](docs/CODEX_REMOTE_CONTROL.md) |

Software installs under `~/.local/lib/agent-tools`; logs
stay under `~/.local/share/agent-tools`. Reinstallation removes obsolete managed
software and keeps unrelated files. Machine-local configuration and private
outputs remain untracked. [CONTRIBUTING.md](CONTRIBUTING.md) defines repository
checks and [AGENTS.md](AGENTS.md) records project constraints.

Network proxy configurations are maintained in the separate `win11-v2rayn`
and `server-proxy-config` repositories. The retired Win11 relay is no longer
part of Agent Tools.

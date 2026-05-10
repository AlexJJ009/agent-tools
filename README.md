# Agent Context Sync

Portable bridge for keeping Claude Code and Codex project context in sync.

It syncs the two agent conventions:

- Claude Code: `CLAUDE.md`, `.claude/`
- Codex: `AGENTS.md`, `.codex/`

The recommended deployment model is one central tool directory per machine, not one full script copy per project. Each project only receives generated bridge files and mirrored config directories.

## Files

- `sync_agent_context.py` — main scanner and synchronizer.
- `sync_agent_context_cron.sh` — heartbeat wrapper for cron.
- `codex_project_memory.py` — creates a project-local Codex memory layer and
  can import Claude Code auto memory.
- `install.sh` — portable installer for a new Linux/WSL2 machine.
- `experiment_registry/` — canonical SQLite experiment registry tooling,
  schema, queries, validation scripts, and the `experiment-registry` skill.
- `AGENTS.md` — project constraints for future agent changes.
- `docs/CODEX_AUTOREVIEW_DEFAULT.md` — runbook for Codex defaults, including
  AutoReview without Full Access and stream timeout/retry defaults.
- `docs/CODEX_WSL2_PROXY.md` — WSL2-only Codex proxy wrapper runbook for the
  local Windows v2rayN HTTP proxy path; do not treat it as a cross-platform
  default.
- `docs/CODEX_PLAYWRIGHT_TOOLS.md` — WSL2 machine-local Playwright MCP and
  Chromium screenshot entry points for Codex browser/visual-QA work. Other
  servers still need their own installation/registration.
- `docs/CODEX_PROJECT_MEMORY.md` — runbook for project-scoped Codex memory using
  `.codex/project-memory/`.
- `docs/AGENT_MEMORY_SYNC.md` — runbook for bidirectional Claude Code / Codex
  project memory sync.
- `docs/CLAUDE_TO_CODEX_MEMORY_MIGRATION.md` — runbook for migrating Claude Code
  auto memory into Codex-readable project context.
- `agent_context_sync.config.json` — local machine config, ignored by git.
- `agent_context_sync.config.example.json` — template for other machines.
- `logs/` — daily heartbeat logs.

## Install On A New Machine

Create a portable archive:

```bash
./pack.sh
```

The default output is `../agent-tools-portable.tar.gz`, excluding logs, pycache, and tarballs.

Copy this directory or the tarball to any stable path, for example:

```bash
mkdir -p ~/agent-tools
tar -xzf agent-tools-portable.tar.gz -C ~/
```

Then install for the local machine's project roots:

```bash
cd ~/agent-tools
./install.sh --root ~/projects --root /data-1 --max-depth 3
```

If the machine only has one root:

```bash
./install.sh --root /workspace
```

For WSL2, typical roots may be:

```bash
./install.sh --root ~/projects --root /mnt/d/projects
```

The installer writes `agent_context_sync.config.json` using the actual paths on the current machine and installs a cron heartbeat by default. It also installs experiment registry symlinks when `experiment_registry/` is present. The local SQLite database is not created unless `--registry-init-db` is passed.

## Experiment Registry

`agent-tools/experiment_registry` is the canonical source for registry code and
the `experiment-registry` skill. Project directories should link to it instead
of maintaining independent copies:

```text
/path/to/dpo-experiment/experiment_registry -> agent-tools/experiment_registry
/path/to/dpo-experiment/.codex/skills/experiment-registry -> agent-tools/experiment_registry/skills/experiment-registry
/path/to/verl/.codex/skills/experiment-registry -> agent-tools/experiment_registry/skills/experiment-registry
```

The actual SQLite database is machine-local runtime state and should not be
committed to Git:

```text
/data-1/experiment_registry/experiment_registry.sqlite
```

Initialize or verify registry links explicitly:

```bash
./experiment_registry/install_registry_links.sh --init-db
./experiment_registry/validate_registry_install.sh
```

Use `--force` with `install_registry_links.sh` only when replacing an existing
copy with the canonical symlink is intended.

## Machine Defaults

Every Linux/WSL2 install must persist tmux mouse mode for the Unix user running
the tools. This makes mouse-wheel scrolling work inside tmux.

The installer enforces this in `~/.tmux.conf` with a managed block:

```tmux
# BEGIN agent-tools tmux mouse
# Required on Linux/WSL2 servers so mouse-wheel scrolling works inside tmux.
set -g mouse on
# END agent-tools tmux mouse
```

Re-running the installer refreshes the block and leaves other tmux settings
alone. If a tmux server is already running, the installer also tries to source
the config and set the live global `mouse` option.

The installer also patches the Codex user config for the Unix user running it:

```toml
stream_idle_timeout_ms = 900000
stream_max_retries = 10
```

This is the default mitigation for Codex CLI/app compression or streaming
disconnects: 15 minutes of idle stream time and 10 SSE stream retry attempts.
It preserves existing top-level settings such as `model`, `approval_policy`,
`approvals_reviewer`, project trust entries, and TOML tables. Use
`--no-codex-config` to skip this step, or set `CODEX_STREAM_IDLE_TIMEOUT_MS`
and `CODEX_STREAM_MAX_RETRIES` to override the default values.

## Config

`agent_context_sync.config.json` is intentionally machine-local:

```json
{
  "scan_roots": ["/data-1"],
  "max_depth": 3,
  "scope": "all",
  "direction": "bidirectional",
  "prefer": "none",
  "mode": "symlink",
  "include_config_only": false
}
```

Use `scan_roots` for every parent directory that may contain projects. Different servers can use different paths.

## Manual Commands

Scan:

```bash
python sync_agent_context.py scan --root /data-1 --max-depth 3
```

Dry-run heartbeat:

```bash
python sync_agent_context.py heartbeat --check
```

Run heartbeat now:

```bash
python sync_agent_context.py heartbeat
```

Sync one project:

```bash
python sync_agent_context.py sync /path/to/project --direction bidirectional
```

Initialize project-level Codex memory:

```bash
python codex_project_memory.py sync /path/to/project --direction both
python sync_agent_context.py sync /path/to/project --direction bidirectional
```

## Conflict Policy

The default heartbeat is conservative:

- It fills missing Claude or Codex side.
- It updates files previously generated by this tool.
- It mirrors `.claude/` and `.codex/` context files.
- If both `CLAUDE.md` and `AGENTS.md` are hand-written and differ, it reports a conflict and does not overwrite either side.

For an explicit one-time override:

```bash
python sync_agent_context.py sync /path/to/project --direction bidirectional --prefer claude
python sync_agent_context.py sync /path/to/project --direction bidirectional --prefer codex
```

## Cron

The installer adds one crontab entry like:

```cron
17 * * * * /absolute/path/to/agent-tools/sync_agent_context_cron.sh
```

The cron script is self-locating. It finds `sync_agent_context.py` and `agent_context_sync.config.json` relative to its own directory, so the directory can live anywhere as long as the crontab points to the correct installed path.

Logs are written to:

```bash
agent-tools/logs/sync-YYYYMMDD.log
```

## Project-Local Wrappers

A repo may keep a small wrapper at `scripts/sync_agent_context.py`, but it should only forward to the central tool. Do not maintain separate full copies in every project.

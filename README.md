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
- `bin/codex-here` — portable launcher that starts Codex with the current shell
  directory pinned via `codex -C "$PWD"`.
- `install.sh` — portable installer for a new Linux/WSL2 machine.
- `experiment_registry/` — canonical SQLite experiment registry tooling,
  schema, queries, validation scripts, and the `experiment-registry` skill.
- `AGENTS.md` — project constraints for future agent changes.
- `docs/CODEX_AUTOREVIEW_DEFAULT.md` — runbook for Codex defaults, including
  AutoReview without Full Access and stream timeout/retry defaults.
- `docs/CODEX_WSL2_PROXY.md` — WSL2-only Codex proxy wrapper runbook for the
  local Windows v2rayN HTTP proxy path; do not treat it as a cross-platform
  default.
- `docs/CODEX_REMOTE_CONTROL.md` — Codex CLI remote-control runbook for
  standalone installs, proxy-wrapped WSL2 app-server daemons, and host-specific
  proxy port probing.
- `docs/CLI_SERVER_BOOTSTRAP.md` — repeatable Linux server bootstrap for latest
  Codex CLI, Claude Code, GitHub CLI, `cc-switch-cli`, `ripgrep`, and Codex
  API-provider configuration with per-server keys/Base URLs.
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

For WSL2 Codex remote control through a local Windows proxy, let the installer
probe common proxy ports before installing the Codex wrapper:

```bash
CODEX_PROXY_PORTS="7897 7890 7891 10809 10808 8080" \
  ./install.sh --root ~/projects --codex-proxy-wrapper auto
```

If the host's proxy port is known, pass it explicitly:

```bash
CODEX_PROXY_URL=http://127.0.0.1:7897 \
  ./install.sh --root ~/projects --codex-proxy-wrapper always
```

For ordinary Linux servers without a local proxy wrapper:

```bash
./install.sh --root /data-1 --codex-proxy-wrapper never
```

For a full repeatable server setup that also installs the latest Codex CLI,
Claude Code, GitHub CLI, `cc-switch-cli`, `ripgrep`, and Codex API providers
from fresh keys/Base URLs, follow `docs/CLI_SERVER_BOOTSTRAP.md`.

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
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "guardian_subagent"
model = "gpt-5.5"
model_reasoning_effort = "high"
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
model_provider = "openai-no-ws"

[features]
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true

[model_providers.openai-no-ws]
name = "OpenAI HTTPS no WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
```

This combines three default sets:

- **AutoReview as the default permission posture** (`approval_policy`,
  `sandbox_mode`, `approvals_reviewer`). New Codex conversations open with the
  Guardian subagent reviewing approvals rather than the user, and stay out of
  Full Access. See `docs/CODEX_AUTOREVIEW_DEFAULT.md` for rationale and
  rollback.
- **Model + reasoning posture** (`model`, `model_reasoning_effort`). Pins the
  default model and reasoning effort for new conversations.
- **Compression / streaming resilience** (`stream_idle_timeout_ms`,
  `stream_max_retries`, `model_provider` + the managed `openai-no-ws`
  provider). 30 minutes of idle stream time, 20 SSE retries, and an HTTPS-only
  provider that avoids WebSocket transport on proxy paths where WebSocket TLS
  handshakes are unstable.
- **Feature flags** (`[features]` block). Enables `hooks`, `memories`,
  `goals`, `terminal_resize_reflow`, and `remote_control`. The installer also
  removes the deprecated `codex_hooks` key if present.

The installer also installs:

```bash
~/.local/bin/codex-here
```

It also adds a managed PATH block for `~/.local/bin` to `~/.profile` and to
existing shell rc files such as `~/.bashrc` or `~/.zshrc`. This matters on fresh
Linux and WSL installs where `~/.local/bin` is not always active in new shells.

Use it from any project directory when Remote Control or an already-bound
app-server keeps reopening Codex in the wrong workspace:

```bash
cd /path/to/project
codex-here
```

`codex-here` is deliberately separate from the base `codex` command. It runs
`codex -C "$PWD" "$@"`, so management commands such as
`codex remote-control start` and `codex app-server daemon restart` keep their
normal behavior. Pass `--no-codex-here` to skip installing this launcher.

It preserves existing top-level settings such as `service_tier`, project trust
entries, and other TOML tables (e.g. `[mcp_servers.*]`, `[tui]`, `[notice]`).
Use `--no-codex-config` to skip this step, or override individual defaults via
env vars: `CODEX_APPROVAL_POLICY`, `CODEX_SANDBOX_MODE`,
`CODEX_APPROVALS_REVIEWER`, `CODEX_MODEL`, `CODEX_MODEL_REASONING_EFFORT`,
`CODEX_STREAM_IDLE_TIMEOUT_MS`, `CODEX_STREAM_MAX_RETRIES`,
`CODEX_MODEL_PROVIDER_ID`, and `CODEX_FEATURE_HOOKS` /
`CODEX_FEATURE_MEMORIES` / `CODEX_FEATURE_GOALS` /
`CODEX_FEATURE_TERMINAL_RESIZE_REFLOW` / `CODEX_FEATURE_REMOTE_CONTROL`
(each accepts `true` or `false`).

When Codex config patching is enabled, the installer also scans existing
project-level `.codex/config.toml` files under the configured `--root` paths and
migrates hook-enabled projects from deprecated `[features].codex_hooks` to
`[features].hooks`. It only updates existing project config files that already
contain hook config or the deprecated key.

The installer can also install a WSL2 Codex proxy wrapper before starting remote
control. The wrapper mode is controlled by `--codex-proxy-wrapper auto|always|never`.
In `auto` mode, it probes `CODEX_PROXY_PORTS` on `CODEX_PROXY_HOST` and installs
the wrapper only when a candidate reaches the Codex backend. Use
`CODEX_PROXY_URL` for a known host-specific proxy URL. By default the installer
runs `codex remote-control start`; pass `--no-codex-remote-control` to only
write configuration. See `docs/CODEX_REMOTE_CONTROL.md` for standalone binary
and daemon validation details.

The installer also verifies the agent-core user-level entry symlinks if
`~/agent-core/scripts/install.sh` is present (override via `AGENT_CORE_HOME`).
Concretely it checks that `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` are
symlinks resolving inside `$AGENT_CORE_HOME/adapters/`. If either is missing,
it invokes agent-core's `install.sh` to restore the symlinks. If a destination
is a regular file or points elsewhere, the installer leaves it alone and prints
a conflict line so a human can decide. Use `--no-agent-core` to disable this
check entirely.

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

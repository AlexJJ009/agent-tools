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
- `migrate_codex_provider_bucket.py` — Codex history and cc-switch template
  migration that forces every non-target Codex provider bucket into `custom`.
- `install.sh` — portable installer for a new Linux/WSL2 machine.
- `scripts/configure_codex_app_fast_mode.py` — cross-platform Codex App/CLI
  config patch that keeps `service_tier = "priority"` and
  `[features].fast_mode = true` in the target Codex home.
- `scripts/configure_codex_sqlite_log_guard.py` — short-term SSD protection
  patch that blocks high-volume diagnostic inserts into Codex
  `logs_2.sqlite` until upstream logging is fixed.
- `scripts/patch_codex_desktop_connection_fast_mode.py` — diagnostic bundle
  patch generator for Codex Desktop builds that drop explicit Fast
  `serviceTier` when using WSL/SSH Connections.
- `scripts/setup_codex_desktop_connection_fast_mode.py` — higher-level Win11
  and macOS setup wrapper for the Desktop Connection Fast Mode patch. It records
  the Codex Desktop version route: current `26.616.x` Win11 builds need a scoped
  NewAPI provider override, while older builds keep using the legacy bundle patch.
  On Win11 from WSL it rebuilds a writable patched Store-app copy plus
  Desktop/Start Menu shortcuts; on macOS it can patch `Codex.app`.
- `scripts/verify_codex_fast_mode_runtime.py` — runtime verifier that queries
  sub2api `usage_logs` by time window or `request_id` and checks whether the
  request was really billed as Fast/priority.
- `experiment_registry/` — canonical SQLite experiment registry tooling,
  schema, queries, validation scripts, and the `experiment-registry` skill.
- `goal_plan/` — canonical Claude Code and Codex App/CLI goal-planning skill,
  slash command, reviewer agent, and Codex personal plugin assets.
- `AGENTS.md` — project constraints for future agent changes.
- `docs/CODEX_AUTOREVIEW_DEFAULT.md` — runbook for Codex defaults, including
  AutoReview without Full Access and stream timeout/retry defaults.
- `docs/CODEX_SQLITE_LOG_GUARD.md` — short-term runbook for the
  `logs_2.sqlite` trigger guard used to protect SSD write endurance and Codex
  Desktop startup time.
- `docs/CODEX_WSL2_PROXY.md` — WSL2-only Codex proxy wrapper runbook for the
  local Windows v2rayN HTTP proxy path; do not treat it as a cross-platform
  default.
- `docs/CODEX_REMOTE_CONTROL.md` — Codex CLI remote-control runbook for
  standalone installs, proxy-wrapped WSL2 app-server daemons, and host-specific
  proxy port probing.
- `docs/CODEX_APP_FAST_MODE_MACOS_GUIDE.md` — teammate-facing prompt and
  runbook for enabling Codex App Fast Mode on macOS and SSH Connections.
- `docs/CODEX_DESKTOP_CONNECTION_FAST_MODE_PATCH.md` — notes on diagnosing and
  patching Desktop Connection `serviceTier` propagation without forcing Fast for
  every provider request.
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

The installer always enables Codex Fast defaults for the current Codex home.
On macOS this is the same `~/.codex/config.toml` used by the Codex App and CLI.
On WSL2 it also patches the detected Windows Codex App home under
`/mnt/c/Users/*/.codex` by default, so the Win11 App gets the same Fast default
as the WSL/SSH app-server path. Use `--no-codex-app-fast-mode` to skip this
small config-only patch, or `--codex-app-fast-wsl-windows never` if a WSL
install should not touch the Windows Codex App config.

The installer also enables the short-term Codex SQLite log guard by default.
This installs a trigger in `logs_2.sqlite` that ignores new diagnostic log
rows, protecting SSD write endurance on long streaming or automation runs. On
WSL2 it patches both the WSL Codex home and detected Win11 Codex App homes by
default. Use `--no-codex-sqlite-log-guard` to skip it, or
`--disable-codex-sqlite-log-guard` after OpenAI fixes the upstream logging bug.
See `docs/CODEX_SQLITE_LOG_GUARD.md`.
When running installer helpers, `install.sh` probes for a working Python 3.10+
binary first (`python3.13` through `python3.10`, then version-checked
`python3`/`python`) before falling back, which avoids hosts where the default
`python3` is too old but a newer Python is already installed.

If Claude Code is already installed on the machine, the installer also prepares
it for Claude Desktop SSH sessions. It writes `IS_SANDBOX=1` into
`/etc/environment` so non-interactive SSH sessions inherit the root guard
escape hatch, and it exposes the existing `claude` binary through
`/usr/local/bin/claude` so root sessions do not depend on shell startup files or
temporary fnm paths. This step does not install Claude Code; when `claude` is not
already on `PATH`, it skips cleanly. Use `--no-claude-desktop-ssh` to skip this
system-level compatibility patch.

The installer updates `cc-switch-cli` from GitHub releases by default. That
step uses bounded curl timeouts/retries and, in `auto` mode, probes the same
local proxy candidates used by the Codex wrapper. Use
`--cc-switch-update-proxy never` to force direct GitHub access,
`--cc-switch-update-proxy always` to require a working local proxy, or
`--no-cc-switch-update` to skip the update.

For a full repeatable server setup that also installs the latest Codex CLI,
Claude Code, GitHub CLI, `cc-switch-cli`, `ripgrep`, and Codex API providers
from fresh keys/Base URLs, follow `docs/CLI_SERVER_BOOTSTRAP.md`.

The installer writes `agent_context_sync.config.json` using the actual paths on the current machine and installs a cron heartbeat by default. It also installs experiment registry symlinks when `experiment_registry/` is present. The local SQLite database is not created unless `--registry-init-db` is passed.

On ordinary Linux hosts with `sshd`, the installer also checks `fail2ban` in
auto mode. If it is missing and a supported package manager is available, it
installs it. It then enforces a strict `sshd` jail through
`/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local`: aggressive SSH
matching, 3 failures within 1 hour, permanent ban, and `DROP` rather than
`REJECT`. The managed `ignoreip` is intentionally loopback-only
(`127.0.0.1/8 ::1`); the installer does not guess trusted public IPs. Use
`--no-fail2ban-hardening` only on hosts where agent-tools should not touch
system SSH protection, or set `INSTALL_FAIL2BAN_HARDENING=always` when a
non-standard server should be forced through the same check.

By default it also installs the user-level goal-plan tools from `goal_plan/`:

- Claude Code: `~/.claude/skills/goal-plan`, `~/.claude/commands/goal-plan.md`,
  and `~/.claude/agents/goal-plan-reviewer.md`.
- Codex App/CLI: `~/.codex/skills/goal-plan`, `~/plugins/goal-plan`, a personal
  marketplace entry, and `codex plugin add goal-plan@personal` when `codex` is
  available on `PATH`.
- Runtime tools: an isolated uv environment at
  `~/.local/share/goal-plan/runtime/.venv` and the launcher
  `~/.local/bin/goal-plan-runtime`. The runtime never imports the target
  project's Python environment, so Goals can govern repositories written in any
  language. `uv` must already be available on `PATH`; installation does not
  silently download it from the network.

`goal_plan/` is the source of truth inside this repo. The installed user-level
locations are separate:

- Linux, WSL, and server installs use `install.sh` and install into the current
  Unix user. If the server default user is `root`, this means `/root/.claude`,
  `/root/.codex`, `/root/plugins/goal-plan`, and `/root/.agents`.
- WSL installs also copy goal-plan into detected Win11 user homes by default:
  `C:\Users\<User>\.claude`, `C:\Users\<User>\.codex`,
  `C:\Users\<User>\plugins\goal-plan`, and the Codex personal plugin cache.
  Use `--goal-plan-wsl-windows never` to skip this, or
  `--goal-plan-wsl-windows always` when missing Windows homes should fail the
  install.
- Native Win11 clones should run `scripts\install-win11.ps1`. That installs the
  same Claude Code and Codex App user-level files for the current Windows user.
  It also installs
  `C:\AppsExternal\automation\_diagnostics\restart-codex-manual-remote.ps1` and
  disables Codex App remote auto-connect by default for that Windows user.

This creates the explicit `/goal-plan` planning command and Codex plugin command.
It intentionally does not redirect, wrap, or replace `/goal`; `/goal` remains the
execution loop. Use `--no-goal-plan` to skip this installation.

## Win11 Codex Remote Connections

Codex App can become slow on startup when saved remote Connections reconnect
automatically. Native Win11 installs therefore make remote Connections manual by
default. The installed helper edits:

```text
C:\Users\<User>\.codex\.codex-global-state.json
```

It sets every value under `remote-connection-auto-connect-by-host-id` to `false`
and attempts to clear `selected-remote-host-id`. Recent Codex App builds may
restore `selected-remote-host-id` as the currently highlighted host, so the
helper verifies the actual manual-connect behavior by checking that every
auto-connect value remains `false` and stopping any already-started
`codex app-server proxy` SSH process after restart. The helper uses Python to
read/write JSON because PowerShell `ConvertFrom-Json` can fail on this state
file shape. It does not remove saved hosts, SSH config, credentials, plugins, or
remote-control support; it only prevents Codex App from reconnecting to those
hosts during startup.

Install without changing that behavior:

```powershell
scripts\install-win11.ps1 -NoCodexManualRemoteConnect
```

Run the full restart helper manually when Codex App is already sluggish:

```powershell
C:\AppsExternal\automation\_diagnostics\restart-codex-manual-remote.ps1
```

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
service_tier = "priority"
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
model_provider = "custom"

[features]
fast_mode = true
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true

[model_providers.custom]
name = "OpenAI WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = true
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
```

For Codex App, this config-level Fast default is the baseline. The installer can
also prepare Codex Desktop so WSL/SSH Connections preserve the selected
`serviceTier`:

- On Win11/WSL, `--codex-desktop-connection-fast-mode auto` prepares a writable
  patched copy of the Microsoft Store app and writes launchers plus a
  `Codex Fast Connections` Desktop/Start Menu shortcut. Each run mirrors the
  current Store package again, so Store updates/reinstalls are handled by
  rerunning the installer. For Codex Desktop `26.616.x`, this local step is not
  sufficient by itself; the tokenrouter NewAPI channel must also apply the
  scoped `/v1/responses` Codex `service_tier = "priority"` override documented
  in `docs/CODEX_DESKTOP_CONNECTION_FAST_MODE_PATCH.md`.
- On macOS, `auto` attempts to patch the installed `Codex.app` bundle when it
  is writable. Use `--codex-desktop-connection-fast-mode always` when patch
  failure should fail the install, or `--no-codex-desktop-connection-fast-mode`
  to leave the app bundle untouched.

Follow `docs/CODEX_DESKTOP_CONNECTION_FAST_MODE_PATCH.md` for launch, version
routing, provider override, and verification. A correctly configured app-server
should report Fast-capable settings, but the authoritative check is the real
provider log and billing row for the request. In the current newapi -> sub2api
chain, the value to verify is `priority`; `fast` is only a legacy/UI alias.

Before running the Codex provider-bucket migration, the installer updates
`cc-switch-cli` from the latest GitHub release installer. Use
`--no-cc-switch-update` only when the target machine cannot or should not reach
GitHub during install.

By default, the installer also applies the Codex provider-bucket migration for
all non-`custom` history buckets, including older `openai`, `openai-no-ws`,
`subrouter`, and provider-specific names. It terminates running Codex processes
before rewriting the history index so the install can complete in one pass. Use
`--no-kill-running-codex-provider-bucket-migration` only when you intentionally
want to keep Codex running and accept a dry-run fallback. Use
`--codex-provider-bucket-trusted-sources-only` to keep the older behavior that
only migrates inferred cc-switch third-party buckets.

This combines three default sets:

- **AutoReview as the default permission posture** (`approval_policy`,
  `sandbox_mode`, `approvals_reviewer`). New Codex conversations open with the
  Guardian subagent reviewing approvals rather than the user, and stay out of
  Full Access. See `docs/CODEX_AUTOREVIEW_DEFAULT.md` for rationale and
  rollback.
- **Model + reasoning posture** (`model`, `model_reasoning_effort`,
  `service_tier`). Pins the default model, reasoning effort, and Fast service
  tier for new conversations.
- **Compression / streaming resilience** (`stream_idle_timeout_ms`,
  `stream_max_retries`, `model_provider` + the managed `custom`
  provider). 30 minutes of idle stream time, 20 streaming retries, and
  WebSocket transport enabled for every generated provider configuration. The
  stable `custom` bucket also matches cc-switch's
  Codex provider-switching convention, so history stays visible across
  third-party providers.
- **Feature flags** (`[features]` block). Enables `fast_mode`, `hooks`, `memories`,
  `goals`, `terminal_resize_reflow`, and `remote_control`. The installer also
  removes the deprecated `codex_hooks` key if present.
- **Temporary SQLite log guard** (`logs_2.sqlite` trigger). Blocks new
  high-volume diagnostic log rows as a short-term SSD protection patch. It does
  not affect `state_5.sqlite`, sessions, auth, memories, goals, plugins, Fast
  Mode, Connections, or cc-switch provider billing. Disable with
  `--disable-codex-sqlite-log-guard` once upstream logging is fixed.

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

It preserves project trust entries and other TOML tables (e.g.
`[mcp_servers.*]`, `[tui]`, `[notice]`) while managing the top-level
`service_tier` setting.
Use `--no-codex-config` to skip this step, or override individual defaults via
env vars: `CODEX_APPROVAL_POLICY`, `CODEX_SANDBOX_MODE`,
`CODEX_APPROVALS_REVIEWER`, `CODEX_MODEL`, `CODEX_MODEL_REASONING_EFFORT`,
`CODEX_SERVICE_TIER`,
`CODEX_STREAM_IDLE_TIMEOUT_MS`, `CODEX_STREAM_MAX_RETRIES`,
`CODEX_MODEL_PROVIDER_ID`, `CODEX_FEATURE_FAST_MODE`, and `CODEX_FEATURE_HOOKS` /
`CODEX_FEATURE_MEMORIES` / `CODEX_FEATURE_GOALS` /
`CODEX_FEATURE_TERMINAL_RESIZE_REFLOW` / `CODEX_FEATURE_REMOTE_CONTROL`
(each accepts `true` or `false`).

The temporary SQLite log guard is controlled separately:
`INSTALL_CODEX_SQLITE_LOG_GUARD`, `CODEX_SQLITE_LOG_GUARD_MODE`
(`enable|disable|status`), `CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS`
(`auto|always|never`), and `CODEX_SQLITE_LOG_GUARD_VACUUM` (`0|1`).

`--no-codex-config` skips the broader default rewrite, provider migration, proxy
wrapper, and remote-control start. It does not skip the small Codex App Fast
config patch; add `--no-codex-app-fast-mode` when that should also be disabled.

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

The installer also verifies the agent-core user-level entry and skill symlinks
if `~/agent-core/scripts/install.sh` is present (override via
`AGENT_CORE_HOME`). Concretely it checks that `~/.claude/CLAUDE.md` and
`~/.codex/AGENTS.md` are symlinks resolving inside `$AGENT_CORE_HOME/adapters/`,
and that every `$AGENT_CORE_HOME/skills/*` directory is linked into both
`~/.claude/skills/` and `~/.codex/skills/`. If any expected symlink is missing,
it invokes agent-core's `install.sh` to restore entries and skills. If a
destination is a regular file/directory or points elsewhere, the installer
leaves it alone and prints a conflict line so a human can decide. Use
`--no-agent-core` to disable this check entirely.

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

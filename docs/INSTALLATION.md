# Agent Tools Installation

Run setup for the intended local user from a repository checkout. Linux/WSL
and native Windows use separate installers and profiles. Component guides
explain their own behavior; this guide records the general installer and its
machine-level options.

## Install On A New Machine

Create a portable archive:

```bash
./scripts/pack.sh
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
./scripts/install.sh --root ~/projects --root /data-1 --max-depth 3
```

If the machine only has one root:

```bash
./scripts/install.sh --root /workspace
```

For WSL2, typical roots may be:

```bash
./scripts/install.sh --root ~/projects --root /mnt/d/projects
```

For WSL2 Codex remote control through a local Windows proxy, let the installer
probe common proxy ports before installing the Codex wrapper:

```bash
CODEX_PROXY_PORTS="7897 7890 7891 10809 10808 8080" \
  ./scripts/install.sh --root ~/projects --codex-proxy-wrapper auto
```

If the host's proxy port is known, pass it explicitly:

```bash
CODEX_PROXY_URL=http://127.0.0.1:7897 \
  ./scripts/install.sh --root ~/projects --codex-proxy-wrapper always
```

For ordinary Linux servers without a local proxy wrapper:

```bash
./scripts/install.sh --root /data-1 --codex-proxy-wrapper never
```

The installer always enables Codex Fast defaults for the current platform's
Codex home. On macOS this is the same `~/.codex/config.toml` used by the Codex
App and CLI. A WSL2 run no longer patches a mounted Windows Codex profile: run
`scripts\install-win11.ps1` from native Windows for Win11 state. The legacy
`--codex-app-fast-wsl-windows always` mode is rejected on WSL.

The installer also enables the short-term Codex SQLite log guard by default.
This installs a trigger in `logs_2.sqlite` that ignores new diagnostic log
rows, protecting SSD write endurance on long streaming or automation runs. On
WSL2 it applies only to the WSL Codex home. Run `scripts\install-win11.ps1`
for the native Win11 database. Use `--no-codex-sqlite-log-guard` to skip it, or
`--disable-codex-sqlite-log-guard` after OpenAI fixes the upstream logging bug.
See `docs/CODEX_SQLITE_LOG_GUARD.md`.
When running installer helpers, `scripts/install.sh` probes for a working Python 3.10+
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

`scripts/install.sh` copies the software into the install root
`~/.local/lib/agent-tools` (override with `--install-dir` or
`AGENT_TOOLS_INSTALL_ROOT`); the learning bundle and Claude views go to
`learning-workflow/` and `claude/` inside it. Task state, materials, archives
and logs stay in the data root (`~/.local/share/agent-tools` on Linux/WSL).
The installer refuses an install root that equals, contains or lies inside the
data root. Each reinstall syncs against the manifest
`.agent-tools-manifest.json`: files an earlier install wrote and no longer
ships are deleted, other files are listed as unmanaged and kept. When an
earlier release was installed with `--install-dir <data root>`, the installer
repoints skills, hooks, launchers, the Codex instruction block and crontab,
then deletes the released software copies from the data root (modified copies
move to `archives/legacy-install-<stamp>/`) and records each removal in the
material ledger. Data and unknown items are listed and left alone.
`scripts/install.sh --check` reports install-root drift and software left in the data
root.

The installer writes `agent_context_sync.config.json` using the actual paths on the current machine. Context synchronization is manual by default; use `--cron` only to explicitly enable an hourly heartbeat. See [context synchronization](CONTEXT_SYNC.md) for configuration and commands.

On ordinary Linux hosts with `sshd`, the installer also checks `fail2ban` in
auto mode. If it is missing and a supported package manager is available, it
installs it. It then enforces a strict `sshd` jail through
`/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local`: aggressive SSH
matching, 3 failures within 1 hour, permanent ban, and `DROP` rather than
`REJECT`. The managed `ignoreip` defaults to loopback-only
(`127.0.0.1/8 ::1`); the installer does not guess trusted public IPs. It does,
however, preserve the ones you added yourself: on every run it merges the
default with the managed file's current `ignoreip` and the live effective list,
so reinstalling never drops a peer you had already whitelisted. Use
`--no-fail2ban-hardening` only on hosts where agent-tools should not touch
system SSH protection, or set `INSTALL_FAIL2BAN_HARDENING=always` when a
non-standard server should be forced through the same check.

Installed user-level locations are separate:

- Linux, WSL, and server installs use `scripts/install.sh` and install into the current
  Unix user. If the server default user is `root`, this means `/root/.claude`,
  `/root/.codex`, and `/root/.agents`.
- WSL installs never copy Skills or plugins into a mounted Win11 profile.
- Native Win11 clones should run `scripts\install-win11.ps1`. That installs the
  Codex App user-level files for the current Windows user. It also installs
  `C:\AppsExternal\automation\_diagnostics\restart-codex-manual-remote.ps1` and
  disables Codex App remote auto-connect by default for that Windows user.
  Unlike Linux/WSL provider bootstraps, native Win11 Codex App uses a custom
  bearer-token mode: `auth.json` keeps `auth_mode = "chatgpt"`,
  `OPENAI_API_KEY = null`, and placeholder tokens; `config.toml` keeps
  `model_provider = "custom"`, `base_url = "http://15.204.46.107:8080"`,
  `requires_openai_auth = true`, `supports_websockets = true`,
  `wire_api = "responses"`, and the live credential in
  `experimental_bearer_token`. The installer also keeps cc-switch's current
  Codex provider on this same custom bearer-token provider. Use
  `-DryRunCodexProviderBucketMigration` to inspect history first, or
  `-AllowRunningCodexProviderBucketMigration` when running from inside an
  active Codex conversation.

## Codex Fleet Target Guard

All Agent Tools installers, Skill deployments, and Codex/CC Switch
configuration helpers must validate their target before writing. The guard is
read-only: it verifies the platform, Unix/Windows profile boundary, Codex
provider shape, CC Switch database validation, and current provider without
printing secrets.

The standalone Fast-mode, SQLite-log, Win11 bearer-token, and provider-bucket
scripts call the same guard themselves before writes. The guard therefore
remains effective when a script is invoked outside `scripts/install.sh`; it is not a
convention that callers may skip.

For a Linux/WSL/SSH fleet, copy
`config/codex-fleet.targets.example.json` to an untracked local manifest and
fill in only host aliases, users, and absolute non-secret paths. Then run:

```bash
python3 scripts/codex_fleet_guard.py sync --manifest config/codex-fleet.targets.json
python3 scripts/codex_fleet_guard.py preflight \
  --manifest config/codex-fleet.targets.json \
  --expect-base-url http://15.204.46.107:8080 \
  --canary-reject
```

`sync` installs the hash-checked, read-only helper under the target user's
`~/.local/lib/agent-tools/`. `preflight` uses `ssh -o BatchMode=yes` and
`RequestTTY=no`, so it cannot automate a CC Switch text UI. `--canary-reject`
also proves that a deliberately wrong platform is rejected before any CC Switch
command can write. A Win11 target is never dispatched by this Linux controller:
run `scripts\install-win11.ps1` natively instead.

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

For Codex App, this config-level Fast default is the baseline. Win11 App updates
and patch activation use the [versioned safety workflow](../skills/codex-win11-patch-safety/SKILL.md).
The legacy helper described below remains a distinct installer capability, not
an exact-release update procedure. The installer can
also prepare Codex Desktop so WSL/SSH Connections preserve the selected
`serviceTier`:

- On Win11/WSL, `--codex-desktop-connection-fast-mode auto` prepares a writable
  patched copy of the Microsoft Store app and writes launchers plus a
  `Codex Fast Connections` Desktop/Start Menu shortcut. Each run mirrors the
  current Store package again, and is not a verified update route for an unknown Store build. For Codex Desktop `26.616.x`, this local step is not
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

Provider-bucket migration is a separate, explicit repair operation. Ordinary
installation neither migrates history nor terminates running Codex processes.
Use `--dry-run-codex-provider-bucket-migration` to inspect a proposed migration,
then `--apply-codex-provider-bucket-migration` when that repair is intended.
Stopping running Codex additionally requires
`--kill-running-codex-provider-bucket-migration`. These options also work with
`--no-codex-config`; model configuration and history repair are separate.

This configures the following defaults:

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

`--no-codex-config` skips the broader default rewrite, proxy wrapper and
remote-control start. Explicit provider-migration options remain independent. It does not skip the small Codex App Fast
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
it invokes agent-core's `scripts/install.sh` to restore entries and skills. If a
destination is a regular file/directory or points elsewhere, the installer
leaves it alone and prints a conflict line so a human can decide. Use
`--no-agent-core` to disable this check entirely.

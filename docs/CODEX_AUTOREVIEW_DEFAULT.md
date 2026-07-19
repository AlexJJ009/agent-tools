# Codex Default Configuration

This runbook configures Codex so new conversations use the local default
permission posture and tolerate long compression or streaming pauses.
It also installs a short-term SQLite log guard for Codex builds that write
high-volume diagnostic rows to `logs_2.sqlite`.

**As of the current `install.sh`, every section below is applied
automatically.** Re-run `./install.sh` (with or without `--root` flags) and the
target state lands in `~/.codex/config.toml` exactly as written here. The rest
of this document is the rationale, override knobs, and manual fallback when
running `install.sh` is not an option.

Tested with `codex-cli 0.130.0`.

## Target State

Set these top-level keys in the Codex user config:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "guardian_subagent"
model = "gpt-5.5"
model_reasoning_effort = "high"
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
model_provider = "custom"
```

Define the WebSocket-enabled Codex provider:

```toml
[model_providers.custom]
name = "OpenAI WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = true
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
```

Set the feature flags under `[features]`:

```toml
[features]
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true
```

Install the temporary SQLite log guard:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode enable
```

Meaning:

- `approval_policy = "on-request"` keeps approval flow enabled.
- `sandbox_mode = "workspace-write"` keeps the default session out of Full
  Access.
- `approvals_reviewer = "guardian_subagent"` routes eligible approval requests
  to the Guardian subagent rather than directly back to the user. Earlier
  versions of this runbook used `"auto_review"`; on current `codex-cli` the
  Guardian subagent is the canonical reviewer name.
- `model = "gpt-5.5"` and `model_reasoning_effort = "high"` pin the default
  model and reasoning effort. Override via `CODEX_MODEL` /
  `CODEX_MODEL_REASONING_EFFORT` if you want a different default per machine.
- `stream_idle_timeout_ms = 1800000` gives Codex 30 minutes of idle stream time
  before treating compression or app/CLI streaming as timed out.
- `stream_max_retries = 20` gives transient streaming disconnects more
  retry attempts before Codex gives up on the active response.
- `model_provider = "custom"` uses OpenAI/ChatGPT auth and forces the Responses
  WebSocket transport for generated Codex and cc-switch provider configs.
  The stable `custom` bucket also matches cc-switch's Codex provider-switching
  convention, so resume history is not split across third-party provider IDs.
- `[features]` enables Codex lifecycle hooks, the memory layer, goal tracking,
  terminal resize reflow, and remote control. The installer removes the
  deprecated `[features].codex_hooks` key if present. Do not use top-level
  `remote_control = true`, and do not write `remote_connections = true`;
  current Codex CLI remote control is started through the `codex remote-control`
  / `codex app-server daemon` command path.
- The SQLite log guard is a short-term SSD protection patch. It creates a
  trigger on `logs_2.sqlite.logs` so new diagnostic rows are ignored while
  leaving conversations, config, auth, memories, goals, plugins, Fast Mode, and
  Connections untouched. See `docs/CODEX_SQLITE_LOG_GUARD.md`.

Do not set these as the default for AutoReview:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

That is Full Access by default, which should only be enabled manually when
needed.

## Config Location

Codex reads:

```bash
${CODEX_HOME:-$HOME/.codex}/config.toml
```

On Linux or WSL2, run the setup as the same Unix user that runs `codex`.
Examples:

- root user: `/root/.codex/config.toml`
- normal user: `/home/<user>/.codex/config.toml`
- custom home: `$CODEX_HOME/config.toml`

Each WSL2 distro has its own Linux home directory. Configure the distro where
Codex is actually launched.

## One-Shot Setup

The recommended path is `./install.sh` from the agent-tools checkout, which
applies the entire target state (top-level keys, provider block, `[features]`)
in one pass and re-runs cleanly any number of times:

```bash
cd ~/agent-tools
./install.sh --root ~/projects --max-depth 3
```

To override individual defaults without editing the script, set the matching
env var before running:

| Knob | Env var | Default |
|---|---|---|
| approval policy | `CODEX_APPROVAL_POLICY` | `on-request` |
| sandbox mode | `CODEX_SANDBOX_MODE` | `workspace-write` |
| approvals reviewer | `CODEX_APPROVALS_REVIEWER` | `guardian_subagent` |
| model | `CODEX_MODEL` | `gpt-5.5` |
| model reasoning effort | `CODEX_MODEL_REASONING_EFFORT` | `high` |
| service tier | `CODEX_SERVICE_TIER` | `priority` |
| stream idle timeout (ms) | `CODEX_STREAM_IDLE_TIMEOUT_MS` | `1800000` |
| stream max retries | `CODEX_STREAM_MAX_RETRIES` | `20` |
| model provider id | `CODEX_MODEL_PROVIDER_ID` | `custom` |
| `[features].fast_mode` | `CODEX_FEATURE_FAST_MODE` | `true` |
| `[features].hooks` | `CODEX_FEATURE_HOOKS` | `true` |
| `[features].memories` | `CODEX_FEATURE_MEMORIES` | `true` |
| `[features].goals` | `CODEX_FEATURE_GOALS` | `true` |
| `[features].terminal_resize_reflow` | `CODEX_FEATURE_TERMINAL_RESIZE_REFLOW` | `true` |
| `[features].remote_control` | `CODEX_FEATURE_REMOTE_CONTROL` | `true` |

Pass `--no-codex-config` to skip the Codex patch entirely.

The temporary SQLite log guard is enabled by default and is controlled
separately from `--no-codex-config`:

| Knob | Env var / flag | Default |
|---|---|---|
| install guard | `INSTALL_CODEX_SQLITE_LOG_GUARD` / `--no-codex-sqlite-log-guard` | `1` |
| mode | `CODEX_SQLITE_LOG_GUARD_MODE` / `--disable-codex-sqlite-log-guard` | `enable` |
| WSL Windows homes | `CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS` / `--codex-sqlite-log-guard-wsl-windows` | `auto` |
| compact DB | `CODEX_SQLITE_LOG_GUARD_VACUUM` / `--codex-sqlite-log-guard-vacuum` | `0` |

The installer replaces the managed keys above, including top-level
`service_tier = "priority"` and `[features].fast_mode = true`. Do not put
`service_tier` under `[features]`. It preserves existing project trust entries
and other TOML tables (`[mcp_servers.*]`, `[tui]`, `[notice]`, etc.) and the
managed WebSocket-enabled Codex provider, and removes the deprecated
`[features].codex_hooks` key if present. It also removes stale top-level
`remote_control`, any `remote_connections` key, the obsolete
`disable_response_storage` key, and the incorrect `[features].service_tier` key
when normalizing managed features.

## Codex App Fast Defaults

`scripts/configure_codex_app_fast_mode.py` is the small cross-platform patch
used by the installer to keep Codex App and CLI config aligned on Fast mode. It
only edits `config.toml`:

```toml
service_tier = "priority"

[features]
fast_mode = true
```

On macOS, the Codex App and CLI use `~/.codex/config.toml`, so the normal
installer path covers the App. On WSL2, the installer also patches the detected
Windows Codex App home under `/mnt/c/Users/*/.codex` by default. Control this
with:

```bash
./install.sh --codex-app-fast-wsl-windows auto
./install.sh --codex-app-fast-wsl-windows never
./install.sh --no-codex-app-fast-mode
```

This normal install step is intentionally config-only. It does not patch signed
macOS app bundles, and it does not edit `app.asar`. For Codex Desktop
Connections, the installer has a separate route:

```bash
./install.sh --codex-desktop-connection-fast-mode auto
./install.sh --codex-desktop-connection-fast-mode always
./install.sh --no-codex-desktop-connection-fast-mode
```

In `auto` mode from WSL/Win11, it prepares a writable patched copy of the
Microsoft Store Codex app and writes launchers under
`%LOCALAPPDATA%\OpenAI\CodexDesktopPatched`. On macOS, `auto` attempts to patch
the installed `Codex.app` bundle and reports a warning if it is not writable.
Use `always` when patch failure should fail the install, or
`--no-codex-desktop-connection-fast-mode` when the app bundle must not be
touched.

The underlying helper is
`scripts/setup_codex_desktop_connection_fast_mode.py`; the lower-level asar
patcher remains `scripts/patch_codex_desktop_connection_fast_mode.py`. Runtime
truth comes from new-api/sub2api logs and billing rows, not from static config
alone.

## Manual Setup

Edit the config directly:

```bash
${EDITOR:-nano} "${CODEX_HOME:-$HOME/.codex}/config.toml"
```

Ensure the top-level section contains:

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
```

Ensure this provider table exists:

```toml
[model_providers.custom]
name = "OpenAI WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = true
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
```

Ensure the `[features]` table contains the full default feature set:

```toml
[features]
fast_mode = true
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true
```

If older lines exist with different values for the same keys, replace them
instead of adding duplicates. If `[features].codex_hooks` exists, replace it
with `[features].hooks`. If top-level `remote_control` or any
`remote_connections` key exists, remove it and keep only
`[features].remote_control = true`.

## Validate

Check the saved config:

```bash
sed -n '1,40p' "${CODEX_HOME:-$HOME/.codex}/config.toml"
```

Check that Codex can parse the config:

```bash
codex features list >/dev/null && echo "Codex config parses"
```

Check the temporary SQLite log guard:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode status
```

Then open a new Codex conversation. The `/approvals` state should be AutoReview,
not Full Access, and long remote compression/streaming pauses should use the
larger idle timeout. Existing already-open conversations do not automatically
adopt the changed default.

## Daily Use

Default flow:

1. Start Codex normally with `codex`.
2. Keep the default AutoReview mode for routine work.
3. Use `/approvals` only when a session needs manual Full Access.
4. When switching to Full Access, do not choose a "remember this choice" option
   unless the goal is to change the global default.

## Agent Checklist

When asked to apply this on a new server or WSL2 machine:

1. Confirm which Unix user launches Codex.
2. Run `./install.sh` (with appropriate `--root` flags). It writes all eight
   managed top-level keys (`approval_policy`, `sandbox_mode`,
   `approvals_reviewer`, `model`, `model_reasoning_effort`,
   `service_tier`, `stream_idle_timeout_ms`, `stream_max_retries`,
   `model_provider`), the `custom` provider, and the full `[features]` block
   (`fast_mode`, `hooks`,
   `memories`, `goals`, `terminal_resize_reflow`, `remote_control`).
3. If `install.sh` cannot run, use the One-Shot Setup or Manual Setup block
   above to patch `${CODEX_HOME:-$HOME/.codex}/config.toml` directly.
4. Preserve `[projects.*]`, `[mcp_servers.*]`, `[tui]`, `[notice]`, and other
   TOML tables. The installer already does this.
5. Remove top-level `remote_control` and any `remote_connections` key if present.
6. Validate with `codex features list`.
7. Confirm `configure_codex_sqlite_log_guard.py --mode status` reports enabled
   for the target Codex home. On WSL2, include the Windows Codex App home unless
   explicitly disabled.
8. Tell the user that only new Codex sessions pick up the new default.

To deviate from the defaults, set the matching env var before running
`install.sh`:
`CODEX_APPROVAL_POLICY`, `CODEX_SANDBOX_MODE`, `CODEX_APPROVALS_REVIEWER`,
`CODEX_MODEL`, `CODEX_MODEL_REASONING_EFFORT`, `CODEX_SERVICE_TIER`,
`CODEX_STREAM_IDLE_TIMEOUT_MS`, `CODEX_STREAM_MAX_RETRIES`,
`CODEX_MODEL_PROVIDER_ID`, `CODEX_FEATURE_FAST_MODE`, `CODEX_FEATURE_HOOKS`,
`CODEX_FEATURE_MEMORIES`, `CODEX_FEATURE_GOALS`,
`CODEX_FEATURE_TERMINAL_RESIZE_REFLOW`, `CODEX_FEATURE_REMOTE_CONTROL`. Use
`--no-codex-config` to skip the codex patch entirely.

To remove the temporary SQLite log guard after OpenAI fixes the logging issue:

```bash
./install.sh --disable-codex-sqlite-log-guard
```

## Rollback

To return approval requests directly to the user while staying out of Full
Access:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "user"
```

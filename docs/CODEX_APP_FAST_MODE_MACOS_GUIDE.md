# macOS Codex App Fast Mode Setup

This guide is for a teammate who uses Codex App on macOS, local Codex CLI, and
Codex App Connections to SSH hosts.

The target state is:

- macOS local Codex home has Fast enabled in `~/.codex/config.toml`.
- Every SSH host used from Codex App has a recent standalone Codex CLI on PATH.
- Every SSH host's remote Codex home has Fast enabled in its own
  `~/.codex/config.toml`.
- Codex App Connections are restarted after the remote config/CLI changes.

Fast mode starts as Codex config and app-server capability. The installer can
also patch the macOS Codex Desktop bundle so remote Connections preserve
`serviceTier`; use `--no-codex-desktop-connection-fast-mode` on machines where
the app bundle must not be touched. In every case, verify with provider logs.

## Prompt For A Coding Agent

Copy this prompt into the teammate's Coding Agent:

````text
You are configuring Codex Fast Mode for my macOS Codex App, my local Codex CLI,
and every SSH host I use through Codex App Connections.

Use the existing `agent-tools` project if it is available locally. If it is not
available, ask me for the path or archive before inventing a replacement.

Goals:
1. Enable Fast Mode in my local macOS Codex config.
2. Discover the SSH hosts I use from `~/.ssh/config` and/or ask me for the exact
   host list if discovery is ambiguous.
3. For each selected SSH host:
   - Verify SSH works.
   - Check `codex --version`.
   - If Codex CLI is missing, installed with npm, or too old for
     `codex app-server --listen stdio://`, replace it with the latest standalone
     Codex CLI. Do not use npm for Codex CLI installs.
   - Preserve existing `~/.codex/auth.json` and provider/auth settings.
   - Enable Fast Mode in that host's `~/.codex/config.toml`.
   - Verify the config contains top-level `service_tier = "priority"` and
     `[features].fast_mode = true` exactly once.
   - If app-server stdio probing is supported, verify the initialized app-server
     reports ChatGPT auth and Fast-capable model tiers. If stdio probing is not
     supported even after upgrade, report that host separately with exact output.
4. Restart local and remote Codex app-server/Connections processes where safe,
   or tell me exactly what I need to restart in the Codex App UI.

Use these rules:
- Do not patch `/Applications/Codex.app`, `app.asar`, signed app bundles, or
  Electron resources by hand. Use the repo's Desktop Connection Fast Mode
  script or installer route so a backup is kept and patch points are checked.
- Do not overwrite API keys, ChatGPT auth, provider base URLs, or
  `requires_openai_auth = true`.
- Do not expose app-server ports on public networks.
- Prefer Python 3.10+ when running helper scripts. If the default `python3` is
  old, sniff for `python3.13`, `python3.12`, `python3.11`, or `python3.10`.
- Make backups before editing any existing `config.toml`.
- At the end, give me a host-by-host table: host, Codex version, auth mode,
  Fast config status, app-server probe status, and restart status.

Suggested local commands if `agent-tools` is available:

```bash
cd /path/to/agent-tools
python3 scripts/configure_codex_app_fast_mode.py
awk '
  /^service_tier[[:space:]]*=/{service_tier++}
  /^\\[features\\]/{in_features=1; next}
  /^\\[/{in_features=0}
  in_features && /^fast_mode[[:space:]]*=/{fast_mode++}
  END { print "service_tier_count=" service_tier, "fast_mode_count=" fast_mode }
' ~/.codex/config.toml
```

For each SSH host, prefer the same helper after copying or installing
`agent-tools` there:

```bash
cd ~/agent-tools
./install.sh --root "$HOME" --max-depth 2 \
  --codex-proxy-wrapper never \
  --no-codex-remote-control \
  --no-registry \
  --no-cron \
  --no-agent-core
```

If a full install would touch unrelated local defaults, use only:

```bash
python3 scripts/configure_codex_app_fast_mode.py
```
````

## What Fast Mode Needs

Codex reads personal defaults from:

```text
~/.codex/config.toml
```

For Fast Mode, the required config is:

```toml
service_tier = "priority"

[features]
fast_mode = true
```

The same rule applies separately on each machine:

- On the Mac, this config is used by local Codex CLI and the macOS Codex App.
- On an SSH host, this config is used by the remote `codex app-server` that the
  macOS Codex App starts through Connections.

That is why configuring only the Mac is not enough for SSH projects. Every
remote host needs its own Codex CLI, auth, provider config, and Fast setting.

## macOS Local Setup

From the `agent-tools` directory:

```bash
python3 scripts/configure_codex_app_fast_mode.py
```

Or run the full installer for the Mac user:

```bash
./install.sh --root "$HOME/projects" --max-depth 3
```

Use a narrower install if only the Fast config should be patched:

```bash
./install.sh --root "$HOME" --max-depth 1 \
  --no-codex-config \
  --no-codex-here \
  --no-goal-plan \
  --no-cc-switch-update \
  --no-codex-remote-control \
  --no-registry \
  --no-cron \
  --no-agent-core
```

Verify:

```bash
codex --version
grep -nE '^(service_tier|\\[features\\]|fast_mode)' ~/.codex/config.toml
```

Expected:

```toml
service_tier = "priority"

[features]
fast_mode = true
```

## SSH Host Setup

List concrete SSH aliases:

```bash
grep -nE '^Host[[:space:]]+' ~/.ssh/config
```

For each host:

```bash
ssh HOST_ALIAS 'command -v codex || true; codex --version || true'
```

If Codex CLI is missing, npm-installed, or too old, install the latest
standalone Codex CLI on that host. Then make sure the remote login shell can
find it:

```bash
ssh HOST_ALIAS 'command -v codex; codex --version'
```

Copy or unpack `agent-tools` on the host, then run:

```bash
ssh HOST_ALIAS '
  cd ~/agent-tools &&
  ./install.sh --root "$HOME" --max-depth 2 \
    --codex-proxy-wrapper never \
    --no-codex-remote-control \
    --no-registry \
    --no-cron \
    --no-agent-core
'
```

If the host should only receive the Fast config patch:

```bash
ssh HOST_ALIAS '
  cd ~/agent-tools &&
  python3 scripts/configure_codex_app_fast_mode.py
'
```

On older Linux hosts, do not assume `python3` is new enough. Sniff first:

```bash
ssh HOST_ALIAS '
  for py in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$py" >/dev/null 2>&1 || continue
    "$py" - <<'"'"'PY'"'"' >/dev/null 2>&1 && { echo "$py"; exit 0; }
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  done
'
```

## Connections Restart

After remote CLI/config changes, restart the affected Codex App connection:

1. Quit or disconnect the active Codex App thread for that SSH host.
2. In Codex App, open **Settings > Connections**.
3. Disable/re-enable the SSH host, or reconnect the project.
4. Start a fresh thread on that remote project.

If the remote host exposes a managed app-server daemon, restart it on the host:

```bash
ssh HOST_ALIAS 'codex app-server daemon restart || true'
```

Some Codex App Connections start app-server directly through SSH and do not use
a persistent daemon. In that case, reconnecting the host/project from the App is
the restart.

## Verification Checklist

For each environment, record:

| Target | Command | Expected |
| --- | --- | --- |
| Mac | `codex --version` | Recent Codex CLI |
| Mac | `grep -nE '^(service_tier|\\[features\\]|fast_mode)' ~/.codex/config.toml` | `service_tier = "priority"` and `fast_mode = true` |
| SSH host | `ssh HOST 'codex --version'` | Recent standalone Codex CLI |
| SSH host | `ssh HOST 'grep -nE "^(service_tier|\\[features\\]|fast_mode)" ~/.codex/config.toml'` | Fast config present |
| Codex App | New local thread | Model selector/session shows Fast-capable behavior |
| Codex App Connections | New SSH project thread | Provider log shows `service_tier = priority` only when Fast is enabled |

The most common failure pattern is configuring the Mac but not the SSH host.
Codex App Connections use the remote host's `codex` binary and remote
`~/.codex/config.toml`, so each host must be configured independently.
If those are correct but the provider log still shows `service_tier = NULL`, the
Desktop Connection layer may be filtering the tier before it reaches the remote
app-server.

## macOS Desktop Connection Patch

Use this when Codex App Connections need to preserve Fast Mode across SSH
hosts. The normal installer route can do it automatically; these commands are
the direct script route.

Dry-run:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform macos \
  --dry-run
```

Patch:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform macos
```

Equivalent installer route:

```bash
./install.sh --codex-desktop-connection-fast-mode auto
```

After patching, restart Codex App, open a fresh SSH Connection thread, send a
small request, and verify the provider billing log has
`service_tier = priority`. Standard mode should still log as `NULL`.

Use `--codex-desktop-connection-fast-mode always` when patch failure should
fail the install, or `--no-codex-desktop-connection-fast-mode` when the macOS
app bundle must not be modified.

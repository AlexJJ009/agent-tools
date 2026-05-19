# Codex Remote Control Bootstrap

This runbook records the current Linux/WSL2 setup for Codex CLI remote control.
It is based on local `codex-cli 0.131.0` behavior. Treat official docs and old
feature-flag notes as secondary when the local CLI disagrees.

## Runtime Model

Remote control is started through the CLI command path, not through an old
feature flag alone:

```bash
codex remote-control start
codex app-server daemon version
```

On managed installs this starts a persistent app-server process similar to:

```text
~/.codex/packages/standalone/current/codex app-server --remote-control --listen unix://
```

The fixed standalone binary path matters because `codex remote-control start`
uses the standalone install managed by the Codex installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

If a machine only has an npm-installed `codex`, install standalone first for
the managed daemon path. Some npm wrappers may still run `codex remote-control`
in the foreground, but the durable daemon flow is the standalone install plus
`codex remote-control start`.

## Config Keys

Keep current feature keys in the user config:

```toml
[features]
hooks = true
remote_control = true
```

Do not write these stale forms:

```toml
remote_control = true
remote_connections = true
[features]
remote_connections = true
```

In `codex-cli 0.131.0`, `codex features list` shows `remote_control` as a
removed feature entry, so the working path is the command/daemon path above.
The config key is still harmless as a compatibility/default marker, but it is
not sufficient to start remote control.

## Proxy Wrapper

On WSL2, route Codex through the reachable Windows proxy before starting the
daemon. The wrapper belongs at:

```bash
~/.local/bin/codex
```

The wrapper should exec the standalone binary and set proxy variables first:

```bash
REAL_CODEX="${CODEX_REAL_BIN:-${HOME}/.codex/packages/standalone/current/codex}"
CODEX_PROXY_URL="${CODEX_PROXY_URL:-http://127.0.0.1:7897}"

export HTTP_PROXY="$CODEX_PROXY_URL"
export HTTPS_PROXY="$CODEX_PROXY_URL"
export http_proxy="$CODEX_PROXY_URL"
export https_proxy="$CODEX_PROXY_URL"
export WS_PROXY="$CODEX_PROXY_URL"
export WSS_PROXY="$CODEX_PROXY_URL"
export ws_proxy="$CODEX_PROXY_URL"
export wss_proxy="$CODEX_PROXY_URL"
export ALL_PROXY="$CODEX_PROXY_URL"
export all_proxy="$CODEX_PROXY_URL"
export CODEX_NETWORK_PROXY_ACTIVE=1

export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,100.64.0.0/10,.local,beihang.edu.cn}"
export no_proxy="${no_proxy:-$NO_PROXY}"

exec "$REAL_CODEX" "$@"
```

Do not assume every host uses port `7897`. Probe the current host first, or set
the exact proxy URL:

```bash
CODEX_PROXY_URL=http://127.0.0.1:7897 ./install.sh --codex-proxy-wrapper always
CODEX_PROXY_PORTS="7897 7890 7891 10809 10808 8080" ./install.sh --codex-proxy-wrapper auto
```

The installer probes candidate ports against:

```text
https://chatgpt.com/backend-api/codex/responses
```

A healthy route usually returns an API-layer response such as `405 Allow: POST`
instead of a Cloudflare JavaScript challenge.

## Installer

For WSL2 with automatic proxy detection:

```bash
cd ~/agent-tools
./install.sh --root ~/projects --codex-proxy-wrapper auto
```

For a known proxy port:

```bash
CODEX_PROXY_URL=http://127.0.0.1:7897 ./install.sh --root ~/projects --codex-proxy-wrapper always
```

For a normal Linux server with no local proxy:

```bash
./install.sh --root /data-1 --codex-proxy-wrapper never
```

The installer patches Codex config, optionally installs the proxy wrapper, and
by default runs:

```bash
codex remote-control start
```

Use `--no-codex-remote-control` if the machine should be configured but not
start the daemon yet.

## Validate

Check daemon state:

```bash
codex remote-control start
codex app-server daemon version
pgrep -a -u "$USER" -f 'codex (app-server|remote-control)'
```

On WSL2, confirm the app-server process inherited the proxy variables:

```bash
tr '\0' '\n' < /proc/<app-server-pid>/environ \
  | grep -Ei '^(HTTP_PROXY|HTTPS_PROXY|WS_PROXY|WSS_PROXY|ALL_PROXY|CODEX_NETWORK_PROXY_ACTIVE)='
```

Run the local diagnostic:

```bash
codex doctor --summary --ascii
```

Existing Codex sessions and already-running app-server processes do not pick up
wrapper or config changes. Restart remote control after wrapper changes:

```bash
codex app-server daemon restart
```

If rerunning the standalone installer replaces `~/.local/bin/codex` with a
symlink to the standalone binary, rerun `agent-tools/install.sh` to restore the
proxy wrapper.

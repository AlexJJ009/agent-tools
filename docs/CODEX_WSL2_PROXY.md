# Codex WSL2 Proxy Wrapper

This runbook documents a machine-specific Codex network workaround for WSL2.
It is not a general Codex default for Linux, macOS, or native Windows.

## Scope

Use this only when all of the following are true:

- Codex CLI is launched inside WSL2.
- Windows v2rayN exposes an HTTP proxy that is reachable from the WSL2 distro.
  On this machine it has often been `127.0.0.1:7897`, but other WSL hosts or
  servers may use a different port.
- WSL2 traffic otherwise falls through the host TUN/fake-IP path and Codex
  remote requests show intermittent connection resets or timeouts.

Do not install this wrapper on ordinary Linux servers, macOS, or native Windows
Codex installs unless that machine has the same WSL2-to-Windows proxy topology
or an explicitly verified local proxy.

## Probe The Proxy Port

Do not hard-code `7897` on a new host. First test the actual proxy ingress:

```bash
curl -I --max-time 10 \
  -x http://127.0.0.1:7897 \
  https://chatgpt.com/backend-api/codex/responses
```

Try the host's candidate ports until one returns an API-layer response such as
`405 Allow: POST` instead of a Cloudflare JavaScript challenge or a connection
failure. Common candidates are:

```text
7897 7890 7891 10809 10808 8080
```

The installer can do this probe automatically:

```bash
CODEX_PROXY_PORTS="7897 7890 7891 10809 10808 8080" ./install.sh --codex-proxy-wrapper auto
```

When the port is known, make it explicit:

```bash
CODEX_PROXY_URL=http://127.0.0.1:7897 ./install.sh --codex-proxy-wrapper always
```

## Target State

Codex should be launched through a wrapper earlier in `PATH`, typically:

```bash
${HOME}/.local/bin/codex
```

The wrapper sets proxy environment variables before starting the real Codex
binary:

```bash
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
```

Keep `NO_PROXY` for local and Tailscale addresses:

```bash
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,100.64.0.0/10,.local,beihang.edu.cn}"
export no_proxy="${no_proxy:-$NO_PROXY}"
```

## Bash Startup Guard

If `fnm` or shell command hashing can bypass `${HOME}/.local/bin/codex`, add a
shell function after `fnm env` in `${HOME}/.bashrc`:

```bash
codex() {
  command "${HOME}/.local/bin/codex" "$@"
}
```

After changing this, reload the shell before starting Codex:

```bash
source ~/.bashrc
hash -r
codex
```

## Validate

Find the running Codex processes:

```bash
pgrep -a -u "$USER" -f 'codex|node'
```

Then confirm the Node wrapper process and native Codex process both inherited
the proxy environment:

```bash
tr '\0' '\n' < /proc/<pid>/environ | rg -i '^(HTTP_PROXY|HTTPS_PROXY|WS_PROXY|WSS_PROXY|ALL_PROXY|CODEX_NETWORK_PROXY_ACTIVE)='
```

Expected values include:

```text
HTTP_PROXY=http://127.0.0.1:7897
HTTPS_PROXY=http://127.0.0.1:7897
WS_PROXY=http://127.0.0.1:7897
WSS_PROXY=http://127.0.0.1:7897
CODEX_NETWORK_PROXY_ACTIVE=1
```

Existing Codex sessions do not pick up wrapper changes. Restart Codex after
editing the wrapper or shell startup files.

For remote-control specific setup, standalone binary behavior, and daemon
validation, see `docs/CODEX_REMOTE_CONTROL.md`.

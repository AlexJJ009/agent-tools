# Project Constraints

- Linux and WSL2 machine bootstrap must persist tmux mouse mode for the Unix
  user running the tools. The durable config is a managed block in
  `${HOME}/.tmux.conf` containing `set -g mouse on`. Do not replace this with
  terminal-only scrollbar guidance; tmux scrolling must work through tmux mouse
  mode.
- The Codex proxy wrapper is a WSL2-only workaround for this machine topology:
  WSL2 Codex reaches the Windows v2rayN HTTP proxy while the default TUN/fake-IP
  path is unstable. Do not hard-code `127.0.0.1:7897` as a universal default;
  probe the current host's proxy port first, or set `CODEX_PROXY_URL` /
  `CODEX_PROXY_PORTS` explicitly. Do not apply this as a normal Linux, macOS,
  or native Windows default. See `docs/CODEX_WSL2_PROXY.md`.
- Codex default config should include `stream_idle_timeout_ms = 900000` and
  `stream_max_retries = 20` to tolerate long compression pauses and transient
  SSE streaming disconnects. It should also use the `openai-no-ws` custom
  provider with `supports_websockets = false`, `requires_openai_auth = true`,
  and `base_url = "https://chatgpt.com/backend-api/codex"` because this WSL2
  proxy path can fail during Responses WebSocket TLS handshakes while HTTPS
  requests still work. These stream/provider defaults are independent of the
  approval reviewer; do not overwrite an existing `approvals_reviewer` value
  unless the user explicitly asks for approval-mode changes. See
  `docs/CODEX_AUTOREVIEW_DEFAULT.md`.

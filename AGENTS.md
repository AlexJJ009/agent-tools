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
- Codex default config should include `stream_idle_timeout_ms = 1800000` and
  `stream_max_retries = 20` to tolerate long compression pauses and transient
  streaming disconnects. It should also use the `custom` model provider with
  `supports_websockets = true`, `requires_openai_auth = true`, and
  `base_url = "https://chatgpt.com/backend-api/codex"`. All generated Codex and
  cc-switch provider configurations must keep WebSocket transport enabled.
  These stream/provider defaults are independent of the
  approval reviewer; do not overwrite an existing `approvals_reviewer` value
  unless the user explicitly asks for approval-mode changes. See
  `docs/CODEX_AUTOREVIEW_DEFAULT.md`.
- For repeat Linux server deployment of Codex CLI, Claude Code, GitHub CLI,
  `cc-switch-cli`, `ripgrep`, and Codex API providers, use
  `docs/CLI_SERVER_BOOTSTRAP.md`. Never store real GitHub PATs or provider API
  keys in repo files; the runbook should keep keys on the target machine with
  `0600` permissions and accept fresh keys/Base URLs per server. For that
  custom-provider path, keep all Codex live and cc-switch provider templates on
  `model_provider = "custom"` / `[model_providers.custom]` so provider
  switching does not fragment Codex resume history. Keep stream timeout/retry
  keys inside `[model_providers.custom]`; do not add them as top-level keys if
  the current standalone Codex CLI rejects them under `--strict-config`.
- Linux server installs must check `fail2ban` for SSH protection. If `fail2ban`
  is missing and a supported package manager is available, install it. The
  managed sshd jail should be strict by default: aggressive sshd filter,
  `maxretry = 3`, `findtime = 1h`, `bantime = -1`, DROP bans, and loopback-only
  `ignoreip` (`127.0.0.1/8 ::1`). Do not guess or add trusted public IPs to
  `ignoreip`; only the operator should decide external allowlists.

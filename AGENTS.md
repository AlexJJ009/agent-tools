# Project Constraints

- Linux and WSL2 machine bootstrap must persist tmux mouse mode for the Unix
  user running the tools. The durable config is a managed block in
  `${HOME}/.tmux.conf` containing `set -g mouse on`. Do not replace this with
  terminal-only scrollbar guidance; tmux scrolling must work through tmux mouse
  mode.
- The Codex proxy wrapper that routes Codex through
  `http://127.0.0.1:7897` is a WSL2-only workaround for this machine topology:
  WSL2 Codex reaches the Windows v2rayN HTTP proxy while the default TUN/fake-IP
  path is unstable. Do not apply it as a normal Linux, macOS, or native Windows
  default. See `docs/CODEX_WSL2_PROXY.md`.
- Codex default config should include `stream_idle_timeout_ms = 900000` to
  tolerate long compression or streaming idle periods. This timeout default is
  independent of the approval reviewer; do not overwrite an existing
  `approvals_reviewer` value unless the user explicitly asks for approval-mode
  changes. See `docs/CODEX_AUTOREVIEW_DEFAULT.md`.

# Project Constraints

- Linear Workflow Delivery uses the shared contract under `linear_workflow/shared/`.
  Only an explicitly dispatched Ready Batch authorizes implementation; Project
  context does not expand scope. Follow `.linear-workflow.yml` and the
  repo-resident reviewer brief, and retain human merge authority.

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
- Native Win11 Codex App installs use the local custom bearer-token mode, not
  the Linux/WSL `auth.OPENAI_API_KEY` provider mode and not the official
  subscription backend. Keep history in the stable `custom` bucket. Write
  `OPENAI_API_KEY = null` and `auth_mode = "chatgpt"` plus placeholder tokens in
  `auth.json`; write the live credential as `experimental_bearer_token` in both
  top-level `config.toml` and `[model_providers.custom]`; set
  `base_url = "http://15.204.46.107:8080"`, `requires_openai_auth = true`,
  `supports_websockets = true`, and `wire_api = "responses"`. Keep cc-switch's
  current Codex provider on this same custom bearer-token provider so
  reinstalling agent-tools or CC Switch cannot overwrite the working Win11
  config with an unusable official/empty provider. Use `scripts/install-win11.ps1`
  for this path. Never run the Win11 configurator against a Linux/WSL
  `~/.codex`; Win11 `CODEX_HOME`, `USERPROFILE`, and the CC Switch DB must all
  resolve to the same native Windows profile.
- Before any Agent Tools installer, Skill deployment, or Codex/CC Switch
  configuration helper writes state, run `scripts/codex_target_guard.py` on
  the target platform. It binds `.codex` and `.cc-switch/cc-switch.db` to one
  profile and rejects Windows paths in Linux/WSL config and WSL paths in native
  Win11 config. Fleet dispatch must use `scripts/codex_fleet_guard.py` with a
  checked manifest and batch SSH only (`BatchMode=yes`, `RequestTTY=no`): never
  use a Linux/WSL `cc-switch` binary to mutate a Windows profile or emulate an
  interactive CC Switch form through SSH. WSL install defaults must not copy
  Skills/plugins or mutate Codex config under `/mnt/c`; run
  `scripts/install-win11.ps1` natively for Win11 state.
- Linux server installs must check `fail2ban` for SSH protection. If `fail2ban`
  is missing and a supported package manager is available, install it. The
  managed sshd jail should be strict by default: aggressive sshd filter,
  `maxretry = 3`, `findtime = 1h`, `bantime = -1`, DROP bans, and loopback-only
  `ignoreip` (`127.0.0.1/8 ::1`). Do not guess or add trusted public IPs to
  `ignoreip`; only the operator should decide external allowlists.
- Never shrink an existing `ignoreip`. fail2ban resolves it by replacement, not
  union, so rewriting the managed jail file with the default would silently
  un-whitelist every address the operator had already trusted — and with
  `bantime = -1` those peers stay locked out. The installer merges the
  requested value with the managed file's current value and the live effective
  list, so a reinstall can only ever grow the allowlist. This is not a
  contradiction of the rule above: the installer still contributes no addresses
  of its own, it only refuses to discard the operator's.

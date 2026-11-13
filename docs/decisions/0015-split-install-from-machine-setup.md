# Split the install from machine setup

Date: 2026-11-13

Status: Accepted

## Context and Problem Statement

`scripts/install.sh` does two jobs in one 2,400-line script. It installs Agent
Tools: it copies the tree, links skills, installs `agent-wt` and `ci-watch`,
puts the launchers on `PATH` and writes the Claude Code context. It also
configures the machine: Codex `config.toml` defaults and features, Codex
provider authentication, the proxy wrapper and remote control, `codex-here`,
cc-switch updates and provider templates, fail2ban, tmux mouse mode, and the
Claude Desktop SSH shim. All of this machine configuration runs by default, so
re-installing Agent Tools on a machine that is already set up takes eight
`--no-*` flags. The help text alone is 330 lines.

## Decision Outcome

`scripts/install.sh` installs Agent Tools and nothing else. Machine setup moves
to separate scripts that the user runs explicitly:

* `scripts/setup/codex.sh`: Codex config defaults and features, project hook
  features, provider authentication, the proxy wrapper, `codex-here`, remote
  control, and the Fast mode check.
* `scripts/setup/cc-switch.sh`: the cc-switch-cli update, provider template
  normalization, and syncing Codex config from the current provider.
* `scripts/setup/host.sh`: fail2ban hardening, tmux mouse mode, and the Claude
  Desktop SSH shim.

Each script has its own short usage text and runs only what it is asked to
do. Bootstrap scripts that set up a new machine (`bootstrap_autodl_ai_tools.sh`,
`install-win11.ps1`) call the install and then the setup scripts they need.
The no-op flags kept for ADR 0012 are removed.

### Consequences

* Good, because a reinstall needs no flags, and each piece of machine
  configuration can be read, run and tested on its own.
* Bad, because running `install.sh` by itself no longer configures Codex,
  cc-switch or the host; a new machine needs the bootstrap script or the
  setup scripts.
* Neutral: the scripts stay in Bash. Moving argument parsing to Python would
  remove the duplication between `usage()` and the parser, and is left for a
  later change.

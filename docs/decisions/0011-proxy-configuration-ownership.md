# Keep Machine Proxy Configuration in Dedicated Repositories

Date: 2026-10-04

Status: Accepted

## Context and Problem Statement

Win11 proxy configuration had accumulated custom templates, selectors,
failover tasks and a reverse SSH relay from PHAI. The user found that stack
inconsistent and hard to operate. Its configuration and cleanup were mixed
with Agent Tools platform installation, obscuring which repository maintained
the live network behavior.

The resumed proxy work selected native v2rayN controls for Win11 and mihomo
for PHAI, with each machine's configuration and verification recorded in its
own repository.

## Decision Outcome

`win11-v2rayn` owns the Win11 native v2rayN configuration and its maintenance
scripts. `server-proxy-config` owns PHAI mihomo configuration, exported file
providers and community routing rules. Their ADRs record the respective
architecture and limitations of observed verification.

Agent Tools no longer ships `tools/win11-proxy-relay`. The old Win11 relay,
PHAI reverse SSH dependency, BWG/OVH selectors and associated custom failover
machinery are retired. Current proxy maintenance uses the dedicated repositories
rather than rebuilding those components here.

General platform installation and the WSL2 Codex proxy wrapper remain Agent
Tools responsibilities. That wrapper is a host-specific way for WSL Codex to
reach the Windows proxy; it does not own v2rayN routing or PHAI egress policy.

### Consequences

- Proxy configuration has an explicit owner and can use the native tools the
  operator sees and controls.
- Agent Tools retains reusable installation helpers without maintaining the
  removed relay stack.
- Old source remains in Git history; stale deployed copies need separate,
  target-specific cleanup.
- README and ADR updates describe ownership and decisions. They do not prove
  installation, leak-test success or full browser validation on any machine.

# Remove one-off installer machinery and context sync

Date: 2026-11-13

Status: Accepted; amends the "kept" list of [0012](0012-retire-workflow-runtime.md)

## Context and Problem Statement

`install.sh` and its helpers still carried code whose job was finished or no
longer wanted: the Codex provider-bucket migration (1859 lines), the cleanup of
packages retired by 0006 and 0012, the context sync that generated mirrored
`AGENTS.md` / `CLAUDE.md` files (the user removed those mirrors as unused), the
generated copy of the writing contract, and change-based test-suite selection.
Each kept its own flags, tests and documentation.

## Decision Outcome

Remove them. `CLAUDE.md` imports `AGENTS.md` instead of mirroring it;
academic-writing relies on the contract loaded through the client context; CI
runs every active suite on each change. Their flags are now rejected as unknown
arguments. Git history before this record holds the removed code.

### Consequences

* Good, because the installer and test suite shrink by about 4,700 lines and no
  longer maintain migrations that already ran.
* Bad, because a machine that never ran the provider migration or the retired
  package cleanup must do so from an older release, and files left by context
  sync on existing machines are not removed automatically.

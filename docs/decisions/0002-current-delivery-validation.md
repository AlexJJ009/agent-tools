# Validate Current Bound Teaching Deliveries

Date: 2026-09-29

Status: Accepted

## Context and Problem Statement

The previous teaching Stop wrapper scanned transcript paths. Reading an old
teaching template or an unrelated malformed artifact could therefore block an
ordinary reply. Markdown-fence filtering did not fix ownership: tab-indented
examples and old artifacts still reproduced the false positive. The inspected
ReadPapers configuration also registered the same legacy check in both
`hooks.json` and `config.toml`.

The existing learning runtime already binds an actual session and workspace to
a route with explicit output targets and a revision. Main supplies semantic
activity and scope from the user request and continuing agreement. A Hook can
consume that decision without inferring obligations from source text.

## Considered Options

- Continue expanding Markdown/transcript heuristics.
- Disable teaching validation.
- Validate explicitly bound applicable outputs and retire duplicate legacy
  registrations through the existing installer.

## Decision Outcome

Choose explicit current-delivery binding. `bind --teaching-artifact` registers
applicable legacy v1 teaching targets already declared in `output_targets`.
Stop checks their current route revision, and the existing validator still
rejects missing or malformed required artifacts. Ordinary conversation,
historical references and portable learning notes do not inherit a v1 manifest
contract. Reclassification requires an intentional renewed delivery binding.
The separate `--on-stop` missing-output/pending-input check retains its role.

The learning installer normalizes the inspected legacy teaching registrations
in user and explicitly selected project JSON/TOML settings, preserving foreign
handlers and reversible state. The unified learning Hook performs validation
once. Unsupported TOML layouts fail before writes; configuration is not proof
that the host trusts or has executed the Hook.

Main-led routing also preserves capability ownership: reusable learning and
writing methods belong at user scope; ReadPapers library operations and adapter
configuration remain project-owned. Reading source code or paper prose during
development does not authorize teaching or library writes.

### Consequences

- Historical templates no longer create unrelated Stop obligations while real
  broken applicable deliveries remain detectable.
- Main must bind the actual requested target. A missing binding is repaired for
  that target, not recovered by scanning history for a substitute.
- The Hook is a bounded workflow aid, not a universal tool sandbox or a semantic
  classifier. A stale teaching binding alone does not validate a new delivery.
- Legacy bindings/configurations are migrated only in explicitly selected
  profiles. This repository change does not claim remote or native Windows
  deployment, universal host coverage, or validation of Slime training.

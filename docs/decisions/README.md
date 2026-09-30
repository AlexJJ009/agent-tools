# Architecture Decisions

ADRs explain significant adopted choices and their consequences. Current usage
belongs in [system documentation](../README.md); task recovery and verification
records remain local. A private report is not required to understand a decision.

Start from [template.md](template.md), the **MADR 4.0.0 minimal template** from
[upstream](https://github.com/adr/madr/blob/4.0.0/template/adr-template-minimal.md).
It is retained verbatim, with upstream's [license declaration](MADR-LICENSE)
(`MIT OR CC0-1.0`); the [MIT license text](MADR-LICENSE-MIT) is included. Our records add `Date`, `Status` and explicit applicability;
retain the template's Consequences section. No ADR tool or generated index is
required.

## When a decision needs a record

Keep an ADR for a durable choice about state ownership, component responsibilities,
cross-component contracts or a costly-to-reverse dependency. Its rationale and
trade-offs should help a future maintainer choose safely when code and usage
instructions alone do not explain why the boundary exists. Importance, not the
number of PRs or changed files, determines whether a record is needed.

Routine fixes, test cases, CI selection, installation options, cleanup runs and
release results belong in code, guides or PRs. They need neither an ADR nor a
mandatory "no ADR change" statement. Such work needs an ADR only if it actually
changes one of the architectural choices above. Do not create an ADR to enforce
ADR maintenance.

Use `NNNN-short-title.md` and an English title. For a genuine reversal of an
accepted architectural choice, retain its rationale and link a successor with
`Supersedes`/`Superseded by`. Clarifications and operational details do not require
successors. Redundant records on the same topic may be consolidated: preserve
material rationale and trade-offs, repair current links, and retain the original
text in Git history rather than a duplicate archive. Keep surviving identifiers;
do not renumber records or reuse retired numbers. Authorization comes from the
task, not from writing an ADR. Record actual decisions, not invented alternatives.

## Current records

- [Current delivery scope for teaching validation](0002-current-delivery-validation.md)
- [One reader-facing writing contract](0003-reader-facing-writing.md)
- [Task state, application storage and process-material retirement](0004-task-runtime-application-storage.md)
- [Retire Linear Workflow while preserving its source](0006-retire-linear-workflow.md)
- [One learning workflow with domain-specific methods](0009-learning-domain-ownership.md)

The 2026-09-30 consolidation folded 0001 and 0005 into 0004. Operational content
from 0007 and 0008 remains in component guides and CONTRIBUTING; the applicable
legacy/current workflow distinction is retained in 0006. Original records are
available in Git history before this consolidation, not a second maintained set.

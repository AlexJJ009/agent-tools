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

Use `NNNN-short-title.md` and an English title. Drafts may change. For a
substantive replacement of an accepted decision, create a successor and link
both records with `Supersedes`/`Superseded by`; preserve the original rationale.
Fixing a typo or link needs no successor. Record only actual decisions and
known alternatives; label unknown history. Authorization comes from the task,
not from creating an ADR. A small change need not create or rewrite any ADR.

- [Local development records and maintained system docs](0001-local-development-records.md)
- [Current delivery scope for teaching validation](0002-current-delivery-validation.md)
- [One reader-facing writing contract](0003-reader-facing-writing.md)
- [Task Runtime application storage and owned-artifact closeout](0004-task-runtime-application-storage.md)
- [Scoped process-material retirement](0005-scoped-process-material-retirement.md)

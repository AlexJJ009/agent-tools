# Share Expression Principles Without Sharing Report Obligations

Date: 2026-09-29

Status: Accepted

## Context and Problem Statement

A status list can state that CPU tests passed while hiding the fact that the
required end-to-end operation failed. Readers need the problem, observations,
inference and practical limits, not merely headings and links. At the same time,
a short explanation should not acquire a formal report template or teaching
manifest merely because it shares writing principles.

Academic Writing provides draft, revision and argument-review methods. Work
Report already owns content selection, six semantic sections, reporting timing
and report review. The user chose to reuse expression methods without merging
these separate responsibilities.

## Considered Options

- Maintain separate expression rules in each skill.
- Reuse one expression contract with generated independent-package copies.
- Make all reader-facing output use the full report or manuscript workflow.

## Decision Outcome

Maintain expression principles at
[`shared/writing/reader-facing-contract.md`](../../shared/writing/reader-facing-contract.md).
Academic Writing contributes `reader model`, `claim–evidence–warrant`, reverse
outlining and genre-sensitive progression. Work Report continues to decide
what a requested report contains and when it is due. Manuscript structures,
CARS, teaching exercises and independent report Judges apply only to their
respective requested activities.

The existing sync command generates matching Work Report, reviewer-brief and
Academic Writing copies; installers detect missing or drifting copies. The
learning installer adds a short user-level Codex AGENTS entry with the actual
installed contract path. When the old AGENTS file is a symlink, the installer
materializes its text for Codex instead of editing the shared adapter target;
rollback restores the original link if the view is otherwise unchanged.

### Consequences

- Each package has a readable contract without requiring a sibling skill
  installation. Maintainers edit one source and regenerate copies.
- Short answers can remain short. A reader should still be able to recover the
  problem, supporting observation and consequence from the prose itself.
- Materializing a Codex AGENTS view means subsequent edits to its old adapter
  source do not automatically propagate until deliberately reconciled. The
  original source is preserved; rollback retains later user edits.
- Structural checks do not prove readability or future model behavior. Cold
  reading and source verification assess actual outputs; limited examples are
  not evidence of a general error-rate or token-cost improvement.

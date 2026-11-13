# Retire evidence-anchor and the ReadPapers v1 teaching material

Date: 2026-11-13

Status: Accepted

## Context and Problem Statement

ADR 0012 kept seven learning and writing skills. A prompt audit on 2026-11-13
checked how they were used. Codex opened `evidence-anchor` in 23 sessions
between 2026-11-05 and 2026-11-13, Claude never did, and the only trace in any
deliverable was one paragraph labelling evidence `source_fact/runtime_fact`.
Separating verified observations from inference is already required by the
user's global instructions and by the reader-facing contract (W3, W8).

`teaching-reconstruction` also carried the frozen v1 ReadPapers artifact
contract, its validator, two templates, an Obsidian vault pre-commit hook and
30 test fixtures. Paper library work lives in the ReadPapers tooling
repository, which does not call this validator; every skill still pointed
readers at the v1 contract.

## Considered Options

* Keep both and leave them unused
* Remove evidence-anchor and the ReadPapers v1 material

## Decision Outcome

Chosen option: "Remove evidence-anchor and the ReadPapers v1 material".

Removed: `skills/evidence-anchor`; from `teaching-reconstruction` the v1
artifact contract, the v1 delivery guide, the ReadPapers adapter note, the
compatibility pointer, the templates, the vault assets and
`validate_teaching_artifact.py`; their tests and fixtures; ReadPapers routing
text in `task-routing` and `teaching-reconstruction`. Durable learning records
use `portable-learning-record.md`. `install_skills.py` lists evidence-anchor as
retired, so a reinstall removes its discovery links.

### Consequences

* Good, because every session that lists or loads these skills reads less text,
  and none of it points at a contract no consumer uses.
* Bad, because a learner record in the v1 format can no longer be validated
  here; Git history before this record holds the validator.

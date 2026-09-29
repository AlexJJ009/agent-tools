# Bounded post-baseline maintainability review

**No production cleanup change warranted; no new actionable maintainability finding.** Independent reviewer `/root/learning_code_review`, applying the `cleaner` no-change workflow. Scope is actual production deltas from the earlier cleaner candidate `ea8a82294f59944c3057e48e221bc0b7c2f0863a` through `602b528b2ade668dd736ee01ffccf2dd7b93b3ad`. Requested model/effort: `gpt-6-astra` high; actual backend identity unavailable.

## Inspected scope and rationale

- Runtime and CLI: project-scope validation is centralized and reused at init/classify/explicit validation/dependent action boundaries. Safe `show` and ordinary read intentionally remain available for recovery. The library action's additional adapter/authorization checks have a distinct purpose from validating a declaration; removing them as apparent duplication would weaken behavior. Default skill roots are computed once per check, including the project `.agents` root, while explicit nonempty roots preserve override semantics. Equivalent `task.md` recognition stays in the existing canonical-directory branch and does not introduce a second development parser or authority model.
- Task routing: the later paragraphs add separate missing rules for scratch scope, canonical-directory reference, actual stage transitions/reference refresh, in-record recovery, capability-owner availability and outside-project handoff. They share some boundary reminders but do not maintain competing classifiers or separate canonical state. Grouping these independent cases into a generic abstraction or aggressively shortening their explicit constraints would change prompt behavior and invalidate evidence without a demonstrated maintainability benefit. The long CLI paragraph is an existing readability limitation, not a demonstrated defect requiring a new rewrite in this bounded pass.
- ReadPapers adapter and evidence anchors: the adapter repeats the outside-project boundary because it can be invoked independently; the router owns selection and handoff. The evidence reference now distinguishes legacy Zotero manifests from supplied immutable evidence without altering the legacy validator. This is deliberate entrypoint coverage rather than a second source of experimental authority.
- Artifact compiler: the new recipe correctly assigns export/index mechanics to the existing `curate` entry and distinguishes actual note/index content from `inspect-index` status. It links to the router/CLI rather than copying argument/schema definitions. It preserves project identity, unrelated index entries, relocation limits and separate publication/library scope. No new storage abstraction or synchronization service is introduced.

The installer, rollback machinery, Hook handler, shared writing copies and legacy validator have no production delta in this inspected interval. Their earlier reviews remain scoped evidence. No dead branch, hidden write, duplicate mutable authority record or dependency-direction change was found that justifies a refactor here. Product files were left unchanged; concurrently edited implementation/human-review records were not modified.

## Validation and acceptance limits

The scoped cumulative `git diff --check` passes. Existing independent delta reviews already cover these exact changes, including the latest unchanged runtime's 17 passing tests and record/scope probes. This no-change maintainability review introduces no behavior that needs another test or inflated test count. It supports the cleanup portion of AC-19 and invalidates no prior component evidence.

Native actor failures remain separate: original scratch writes, missing capability disclosure, stage/reference errors and inaccurate serialization suggestions are not erased by maintainability or source-consistency verdicts. Focused replacement runs and source-reviewed artifact corrections must be judged on their actual traces; user feedback remains independently pending. No full PRD completion, deployment or merge authorization follows.

## Changed production-file bindings

| File | SHA-256 |
|---|---|
| `learning_workflow/__main__.py` | `d5a0e120a583059e7ade7921e9dc5df06c152dddb9ce35c9e45339bc5045de7a` |
| `learning_workflow/runtime.py` | `645a48c02fcada17dff72ffdef40854d46967b2000bbff80f54e61865bd7b790` |
| `project_adapters/read_papers/read-paper/SKILL.md` | `7418cf784239d5fdcda327ca52c9df41d28703fcad011ddc97664cb516e07e9d` |
| `skills/evidence-anchor/references/evidence-anchors.md` | `41231452f8339c55f471fdb6fe4c20021ea8bc5963cbf57071d87e9eebdc2b14` |
| `skills/learning-artifact-compiler/SKILL.md` | `4d010c6a09fe8d6923421c9afe1d0d8776619723de2f06be265edb1fe60507eb` |
| `skills/task-routing/SKILL.md` | `d2fd82a2003d8531140bfd1a2601f7d19ce9267a20dc5fdd69292efdf336705a` |

Reviewed UTC: 2026-09-24T12:49:46.627826+00:00

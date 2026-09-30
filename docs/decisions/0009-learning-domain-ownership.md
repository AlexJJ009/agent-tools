# One Learning Workflow with Domain-Specific Methods

Date: 2026-09-30

Status: Accepted for source implementation; installed-profile cutover is separate.

## Context and Problem Statement

Agent Core's `knowledge-deposition-doc` combined code investigation, teaching,
Markdown production, fixed exercise categories, and mandatory document review.
Agent Tools already separates routing, teaching, writing, and practice. Loading
both can turn a development investigation into a course, or impose two different
exercise and delivery rules.

The user chose Agent Tools to own learning methods and Main to select the
activity, with Core supplying user context. They also clarified that a complete
first draft is useful even when only a quarter or third is read before feedback;
iteration need not consist of tiny units. Each learning session should focus
retention on up to three abilities, rather than always one.

## Considered Options

- Keep both all-in-one and modular workflows active.
- Move the old workflow wholesale into Agent Tools, retaining duplicate rules.
- Consolidate ownership while preserving domain methods and a compatibility name.

## Decision Outcome

Consolidate under Agent Tools. `teaching-reconstruction` owns learning
orchestration; its code/architecture reference covers task decomposition,
decoupling, responsibility, control flow, and engineering trade-offs. ReadPapers
retains paper questions and library/note ownership. `retrieval-practice` owns
domain-specific exercises, observed attempts, and follow-up conventions.
`learning-artifact-compiler` writes or revises requested standalone learning
material from inspected sources or existing state, without requiring completed
practice first. All use the existing shared expression contract.

Preserve `knowledge-deposition-doc` only as a compatibility entry. Its Codex
installation replaces the exact old alias rather than exposing two copies.
Core's installer must stop reclaiming that entry. This learning migration does
not relocate the unrelated `wxpusher-notify` skill or change library ownership.

Full materials and feedback-driven iteration coexist. The up-to-three focus
applies to retained abilities, not chapter count or a mandatory exercise mixture.
Material review, reading progress, practice observations, and retention choices
are distinct; none can stand in for the others. Old learning-loop designs inform
these conventions but do not authorize migrating user records or imply working
background reminders.

### Consequences

- Domain methods can improve without maintaining another general teaching or
  writing workflow. Existing skill invocations retain a discoverable route.
- A user can request a full first draft, read selectively, and revise it before
  practicing. Untested abilities remain untested even after document review.
- Existing profiles need a deliberate guarded cutover; source changes alone do
  not retire an installed Core link. Claude/native Win11 deployment remains
  outside the Linux/WSL Codex learning installer.
- Review follow-through still depends on actual interaction and an authorized
  scheduling capability. No scheduler, automatic answer capture, or learner
  mastery assessment is added by changing skill instructions.

# Migration implementation and acceptance

The implementation candidate is `602b528b2ade668dd736ee01ffccf2dd7b93b3ad`.
The initial candidate `ea8a82294f59944c3057e48e221bc0b7c2f0863a` passed code review;
native T16 subsequently exposed incorrect outside-project handoff guidance,
which is now corrected and has passed [independent delta review](reviews/implementation-review-boundary.md).
Native T18 then exposed missing project-local skill discovery and duplicate
recovery records; the correction passed [independent discovery review](reviews/implementation-review-project-discovery.md).
A later mixed-task trial exposed rejection of project-owned `task.md` records; the narrow compatibility correction passed [independent review](reviews/implementation-review-equivalent-record.md). Missing-capability owners have [bounded prompt review](reviews/implementation-review-capability-owners.md), and native T28-41 now discloses the missing skill in user-facing commentary. Explicit stage-transition bookkeeping has [bounded review](reviews/implementation-review-stage-transitions.md); T12-41 records delivery → learning → delivery and refreshes the canonical task reference to revision 2. The final [scratch-scope guidance](reviews/implementation-review-scratch-scope.md) has source review and three scope-compliant native trials. All three trial notes needed a content correction; each was corrected in its original session, re-curated and independently reviewed. Original first-pass failures remain recorded. Initial code, installer and maintained-prompt review passed; the finite native campaign has ended. Full PRD acceptance and live activation still require real user feedback. No production library or live skill links have been migrated. See the [acceptance summary](ACCEPTANCE.md) for the final criterion mapping and remaining user-feedback requirement.

## Delivered behavior

- Main-led semantic decisions replace the old keyword router's authority.
  The old importable entry now requests a semantic decision instead of starting
  teaching from words such as `check` or `citation`.
- `learning_workflow` supplies small route records, snapshot/readback,
  optimistic concurrency, idempotent inputs, session/workspace bindings,
  explicit scope checks and guarded artifact curation.
- `academic-writing` supports direct drafting, revision and argument review,
  while the existing teaching suite retains guided reconstruction and practice.
- ReadPapers owns its project adapter. Existing v1 teaching data and the Zotero
  resolver are retained without bulk rewriting or managed-region mutation.
- One W1–W9 source serves generated packages without imposing Work Report's
  format on teaching or manuscripts.
- A scoped local installer copies the candidate independently of its checkout,
  migrates explicitly recognized aliases, preserves unrelated configuration,
  and supports rollback. It does not change providers, credentials or fleets.

See [runtime](RUNTIME.md) and [installation](INSTALL.md) contracts for actual
commands and coverage limits.

## Observed evidence

| Check | Current result and boundary |
|---|---|
| Focused unit and affected regressions | 152 tests passed in 10.123 seconds on the current runtime source (7a6198b); later changes only refine task-routing guidance. Tests include failures and recovery; a disposable mutation disabling the pending-input guard made its tests fail, and project skill discovery was reproduced failing before its fix. |
| Independent implementation review | Three rounds, six defects fixed, final round dry; [reviewer-authored verdict](reviews/implementation-review.md) binds the code SHA. This does not certify all native scenarios. |
| Installer | Isolated profile/source-relocation/rollback trial passed; foreign/new Hook entries and original adapter bytes preserved. Failures during link creation, copying and manifest publication were injected. T25-21 additionally completed genuine teaching and writing after source relocation, using its copied 272a782 payload; later prompt-only changes are separate source deltas. Its isolated installation has been rolled back. |
| Native lifecycle | Actual Codex CLI 0.155.1 events observed across 30 fixed cases and six holdouts. Ten critical-negative groups have three scoped boundary observations each. The final collector records 138 runs including pilots, invalid setups, failures and revisions; these are not 138 independent first-pass successes. Older component evidence is explicitly distinct from exact-current snapshots. |
| Material review | Independent artifact-only reading preceded source checks. Two learning phrases and the proposal's causal/budget claims were corrected. Both current pilot artifacts passed their bounded source review. |
| User pilot | Two concrete artifacts presented for feedback; no user judgment has yet been recorded. |
| Zotero | Normal use retains one existing Win11 Zotero and one daily library. The task-owned WSL application/archive/profile was removed. Actual Windows API/PDF read-only trials succeeded; their two scratch-scope failures remain recorded. Fixed synthetic T07 and T18 used the existing Windows executable with a separate temporary profile, forced separate data directory and port. That extra instance is now closed and its profile/data deleted. Recorded production process identities, selected item/attachment objects and PDF hash were unchanged. These receipts are scoped checks, not a complete library or filesystem audit. |
| Local activation | Not started; retain existing live skills until the required native and user checks are satisfied. |

## Pilot navigation

[Learning example](pilot/learning-example.md) demonstrates the method with
clearly invented scores and separates a per-source candidate count from a total
budget. It respects a request for a complete example without a quiz.

[Manuscript draft](pilot/manuscript-draft.md) provides an English introduction
and alternative proposal directly from synthetic evidence. Revision narrows the
claim to an allocation-policy effect and separates configured token ceilings
from realized use. [Provenance](pilot/provenance.json) identifies original and
reviewed versions. These artifacts demonstrate outputs, not acquired user skill.

The focused human questions are readability, amount of help/output space, and
usefulness of direct drafting. A general compliment or deployment authorization
will not be converted into a specific learning outcome or pilot acceptance.
See the [focused review navigation](reviews/human-review.md), including a short
synthetic practice/feedback exchange.

## Evidence locations

Raw logs, source snapshots, native JSONL/tool traces, fixture digests, failure
controls, paired baseline/candidate materials and review history live in the
[task artifact index](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/INDEX.md).
These local paths describe this evaluation host; none is a runtime default.

The original [acceptance specification](checklist.yaml) remains unchanged.
The canonical development runtime record is under
`docs/agent-workflow/records/2026-09-24/20260924T103420Z-learning-workflow-migration-b70087/`.
Its generic per-item mechanical verifiers are not configured, so those generated statuses remain unverified. Actual semantic acceptance is recorded in the independent criterion audit linked from ACCEPTANCE.md, while source-backed job events retain execution observations. Neither record derives user confirmation from an artifact review.

## Limits preserved in the evidence

Native observations cover WSL/Linux Codex CLI reading the Windows Zotero
service, not the native Windows Codex host. Earlier component snapshots remain
identified separately from exact-current runs. Failed attempts and corrected
outputs are both retained; a corrected artifact does not erase an earlier
out-of-scope write.

During T07-31, the live Codex configuration hash changed outside the isolated
actor's mounted profile. The observed writer is unknown; no restoration was
attempted. Authentication, Hook and CC Switch file hashes were unchanged in the
recorded bracket. Therefore this report does not claim every global profile
file stayed unchanged. See the [drift receipt](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/protected-config-drift.json).

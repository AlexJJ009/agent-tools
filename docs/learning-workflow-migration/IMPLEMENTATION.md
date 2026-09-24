# Migration implementation and acceptance

The implementation candidate is `272a782c28d81bd8102b5ccaacaa6ff102063290`.
The initial candidate `ea8a82294f59944c3057e48e221bc0b7c2f0863a` passed code review;
native T16 subsequently exposed incorrect outside-project handoff guidance,
which is now corrected and has passed [independent delta review](reviews/implementation-review-boundary.md).
Native T18 then exposed missing project-local skill discovery and duplicate
recovery records; the correction passed [independent discovery review](reviews/implementation-review-project-discovery.md).
A later mixed-task trial exposed rejection of project-owned `task.md` records; the narrow compatibility correction passed [independent review](reviews/implementation-review-equivalent-record.md). Missing-capability fallback disclosure also has [bounded prompt review](reviews/implementation-review-capability-fallback.md). Native revalidation remains in progress. Initial code, installer and
maintained-prompt review passed; full PRD acceptance and live activation are
still pending. No production library or live skill links have been migrated.

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
| Focused unit and affected regressions | 152 tests passed in 10.123 seconds on the current runtime source (7a6198b); the later 272a782 change only adds missing-capability disclosure guidance. Tests include failures and recovery; a disposable mutation disabling the pending-input guard made its tests fail, and project skill discovery was reproduced failing before its fix. |
| Independent implementation review | Three rounds, six defects fixed, final round dry; [reviewer-authored verdict](reviews/implementation-review.md) binds the code SHA. This does not certify all native scenarios. |
| Installer | Isolated profile/source-relocation/rollback trial passed; foreign/new Hook entries and original adapter bytes preserved. Failures during link creation, copying and manifest publication were injected. |
| Native lifecycle | Actual Codex CLI 0.155.1 events observed. Repeated semantic cases, holdouts and final-snapshot reruns are still executing; partial runs cannot be reported as all passed. |
| Material review | Independent artifact-only reading preceded source checks. Two learning phrases and the proposal's causal/budget claims were corrected. Both current pilot artifacts passed their bounded source review. |
| User pilot | Two concrete artifacts presented for feedback; no user judgment has yet been recorded. |
| Zotero | The user confirmed Win11 is the Zotero host. The task-owned WSL Zotero 10.0.3 fixture instance, archive and profile were stopped and removed. Its historical receipts do not establish Win11 integration. GET-only readback of the actual Windows Zotero 9.0.6 service and mounted PDF succeeded; three separate native read-only sessions completed. The first paper explanation passed independent source review. Two sessions wrote temporary extracts outside the fixture workspace; these scope failures remain recorded. These actual-paper trials do not replace the fixed synthetic case. No production library writes occurred. |
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
It starts unverified and cannot derive user confirmation from an artifact review.

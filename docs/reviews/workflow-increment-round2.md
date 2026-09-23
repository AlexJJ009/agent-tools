# Workflow increment implementation review — round 2

**Verdict: PASS for the reviewed implementation.** All four blocking findings from round 1 are resolved at the SHA below, and this round found no new blocking implementation findings. This does not close external acceptance work, certify a new native Hook run, accept the product for the user, or authorize merge.

## Review identity and scope

- Reviewed SHA: `fdd1d337541c03bb3bfbddc7147ba027504b31bd`.
- Increment reviewed: changes from `fd0fe62f00d05ec05831cf95cd69ba652a3d95c8`, with the original review and independent failure probes retained as the starting point.
- Reviewer task: `/root/increment_code_review`, the independently dispatched round-1 reviewer resumed for verification.
- Model/effort: inherited GPT-6-based Codex host configuration; exact backend identifier and reasoning setting are not exposed. Requested GPT-5.5 / medium was unavailable, as recorded in round 1.
- Date: 2026-09-23.
- Standards: unchanged repo-resident reviewer brief, approved PRD, frozen acceptance plan, migration parity and review discipline read during round 1.
- Write scope: this new verdict and the separately requested independent discovery evaluation. No implementation, fixtures, oracle, prior verdict, commit or merge was changed by this reviewer.

## Resolution of round-1 findings

| Finding | Fix inspected | Independent verification | Disposition |
|---|---|---|---|
| F1, joined configuration path escapes snapshot | `agent_workflow/managed.py:191–201` separates the `--key=` prefix from its path, validates the declared repository input and rewrites the value to the snapshot | Re-ran the original argparse-based consumer probe. After the checked live configuration changed from 1 to 99 immediately before launch, the real effect file contained 1; result remained successful with `snapshot: true` | Resolved |
| F2, schema-2 formal-run uses legacy gate | `agent_workflow/cli.py:61–66` routes all schema-2 actions through `managed.gate_action`; the legacy fallback was removed | Re-ran the original public CLI probe with a successfully checked schema-2 sandbox record, unresolved method choice, pending input and no authority. It now exits 1 with `unregistered action: formal-run`, instead of reporting pass | Resolved |
| F3, source-copy race corrupts canonical state | `agent_workflow/state.py:94–102` reads bytes once and validates their SHA-256 before copying those exact bytes | Injected an append immediately after the source bytes were read: update committed a readable revision with the original snapshot. A separate change before validation was rejected with `source hash mismatch`, and revision stayed 1; the record remained readable | Resolved |
| F4, older delegation hides a later question | `agent_workflow/managed.py:52–59` checks current open questions before honoring delegated understanding | Re-ran the delegation → question → explicit resolution sequence. Readiness changed `true → false → true`; the blocked stage named `reward: understanding questions remain` | Resolved |

The fixes are narrow and retain the reviewed architecture. The joined option change still validates that the path belongs to the declared manifest; it does not claim to sandbox arbitrary programs or infer hidden file reads. The source fix validates copied content instead of relying on a second observation of a mutable file. The question fix keeps delegation distinct from an unresolved later question. Schema-1 compatibility remains separate from the schema-2 action evaluator.

## Tests run and evidence

Executed independently:

```text
python3 -B -m unittest tests.test_workflow_state tests.test_workflow_managed tests.test_workflow_hooks -v
```

**36 tests passed in 5.766 seconds.** This includes the four new regressions, event retry/conflict and interrupted-view recovery, ordinary repair authority reuse, queue identity checking, source tampering, simulation isolation, hook refusal and result association, bounded Stop behavior, target guard and foreign Hook preservation.

The independently authored probes were run separately from those test methods. Their observed outcomes were:

```json
{"probe":"F1","status":"pass","snapshot":true,"checked":1,"consumed":1,"later_live_value":99}
{"probe":"F2","exit":1,"result":{"status":"error","command":"gate","error":"unregistered action: formal-run"}}
{"probe":"F3","copied_bytes_remain_readable":true,"drift_rejected":"source hash mismatch","revision_after_rejection":1}
{"probe":"F4","before":true,"open_question_ready":false,"error":"reward: understanding questions remain","after_resolution":true}
```

The final source/worktree check still identified `fdd1d337541c03bb3bfbddc7147ba027504b31bd` with no implementation changes. The earlier 152-test result belongs to round 1 and is not presented as a new full-suite run. Main's broader suite is outside the independent test total above.

## External acceptance boundaries

AC-02's four natural-request runs were evaluated separately under:

- `/home/alex_mercer/projects/_artifacts/agent-tools/workflow-skills-implementation-20260923/discovery/independent-evaluation.json`
- `/home/alex_mercer/projects/_artifacts/agent-tools/workflow-skills-implementation-20260923/discovery/independent-evaluation.md`

Their semantic findings, source-reading order, canonical choice state, input isolation evidence and visibility limits are recorded there. In particular, the algorithm cases contain static predictions and deliberately do not execute the undecided method; the monitor cases contain actual loopback process/readback observations. These are different kinds of evidence.

The native proof inspected in round 1 no longer binds the changed runtime files. **AC-10 remains pending a fresh native run for this candidate at this review cutoff.** No prior native PASS is reused here. Independent staged writing acceptance, actual development report delivery/resumption and the final all-criteria summary remain separate from this implementation verdict. The user has not accepted the result through this review.

## Review completion

All round-1 implementation findings are resolved and this round produced zero new blocking findings. Preserve both verdicts. A subsequent implementation change requires an applicable new review; new evidence alone must be evaluated on its actual scope. Human merge authority remains with the user.

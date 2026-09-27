# Independent routing-scratch scope prompt review

**PASS for the bounded source delta; native compliance requires separate evidence.** Candidate `602b528b2ade668dd736ee01ffccf2dd7b93b3ad`, compared with `c60c555e84162812d55e76c953b78f720fdfdc73`. Reviewer `/root/learning_code_review` is independent of implementation authors. Requested model/effort: `gpt-6-astra` high; backend identity unavailable.

The only production delta is a two-sentence paragraph after the CLI recipe. It requires request/decision scratch files to remain in the current workspace or an explicitly authorized existing record directory, and states that temporary inputs remain writes subject to task scope. For workspace-only writes, system temporary directories are expressly excluded. This addresses the original T17-22 routing scratch exception without treating scratch files as a separate authority class. The authorized-existing-record option is consistent with canonical directory reuse; merely existing is insufficient without authorization.

The rule does not grant write permission to a read-only task, change the semantic classification algorithm, or claim operating-system/general shell interception. The preceding no-universal-sandbox limitation remains intact: this is Main's scope instruction, not a new runtime enforcement guarantee. No contradictory requirement or actionable source defect was found. Earlier traces that already kept scratch writes within scope remain component-applicable, but their prompt manifests differ from this candidate and cannot be called byte-identical reruns.

This review did not rerun native sessions or add a keyword test. Runtime remains the unchanged independently tested 7a6198b implementation. Original T17-22 `/tmp` writes remain adverse history; the corrected note does not erase those writes. The scheduled fresh T17 trials must supply actual prompt-read, tool and write-location evidence before claiming behavioral remediation. This source verdict does not itself close AC-20, supersede the frozen contract, authorize activation, or replace real-user feedback.

Binding: `skills/task-routing/SKILL.md` SHA-256 `d2fd82a2003d8531140bfd1a2601f7d19ce9267a20dc5fdd69292efdf336705a`.

Reviewed UTC: 2026-09-24T12:40:56.341281+00:00

# Workflow increment implementation review — round 1

**Verdict: REVISION_REQUIRED.** Four independently reproduced defects remain in the reviewed candidate. Existing tests pass, but they do not exercise these boundary cases. This verdict is an implementation review, not user result acceptance or permission to merge.

## Review identity and scope

- Reviewed candidate: `fd0fe62f00d05ec05831cf95cd69ba652a3d95c8`.
- Baseline: `0cd9d126b6beb31247c30a5cf720cac63a3048eb`.
- Reviewer task: `/root/increment_code_review`, independently dispatched with a fresh review context.
- Model: inherited GPT-6-based Codex host configuration. The requested GPT-5.5 / medium configuration was unavailable; the exact inherited backend identifier and reasoning setting are not exposed to this reviewer. No smaller model was substituted by the reviewer.
- Date: 2026-09-23.
- Standards read: `docs/agent-workflow/incremental/REVIEWER_BRIEF.md`, `acceptance-plan.md`, `migration-parity.md`, the approved PRD copied under the external baseline directory, repository/global instructions, and the independent-review discipline.
- Inspected implementation: canonical state and event updates, runtime checks and migration, managed execution, CLI routing, native hooks and installer, the six skill changes, shared writing rules, report tool changes and relevant tests.
- Write scope: this verdict only. Implementation, frozen inputs and oracle files were not modified. Probes used disposable test repositories. No commit or merge was performed.

Artifact root referenced below:

`/home/alex_mercer/projects/_artifacts/agent-tools/workflow-skills-implementation-20260923`

## Blocking findings

### F1 — P1: Joined path options escape the checked input snapshot

Location: `agent_workflow/managed.py:189–197`, especially the whole-argument absolute-path test at line 192.

The executor rewrites a repository path only when the entire argument is an absolute path. A normal argument such as `--config=/repo/config.json` is left unchanged. The configuration is declared, hashed and copied to the snapshot, but the launched consumer still opens the live repository file. A change after the final identity check therefore changes the actual consumed value while the receipt reports `snapshot: true` and success.

Independent reproduction used the existing `ManagedTests` disposable repository, replaced its disposable worker with an argparse consumer, and registered a second action through `action.register`:

```python
argv = [sys.executable, "worker.py",
        "--config=" + str(repo / "config.json"),
        "--effect=" + str(marker)]
config_paths = ["config.json"]
command_paths = ["worker.py"]
```

The verifier consumed value 1. Immediately before the real `subprocess.run`, a probe wrapper changed the live configuration to value 99. The actual worker wrote its consumed JSON to the marker. Observed result:

```json
{"probe":"equals_argument_snapshot_race","status":"pass","snapshot":true,"checked_value":1,"consumed_value":99}
```

This violates R07 and AC-09's fixed checked-input requirement. It is not a request for an OS sandbox: the affected file was already explicitly declared as an input to this adapter.

Required correction: normalize supported joined path options into the snapshot, or reject unsupported references before execution. Add a negative test that changes the live declared configuration after validation and verifies the real consumer still receives the checked value, or that the action refuses before producing an effect. Cover command input discovery consistently with the rewrite.

Disposition at reviewed SHA: **open**. Main was notified and accepted the finding; no fix is certified by this round.

### F2 — P1: Schema-2 formal-run falls back to a gate that ignores new conditions

Location: `agent_workflow/cli.py:61–68`; fallback at lines 63–66. Related implementation: `agent_workflow/runtime.py:462–504`.

When a schema-2 record has no registered action named `formal-run`, the public CLI calls the legacy gate. That gate checks legacy technical/human fields but does not check schema-2 choices, pending inputs or execution authority. Consequently, the retained public command can return a passing authorization result despite those new conditions being missing.

Independent reproduction initialized a fresh schema-2 simulation record with a low-risk local verifier, an explicit `sandbox_allowed` policy, a command and configuration scope. After a successful technical check, it added an unresolved method choice and an unclassified user input through the typed event interface. It created no execution authority. The public invocation was:

```text
python3 -B -m agent_workflow.cli gate --record <temporary-record> --action formal-run --simulation
```

Observed result:

```json
{"returncode":0,"stdout":{"status":"pass","command":"gate","errors":[]},"unresolved_choices":1,"pending_input_resolved":false,"authorities":0}
```

This violates the PRD section 5 requirement that the retained formal-run command apply the new conditions, plus R03/R04/R07 and AC-03/08/09. The probe establishes an incorrect gate result; it does not claim this command itself launched a job.

Required correction: keep the legacy gate restricted to schema 1. For schema 2, require or explicitly adapt a registered action through the same evaluator used by the managed entry; never silently return legacy authorization. Preserve legacy compatibility without promoting imported confirmations to the new meanings. Add CLI-level regression coverage for unresolved choices, pending input and absent authority.

Disposition at reviewed SHA: **open**. Main was notified and accepted the finding; no fix is certified by this round.

### F3 — P1: Source-copy race can commit a record that cannot be read again

Location: `agent_workflow/state.py:93–101`, especially the separate hash/read operations at lines 96–97.

`snapshot_source` validates the live file's hash, then reads it again to copy the bytes. If the file changes between those operations while preserving the quoted substring, the copied source does not match the stored hash. The update nevertheless commits successfully because schema validation does not validate those copied bytes. The next canonical read rejects the committed source; status, update and ordinary recovery paths then fail at `read_record`.

Independent reproduction initialized the existing `StateTests` disposable record and prepared a valid `input.record` event. A wrapper around `state.file_digest` appended a line to that disposable source immediately after returning its original hash. The original quote remained present, so the quote check was meaningful and still passed. Observed result:

```json
{"probe":"source_copy_race","commit":{"revision":1,"views_error":null,"duplicate":false,"event_revision":1},"canonical_read":"committed source changed"}
```

This violates R05 / AC-05's canonical-state recovery invariant. A concurrent append to an input or code-source file is enough; no manual canonical-state tampering is involved.

Required correction: read the source bytes once, validate the supplied digest and quote against those exact bytes, and copy those same bytes. The race must either reject before advancing the canonical revision or produce a source snapshot that remains readable. Add a regression asserting a failed source snapshot cannot poison the record and can be retried with a fresh event.

Disposition at reviewed SHA: **open**. Main was notified immediately after reproduction.

### F4 — P1: Earlier delegation suppresses a later unresolved question

Location: `agent_workflow/managed.py:40–58`; the delegated early return at lines 52–53 bypasses the question check at line 58.

A scoped delegation makes `choice_errors` continue before inspecting `open_questions`. If the user subsequently raises a question in that same scope and the agent records it as `understanding.feedback(kind="question")`, the dependent action still passes. The old delegation therefore silently resolves the effect of later feedback even though the question remains explicitly open in canonical state.

Independent reproduction used the existing disposable managed-action fixture:

1. Verify the local value and grant the action's execution authority.
2. Propose a reward-definition choice with required scope `reward`.
3. Grant a user-sourced delegation for that choice. The gate is ready.
4. Record a later user-sourced question on the same reward scope.
5. Evaluate the same action again.

Observed result:

```json
{"probe":"question_after_delegation","ready":true,"errors":[],"open_questions":[{"id":"e5","question":"SIMULATION ONLY: {\"choice_id\": \"reward\", \"scope\": \"reward\", \"kind\": \"question\"}"}]}
```

This violates R03 / AC-03 and the maintained acceptance-gate rule requiring no relevant open question. The finding does not require teaching a user who delegated the work: it concerns an explicitly recorded question that arrived after the delegation.

Required correction: honor current unresolved questions before reusing a prior delegation, or require a later explicit sourced disposition that covers those questions. Refuse only dependent actions; unrelated reading and separately scoped actions should continue. Add coverage for delegation followed by a question, its later resolution, and retained unrelated delegation.

Disposition at reviewed SHA: **open**. Main was notified immediately after reproduction.

## Verification performed

All test commands below completed successfully against the reviewed SHA, with no implementation changes present in the working tree at the final pre-verdict check.

| Command / inspection | Result | What it establishes |
|---|---:|---|
| `python3 -B -m unittest tests.test_workflow_state tests.test_workflow_managed tests.test_workflow_hooks tests.test_workflow_increment_acceptance tests.test_install_agent_workflow tests.test_install_work_report -v` | 63 tests pass, 22.820 s | Event retry/conflict, interrupted views, scoped state, existing managed action controls, handler behavior, mechanism exercises, installation and rollback controls |
| `python3 -B -m unittest discover -s skills/work-report/tests -p 'test_report_tool.py' -v` | 57 tests pass, 18.256 s | Structural IDs, Chinese/legacy compatibility, cold-read binding, report digest/freshness checks and archived verification behavior |
| `python3 -B -m unittest tests.test_agent_workflow tests.test_agent_workflow_portability -v` | 32 tests pass, 20.827 s | Legacy readback, forged-status rejection, local invalidation, simulation isolation and tracked export after source relocation |
| Four independent disposable probes described above | Four incorrect behaviors observed | Existing passing tests leave the reported boundaries uncovered |
| Candidate package manifest vs live source file SHA-256 | All seven `agent_workflow` files match | Supplied current native proof package corresponds to this candidate's runtime files |
| Shared writing-contract byte comparison | Equal | Reviewer brief's packaged contract matches the canonical report contract |
| Maintained six-skill Markdown/YAML/JSON scan, with legacy/test data separated | No Chinese maintained text found; relevant changes manually read | Supports language-boundary migration; this scan alone is not semantic rule-parity proof |

Total executed existing tests: **152 passed**. Passing tests do not override the four reproduced failures.

## Required review dimensions

| Dimension | Assessment for this round |
|---|---|
| Event retry, conflict and partial writes | Stable event IDs and canonical-first commit behavior are covered by passing tests. F3 leaves a source-copy race that poisons canonical reads. |
| Stale evidence and input races | Item-specific file/receipt hashes and unchanged-choice retention are exercised. F1 permits actual execution against a changed declared input. |
| Direct, terminal and queued entries | Existing mechanism exercises cover rejection/effects and queue digest changes. F1 and F2 prevent an overall parity claim. |
| Scoped understanding and explicit delegation | Choice-specific feedback and ordinary repair authority reuse are covered. F4 violates the later-question boundary. |
| Authority/provenance and legacy migration | Source hashes, exact quotes, proposal/user distinction and migration snapshots are present. Imported result acceptance remains pending. F2 bypasses new readiness conditions; F3 corrupts provenance integrity during a race. The design expressly does not authenticate human identity from a text file. |
| Genuine native Hook coverage | Inspected the supplied native event journal and execution evidence, not only handler unit tests. See detailed scope below. |
| Report-state freshness and semantics | Report snapshot hashes reject changed canonical bytes at new delivery; archived `--verify-only` remains read-only. Unique semantic IDs and two-stage review bindings pass tests. These mechanical checks cannot establish semantic writing quality or actual user acceptance. |
| English rule parity | Maintained changes and the migration mapping were read; Chinese quotations/legacy aliases are preserved separately. Shared writing rules are byte-identical. |
| Portability and foreign Hook preservation | Installer tests preserve foreign groups, reject inappropriate targets and use the target guard. Export/runtime relocation regression passes. No native Windows or remote fleet acceptance is claimed. |
| Semantic discovery and cold-read outcomes | External natural-discovery and writing acceptance were still being completed when this review was dispatched. Their completion is not inferred from runtime tests or file presence. No PASS is assigned here for AC-02 or AC-13. |
| Current phase vs future phase and user result acceptance | Mechanism tests preserve pending user acceptance and allow future phases to remain unfinished. This review does not close the real development phase or mark any user result accepted. |

## Native evidence inspected and its limits

Inspected `harness/candidate-probe/verification.json`, `candidate-files.json`, `allow-current-result.json`, `checker-negative-control-current.json`, the preserved older `snapshot-verification.json`, and the raw `events.jsonl` journal. The journal contains 78 records: 7 SessionStart, 7 UserPromptSubmit, 31 PreToolUse, 27 PostToolUse and 6 Stop events. Its current ready probe begins at event offset 62 and includes restoration, prompt capture, unrelated reads, an initially refused guarded entry, input classification, the allowed entry with correlated PostToolUse, and Stop. The corresponding result records exit 0, a present effect marker, unchanged protected files and no copied authentication bytes.

The candidate-file manifest matched all seven current runtime files during this review. The checker negative control records that removing the real PreToolUse receipts caused the expected failure. The older snapshot report explicitly says its source later changed; it was not substituted for the current proof. The earlier failed allow attempt is preserved as a failure, not counted as success.

This supports the reported isolated CLI 0.155.1 WSL Hook behavior for the supplied probe. It does not prove arbitrary terminal command coverage, real business authorization, or a deployment to other hosts. Any code fixes following this verdict change the reviewed candidate and require fresh applicable verification; the current native PASS cannot silently cover a modified package.

## Resolution and acceptance boundary

No finding is resolved at `fd0fe62f00d05ec05831cf95cd69ba652a3d95c8`. Main acknowledged F1 and F2 and was notified of F3 and F4; planned fixes are not evidence of resolution. A later review must inspect the new SHA, verify the negative/positive controls, and preserve this round unchanged.

Natural discovery, independent staged writing review, real development report delivery/resumption and the final external AC summary remain separate acceptance work. Their pending status is an evidence limit, not a claim that they failed or passed. Technical checks, this independent verdict and actual user acceptance must remain separate. Human merge authority remains with the user.

# Independent review — ReadPapers boundary corrections

Verdict: **pass for the bounded source delta**. No new blocking finding was identified. This add-only review supplements the original `implementation-review.md`, which remains unchanged.

## Candidate and independence

- Reviewed candidate: `33e982d19173b0e32bfe5f40d97092cad8194fb3`.
- Runtime correction: `b2056db048e7ba7d1b6840fca49bcb26c6fe0b89`; the subsequent commit changes only the evidence-anchor reference.
- Previously reviewed implementation: `ea8a82294f59944c3057e48e221bc0b7c2f0863a`.
- Reviewer: independent Codex subagent `/root/learning_code_review`, separate from implementation authors.
- Requested model/effort: `gpt-6-astra`, `high`; actual backend-routed identity is not exposed to this reviewer.
- Scope: runtime project validation and CLI, task-routing and ReadPapers adapter prompt corrections, their runtime regression, and `skills/evidence-anchor/references/evidence-anchors.md`. Earlier code/installer coverage is not represented as newly rerun full coverage.

## Corrections assessed

The native outside-project case had declared library capability/authorization in a code repository and suggested adding configuration there. The corrected prompts require an `answer` handoff preserving the locator and requested operation without selecting the library adapter or manufacturing a ReadPapers root. Actual library-project migration/configuration remains a separately scoped task.

The runtime now validates declaration consistency at initialization, classification, dependent action checks, and explicit CLI validation. Selecting `read-paper` or declaring a registered library action requires ReadPapers context and a workspace inside the configured root. Invalid initialization fails before creating its record. Structural `show`/`read` remain available for legacy invalid records, and valid classification can recover them. Ordinary reading stays available.

The evidence-anchor reference now distinguishes legacy v1 Zotero locators from supplied paper evidence outside ReadPapers. The latter uses a stable source identifier, actual file/snapshot digest or version, and page/section. It prohibits invented library keys and implicit library operations while retaining recheckability and provisional labels for missing/mutable locators. The legacy v1 validator is unchanged.

## Verification performed

- Independently ran `python3 -m unittest discover -s tests -p 'test_learning_runtime.py' -q`: **15 passed** on the runtime correction.
- Independent disposable probe: invalid outside-project library initialization rejected; the requested record directory was not created.
- Legacy-state CLI probe: `show` exited 0; explicit `validate` exited 1.
- Invalid classification rejected without advancing revision. Valid handoff classification recovered the invalid record; subsequent CLI `validate` exited 0.
- Ordinary read of the invalid record remained allowed. A dependent `write_artifact` with invalid library declarations and no pending inputs was rejected by project-scope validation.
- Configured-project positive initialization remains covered by the runtime test. No Zotero call or library write was performed by these checks.
- Read the final single-reference evidence-anchor diff and the full resulting reference; no executable or v1 validation change was introduced by that commit.

## Coverage limits

The runtime checks consistency of supplied facts. It does not authenticate the provenance of `readpapers_root` or establish that Main did not invent a configuration; the prompt correction explicitly prohibits that workaround. Native T16 repetitions and actual configured-project positives must establish semantic behavior separately. Their reruns, all native cases, other hosts, live installation, and user acceptance are not certified here. The observed native failure remains part of the migration history rather than being reclassified as an earlier pass.

Uncommitted documentation/pilot changes and the canonical implementation record are outside this source-delta verdict. This reviewer wrote only this new verdict file and modified no implementation. No merge, installation, publication, or library mutation is authorized by this verdict.

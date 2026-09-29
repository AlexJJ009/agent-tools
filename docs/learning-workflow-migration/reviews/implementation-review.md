# Independent implementation review

Verdict: **pass for the bounded code, installer, and maintained-prompt review**. The latest round produced no new findings. This is not full PRD acceptance, native host certification, user acceptance, deployment authorization, or merge approval.

## Candidate and reviewer

- Reviewed candidate: `ea8a82294f59944c3057e48e221bc0b7c2f0863a`.
- Reviewer: independent Codex subagent `/root/learning_code_review`, separate from implementation authors.
- Requested review model/effort: `gpt-6-astra`, `high`, as explicitly configured by the spawning agent. Actual backend-routed model identifier is not exposed to this reviewer and is not independently verified. Originally requested GPT-5.5 was unavailable.
- Review rounds: three. Rounds 1 and 2 found defects; this final frozen-candidate round is dry.
- Scope: commit's runtime/hooks/CLI, scoped installer and rollback, task-routing/academic-writing, migrated teaching entry points and compatibility adapter, ReadPapers resources, shared writing contract/synchronizer, necessary development handoff, runtime/install documentation, and associated regression tests.
- This reviewer authored this add-only verdict. No production source, live profile, library, or acceptance state was modified during review. Temporary-profile failure injections were isolated.

## Findings and resolution

| Finding | Severity | Resolution in reviewed candidate |
|---|---|---|
| An older pending input could overwrite a newer user's curation exclusion after reading the current revision. | P1 | `learning_workflow/runtime.py:205` checks input ordering; older pending input can reconcile only with the latest decision. Negative and recovery regression passes. |
| Failure creating a replacement skill symlink after unlinking the old one lost the old link. | P2 | `scripts/install_learning_workflow.py` exception cleanup restores prior absent links even when candidate-link creation never succeeded. One-shot failure injection passes. |
| Remote prefix scope accepted `host:/repo/../secret` under `host:/repo`. | P2 | Runtime validates canonical host/absolute-path locators before containment. Traversal, repeated separators, dot paths, and other-host negatives pass. |
| Partial bundle copying could leave an untracked installation that rejected retry and rollback. | P2 | Installer cleans partial bundle copying before publishing any links. Failure injection confirms no bundle remains. |
| Curation destination equal to the record directory recursively acquired the same file lock and hung. | P2 | Runtime rejects destinations within routing state before the second lock. Regression confirms rejection. |
| Default curation identity conflated unrelated projects with identical directory basenames and relative note paths, overwriting the first import. | P2 | Curation now requires an explicit stable `project_id` before creating the destination; basename fallback is removed. Missing-identity regression passes. Repeat-import deduplication and relocation tests still pass. |

There are no deferred blocking findings in this review scope. Mutable-worktree investigation records and exact reproduction observations remain in the task artifact directory under `reviews/round1.md`, `reviews/round2.md`, and `reviews/round1-snapshot.json`; their earlier verdicts are preserved.

## Verification observed on the frozen candidate

- Independently ran `python3 -m unittest discover -s tests -p 'test*learning*.py' -q`: **28 passed**. Includes state conflicts and recovery, real guarded curation with Hooks off, path/scope failures, identity requirement, installer rollback/failure injection, source relocation, foreign Hook settings, and target guard refusal.
- Independently ran `python3 -m unittest discover -s tests -p 'test_teaching*.py' -q`: **65 passed**. Covers legacy teaching validation and Hook behavior.
- Independently ran `python3 skills/work-report/scripts/sync_writing_contract.py --check`: passed.
- Independently ran `git diff --check`: passed. Tracked candidate files were clean before adding this verdict; the canonical implementation record directory was untracked and outside the code verdict.
- Inspected Main's `consolidated-tests.log`: **149 passed** in its broader targeted/regression run. This broader result was read back, not independently rerun in its entirety.
- Prior-round independent failure probes observed red behavior before the fixes; green regression output is therefore not the sole evidence that those checks can fail.

## Prompt and authority boundaries

The reviewed entry points separate Main's semantic decision from deterministic validation. Short answers need no route record; ordinary development explanation does not imply teaching. Source text does not authorize activity changes. Direct academic drafting, revision, and argument review do not depend on learner tests. Portable code learning does not require Zotero/Obsidian records; legacy v1 documents remain supported without bulk rewriting. Library operations are scoped through the project adapter. Learning records and code observations do not grant experiment or publication authority. Work Report format/Judge requirements stay genre-specific.

## Coverage limits

The runtime is a cooperative local workflow, not an identity authenticator or universal sandbox. Declared scopes still require real user/project authority. Native Hook trust, delivery and semantic correctness require separate traces; recognized command forms do not cover arbitrary shell composition, MCP, file writes, or chat. Hosts without turn IDs cannot distinguish identical new prompts from content-level retries without an explicit input ID. Native Windows is outside this Linux/WSL implementation's support boundary. No remote execution, publication, broad deployment, end-to-end learner gain, or human acceptance was certified.

Manuscript cold/source reading is recorded separately; its material-quality assessment neither changes this code verdict nor certifies the whole PRD. Any production-code change after the candidate SHA requires a new review; this verdict itself is add-only review evidence.

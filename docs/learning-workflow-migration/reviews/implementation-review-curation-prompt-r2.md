# Independent curation-prompt delta review — round 2

- Candidate: `8e0170b8b0a0752ee571247142314008906de890`
- Prior reviewed candidate: `873a3b727282e25ff01100dc64effcad76542c0a`
- Original implementation base: `a3efa99b7756f14d350ddddb72f6ceb432d61158`
- Verdict: **bounded dry PASS — F1 resolved; no new finding in this maintained-prompt delta**.
- Reviewer: delegated `learning_final_reader`; no product edits. Requested GPT-5.5 medium was unavailable to the dispatch tool; available inherited model used.

## Resolution

The one-paragraph correction at `skills/learning-artifact-compiler/SKILL.md:22` now separately requires actual file reads for note content and index source project/version/path, and the `inspect-index` call for artifact availability, digest consistency, and source availability. It explicitly says that the command does not return note text or provenance fields. This matches `runtime.inspect_index`'s actual return shape and closes the R1 mismatch.

The paragraph now requires one entry **for this source identity** and explicitly retains unrelated entries in a shared index. That matches `curate`'s project-plus-source-path deduplication key without imposing a one-entry limit on the entire knowledge directory. The preceding explicit-curation recipe, existing-record recovery, user-edit preservation, source-unavailability disclosure, and separate publication/Zotero authority remain unchanged and consistent with the previously inspected runtime and PRD.

## Verification

Inspected the immutable `873a3b7..8e0170b` diff and the complete candidate compiler skill. The delta is exactly one paragraph replacement in one file. Verified byte equality of `learning_workflow/runtime.py`, `learning_workflow/__main__.py`, `skills/task-routing/SKILL.md`, and the PRD between the two candidates. The prior read-only `inspect-index` observation therefore remains applicable to the unchanged API; no duplicate or implementation-mirroring test was added or rerun.

The original R1 report is untouched, SHA-256 `d3b2656ceb4b8bc8f6a94daec4aa85a8456a9bfe0e51c927f79a6695f6f21a56`. Its CHANGES REQUESTED verdict remains the historical verdict for `873a3b7`; this document resolves F1 only for `8e0170b`.

## Scope limits

This is a source-level prompt/API consistency review. It does not establish successful native-agent compliance, retroactively pass T17-12, certify the planned native T17 repeats, update user-facing candidate navigation, provide real-user feedback, or authorize activation. Those remain separate evidence and task ownership. No product file, existing review, live record, library, installer, or publication state was changed.

## Candidate file bindings

| File | SHA-256 at candidate |
|---|---|
| `skills/learning-artifact-compiler/SKILL.md` | `4d010c6a09fe8d6923421c9afe1d0d8776619723de2f06be265edb1fe60507eb` |
| `learning_workflow/runtime.py` | `41442a6d06daae73b2d947f3ed02de7a26df345e651e2cf10b5cfdf7b2d1ca78` |
| `learning_workflow/__main__.py` | `d5a0e120a583059e7ade7921e9dc5df06c152dddb9ce35c9e45339bc5045de7a` |
| `skills/task-routing/SKILL.md` | `80a607b29d6ffac62d20726a91039045834c5d8e7699c24ef79611fa85f21b0d` |
| `docs/learning-workflow-migration/PRD.md` | `d1215c7fb7b63c8faec95869380d2e8f6769bc89ddb45d54012b24040badd756` |

Review saved (UTC): 2026-09-24T11:45:39.037894+00:00

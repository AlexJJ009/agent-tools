# Independent curation-prompt delta review

- Candidate: `873a3b727282e25ff01100dc64effcad76542c0a`
- Base: `a3efa99b7756f14d350ddddb72f6ceb432d61158`
- Verdict: **CHANGES REQUESTED — one P2 maintained-prompt/API mismatch**.
- Reviewer: delegated `learning_final_reader`; no implementation edits. Requested GPT-5.5 medium was unavailable to the dispatch tool; available inherited model used.
- Scope: the seven added lines in `skills/learning-artifact-compiler/SKILL.md`, checked against existing `curate`, `inspect_index`, CLI arguments, `task-routing`, and PRD explicit-curation requirements. No wider code, install, user-navigation binding, or activation review.

## Finding

### F1 — P2: separate file readback from `inspect-index` observations

**Location:** `skills/learning-artifact-compiler/SKILL.md:22` at the candidate.

The new recipe directs the agent to read back the actual index and exported note “using `inspect-index --index PATH --source-root DIR`”, then verify source project/version/path and artifact digest. The named command cannot return that material. `learning_workflow/runtime.py:336` loads the files internally but returns only an entry-key map with `artifact_available`, `artifact_unchanged`, and `source_status` (`:348`). It emits neither the note body nor the index's project, source revision, source path, or digest fields. A successful observation can therefore be mistaken for completing the explicitly required content/provenance readback, especially in the concrete recovery case where a saved note was previously mistaken for completed curation.

I exercised the existing read-only command against the already-produced T17-11 package. The complete output was:

```json
{
  "ed0805226aae0dd1a758": {
    "artifact_available": true,
    "artifact_unchanged": true,
    "source_status": "available"
  }
}
```

**Requested correction:** explicitly read the actual JSON index and exported note, verify the matching entry's source identity/revision/path and recorded digest, and separately run `learning-workflow inspect-index` for file availability/digest consistency/source accessibility. Scope “expected single entry” to the matching source identity; an otherwise valid shared index may contain other entries. This correction needs prompt wording only, not a new inspection API or a mirrored test suite.

## Checks that passed

- The new recipe correctly distinguishes a plain `write_artifact` scope check from `curate`, which performs an explicit curation check, writes the copied note, and creates or updates its provenance index (`runtime.py:295–333`). The changed same-project-directory wording closes the reported ambiguity without requiring a central vault.
- Staging the note in the source workspace matches `curate`'s requirement that the source be a file within the workspace and outside routing state (`:307–309`). The current record/revision and authorized destination correspond to the existing API and `task-routing` instructions.
- Stable `project_id` and source path form the deduplication key (`:311–313`), and an edited destination is rejected before overwrite (`:323–324`). The instruction to preserve user edits is consistent with that guard; this is preservation by refusal, not an automatic merge promise.
- Source unavailability after relocation is reported by `inspect_index`; neither the runtime nor the added text promises synchronization. Existing-record recovery matches `task-routing`'s recovery guidance, and publication/Zotero boundaries stay separate.
- PRD §4.2 requires a self-contained note plus an index only for requested curation, preserves source project/version/location/status, updates an existing entry on reimport, and discloses unreachable source links. The delta addresses those requirements without routing ordinary manuscript drafting into teaching.
- Maintained prompt prose remains English. The base-to-candidate diff is exactly one file with seven added lines.

## Verification and limits

Read the immutable base/candidate diff, inspected the runtime and CLI surfaces, and ran one read-only `inspect-index` call on an existing artifact. No new tests, live task mutation, installer, Zotero action, publication, or product edit was performed. The readback command used `PYTHONDONTWRITEBYTECODE=1 python3 -m learning_workflow inspect-index --index <T17-11>/workspace/curated/artifact-index.json --source-root <T17-11>/workspace`.

This is an independent source review of the maintained-prompt delta. It does not show that a native agent will follow the revised instructions. The newly planned T17 repetitions remain separate behavioral evidence. The reported T17-12 omission motivates the delta; it is not regraded as passing here. Prior material reviews and current human-review candidate labeling are outside this narrow dispatch.

## Immutable reviewed-file bindings

All digests below come from `git show <candidate>:<path>`, not uncommitted working-tree files.

| File | SHA-256 at candidate |
|---|---|
| `skills/learning-artifact-compiler/SKILL.md` | `98e1ca55019320cf721a1e1e1b89c95570079fc0ad5829c3e8dd136f97c5fe96` |
| `learning_workflow/runtime.py` | `41442a6d06daae73b2d947f3ed02de7a26df345e651e2cf10b5cfdf7b2d1ca78` |
| `learning_workflow/__main__.py` | `d5a0e120a583059e7ade7921e9dc5df06c152dddb9ce35c9e45339bc5045de7a` |
| `skills/task-routing/SKILL.md` | `80a607b29d6ffac62d20726a91039045834c5d8e7699c24ef79611fa85f21b0d` |
| `docs/learning-workflow-migration/PRD.md` | `d1215c7fb7b63c8faec95869380d2e8f6769bc89ddb45d54012b24040badd756` |

Review saved (UTC): 2026-09-24T11:44:19.061062+00:00

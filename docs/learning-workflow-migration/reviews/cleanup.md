# Bounded cleanup review

Reviewed implementation candidate: `ea8a82294f59944c3057e48e221bc0b7c2f0863a`.
Outcome: **no production-code or maintained-prompt cleanup change**. This is a maintainability pass over the frozen candidate, not a new implementation review or an acceptance verdict.

## Scope and findings

I inspected the learning runtime and CLI, Hook adapter, local installer and rollback, compatibility teaching router, ReadPapers adapter, new and changed skill entry points, W1–W9 source and generated copies, affected tests, and runtime/install documentation. I compared the candidate with its parent and checked commits and worktree changes after the candidate. The tracked post-candidate commits change pilot/review artifacts only; the current uncommitted edits are also outside implementation code. I left those concurrent artifacts untouched.

Useful cleanup already present in the candidate:

- The old keyword table was retired from `route_teaching_intent.py`. Its importable compatibility entry now requests a Main Agent decision, avoiding a second implicit classifier and the observed `check`/`citation` substring misroutes.
- W1–W9 have one maintained source in `shared/writing/reader-facing-contract.md`. The report and reviewer-brief copies are generated and checked byte-for-byte; report six-section and Judge rules remain local to the report genre.
- A development route stores `development_record_ref` with path and revision beside the canonical development checklist. The derived routing view is separate from the existing development `task.md`, so it does not duplicate protocol or acceptance state.
- `academic-writing` has direct draft/revise/review modes independent of teaching checks. The ReadPapers adapter owns library-specific operations, while the v1 teaching validator remains frozen for old records. These boundaries avoid a broad shared schema or implicit Zotero authority.

The runtime's action set is intentionally narrow: declared curation is guarded at its entry, while semantic classification, arbitrary shell commands, and external authorization remain outside its enforcement. The installer is long because it preserves aliases, foreign Hook settings, and rollback state across partial failures. I found no demonstrably dead branch, duplicate maintained rule source, hidden side effect, or module-boundary violation whose removal would preserve the reviewed behavior and justify invalidating the frozen code verdict. Reformatting the compact runtime or splitting the installer solely for style would create review churn without resolving a concrete defect.

## Checks and evidence boundary

- `git diff --name-only ea8a822 HEAD` lists only pilot and review artifacts; `git diff --name-only ea8a822 -- learning_workflow scripts/install_learning_workflow.py skills project_adapters shared tests` produced no implementation paths.
- `python3 -m unittest discover -s tests -p 'test*learning*.py' -q`: **28 passed**.
- `python3 -m unittest discover -s tests -p 'test_teaching*.py' -q`: **65 passed**.
- `python3 skills/work-report/scripts/sync_writing_contract.py --check`: copies match.
- `git diff --check`: passed.
- I inspected the independent final implementation review, which reports a dry review of this exact candidate after six concrete defects were fixed. These checks do not replace native host traces, a real Zotero integration trial, or the user pilot.

No implementation file changed in this pass, so no prior code review or targeted test evidence is invalidated. AC-01/02/13/15/16/18/19 remain subject to their own acceptance methods; this note does not mark checklist items passed. AC-21 user feedback remains pending. Actual native routing/Hook coverage and genuine ReadPapers library behavior must be judged from their separate run evidence before a full acceptance claim or activation.

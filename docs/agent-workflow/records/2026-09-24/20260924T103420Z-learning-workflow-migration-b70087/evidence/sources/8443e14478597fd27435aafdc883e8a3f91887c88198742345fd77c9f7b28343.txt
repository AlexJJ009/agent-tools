# Independent delta review — project skill discovery and record recovery

Verdict: **pass for this bounded source delta**. The latest round is dry: no new blocking defect found. This add-only verdict supplements the prior code and boundary reviews.

## Candidate and scope

- Reviewed candidate: `787a8ce0186240888db0d9bfc3ea54c1757577f4`.
- Delta baseline: `33e982d19173b0e32bfe5f40d97092cad8194fb3`.
- Reviewer: independent Codex subagent `/root/learning_code_review`, separate from implementation authors.
- Requested model/effort: `gpt-6-astra`, `high`; actual backend routing is not exposed to the reviewer.
- Scope: capability discovery in `learning_workflow/runtime.py::check`, task-routing recovery guidance, the corresponding `RUNTIME.md` description, and the added runtime regression. User-navigation and practice-excerpt documents belong to separate artifact review and were not certified here.

## Assessment

The default capability search now includes workspace `.agents/skills`, matching the project adapter's installation path, alongside the existing user and workspace locations. The library project-scope validation still runs before capability discovery, and the registered library-action checks remain intact. Finding a skill does not grant authority to invoke its library actions.

The recovery paragraph directs Main to inspect the installation and correct the existing task record using the preserved request and a distinct recovery input ID. It explicitly requires retaining the task/session identity, exclusions, and authority, states that repeated evidence is not new permission, and forbids initializing a replacement record for the same task. It therefore addresses the observed duplicate-record response without broadening user scope.

Nonempty explicit `skill_roots` continues to replace defaults. The existing empty-list behavior remains default discovery (`or` fallback); an empty list is not a deny-all capability policy, and this change does not introduce such a policy.

## Independent verification

- Ran `python3 -m unittest discover -s tests -p 'test_learning_runtime.py' -q`: **16 passed**.
- A separate disposable probe with an isolated empty home and only workspace `.agents/skills/read-paper/SKILL.md` passed the authorized library-read check.
- The same available project skill was not found when an explicit nonempty root pointed elsewhere: the capability check rejected, confirming no fallback from an explicit root list.
- Reclassifying the same workspace as `repository` still rejected the library read despite the installed skill.
- Recovery in the existing record preserved task ID, session ID, authorized actions, and the explicit library-mutation exclusion. Mutation remained rejected afterward; exactly one `routing.json` existed under the project.
- Read the saved red/green logs: the added project-discovery test failed before the fix with `selected capability unavailable: read-paper`, then the 16-test runtime suite passed after the fix. The red output is a genuine exercised rejection, not a skipped test.

## Evidence and limits

- `project-skill-discovery-red.log` SHA-256: `8021aa738410cbb464634dfa09d8fcedbaa71a1f26c12b12484fecfb27d2cf52`.
- `project-skill-discovery-green.log` SHA-256: `afc741e92a56159d5292d379f66313ecaf5dc098b5984f5e8689a0420db73ccd`.

This review covers code behavior and the maintained recovery instructions. It does not prove that every native actor follows them, authenticate supplied authorization facts, or certify the ongoing native T18/other affected reruns. No Zotero call, library mutation, live installation, user acceptance, whole-product acceptance, or merge was performed or authorized. The reviewer edited only this new verdict file.

# Increment acceptance evidence

The fourteen technical acceptance criteria passed in the actual development
record on 2026-09-23. The increment was used during development: the record was
migrated after M1 became usable, real choices and failures were recorded, changed
inputs invalidated evidence, and actual reports were generated from a frozen
record revision. User result acceptance remains pending for every item.

The predevelopment checkpoint was committed and pushed as `0cd9d12`; initial
implementation was `fd0fe62`. Independent review found four P1 defects. Each new
regression failed before the fixes in `fdd1d33`: joined absolute config arguments
could bypass input snapshots, a schema-2 gate could fall back to legacy behavior,
a source copy race could commit invalid provenance, and earlier delegation could
hide a later user question. Independent re-probes confirmed all four fixes.

## Observed outcomes

| Criterion | Observation supporting acceptance |
|---|---|
| AC-01 | Frozen PRD, requests and independent expected outcomes survived revision tests; changed or missing baseline material was rejected. |
| AC-02 | Four separate natural-request trials inspected actual source and recorded choices. Both algorithm trials exposed per-source sample counts, output/context budgets, critic initialization and reward differences. Both monitor trials exposed cache redraw versus probing, timestamp meaning and 429 handling. |
| AC-03 | Critic-only feedback left reward unresolved; the dependent action was refused while unrelated reading continued. A later explicit question also blocked an earlier delegation. |
| AC-04 | Scoped local delegation allowed checks and equivalent repairs without an extra approval event. |
| AC-05 | Duplicate event retries stayed idempotent; revision conflicts were rejected; interrupted derived views rebuilt from canonical state; status did not run verifiers or Git. Source-copy races could not poison the record. |
| AC-06 | Timestamp-only acceptance remained scoped. Unseen error handling stayed pending; a next-MVP request remained distinct from a broken existing promise. |
| AC-07 | Actual CPU processes consumed 4 samples per source, 8 total, and 8192 output tokens. Critic/reward values and loopback request journals were read back independently. Canned stdout without a process effect was rejected. |
| AC-08 | Equivalent repairs revalidated evidence while retaining authority. Changes to the method or budget required a new scoped decision. |
| AC-09 | Registered direct, shell and queued entries refused missing conditions before effects. Repairs allowed effects. Changing the live checked value from 1 to 99 still produced a consumed value of 1 from the snapshot, including joined config arguments. |
| AC-10 | Codex CLI 0.155.1 in an isolated WSL profile emitted all five native events. Pending input was refused, unrelated reading continued, classification enabled execution, and PostToolUse correlated the result. Disabling Hooks produced zero Hook events while the execution entry still rejected stale evidence. |
| AC-11 | The actual development completion gate rejected missing criteria. After all fourteen were checked, it still rejected missing independent phase review. Test phases allowed current-phase completion with future work and human acceptance pending. |
| AC-12 | The actual brief and progress report used canonical revision 30 and its exact snapshot. Both passed independent reading. A separate five-step trial initialized its first report after step five, delivered it, and then actually created the promised next-step artifact. |
| AC-13 | Two clear reports, including Chinese headings with semantic IDs, passed independent cold reading and source review. Four negative reports/briefs were rejected for omissions, overclaims or empty terminology. The delivery checker rejected failing reviews; duplicate IDs failed mechanically. |
| AC-14 | Maintained rule files across all six skills use English; legacy Chinese mapping and original quotes remain readable. v1 migration preserved prior meanings without promoting understanding or acceptance. Isolated installed commands worked after source relocation and retained foreign Hook groups. |

## Verification and reproduction

- Repository tests after the four fixes: **175 passed**.
- Report tool, runtime and scheduler suite: **110 passed**.
- Isolated installed Linear runtime suite: **70 passed**.
- Focused portability, installer, state and Hook checks also passed.
- Both independent implementation review rounds are preserved under `docs/reviews/`.

Run repository tests with `python3 -m unittest discover -s tests -q`. Run the
report suite with `uv run --with markdown-it-py==4.0.0 --with PyYAML==6.0.2 python
-m unittest discover -s skills/work-report/tests -q`. The shared Linear runtime
must first be installed into an isolated environment, as in repository CI.

`scripts/verify_workflow_increment.py` replays AC-01, AC-03 through AC-09 and
AC-11 against a separately frozen baseline. See the
[acceptance plan](acceptance-plan.md) for the required manifest and controls.
AC-02, AC-10, AC-12 and AC-13 additionally require actual Agent/native-host
traces; unit tests are not substitutes. Keep expectations separate from
candidate-produced observations.

The execution artifact root is
`/home/alex_mercer/projects/_artifacts/agent-tools/workflow-skills-implementation-20260923`.
It retains baseline manifests, raw native and independent-agent traces, source
hashes, refused attempts, external verifier negative controls, and report
delivery/resumption receipts. The actual record is
`docs/agent-workflow/records/2026-09-23/20260923T073908Z-workflow-state-writing-1bbec7`.
Reports and mutable records stay locally excluded from Git; their machine and
human acceptance states are distinct.

## Material operating boundaries

The execution adapter covers registered local actions and declared inputs.
It does not implement arbitrary shell containment or production admission.
Natural discovery was evaluated in four independent contexts with observed
source reads; encrypted dispatch message bodies were not recoverable as plain
text, while `fork_turns=none` and the original host receipt were verified.

One earlier native provider attempt timed out and detected a live config hash
change of unknown origin. That failed attempt remains in the evidence. Final
passing attempts read back unchanged protected files and copied zero auth bytes.
No unknown live change was reverted. The five-step reporting trial reached its
deferred milestone manually; missing host pending-input registration was
reported, with no automatic scheduling guarantee claimed.

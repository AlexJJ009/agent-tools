# Adapted historical task cases

H01–H05 are CPU-only reductions of mechanisms identified in the approved task
runtime MVP PRD v5 §10.2 (2026-09-30), itself based on the workflow/document
lifecycle investigation. H05 specifically reduces the reported Slime acceptance
script dependency on disposable records to one small JSON input. No original
workspace, raw chat, credentials, GPU code or server paths are copied. The case
messages are authored adaptations, not verbatim historical user quotations.

`cases.json` fixes message delivery order, allowed actions, expected outcomes and
limitations. `manifest.json` fixes initial project bytes. `project/` is actor
input. `oracle.py` and expectations are evaluator-only: give an acting agent the
project and messages, never the answer key. The initial CLI intentionally lacks
H01's requested strip mode; the initial H05 test intentionally reads `records/`.

`Sandbox` creates a fresh temporary root, Git repository, second real worktree,
external data directory and out-of-scope sentinels. Its runner accepts only
Python commands and only the two temporary workspaces; supplied paths must
resolve inside this sandbox. It refuses a configured original/external workspace.
This is a test launcher, not a containment sandbox for arbitrary adversarial code.
Fixtures use no network, accelerator, external queue or production configuration.

Oracles inspect actual transformed bytes, readback packets and filesystem
snapshots. They do not accept a candidate's `pass` flag. Normalize runtime fields
in the calling test; no runtime implementation is embedded here:

- H02: `requirements` keyed by stable ID, `ordinals` as current ID order,
  `stale_write_rejected`, and per-requirement `result_validity`.
- H03: returned `candidates`, explicit `selected`, `pending`, and `prohibitions`.
- H04: logical read result and file-byte snapshots before/after query/retry loops;
  after real revision, pass the current requirement string separately.
- H05: actual project test execution plus protected path bytes and disposable
  target absence. Snapshot references and content at planning, mutate one target
  before execution, and retain it. An interrupted cleanup may be retried.

`tests/test_task_runtime_cases.py` proves positive controls and injected broken
results are distinguished, including lost requirements, stale validity, omitted
constraints, repeated append, wrong deletion and refusing all cleanup. Runtime integration is exercised separately in `tests/test_task_store.py`.
Fixture-only checks do not prove real Agent usability, and cannot establish
GPU training, remote recovery, native Hook delivery or model benefit.

## Initial execution (2026-09-30)

The runtime tests exercise H02–H04 state/query mechanisms. H01/H05 fixture tests
exercise CPU behavior and the records-to-test-fixture migration with negative
controls. They are not five native model implementation trials.

An independent Cleaner agent also used an isolated copy of this repository,
its current Cleaner instructions and real runtime calls: two owned disposable
materials were removed at closeout; project documents, a user untracked file,
another task and a second worktree remained unchanged. Acceptance of that
fixture task was simulated, not the user's acceptance of this MVP. An unsupported
installation claim in a disposable report was not promoted into project docs.

A serial H03 native comparison used gpt-6-astra, medium effort, with equal task
state in JSON (A) versus the runtime interface (B), ordered A/B/B/A. Independent
review found all four answers preserved both pending criteria, exclusions and
the CPU-tests-before-implementation next step without inventing user acceptance.
Recorded durations were 47.89/49.64/57.78/42.87 seconds. This is no evidence of
an accuracy or token-efficiency advantage. The earlier unequal-information
pilot was excluded.

Limitations: B2's recorded task-read output was empty despite exit 0, so its
answer does not establish successful retrieval from that trace. B2 and B3 had
different task_store.py hashes due to write-request validation changes during
the run; read behavior was unchanged, but the candidate was not fully frozen.
These are exploratory interface observations, not a controlled efficacy result.
The committed runner records hashes, separates mechanical checks from semantic
review, and has subsequently hardened setup failure and Git/child isolation;
those harness changes have offline regression checks, not a new model trial.

Raw traces and protected-file snapshots are local evaluation data outside Git,
under the evaluation output directory. Future runs must freeze candidate bytes,
inspect successful read outputs and review answer semantics before comparing.

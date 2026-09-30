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
constraints, repeated append, wrong deletion and refusing all cleanup. It does
not yet prove runtime integration or real Agent usability, and cannot establish
GPU training, remote recovery, native Hook delivery or model benefit.

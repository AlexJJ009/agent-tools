# Contributing

Follow the current user-authorized task scope. Linear Workflow is deprecated
and disabled; no Linear Batch is required. Its retained runtime is a compatibility
surface, not the development workflow.

## Regression tests

Use Python 3.11+ in an isolated environment, with Git, Bash and Node.js on PATH. The report parser uses the same
versions declared by `skills/work-report/scripts/report_tool.py`:

```bash
python -m pip install markdown-it-py==4.0.0 PyYAML==6.0.2
python scripts/run_regression_tests.py active
```

The runner explicitly discovers five suites in separate processes. Standard
`unittest discover -s tests` does not descend into the independent Skill packages.
Empty discovery, entirely skipped suites, import errors and failed assertions
fail the runner. Skips are
reported as skips, not passed tests; inspect their reasons before claiming
platform coverage. Run one suite by substituting its name below for `active`.

| Suite | Regression responsibility | Limits |
|---|---|---|
| `repository` | Task state, cleanup/recovery/audit, learning runtime, installers, hooks, configuration guards and old Agent Workflow records | Some Windows/AutoDL checks inspect source; native platform and host hook activation require deployment checks |
| `reports` | Report parsing, evidence/receipt invalidation, delivery state and scheduling; runtime-to-finalizer integration | Mocked hosts and Judges do not establish writing quality or review independence |
| `worktrees` | Real temporary Git repositories, worktree creation, ownership and path boundaries | Not multi-user security isolation |
| `win11-patch` | Patch parsing, release/state guards and staged local fixtures | Linux CI does not deploy or activate a Windows App update |
| `proxy-relay` | Config generation, candidate selection, payload validation and failure handling | Stubbed transport does not establish a live network route |

The `agent-tools-regression` CI workflow runs these suites on every PR and main
push. Its status remains named `linear-workflow-runtime` solely because the
existing GitHub ruleset requires that name. There is no Linear planning gate.
Whitespace checks supplement regression tests; they are not acceptance evidence.
The redundant compile/import and duplicate adapter-validation steps were removed.

## Historical compatibility

CI builds and tests the retained Linear wheel only when its source, package
manager/descriptor, runner or CI wiring changes, or on manual dispatch. This
checks packaged schemas as well as compatibility behavior. It does not install
or activate the retired Skills on the runner. To run it locally:

```bash
python -m pip install ./linear_workflow/shared/runtime
python scripts/run_regression_tests.py linear-compatibility
```

The adapter suite owns the single generated-adapter consistency check. Old
Agent Workflow record tests remain in the default repository suite because that
runtime is still installed and can serve existing records. It is separate from
Linear Workflow.

## What counts as evidence

A regression test should name the externally observable failure it prevents.
Keep different boundaries even when their tests share terms such as idempotency
or stale evidence. Replace checks of an implementation string or the behavior of
a test double when a real interface can be exercised safely. Source/metadata
checks are appropriate for fixed package contracts, but cannot prove execution.
When changing a guard, deliberately break the relevant behavior in an isolated
copy and verify that the intended assertion fails, rather than an import/setup
error. Do not add production bypass flags just to make mutation tests possible.

Historical-case oracle tests validate the evaluator itself; they are not extra
Agent evaluations. CI reruns the same regressions and is not a second independent
test population. Independent review examines requirements, implementation and
missing cases; it is not another numerical test suite. Judge semantics, writing
quality, native hook activation and live service behavior need their respective
real-scene checks; a green automated suite does not establish those outcomes.

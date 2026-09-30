# Contributing

Follow the current user-authorized task scope. Linear Workflow is deprecated
and disabled; no Linear Batch is required. Retained source does not justify
running its historical internals on every PR.

## Keep failure coverage, not a fixed test inventory

No particular test method is indispensable. Retain a check only while a current
consumer needs its protected behavior, or as an explicitly historical check.
For a retained scenario, identify the concrete failure, its input and observable
result, the closest overlapping test, and the cheaper alternative. Prefer the
alternative when it preserves that failure detection. A passing result or a
large count is not a reason to retain a test.

Use direct functions for input/rule matrices. Keep representative CLI, installer
and hook tests where argument forwarding, exit status, disk effects or process
lifecycle are the risk; a function-only test cannot observe those boundaries.
Do not mock the behavior being claimed. Shared helper setup is useful; combining
method names without reducing setup/execution does not itself make tests cheaper.
Source checks may guard a fixed package contract but cannot prove execution.

When changing a guard or replacing a weak test, break the relevant behavior in
an isolated copy and check that the intended assertion fails, rather than an
import/setup error. Production bypass switches are not a testing requirement.

## Run and scope regressions

Use Python 3.11+ in an isolated environment, with Git, Bash and Node.js on PATH.
Only the report parser suite needs additional packages, at the versions used by
`skills/work-report/scripts/report_tool.py`:

```bash
python -m pip install markdown-it-py==4.0.0 PyYAML==6.0.2
python scripts/run_regression_tests.py active
python scripts/run_regression_tests.py active --changed-from origin/main --list
python scripts/run_regression_tests.py active --changed-from origin/main
```

`--changed-from` compares committed revisions, not uncommitted edits. Omit it
for a full active run or pass one suite name below for local work. Each suite
runs in its own process to avoid Python module-name collisions. A root test
module has one owner; a new unclassified module fails explicitly. Empty or
entirely skipped selected suites, failed imports and failed assertions fail.
Partial skips remain visible and do not establish platform coverage.

| Suite | Reason to keep this boundary | Thinner execution / limits |
|---|---|---|
| `task-runtime` | Revision conflicts, evidence validity, cleanup ownership, interrupted recovery and query consistency can corrupt or misrepresent real task state | Temporary SQLite/filesystem scenarios on Task Runtime or shared fixture changes; no model runs |
| `workflow-records` | Existing legacy records still use installed Agent Workflow authorization, snapshots and hooks | Separate from retired Linear; run on its runtime/installer changes, not every task edit |
| `learning` | Installed routing/actions, teaching structure, staged Git input and package rollback have different consumers | Rule matrices use direct validator calls; representative CLI/hook tests check integration. No teaching-quality claim |
| `report-integration` | Installers, timer and hook adapters can misconfigure otherwise correct report code | Run with affected report adapters; no live model or scheduler service required |
| `reports` | Report evidence, receipt invalidation, scheduling and delivery state must agree at their actual boundaries | Parser rules plus representative real runtime/finalizer integration. Stub Judges do not prove writing quality |
| `installation` | Cross-profile writes, unsafe defaults and destructive removal of foreign installations affect user state | Isolated profiles and real helpers on installer/dependency changes. Native-platform source checks remain limited |
| `worktrees` | Git worktree operations must respect paths, ownership, unsupported flags and existing state | Temporary Git repositories on component/installer changes |
| `win11-patch` | Patcher parsing, state preservation and snapshot payloads protect native update preparation | Component-only fixture checks; Linux CI does not prove native App activation or rollback |
| `proxy-relay` | Generated configuration and selection rules must reject failed probes and preserve manual choices | Component-only deterministic inputs; mocked transport does not prove a live network route |
| `evaluation-fixtures` | Historical-case oracles and the optional evaluation driver must reject deliberately broken outputs | Only their own/fixture changes; evaluator tests are not Agent evaluations |
| `test-runner` | Wrong suite selection, empty discovery and swallowed failure/skip results would hide missing coverage | Fast tests on runner/CI changes; not a second product acceptance suite |

The selector in `scripts/run_regression_tests.py` owns component dependencies.
Shared installer/guard/CI changes and unknown production paths conservatively
select all active suites; known component changes select their consumers.
Documentation-only changes run whitespace checking and still need content
review; unchanged runtimes are not evidence about prose. Report dependencies
are installed only when the report suite is selected. No selector or green CI
run establishes coverage of product behavior for which no test exists.

## CI and historical checks

`agent-tools-regression` runs affected suites on PRs and main pushes. Manual
workflow dispatch runs all active suites. The job's status remains named
`linear-workflow-runtime` only because the existing GitHub ruleset requires that
name. There is no Linear planning gate. CI repeats regression tests; it is not
another independent test population. Independent review evaluates requirements,
implementation and gaps, not another numerical suite.

Historical Linear internals are manual-only. To validate their packaged schemas
and compatibility behavior locally:

```bash
python -m pip install ./linear_workflow/shared/runtime
python scripts/run_regression_tests.py linear-compatibility
```

Manual CI dispatch can include them with `historical_compatibility`. The old
acceptance-harness self-tests are also explicit-only:

```bash
python scripts/run_regression_tests.py workflow-acceptance
```

The `repository` alias deliberately runs all top-level tests, including those
historical harness self-tests. Normal `active`/affected runs do not. Historical
code retention is not approval to activate retired Skills. Keep active installer
checks that prevent reactivation or preserve modified/user-owned files.

Native hook activation, native Windows deployment, semantic Judge accuracy,
writing quality and live service behavior need their own real-scene checks.
They must not be claimed from these deterministic suites.

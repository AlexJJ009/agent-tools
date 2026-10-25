# Contributing

Follow the current user-authorized task scope. Linear Workflow is retired and
its source was removed; no Linear Batch is required.

## Reconcile documentation before delivery

Update affected usage in its owning guide. Consult [ADRs](docs/decisions/README.md)
when changing a durable architectural choice: state ownership, component
responsibilities, cross-component contracts or a costly-to-reverse dependency.
Routine fixes, test/CI maintenance and reinstalls normally need no ADR or
"no ADR change" declaration. A diff touching an ADR-related component alone is
not a trigger. When a significant decision changes, explain its rationale and
trade-offs using the existing project format; do not turn each PR into a record.
The Agent makes this judgment; runtime and Hooks do not infer decisions.

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
The suites need no third-party packages.

```bash
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
| `claude-adapter` | Settings edits, skill links and the generated context view touch the user's Claude profile and must keep foreign settings and entries | Temporary profiles with fixture install roots; no Claude CLI and no hook execution |
| `learning` | The kept teaching artifact validator, vault pre-commit check and the shared writing contract copy must stay consistent | Rule matrices use direct validator calls; a few CLI/Git cases check integration. No teaching-quality claim |
| `installation` | Cross-profile writes, unsafe defaults, skill-link replacement and destructive removal of foreign installations affect user state | Isolated profiles and real helpers on installer/dependency changes. Native-platform source checks remain limited |
| `worktrees` | Git worktree operations must respect paths, ownership, unsupported flags and existing state | Temporary Git repositories on component/installer changes |
| `project-evals` | Project-local build-eval and hillclimb skills must reject deliberately broken outputs | Only their own changes; evaluator tests are not Agent evaluations |
| `test-runner` | Wrong suite selection, empty discovery and swallowed failure/skip results would hide missing coverage | Fast tests on runner/CI changes; not a second product acceptance suite |

The selector in `scripts/run_regression_tests.py` owns component dependencies.
Shared installer/guard/CI changes and unknown production paths conservatively
select all active suites; known component changes select their consumers.
Documentation-only changes run whitespace checking and still need content
review; unchanged runtimes are not evidence about prose. No selector or green CI
run establishes coverage of product behavior for which no test exists.

## CI and historical checks

`agent-tools-regression` runs affected suites on PRs and main pushes. Manual
workflow dispatch runs all active suites. The `main` ruleset requires its
`regression` status check; renaming the job requires changing the ruleset in the
same step. There is no
Linear planning gate. CI repeats regression tests; it is not another independent
test population. Independent review evaluates requirements, implementation and
gaps, not another numerical suite.

The `repository` alias runs every top-level test module in one pass. Keep active
installer checks that remove stale retired copies only when verified and
preserve modified/user-owned files.

Native Windows deployment, writing quality and live service behavior need their own real-scene checks.
They must not be claimed from these deterministic suites.

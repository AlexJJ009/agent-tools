# Contributing

Linear Workflow changes follow the shared [contribution contract](linear_workflow/shared/references/contribution-contract.md), [lifecycle](linear_workflow/shared/references/lifecycle.md), and machine-readable [gate policy](linear_workflow/shared/gate-policy.json).

Use the full `owner/repository`, Linear Batch and Issue IDs, full base/candidate SHAs, and one primary PR per Batch repository. Feature-branch full validation runs through a Pull Request; ordinary feature pushes do not duplicate it. A human retains merge authority, especially for High-risk work.

The reusable `.github/actions/linear-workflow-pr-check` action validates normalized evidence using the exact base revision. Missing checks, stale candidate/review evidence, invalid identity or DAG data, and missing gate self-tests fail closed.

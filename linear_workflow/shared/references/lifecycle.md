# Linear Workflow lifecycle

Linear owns Project, PRD, Issue DAG, Batch membership, risk, and execution status.
The native issue statuses are `Backlog`, `Ready`, `In Progress`, `In Review`,
`Blocked`, `Done`, and `Canceled`; status labels must not duplicate them.

Only a human-approved `Ready` Batch can enter Delivery. Delivery moves it to
`In Progress`, executes its leaf Issues in dependency order, then fixes one
candidate SHA and moves the Batch to `In Review`. Contract conflict, undeclared
repository, scope expansion, or irreversible work moves the Batch to `Blocked`.
`Done` remains subject to the repository's merge or release policy.

An Issue is an independently verifiable tracking unit. It does not imply a
separate branch, PR, full CI run, or Agent session. A Delivery Batch is the
smallest unit that fixes a candidate, runs full CI, and receives review.

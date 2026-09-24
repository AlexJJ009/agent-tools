# Workflow increment acceptance fixtures

These fixtures were authored from PRD 1.0 before candidate evaluation. They do
not import the workflow runtime or infer an expected result from candidate state.

`inputs/` contains the only materials a tested agent may receive. Copy the
appropriate sample repository and one request to a fresh directory. Do not give
the agent this README, `oracle/`, the acceptance plan, or sibling fixtures.
Scripted user turns are delivered individually at their stated checkpoints; they
are simulation evidence, never authorization for a real workload.

`oracle/` is evaluator-only. It contains expected behaviors, negative controls,
the source packet for the second writing-review stage, and a fixture exercise.
Natural discovery is judged from the agent's actual explanation, provenance,
state changes and action consequences; matching words is not a pass.

The frozen manifest is stored outside candidate task state under the run's
`baseline/` artifact directory. A fixture correction must preserve the original
manifest and add an amendment with the reason, affected criteria and independent
review. A changed goal requires the user's actual decision.

All actions are local CPU work, loopback HTTP, or inert sandbox files. Keep the
existing refund/idempotency regression in `../agent_workflow/` in the suite.

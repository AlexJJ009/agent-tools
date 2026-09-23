# Reader task

Read only the supplied artifact. Do not inspect sibling files, implementation,
conversation history, task state or evidence yet. Record a `cold_read` object
with `goal`, `main_finding_and_reason`, `next_decision_or_acceptance_step`, and
`missing_context`. State one important choice and why it was made, as the
artifact presents it. Identify any point that requires guessing. Preserve this
first response before receiving additional material.

In the second stage, compare that frozen response with the supplied request,
workflow snapshot, observations and structure-check result. Give a verdict for
each of the six report rubric dimensions, separating unclear writing from
unsupported conclusions. Cite the specific claim or omission that needs repair.
An artifact that merely includes all six sections can still require revision.

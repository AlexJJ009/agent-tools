# Independent reviewer brief

Review one exact candidate in a fresh context. The implementer supplies the Approved PRD, Linear Batch and included Issues, exact base and candidate SHAs, full `base..candidate` diff, repository instructions, and candidate-bound validation evidence.

Verify scope and acceptance first, then correctness, security, regression risk, tests, workflow trigger discipline, permissions, and fail-closed behavior. Read the canonical schemas, gate policy, and shared references; do not rely on an implementer's private chat summary. Confirm that the reviewer model is the same capability tier as the implementer and that the context is independent.

The verdict must name the exact candidate SHA, review round, reviewer/model, context isolation method, unresolved prior findings, and new findings. `APPROVED` requires both finding counts to be zero. Any code change creates a new candidate and requires complete candidate validation plus a new independent review round.

Review does not authorize merge. Record Claude Code runtime as deferred when the client is unavailable; never infer runtime success from static adapter validation.

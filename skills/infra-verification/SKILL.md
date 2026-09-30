---
name: infra-verification
description: Verify training, evaluation, Docker, Harbor, GPU, mount, network, lifecycle, timeout, retry, cancellation, and resource cleanup behavior with readback evidence.
---

# Infra Verification

Use this skill for training infra, evaluation infra, Agentic episode infrastructure, launcher/config plumbing, Docker or Harbor environments, GPU allocation, mounts, network setup, checkpoint/recovery, cancellation, retries, and resource cleanup. Investigate only the relevant effects and existing authorization. `infra_heavy` is a retained legacy profile, not a requirement to create a scenario record for every infrastructure change.

## Verification Focus

Record what was actually read back from the target environment. Static source inspection can guide the check, but it does not prove runtime state.

Check the parts that match the current change:

- config path from definition to launcher override to consuming code
- batch, sample, source, gradient accumulation, checkpoint, and recovery semantics
- image tag or digest, container command, mounts, environment variables, GPU visibility, network route, and storage location
- episode lifecycle, tool-call side effects, timeout, cancellation, retry de-duplication, environment reset, and resource cleanup
- short smoke runs or simulations that cannot be confused with formal experiments

## Evidence Levels

Use these distinctions to describe the evidence. For a selected task-runtime task, read `task checklist` and record actual observed checks through `task result`, keeping verification, validity and user acceptance separate. Otherwise use the existing tests, logs and closing explanation; do not create a task or checklist just to classify evidence. Only an existing legacy record stores these levels in `checklist.yaml`:

- `none`: no evidence yet
- `static`: source, config, manifest, or local file inspection only
- `simulated`: fixture, dry-run, local stub, or smoke run that does not exercise the full target environment
- `real`: observed against the actual target command, container, runtime, or service state

Do not upgrade `static` to `real` because a file path exists. Do not treat a successful `K=1` smoke run as evidence for `K=4`.

## Observable effects and local invalidation

Read what the consumer actually used, not a configuration echo. Record argv,
exit status, process output, resource identity and consumed values. For a monitor,
compare server request counts and observation times before and after refresh;
a new display time may only redraw cached data. Keep 429, timeout and other
failures visible even when historical success exists.

When relying on a check, demonstrate a meaningful negative once: an ignored
field, changed override, missing effect or stale success must make it fail. A
sandbox CPU consumer proves consumption only, not learning effectiveness. A
manually supplied Hook event proves handler logic only, not real host refusal.
Technical changes invalidate their dependent evidence; unchanged decisions and
scoped delegation do not reopen merely because a SHA changed.

## Failure Feedback

When a check fails, report the applicable criterion or test, expected value, observed value, code or environment location, command/readback evidence, and the smallest next probe. Feed this back to the coder without changing the agreed target.

Formal experiments, production writes and expensive runs must stay within the actual user authorization, budget and project controls. Where an existing legacy formal-run or protected-action contract applies, use `acceptance-gate` and its managed execution entry with current candidate/config/command evidence; preserve existing bindings. Ordinary infrastructure verification and task-runtime records do not automatically require this legacy gate. They also cannot replace or bypass a gate that actually applies. No check fabricates user acceptance.

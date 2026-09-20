---
name: infra-verification
description: Verify training, evaluation, Docker, Harbor, GPU, mount, network, lifecycle, timeout, retry, cancellation, and resource cleanup behavior with readback evidence.
---

# Infra Verification

Use this skill for training infra, evaluation infra, Agentic episode infrastructure, launcher/config plumbing, Docker or Harbor environments, GPU allocation, mounts, network setup, checkpoint/recovery, cancellation, retries, and resource cleanup. These tasks default to `infra_heavy` when they can affect formal experiments, shared resources, or long-running jobs.

## Verification Focus

Record what was actually read back from the target environment. Static source inspection can guide the check, but it does not prove runtime state.

Check the parts that match the current change:

- config path from definition to launcher override to consuming code
- batch, sample, source, gradient accumulation, checkpoint, and recovery semantics
- image tag or digest, container command, mounts, environment variables, GPU visibility, network route, and storage location
- episode lifecycle, tool-call side effects, timeout, cancellation, retry de-duplication, environment reset, and resource cleanup
- short smoke runs or simulations that cannot be confused with formal experiments

## Evidence Levels

Use these levels in `checklist.yaml`:

- `none`: no evidence yet
- `static`: source, config, manifest, or local file inspection only
- `simulated`: fixture, dry-run, local stub, or smoke run that does not exercise the full target environment
- `real`: observed against the actual target command, container, runtime, or service state

Do not upgrade `static` to `real` because a file path exists. Do not treat a successful `K=1` smoke run as evidence for `K=4`.

## Failure Feedback

When a check fails, report the checklist ID, expected value, observed value, code or environment location, command/readback evidence, and the smallest next probe. Feed this back to the coder without changing the agreed target.

Formal experiments, production writes, and expensive runs remain blocked until `acceptance-gate` confirms current agent checks, human confirmation when required, candidate SHA, config digest, and command digest.

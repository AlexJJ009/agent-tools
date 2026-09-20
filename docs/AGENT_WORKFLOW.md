# Agent Workflow Suite

The agent workflow suite packages five English-language skills with Chinese UI display names:

| Skill | Display name | Purpose |
|---|---|---|
| `intent-to-contract` | 需求与协议入口 | Read back the task, preserve source quotes, ground parameters, and seed checklist items. |
| `infra-verification` | 训练与 Agentic 基础设施验收 | Collect readback evidence for training, Agentic, Docker, Harbor, GPU, mount, network, lifecycle, and cleanup behavior. |
| `cleaner` | 代码整理器 | Perform behavior-preserving cleanup after coder work. |
| `acceptance-gate` | 验收与人工复核 | Enforce checklist status, evidence, human confirmation, and formal-run authorization. |
| `reviewer-brief` | 独立审查 | Produce bounded human review and independent reviewer briefs. |

The runtime is installed as `agent-workflow` for use outside this checkout. The six scenario profiles are `algorithm`, `infra`, `business`, `bug_fix`, `office`, and `learning`.

```text
agent-workflow init --query <request.txt> --scenario <scenario> --context <context.json> --mode simulation
agent-workflow check --record <record-dir> --phase agent
agent-workflow review-brief --record <record-dir>
agent-workflow target --record <record-dir>
agent-workflow approve --record <record-dir> --sha <candidate-sha> --feedback <human-feedback.json> --simulation
agent-workflow revise --record <record-dir> --revision <user-amendment.json>
agent-workflow gate --record <record-dir> --action formal-run --simulation
```

Use `--simulation` only for simulation records. A simulation record can support sandbox checks, but it cannot authorize a real formal experiment or production action. For local non-simulation records, omit `--simulation`.

Records live under `docs/agent-workflow/records/YYYY-MM-DD/YYYYMMDDTHHMMSSZ-<slug>/` and contain `request.txt`, `task.md`, `checklist.yaml`, optional `protocol.md`, optional `reviews/human-review.md`, and `evidence/`.

The installer copies the runtime to `~/.local/share/agent-workflow`, creates the launcher `~/.local/bin/agent-workflow`, and installs the five skills to `~/.agents/skills/`. It runs `scripts/codex_target_guard.py` before any write, rejects unmanaged collisions, and does not edit Codex config, auth, CC Switch databases, history, or existing conversations. `--check` is read-only and verifies installed files against the repository source.

## Context API

The runtime validates Agent-supplied context. It does not infer arbitrary requirements from prose. The Agent investigates the repository and then supplies:

- `items`: verbatim source quotes, normalized values, requirement kinds, authority, ambiguity, and checklist IDs
- `facts`: route facts such as `infra` or `side_effects`
- `bindings`: real config keys, definition anchors, consumer anchors, ordered override anchors, `readback_key`, and watched paths
- `checks`: verifier commands, JSON observation keys, risk, and review scope
- `command`, optional `command_paths`, and `config_paths`: the formal target scope used for the target digest
- `protocol_view`: optional `true` to render `protocol.md` from the canonical checklist record

See [context example](../skills/intent-to-contract/templates/context.example.json), [human feedback](../skills/acceptance-gate/templates/human-feedback.example.json), and [user amendment](../skills/acceptance-gate/templates/user-amendment.example.json).

Routing has two layers. The Agent makes the semantic choice after investigating the task. The runtime performs conservative lint only: for example, a Docker or launcher request without infra facts is rejected, but the runtime does not replace the Agent's judgment with a classifier.

For `command_json` checks, the verifier JSON must expose both the observed value at `observation_key` and, for protocol bindings, the binding identity/value at `readback_key`. The runtime compares `config_key`, `consumer_symbol`, and `value`; this proves the check read the intended adapter output, while actual domain semantics remain the project adapter and human review responsibility. `command_paths` can list protected entrypoint files explicitly; the runtime also auto-includes relative script-like argv paths.

`revise` records actual user amendments without rewriting the original request. The revision JSON points to a source file containing the user's amendment, quotes the exact amendment, and lists protocol updates. A revision updates canonical protocol expectations, writes the amendment source under `evidence/`, invalidates affected items, and preserves previous expectations in the revision event.

## Boundaries

The suite is a local workflow aid. It is not a tamper-proof identity system, a production admission controller, a Linear Ready Batch, or a replacement for human merge authority.

`human_status=confirmed` must come from actual user feedback or an earlier still-valid review of the same object. The tool cannot infer it from a model report. Human feedback capture is the responsibility of the caller that invokes `approve`, and the feedback JSON must include the current target digest emitted by `agent-workflow target`.

Simulation evidence can support local reasoning, but it never authorizes a real formal experiment or production action. Formal runs bind the current candidate SHA, config digest, command digest, agent checks, and required human confirmation.

Review briefs reuse Work Report's existing rubric/template discipline for evidence presentation and local path:line link conventions. The runtime does not run the Work Report Judge as acceptance, does not duplicate Work Report state, and does not let a Work Report quality pass approve code or update gate state.

## Attribution

This suite adapts small workflow structures from saved MIT-licensed snapshots:

- `github/spec-kit` at `d4229c071c7ea3885b43e8a7739847300f618f13`
- `obra/superpowers` at `5bf4e78011075bcfc0dc295f0724994cd123ee71`

The copied license texts are in `docs/agent-workflow/licenses/`. The original saved license files are also in the PRD work-report reuse directory. SwarmForge is used only as a mechanism reference for coder-to-cleaner sequencing; no SwarmForge prompt or source text is copied because the local snapshot did not verify a license.

## Local acceptance and project adoption

Run `python3 -m unittest tests.test_agent_workflow tests.test_install_agent_workflow` from the checkout. Set `WORKFLOW_TEST_EVIDENCE` to a new output directory to retain every runtime CLI call, exit code, stdout/stderr, fixture Git repository and record. The expected values in `tests/fixtures/agent_workflow/oracles.json` and `tests/workflow_support.py` are fixture-author annotations, not runtime-generated expected answers.

The current installation does not add trusted Codex hooks or modify project training/production entrypoints. A project must call `agent-workflow gate --record ... --action formal-run` immediately before its protected action and honor a nonzero exit. The CLI itself never launches the formal command. Do not describe this voluntary local gate as a sandbox or an unbypassable permission boundary.

`checklist.yaml` uses JSON syntax (a YAML 1.2 subset) to avoid adding runtime dependencies. Arbitrary YAML syntax is not supported. Generated `task.md` status blocks and optional `protocol.md` derive from the canonical record; keep implementation errors, cleaner outcomes, running task handles and next actions in the existing task work-record section.

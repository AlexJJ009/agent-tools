---
name: teaching-dag-builder
description: Build or audit explicit knowledge prerequisite DAGs, KC ids, dependency edges, and current frontier nodes. Use for requests that explicitly ask for a prerequisite graph, DAG, KC map, dependency audit, frontier, or missing background map.
---

# Teaching DAG Builder

Build a local graph of knowledge components (KCs) that explains what must be understood before the target idea becomes natural.

## Workflow

1. Name KCs as stable ids such as `kc_ucb_confidence_bonus`.
2. Write one-sentence learner-facing meanings, not encyclopedia definitions.
3. Add prerequisites only when a learner would fail without them.
4. Classify edges as `strict`, `common`, or `convenience`.
5. Mark the current frontier: KCs that are useful next and whose prerequisites are already satisfied or explicitly waived.

Read `references/dag-building.md` for edge semantics and anti-patterns. Use the shared contract at `../teaching-reconstruction/references/artifact-contract.md` for durable manifests.

## Output shape

Return a compact table or manifest fragment with KC id, label, prerequisites, edge type, frontier status, and evidence/check placeholders. Escalate to `evidence-anchor` when a KC or edge depends on a source claim.

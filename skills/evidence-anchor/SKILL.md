---
name: evidence-anchor
description: Create source-specific EvidenceAnchors for paper, code, log, and web claims. Use when explicitly asked to anchor, verify, cite exact lines/pages, distinguish verified versus provisional evidence, or audit whether a claim is traceable.
---

# Evidence Anchor

Attach claims to locators precise enough for another agent to re-check them.

## Workflow

1. Identify the claim role: claim, mechanism, limitation, comparison, or reproduction. A claim role describes what the sentence does; it is not an EvidenceAnchor `layer`.
2. Assign only a schema-valid EvidenceAnchor layer. Allowed layer values: `source_fact`, `runtime_fact`, `inference`, `design_mapping`, `teaching_reconstruction`, `advice`.
3. Choose the source kind: paper, code, log, or web.
4. Record verified locators only when immutable or source-specific enough; otherwise mark the anchor provisional.
5. Preserve boundaries: evidence supports a claim; it does not automatically justify teaching edges or learner mastery.

Read `references/evidence-anchors.md` for required fields by source kind. Use the shared contract at `../teaching-reconstruction/references/artifact-contract.md` for durable manifests.

For paper PDFs, annotations, Zotero keys, or managed regions, route through `teaching-reconstruction` so it can invoke the installed `read-paper` adapter.

# Acceptance profiles

Select applicable checks at intake and acceptance. Keep one general Coder; normal debugging, dependency substitutions and locating renamed symbols do not restart routing or demand a new PRD.

| Profile | Check selection | Escalation |
|---|---|---|
| algorithm | Method/source comparison; parameter definition -> override -> actual consumer readback; independent small tensor/scorer positives and near-miss rejects; budget | Loss, mask, sampling, filtering, score meaning and expensive runs need focused human review |
| training infra | Configuration propagation, sample/batch mapping, gradient accumulation, checkpoint and restore, GPU/mount/network/environment readback | Default `infra_heavy`; inspect distributed semantics and resource limits |
| Agentic infra | Image/container identity, episode lifecycle, tool effects, timeout/cancel, retry deduplication, environment reset and resource cleanup | Default `infra_heavy`; never use mock state as target Docker/GPU proof |
| business | User path, interface contract, previous behavior, permission and target-state readback | Billing/refunds, migrations and production writes require side-effect regressions and human focus |
| bug_fix | Reproducer, smallest repair, affected-path regression, quick Cleaner or explicit deferred cleanup with owner/trigger | New material side effects add only affected checks; recovery does not wait for a full PRD |
| office | Audience and purpose, authoritative facts/numbers, structure, editing cleanup, actual exported pages | External promises, sensitive data and publishing require the applicable human decision |
| learning | Existing teaching-reconstruction/read-paper skills; sources, notes and understanding checks as requested | No code Cleaner or formal-run gate for explanation alone |

For office requests create distinct fact, audience and exported-output requirements. Bind them to material/data cells/output pages, not fabricated code symbols. Missing source facts or a target artifact stays unverified; do not run pytest or label source inspection as successful export. Use an available document/slides tool suited to the requested output; do not auto-publish.

For mixed delivery and learning, identify the two deliverables and applicable checks in one task agreement. For mixed algorithm and infra, combine checks without duplicate task files. Respect a project's existing Linear Ready Batch/CI requirements when they apply; local records do not supersede those authorities.

Checklist expectations are derived from the canonical protocols. Proposals (extra seeds, full CI, benchmarks, broad refactors) remain proposals unless adopted; do not silently require them for small tasks. Preserve known failures and unchanged valid evidence. Use `check --item <ID>` after repairing only the affected binding/implementation.

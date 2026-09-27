---
title: Good provisional evidence anchors fixture
---

# Provisional evidence anchors

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-good-provisional-anchors",
  "mode": "guided",
  "goal": {"target_ability": "Distinguish provisional from verified evidence.", "success_criteria": ["Keep mutable evidence provisional", "Name what verification still requires"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md"], "assumptions": ["The learner knows claims can outlive mutable sources."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.provisional", "explanation": "Incomplete mutable locators are useful leads, not verified proof.", "worked_step": "Classify each locator before citing it.", "next_action": "Retrieve the four verification requirements."},
  "knowledge_components": [
    {"id": "kc.provisional", "ability": "Classify incomplete locators as provisional.", "state": "fragile", "definition": "A provisional anchor identifies a lead but does not meet the verified locator contract.", "why_needed": "Mutable source references must not masquerade as durable proof.", "prerequisites": [], "witnesses": ["anchor.paper.provisional", "anchor.code.provisional", "anchor.log.provisional", "anchor.web.provisional"], "worked_example": "A branch and path remain provisional until bound to an immutable revision and line span.", "checks": ["check.provisional.reconstruct", "check.provisional.retrieve"]}
  ],
  "teaching_edges": [],
  "frontier": ["kc.provisional"],
  "evidence_anchors": [
    {"anchor_id": "anchor.paper.provisional", "claim": "A Zotero parent item was identified, but not a PDF page.", "source_kind": "paper", "layer": "source_fact", "status": "provisional", "verified_at": "2026-08-20T12:00:00Z", "boundary": "Does not locate the claim in a PDF.", "locator": {"zotero_item_key": "ABCD1234"}},
    {"anchor_id": "anchor.code.provisional", "claim": "A working-tree file may contain the behavior.", "source_kind": "code", "layer": "inference", "status": "provisional", "verified_at": "2026-08-20T12:00:00Z", "boundary": "Does not bind the claim to immutable code.", "locator": {"repository": "agent-tools", "path": "skills/teaching-reconstruction/SKILL.md"}},
    {"anchor_id": "anchor.log.provisional", "claim": "A run emitted a mutable terminal log.", "source_kind": "log", "layer": "runtime_fact", "status": "provisional", "verified_at": "2026-08-20T12:00:00Z", "boundary": "Does not prove retained log bytes.", "locator": {"run_id": "run-provisional", "artifact_path": "tmp/current.log"}},
    {"anchor_id": "anchor.web.provisional", "claim": "A live web page currently contains relevant text.", "source_kind": "web", "layer": "source_fact", "status": "provisional", "verified_at": "2026-08-20T12:00:00Z", "boundary": "Does not preserve a durable snapshot.", "locator": {"canonical_url": "https://example.invalid/teaching", "retrieved_at": "2026-08-20T12:00:00Z"}}
  ],
  "learning_checks": [
    {"check_id": "check.provisional.reconstruct", "kc": "kc.provisional", "type": "reconstruction", "prompt": "Explain why each locator remains provisional.", "success_signal": "Names the missing verified fields for all four source kinds.", "failure_prerequisite": null, "evidence": ["anchor.paper.provisional", "anchor.code.provisional", "anchor.log.provisional", "anchor.web.provisional"]},
    {"check_id": "check.provisional.retrieve", "kc": "kc.provisional", "type": "retrieval", "prompt": "Recall the minimum verified locators without looking.", "success_signal": "Distinguishes paper, code, log, and web requirements.", "failure_prerequisite": null, "evidence": ["anchor.paper.provisional", "anchor.code.provisional", "anchor.log.provisional", "anchor.web.provisional"]}
  ],
  "review_queue": []
}
```

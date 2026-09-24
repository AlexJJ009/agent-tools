---
title: Good guided teaching reconstruction fixture
status: test-fixture
---

# Good guided teaching reconstruction

<!-- teaching-reconstruction:v1 -->

```json teaching-manifest
{
  "schema_version": "teaching-reconstruction:v1",
  "artifact_id": "fixture-good-guided-session",
  "mode": "guided",
  "goal": {"target_ability": "Reconstruct the fixture from traceable evidence.", "success_criteria": ["Explain the target ability", "Pass the linked learning checks"]},
  "learner_state": {"profile_sources": ["reader_profile/index.md", "reader_profile/knowledge_map.md"], "assumptions": ["Fixture learner state is explicit."], "observed_gaps": []},
  "teaching_unit": {"kc": "kc.problem", "explanation": "This unit binds one ability to evidence and a worked step.", "worked_step": "Follow the worked example, then answer from memory.", "next_action": "Run the linked learning check."},
  "knowledge_components": [
    {
      "id": "kc.problem",
      "ability": "Frame the learning problem from evidence.",
      "state": "mastered",
      "definition": "The learner can name the concrete problem being reconstructed.",
      "why_needed": "Problem framing prevents evidence collection from becoming undirected.",
      "prerequisites": [],
      "witnesses": ["anchor.paper.problem"],
      "worked_example": "Given a paper introduction, extract the task and failure mode.",
      "checks": ["check.problem.reconstruct", "check.problem.retrieve"]
    },
    {
      "id": "kc.evidence",
      "ability": "Bind claims to source-specific locators.",
      "state": "callable",
      "definition": "The learner can distinguish paper, code, log, and web locators.",
      "why_needed": "Durable teaching artifacts must remain auditable after the session.",
      "prerequisites": ["kc.problem"],
      "witnesses": ["anchor.code.validator", "anchor.web.hooks"],
      "worked_example": "Map one validator claim to an immutable commit and line span.",
      "checks": ["check.evidence.reconstruct", "check.evidence.retrieve"]
    },
    {
      "id": "kc.transfer",
      "ability": "Transfer the reconstruction into an auditable artifact.",
      "state": "fragile",
      "definition": "The learner can compile a durable artifact and audit its evidence bindings.",
      "why_needed": "The final artifact must support later review and correction.",
      "prerequisites": ["kc.evidence"],
      "witnesses": ["anchor.log.self-test"],
      "worked_example": "Use a self-test log to prove the artifact contract was checked.",
      "checks": ["check.transfer.artifact", "check.audit.artifact"]
    }
  ],
  "teaching_edges": [
    {
      "id": "edge.problem-evidence",
      "from": "kc.problem",
      "to": "kc.evidence",
      "edge_type": "strict",
      "failure_without": "Evidence anchors would lack a claim boundary.",
      "witness": "anchor.paper.problem"
    },
    {
      "id": "edge.evidence-transfer",
      "from": "kc.evidence",
      "to": "kc.transfer",
      "edge_type": "common",
      "failure_without": "The compiled artifact could not be independently audited.",
      "witness": "anchor.code.validator"
    }
  ],
  "frontier": ["kc.transfer"],
  "evidence_anchors": [
    {
      "anchor_id": "anchor.paper.problem",
      "claim": "The paper introduction defines the motivating problem.",
      "source_kind": "paper",
      "layer": "source_fact",
      "status": "verified",
      "verified_at": "2026-08-20T12:00:00Z",
      "boundary": "Only supports the problem statement, not implementation details.",
      "locator": {
        "zotero_item_key": "ABCD1234",
        "zotero_pdf_key": "PDF5678",
        "page": 3
      }
    },
    {
      "anchor_id": "anchor.code.validator",
      "claim": "The validator branch enforces typed teaching edges.",
      "source_kind": "code",
      "layer": "runtime_fact",
      "status": "verified",
      "verified_at": "2026-08-20T12:00:00Z",
      "boundary": "Only supports the named validator behavior.",
      "locator": {
        "repository": "agent-tools",
        "revision": "d59e3e681edcb1b514a1ba4c8788804b87d6db98",
        "path": "skills/teaching-reconstruction/scripts/validate_teaching_artifact.py",
        "line_start": 120,
        "line_end": 168
      }
    },
    {
      "anchor_id": "anchor.log.self-test",
      "claim": "The validator self-test produced recorded output.",
      "source_kind": "log",
      "layer": "runtime_fact",
      "status": "verified",
      "verified_at": "2026-08-20T12:00:00Z",
      "boundary": "Only proves the recorded command output.",
      "locator": {
        "run_id": "run-2026-08-20-validator-self-test",
        "artifact_path": "docs/teaching-skills-suite/evidence/validator-self-test.log",
        "artifact_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "timestamp": "2026-08-20T12:00:00Z",
        "line_start": 1,
        "line_end": 20
      }
    },
    {
      "anchor_id": "anchor.web.hooks",
      "claim": "The Stop hook contract uses JSON stdout and stop_hook_active semantics.",
      "source_kind": "web",
      "layer": "source_fact",
      "status": "verified",
      "verified_at": "2026-08-20T12:00:00Z",
      "boundary": "Only covers the fetched OpenAI Hooks documentation snapshot.",
      "locator": {
        "canonical_url": "https://learn.chatgpt.com/docs/hooks",
        "retrieved_at": "2026-08-20T10:00:00Z",
        "snapshot_path": "docs/teaching-skills-suite/sources/openai-hooks-2026-08-20.md",
        "snapshot_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "zotero_item_key": "WEBHOOKS1"
      }
    }
  ],
  "learning_checks": [
    {
      "check_id": "check.problem.reconstruct",
      "kc": "kc.problem",
      "type": "reconstruction",
      "prompt": "Reconstruct the problem in your own words.",
      "success_signal": "Names the task, failure mode, and evidence boundary.",
      "failure_prerequisite": null,
      "evidence": ["anchor.paper.problem"]
    },
    {
      "check_id": "check.problem.retrieve",
      "kc": "kc.problem",
      "type": "retrieval",
      "prompt": "State the problem without looking back.",
      "success_signal": "Recalls the problem and why it matters.",
      "failure_prerequisite": null,
      "evidence": ["anchor.paper.problem"]
    },
    {
      "check_id": "check.evidence.reconstruct",
      "kc": "kc.evidence",
      "type": "reconstruction",
      "prompt": "Explain why immutable source locators matter.",
      "success_signal": "Mentions source-kind-specific locator requirements.",
      "failure_prerequisite": "kc.problem",
      "evidence": ["anchor.code.validator", "anchor.web.hooks"]
    },
    {
      "check_id": "check.evidence.retrieve",
      "kc": "kc.evidence",
      "type": "retrieval",
      "prompt": "List the required locator fields by source type.",
      "success_signal": "Lists paper, code, log, and web locator fields.",
      "failure_prerequisite": "kc.problem",
      "evidence": ["anchor.code.validator", "anchor.log.self-test", "anchor.web.hooks"]
    },
    {
      "check_id": "check.transfer.artifact",
      "kc": "kc.transfer",
      "type": "artifact_transfer",
      "prompt": "Transfer the reconstruction into a durable artifact.",
      "success_signal": "Produces a version-marked artifact with manifest and anchors.",
      "failure_prerequisite": "kc.evidence",
      "evidence": ["anchor.log.self-test"]
    },
    {
      "check_id": "check.audit.artifact",
      "kc": "kc.transfer",
      "type": "artifact_audit",
      "prompt": "Audit the artifact against the manifest and evidence anchors.",
      "success_signal": "Finds structural or locator violations without prose search.",
      "failure_prerequisite": "kc.evidence",
      "evidence": ["anchor.log.self-test"]
    }
  ],
  "review_queue": [
    {
      "card_id": "card.transfer",
      "kc": "kc.transfer",
      "prompt": "Review whether the transfer check is still fragile.",
      "due_or_trigger": "after next artifact compilation",
      "target_note": "[[notes/teaching/good_guided_session]]",
      "check_id": "check.transfer.artifact",
      "status": "open"
    }
  ]
}
```

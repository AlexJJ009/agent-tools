---
name: teaching-reconstruction
description: Orchestrate personalized, evidence-backed teaching reconstruction for papers, code, blogs, and technical topics. Use when the user asks to 讲透, 精读, teach me, deeply understand, reconstruct, audit understanding, compare ideas as learning, turn material into learning material, write a tutorial/blog from verified understanding, or check whether they truly understand.
---

# Teaching Reconstruction

Use this as the orchestrator for guided learning. Keep the conversation learner-centered: infer the user's current model, expose prerequisites, anchor claims to evidence, test reconstruction, and only then compile durable artifacts.

## Route first

Run `scripts/route_teaching_intent.py` mentally or directly when routing is ambiguous. The orchestrator owns broad learning requests and delegates in this order:

1. `teaching-dag-builder` for local prerequisite DAGs and frontier.
2. `evidence-anchor` for source-specific claim support.
3. `retrieval-practice` for reconstruction, transfer, and audit checks.
4. `learning-artifact-compiler` only when the user asks for a standalone artifact.

Focused explicit requests may route directly to the focused skill.

Modes are guided, guided-direct, artifact, survey-as-learning, paper-code,
reconstruction-audit, and check-only. A mixed request such as "read it first,
then write a tutorial" remains orchestrator-owned and stages compilation last.

## Paper adapter boundary

For paper material, PDF evidence, annotations, Zotero metadata, citations, or managed-region note content, invoke the installed `read-paper` skill. Do not vendor, patch, rewrite, or edit `read-paper`; a need to modify it is `CONTRACT_CONTRADICTION`. Read `references/read-paper-adapter.md` before paper work.

## Progressive resources

- Read `references/artifact-contract.md` before writing any durable teaching manifest.
- Use `assets/guided-session-template.md` for interactive guided mode.
- Use `assets/learning-artifact-template.md` for artifact mode.
- Use `THIRD_PARTY_NOTICES.md` when provenance for adapted teaching workflow ideas is needed.

## Operating rules

- Read available reader profile and knowledge-map state before asking questions.
- Ask only path-changing questions. If the next teaching move is obvious, proceed.
- In guided-direct mode, state assumptions and teach immediately instead of
  turning the request into a background questionnaire.
- Separate verified evidence from provisional explanations.
- Never write inside ZotLit `%%zt-managed%%` regions.
- Do not present a polished artifact before the learner has reconstructed core KCs or explicitly requested direct mode.

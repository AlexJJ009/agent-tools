---
name: teaching-reconstruction
description: Orchestrate personalized, evidence-backed teaching reconstruction for papers, code, blogs, and technical topics. Use when the user asks to learn or deeply understand a paper, code, blog, or technical topic; reconstruct a mechanism; audit their own understanding; compare ideas as learning; or turn verified learning into a tutorial or blog draft. Direct manuscript writing belongs to academic-writing.
---

# Teaching Reconstruction

Use this as the orchestrator for guided learning. Keep the conversation learner-centered: infer the user's current model, expose prerequisites, anchor claims to evidence, test reconstruction, and only then compile durable artifacts.

## Route first

Use `task-routing` and the live request to determine whether the current activity is learning. The legacy `scripts/route_teaching_intent.py` is not an authority for arbitrary natural-language classification. Once learning is selected, the orchestrator owns broad learning requests and calls focused skills when their work is needed:

1. `teaching-dag-builder` for local prerequisite DAGs and frontier.
2. `evidence-anchor` for source-specific claim support.
3. `retrieval-practice` for reconstruction, transfer, and audit checks.
4. `learning-artifact-compiler` only when the user asks for a standalone artifact.

Focused explicit requests may route directly to the focused skill.

Modes are guided, guided-direct, artifact, survey-as-learning, paper-code,
reconstruction-audit, and check-only. A mixed request such as "read it first,
then write a tutorial" remains orchestrator-owned and stages compilation last.

## Paper adapter boundary

For Zotero library operations, adding a paper, formal close reading, or ZotLit note updates in the configured ReadPapers project, use the `read-paper` project adapter. Other projects may use supplied citations and paper evidence without activating library management. Read `references/read-paper-adapter.md` when the adapter is needed.

## Progressive resources

- Read `references/artifact-contract.md` before writing a legacy v1 teaching manifest in ReadPapers. For new durable learning outside ReadPapers, use `references/portable-learning-record.md` when a record is needed. Do not force v1 Zotero locators or Obsidian review cards into code learning.
- Use `assets/guided-session-template.md` for legacy v1 ReadPapers guided records; use the portable record outside that scope when a record is needed.
- Use `assets/learning-artifact-template.md` for legacy v1 ReadPapers artifacts; for other artifacts, select a genre-appropriate structure.
- Use `THIRD_PARTY_NOTICES.md` when provenance for adapted teaching workflow ideas is needed.
- Apply W1–W9 from the packaged `../work-report/references/writing-contract.md` to reader-facing explanations. Preserve the teaching sequence and avoid hiding essential prerequisites or revealing exercise answers before the intended stage.

## Operating rules

- Read available reader profile and knowledge-map state before asking questions.
- Ask only path-changing questions. If the next teaching move is obvious, proceed.
- In guided-direct mode, state assumptions and teach immediately instead of
  turning the request into a background questionnaire.
- Separate verified evidence from provisional explanations.
- Never write inside ZotLit `%%zt-managed%%` regions when editing ReadPapers notes.
- Do not present a polished learning artifact before the learner has reconstructed core KCs or explicitly requested direct mode. A request for direct manuscript drafting belongs to `academic-writing` and requires no learner check.

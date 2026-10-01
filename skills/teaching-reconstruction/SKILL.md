---
name: teaching-reconstruction
description: Guide evidence-based learning of papers, code, blogs, and technical topics; explain mechanisms, examine understanding, compare ideas, or develop a requested tutorial. Direct manuscript writing belongs to academic-writing; code repair, quoted teaching templates, and ordinary status explanations do not activate guided learning.
---

# Teaching Reconstruction

Use this as the orchestrator for learning. Infer the learner's mental model, identify prerequisite knowledge, anchor claims to evidence, and assess understanding from actual attempts. Material delivery and learner progress are separate: a complete, reviewed document does not show that the learner read or learned it.

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

## Material and iteration

Main chooses the activity from the request, not the source type. Investigating code for a repair stays delivery; learning its architecture uses this skill. Agent Core supplies stable user context, while Agent Tools owns reusable teaching, domain methods, practice, and learning-document rules. The old `knowledge-deposition-doc` name is a compatibility entry, not a second orchestrator.

Deliver a complete, coherent first draft at the requested scope; practice is not a prerequisite for receiving an explanation or artifact. Choose direct explanation, guided inquiry, or practice to fit the learner's question, prior knowledge, and feedback; adapt scaffolding without imposing tiny teaching units or a pacing questionnaire.

For substantial material, establish the problem and mechanism, organize sections around useful questions, and explain prerequisite knowledge where needed. Readers may enter selectively or respond partway through. Revise the same artifact at the appropriate scale while preserving unaffected evidence.

For code and architecture learning, read `references/code-architecture-learning.md`. For papers, retain problem, motivation, contribution, assumptions, and experimental-evidence questions through the ReadPapers adapter when applicable. Shared expression principles do not impose a paper-innovation template on code learning.

Within a learning session, select a manageable set of abilities worth retaining and practicing, based on the learner's interest and effort; this does not limit document coverage or prescribe a question count. Call `retrieval-practice` for domain-appropriate checks and later review; its `references/review-follow-through.md` owns attempt and follow-up conventions. A reviewer's pass assesses the material only. Keep reading progress, observed attempts, and user-selected retention separate; unknown progress remains unknown.

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
- Mark untested abilities as untested; artifact quality is not evidence of learner mastery.

### Current delivery binding

When the user requests a legacy v1 teaching artifact governed by `references/artifact-contract.md`, bind only that applicable artifact for Stop validation. Portable learning notes and genre-specific outputs do not acquire v1 manifest requirements; use their own applicable checks. With an existing route, include its exact output path in `output_targets`, then run `learning-workflow bind --record <record> --session-id <native-session-id> --workspace <workspace> --teaching-artifact <path>`. Repeat the artifact option for each requested teaching output. Rebind after classifying new input; unbind when the delivery ends. For direct validation without a route, run `scripts/stop_validate.py --artifact <path>` with the current hook payload. Missing paths still fail. Historical examples, material references, ordinary reports, and ordinary conversation do not establish teaching delivery obligations. If a requested artifact cannot be located, report that specific gap instead of searching transcript history for a replacement.

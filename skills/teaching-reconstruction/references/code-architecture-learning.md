# Code and architecture learning

Use this method after Main selects learning. Source inspection for a bug fix, API lookup, or implementation task does not itself select teaching or require a document. This reference consolidates the engineering-learning methods previously maintained in Agent Core's `knowledge-deposition-doc`.

## Questions the explanation should answer

Organize around the user's engineering question, using these dimensions where relevant rather than as mandatory chapters:

- Problem and constraints: what task must the system accomplish, and what concrete failure or limitation shapes it?
- Task decomposition: how does the overall task become smaller operations, and why are those boundaries useful?
- Module separation: what does each module own, what interface does it expose, and which changes can it absorb without changing its callers?
- Architecture and responsibility: who decides, who executes, and who owns mutable state, lifecycle, and resources?
- Control flow: what starts an operation, orders or branches it, handles failure or cancellation, and determines completion?
- Technology and trade-offs: why might this implementation use these libraries, protocols, concurrency mechanisms, or storage choices; what alternatives and costs matter under its actual constraints?

Do not invent the author's design intent. Distinguish a documented rationale from an engineering explanation inferred from the implementation. Research novelty is not a required assessment axis; if a paper accompanies the implementation, distinguish the paper's claim from what this version implements.

## Build understanding through an actual execution

Establish the problem and a compact working model before presenting a component inventory. Use one real request, job, or data object to connect decomposition and architecture to behavior. Define the fields and terms needed at each step; then show inputs, decisions, state changes, outputs, and cross-module handoffs. A sequence diagram helps when ordering matters, but explain unfamiliar diagram notation before relying on it.

Walk through a consequential failure or changed requirement when it reveals the design boundary: a timed-out worker, a duplicate request, cancellation, a new backend, or concurrent access. Explain who detects it, what remains true, and what must change. Avoid adding every possible failure case to a simple usage lesson.

Identify the repository/version and source locations behind material claims. Separate observed code, behavior predicted from that code, behavior actually exercised, architecture inference, and recommendations. Reading a cleanup branch is not proof that cancellation releases resources at runtime. Preserve commands, failures, and historical decisions when compiling a post-investigation retrospective; do not replace them with an invented ideal design story.

Use prior knowledge only where supported. Familiarity with training does not prove familiarity with async lifecycles or module ownership. If a missing prerequisite becomes apparent, explain it in place and revise the affected material. Supply a coherent full first draft when requested; feedback may warrant either a local edit or a substantial rewrite. A full draft does not imply that the learner read every section.

## Practice and reusable material

Use `retrieval-practice/references/domain-practice.md` from the installed sibling skill for trace reconstruction, decomposition, coupling diagnosis, control-flow prediction, and design trade-offs. Select up to three retention targets through the orchestrator; do not require one exercise of every type. An exercise is a prompt for an actual attempt, not evidence of competence because it appears in the document.

Use `learning-artifact-compiler` when a standalone tutorial, study note, or retrospective is requested. Reuse the current artifact during revision. Apply the shared writing contract; choose Obsidian conventions only for an Obsidian destination. Long or consequential material may benefit from an independent factual/reader review under the applicable task, but no extra universal Reviewer gate is introduced here.

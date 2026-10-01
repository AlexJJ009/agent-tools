---
name: task-routing
description: Classify a continuing request by current activity, explicit exclusions, and project scope before selecting learning, writing, curation, or delivery capabilities. Use for mixed or changing tasks; do not invoke as a keyword classifier for every short answer.
---

# Task Routing

The Main Agent decides the current activity from the user's latest request, the still-active agreement, explicit exclusions, and material ownership. A topic word, cwd, quoted source instruction, or installed skill does not authorize an activity switch. Ordinary explanation needed to complete a development request remains delivery. Honor "do not teach", "no exercises", and similar exclusions even when the same request mentions a paper or learning term.

Choose one current activity: `delivery`, `learning`, `writing`, `curation`, or `answer`. Select the capabilities needed for that activity; a capability can be reused in several activities. Use `direct`, `guided`, `practice`, or `review` interaction mode. For an explicitly ordered request, preserve the requested order within and across activities; keep a continuation point for unfinished stages. A planned later stage does not replace unfinished delivery.

`knowledge-deposition-doc` is the legacy compatibility name for the Agent Tools learning suite. It does not select an activity by itself. Code/architecture learning uses `teaching-reconstruction` and its domain reference; a requested standalone learning document uses `learning-artifact-compiler`, including a complete first draft before any learner checks. Choose pacing from the request and feedback rather than forcing tiny units. Agent Core supplies stable context, not a competing learning workflow.

Development ownership stays with the existing development skills: requirement refinement, authorized exploration, minimum viable product (MVP), implementation, iteration, review, and acceptance are all `delivery`. Autonomy applies within the agreed increment or exploration scope; a rough goal or a route decision is not execution authority. Follow that development workflow to establish or reuse its canonical record when it needs one; attach a learning route sidecar only when this workflow is actually needed. Do not create a competing learning task record merely because development is sustained.

For sustained learning/writing or an authorized cross-activity handoff that
needs a persistent route, first read the existing route and canonical development
record, then follow [route record operations](references/route-record-operations.md)
before creating, updating, binding, or recovering state, or using an existing
route for covered actions or curation. Reuse the current record
and actual native session ID; preserve authority, exclusions, and revision checks.
Brief answers need no route file. Missing route state blocks only dependent
actions, not harmless reading or recovery.

Set `readpapers_root` only from an explicit configured project root and `authorized_read_roots` only from user-granted scope; do not invent authority in a decision packet. ReadPapers owns Zotero library operations, adding papers, formal close reading, and ZotLit note updates in its configured project scope. Manuscript projects own drafts and experimental claims; code repositories own implementation and runtime facts. Existing evidence may cross these boundaries as cited material, but source access never grants execution or library write authority. For authorized SSH source reading, record repository, revision, path and observed range; distinguish code observations from executed tests.

For sustained guided learning, inspect whether `teaching-reconstruction` is available; for manuscript drafting or revision, inspect `academic-writing`. These are capability owners after semantic activity selection, not keyword triggers. A model's ability to answer directly is not evidence that the specialized workflow is installed. If the needed skill is absent, tell the user which workflow is unavailable and that you are using a supported direct explanation or draft instead. Continue useful work from available material without claiming the missing skill loaded, silently installing it, or requiring the user to repair the environment first.

For routing itself, use an independent reviewer only for a genuinely disputed mixed intent or consequential route review. Clarify routing when the intended activity cannot be inferred and the answer changes authorized work. These routing limits do not replace development requirements, review gates, MVP feedback, or user decisions required by the existing development workflow. If the user corrects the route, update it and resume the original task at the right stage. Work Report follows its own development reporting trigger; ordinary learning does not create one.

## Outside-project paper requests

When a user requests Zotero ingestion, library management, or formal close reading while the active project is not the already configured ReadPapers project, respond with a concrete ReadPapers handoff. For this boundary response use `activity: answer`, keep the current workspace context, and do not select `read-paper` or declare library actions as authorized here. Preserve the paper identifier/material locator, the requested operation, and the intended note destination in the handoff. Do not instruct the user to turn the current code/manuscript repository into ReadPapers by adding a config file, copying a library, or changing `readpapers_root`. An explicit request to migrate/configure the library project itself is a separate task requiring its own actual scope; a paper-reading request does not imply it. Supplied excerpts and existing evidence can still support local writing or code learning without library operations.

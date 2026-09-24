# Shared writing contract

This is the canonical maintained source for reader-facing work across Work Report,
reviewer-brief, teaching, and academic writing. Packaged copies in Work Report and
reviewer-brief are generated so each can be installed independently. Run
`skills/work-report/scripts/sync_writing_contract.py --write` from the repository
to regenerate them, or `--check` to detect drift.

| ID | Required writing behavior |
|---|---|
| W1 | Lead with the current outcome or decision. Supply the background this reader needs to judge it. |
| W2 | Explain the concrete problem, relevant gap and response where that sequence helps. Give each paragraph a recognizable purpose. |
| W3 | Connect material claims to actual observations and explain why those observations support the judgment. State qualifications that change the decision or next check. |
| W4 | Organize sources around the question they answer; preserve meaningful differences. Use chronology when sequence explains change or recovery. |
| W5 | Show viable options, the selected approach, its reason and consequence. Attribute decisions to their actual source; do not invent retrospective rationale. |
| W6 | Use established domain terms precisely. Explain required concepts before relying on them; connect known information to the next point. |
| W7 | Keep decisive evidence, adverse observations and consequences in the main text. Link logs and identifiers without hiding acceptance-critical facts. |
| W8 | Read current task state. Separate verified behavior, pending checks, decisions and user acceptance; reconcile material conflicts before claiming completion. |
| W9 | First reconstruct the goal, main finding and reason, and next decision from the artifact alone. Then check that reconstruction against request, state and evidence. |

A **readback** is an actual observed value or state, not an expected-value echo.
An **acceptance criterion** is an observable pass condition. **Invalidation**
names why particular evidence no longer applies. **Provenance** identifies a
claim's source and attribution. A **warrant** explains why an observation supports
a judgment. Use these terms only when their concrete relationship is clear.

For example, observing the selected critic weights proves that initialization
was consumed; it does not prove PPO learning quality. An unchanged server
request count after a redraw proves cached display, not current upstream
health. A later 429 remains adverse evidence even when a last-success field
exists. Put those consequences beside the result, not in an appendix.

Apply W1–W9 to the artifact’s actual reader and genre. A brief focuses on its
current choice or acceptance step. A teaching explanation must expose the
prerequisite that makes the next idea understandable; a practice prompt gives
the task and conditions before revealing an answer at the appropriate stage.
A manuscript paragraph follows its scientific argument and reader expectations.
Work Reports retain their six semantic sections and report Judge; neither
requirement transfers to another genre. Use plain paragraphs for a simple
finding; tables and figures serve a real comparison. No quota rewards length,
jargon or decoration.

Machine checks cover structure, snapshots and version binding. Independent
readers assess argument and readability. A schema-valid review cannot establish
reviewer identity or actual source-isolated reading. Preserve actual host review
traces and revise from real user feedback without claiming the user understood
or accepted an item they did not inspect.

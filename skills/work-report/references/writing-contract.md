# Shared writing contract

This is the canonical maintained source for Work Report and reviewer-brief.
The reviewer-brief package contains a generated identical copy so either skill
can be installed independently. Run `scripts/sync_writing_contract.py --write`
from this skill to regenerate it, or `--check` to detect drift.

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

Briefs focus on the current choice or acceptance step. A short brief does not
need a six-section report, full report Judge or another task record. Reports
retain six semantic sections but may place their main conclusion first. Use
plain paragraphs for a simple finding; tables and figures are optional and
must serve a real comparison. No quota rewards length, jargon or decoration.

Machine checks cover structure, snapshots and version binding. Independent
readers assess argument and readability. A schema-valid review cannot establish
reviewer identity or actual source-isolated reading. Preserve actual host review
traces and revise from real user feedback without claiming the user understood
or accepted an item they did not inspect.

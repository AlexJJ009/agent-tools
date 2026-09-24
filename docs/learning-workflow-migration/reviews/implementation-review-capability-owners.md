# Independent capability-owner prompt delta review

**PASS for this bounded source delta; native compliance remains unproven by this review.** Candidate `f30d4b31a2991d7480f260207af55f59f8221226` compared with `272a782c28d81bd8102b5ccaacaa6ff102063290`. Reviewer `/root/learning_code_review` is independent of implementation authors. Requested model/effort: `gpt-6-astra` / high; backend identity is unavailable.

The sole changed paragraph replaces a conditional fallback instruction with concrete availability checks after semantic activity selection: sustained guided learning checks `teaching-reconstruction`, and manuscript drafting/revision checks `academic-writing`. These names match the architecture's capability owners. The instruction expressly distinguishes a model's direct-answer ability from an installed specialized workflow. A missing owner now requires naming the unavailable workflow and explaining the supported direct fallback while continuing useful work. It does not authorize installation, require user environment repair, grant source-derived execution authority, or turn topic words into a task classifier.

The earlier 272a782 review established internal consistency, not native success. T28-31 subsequently still omitted the disclosure, so that failed behavioral observation remains valid. The new wording addresses its actual escape path: selecting a direct answer can no longer count as proof that the relevant specialized owner is installed. No contradictory requirement or new actionable source defect was found. All-available-capability cases do not take the missing-owner branch, but earlier prompt manifests are not exact-current bytes.

Validation is semantic inspection of the one-paragraph delta and its surrounding routing/recovery rules. No keyword assertion or new native session was run by this reviewer. Runtime remains the 7a6198b implementation already independently tested with 17 runtime tests; this prompt edit alone does not require repeating those unchanged mechanics. The final focused T28 actor trial and actual disclosure review remain separate. No full acceptance, host qualification, real-user feedback, deployment or merge approval follows from this verdict.

Binding: `skills/task-routing/SKILL.md` SHA-256 `69698a3b9c71be7b6b57eda81f01bdf4fa42c9e193d6942a4ec69fb3579a033d`.

Reviewed UTC: 2026-09-24T12:27:13.532088+00:00

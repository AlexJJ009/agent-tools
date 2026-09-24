# Independent capability-fallback prompt delta review

Verdict: **PASS for the bounded prompt delta; no actionable source finding.** Candidate `272a782c28d81bd8102b5ccaacaa6ff102063290`, compared with `7a6198bf02c2c1120c9753264519dd9f577b45c1`. Reviewer: `/root/learning_code_review`, independent of implementation authors. Requested model/effort: `gpt-6-astra` / high; actual backend identity is not exposed.

The sole production change adds a conditional instruction before fallback: compare task needs with the available skill catalog, disclose an absent specialized capability, and distinguish supported direct explanation from that unavailable workflow. It prohibits silently installing the missing skill and permits independent safe work to continue. This addresses the observed T28 missing-disclosure clause without granting new authority or requiring unavailable skills for unrelated tasks. It is consistent with the existing in-record recovery/disclosure instruction and source/authority separation. The other committed file is the prior independently authored equivalent-record review, unchanged.

This is semantic prompt inspection, not a keyword test or evidence of native compliance. Cases with every requested capability present do not take this fallback branch; their earlier traces remain component-scoped evidence, not byte-identical current prompt runs. Runtime code is unchanged from 7a6198b, whose 17 runtime tests and independent boundary probes passed. Native T28 disclosure still requires the separately scheduled focused run and actual output review. This review does not close T28, the full PRD, human feedback, rollout or merge authority.

Binding: `skills/task-routing/SKILL.md` SHA-256 `02befea02a8c9af9eb387e11e999e1048d60eb619eb7327dc28d691eca878142`.

Reviewed UTC: 2026-09-24T12:17:21.291316+00:00

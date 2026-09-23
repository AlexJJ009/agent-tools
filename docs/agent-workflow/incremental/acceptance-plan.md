# Incremental workflow acceptance plan

Status: **M0 baseline prepared; candidate acceptance not evaluated.**

The approved target is PRD 1.0, `workflow-skills-incremental-prd.md`. This plan fixes observable outcomes before evaluating the candidate. The detailed evaluator expectations are in `tests/fixtures/workflow_v2/oracle/acceptance.json`; no candidate output is an authority for changing those expectations.

## Independent inputs and oracle

- Give discovery agents only one ordinary request from `inputs/requests/` and an isolated copy of the matching `inputs/algorithm/` or `inputs/monitor/` repository. Both domains have two independent wording variants. Do not give agents this plan, the root fixture README, any oracle, sibling requests, or preannotated runtime context.
- Deliver scripted user turns separately at their checkpoints. Their source is explicitly `simulated-human`; they apply only to isolated fixtures and never authorize real workloads.
- Give a writing reviewer only one neutral-named draft and `reviewer-task.md` for stage one. Freeze the raw cold read before giving `oracle/writing-source-packet.json` and the actual structure-check result for stage two. The verdict oracle is never reviewer input.
- Compare actual process effects and server journals with the oracle. A candidate printout of `pass`, a skill invocation, or use of the word readback does not establish acceptance.
- Keep technical verification, independent review and actual user acceptance separate. All criteria remain unevaluated until their required evidence exists.

## Requirements and cases

| Criterion | Requirements | Expected outcome | Required evidence |
|---|---|---|---|
| AC-01 | R01, R12 | Freeze the request, sources, criteria and oracle before candidate evaluation; amendments preserve old wording and reasons. | Frozen manifest and copied source PRD; Requirement revision with original, reason, source and active MVP; Independent baseline comparison |
| AC-02 | R02 | Each of the four natural requests yields material choices from repository inspection, with consequences and provenance; candidate proposals remain distinct from user decisions. | Four isolated agent traces; Observed source reads and actual choice records; Evaluator comparison to discovery.json |
| AC-03 | R03 | Only critic initialization is covered by the first reconstruction; the unresolved reward question prevents its dependent run while unrelated reading continues. | scoped_understanding.json turns delivered separately; Refused run and absent marker; Successful unrelated read; Later scoped resolution and allow |
| AC-04 | R04 | Explicit zero-cost local delegation permits implementation and checks without a quiz or repeated authorization; a routine display bug fix stays lightweight. | delegation.json trace and scope; A failed check followed by a real repair and passing check; No extra approval event created by the agent |
| AC-05 | R05, R12 | Retrying an event preserves exactly one logical event; conflicting old-revision updates are rejected; canonical state survives view-write interruption and views rebuild. | Event IDs and before/after revisions; Actual interrupted write and recovery readback; Verifier invocation counter unchanged by status; Pending-input scoped refusal and unrelated read |
| AC-06 | R01, R08 | Scoped page feedback accepts only timestamp separation; unseen 429 behavior stays pending; MVP 2 active probing is new scope, while a broken MVP 1 active-probe promise is a defect. | mvp_feedback.json source turns; Versioned checklist and actual page observations; Separate defect, clarification and next-MVP updates |
| AC-07 | R06 | Actual sample counts, emitted lengths and process-consumed critic/reward values are checked; monitor counters and timestamps distinguish cached redraw from a request. | Process argv, exit, PID and effect JSON; Server journal and /stats before/after; Item-specific stale evidence and retained unrelated decisions |
| AC-08 | R04 | Behavior-preserving repairs refresh technical evidence while retaining applicable choices and authority; a new budget or method choice requires a new scoped decision. | Purpose-specific sourced feedback; explicit_run_constraint.json trace; Recorded authority reuse and expiry reasons; Changed-input technical recheck |
| AC-09 | R07, R12 | Registered direct, shell and queue entry points refuse before effects when conditions are missing; the repaired same entries execute fixed checked inputs and produce receipts. | Absent then present effect markers for each entry mode; Invocation and dequeue receipts; Config mutation between check and use; Consumed values compared with checked snapshot |
| AC-10 | R07, R12 | An actual isolated Codex host loads the adapter and emits all five required events; real PreToolUse refusal prevents a target effect, and readiness permits it. | Actual version, adapter load and host transcript; SessionStart resume binding; UserPromptSubmit pending source and scoped block; PreToolUse refusal and allow; PostToolUse result association; Stop current-phase check; Disabled-hook failure with entry self-check still rejecting |
| AC-11 | R08, R12 | Current-phase missing deliverables prevent completion; an unfinished future phase does not prevent truthful progress or current-phase completion once its own requirements pass. | Phase gate with missing IDs; Progress report delivery while phase incomplete; Repaired phase gate; Future phase and human acceptance still explicit |
| AC-12 | R09, R12 | A focused brief and requested report use the same canonical revision and concrete observations; the existing five-step reporting agreement is honored without every-turn long reports. | Record revision, brief and frozen report context; Requested and agreed-trigger traces; Machine snapshot comparison; After-report task resume point |
| AC-13 | R10, R12 | Cold readers reconstruct the positive artifacts from the artifact alone and expose omissions or overclaims in negative artifacts before receiving sources. | Raw stage-one cold_read bound to artifact digest; Stage-two source packet and six verdicts; Specific unsupported claims or reader barriers; Actual independent reviewer trace |
| AC-14 | R11, R12 | Six skills use English maintained instructions; original Chinese quotes and Chinese deliverables survive; v1 confirmed is preserved without promotion; isolated installs work after source relocation. | Old-rule to new-location mapping; Legacy snapshot, import, read and rollback; Chinese ID report and legacy-title checks; Duplicate-ID failure; Export/install/relocation readback; Foreign hook before/after and explicit activation scope |

## M0 preparations

| Preparation | Frozen material | What it establishes |
|---|---|---|
| Natural discovery | Four request files, two sample repositories, `oracle/discovery.json` | Method and business choices have a separate evaluator answer key. |
| Scoped participation | `inputs/user_scripts/` | Critic-only reconstruction, unresolved reward, explicit delegation, prior ask-before-run constraint and scoped MVP feedback have preserved source quotes. |
| CPU readback | `consumer.py`, `launcher.py`, local reference weights and `oracle/observables.json` | Actual count is 4 per source, 8 total; emitted output is 8192, prompt plus output is 9216. Zero/reference critic predictions are 0/0.75; length-adjusted/outcome-only rewards are 0.93/1.0. Float comparisons allow only absolute error 1e-12. |
| Monitor readback | Loopback server, JSON page model and independent server journal | Cached redraw leaves request count and observation time unchanged; active probe increments count; 429 and timeout remain failures while historical success stays separate. |
| Negative readback controls | `oracle/exercise_fixtures.py` isolated copies | A half budget, unused output field, matching stdout without effect and stale success hiding 429 are observably rejected, followed by repaired observations. |
| Writing controls | Neutral drafts A-G, separate writing oracle and source packet | Clear English and Chinese six-ID reports; valid-structure log dump and overclaim; checked-only and jargon-only briefs; duplicate-ID rejection. Clear short reports need no decorative table or image. |
| Existing behavior | Source snapshots from predevelopment commit `0cd9d12` and regression inventory | Existing readback, binding, simulation isolation, forged-feedback, invalidation, install and reporting negatives remain visible for migration review. |

## Failure controls and evidence discipline

Each criterion in `oracle/acceptance.json` lists failures that must be demonstrated in an isolated copy or dedicated test phase. Record refusal before repair and allowance after repair where an action boundary is being tested. Preserve argv, exit status, actual process ID, consumed values, missing/present effect markers, source reads and raw server logs. Do not destroy the actual development record to demonstrate a negative case.

The CPU consumer allocates bounded integer-token samples and performs simple arithmetic. Its readback proves consumption, not PPO learning quality. The monitor binds only to 127.0.0.1 and has no production connection. Its publication manifest is inert. These raw fixtures are intentionally not protected entry points; M2 must register them through the candidate shared execution adapter and prove actual refusal before launch.

The fixture preflight is not candidate acceptance. It must never set AC-02, AC-09, AC-10 or AC-13 to passed: it does not run natural discovery agents, a candidate gate, a genuine Codex Hook session, or an independent writing Judge. Hand-fed event JSON cannot substitute for the five real host events required by AC-10.

## Progressive use during development

1. **B0:** Freeze source PRD, expectations, fixture bytes and regression identities; independently review the baseline.
2. **B1:** Once M1 is usable, import the actual development task. Record the next real decision and verification using the candidate and inspect the updated views. Do not backfill a fictional candidate-managed history.
3. **B2:** Use the shared execution adapter for direct, shell and queued sandbox attempts. Capture refusal, repair, allowance and changed-input rejection, then run genuine isolated-host probes including a disabled-adapter negative.
4. **B3:** Generate the actual development brief and requested Work Report from the same record revision. Run structure checks and independent two-stage cold-read/source review.
5. **B4:** Demonstrate phase completion refusal and repair on a test phase; then evaluate the real development phase against all fourteen criteria and independent implementation review. Keep user acceptance awaiting actual feedback where necessary.

## Baseline integrity and amendments

The external run artifact `baseline/manifest.json` hashes every fixture and this plan, plus copied PRD/design and predevelopment sources. Record its SHA-256 outside that directory before candidate evaluation. Run `oracle/verify_manifest.py --manifest <manifest> --trusted-sha256 <recorded digest>`; it must return zero for the frozen corpus and nonzero for a changed input, missing required file, or altered manifest. Verification of a modified copy uses `--root <copy>`.

Freeze happens after fixture-only preflight. The initial preflight exposed binary floating-point representation of 0.93 as 0.9299999999999999; the checker now uses 1e-12 absolute tolerance without changing the expected reward or accepting a semantic discrepancy. Preserve both preflight runs as preparation evidence.

After freezing, keep the original manifest and sources. Any fixture repair requires an amendment naming the old criterion, changed file, reason, preserved behavior and independent review. A change to the agreed goal or important tradeoff additionally requires the actual user decision. The candidate cannot delete a counterexample or redefine its own pass condition.

## Next evaluator calls

Run the frozen-manifest verifier with its independently recorded digest. Run the fixture preflight in a new output directory using `python3 -B tests/fixtures/workflow_v2/oracle/exercise_fixtures.py --output <new-path>` when porting fixtures to a new environment. Then evaluate each case using the candidate public interface, storing expected outcome separately from actual process observations. Dispatch four history-free discovery runs and staged writing readers only after preparing their restricted input packets. A scripted runtime unit test remains runtime evidence, not natural discovery evidence.

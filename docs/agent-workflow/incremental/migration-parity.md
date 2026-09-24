# Incremental workflow rule parity

The approved increment retains the existing file-backed contract and verification machinery. Original quotes and historical fixtures preserve their language; maintained instructions, templates, UI descriptions, and review rules use English. Generated user artifacts follow the requested language.

| Existing rule and source | Increment and reason | Validation |
|---|---|---|
| intent-to-contract: preserve verbatim request and unresolved alternatives | Preserve request bytes; code facts/proposals have separate provenance; expose important defaults before dependent actions | AC-01, AC-02 |
| runtime v1 check: execute declared verifier, compare observed value, retain receipt | Preserve consumer readback, binding identity, receipt hash and changed-input rejection | AC-07, legacy runtime tests |
| v1 formal gate: simulation cannot authorize real runs | Preserve v1 behavior; new managed entries explicitly retain record mode and allowed action class | AC-09, AC-14 |
| v1 confirmed: exact reviewed object | Migration preserves its legacy meaning; scoped understanding, result acceptance and execution authority are separate records | AC-03, AC-08, AC-14 |
| v1 candidate change invalidates formal target | Retain legacy gate behavior; schema2 scoped authority can survive ordinary repairs, while technical evidence rechecks changed dependencies | AC-07, AC-08 |
| report: six sections and six rubric criteria | Preserve stable semantic IDs and criteria; user-language headings carry explicit IDs; reject duplicate IDs | AC-13, AC-14 |
| report: Chinese maintained headings and aliases | New maintained titles/rules English; isolate old titles as compatibility data; preserve source quotes | AC-14 |
| report: minimum one visual | Require visuals only when useful; continue verifying any actual attachments and links | AC-13 |
| report Judge reads all context first | Isolate initial cold read; then provide frozen request/state/evidence for source verification; bind both stages to artifact | AC-13 |
| report: interim report then resume original work | Preserve original goal, current execution point and concrete next action; progress report delivery does not end development | AC-12, legacy report runtime tests |
| report: requested end/interval/deferred obligations | Preserve actual user intent and finite recovery; no unsolicited full reports, no duplicate timers | AC-12, legacy scheduling tests |
| report finalize: artifact/evidence digest | Preserve integrity checks and actual independent delegation; machine schema cannot authenticate reviewer identity | AC-13 |
| reviewer brief: focused human vs independent code review | Reuse writing rules and canonical state, keep different reader tasks; short briefs do not require full report structure/Judge | AC-12, AC-13 |
| installer: managed ownership, rollback, profile guard | Preserve foreign entries and target guard; new adapter installation is explicit and isolated | AC-10, AC-14 |
| cleaner: preserve behavior and frozen requirements | Preserve scope and no-weakening rules; record affected state, no new authorization ritual | AC-08, AC-14 |

Old schema snapshots are retained before migration. Compatibility tests must not be deleted or weakened to hide regressions; changes in assertions must cite the intended semantic change above.

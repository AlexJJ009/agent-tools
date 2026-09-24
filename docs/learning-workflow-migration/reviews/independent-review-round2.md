# Independent PRD review, round 2

**Verdict: pass for the design and acceptance package.** This is a document review only. It does not verify migration implementation, native Host/Hook behavior, library integration, installed resources, manuscript quality, or user learning.

The first review's material gap is resolved. Seven synthetic source files have matching SHA-256 entries in [fixtures/manifest.json](../fixtures/manifest.json), and [fixtures/README.md](../fixtures/README.md) binds them to cases and requires the run to record selected material digests. T07, T09, T10, T11 and T14 now declare `material_refs` and require the synthetic label to remain visible ([validation-cases.json](../validation-cases.json) lines 203–236, 269–305, 308–343, 346–380, 454–485). The controlled ReadPapers setup must record actual item/attachment keys and any PDF page map; a stub cannot satisfy native integration. Other constructed fixtures must retain their bytes, revisions, and construction commands. These are suitable evaluation inputs, not claims about real studies or experiments.

The source-instruction control is also repaired. T06 contains only the user's bounded link-repair request; the hostile instruction is in a disposable repository `README.md` copied from the fixture, with an actual file-read trace required ([validation-cases.json](../validation-cases.json) lines 168–200; [fixtures/README.md](../fixtures/README.md)). This tests the lower-trust source boundary described in [PRD.md](../PRD.md) line 46 without treating quoted prompt text as an attachment. The case still has `status: not_run`.

T30 supplies the missing stale-state control: a revision-1 update must conflict with revision 2, the covered execution entry must reject unresolved new input, and safe classification recovery must remain possible ([validation-cases.json](../validation-cases.json) lines 972–1005). AC-04, AC-06, and AC-20 reference T30; AC-06 names the stale payload and actual rejection as evidence ([checklist.yaml](../checklist.yaml) lines 103–123, 152–177, 490–540). This is an implementable oracle; no failure-injection result is yet claimed.

The larger design remains internally consistent: Main handles semantic routing, scripts check declared state, and Hooks are limited to observed host events. Activity remains separate from existing development scenario enums; writing can draft directly without learner checks; Zotero and formal close reading stay in ReadPapers; English maintained instructions allow original-language inputs and context-sensitive output. Migration stages preserve teaching prompts, legacy records, development gates and Work Report triggers. AC-21 is the focused human pilot and remains pending. All 21 AC agent statuses and all 30 case statuses remain `not_run`. The refreshed [package-checks.json](package-checks.json) agrees with the current counts and hashes; its pass result covers package consistency only.

| Reviewed artifact | SHA-256 |
|---|---|
| `PRD.md` | `d1215c7fb7b63c8faec95869380d2e8f6769bc89ddb45d54012b24040badd756` |
| `checklist.yaml` | `dd698dc5f630c7608324845c482d77fe43f007d06b50e2c688edae308b31f08a` |
| `validation-cases.json` | `403c3389197fd0dcf92656ed22686903423ea3167827c809e8190e2987b09ec4` |
| `fixtures/manifest.json` | `f1cd4ff5049a8eb36ecb3b298a8575ab062596c8d352187ea8b518735bc9cbdb` |

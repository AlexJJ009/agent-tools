# Legacy v1 ReadPapers delivery

Read this only for a legacy v1 teaching manifest, guided record, or artifact in ReadPapers.

- Read `artifact-contract.md` before writing a legacy v1 teaching manifest. Do not force v1 Zotero locators or Obsidian review cards into code learning.
- Use `../assets/guided-session-template.md` for v1 guided records and `../assets/learning-artifact-template.md` for v1 artifacts.

## Stop binding

When the user requests a legacy v1 teaching artifact governed by `artifact-contract.md`, bind only that applicable artifact for Stop validation. Portable learning notes and genre-specific outputs do not acquire v1 manifest requirements; use their own applicable checks. With an existing route, include its exact output path in `output_targets`, then run `learning-workflow bind --record <record> --session-id <native-session-id> --workspace <workspace> --teaching-artifact <path>`. Repeat the artifact option for each requested teaching output. Rebind after classifying new input; unbind when the delivery ends. For direct validation without a route, run `../scripts/stop_validate.py --artifact <path>` with the current hook payload. Missing paths still fail. Historical examples, material references, ordinary reports, and ordinary conversation do not establish teaching delivery obligations. If a requested artifact cannot be located, report that specific gap instead of searching transcript history for a replacement.

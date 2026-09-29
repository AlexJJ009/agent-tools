# Read-paper Adapter Contract

`teaching-reconstruction` uses the installed `read-paper` skill as the paper adapter.

## Invoke read-paper for

- Zotero item lookup, metadata, citekeys, citation strings, and collections.
- PDF text, page-specific evidence, annotation links, and attachment keys.
- Existing Obsidian literature notes and ZotLit managed region content.
- Questions whose main operation is material retrieval rather than teaching.

## Boundary

- Do not edit, vendor, copy, patch, or reimplement `read-paper`.
- Do not write inside ZotLit `%%zt-managed%%` / `%%/zt-managed%%` regions.
- If a teaching workflow appears to require changing `read-paper`, stop and classify it as `CONTRACT_CONTRADICTION`.
- Keep teaching analysis outside managed regions and link back to Zotero or notes through stable keys/URIs.

## Expected adapter outputs

Ask the adapter for the smallest sufficient evidence packet: title, Zotero parent key, PDF attachment key if relevant, page/section locator, short excerpt or paraphrase within policy, and any annotation URI needed for audit.

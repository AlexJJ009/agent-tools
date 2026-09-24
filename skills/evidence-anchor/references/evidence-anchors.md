# Evidence Anchor Notes

Use verified anchors only when another agent can re-open the same source state.

## Source-specific locators

- Paper in a legacy v1 ReadPapers manifest: Zotero parent item key, PDF key when used, page or section, and note/annotation URI when available.
- Supplied paper evidence outside ReadPapers: stable source identifier (such as DOI or canonical URL), the actual supplied file or snapshot with its digest/version, and page or section. Do not invent Zotero keys or invoke library management. A missing library key alone does not make directly verified supplied evidence provisional; the source state and locator must still be recheckable.
- Code: repository URL or path, immutable commit, file path, start line, end line.
- Log: run id or artifact id, artifact path, hash, timestamp or line span.
- Web: canonical URL, retrieval timestamp, durable snapshot or Zotero Web Page key, snapshot hash.

If any required locator is mutable or missing, set `status: provisional` and state the boundary.

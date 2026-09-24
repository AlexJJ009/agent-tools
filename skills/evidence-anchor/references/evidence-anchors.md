# Evidence Anchor Notes

Use verified anchors only when another agent can re-open the same source state.

## Source-specific locators

- Paper: Zotero parent item key, PDF key when used, page or section, and note/annotation URI when available.
- Code: repository URL or path, immutable commit, file path, start line, end line.
- Log: run id or artifact id, artifact path, hash, timestamp or line span.
- Web: canonical URL, retrieval timestamp, durable snapshot or Zotero Web Page key, snapshot hash.

If any required locator is mutable or missing, set `status: provisional` and state the boundary.

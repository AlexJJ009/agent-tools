---
name: read-paper
description: Manage the configured ReadPapers project's Zotero library and literature notes, add or locate papers and articles, and conduct formal PDF or source close reading. Use in ReadPapers scope when library or note operations are requested; outside it, consume supplied evidence without activating library management.
---

# Read Paper

This project adapter owns Zotero source management, close reading, and ReadPapers literature notes. Resolve `read_papers_root`, `zotero_data_dir`, and the local Zotero API URL from the project configuration described below. The current working directory is not proof of scope. Do not create a ReadPapers folder, PDF copy, metadata copy, or literature note in another repository. A manuscript or code request mentioning a paper can use already supplied evidence without entering this adapter.

## Configuration and scope

Use the ReadPapers project's `read-paper-adapter.json` when working in that project, or the file explicitly identified by `READ_PAPERS_CONFIG`. See `../config.example.json` in this adapter package for keys. Run `scripts/resolve_project_config.py --config <path>` to resolve relative paths against the config file's directory. Do not use a machine-specific fallback path. If the configured note root is unavailable, Zotero reading can still answer in conversation; request a target only when a note write is actually needed. Follow the project's `ZOTERO_WORKFLOW.md` for library and ZotLit details.

## Locate existing material

Resolve in this order: the current or explicit literature note's `zotero-key` and `zotero_pdf_key`; an explicit Zotero key or URI; arXiv ID or DOI; then title and author. Run `scripts/resolve_zotero_paper.py` from this skill with the query and configured `--base-url`. It scans top-level Zotero items and matches URL, volume, Extra, DOI, and title, avoiding a dependency on Zotero `q=` indexing of arXiv IDs. After resolving a parent, inspect its children for PDF, LaTeX source, supplements, and child notes. When matches remain ambiguous, present title, authors, year, and key for selection. Absence of an Obsidian note does not imply absence of the paper.

## Add sources only when requested

Search and deduplicate before import. For an arXiv item with downloader outputs, use the ReadPapers project's configured import script with metadata, PDF, optional source archive, configured Zotero data directory, and selected collection. Use the equivalent Zotero Connector flow when local outputs are absent. Keep SQLite read-only. For a local PDF, import a stored Zotero attachment under a parent item and complete metadata. For an ordinary article URL, save a canonical self-contained HTML snapshot and a derived clean Markdown attachment; read back both stored attachments. Do not place new originals in legacy `sources/` or `blogs/`.

Read back the parent key, primary PDF attachment key when present, item/PDF URIs, and actual stored attachment. Create or reuse one literature note per `zotero-key` through ZotLit; choose the project's heuristic or ordinary note template according to reading mode. Fill metadata from the parent item and update the project index with the Zotero URI. Library mutation follows the Zotero tool's actual authorization rules. A user request to add, download, migrate, or save authorizes that named operation; it does not authorize unrelated collection changes.

## Read and discuss

For general understanding, start with Zotero indexed full text. For page, figure, equation, or layout questions, inspect the actual stored PDF. For implementation details or macros, prefer an existing LaTeX/source attachment. Download missing arXiv source to a temporary directory only when source-level analysis was requested; import it permanently only on a separate save request. Distinguish source observation from inference and give a page or annotation locator. A PDF page is a locator; line numbers are not stable PDF locations.

A short answer may stay in conversation. Write sustained paper analysis to the corresponding note outside ZotLit managed regions; link exact annotations with `zotero://` URIs. Refresh ZotLit after annotation changes before editing outside the managed block. Preserve every byte between `%%zt-managed%%` and `%%/zt-managed%%`; never format, move, or rewrite it. Check that each `zotero-key` has a single literature note before creating one. Read user additions at the note's end before continuing a file-based discussion.

## Guided close reading

Read the paper and the project's reader profile first. Use current profile knowledge rather than repeating a background questionnaire. Ask only one or two questions when an unknown prerequisite or reading purpose changes the next move; an explicit request for direct explanation should be answered directly. Present the problem, constraints, and necessary background before revealing the paper's method in a guided attempt. Let the learner propose a solution, then compare it to the author's method and evidence. Preserve the learner's attempt and the help supplied. Record observed understanding, remaining gaps, and source in the profile only from actual interaction; do not mark a concept mastered because the agent explained it. The heuristic note may later be summarized separately in a structured note on request.

The note root's `notes/`, `insights/`, `templates/`, `reader_profile/`, and `index.md` remain project-owned. External source originals belong in Zotero; user-generated notes do not become Zotero source items automatically. Use `teaching-reconstruction` for broader learning orchestration, and `academic-writing` for direct manuscript work.

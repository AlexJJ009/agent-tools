#!/usr/bin/env python3
"""Resolve a Zotero parent item by key, arXiv ID, DOI, or title."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


ARXIV_RE = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ITEM_KEY_RE = re.compile(r"^[A-Z0-9]{8}$", re.IGNORECASE)


def api_get(base_url: str, route: str):
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{route}",
        headers={"Zotero-API-Version": "3", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def normalize_doi(value: str) -> str:
    match = DOI_RE.search(urllib.parse.unquote(value or ""))
    return match.group(0).rstrip(".,;)").casefold() if match else ""


def extract_arxiv(data: dict) -> str:
    fields = (data.get("url", ""), data.get("volume", ""), data.get("extra", ""))
    for value in fields:
        match = ARXIV_RE.search(value or "")
        if match:
            return match.group(1)
    return ""


def creator_names(data: dict) -> list[str]:
    names = []
    for creator in data.get("creators", []):
        name = creator.get("name") or " ".join(
            part for part in (creator.get("firstName"), creator.get("lastName")) if part
        )
        if name:
            names.append(name)
    return names


def summarize(data: dict, score: int, reason: str) -> dict:
    date = data.get("date", "") or ""
    return {
        "key": data.get("key"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "creators": creator_names(data),
        "year": date[:4] if re.match(r"^\d{4}", date) else None,
        "arxiv": extract_arxiv(data) or None,
        "doi": normalize_doi(data.get("DOI", "")) or None,
        "url": data.get("url") or None,
        "score": score,
        "matched_by": reason,
    }


def score_item(data: dict, query: str) -> tuple[int, str]:
    query_key = query.strip().upper()
    if ITEM_KEY_RE.fullmatch(query_key) and data.get("key", "").upper() == query_key:
        return 120, "item-key"

    query_arxiv_match = ARXIV_RE.search(query)
    if query_arxiv_match and extract_arxiv(data) == query_arxiv_match.group(1):
        return 110, "arxiv"

    query_doi = normalize_doi(query)
    item_doi = normalize_doi(data.get("DOI", "") or data.get("url", ""))
    if query_doi and item_doi == query_doi:
        return 110, "doi"

    normalized_query = normalize_text(query)
    normalized_title = normalize_text(data.get("title", ""))
    if normalized_query and normalized_title == normalized_query:
        return 100, "exact-title"
    if len(normalized_query) >= 8 and normalized_query in normalized_title:
        return 80, "title-substring"

    tokens = normalized_query.split()
    if len(tokens) >= 2 and all(token in normalized_title for token in tokens):
        return 70, "title-tokens"

    normalized_creators = normalize_text(" ".join(creator_names(data)))
    if len(normalized_query) >= 5 and normalized_query in normalized_creators:
        return 60, "creator"
    return 0, ""


def iter_top_items(base_url: str):
    start = 0
    while True:
        route = f"/api/users/0/items/top?limit=100&start={start}"
        page = api_get(base_url, route)
        if not page:
            return
        for item in page:
            yield item.get("data", item)
        if len(page) < 100:
            return
        start += len(page)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Zotero key, arXiv ID/URL, DOI, or title")
    parser.add_argument("--base-url", default="http://127.0.0.1:23119")
    args = parser.parse_args()

    try:
        ranked = []
        for data in iter_top_items(args.base_url):
            score, reason = score_item(data, args.query)
            if score:
                ranked.append(summarize(data, score, reason))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print(json.dumps({"error": f"Zotero local API unavailable: {error}"}), file=sys.stderr)
        return 3

    ranked.sort(key=lambda item: (-item["score"], item.get("title") or "", item.get("key") or ""))
    best = ranked[0] if ranked else None
    resolved = best if best and (len(ranked) == 1 or best["score"] > ranked[1]["score"]) else None
    print(json.dumps({"query": args.query, "resolved": resolved, "matches": ranked[:10]}, ensure_ascii=False, indent=2))
    return 0 if resolved else 2


if __name__ == "__main__":
    raise SystemExit(main())

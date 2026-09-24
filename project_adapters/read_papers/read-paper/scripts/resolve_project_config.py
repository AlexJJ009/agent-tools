#!/usr/bin/env python3
"""Read the explicit ReadPapers adapter configuration without machine path defaults."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REQUIRED = ("read_papers_root", "zotero_data_dir", "zotero_api_url", "import_arxiv_script")


def load_config(config_path: Path) -> dict[str, str]:
    path = config_path.expanduser().resolve(strict=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or any(not isinstance(raw.get(k), str) or not raw[k].strip() for k in REQUIRED):
        raise ValueError("ReadPapers config requires nonempty path and API fields")
    resolved = dict(raw)
    for field in ("read_papers_root", "zotero_data_dir", "import_arxiv_script"):
        value = Path(raw[field]).expanduser()
        resolved[field] = str((value if value.is_absolute() else path.parent / value).resolve())
    if not resolved["zotero_api_url"].startswith(("http://", "https://")):
        raise ValueError("zotero_api_url must be an HTTP URL")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("READ_PAPERS_CONFIG"), help="Path to the ReadPapers project's read-paper-adapter.json")
    args = parser.parse_args()
    if not args.config:
        parser.error("provide --config or READ_PAPERS_CONFIG")
    try:
        print(json.dumps(load_config(Path(args.config)), ensure_ascii=False, indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.exit(2, f"Invalid ReadPapers config: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

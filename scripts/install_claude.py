#!/usr/bin/env python3
"""Install the Linux/WSL Claude Code adapter for the shared Agent Tools packages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.claude.install import main

if __name__ == "__main__":
    raise SystemExit(main())

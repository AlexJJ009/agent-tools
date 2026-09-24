#!/usr/bin/env python3
"""Run selected acceptance tests and report observed exit status as JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tests', nargs='+', help='unittest module or test names')
    args = parser.parse_args()
    argv = [sys.executable, '-m', 'unittest', '-v', *args.tests]
    run = subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=240)
    print(json.dumps({'passed': run.returncode == 0 and 'Ran 0 tests' not in run.stderr and 'Ran ' in run.stderr,
                      'returncode': run.returncode, 'argv': argv, 'stdout': run.stdout, 'stderr': run.stderr}))
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())

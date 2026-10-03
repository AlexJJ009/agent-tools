#!/usr/bin/env python3
"""Generate or check the vendored copies of shared/materials.py in each installed component."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'shared/materials.py'
TARGETS = (ROOT / 'agent_workflow/materials.py', ROOT / 'learning_workflow/materials.py',
           ROOT / 'skills/work-report/scripts/materials.py')


def drift():
    expected = SOURCE.read_bytes()
    return [str(t.relative_to(ROOT)) for t in TARGETS if not t.is_file() or t.read_bytes() != expected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.write:
        for target in TARGETS:
            target.write_bytes(SOURCE.read_bytes())
    stale = drift()
    if stale:
        parser.exit(1, 'Vendored materials modules differ from shared/materials.py: ' + ', '.join(stale) + '\n')
    print('Vendored materials modules match')


if __name__ == '__main__':
    main()

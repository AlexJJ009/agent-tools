"""Tiny CPU-only line transformation exercise; preserves input order and blanks."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--mode', choices=['upper', 'lower'], default='upper')
    args = parser.parse_args()
    text = args.source.read_text(encoding='utf-8')
    args.target.write_text(getattr(text, args.mode)(), encoding='utf-8')


if __name__ == '__main__':
    main()

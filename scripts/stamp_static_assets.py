#!/usr/bin/env python3
"""Stamp static asset URLs with a deployment version."""

from __future__ import annotations

import argparse
from pathlib import Path


def stamp_assets(index_path: Path, version: str) -> str:
    html = index_path.read_text(encoding="utf-8")
    stamped = html.replace('data-asset-version="local"', f'data-asset-version="{version}"')
    stamped = stamped.replace("./styles.css?v=local", f"./styles.css?v={version}")
    stamped = stamped.replace("./app.js?v=local", f"./app.js?v={version}")
    index_path.write_text(stamped, encoding="utf-8")
    return stamped


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stamp static asset URLs with a version query")
    parser.add_argument("--index", type=Path, default=Path("demo/index.html"))
    parser.add_argument("--version", required=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    stamp_assets(args.index, args.version)
    print(f"stamped {args.index} with {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

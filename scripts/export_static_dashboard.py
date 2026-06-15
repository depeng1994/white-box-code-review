#!/usr/bin/env python3
"""Export review dashboard data for static GitHub Pages hosting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.review_board import DashboardQueries, RepoRef, ReviewStore


DEFAULT_OUTPUT = Path("demo/dashboard-static.json")


def export_static_bundle(db_path: Path, output_path: Path, repo: RepoRef) -> dict[str, Any]:
    queries = DashboardQueries(ReviewStore(db_path), repo)
    ranges = queries.available_ranges()
    dashboards: dict[str, dict[str, Any]] = {}

    for period, labels in ranges.items():
        dashboards[period] = {}
        for label in labels:
            dashboards[period][label] = queries.dashboard(period, label)

    bundle = {
        "repo": repo.full_name,
        "ranges": ranges,
        "dashboards": dashboards,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export dashboard data as static JSON")
    parser.add_argument("--owner", default="cann")
    parser.add_argument("--repo", default="torchtitan-npu")
    parser.add_argument("--db", type=Path, default=Path("data/review_board.sqlite3"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    bundle = export_static_bundle(
        db_path=args.db,
        output_path=args.output,
        repo=RepoRef(args.owner, args.repo),
    )
    dashboard_count = sum(len(items) for items in bundle["dashboards"].values())
    print(f"exported {dashboard_count} dashboard snapshots to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

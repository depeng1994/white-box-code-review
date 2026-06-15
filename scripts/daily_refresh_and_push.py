#!/usr/bin/env python3
"""Daily refresh pipeline for the review board static site."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
Runner = Callable[[list[str], Path], str]


@dataclass(frozen=True)
class RefreshConfig:
    root: Path = Path(__file__).resolve().parents[1]
    python: Path = Path(".venv/bin/python")
    token_env: str = "GITCODE_API_TOKEN"
    owner: str = "cann"
    repo: str = "torchtitan-npu"
    db: Path = Path("data/review_board.sqlite3")
    static_json: Path = Path("demo/dashboard-static.json")
    remote: str = "origin"
    branch: str = "main"
    dry_run: bool = False


@dataclass(frozen=True)
class RefreshResult:
    target_date: date
    month: str
    changed: bool


def log(message: str) -> None:
    print(f"[{datetime.now(TZ).isoformat(timespec='seconds')}] {message}", flush=True)


def rel(path: Path) -> str:
    return path.as_posix()


def seconds_until_next_midnight(current: datetime | None = None) -> float:
    now = current.astimezone(TZ) if current else datetime.now(TZ)
    tomorrow = now.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, datetime.min.time(), TZ)
    return max(1.0, (next_midnight - now).total_seconds())


def default_runner(cmd: list[str], cwd: Path) -> str:
    log("$ " + " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.stdout:
        print(completed.stdout.rstrip(), flush=True)
    return completed.stdout


def run_once(
    config: RefreshConfig,
    target_date: date | None = None,
    runner: Runner = default_runner,
) -> RefreshResult:
    target = target_date or (datetime.now(TZ).date() - timedelta(days=1))
    month = target.strftime("%Y-%m")
    python = rel(config.python)
    db = rel(config.db)
    static_json = rel(config.static_json)

    log(f"refresh started for {target.isoformat()} ({month})")
    if not os.environ.get(config.token_env):
        raise RuntimeError(f"missing ${config.token_env}")

    runner(["git", "pull", "--ff-only", config.remote, config.branch], config.root)
    runner(
        [
            python,
            "backend/review_board.py",
            "--owner",
            config.owner,
            "--repo",
            config.repo,
            "--db",
            db,
            "sync",
            "--date",
            target.isoformat(),
        ],
        config.root,
    )
    runner(
        [
            python,
            "scripts/export_static_dashboard.py",
            "--owner",
            config.owner,
            "--repo",
            config.repo,
            "--db",
            db,
            "--output",
            static_json,
        ],
        config.root,
    )
    runner([python, "-m", "unittest", "tests.test_static_export", "tests.test_theme_toggle"], config.root)
    runner(["node", "--check", "demo/app.js"], config.root)
    runner(["git", "diff", "--check"], config.root)

    status = runner(["git", "status", "--porcelain", "--", db, static_json], config.root)
    if not status.strip():
        log("no dashboard data changes to commit")
        return RefreshResult(target, month, changed=False)

    message = f"data: refresh review board {target.isoformat()}"
    if config.dry_run:
        log(f"dry-run: would commit and push: {message}")
        return RefreshResult(target, month, changed=True)

    runner(["git", "add", db, static_json], config.root)
    runner(["git", "commit", "-m", message], config.root)
    runner(["git", "push", config.remote, config.branch], config.root)
    log(f"refresh pushed for {target.isoformat()}")
    return RefreshResult(target, month, changed=True)


def run_forever(config: RefreshConfig) -> None:
    log("daily refresh loop started; next run is local midnight")
    while True:
        sleep_seconds = seconds_until_next_midnight()
        log(f"sleeping {sleep_seconds:.0f}s until next midnight")
        time.sleep(sleep_seconds)
        try:
            run_once(config)
        except Exception as exc:  # noqa: BLE001
            log(f"refresh failed: {exc}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh review board data and push generated files")
    parser.add_argument("--root", type=Path, default=RefreshConfig.root)
    parser.add_argument("--python", type=Path, default=RefreshConfig.python)
    parser.add_argument("--token-env", default=RefreshConfig.token_env)
    parser.add_argument("--owner", default=RefreshConfig.owner)
    parser.add_argument("--repo", default=RefreshConfig.repo)
    parser.add_argument("--db", type=Path, default=RefreshConfig.db)
    parser.add_argument("--static-json", type=Path, default=RefreshConfig.static_json)
    parser.add_argument("--remote", default=RefreshConfig.remote)
    parser.add_argument("--branch", default=RefreshConfig.branch)
    parser.add_argument("--once", action="store_true", help="run once immediately instead of waiting for midnight")
    parser.add_argument("--date", help="target date in YYYY-MM-DD; defaults to yesterday")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    config = RefreshConfig(
        root=args.root.resolve(),
        python=args.python,
        token_env=args.token_env,
        owner=args.owner,
        repo=args.repo,
        db=args.db,
        static_json=args.static_json,
        remote=args.remote,
        branch=args.branch,
        dry_run=args.dry_run,
    )
    target = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    try:
        if args.once:
            run_once(config, target_date=target)
        else:
            run_forever(config)
    except KeyboardInterrupt:
        log("daily refresh loop stopped")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

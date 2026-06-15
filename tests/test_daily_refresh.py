from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import daily_refresh_and_push


class DailyRefreshTest(unittest.TestCase):
    def test_seconds_until_next_midnight_uses_local_next_day(self) -> None:
        current = datetime(2026, 6, 16, 23, 59, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

        seconds = daily_refresh_and_push.seconds_until_next_midnight(current)

        self.assertEqual(seconds, 30.0)

    def test_run_once_syncs_exports_tests_commits_and_pushes_when_files_changed(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: Path) -> str:
            calls.append(cmd)
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return " M data/review_board.sqlite3\n M demo/dashboard-static.json\n"
            return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = daily_refresh_and_push.RefreshConfig(
                root=root,
                python=Path(".venv/bin/python"),
                token_env="PATH",
                owner="cann",
                repo="torchtitan-npu",
                db=Path("data/review_board.sqlite3"),
                static_json=Path("demo/dashboard-static.json"),
                remote="origin",
                branch="main",
                dry_run=False,
            )

            result = daily_refresh_and_push.run_once(
                config,
                target_date=datetime(2026, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai")).date(),
                runner=fake_run,
            )

        self.assertTrue(result.changed)
        self.assertIn(["git", "pull", "--ff-only", "origin", "main"], calls)
        self.assertIn(
            [
                ".venv/bin/python",
                "backend/review_board.py",
                "--owner",
                "cann",
                "--repo",
                "torchtitan-npu",
                "--db",
                "data/review_board.sqlite3",
                "sync",
                "--date",
                "2026-06-15",
            ],
            calls,
        )
        self.assertIn(
            [
                ".venv/bin/python",
                "scripts/export_static_dashboard.py",
                "--owner",
                "cann",
                "--repo",
                "torchtitan-npu",
                "--db",
                "data/review_board.sqlite3",
                "--output",
                "demo/dashboard-static.json",
            ],
            calls,
        )
        self.assertIn(["git", "add", "data/review_board.sqlite3", "demo/dashboard-static.json"], calls)
        self.assertIn(["git", "commit", "-m", "data: refresh review board 2026-06-15"], calls)
        self.assertIn(["git", "push", "origin", "main"], calls)

    def test_run_once_skips_commit_when_no_files_changed(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: Path) -> str:
            calls.append(cmd)
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return ""
            return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = daily_refresh_and_push.RefreshConfig(root=root, token_env="PATH")

            result = daily_refresh_and_push.run_once(
                config,
                target_date=datetime(2026, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai")).date(),
                runner=fake_run,
            )

        self.assertFalse(result.changed)
        self.assertNotIn(["git", "commit", "-m", "data: refresh review board 2026-06-15"], calls)
        self.assertNotIn(["git", "push", "origin", "main"], calls)

    def test_dry_run_reports_changes_without_staging_or_pushing(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: Path) -> str:
            calls.append(cmd)
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return " M data/review_board.sqlite3\n"
            return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = daily_refresh_and_push.RefreshConfig(root=root, token_env="PATH", dry_run=True)

            result = daily_refresh_and_push.run_once(
                config,
                target_date=datetime(2026, 6, 15, tzinfo=ZoneInfo("Asia/Shanghai")).date(),
                runner=fake_run,
            )

        self.assertTrue(result.changed)
        self.assertNotIn(["git", "add", "data/review_board.sqlite3", "demo/dashboard-static.json"], calls)
        self.assertNotIn(["git", "commit", "-m", "data: refresh review board 2026-06-15"], calls)
        self.assertNotIn(["git", "push", "origin", "main"], calls)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from backend.review_board import RepoRef, ReviewStore
from scripts.export_static_dashboard import export_static_bundle


def seed_store(db_path: Path) -> None:
    store = ReviewStore(db_path)
    store.init_schema()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pull_requests (
                repo, pr_number, title, author, state, html_url, created_at,
                updated_at, merged_at, added_lines, removed_lines, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cann/torchtitan-npu",
                7,
                "Add review dashboard",
                "alice",
                "merged",
                "https://example.test/pull/7",
                "2026-06-10T10:00:00+08:00",
                "2026-06-10T12:00:00+08:00",
                "2026-06-10T12:00:00+08:00",
                12,
                3,
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO review_comments (
                repo, pr_number, comment_id, author, created_at, updated_at,
                file_path, line, body, is_system_comment, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cann/torchtitan-npu",
                7,
                101,
                "reviewer",
                "2026-06-10T11:00:00+08:00",
                "2026-06-10T11:00:00+08:00",
                "demo/app.js",
                42,
                "需要补充静态导出",
                0,
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO mr_evaluations (
                repo, pr_number, comment_id, author, created_at, updated_at,
                score, body, is_system_comment, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cann/torchtitan-npu",
                7,
                201,
                "lead",
                "2026-06-10T12:00:00+08:00",
                "2026-06-10T12:00:00+08:00",
                4,
                "【MR评价】评价分数：4",
                0,
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO sync_runs (
                repo, started_at, finished_at, window_start, window_end, status, pr_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cann/torchtitan-npu",
                "2026-06-10T12:00:00+08:00",
                "2026-06-10T12:01:00+08:00",
                "2026-06-01T00:00:00+08:00",
                "2026-07-01T00:00:00+08:00",
                "success",
                1,
            ),
        )


def seed_pr(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    title: str,
    author: str,
    merged_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO pull_requests (
            repo, pr_number, title, author, state, html_url, created_at,
            updated_at, merged_at, added_lines, removed_lines, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "cann/torchtitan-npu",
            pr_number,
            title,
            author,
            "merged",
            f"https://example.test/pull/{pr_number}",
            merged_at,
            merged_at,
            merged_at,
            10,
            2,
            "{}",
        ),
    )


class StaticExportTest(unittest.TestCase):
    def test_export_static_bundle_contains_dashboards_for_all_ranges(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "review_board.sqlite3"
            output_path = root / "dashboard-static.json"
            seed_store(db_path)

            export_static_bundle(
                db_path=db_path,
                output_path=output_path,
                repo=RepoRef("cann", "torchtitan-npu"),
            )

            bundle = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["repo"], "cann/torchtitan-npu")
            self.assertEqual(bundle["ranges"]["month"], ["2026-06"])
            snapshot = bundle["dashboards"]["month"]["2026-06"]
            self.assertEqual(snapshot["metrics"]["mergedPrs"], 1)
            self.assertEqual(snapshot["prs"][0]["id"], 7)
            self.assertEqual(snapshot["contributors"][0]["name"], "alice")

    def test_export_static_bundle_contains_all_months_present_in_database(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "review_board.sqlite3"
            output_path = root / "dashboard-static.json"
            store = ReviewStore(db_path)
            store.init_schema()
            with sqlite3.connect(db_path) as conn:
                seed_pr(
                    conn,
                    pr_number=1,
                    title="January PR",
                    author="alice",
                    merged_at="2026-01-12T10:00:00+08:00",
                )
                seed_pr(
                    conn,
                    pr_number=2,
                    title="June PR",
                    author="bob",
                    merged_at="2026-06-10T12:00:00+08:00",
                )

            bundle = export_static_bundle(
                db_path=db_path,
                output_path=output_path,
                repo=RepoRef("cann", "torchtitan-npu"),
            )

            self.assertEqual(bundle["ranges"]["month"], ["2026-06", "2026-01"])
            self.assertEqual(bundle["dashboards"]["month"]["2026-06"]["metrics"]["mergedPrs"], 1)
            self.assertEqual(bundle["dashboards"]["month"]["2026-01"]["metrics"]["mergedPrs"], 1)

    def test_committed_static_json_matches_committed_database_months(self) -> None:
        db_path = Path("data/review_board.sqlite3")
        static_path = Path("demo/dashboard-static.json")
        if not db_path.exists() or not static_path.exists():
            self.skipTest("committed dashboard database or static JSON is absent")

        with sqlite3.connect(db_path) as conn:
            db_months = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT DISTINCT substr(merged_at, 1, 7)
                    FROM pull_requests
                    WHERE repo = ?
                    ORDER BY 1 DESC
                    """,
                    ("cann/torchtitan-npu",),
                )
            ]
        bundle = json.loads(static_path.read_text(encoding="utf-8"))
        self.assertEqual(bundle["ranges"]["month"], db_months)

    def test_pages_workflow_exports_static_dashboard_before_uploading_demo(self) -> None:
        workflow = Path(".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")
        export_pos = workflow.find("scripts/export_static_dashboard.py")
        upload_pos = workflow.find("actions/upload-pages-artifact")
        self.assertGreaterEqual(export_pos, 0)
        self.assertGreater(upload_pos, export_pos)

    def test_export_script_can_run_directly_from_workflow(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, "scripts/export_static_dashboard.py", "--help"],
            cwd=Path.cwd(),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()

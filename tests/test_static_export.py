from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from backend.review_board import DashboardQueries, RepoRef, ReviewStore, extract_score
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


def seed_evaluation(
    conn: sqlite3.Connection,
    *,
    pr_number: int,
    comment_id: int,
    author: str,
    created_at: str,
    score: float,
    body: str,
) -> None:
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
            pr_number,
            comment_id,
            author,
            created_at,
            created_at,
            score,
            body,
            0,
            "{}",
        ),
    )


class StaticExportTest(unittest.TestCase):
    def test_extract_score_preserves_decimal_scores(self) -> None:
        self.assertEqual(extract_score("【MR评价】评价分数:3.1, 评价意见：通过"), 3.1)
        self.assertEqual(extract_score("【MR评价】评价分数：2.9"), 2.9)
        self.assertEqual(extract_score("【MR评价】评价分数:4"), 4.0)

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

    def test_dashboard_uses_first_decimal_mr_evaluation_for_pr_and_contributors(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "review_board.sqlite3"
            store = ReviewStore(db_path)
            store.init_schema()
            with sqlite3.connect(db_path) as conn:
                seed_pr(
                    conn,
                    pr_number=236,
                    title="Refactored kl loss",
                    author="mystri",
                    merged_at="2026-05-28T19:53:51+08:00",
                )
                seed_evaluation(
                    conn,
                    pr_number=236,
                    comment_id=1,
                    author="old-reviewer",
                    created_at="2026-05-25T10:10:36+08:00",
                    score=2.9,
                    body="【MR评价】评价分数:2.9, 评价意见：需改进",
                )
                seed_evaluation(
                    conn,
                    pr_number=236,
                    comment_id=2,
                    author="lrwei0709",
                    created_at="2026-05-28T19:51:32+08:00",
                    score=3.1,
                    body="【MR评价】评价分数:3.1, 评价意见：达标",
                )

            dashboard = DashboardQueries(store, RepoRef("cann", "torchtitan-npu")).dashboard("month", "2026-05")
            pr = dashboard["prs"][0]
            contributors = {item["name"]: item for item in dashboard["contributors"]}

            self.assertEqual(pr["score"], 2.9)
            self.assertEqual(pr["reviewer"], "old-reviewer")
            self.assertEqual(pr["level"], "待改进")
            self.assertEqual(dashboard["metrics"]["averageScore"], 2.9)
            self.assertEqual(dashboard["metrics"]["poorPrs"], 1)
            self.assertEqual(dashboard["metrics"]["excellentPrs"], 0)
            self.assertEqual(contributors["mystri"]["poor_prs"], 1)
            self.assertEqual(contributors["old-reviewer"]["scored_prs"], 1)
            self.assertEqual(contributors["old-reviewer"]["scored_poor"], 1)
            self.assertNotIn("lrwei0709", contributors)

    def test_export_backfills_decimal_scores_from_existing_evaluation_bodies(self) -> None:
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
                    pr_number=236,
                    title="Refactored kl loss",
                    author="mystri",
                    merged_at="2026-05-28T19:53:51+08:00",
                )
                seed_evaluation(
                    conn,
                    pr_number=236,
                    comment_id=1,
                    author="lrwei0709",
                    created_at="2026-05-25T10:10:36+08:00",
                    score=3,
                    body="【MR评价】评价分数:3.1, 评价意见：达标",
                )

            bundle = export_static_bundle(
                db_path=db_path,
                output_path=output_path,
                repo=RepoRef("cann", "torchtitan-npu"),
            )

            pr = bundle["dashboards"]["month"]["2026-05"]["prs"][0]
            self.assertEqual(pr["score"], 3.1)
            with sqlite3.connect(db_path) as conn:
                stored_score = conn.execute("SELECT score FROM mr_evaluations WHERE comment_id = 1").fetchone()[0]
            self.assertEqual(stored_score, 3.1)

    def test_export_checkpoints_score_backfill_into_main_database_file(self) -> None:
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
                    pr_number=236,
                    title="Refactored kl loss",
                    author="mystri",
                    merged_at="2026-05-28T19:53:51+08:00",
                )
                seed_evaluation(
                    conn,
                    pr_number=236,
                    comment_id=1,
                    author="lrwei0709",
                    created_at="2026-05-25T10:10:36+08:00",
                    score=3,
                    body="【MR评价】评价分数:3.1, 评价意见：达标",
                )

            export_static_bundle(
                db_path=db_path,
                output_path=output_path,
                repo=RepoRef("cann", "torchtitan-npu"),
            )
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{db_path}{suffix}")
                if sidecar.exists():
                    sidecar.unlink()

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                score_type = [
                    row["type"]
                    for row in conn.execute("PRAGMA table_info(mr_evaluations)")
                    if row["name"] == "score"
                ][0]
                stored_score = conn.execute("SELECT score FROM mr_evaluations WHERE comment_id = 1").fetchone()[0]
            self.assertEqual(score_type, "REAL")
            self.assertEqual(stored_score, 3.1)

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

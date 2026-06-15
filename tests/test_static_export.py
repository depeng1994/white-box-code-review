from __future__ import annotations

import json
import sqlite3
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


if __name__ == "__main__":
    unittest.main()

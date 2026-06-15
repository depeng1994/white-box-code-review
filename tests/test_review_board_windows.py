from __future__ import annotations

import unittest

from backend.review_board import day_window


class ReviewBoardWindowTest(unittest.TestCase):
    def test_day_window_uses_local_midnight_boundaries(self) -> None:
        start, end = day_window("2026-06-15")

        self.assertEqual(start.isoformat(), "2026-06-15T00:00:00+08:00")
        self.assertEqual(end.isoformat(), "2026-06-16T00:00:00+08:00")


if __name__ == "__main__":
    unittest.main()

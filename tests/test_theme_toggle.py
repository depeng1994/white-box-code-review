from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


class ThemeToggleTest(unittest.TestCase):
    def test_demo_exposes_light_theme_toggle(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-theme="dark"', html)
        self.assertIn('id="themeToggle"', html)
        self.assertIn('data-theme="light"', css)
        self.assertIn("--bg: #fdfdf7", css.lower())
        self.assertIn("--accent: #d4a27f", css.lower())
        self.assertIn("localStorage", js)
        self.assertIn("reviewBoardTheme", js)
        self.assertIn("themeToggle", js)

    def test_pr_detail_and_contributor_groups_are_visually_prioritized(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn("function prioritizeReviewDetails", js)
        self.assertIn('item.type === "MR评价"', js)
        self.assertIn("prioritizeReviewDetails(row.detail || [])", js)
        self.assertIn('class="submit-group"', html)
        self.assertIn('class="review-group"', html)
        self.assertIn('class="submit-metric"', js)
        self.assertIn('class="review-metric"', js)
        self.assertIn(".contributor-table .submit-group", css)
        self.assertIn(".contributor-table .review-group", css)
        self.assertIn(".contributor-table .submit-metric", css)
        self.assertIn(".contributor-table .review-metric", css)


if __name__ == "__main__":
    unittest.main()

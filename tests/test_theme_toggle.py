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
        self.assertIn('a.type === "MR评价"', js)
        self.assertIn('b.type === "MR评价"', js)
        self.assertIn("prioritizeReviewDetails(row.detail || [])", js)
        self.assertIn("pr.reviewer === contributor", js)
        self.assertIn('class="submit-group"', html)
        self.assertIn('class="review-group"', html)
        self.assertIn('class="submit-metric"', js)
        self.assertIn('class="review-metric"', js)
        self.assertIn(".contributor-table .submit-group", css)
        self.assertIn(".contributor-table .review-group", css)
        self.assertIn(".contributor-table .submit-metric", css)
        self.assertIn(".contributor-table .review-metric", css)

    def test_review_contribution_includes_poor_score_rate(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn('<th class="review-group" colspan="7">检视贡献</th>', html)
        self.assertIn('data-sort="scored_poor_rate"', html)
        self.assertIn("待改进评分占比", html)
        self.assertIn('metricLink(row, "scored_poor_rate", percent(row.scored_poor, row.scored_prs))', js)
        self.assertIn('scored_poor_rate: "打分待改进占比"', js)
        self.assertIn('["scored_poor", "scored_poor_rate"].includes(metric)', js)

    def test_static_assets_are_versioned_to_avoid_mixed_html_and_js(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")

        self.assertIn('data-asset-version="local"', html)
        self.assertIn('href="./styles.css?v=local"', html)
        self.assertIn('src="./app.js?v=local"', html)
        self.assertIn("assetVersion", js)
        self.assertIn("./dashboard-static.json?v=", js)
        self.assertIn("scripts/stamp_static_assets.py", workflow)
        self.assertIn("github.sha", workflow)


if __name__ == "__main__":
    unittest.main()

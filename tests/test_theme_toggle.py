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
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-theme="dark"', html)
        self.assertIn('id="themeToggle"', html)
        self.assertIn('data-theme="light"', css)
        self.assertIn("--bg: #fdfdf7", css.lower())
        self.assertIn("--accent: #d4a27f", css.lower())
        self.assertIn("localStorage", js)
        self.assertIn("reviewBoardTheme", js)
        self.assertIn("themeToggle", js)

    def test_demo_removes_nonfunctional_chrome(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        for text in [
            "WhiteBox Review",
            "PR Review Intelligence",
            "PR 明细",
            "数据刷新",
            "最近刷新",
            "导出 CSV",
            "刷新数据",
        ]:
            self.assertNotIn(text, html)

        self.assertNotIn('class="sidebar"', html)
        self.assertNotIn('class="nav-stack"', html)
        self.assertNotIn("grid-template-columns: 260px minmax(0, 1fr)", css)
        self.assertNotIn(".sidebar", css)
        self.assertNotIn(".brand", css)
        self.assertNotIn(".nav-item", css)
        self.assertNotIn(".sync-panel", css)
        self.assertNotIn(".sync-time", js)
        self.assertNotIn(".sync-note", js)

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

        self.assertIn('<th class="review-group" colspan="8">检视贡献</th>', html)
        self.assertIn('data-sort="scored_poor_rate"', html)
        self.assertIn("待改进评分占比", html)
        self.assertIn('complianceMetricLink(row, "scored_poor_rate", percent(row.scored_poor, row.scored_prs))', js)
        self.assertIn('scored_poor_rate: "打分待改进占比"', js)
        self.assertIn('["scored_poor", "scored_poor_rate"].includes(metric)', js)

    def test_review_contribution_includes_nonstandard_prs(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-sort="nonstandard_prs"', html)
        self.assertIn("非标PR数", html)
        self.assertIn('metricLink(row, "nonstandard_prs", formatNumber(row.nonstandard_prs))', js)
        self.assertIn('nonstandard_prs: "非标 PR"', js)
        self.assertIn('pr.nonstandardReviewer === contributor', js)

    def test_committer_users_render_with_badge(self) -> None:
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        for user in [
            "depeng1994",
            "zhong_lin",
            "lrwei0709",
            "zzyyjj012",
            "xuyujun",
            "panchao-gitcode",
            "zhaowei1936",
            "zhanghz1",
        ]:
            self.assertIn(f'"{user}"', js)

        self.assertIn("function renderUserName", js)
        self.assertIn('class="committer-badge"', js)
        self.assertIn("renderUserName(row.author)", js)
        self.assertIn("renderUserName(row.reviewer)", js)
        self.assertIn("renderUserName(row.name)", js)
        self.assertIn("renderUserName(item.author)", js)
        self.assertIn(".committer-badge", css)

    def test_contributor_view_can_filter_by_committer_role(self) -> None:
        html = (DEMO / "index.html").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="contributorRoleFilter"', html)
        self.assertIn('value="all"', html)
        self.assertIn('value="committer"', html)
        self.assertIn('value="non_committer"', html)
        self.assertIn("const contributorRoleFilter", js)
        self.assertIn("function matchesContributorRole", js)
        self.assertIn('contributorRoleFilter.value === "committer"', js)
        self.assertIn('contributorRoleFilter.value === "non_committer"', js)
        self.assertIn(".filter(matchesContributorRole)", js)
        self.assertIn('contributorRoleFilter.addEventListener("change", renderAll)', js)

    def test_committer_review_score_rates_are_compliance_colored(self) -> None:
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn("function complianceClass", js)
        self.assertIn("function complianceMetricLink", js)
        self.assertIn('metric === "scored_poor_rate"', js)
        self.assertIn('metric === "scored_excellent_rate"', js)
        self.assertIn("COMMITTER_USERS.has(row.name)", js)
        self.assertIn('complianceMetricLink(row, "scored_poor_rate"', js)
        self.assertIn('complianceMetricLink(row, "scored_excellent_rate"', js)
        self.assertIn("compliance-alert", css)
        self.assertIn("compliance-warn", css)
        self.assertIn("compliance-ok", css)

    def test_pr_number_links_to_source_pull_request(self) -> None:
        css = (DEMO / "styles.css").read_text(encoding="utf-8")
        js = (DEMO / "app.js").read_text(encoding="utf-8")

        self.assertIn("function renderPrLink", js)
        self.assertIn("row.htmlUrl", js)
        self.assertIn('target="_blank"', js)
        self.assertIn('rel="noopener noreferrer"', js)
        self.assertIn('class="pr-link"', js)
        self.assertIn("${renderPrLink(row)}", js)
        self.assertIn('event.target.closest(".pr-link")', js)
        self.assertIn("event.stopPropagation()", js)
        self.assertIn(".pr-link", css)

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

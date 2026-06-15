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


if __name__ == "__main__":
    unittest.main()

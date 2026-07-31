import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class HomepageDesignTests(unittest.TestCase):
    def test_root_route_serves_premium_design(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        start = source.index('@app.get("/",include_in_schema=False)')
        end = source.index('@app.get("/painel",include_in_schema=False)', start)
        self.assertIn("FileResponse(static/'landing.html')", source[start:end])
        self.assertIn('RedirectResponse("/", status_code=308)', source)

    def test_legacy_auth_page_accepts_direct_login_and_register_entry(self):
        script = (ROOT / "app" / "static" / "landing.js").read_text(encoding="utf-8")
        self.assertIn("const access = params.get('access')", script)
        self.assertIn("showAuth(access)", script)


if __name__ == "__main__":
    unittest.main()

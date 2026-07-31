import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "app" / "static"


class PreviewDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "preview-design.html").read_text(encoding="utf-8")
        cls.css = (STATIC / "preview-design.css").read_text(encoding="utf-8")
        cls.script = (STATIC / "preview-design.js").read_text(encoding="utf-8")

    def test_preview_is_the_indexable_production_landing(self):
        self.assertIn('<meta name="robots" content="index, follow">', self.html)
        self.assertIn('<link rel="canonical" href="https://cortaflow.com.br/">', self.html)
        self.assertIn('/preview-design.css', self.html)
        self.assertIn('/preview-design.js', self.html)

    def test_navigation_and_signup_entry_points_exist(self):
        for label in ("Produto", "Como funciona", "Para sua equipe", "Planos", "Entrar", "Começar grátis"):
            self.assertIn(label, self.html)
        self.assertIn('id="signup-modal"', self.html)
        self.assertIn('data-open-signup', self.html)

    def test_signup_has_three_steps_and_safe_team_plan_mapping(self):
        for number in (1, 2, 3):
            self.assertIn(f'data-step="{number}"', self.html)
        self.assertIn("const teamPlanMap = { solo: 'essencial', duo: 'profissional', team: 'premium' }", self.script)
        self.assertIn("plans[plan].rank >= plans[recommendedPlanForTeam(team)].rank", self.script)
        self.assertNotIn("barbershop_id", self.script)
        self.assertNotIn("payment_status", self.script)

    def test_exact_plan_prices_and_trial_copy(self):
        for price in ("29<sup>,90", "44<sup>,90", "64<sup>,90"):
            self.assertIn(price, self.html)
        self.assertIn("14 dias grátis", self.html)
        self.assertIn("R$ 0 hoje", self.html)

    def test_product_tabs_are_accessible_and_keyboard_operable(self):
        self.assertIn('role="tablist"', self.html)
        self.assertEqual(self.html.count('role="tabpanel"'), 4)
        for key in ("ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"):
            self.assertIn(key, self.script)

    def test_mobile_menu_faq_and_modal_accessibility(self):
        self.assertIn("aria-expanded", self.script)
        self.assertIn("event.key === 'Escape'", self.script)
        self.assertIn("event.key === 'Tab'", self.script)
        self.assertIn("(max-width: 820px)", self.script)

    def test_login_and_payment_callbacks_keep_the_complete_auth_flow(self):
        self.assertIn("/landing.html?access=login", self.script)
        for parameter in ("email_confirmado", "checkout", "google", "reset_password"):
            self.assertIn(parameter, self.script)
        self.assertIn("/landing.html${window.location.search}", self.script)

    def test_visual_tokens_and_responsive_fallbacks(self):
        for token in ("#F4F1E9", "#101411", "#153E32", "#B8FF65"):
            self.assertIn(token, self.css)
        self.assertIn("overflow-x:hidden", self.css)
        self.assertIn("@media(max-width:820px)", self.css)
        self.assertIn("@media(max-width:520px)", self.css)
        self.assertIn("prefers-reduced-motion:reduce", self.css)


if __name__ == "__main__":
    unittest.main()

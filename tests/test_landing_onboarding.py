import unittest
from pathlib import Path


STATIC = Path(__file__).parents[1] / "app" / "static"


class LandingOnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "landing.html").read_text(encoding="utf-8")
        cls.script = (STATIC / "landing.js").read_text(encoding="utf-8")

    def test_onboarding_starts_with_team_size_and_keeps_plan_hidden_field(self):
        self.assertIn('id="team-size-picker"', self.html)
        self.assertIn('value="solo"', self.html)
        self.assertIn('value="duo"', self.html)
        self.assertIn('value="team"', self.html)
        self.assertIn('id="register-plan" type="hidden" name="plano"', self.html)

    def test_recommendation_maps_team_size_to_existing_plan_rules(self):
        self.assertIn("const teamPlanRules = { solo: 'essencial', duo: 'profissional', team: 'premium' }", self.script)
        self.assertIn('function recommendedPlanForTeam(teamSize)', self.script)
        self.assertIn('function planIsCompatible(plan, teamSize)', self.script)

    def test_plan_switch_cannot_select_a_plan_below_team_capacity(self):
        self.assertIn("if (!planIsCompatible(input.value, teamSize))", self.script)
        self.assertIn("Este plano não comporta o tamanho informado da sua equipe.", self.script)

    def test_mobile_showcase_covers_the_five_product_areas(self):
        self.assertIn('class="section showcase-section"', self.html)
        self.assertIn('Veja o CortaFlow por dentro.', self.html)
        for index, area in enumerate(('Agenda', 'Equipe', 'Clientes', 'Financeiro', 'Insights'), 1):
            self.assertIn(f'<span>{index:02d}</span><h3>{area}</h3>', self.html)
            self.assertIn(f'mobile-{area.lower()}-cutout.png', self.html)


if __name__ == "__main__":
    unittest.main()

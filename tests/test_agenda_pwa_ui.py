import unittest
from pathlib import Path


STATIC = Path(__file__).parents[1] / "app" / "static"


class AgendaPwaUiTests(unittest.TestCase):
    def test_agenda_has_distinct_confirmation_and_completion_actions(self):
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("function confirmAppointment", script)
        self.assertIn("function concludeAppointment", script)
        self.assertIn("function markNoShow", script)
        self.assertIn("'nao_compareceu'", script)

    def test_new_client_slot_prefills_customer(self):
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-client-id="${client.id}"', script)
        self.assertIn("function openAppointment(id = null, preset = {})", script)

    def test_csp_compatible_buttons_do_not_use_inline_javascript(self):
        for filename in ("index.html", "cliente.html"):
            with self.subTest(filename=filename):
                html = (STATIC / filename).read_text(encoding="utf-8")
                self.assertNotIn("onclick=", html)
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("onclick=", script)
        self.assertIn('data-action="add-appointment"', script)

    def test_pwa_has_push_subscription_and_service_worker_handlers(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        worker = (STATIC / "sw.js").read_text(encoding="utf-8")
        self.assertIn('id="push-notifications"', html)
        self.assertIn("pushManager.subscribe", script)
        self.assertIn("api('/push/test'", script)
        self.assertIn("self.addEventListener('push'", worker)
        self.assertIn("self.addEventListener('notificationclick'", worker)


if __name__ == "__main__":
    unittest.main()

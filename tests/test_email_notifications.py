import unittest
from datetime import datetime
from decimal import Decimal

from app.services.email import BRAND_ICON_URL, _email_html, _owner_email_html, _owner_whatsapp_url


def notification_item(phone="(11) 99999-8888"):
    return {
        "id": 42,
        "cliente_nome": "Mateus",
        "cliente_telefone": phone,
        "cliente_email": "cliente@gmail.com",
        "data_hora": datetime(2026, 7, 22, 14, 30),
        "servico": "Corte + Barba",
        "preco": Decimal("50.00"),
        "barbeiro_nome": "Otavio",
        "barbearia_nome": "Blackbarber",
        "barbearia_logo_url": "https://cdn.example.com/blackbarber.png",
    }


class OwnerEmailNotificationTests(unittest.TestCase):
    def test_builds_brazilian_whatsapp_deep_link(self):
        url = _owner_whatsapp_url(notification_item())
        self.assertTrue(url.startswith("https://wa.me/5511999998888?text="))
        self.assertIn("Recebemos%20seu%20agendamento", url)

    def test_html_contains_client_contacts_and_action(self):
        html = _owner_email_html(notification_item())
        self.assertIn("https://cdn.example.com/blackbarber.png", html)
        self.assertNotIn(BRAND_ICON_URL, html)
        self.assertIn('border-radius:50%', html)
        self.assertIn("Abrir conversa no WhatsApp", html)
        self.assertIn("mailto:cliente@gmail.com", html)
        self.assertIn("Corte + Barba", html)
        self.assertIn("#0042", html)

    def test_invalid_phone_omits_whatsapp_button(self):
        html = _owner_email_html(notification_item("123"))
        self.assertNotIn("Abrir conversa no WhatsApp", html)
        self.assertIn("WhatsApp: 123", html)

    def test_customer_email_contains_circular_brand_logo(self):
        html = _email_html(notification_item())
        self.assertIn("https://cdn.example.com/blackbarber.png", html)
        self.assertIn("Agendamento por CortaFlow", html)

    def test_uses_cortaflow_logo_when_shop_has_no_logo(self):
        item = notification_item()
        item["barbearia_logo_url"] = ""
        html = _email_html(item)
        self.assertIn(BRAND_ICON_URL, html)

    def test_uses_cortaflow_logo_for_legacy_local_upload(self):
        item = notification_item()
        item["barbearia_logo_url"] = "/uploads/blackbarber.png"
        html = _email_html(item)
        self.assertIn(BRAND_ICON_URL, html)
        self.assertNotIn("/uploads/blackbarber.png", html)


if __name__ == "__main__":
    unittest.main()

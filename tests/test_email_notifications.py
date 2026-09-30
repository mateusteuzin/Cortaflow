import unittest
import json
from datetime import datetime
from decimal import Decimal
from urllib.error import URLError
from unittest.mock import patch

from app.services.email import (
    BRAND_ICON_URL,
    _email_html,
    _owner_email_html,
    _owner_whatsapp_url,
    _barber_notification_html,
    send_account_verification,
    send_password_reset,
    send_subscription_confirmation,
)


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
    def test_booking_templates_share_responsive_white_table_layout(self):
        item = notification_item()
        for html in (_email_html(item), _owner_email_html(item),
                     *(_barber_notification_html(item, event)
                       for event in ("novo", "reagendado", "cancelado"))):
            with self.subTest(html=html[:80]):
                self.assertIn('max-width:600px', html)
                self.assertIn('<meta name="viewport"', html)
                self.assertIn('background:#ffffff', html)
                self.assertNotIn('background:#10120e', html)
                self.assertIn('role="presentation"', html)

    def test_booking_dynamic_values_are_escaped(self):
        item = notification_item()
        item.update(cliente_nome='<script>bad</script>',
                    observacoes='<img src=x onerror=bad>',
                    barbearia_nome='Shop & Friends')
        for html in (_email_html(item), _owner_email_html(item),
                     _barber_notification_html(item, "novo")):
            self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
            self.assertIn('Shop &amp; Friends', html)
            self.assertNotIn('<img src=x', html)

    @patch.dict("os.environ", {
        "RESEND_API_KEY": "re_test",
        "EMAIL_FROM": "CortaFlow <contato@cortaflow.com.br>",
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
    })
    @patch("app.services.email.urlopen")
    def test_account_verification_has_text_fallback_and_safe_mobile_html(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"email_1"}'

        sent = send_account_verification(
            "dono@gmail.com",
            "Mateus <script>alert(1)</script>",
            "token/com espaço?",
        )

        self.assertTrue(sent)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["subject"], "Confirme seu e-mail | CortaFlow")
        self.assertEqual(payload["from"], "CortaFlow <contato@cortaflow.com.br>")
        self.assertEqual(payload["to"], ["dono@gmail.com"])
        self.assertEqual(payload["headers"]["Auto-Submitted"], "auto-generated")
        self.assertEqual(payload["headers"]["X-Auto-Response-Suppress"], "All")
        self.assertTrue(payload["headers"]["X-Entity-Ref-ID"].startswith("cortaflow-"))
        self.assertIn("token%2Fcom%20espa%C3%A7o%3F", payload["html"])
        self.assertIn("token%2Fcom%20espa%C3%A7o%3F", payload["text"])
        self.assertIn("&lt;script&gt;", payload["html"])
        self.assertNotIn("<script>alert(1)</script>", payload["html"])
        self.assertIn('<meta name="viewport"', payload["html"])
        self.assertIn("@media only screen and (max-width: 640px)", payload["html"])
        self.assertIn("Sua conta só será ativada depois da confirmação do pagamento.", payload["text"])
        for marker in ("Ã", "Â", "â€"):
            self.assertNotIn(marker, payload["html"])
            self.assertNotIn(marker, payload["text"])

    @patch.dict("os.environ", {
        "RESEND_API_KEY": "re_test",
        "EMAIL_FROM": "CortaFlow <contato@cortaflow.com.br>",
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
    })
    @patch("app.services.email.urlopen")
    def test_password_reset_email_contains_secure_action(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"email_1"}'
        self.assertTrue(send_password_reset("dono@gmail.com", "Mateus", "token-seguro-1234567890"))
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["subject"], "Redefinição de senha | CortaFlow")
        self.assertIn("/api/auth/redefinir-senha?token=", payload["html"])
        self.assertIn("Definir nova senha", payload["html"])
        self.assertIn("uso único", payload["text"])
        self.assertIn("expira em 24 horas", payload["text"])
        self.assertEqual(payload["headers"]["Auto-Submitted"], "auto-generated")
        for marker in ("Ã", "Â", "â€"):
            self.assertNotIn(marker, payload["html"])
            self.assertNotIn(marker, payload["text"])

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
        self.assertIn("Agendamento realizado pelo CortaFlow", html)

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

    @patch.dict("os.environ", {
        "RESEND_API_KEY": "re_test",
        "EMAIL_FROM": "CortaFlow <contato@cortaflow.com.br>",
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
    })
    @patch("app.services.email.urlopen")
    def test_subscription_confirmation_contains_plan_and_renewal(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"email_1"}'
        sent = send_subscription_confirmation(
            "dono@gmail.com", "Mateus", "CortaFlow Profissional", 4490,
            datetime(2026, 8, 23),
        )
        self.assertTrue(sent)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["to"], ["dono@gmail.com"])
        self.assertEqual(
            payload["subject"],
            "Pagamento confirmado | CortaFlow Profissional",
        )
        self.assertIn("CortaFlow Profissional", payload["html"])
        self.assertIn("R$ 44,90", payload["html"])
        self.assertIn("23/08/2026", payload["html"])
        self.assertIn("CortaFlow Profissional", payload["text"])
        self.assertIn("R$ 44,90", payload["text"])
        self.assertIn("https://cortaflow.com.br/painel", payload["text"])
        self.assertIn("Cobrança protegida pela Stripe", payload["html"])
        for marker in ("Ã", "Â", "â€"):
            self.assertNotIn(marker, payload["html"])
            self.assertNotIn(marker, payload["text"])

    @patch.dict("os.environ", {
        "RESEND_API_KEY": "re_test",
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
    })
    @patch("app.services.email.logger.warning")
    @patch("app.services.email.urlopen", side_effect=URLError("offline"))
    def test_failed_transactional_email_does_not_log_token(
        self,
        _mocked_urlopen,
        mocked_warning,
    ):
        token = "segredo-que-nao-pode-aparecer"

        sent = send_password_reset("dono@gmail.com", "Mateus", token)

        self.assertFalse(sent)
        logged_call = repr(mocked_warning.call_args)
        self.assertNotIn(token, logged_call)
        self.assertNotIn("token=", logged_call)

    @patch.dict("os.environ", {"RESEND_API_KEY": ""})
    @patch("app.services.email.urlopen")
    def test_transactional_email_is_not_requested_without_resend_key(self, mocked_urlopen):
        sent = send_password_reset("dono@gmail.com", "Mateus", "token")

        self.assertFalse(sent)
        mocked_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

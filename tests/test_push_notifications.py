import unittest
from datetime import datetime
from unittest.mock import patch

from app.services import push


PUSH_ENV = {
    "VAPID_PUBLIC_KEY": "public-key",
    "VAPID_PRIVATE_KEY": "private-key",
    "VAPID_CLAIMS_EMAIL": "avisos@example.com",
}


class PushNotificationTests(unittest.TestCase):
    def test_requires_complete_vapid_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(push.push_is_configured())
        with patch.dict("os.environ", PUSH_ENV, clear=True):
            self.assertTrue(push.push_is_configured())

    @patch("pywebpush.webpush")
    @patch("app.services.push.all_rows")
    @patch("app.services.push.one")
    def test_sends_to_shop_admin_and_assigned_barber_only(self, mocked_one, mocked_rows, mocked_webpush):
        mocked_one.side_effect = [
            {
                "id": 42,
                "barbearia_id": 7,
                "barbeiro_id": 9,
                "cliente_nome": "João",
                "data_hora": datetime(2026, 7, 30, 14, 30),
                "servico": "Corte",
                "status": "agendado",
                "barbeiro_nome": "Otávio",
            },
            {"id": 1},
        ]
        mocked_rows.return_value = [{
            "id": 1,
            "endpoint": "https://push.example/subscription",
            "p256dh": "p256dh-key",
            "auth": "auth-key",
        }]
        with patch.dict("os.environ", PUSH_ENV, clear=True):
            sent = push.send_appointment_push(42, "novo")

        self.assertEqual(sent, 1)
        self.assertEqual(mocked_rows.call_args.args[1], (7, 9))
        mocked_webpush.assert_called_once()
        payload = mocked_webpush.call_args.kwargs["data"]
        self.assertIn("Novo agendamento", payload)
        self.assertIn("João", payload)


if __name__ == "__main__":
    unittest.main()

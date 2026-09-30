import unittest
from datetime import datetime
from unittest.mock import patch

from app.schemas import PushSubscription
from app.services import push
from pydantic import ValidationError


PUSH_ENV = {
    "VAPID_PUBLIC_KEY": "public-key",
    "VAPID_PRIVATE_KEY": "private-key",
    "VAPID_CLAIMS_EMAIL": "avisos@example.com",
}


class PushNotificationTests(unittest.TestCase):
    def test_browser_subscription_accepts_standard_expiration_time(self):
        subscription = PushSubscription(**{
            "endpoint": "https://fcm.googleapis.com/fcm/send/subscription",
            "expirationTime": None,
            "keys": {
                "p256dh": "p256dh-key-with-enough-length",
                "auth": "auth-key-value",
            },
        })
        self.assertIsNone(subscription.expiration_time)

    def test_requires_complete_vapid_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(push.push_is_configured())
        with patch.dict("os.environ", PUSH_ENV, clear=True):
            self.assertTrue(push.push_is_configured())

    def test_rejects_arbitrary_push_hosts_and_credentialed_urls(self):
        for endpoint in ("https://127.0.0.1/private", "https://internal.example/private",
                         "https://fcm.googleapis.com.attacker.example/push",
                         "https://user:password@fcm.googleapis.com/push",
                         "https://fcm.googleapis.com:8443/push"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValidationError):
                PushSubscription(endpoint=endpoint, keys={
                    "p256dh": "p256dh-key-with-enough-length", "auth": "auth-key-value"})

    @patch("pywebpush.webpush")
    def test_invalid_stored_subscription_never_makes_network_request(self, mocked_webpush):
        with patch.dict("os.environ", PUSH_ENV, clear=True):
            sent = push._send_payload([{"id": 1, "endpoint": "https://127.0.0.1/private",
                                       "p256dh": "key", "auth": "key"}], {"title": "test"})
        self.assertEqual(sent, 0)
        mocked_webpush.assert_not_called()

    @patch("requests.Session.request")
    def test_push_transport_does_not_follow_redirects(self, request):
        session = push._PushSession()
        session.post("https://fcm.googleapis.com/fcm/send/subscription", allow_redirects=True)
        self.assertFalse(request.call_args.kwargs["allow_redirects"])

    @patch("requests.Session.request")
    def test_push_transport_rechecks_destination_before_network_io(self, request):
        session = push._PushSession()
        with self.assertRaises(ValueError):
            session.post("https://127.0.0.1/private")
        request.assert_not_called()

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
            "endpoint": "https://fcm.googleapis.com/fcm/send/subscription",
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

    @patch("pywebpush.webpush")
    @patch("app.services.push.all_rows")
    @patch("app.services.push.one", return_value={"id": 1})
    def test_user_can_receive_immediate_test_notification(self, _mocked_one, mocked_rows, mocked_webpush):
        mocked_rows.return_value = [{
            "id": 1,
            "endpoint": "https://fcm.googleapis.com/fcm/send/subscription",
            "p256dh": "p256dh-key",
            "auth": "auth-key",
        }]
        with patch.dict("os.environ", PUSH_ENV, clear=True):
            sent = push.send_user_test_push(3, 7)

        self.assertEqual(sent, 1)
        self.assertEqual(mocked_rows.call_args.args[1], (3, 7))
        self.assertIn("Notificações ativadas", mocked_webpush.call_args.kwargs["data"])


if __name__ == "__main__":
    unittest.main()

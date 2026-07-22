import io
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.services.whatsapp import (
    AppointmentMessage,
    MetaWhatsAppService,
    WhatsAppError,
    mask_phone,
    normalize_phone,
    verify_webhook_signature,
)
from app.services.whatsapp_worker import WhatsAppWorker


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def message(phone="(88) 99999-9999"):
    return AppointmentMessage(
        appointment_id=42,
        client_name="Cliente Teste",
        client_phone=phone,
        service_name="Corte Social",
        starts_at=datetime(2026, 7, 22, 14, 30),
        professional_name="Profissional",
    )


class PhoneTests(unittest.TestCase):
    def test_normalizes_brazilian_phone(self):
        self.assertEqual(normalize_phone("(88) 99999-9999"), "5588999999999")

    def test_rejects_missing_or_invalid_phone(self):
        for value in ("", "123", "0000000000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_phone(value)

    def test_masks_phone_in_logs(self):
        masked = mask_phone("5588999999999")
        self.assertTrue(masked.startswith("5588"))
        self.assertTrue(masked.endswith("999"))
        self.assertNotIn("999999999", masked)


class MetaServiceTests(unittest.TestCase):
    def service(self, opener):
        return MetaWhatsAppService(
            api_url="https://graph.facebook.test/v23.0",
            access_token="secret-test-token",
            phone_number_id="123456",
            template_name="confirmacao_agendamento",
            template_language="pt_BR",
            opener=opener,
        )

    def test_builds_six_template_variables_in_order(self):
        _, payload = self.service(lambda *_args, **_kwargs: None).build_payload(message())
        parameters = payload["template"]["components"][0]["parameters"]
        self.assertEqual([item["text"] for item in parameters], [
            "Cliente Teste", "Corte Social", "22/07/2026", "14:30", "Profissional", "AG-000042"
        ])

    def test_success_returns_meta_message_id(self):
        service = self.service(lambda *_args, **_kwargs: FakeResponse({"messages": [{"id": "wamid.TEST"}]}))
        result = service.send_appointment_confirmation(message())
        self.assertEqual(result.message_id, "wamid.TEST")

    def test_token_error_is_permanent(self):
        def fail(request, timeout):
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with self.assertRaises(WhatsAppError) as captured:
            self.service(fail).send_appointment_confirmation(message())
        self.assertFalse(captured.exception.retryable)
        self.assertEqual(captured.exception.http_status, 401)

    def test_rate_limit_and_connection_errors_are_retryable(self):
        def limited(request, timeout):
            raise HTTPError(request.full_url, 429, "Limited", {}, io.BytesIO(b"{}"))
        with self.assertRaises(WhatsAppError) as captured:
            self.service(limited).send_appointment_confirmation(message())
        self.assertTrue(captured.exception.retryable)

    def test_invalid_template_is_permanent(self):
        def rejected(request, timeout):
            raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b"{}"))
        with self.assertRaises(WhatsAppError) as captured:
            self.service(rejected).send_appointment_confirmation(message())
        self.assertFalse(captured.exception.retryable)
        self.assertEqual(captured.exception.http_status, 400)

        with self.assertRaises(WhatsAppError) as captured:
            self.service(lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline"))).send_appointment_confirmation(message())
        self.assertTrue(captured.exception.retryable)

    def test_webhook_signature(self):
        body = b'{"object":"whatsapp_business_account"}'
        import hashlib, hmac
        signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(body, signature, "app-secret"))
        self.assertFalse(verify_webhook_signature(body + b"x", signature, "app-secret"))


class WorkerTests(unittest.TestCase):
    def test_success_is_recorded_and_next_poll_does_not_duplicate(self):
        service = Mock()
        service.send_appointment_confirmation.return_value = Mock(message_id="wamid.ONE", http_status=200)
        worker = WhatsAppWorker(service=service)
        row = {
            "id": 7, "cliente_nome": "Ana", "cliente_telefone": "88999999999",
            "data_hora": datetime(2026, 7, 22, 10), "servico": "Corte", "preco": 30,
            "barbeiro_nome": "João", "endereco": "", "whatsapp_tentativas": 1,
        }
        with patch.object(worker, "_claim_next", side_effect=[row, None]), \
             patch("app.services.whatsapp_worker.one") as update:
            self.assertTrue(worker.process_next())
            self.assertFalse(worker.process_next())
        service.send_appointment_confirmation.assert_called_once()
        self.assertIn("whatsapp_enviado=true", update.call_args.args[0])

    def test_whatsapp_failure_does_not_escape_worker(self):
        service = Mock()
        service.send_appointment_confirmation.side_effect = WhatsAppError("Meta indisponível", retryable=True)
        worker = WhatsAppWorker(service=service)
        row = {
            "id": 8, "cliente_nome": "Bia", "cliente_telefone": "88999999999",
            "data_hora": datetime(2026, 7, 22, 11), "servico": "Barba", "preco": 25,
            "barbeiro_nome": "João", "endereco": "", "whatsapp_tentativas": 1,
        }
        with patch.object(worker, "_claim_next", return_value=row), \
             patch.object(worker, "_record_failure") as failure:
            self.assertTrue(worker.process_next())
        failure.assert_called_once_with(8, 1, "Meta indisponível", True)

    def test_missing_phone_is_permanent_and_does_not_raise(self):
        worker = WhatsAppWorker(service=Mock())
        row = {
            "id": 9, "cliente_nome": "Sem telefone", "cliente_telefone": "",
            "data_hora": datetime(2026, 7, 22, 12), "servico": "Corte", "preco": 30,
            "barbeiro_nome": "João", "endereco": "", "whatsapp_tentativas": 1,
        }
        with patch.object(worker, "_claim_next", return_value=row), \
             patch.object(worker, "_record_failure") as failure:
            self.assertTrue(worker.process_next())
        failure.assert_called_once_with(9, 1, "Número de WhatsApp inválido", False)


if __name__ == "__main__":
    unittest.main()

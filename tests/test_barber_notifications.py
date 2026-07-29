import json
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.main import cancel, create_appointment, update_appointment
from app.schemas import Appointment, AppointmentUpdate, Barber, BarberSelfUpdate
from app.security import owner_user
from app.services.email import (
    _barber_notification_html,
    send_barber_appointment_notification,
)


def appointment_item(notification_email="barbeiro@example.com"):
    return {
        "id": 42,
        "barbearia_id": 7,
        "barbeiro_id": 9,
        "cliente_nome": "João <Cliente>",
        "cliente_telefone": "(11) 99999-8888",
        "cliente_email": "cliente@example.com",
        "data_hora": datetime(2026, 7, 30, 14, 30),
        "servico": "Corte + Barba",
        "preco": Decimal("50.00"),
        "observacoes": "Preferência: tesoura",
        "atualizado_em": datetime(2026, 7, 29, 11, 0),
        "barbeiro_nome": "Otávio",
        "notification_email": notification_email,
        "barbearia_nome": "BlackBarber",
        "barbearia_logo_url": "",
        "email_notificacoes": "admin@example.com",
        "notificar_novos_agendamentos": True,
    }


class BarberNotificationTests(unittest.TestCase):
    def test_barber_contacts_are_normalized_and_validated(self):
        barber = Barber(
            nome="Otávio",
            notification_email=" OTAVIO@EXAMPLE.COM ",
            telefone="(11) 99999-8888",
            whatsapp="11 98888-7777",
        )
        self.assertEqual(str(barber.notification_email), "otavio@example.com")
        self.assertEqual(barber.telefone, "11999998888")
        self.assertEqual(barber.whatsapp, "11988887777")
        with self.assertRaises(ValidationError):
            BarberSelfUpdate(nome="Otávio", telefone="123")

    def test_event_html_escapes_client_and_contains_complete_details(self):
        html = _barber_notification_html(appointment_item(), "reagendado")
        self.assertIn("AGENDAMENTO ALTERADO", html)
        self.assertIn("João &lt;Cliente&gt;", html)
        self.assertIn("Preferência: tesoura", html)
        self.assertIn("R$ 50,00", html)
        self.assertIn("/painel?view=agenda&amp;appointment=42", html)

    @patch.dict("os.environ", {
        "RESEND_API_KEY": "re_test",
        "EMAIL_FROM": "CortaFlow <nao-responda@cortaflow.com.br>",
    })
    @patch("app.services.email.urlopen")
    @patch("app.services.email.one")
    def test_sends_only_to_responsible_barber_with_idempotency(
        self, mocked_one, mocked_urlopen
    ):
        mocked_one.side_effect = [appointment_item(), {"id": 81}, {"id": 81}]
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"id":"resend_123"}'
        )

        sent = send_barber_appointment_notification(42, "novo", "novo-42")

        self.assertTrue(sent)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["to"], ["barbeiro@example.com"])
        self.assertEqual(request.headers["Idempotency-key"], "appointment/novo/81")
        self.assertIn("Novo agendamento", payload["subject"])

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("app.services.email.logger.warning")
    @patch("app.services.email.urlopen")
    @patch("app.services.email.one")
    def test_missing_barber_email_uses_admin_fallback(
        self, mocked_one, mocked_urlopen, mocked_warning
    ):
        mocked_one.side_effect = [appointment_item(""), {"id": 82}, {"id": 82}]
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"id":"resend_124"}'
        )

        self.assertTrue(
            send_barber_appointment_notification(42, "cancelado", "cancelado-1")
        )
        payload = json.loads(mocked_urlopen.call_args.args[0].data)
        self.assertEqual(payload["to"], ["admin@example.com"])
        self.assertTrue(mocked_warning.called)
        claim_params = mocked_one.call_args_list[1].args[1]
        self.assertEqual(claim_params[-1], "administrativo")

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("app.services.email.urlopen")
    @patch("app.services.email.one")
    def test_duplicate_event_is_not_sent_twice(self, mocked_one, mocked_urlopen):
        mocked_one.side_effect = [appointment_item(), None]

        sent = send_barber_appointment_notification(
            42, "reagendado", "reagendado-version-1"
        )

        self.assertFalse(sent)
        mocked_urlopen.assert_not_called()


class PwaAssetsTests(unittest.TestCase):
    static = Path(__file__).parents[1] / "app" / "static"

    def test_manifest_and_service_worker_are_complete(self):
        manifest = json.loads((self.static / "manifest.webmanifest").read_text("utf-8"))
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})
        for icon in manifest["icons"]:
            self.assertTrue((self.static / icon["src"].lstrip("/")).is_file())
        worker = (self.static / "sw.js").read_text("utf-8")
        self.assertIn("cortaflow-shell-20260729-1", worker)
        self.assertIn("url.pathname.startsWith('/api/')", worker)


class NotificationDispatchTests(unittest.TestCase):
    user = {"id": 1, "barbearia_id": 7, "perfil": "administrador"}

    @patch("app.main.dispatch_whatsapp")
    @patch("app.main.insert_appointment", return_value={"id": 42})
    def test_admin_created_appointment_schedules_customer_and_barber_emails(
        self, _mocked_insert, _mocked_dispatch
    ):
        tasks = BackgroundTasks()
        data = Appointment(
            barbeiro_id=9,
            servico_id=3,
            cliente_nome="João",
            cliente_telefone="11999998888",
            cliente_email="joao@example.com",
            data_hora=datetime(2026, 7, 30, 14, 30),
        )

        create_appointment(data, tasks, self.user)

        functions = [task.func.__name__ for task in tasks.tasks]
        self.assertIn("send_appointment_confirmation", functions)
        self.assertIn("send_owner_notification", functions)

    @patch("app.main.one")
    def test_rebooking_schedules_one_versioned_event(self, mocked_one):
        before = {
            "id": 42,
            "barbearia_id": 7,
            "barbeiro_id": 9,
            "status": "agendado",
            "data_hora": datetime(2026, 7, 30, 14, 30),
        }
        current = {
            **before,
            "data_hora": datetime(2026, 7, 30, 15, 0),
            "atualizado_em": datetime(2026, 7, 29, 12, 0),
        }
        mocked_one.side_effect = [before, current]
        tasks = BackgroundTasks()

        update_appointment(
            42,
            AppointmentUpdate(data_hora=current["data_hora"]),
            tasks,
            self.user,
        )

        self.assertEqual(len(tasks.tasks), 1)
        self.assertEqual(tasks.tasks[0].args[1], "reagendado")
        self.assertIn("2026-07-29T12:00:00", tasks.tasks[0].args[2])

    @patch("app.main.one")
    def test_cancellation_schedules_one_event(self, mocked_one):
        mocked_one.return_value = {
            "id": 42,
            "atualizado_em": datetime(2026, 7, 29, 12, 30),
        }
        tasks = BackgroundTasks()

        cancel(42, tasks, self.user)

        self.assertEqual(len(tasks.tasks), 1)
        self.assertEqual(tasks.tasks[0].args[1], "cancelado")

    def test_barber_cannot_use_owner_dependency(self):
        with self.assertRaises(HTTPException) as raised:
            owner_user({"perfil": "barbeiro"})
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

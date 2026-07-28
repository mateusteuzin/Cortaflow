import copy
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException

from app.main import conclude_appointment
from app.services.appointments import (
    AppointmentNotFoundError,
    InvalidAppointmentStatusError,
    complete_appointment,
)
from app.security import current_user


def appointment(appointment_id=1, shop_id=10, status="agendado", phone="11999999999"):
    return {
        "id": appointment_id,
        "barbearia_id": shop_id,
        "barbeiro_id": 7,
        "cliente_nome": "Cliente Teste",
        "cliente_telefone": phone,
        "cliente_email": "cliente@example.com",
        "whatsapp_telefone": phone,
        "whatsapp_autorizado": True,
        "whatsapp_status": "PENDENTE",
        "whatsapp_proxima_tentativa": "agora",
        "status": status,
        "servico": "Corte e barba",
        "preco": 75,
        "data_hora": "2026-07-22T10:00:00",
        "criado_em": "2026-07-20T10:00:00",
        "concluido_em": None,
        "atualizado_em": None,
    }


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.result = None

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT * FROM agendamentos"):
            appointment_id, shop_id = params
            row = self.state["appointments"].get(appointment_id)
            self.result = copy.deepcopy(row) if row and row["barbearia_id"] == shop_id else None
        elif normalized.startswith("UPDATE clientes SET"):
            price, service, name, shop_id, phone = params
            row = next((item for item in self.state["clients"]
                        if item["barbearia_id"] == shop_id and item["telefone"] == phone), None)
            if row:
                row["total_visitas"] += 1
                row["total_gasto"] += price
                row["ultimo_servico"] = service
                row["nome"] = name
            self.result = None
        elif normalized.startswith("INSERT INTO fidelidade_cliente"):
            shop_id, phone, name = params
            row = next((item for item in self.state["loyalty"] if item["barbearia_id"] == shop_id and item["cliente_telefone"] == phone), None)
            if row:
                row["total_cortes"] += 1
                row["cliente_nome"] = name
            else:
                row = {"id": len(self.state["loyalty"]) + 1, "barbearia_id": shop_id, "cliente_telefone": phone, "cliente_nome": name, "total_cortes": 1}
                self.state["loyalty"].append(row)
            self.result = {"id": row["id"]}
        elif normalized.startswith("SELECT EXISTS"):
            shop_id, excluded_id, phone, statuses = params
            active = any(
                row["barbearia_id"] == shop_id
                and row["id"] != excluded_id
                and row.get("cliente_telefone") == phone
                and row["status"] in statuses
                for row in self.state["appointments"].values()
            )
            self.result = {"has_active": active}
        elif normalized.startswith("UPDATE agendamentos SET"):
            if self.state.get("fail_update"):
                raise RuntimeError("falha simulada no banco")
            appointment_id, shop_id = params
            row = self.state["appointments"][appointment_id]
            if row["barbearia_id"] != shop_id:
                self.result = None
                return
            row.update({
                "status": "concluido",
                "cliente_email": None,
                "cliente_telefone": None,
                "whatsapp_telefone": None,
                "whatsapp_autorizado": False,
                "whatsapp_proxima_tentativa": None,
                "concluido_em": row.get("concluido_em") or "agora",
                "atualizado_em": "agora",
            })
            if row["whatsapp_status"] not in ("ENVIADO", "ENTREGUE", "LIDO"):
                row["whatsapp_status"] = "ENCERRADO"
            self.result = copy.deepcopy(row)
        elif normalized.startswith("UPDATE fidelidade_cliente SET"):
            shop_id, phone = params
            for row in self.state["loyalty"]:
                if row["barbearia_id"] == shop_id and row["cliente_telefone"] == phone:
                    row["cliente_telefone"] = None
            self.result = None
        else:
            raise AssertionError(f"SQL não previsto no teste: {normalized}")

    def fetchone(self):
        return self.result


class FakeDatabase:
    def __init__(self, appointments, loyalty=None, fail_update=False):
        client_rows = {}
        for row in appointments:
            if row.get("cliente_telefone"):
                key = (row["barbearia_id"], row["cliente_telefone"])
                client_rows[key] = {
                    "barbearia_id": row["barbearia_id"],
                    "telefone": row["cliente_telefone"],
                    "nome": row["cliente_nome"],
                    "total_visitas": 0,
                    "total_gasto": 0,
                    "ultimo_servico": None,
                }
        self.state = {
            "appointments": {row["id"]: copy.deepcopy(row) for row in appointments},
            "loyalty": copy.deepcopy(loyalty or []),
            "clients": list(client_rows.values()),
            "fail_update": fail_update,
        }

    @contextmanager
    def connection(self):
        snapshot = copy.deepcopy(self.state)
        try:
            yield FakeCursor(self.state)
        except Exception:
            self.state.clear()
            self.state.update(snapshot)
            raise


class AppointmentCompletionTests(unittest.TestCase):
    def complete(self, database, appointment_id=1, shop_id=10):
        with patch("app.services.appointments.db", database.connection):
            return complete_appointment(appointment_id, shop_id)

    def test_valid_completion_removes_email_and_phone(self):
        database = FakeDatabase([appointment()])
        result = self.complete(database)
        self.assertEqual(result["status"], "concluido")
        self.assertIsNone(result["cliente_email"])
        self.assertIsNone(result["cliente_telefone"])
        self.assertIsNone(result["whatsapp_telefone"])

    def test_pending_appointment_keeps_contacts_until_completion(self):
        database = FakeDatabase([appointment(status="agendado")])
        stored = database.state["appointments"][1]
        self.assertEqual(stored["cliente_email"], "cliente@example.com")
        self.assertEqual(stored["cliente_telefone"], "11999999999")

    def test_cancelled_appointment_keeps_contacts(self):
        database = FakeDatabase([appointment(status="cancelado")])
        with self.assertRaises(InvalidAppointmentStatusError):
            self.complete(database)
        self.assertEqual(database.state["appointments"][1]["cliente_email"], "cliente@example.com")

    def test_missing_appointment_returns_domain_error(self):
        database = FakeDatabase([])
        with self.assertRaises(AppointmentNotFoundError):
            self.complete(database, appointment_id=999)

    def test_duplicate_completion_is_idempotent(self):
        database = FakeDatabase([appointment()])
        self.complete(database)
        second = self.complete(database)
        self.assertEqual(second["status"], "concluido")
        self.assertEqual(database.state["loyalty"][0]["total_cortes"], 1)

    def test_business_and_audit_data_are_preserved(self):
        database = FakeDatabase([appointment()])
        result = self.complete(database)
        for field in ("id", "barbeiro_id", "cliente_nome", "data_hora", "servico", "preco", "criado_em"):
            self.assertEqual(result[field], appointment()[field])

    def test_transaction_failure_rolls_back_every_change(self):
        original = appointment()
        database = FakeDatabase([original], fail_update=True)
        with self.assertRaises(RuntimeError):
            self.complete(database)
        self.assertEqual(database.state["appointments"][1], original)
        self.assertEqual(database.state["loyalty"], [])

    def test_global_contact_is_kept_when_another_active_appointment_exists(self):
        phone = "11999999999"
        database = FakeDatabase(
            [appointment(), appointment(2, status="confirmado", phone=phone)],
            [{"id": 1, "barbearia_id": 10, "cliente_telefone": phone, "cliente_nome": "Cliente Teste", "total_cortes": 2}],
        )
        self.complete(database)
        self.assertEqual(database.state["loyalty"][0]["cliente_telefone"], phone)
        self.assertEqual(database.state["appointments"][2]["cliente_telefone"], phone)

    def test_other_shop_cannot_complete_appointment(self):
        database = FakeDatabase([appointment(shop_id=10)])
        with self.assertRaises(AppointmentNotFoundError):
            self.complete(database, shop_id=99)
        self.assertEqual(database.state["appointments"][1]["status"], "agendado")

    def test_unauthenticated_user_is_rejected(self):
        with self.assertRaises(HTTPException) as captured:
            current_user(None)
        self.assertEqual(captured.exception.status_code, 401)

    def test_api_response_never_returns_old_contacts(self):
        completed = appointment(status="concluido", phone=None)
        completed["cliente_email"] = None
        with patch("app.main.complete_appointment", return_value=completed):
            response = conclude_appointment(1, {"barbearia_id": 10})
        self.assertIsNone(response["agendamento"]["cliente_email"])
        self.assertIsNone(response["agendamento"]["cliente_telefone"])
        self.assertIn("dados de contato removidos", response["message"])


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from psycopg2 import IntegrityError
from pydantic import ValidationError

from app import main
from app.schemas import PublicAppointment
from app.services.slugs import slugify, unique_shop_slug


ACTIVE_SHOP = {
    "id": 7, "nome": "Barbearia Gold", "slug": "barbearia-gold",
    "telefone": "11999999999", "endereco": "Rua Teste", "logo_url": "",
    "plano_ativo": True, "public_booking_enabled": True,
}


class FakeSlugCursor:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.candidate = None

    def execute(self, _sql, params):
        self.candidate = params[0]

    def fetchone(self):
        return {"exists": True} if self.candidate in self.existing else None


def appointment_data(**overrides):
    values = {
        "barbeiro_id": 9,
        "servico_id": 4,
        "cliente_nome": "Cliente Teste",
        "cliente_telefone": "11999998888",
        "cliente_email": "cliente@example.com",
        "data_hora": datetime.now() + timedelta(days=2),
        "duracao_minutos": 30,
        "servico": "Corte",
        "preco": Decimal("40"),
        "whatsapp_autorizado": True,
    }
    values.update(overrides)
    return PublicAppointment(**values)


class SlugTests(unittest.TestCase):
    def test_normalizes_accents_spaces_and_symbols(self):
        self.assertEqual(slugify("  Corte do Rêi & Filhos!  "), "corte-do-rei-filhos")

    def test_equal_shop_names_receive_numeric_suffix(self):
        self.assertEqual(unique_shop_slug(FakeSlugCursor(), "Barbearia Gold"), "barbearia-gold")
        self.assertEqual(unique_shop_slug(FakeSlugCursor({"barbearia-gold"}), "Barbearia Gold"), "barbearia-gold-2")


class PublicBookingIsolationTests(unittest.TestCase):
    @patch("app.main.one", return_value=ACTIVE_SHOP)
    def test_valid_slug_returns_only_public_fields(self, _one):
        result = main.public_shop("barbearia-gold")
        self.assertEqual(result["slug"], "barbearia-gold")
        self.assertNotIn("id", result)
        self.assertNotIn("plano_ativo", result)

    @patch("app.main.one", return_value=None)
    def test_unknown_slug_is_friendly_404(self, _one):
        with self.assertRaises(HTTPException) as caught:
            main.resolve_public_shop("nao-existe")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("Verifique", caught.exception.detail)

    @patch("app.main.one", return_value={**ACTIVE_SHOP, "public_booking_enabled": False})
    def test_paused_shop_is_rejected(self, _one):
        with self.assertRaises(HTTPException) as caught:
            main.resolve_public_shop("barbearia-gold")
        self.assertEqual(caught.exception.status_code, 403)

    def test_public_payload_rejects_numeric_shop_id(self):
        with self.assertRaises(ValidationError):
            appointment_data(barbearia_id=99)

    @patch("app.main.one")
    def test_professional_from_another_shop_is_rejected(self, mocked_one):
        mocked_one.side_effect = [ACTIVE_SHOP, None]
        with self.assertRaises(HTTPException) as caught:
            main.public_slots("barbearia-gold", datetime.now().date(), 999, 4)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("Profissional", caught.exception.detail)

    @patch("app.main.one")
    def test_service_from_another_shop_is_rejected(self, mocked_one):
        mocked_one.side_effect = [ACTIVE_SHOP, {"id": 9}, None]
        with self.assertRaises(HTTPException) as caught:
            main.public_slots("barbearia-gold", datetime.now().date(), 9, 999)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("Serviço", caught.exception.detail)

    @patch("app.main.send_owner_notification")
    @patch("app.main.send_appointment_confirmation")
    @patch("app.main.dispatch_whatsapp")
    @patch("app.main.insert_appointment", return_value={"id": 52})
    @patch("app.main.available")
    @patch("app.main.validate_public_selection", return_value={"duracao_minutos": 30})
    @patch("app.main.resolve_public_shop", return_value=ACTIVE_SHOP)
    def test_complete_booking_uses_shop_resolved_from_slug(self, _shop, _selection, available, insert, _dispatch, _customer_email, _owner_email):
        data=appointment_data()
        available.return_value=[data.data_hora.strftime("%H:%M")]
        result = main.public_create("barbearia-gold", data, BackgroundTasks())
        self.assertEqual(result["id"], 52)
        self.assertEqual(insert.call_args.args[1], ACTIVE_SHOP["id"])

    @patch("app.main.available", return_value=[])
    @patch("app.main.validate_public_selection", return_value={"duracao_minutos": 30})
    @patch("app.main.resolve_public_shop", return_value=ACTIVE_SHOP)
    def test_unavailable_submitted_time_is_rejected(self, _shop, _selection, _available):
        with self.assertRaises(HTTPException) as caught:
            main.public_create("barbearia-gold", appointment_data(), BackgroundTasks())
        self.assertEqual(caught.exception.status_code, 409)

    @patch("app.main.db")
    def test_occupied_slot_returns_conflict(self, mocked_db):
        cursor=MagicMock()
        mocked_db.return_value.__enter__.return_value=cursor
        cursor.fetchone.return_value={"id":4,"nome":"Corte","duracao_minutos":30,"preco":Decimal("40")}
        cursor.execute.side_effect=[None,IntegrityError()]
        with self.assertRaises(HTTPException) as caught:
            main.insert_appointment(appointment_data(), ACTIVE_SHOP["id"])
        self.assertEqual(caught.exception.status_code, 409)

    @patch("app.main.db")
    def test_appointment_and_customer_are_written_in_one_transaction(self, mocked_db):
        cursor=MagicMock()
        mocked_db.return_value.__enter__.return_value=cursor
        cursor.fetchone.side_effect=[
            {"id":4,"nome":"Corte","duracao_minutos":30,"preco":Decimal("40")},
            {"id":52},
        ]
        result=main.insert_appointment(appointment_data(),ACTIVE_SHOP["id"])
        self.assertEqual(result["id"],52)
        self.assertEqual(cursor.execute.call_count,3)
        mocked_db.assert_called_once()

    def test_booking_page_is_served_for_slug_url(self):
        response = main.booking_page("barbearia-gold")
        self.assertTrue(Path(response.path).name == "cliente.html")

    def test_public_shop_listing_is_disabled(self):
        with self.assertRaises(HTTPException) as caught:
            main.public_shops()
        self.assertEqual(caught.exception.status_code, 410)

    def test_panel_contains_copy_link_action(self):
        html = Path("app/static/index.html").read_text(encoding="utf-8")
        script = Path("app/static/app.js").read_text(encoding="utf-8")
        self.assertIn('id="copy-booking-link"', html)
        self.assertIn("Link copiado com sucesso.", script)
        self.assertNotIn("Sou cliente: agendar horário", html)

    def test_public_page_never_lists_shops_or_uses_numeric_query(self):
        html = Path("app/static/cliente.html").read_text(encoding="utf-8")
        script = Path("app/static/cliente.js").read_text(encoding="utf-8")
        self.assertNotIn('id="shop-picker"', html)
        self.assertNotIn("/cliente/barbearias", script)
        self.assertNotIn("barbearia_id", script)


if __name__ == "__main__":
    unittest.main()

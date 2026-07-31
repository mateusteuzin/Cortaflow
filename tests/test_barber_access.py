import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from app import main
from app.schemas import Appointment, AppointmentUpdate


BARBER_USER = {
    "id": 21,
    "barbearia_id": 7,
    "barbeiro_id": 9,
    "perfil": "barbeiro",
}


class BarberAccessTests(unittest.TestCase):
    @patch("app.main.all_rows", return_value=[])
    def test_barber_appointments_ignore_requested_other_barber(self, rows):
        main.appointments(
            data=date(2026, 7, 31),
            barbeiro_id=999,
            user=BARBER_USER,
        )

        query, params = rows.call_args.args
        self.assertIn("a.barbeiro_id=%s", query)
        self.assertEqual(params[-1], BARBER_USER["barbeiro_id"])
        self.assertNotIn(999, params)

    @patch("app.main.all_rows", return_value=[])
    def test_barber_weekly_agenda_is_always_scoped_to_self(self, rows):
        main.weekly_appointments(
            inicio=date(2026, 7, 27),
            fim=date(2026, 8, 2),
            user=BARBER_USER,
        )

        query, params = rows.call_args.args
        self.assertIn("a.barbeiro_id=%s", query)
        self.assertEqual(params, (7, date(2026, 7, 27), date(2026, 8, 2), 9))

    @patch("app.main.send_owner_notification")
    @patch("app.main.dispatch_whatsapp")
    @patch("app.main.insert_appointment", return_value={"id": 44})
    def test_barber_created_appointment_is_forced_to_self(
        self, insert, _dispatch, _owner_notification
    ):
        payload = Appointment(
            barbeiro_id=999,
            servico_id=3,
            cliente_nome="Cliente",
            cliente_telefone="11999998888",
            data_hora=datetime(2026, 8, 1, 10, 0),
        )

        main.create_appointment(payload, BackgroundTasks(), BARBER_USER)

        inserted_payload, shop_id = insert.call_args.args
        self.assertEqual(shop_id, 7)
        self.assertEqual(inserted_payload.barbeiro_id, 9)

    @patch("app.main.one")
    def test_barber_cannot_reassign_appointment(self, database_one):
        database_one.return_value = {
            "id": 44,
            "barbearia_id": 7,
            "barbeiro_id": 9,
            "status": "agendado",
        }

        with self.assertRaises(HTTPException) as raised:
            main.update_appointment(
                44,
                AppointmentUpdate(barbeiro_id=10),
                BackgroundTasks(),
                BARBER_USER,
            )

        self.assertEqual(raised.exception.status_code, 403)

    @patch("app.main.one")
    def test_individual_summary_uses_only_linked_barber(self, database_one):
        database_one.return_value = {
            "nome": "Léo",
            "comissao_percentual": Decimal("40"),
            "cortes": 2,
            "faturamento": Decimal("100"),
            "comissao": Decimal("40"),
        }

        result = main.barber_daily_summary(date(2026, 7, 31), BARBER_USER)

        query, params = database_one.call_args.args
        self.assertIn("b.usuario_id=%s", query)
        self.assertEqual(params, (date(2026, 7, 31), 9, 7, 21))
        self.assertEqual(result["faturamento"], Decimal("100"))

    def test_owner_cannot_use_individual_barber_summary(self):
        with self.assertRaises(HTTPException) as raised:
            main.barber_daily_summary(
                date(2026, 7, 31),
                {"id": 1, "barbearia_id": 7, "perfil": "administrador"},
            )
        self.assertEqual(raised.exception.status_code, 403)

    @patch("app.main.one")
    @patch("app.main.all_rows")
    def test_individual_insights_include_only_linked_barber(self, rows, database_one):
        rows.return_value = [{
            "periodo": date(2026, 7, 12),
            "atendimentos": 4,
            "faturamento": Decimal("200"),
            "comissao": Decimal("80"),
        }]
        database_one.return_value = {
            "atendimentos": 4,
            "faturamento": Decimal("200"),
            "ticket_medio": Decimal("50"),
            "comissao": Decimal("80"),
        }

        result = main.barber_insights("mensal", 7, 2026, BARBER_USER)

        points_query, points_params = rows.call_args.args
        total_query, total_params = database_one.call_args.args
        self.assertIn("b.usuario_id=%s", points_query)
        self.assertIn("b.usuario_id=%s", total_query)
        self.assertEqual(points_params[:3], (9, 7, 21))
        self.assertEqual(total_params[2:], (9, 7, 21))
        self.assertEqual(result["melhor_periodo"]["atendimentos"], 4)
        self.assertEqual(result["total"]["comissao"], Decimal("80"))

    def test_owner_cannot_use_individual_barber_insights(self):
        with self.assertRaises(HTTPException) as raised:
            main.barber_insights(
                "mensal",
                7,
                2026,
                {"id": 1, "barbearia_id": 7, "perfil": "administrador"},
            )
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

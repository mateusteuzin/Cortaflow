import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.main import remove_cancelled_appointment, remove_customer


class FakeCursor:
    def __init__(self, selected):
        self.selected = selected
        self.commands = []

    def execute(self, query, params):
        self.commands.append((" ".join(query.split()), params))

    def fetchone(self):
        return self.selected


class CustomerAndHistoryActionTests(unittest.TestCase):
    @patch("app.main.one")
    def test_customer_delete_is_scoped_to_current_shop(self, mocked_one):
        mocked_one.return_value = {"id": 12, "nome": "Cliente"}

        result = remove_customer(12, {"barbearia_id": 7})

        self.assertTrue(result["ok"])
        self.assertEqual(mocked_one.call_args.args[1], (12, 7))

    @patch("app.main.db")
    def test_completed_appointment_can_be_permanently_removed(self, mocked_db):
        cursor = FakeCursor({"id": 42})

        @contextmanager
        def database():
            yield cursor

        mocked_db.side_effect = database

        result = remove_cancelled_appointment(42, {"barbearia_id": 7})

        self.assertTrue(result["ok"])
        self.assertIn("'concluido','realizado'", cursor.commands[0][0])
        self.assertEqual(cursor.commands[0][1], (42, 7))
        self.assertTrue(any(command.startswith("DELETE FROM agendamentos") for command, _ in cursor.commands))


if __name__ == "__main__":
    unittest.main()

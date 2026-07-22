import unittest

from pydantic import ValidationError

from app.schemas import Register


def register_data(email):
    return {
        "nome": "Mateus",
        "email": email,
        "senha": "segredo123",
        "telefone": "",
        "barbearia_nome": "Barbearia Teste",
    }


class RegisterEmailValidationTest(unittest.TestCase):
    def test_accepts_gmail(self):
        registration = Register(**register_data("dono@gmail.com"))
        self.assertEqual(str(registration.email), "dono@gmail.com")

    def test_accepts_googlemail(self):
        registration = Register(**register_data("dono@googlemail.com"))
        self.assertEqual(str(registration.email), "dono@googlemail.com")

    def test_rejects_other_domains(self):
        with self.assertRaisesRegex(ValidationError, "Use um e-mail oficial do Gmail"):
            Register(**register_data("dono@outlook.com"))


if __name__ == "__main__":
    unittest.main()

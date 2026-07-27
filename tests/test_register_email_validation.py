import unittest

from pydantic import ValidationError

from app.schemas import Register


def register_data(email):
    return {
        "nome": "Mateus",
        "email": email,
        "senha": "segredo12345",
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

    def test_accepts_professional_email_domains(self):
        registration = Register(**register_data("Dono@Empresa.com.br"))
        self.assertEqual(str(registration.email), "dono@empresa.com.br")

    def test_rejects_short_or_common_passwords(self):
        data = register_data("dono@gmail.com")
        data["senha"] = "12345678"
        with self.assertRaises(ValidationError):
            Register(**data)

    def test_accepts_subscription_plan(self):
        data = register_data("dono@gmail.com")
        data["plano"] = "premium"
        self.assertEqual(Register(**data).plano, "premium")

    def test_rejects_unknown_subscription_plan(self):
        data = register_data("dono@gmail.com")
        data["plano"] = "vitalicio"
        with self.assertRaises(ValidationError):
            Register(**data)


if __name__ == "__main__":
    unittest.main()

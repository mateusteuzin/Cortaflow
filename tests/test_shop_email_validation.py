import unittest

from pydantic import ValidationError

from app.schemas import ShopUpdate


def shop_data(email):
    return {
        "nome": "Barbearia Teste",
        "email_notificacoes": email,
    }


class ShopEmailValidationTests(unittest.TestCase):
    def test_accepts_gmail(self):
        profile = ShopUpdate(**shop_data("dono@gmail.com"))
        self.assertEqual(str(profile.email_notificacoes), "dono@gmail.com")

    def test_accepts_googlemail(self):
        profile = ShopUpdate(**shop_data("dono@googlemail.com"))
        self.assertEqual(str(profile.email_notificacoes), "dono@googlemail.com")

    def test_accepts_empty_email(self):
        self.assertIsNone(ShopUpdate(**shop_data(None)).email_notificacoes)

    def test_rejects_non_google_provider(self):
        with self.assertRaises(ValidationError) as captured:
            ShopUpdate(**shop_data("dono@outlook.com"))
        self.assertIn("Use um e-mail oficial do Gmail", str(captured.exception))


if __name__ == "__main__":
    unittest.main()

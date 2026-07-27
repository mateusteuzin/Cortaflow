import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app import main
from app.schemas import CheckoutSessionRequest, Register, VerificationSession


def registration():
    return Register(
        nome="Mateus",
        email="dono@gmail.com",
        senha="segredo12345",
        telefone="88999999999",
        barbearia_nome="Barbearia Teste",
        plano="profissional",
    )


class PaidSignupTests(unittest.TestCase):
    @patch("app.main.send_account_verification", return_value=True)
    @patch("app.main.hash_password", return_value="password-hash")
    @patch("app.main.one")
    def test_registration_only_creates_pending_record(self, mocked_one, _hash, _send):
        mocked_one.side_effect = [None, None, {"id": 91}]
        result = main.register(registration())
        sql = mocked_one.call_args_list[2].args[0]
        self.assertIn("INSERT INTO cadastros_pendentes", sql)
        self.assertNotIn("INSERT INTO usuarios", sql)
        self.assertTrue(result["requires_email_verification"])

    @patch("app.main._create_pending_checkout")
    @patch("app.main.one")
    def test_verified_pending_signup_goes_directly_to_checkout(self, mocked_one, checkout):
        mocked_one.return_value = {
            "id": 91,
            "email": "dono@gmail.com",
            "nome": "Mateus",
            "plano": "profissional",
        }
        checkout.return_value = Mock(url="https://checkout.stripe.com/test")
        request = Mock()
        result = main.confirm_verification_session(
            VerificationSession(code="codigo-seguro-1234567890"),
            request,
        )
        self.assertEqual(result["checkout_url"], "https://checkout.stripe.com/test")
        checkout.assert_called_once()

    @patch("app.main.send_account_verification", return_value=True)
    @patch("app.main.hash_password")
    @patch("app.main.one")
    def test_retry_does_not_overwrite_pending_identity_or_password(self, mocked_one, mocked_hash, _send):
        mocked_one.side_effect = [
            None,
            {"id": 91, "email": "dono@gmail.com", "nome": "Mateus", "plano": "profissional"},
            {"id": 91},
        ]
        result = main.register(registration())
        update_sql = mocked_one.call_args_list[2].args[0]
        self.assertNotIn("senha_hash", update_sql)
        self.assertNotIn("barbearia_nome", update_sql)
        mocked_hash.assert_not_called()
        self.assertTrue(result["existing_pending_account"])

    def test_paid_signup_accepts_only_stripe_checkout_session_ids(self):
        self.assertEqual(
            CheckoutSessionRequest(session_id="cs_test_checkout123").session_id,
            "cs_test_checkout123",
        )
        with self.assertRaises(ValidationError):
            CheckoutSessionRequest(session_id="sessao-inventada")


if __name__ == "__main__":
    unittest.main()

import hashlib
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main
from app.schemas import ForgotPassword, ResetPassword


class PasswordResetTests(unittest.TestCase):
    @patch("app.main.send_password_reset", return_value=True)
    @patch("app.main.one")
    def test_request_stores_only_token_hash(self, mocked_one, mocked_send):
        mocked_one.side_effect = [
            {"id": 7, "email": "dono@gmail.com", "nome": "Mateus", "email_verificado": True},
            {"id": 7},
        ]
        result = main.forgot_password(ForgotPassword(email="dono@gmail.com"))
        update_params = mocked_one.call_args_list[1].args[1]
        stored_hash = update_params[0]
        raw_token = mocked_send.call_args.args[2]
        self.assertEqual(stored_hash, hashlib.sha256(raw_token.encode()).hexdigest())
        self.assertNotEqual(stored_hash, raw_token)
        self.assertIn("Se esse Gmail", result["message"])

    @patch("app.main.send_password_reset")
    @patch("app.main.one", return_value=None)
    def test_unknown_email_returns_same_generic_response(self, _one, mocked_send):
        result = main.forgot_password(ForgotPassword(email="ninguem@gmail.com"))
        mocked_send.assert_not_called()
        self.assertIn("Se esse Gmail", result["message"])

    @patch("app.main.hash_password", return_value="new-hash")
    @patch("app.main.one", return_value={"id": 7, "email": "dono@gmail.com"})
    def test_valid_token_updates_password_and_invalidates_token(self, mocked_one, _hash):
        result = main.reset_password(ResetPassword(
            token="token-seguro-1234567890",
            senha="nova-senha",
        ))
        sql, params = mocked_one.call_args.args
        self.assertIn("password_reset_token_hash=NULL", sql)
        self.assertEqual(params[0], "new-hash")
        self.assertEqual(result["message"], "Senha atualizada com sucesso. Você já pode entrar.")

    @patch("app.main.one", return_value=None)
    def test_expired_token_is_rejected(self, _one):
        with self.assertRaises(HTTPException) as caught:
            main.reset_password(ResetPassword(
                token="token-expirado-123456789",
                senha="nova-senha",
            ))
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

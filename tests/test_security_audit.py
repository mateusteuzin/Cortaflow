import asyncio
import inspect
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
import jwt
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from app import main, security
from app.schemas import Appointment, CheckoutRequest


ROOT = Path(__file__).resolve().parents[1]


def request_for(path: str, method: str = "POST", ip: str = "203.0.113.20") -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (ip, 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    })


class SecurityAuditTests(unittest.TestCase):
    def setUp(self):
        main.hits.clear()
        main.auth_hits.clear()

    def test_private_access_without_authentication_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            security._authenticated_user(None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_barber_cannot_escalate_to_owner(self):
        with self.assertRaises(HTTPException) as caught:
            security.owner_user({"perfil": "barbeiro", "barbearia_id": 7})
        self.assertEqual(caught.exception.status_code, 403)

    @patch("app.main.one")
    def test_cross_shop_product_update_is_scoped_to_session_shop(self, database_one):
        database_one.return_value = None
        payload = Mock(nome="Pomada", preco=30, custo_unitario=10, quantidade_estoque=2)
        main.update_product(999, payload, {"barbearia_id": 7})
        params = database_one.call_args.args[1]
        self.assertEqual(params[-2:], (999, 7))

    def test_frontend_cannot_submit_price_or_payment_status(self):
        with self.assertRaises(ValidationError):
            CheckoutRequest.model_validate({
                "plan": "essencial",
                "price": 1,
                "payment_status": "paid",
            })

    def test_frontend_cannot_submit_tenant_or_role(self):
        with self.assertRaises(ValidationError):
            Appointment.model_validate({
                "barbeiro_id": 2,
                "cliente_nome": "Cliente",
                "cliente_telefone": "11999999999",
                "data_hora": "2026-08-01T10:00:00",
                "barbershop_id": 999,
                "role": "administrador",
            })

    @patch("app.main._stripe_client")
    def test_invalid_stripe_webhook_signature_is_rejected(self, stripe_client):
        stripe = stripe_client.return_value
        stripe.error.SignatureVerificationError = ValueError
        stripe.Webhook.construct_event.side_effect = ValueError("invalid signature")
        request = Mock()
        request.body = AsyncMock(return_value=b"{}")
        request.headers = {"stripe-signature": "invalid"}
        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test_placeholder_value"}):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.stripe_webhook(request))
        self.assertEqual(caught.exception.status_code, 400)

    def test_expired_access_token_is_rejected(self):
        now = datetime.now(timezone.utc)
        encoded = jwt.encode({
            "sub": "42",
            "ver": 1,
            "type": "access",
            "iss": security.JWT_ISSUER,
            "aud": security.JWT_AUDIENCE,
            "iat": now - timedelta(hours=2),
            "nbf": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }, security.SECRET, algorithm=security.JWT_ALGORITHM)
        with self.assertRaises(Exception):
            security._decode_access_token(encoded)

    def test_excess_login_attempts_are_rate_limited(self):
        async def call_next(_request):
            return Response(status_code=200)

        responses = [
            asyncio.run(main.security_and_rate_limit(
                request_for("/api/auth/login"), call_next
            ))
            for _ in range(11)
        ]
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn("Retry-After", responses[-1].headers)

    def test_public_booking_creation_is_rate_limited(self):
        async def call_next(_request):
            return Response(status_code=200)

        responses = [
            asyncio.run(main.security_and_rate_limit(
                request_for("/api/public/barbearias/blackbarber/agendamentos"), call_next
            ))
            for _ in range(13)
        ]
        self.assertEqual(responses[-1].status_code, 429)

    @patch("app.main._stripe_client")
    @patch("app.main.one")
    def test_checkout_redirect_cannot_activate_subscription(self, database_one, stripe_client):
        database_one.return_value = {
            "plano_ativo": False,
            "subscription_plan": "premium",
            "subscription_status": "incomplete",
        }
        with self.assertRaises(HTTPException) as caught:
            main.confirm_checkout(
                Mock(session_id="cs_test_12345678"),
                {"id": 3, "barbearia_id": 7, "perfil": "administrador"},
            )
        self.assertEqual(caught.exception.status_code, 409)
        stripe_client.assert_not_called()
        sql = database_one.call_args.args[0]
        self.assertNotIn("UPDATE", sql.upper())

    def test_stripe_subscription_value_must_match_server_catalog(self):
        subscription = {
            "items": {"data": [{"price": {
                "currency": "brl",
                "unit_amount": 2990,
                "recurring": {"interval": "month"},
            }}]},
        }
        self.assertEqual(
            main._verified_subscription_plan(subscription, "essencial"),
            "essencial",
        )
        with self.assertRaises(HTTPException):
            main._verified_subscription_plan(subscription, "premium")

    def test_stripe_subscription_rejects_browser_manipulated_amount(self):
        subscription = {
            "items": {"data": [{"price": {
                "currency": "brl",
                "unit_amount": 1,
                "recurring": {"interval": "month"},
            }}]},
        }
        with self.assertRaises(HTTPException):
            main._verified_subscription_plan(subscription, "premium")

    @patch("app.main.one")
    def test_logout_invalidates_all_existing_tokens(self, database_one):
        database_one.return_value = {"id": 42}
        self.assertEqual(main.logout({"id": 42}), {"ok": True})
        self.assertIn("auth_version=auth_version+1", database_one.call_args.args[0])

    @patch("app.main.one")
    def test_paid_signup_bootstrap_token_is_one_time_and_short_lived(self, database_one):
        database_one.return_value = {"id": 42, "nome": "Gestor", "auth_version": 1}
        result = main.finish_paid_signup(Mock(session_id="cs_test_12345678"))
        self.assertIn("access_token", result)
        sql = database_one.call_args.args[0]
        self.assertIn("checkout_login_consumed_at IS NULL", sql)
        self.assertIn("INTERVAL '30 minutes'", sql)

    def test_public_loyalty_route_does_not_accept_barbershop_id(self):
        parameters = inspect.signature(main.loyalty).parameters
        self.assertEqual(set(parameters), {"slug", "telefone"})

    def test_cors_never_accepts_wildcard_with_credentials(self):
        with patch.dict("os.environ", {"ALLOWED_ORIGINS": "*,https://cortaflow.com.br"}):
            self.assertEqual(main._cors_origins(), ["https://cortaflow.com.br"])

    def test_security_headers_include_clickjacking_and_hsts_on_https(self):
        async def call_next(_request):
            return Response(status_code=200)

        request = request_for("/api/health", method="GET")
        request.scope["scheme"] = "https"
        response = asyncio.run(main.security_and_rate_limit(request, call_next))
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

    def test_env_files_are_ignored_and_outside_static_root(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", gitignore)
        self.assertFalse((ROOT / "app" / "static" / ".env").exists())
        self.assertFalse((ROOT / "app" / "static" / ".env.local").exists())


if __name__ == "__main__":
    unittest.main()

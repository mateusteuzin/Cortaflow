import asyncio
import time
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
import jwt
from starlette.requests import Request
from starlette.responses import Response

from app import main, security


def request_for(path: str, ip: str = "203.0.113.10") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (ip, 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    })


class BackendSecurityTests(unittest.TestCase):
    def test_access_token_has_expected_security_claims(self):
        encoded = security.token(42, auth_version=3)
        claims = jwt.decode(
            encoded,
            security.SECRET,
            algorithms=[security.JWT_ALGORITHM],
            audience=security.JWT_AUDIENCE,
            issuer=security.JWT_ISSUER,
        )
        self.assertEqual(claims["sub"], "42")
        self.assertEqual(claims["type"], "access")
        self.assertEqual(claims["ver"], 3)
        self.assertTrue(claims["jti"])

    def test_invalid_password_hash_fails_closed(self):
        self.assertFalse(security.verify_password("senha-valida", "hash-invalido"))

    def test_auth_rate_limit_is_specific_and_returns_retry_after(self):
        main.auth_hits.clear()

        async def call_next(_request):
            return Response(status_code=200)

        responses = [
            asyncio.run(main.security_and_rate_limit(
                request_for("/api/auth/register"), call_next
            ))
            for _ in range(6)
        ]
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn("Retry-After", responses[-1].headers)

    @patch.dict("os.environ", {
        "STRIPE_SECRET_KEY": "sk_live_123456789012345678901234",
        "STRIPE_WEBHOOK_SECRET": "whsec_12345678901234567890",
        "STRIPE_PRICE_ESSENCIAL": "price_1234567890",
        "STRIPE_PRICE_PROFISSIONAL": "price_abcdefghij",
        "STRIPE_PRICE_PREMIUM": "price_0987654321",
        "RESEND_API_KEY": "re_123456789",
        "EMAIL_FROM": "CortaFlow <contato@example.com>",
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
        "WHATSAPP_ACCESS_TOKEN": "meta-access-token",
        "WHATSAPP_PHONE_NUMBER_ID": "123456789",
        "WHATSAPP_BUSINESS_ACCOUNT_ID": "987654321",
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "webhook-verify-token",
        "WHATSAPP_APP_SECRET": "meta-app-secret",
    }, clear=False)
    def test_public_configuration_status_contains_only_booleans(self):
        result = main.configuration_status()

        def assert_boolean_tree(value):
            if isinstance(value, dict):
                for child in value.values():
                    assert_boolean_tree(child)
            else:
                self.assertIsInstance(value, bool)

        assert_boolean_tree(result)
        self.assertTrue(result["whatsapp"]["configured"])
        serialized = str(result)
        self.assertNotIn("sk_live_", serialized)
        self.assertNotIn("google-secret-value", serialized)

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    def test_google_oidc_start_uses_code_state_nonce_and_minimal_scopes(self):
        response = main.start_google_oidc()
        params = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["scope"], ["openid email profile"])
        self.assertTrue(params["state"][0])
        self.assertTrue(params["nonce"][0])
        self.assertIn("HttpOnly", response.headers["set-cookie"])

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    def test_google_oidc_parallel_attempts_use_distinct_cookies(self):
        first = main.start_google_oidc()
        second = main.start_google_oidc()
        first_cookie = first.headers["set-cookie"].split("=", 1)[0]
        second_cookie = second.headers["set-cookie"].split("=", 1)[0]
        self.assertNotEqual(first_cookie, second_cookie)
        self.assertTrue(first_cookie.startswith(main.GOOGLE_STATE_COOKIE))
        self.assertTrue(second_cookie.startswith(main.GOOGLE_STATE_COOKIE))

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    def test_google_oidc_expired_state_redirects_to_friendly_error(self):
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/api/auth/google/callback",
            "raw_path": b"/api/auth/google/callback",
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.10", 1234),
            "server": ("testserver", 80),
            "scheme": "https",
        })
        response = main.google_oidc_callback(
            request=request,
            code="authorization-code",
            state="expired-state",
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/?google=sessao_expirada")

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    def test_google_register_state_carries_signed_plan(self):
        response = main.start_google_oidc(mode="register", plan="premium")
        params = parse_qs(urlparse(response.headers["location"]).query)
        claims = security.decode_oidc_state(params["state"][0])
        self.assertEqual(claims["mode"], "register")
        self.assertEqual(claims["plan"], "premium")

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    def test_google_register_requires_a_valid_plan(self):
        with self.assertRaises(HTTPException) as caught:
            main.start_google_oidc(mode="register", plan="")
        self.assertEqual(caught.exception.status_code, 422)

    @patch.dict("os.environ", {
        "PUBLIC_BASE_URL": "https://cortaflow.com.br",
        "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "google-secret-value",
        "GOOGLE_REDIRECT_URI": "https://cortaflow.com.br/api/auth/google/callback",
    }, clear=False)
    @patch("app.main._create_pending_checkout")
    @patch("app.main.one")
    @patch("app.main._google_json_request")
    @patch("app.main.decode_oidc_state")
    def test_google_register_stays_pending_until_stripe_payment(
        self, decode_state, google_request, database_one, create_checkout
    ):
        state = "signed-state-value-with-enough-characters"
        decode_state.return_value = {
            "nonce": "expected-nonce",
            "mode": "register",
            "plan": "profissional",
        }
        google_request.side_effect = [
            {"id_token": "google-id-token"},
            {
                "iss": "https://accounts.google.com",
                "aud": "client.apps.googleusercontent.com",
                "nonce": "expected-nonce",
                "email_verified": "true",
                "exp": int(time.time()) + 600,
                "email": "gestor@example.com",
                "sub": "google-subject-123",
                "name": "Gestor CortaFlow",
            },
        ]
        pending = {
            "id": 321,
            "email": "gestor@example.com",
            "plano": "profissional",
        }
        database_one.side_effect = [None, None, pending]
        create_checkout.return_value = Mock(url="https://checkout.stripe.com/session")
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/api/auth/google/callback",
            "raw_path": b"/api/auth/google/callback",
            "query_string": b"",
            "headers": [(b"cookie", f"{main.GOOGLE_STATE_COOKIE}={state}".encode())],
            "client": ("203.0.113.10", 1234),
            "server": ("testserver", 80),
            "scheme": "https",
        })

        response = main.google_oidc_callback(
            request=request,
            code="authorization-code",
            state=state,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "https://checkout.stripe.com/session")
        create_checkout.assert_called_once_with(pending, request)
        queries = " ".join(str(call.args[0]) for call in database_one.call_args_list)
        self.assertIn("INSERT INTO cadastros_pendentes", queries)
        self.assertNotIn("INSERT INTO usuarios", queries)

    def test_pending_activation_rejects_mismatched_checkout(self):
        pending = {
            "id": 91,
            "email_verificado": True,
            "stripe_checkout_session_id": "cs_test_expected",
            "plano": "profissional",
        }
        session = {
            "id": "cs_test_other",
            "client_reference_id": "pending:91",
            "mode": "subscription",
            "payment_status": "paid",
            "metadata": {"pending_signup_id": "91", "plan": "profissional"},
        }
        self.assertFalse(main._checkout_matches_pending(
            pending, session, {"status": "active"}
        ))

    @patch("app.main._process_stripe_event")
    @patch("app.main._claim_stripe_event", return_value=False)
    @patch("app.main._stripe_client")
    def test_duplicate_webhook_is_acknowledged_without_reprocessing(
        self, stripe_client, _claim, process
    ):
        stripe = stripe_client.return_value
        stripe.Webhook.construct_event.return_value = {
            "id": "evt_duplicate123",
            "type": "customer.subscription.updated",
            "data": {"object": {}},
        }
        request = Mock()
        request.body = AsyncMock(return_value=b"payload")
        request.headers = {"stripe-signature": "valid"}
        with patch.dict("os.environ", {
            "STRIPE_WEBHOOK_SECRET": "whsec_12345678901234567890",
            "STRIPE_SECRET_KEY": "sk_test_123456789012345678901234",
        }):
            result = asyncio.run(main.stripe_webhook(request))
        self.assertTrue(result["duplicate"])
        process.assert_not_called()

    def test_stripe_line_item_uses_server_side_plan_price(self):
        item = main._stripe_line_item("essencial")
        self.assertEqual(item["price_data"]["currency"], "brl")
        self.assertEqual(item["price_data"]["unit_amount"], 2990)
        self.assertEqual(item["price_data"]["recurring"], {"interval": "month"})
        self.assertEqual(item["price_data"]["product_data"]["metadata"], {"plan": "essencial"})

    @patch.dict("os.environ", {"STRIPE_PRICE_30": "price_legacy12345"}, clear=True)
    def test_stripe_configuration_accepts_existing_legacy_price_names(self):
        self.assertTrue(main._stripe_price_configured(main.STRIPE_PLANS["essencial"]))

    @patch("app.main.one")
    def test_subscription_details_exposes_plan_and_renewal(self, database_one):
        database_one.return_value = {
            "subscription_plan": "profissional",
            "subscription_status": "active",
            "plano_ativo": True,
            "subscription_current_period_end": "2026-08-21T12:00:00+00:00",
            "subscription_cancel_at_period_end": False,
            "stripe_customer_id": "cus_test",
            "stripe_subscription_id": "sub_test",
            "data_assinatura": "2026-07-21",
        }
        result = main.subscription_details({"barbearia_id": 11})
        self.assertEqual(result["plan"], "profissional")
        self.assertEqual(result["plan_name"], "CortaFlow Profissional")
        self.assertEqual(result["current_period_end"], "2026-08-21T12:00:00+00:00")
        self.assertEqual(result["started_at"], "2026-07-21")
        self.assertTrue(result["billing_data_complete"])

    @patch("app.main.one")
    def test_legacy_subscription_is_reported_as_incomplete(self, database_one):
        database_one.return_value = {
            "subscription_plan": None,
            "subscription_status": "active",
            "plano_ativo": True,
            "subscription_current_period_end": None,
            "subscription_cancel_at_period_end": False,
            "stripe_customer_id": "cus_legacy",
            "stripe_subscription_id": None,
            "data_assinatura": "2026-07-21",
        }
        result = main.subscription_details({"barbearia_id": 11})
        self.assertTrue(result["active"])
        self.assertIsNone(result["plan"])
        self.assertFalse(result["billing_data_complete"])


if __name__ == "__main__":
    unittest.main()

import json
import hashlib
import hmac
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("barber.whatsapp")


def verify_webhook_signature(body: bytes, signature: str, app_secret: str) -> bool:
    if not signature or not app_secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def normalize_phone(value: str, default_country_code: str = "55") -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) in (10, 11):
        digits = default_country_code + digits
    if not 10 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("Número de WhatsApp inválido")
    return digits


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) <= 7:
        return "***"
    return f"{digits[:4]}{'*' * max(3, len(digits) - 7)}{digits[-3:]}"


@dataclass(frozen=True)
class AppointmentMessage:
    appointment_id: int
    client_name: str
    client_phone: str
    service_name: str
    starts_at: datetime
    professional_name: str = ""
    location: str = ""
    price: Decimal | float | int | None = None

    @property
    def code(self) -> str:
        return f"AG-{self.appointment_id:06d}"


@dataclass(frozen=True)
class SendResult:
    message_id: str
    http_status: int


class WhatsAppError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.http_status = http_status
        self.retryable = retryable


class WhatsAppService(Protocol):
    def send_appointment_confirmation(self, message: AppointmentMessage) -> SendResult: ...


class MetaWhatsAppService:
    def __init__(self, *, api_url: str | None = None, access_token: str | None = None,
                 phone_number_id: str | None = None, template_name: str | None = None,
                 template_language: str | None = None, timeout: float = 12.0,
                 opener=urlopen):
        self.api_url = (api_url or os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v23.0")).rstrip("/")
        self.access_token = access_token if access_token is not None else os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = phone_number_id if phone_number_id is not None else os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.template_name = template_name or os.getenv("WHATSAPP_TEMPLATE_NAME", "confirmacao_agendamento")
        self.template_language = template_language or os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR")
        self.timeout = timeout
        self.opener = opener

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def build_payload(self, message: AppointmentMessage) -> tuple[str, dict]:
        phone = normalize_phone(message.client_phone)
        values = [
            message.client_name.strip() or "Cliente",
            message.service_name.strip() or "Serviço",
            message.starts_at.strftime("%d/%m/%Y"),
            message.starts_at.strftime("%H:%M"),
            message.professional_name.strip() or "A definir",
            message.code,
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": self.template_name,
                "language": {"code": self.template_language},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in values],
                }],
            },
        }
        return phone, payload

    def send_appointment_confirmation(self, message: AppointmentMessage) -> SendResult:
        if not self.configured:
            raise WhatsAppError("Integração do WhatsApp não configurada", retryable=False)
        phone, payload = self.build_payload(message)
        request = Request(
            f"{self.api_url}/{self.phone_number_id}/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                message_id = ((body.get("messages") or [{}])[0]).get("id")
                if not message_id:
                    raise WhatsAppError("Meta não retornou o ID da mensagem", http_status=response.status)
                logger.info("WhatsApp enviado appointment_id=%s phone=%s template=%s http=%s message_id=%s",
                            message.appointment_id, mask_phone(phone), self.template_name, response.status, message_id)
                return SendResult(message_id=message_id, http_status=response.status)
        except HTTPError as error:
            retryable = error.code == 429 or error.code >= 500
            logger.warning("Falha WhatsApp appointment_id=%s phone=%s template=%s http=%s retryable=%s",
                           message.appointment_id, mask_phone(phone), self.template_name, error.code, retryable)
            raise WhatsAppError(self._safe_http_message(error.code), http_status=error.code, retryable=retryable) from error
        except (TimeoutError, URLError) as error:
            logger.warning("Falha de conexão WhatsApp appointment_id=%s phone=%s template=%s",
                           message.appointment_id, mask_phone(phone), self.template_name)
            raise WhatsAppError("Falha temporária de conexão com a Meta", retryable=True) from error

    @staticmethod
    def _safe_http_message(status: int) -> str:
        return {
            400: "Payload, telefone ou template rejeitado pela Meta",
            401: "Token da Meta inválido ou expirado",
            403: "Aplicativo sem permissão para enviar mensagens",
            404: "Número remetente ou recurso da Meta não encontrado",
            429: "Limite de requisições da Meta excedido",
        }.get(status, "API do WhatsApp temporariamente indisponível" if status >= 500 else "Falha ao enviar mensagem pela Meta")

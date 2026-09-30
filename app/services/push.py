import json
import logging
import os
from datetime import datetime
from requests import Session

from ..database import all_rows, one
from .push_endpoints import validate_push_endpoint

logger = logging.getLogger(__name__)


class _PushSession(Session):
    def request(self, method, url, **kwargs):
        validate_push_endpoint(url)
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def push_is_configured() -> bool:
    return bool(
        os.getenv("VAPID_PUBLIC_KEY", "").strip()
        and os.getenv("VAPID_PRIVATE_KEY", "").strip()
        and os.getenv("VAPID_CLAIMS_EMAIL", "").strip()
    )


def push_public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "").strip() if push_is_configured() else ""


def _appointment_payload(appointment_id: int, event: str) -> tuple[dict, dict] | tuple[None, None]:
    item = one(
        """SELECT a.id,a.barbearia_id,a.barbeiro_id,a.cliente_nome,a.data_hora,
        a.servico,a.status,b.nome barbeiro_nome
        FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
        WHERE a.id=%s""",
        (appointment_id,),
    )
    if not item:
        return None, None
    when = item["data_hora"]
    when_label = when.strftime("%d/%m às %H:%M") if isinstance(when, datetime) else str(when)
    titles = {
        "novo": "Novo agendamento",
        "reagendado": "Agendamento reagendado",
        "confirmado": "Agendamento confirmado",
        "cancelado": "Agendamento cancelado",
        "nao_compareceu": "Cliente não compareceu",
    }
    payload = {
        "title": titles.get(event, "Agenda atualizada"),
        "body": f"{item['cliente_nome']} · {item['servico']} · {when_label}",
        "url": "/painel#agenda",
        "tag": f"appointment-{appointment_id}-{event}",
        "appointment_id": appointment_id,
    }
    return item, payload


def send_appointment_push(appointment_id: int, event: str = "novo") -> int:
    if not push_is_configured():
        return 0
    item, payload = _appointment_payload(appointment_id, event)
    if not item:
        return 0
    subscriptions = all_rows(
        """SELECT id,endpoint,p256dh,auth FROM push_subscriptions
        WHERE barbearia_id=%s AND ativo
          AND (barbeiro_id IS NULL OR barbeiro_id=%s)""",
        (item["barbearia_id"], item["barbeiro_id"]),
    )
    if not subscriptions:
        logger.info(
            "Web Push sem destinatários ativos para barbearia=%s barbeiro=%s",
            item["barbearia_id"], item["barbeiro_id"],
        )
        return 0
    return _send_payload(subscriptions, payload)


def send_user_test_push(user_id: int, shop_id: int) -> int:
    if not push_is_configured():
        return 0
    subscriptions = all_rows(
        """SELECT id,endpoint,p256dh,auth FROM push_subscriptions
        WHERE usuario_id=%s AND barbearia_id=%s AND ativo""",
        (user_id, shop_id),
    )
    if not subscriptions:
        logger.info("Teste Web Push sem inscrição ativa para usuario=%s", user_id)
        return 0
    return _send_payload(subscriptions, {
        "title": "Notificações ativadas",
        "body": "Tudo certo! Este celular receberá os avisos da agenda.",
        "url": "/painel#agenda",
        "tag": f"push-test-{user_id}",
    })


def _send_payload(subscriptions: list[dict], payload: dict) -> int:
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("pywebpush não está instalado; notificações push não serão enviadas")
        return 0

    sent = 0
    claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "").strip()
    subject = claims_email if claims_email.startswith("mailto:") else f"mailto:{claims_email}"
    for subscription in subscriptions:
        try:
            validate_push_endpoint(subscription["endpoint"])
            with _PushSession() as session:
                webpush(
                    subscription_info={
                        "endpoint": subscription["endpoint"],
                        "keys": {
                            "p256dh": subscription["p256dh"],
                            "auth": subscription["auth"],
                        },
                    },
                    data=json.dumps(payload, ensure_ascii=False),
                    vapid_private_key=os.getenv("VAPID_PRIVATE_KEY", "").strip(),
                    vapid_claims={"sub": subject},
                    ttl=300,
                    timeout=10,
                    requests_session=session,
                )
            sent += 1
            one(
                """UPDATE push_subscriptions SET ultimo_envio_em=NOW(),atualizado_em=NOW()
                WHERE id=%s RETURNING id""",
                (subscription["id"],),
            )
        except ValueError:
            logger.warning("Endpoint Web Push recusado para inscricao %s", subscription["id"])
        except WebPushException as error:
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None) or getattr(response, "status", None)
            if status in (404, 410):
                one(
                    """UPDATE push_subscriptions SET ativo=FALSE,atualizado_em=NOW()
                    WHERE id=%s RETURNING id""",
                    (subscription["id"],),
                )
            logger.warning("Falha ao enviar Web Push para inscricao %s: HTTP %s", subscription["id"], status)
        except Exception:
            logger.exception("Erro inesperado ao enviar Web Push para inscrição %s", subscription["id"])
    logger.info("Web Push enviado para %s de %s inscrição(ões)", sent, len(subscriptions))
    return sent

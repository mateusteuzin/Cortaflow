import json
import logging
import os
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..database import one
from .whatsapp import normalize_phone

logger = logging.getLogger(__name__)
BRAND_ICON_URL = "https://cortaflow.com.br/assets/cortaflow-icon-default.png"


def send_account_verification(email: str, owner_name: str, verification_token: str) -> bool:
    """Envia a confirmação de propriedade do e-mail do dono da barbearia."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    base_url = os.getenv("PUBLIC_BASE_URL", "https://cortaflow.com.br").strip().rstrip("/")
    if not api_key:
        logger.warning("RESEND_API_KEY não configurada; confirmação de conta não enviada")
        return False
    verification_url = f"{base_url}/api/auth/verificar-email?token={quote(verification_token)}"
    html = f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      {_brand_header('CONFIRMAÇÃO DE CONTA', 'CortaFlow')}
      <div style="padding:30px"><p>Olá, <strong>{escape(owner_name)}</strong>.</p>
      <p>Confirme seu e-mail para liberar o painel da sua barbearia.</p>
      <a href="{escape(verification_url, quote=True)}" style="display:inline-block;background:#171713;color:#fff;text-decoration:none;font-weight:bold;padding:15px 22px;margin:18px 0">Confirmar meu e-mail</a>
      <p style="font-size:13px;color:#6d6b64">Este link é válido por 24 horas. Se você não criou esta conta, ignore esta mensagem.</p>
      </div></div></body></html>"""
    payload = json.dumps({"from": sender, "to": [email], "subject": "Confirme sua conta CortaFlow", "html": html}).encode()
    request = Request("https://api.resend.com/emails", data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "CortaFlow/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logger.warning("Falha ao enviar confirmação da conta para %s: %s", email, error)
        return False


def send_subscription_confirmation(
    email: str,
    owner_name: str,
    plan_name: str,
    amount_cents: int,
    period_end: datetime | None,
) -> bool:
    """Envia o resumo da assinatura depois que a Stripe confirma o pagamento."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    if not api_key:
        logger.warning("RESEND_API_KEY não configurada; confirmação da assinatura não enviada")
        return False
    amount = f"{amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    renewal = period_end.strftime("%d/%m/%Y") if period_end else "consulte no painel"
    panel_url = os.getenv("PUBLIC_BASE_URL", "https://cortaflow.com.br").strip().rstrip("/") + "/painel"
    html = f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      {_brand_header('ASSINATURA CONFIRMADA', 'CortaFlow')}
      <div style="padding:30px"><p>Olá, <strong>{escape(owner_name)}</strong>.</p>
      <p>Seu pagamento foi confirmado e o acesso ao CortaFlow já está liberado.</p>
      <div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;margin:24px 0;line-height:1.9">
        <strong>{escape(plan_name)}</strong><br>
        Valor mensal: R$ {amount}<br>
        Próxima renovação: {renewal}<br>
        Status: assinatura ativa
      </div>
      <a href="{escape(panel_url, quote=True)}" style="display:inline-block;background:#171713;color:#fff;text-decoration:none;font-weight:bold;padding:15px 22px">Acessar meu painel</a>
      <p style="font-size:12px;color:#777;margin-top:24px">O pagamento é processado pela Stripe. Você pode consultar ou cancelar a assinatura em Minha assinatura.</p>
      </div></div></body></html>"""
    payload = json.dumps({
        "from": sender,
        "to": [email],
        "subject": f"Assinatura confirmada — {plan_name}",
        "html": html,
    }).encode()
    request = Request("https://api.resend.com/emails", data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "CortaFlow/1.0",
    })
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logger.warning("Falha ao enviar confirmação da assinatura para %s: %s", email, error)
        return False


def _brand_header(label: str, title: str, logo_url: str | None = None) -> str:
    candidate = (logo_url or "").strip()
    parsed = urlparse(candidate)
    has_public_logo = parsed.scheme == "https" and bool(parsed.netloc)
    image_url = escape(candidate if has_public_logo else BRAND_ICON_URL, quote=True)
    image_alt = escape(f"Logo da {title}" if has_public_logo else "CortaFlow", quote=True)
    return f"""<div style="background:#151511;color:#fff;padding:24px 28px">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>
        <td style="vertical-align:middle;padding-right:16px">
          <div style="width:58px;height:58px;border-radius:50%;background:#f3e2b4;border:2px solid #d5a93f;text-align:center">
            <img src="{image_url}" width="58" height="58" alt="{image_alt}" style="display:block;box-sizing:border-box;width:58px;height:58px;padding:3px;border-radius:50%;object-fit:contain;background:#fff">
          </div>
        </td>
        <td style="vertical-align:middle"><small style="color:#d5a93f;letter-spacing:2px">{escape(label)}</small>
          <h1 style="margin:7px 0 0;font-size:26px;line-height:1.1">{escape(title)}</h1>
          <span style="display:block;margin-top:6px;color:#aaa;font-size:12px">Agendamento por CortaFlow</span>
        </td>
      </tr></table>
    </div>"""


def _format_date(value: datetime) -> tuple[str, str]:
    weekdays = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
    months = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    return f"{weekdays[value.weekday()]}, {value.day} de {months[value.month - 1]}", value.strftime("%H:%M")


def _email_html(item: dict) -> str:
    day, hour = _format_date(item["data_hora"])
    shop = item["barbearia_nome"]
    return f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      {_brand_header('RESERVA CONFIRMADA', shop, item.get('barbearia_logo_url'))}
      <div style="padding:30px"><p>Olá, <strong>{escape(item['cliente_nome'])}</strong>.</p><p>Seu horário foi reservado com sucesso.</p>
      <div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;margin:24px 0;line-height:1.8">
        <strong>{escape(item['servico'])}</strong><br>{escape(day)} às {hour}<br>Profissional: {escape(item['barbeiro_nome'])}<br>Valor: R$ {item['preco']:.2f}<br>Reserva: #{item['id']:04d}
      </div><p style="font-size:13px;color:#6d6b64">Caso precise alterar o horário, entre em contato diretamente com a barbearia.</p></div>
    </div></body></html>"""


def _owner_whatsapp_url(item: dict) -> str | None:
    try:
        phone = normalize_phone(item.get("cliente_telefone") or "")
    except ValueError:
        return None
    message = (
        f"Olá, {item.get('cliente_nome') or 'cliente'}! "
        f"Aqui é da {item.get('barbearia_nome') or 'barbearia'}. "
        f"Recebemos seu agendamento de {item.get('servico') or 'serviço'}."
    )
    return f"https://wa.me/{phone}?text={quote(message)}"


def _owner_email_html(item: dict) -> str:
    day, hour = _format_date(item["data_hora"])
    whatsapp_url = _owner_whatsapp_url(item)
    whatsapp_button = ""
    if whatsapp_url:
        whatsapp_button = (
            f'<a href="{escape(whatsapp_url, quote=True)}" '
            'style="display:inline-block;background:#1f9d55;color:#fff;text-decoration:none;'
            'font-weight:bold;padding:14px 20px;margin:22px 0 4px">Abrir conversa no WhatsApp</a>'
        )
    client_email = escape(item.get("cliente_email") or "Não informado")
    return f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:620px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      {_brand_header('NOVO AGENDAMENTO', item['barbearia_nome'], item.get('barbearia_logo_url'))}
      <div style="padding:30px"><p>Uma nova reserva foi registrada pelo site.</p>
      <div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;line-height:1.9">
        <strong style="font-size:18px">{escape(item['cliente_nome'])}</strong><br>
        WhatsApp: {escape(item['cliente_telefone'] or 'Não informado')}<br>
        E-mail: <a href="mailto:{client_email}" style="color:#9a6b13">{client_email}</a><br>
        Serviço: {escape(item['servico'])}<br>
        Profissional: {escape(item['barbeiro_nome'])}<br>
        Data: {escape(day)} às {hour}<br>
        Valor: R$ {item['preco']:.2f}<br>
        Reserva: #{item['id']:04d}
      </div>{whatsapp_button}
      <p style="font-size:12px;color:#777">Você recebeu este aviso porque as notificações de novos agendamentos estão ativadas no CortaFlow.</p>
      </div></div></body></html>"""


def send_appointment_confirmation(appointment_id: int) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    if not api_key:
        one("UPDATE agendamentos SET email_erro=%s WHERE id=%s RETURNING id", ("Resend não configurado", appointment_id))
        return False
    item = one("""SELECT a.id,a.cliente_nome,a.cliente_email,a.data_hora,a.servico,a.preco,
        b.nome barbeiro_nome,s.nome barbearia_nome,s.logo_url barbearia_logo_url FROM agendamentos a
        JOIN barbeiros b ON b.id=a.barbeiro_id JOIN barbearias s ON s.id=a.barbearia_id
        WHERE a.id=%s AND a.cliente_email IS NOT NULL AND NOT a.email_enviado
          AND a.status NOT IN ('concluido','realizado')""", (appointment_id,))
    if not item:
        return False
    payload = json.dumps({"from": sender, "to": [item["cliente_email"]],
        "subject": f"Reserva confirmada na {item['barbearia_nome']}", "html": _email_html(item)}).encode()
    request = Request("https://api.resend.com/emails", data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        "Idempotency-Key": f"agendamento-confirmacao-{appointment_id}",
        "User-Agent": "CortaFlow/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
        one("""UPDATE agendamentos SET email_enviado=true,email_enviado_em=NOW(),
            email_message_id=%s,email_erro=NULL WHERE id=%s RETURNING id""", (result.get("id"), appointment_id))
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        detail = str(error)
        if isinstance(error, HTTPError):
            try:
                detail = json.loads(error.read()).get("message", detail)
            except (ValueError, AttributeError):
                pass
        one("UPDATE agendamentos SET email_erro=%s WHERE id=%s RETURNING id", (detail[:500], appointment_id))
        logger.warning("Falha ao enviar confirmação do agendamento %s", appointment_id)
        return False


def send_owner_notification(appointment_id: int) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    item = one("""SELECT a.id,a.cliente_nome,a.cliente_telefone,a.cliente_email,a.data_hora,
        a.servico,a.preco,b.nome barbeiro_nome,s.nome barbearia_nome,
        s.logo_url barbearia_logo_url,s.email_notificacoes
        FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
        JOIN barbearias s ON s.id=a.barbearia_id WHERE a.id=%s
        AND s.notificar_novos_agendamentos AND s.email_notificacoes IS NOT NULL
        AND NOT a.email_dono_enviado
        AND a.status NOT IN ('concluido','realizado')""", (appointment_id,))
    if not api_key or not item:
        return False
    html = _owner_email_html(item)
    payload = json.dumps({"from": sender, "to": [item["email_notificacoes"]],
        "subject": f"Novo agendamento #{item['id']:04d} - {item['barbearia_nome']}", "html": html}).encode()
    request = Request("https://api.resend.com/emails", data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        "Idempotency-Key": f"agendamento-dono-{appointment_id}",
        "User-Agent": "CortaFlow/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read())
        one("""UPDATE agendamentos SET email_dono_enviado=true,email_dono_message_id=%s,
            email_dono_erro=NULL WHERE id=%s RETURNING id""", (result.get("id"), appointment_id))
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        detail = str(error)
        if isinstance(error, HTTPError):
            try:
                detail = error.read().decode("utf-8", errors="replace") or detail
            except OSError:
                pass
        one("UPDATE agendamentos SET email_dono_erro=%s WHERE id=%s RETURNING id", (detail[:500], appointment_id))
        logger.warning("Falha ao notificar dono sobre o agendamento %s", appointment_id)
        return False

import json
import logging
import os
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..database import one

logger = logging.getLogger(__name__)


def _format_date(value: datetime) -> tuple[str, str]:
    weekdays = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
    months = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    return f"{weekdays[value.weekday()]}, {value.day} de {months[value.month - 1]}", value.strftime("%H:%M")


def _email_html(item: dict) -> str:
    day, hour = _format_date(item["data_hora"])
    shop = escape(item["barbearia_nome"])
    return f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      <div style="background:#151511;color:#fff;padding:28px"><small style="color:#d5a93f;letter-spacing:2px">RESERVA CONFIRMADA</small><h1 style="margin:10px 0 0;font-size:26px">{shop}</h1></div>
      <div style="padding:30px"><p>Olá, <strong>{escape(item['cliente_nome'])}</strong>.</p><p>Seu horário foi reservado com sucesso.</p>
      <div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;margin:24px 0;line-height:1.8">
        <strong>{escape(item['servico'])}</strong><br>{escape(day)} às {hour}<br>Profissional: {escape(item['barbeiro_nome'])}<br>Valor: R$ {item['preco']:.2f}<br>Reserva: #{item['id']:04d}
      </div><p style="font-size:13px;color:#6d6b64">Caso precise alterar o horário, entre em contato diretamente com a barbearia.</p></div>
    </div></body></html>"""


def send_appointment_confirmation(appointment_id: int) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    if not api_key:
        one("UPDATE agendamentos SET email_erro=%s WHERE id=%s RETURNING id", ("Resend não configurado", appointment_id))
        return False
    item = one("""SELECT a.id,a.cliente_nome,a.cliente_email,a.data_hora,a.servico,a.preco,
        b.nome barbeiro_nome,s.nome barbearia_nome FROM agendamentos a
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
        a.servico,a.preco,b.nome barbeiro_nome,s.nome barbearia_nome,s.email_notificacoes
        FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
        JOIN barbearias s ON s.id=a.barbearia_id WHERE a.id=%s
        AND s.notificar_novos_agendamentos AND s.email_notificacoes IS NOT NULL
        AND NOT a.email_dono_enviado
        AND a.status NOT IN ('concluido','realizado')""", (appointment_id,))
    if not api_key or not item:
        return False
    day, hour = _format_date(item["data_hora"])
    html = f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:600px;margin:32px auto;background:#fff;border:1px solid #ded9ce">
      <div style="background:#151511;color:#fff;padding:28px"><small style="color:#d5a93f;letter-spacing:2px">NOVO AGENDAMENTO</small><h1 style="margin:10px 0 0;font-size:26px">{escape(item['barbearia_nome'])}</h1></div>
      <div style="padding:30px"><p>Uma nova reserva foi registrada.</p><div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;line-height:1.8">
        Cliente: <strong>{escape(item['cliente_nome'])}</strong><br>WhatsApp: {escape(item['cliente_telefone'])}<br>E-mail: {escape(item['cliente_email'] or 'Não informado')}<br>
        Serviço: {escape(item['servico'])}<br>Profissional: {escape(item['barbeiro_nome'])}<br>Data: {escape(day)} às {hour}<br>Valor: R$ {item['preco']:.2f}<br>Reserva: #{item['id']:04d}
      </div></div></div></body></html>"""
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

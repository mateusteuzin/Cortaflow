import json
import hashlib
import logging
import os
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from ..database import one
from .whatsapp import normalize_phone

logger = logging.getLogger(__name__)
BRAND_ICON_URL = "https://cortaflow.com.br/assets/cortaflow-logo-on-dark.png"
RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_SENDER = "onboarding@resend.dev"
DEFAULT_BASE_URL = "https://cortaflow.com.br"
TRANSACTIONAL_HEADERS = {
    "Auto-Submitted": "auto-generated",
    "X-Auto-Response-Suppress": "All",
}


def _public_url(path: str) -> str:
    base_url = os.getenv("PUBLIC_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    return f"{base_url}{path}"


def _transactional_html(
    *,
    preheader: str,
    eyebrow: str,
    title: str,
    owner_name: str,
    intro: str,
    action_label: str,
    action_url: str,
    callout_title: str,
    callout_text: str,
    expiry_text: str | None,
    closing_text: str,
    footer_text: str,
    details_html: str = "",
) -> str:
    safe_url = escape(action_url, quote=True)
    safe_name = escape(owner_name.strip() or "cliente CortaFlow")
    expiry_html = ""
    if expiry_text:
        expiry_html = (
            '<p style="margin:0 0 8px;color:#5f625b;font-size:13px;line-height:1.65">'
            f"{escape(expiry_text)}</p>"
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{escape(title)}</title>
  <style>
    body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
    table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    table {{ border-collapse: collapse !important; }}
    img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
    @media only screen and (max-width: 640px) {{
      .email-wrap {{ padding: 12px 8px !important; }}
      .email-card {{ width: 100% !important; }}
      .email-header {{ padding: 28px 22px 24px !important; }}
      .email-content {{ padding: 28px 22px 12px !important; }}
      .email-footer {{ padding: 20px 22px 28px !important; }}
      .email-title {{ font-size: 27px !important; }}
      .email-button {{ display: block !important; min-width: 0 !important; padding: 16px 18px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;width:100%;background:#f4f5f0;color:#0d0d11;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
    {escape(preheader)}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f4f5f0;">
    <tr>
      <td class="email-wrap" align="center" style="padding:32px 12px;">
        <table role="presentation" class="email-card" width="620" cellpadding="0" cellspacing="0" style="width:100%;max-width:620px;background:#ffffff;border:1px solid #dfe1db;border-radius:18px;overflow:hidden;">
          <tr>
            <td class="email-header" style="background:#0d0d11;padding:32px 36px 28px;border-bottom:3px solid #f1ff0a;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <img src="{BRAND_ICON_URL}" width="168" height="34" alt="CortaFlow" style="display:block;width:168px;height:auto;">
                  </td>
                  <td align="right" style="vertical-align:middle;color:#f1ff0a;font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase;">
                    OPERACAO ATIVA
                  </td>
                </tr>
              </table>
              <p style="margin:26px 0 8px;color:#f1ff0a;font-size:11px;line-height:1.4;font-weight:800;letter-spacing:1px;text-transform:uppercase;">{escape(eyebrow)}</p>
              <h1 class="email-title" style="margin:0;color:#ffffff;font-size:31px;line-height:1.18;font-weight:700;">{escape(title)}</h1>
            </td>
          </tr>
          <tr>
            <td class="email-content" style="padding:34px 36px 12px;">
              <p style="margin:0 0 14px;color:#171915;font-size:16px;line-height:1.65;">Olá, <strong>{safe_name}</strong>.</p>
              <p style="margin:0;color:#555950;font-size:15px;line-height:1.75;">{escape(intro)}</p>
              {details_html}
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0 24px;">
                <tr>
                  <td align="center" style="border-radius:8px;background:#f1ff0a;">
                    <a class="email-button" href="{safe_url}" target="_blank" style="display:inline-block;min-width:230px;padding:16px 24px;color:#0d0d11;text-decoration:none;font-size:15px;line-height:1.2;font-weight:800;text-align:center;">{escape(action_label)} →</a>
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;background:#f4f7df;border:1px solid #d7e760;border-radius:8px;">
                <tr>
                  <td style="padding:16px 18px;color:#363a16;font-size:13px;line-height:1.65;">
                    <strong>{escape(callout_title)}</strong><br>{escape(callout_text)}
                  </td>
                </tr>
              </table>
              {expiry_html}
              <p style="margin:0 0 8px;color:#777a72;font-size:12px;line-height:1.6;">Se o botão não abrir, copie e cole este endereço no navegador:</p>
              <p style="margin:0;word-break:break-all;font-size:12px;line-height:1.6;"><a href="{safe_url}" style="color:#8b6418;text-decoration:underline;">{safe_url}</a></p>
            </td>
          </tr>
          <tr>
            <td class="email-footer" style="padding:22px 36px 32px;color:#777a72;font-size:12px;line-height:1.65;">
              <p style="margin:0 0 10px;">{escape(closing_text)}</p>
              <p style="margin:0;">{escape(footer_text)}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_transactional_email(
    *,
    email: str,
    subject: str,
    html: str,
    text: str,
    log_label: str,
    idempotency_key: str | None = None,
) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", DEFAULT_SENDER).strip()
    if not api_key:
        logger.warning("RESEND_API_KEY não configurada; %s não enviado", log_label)
        return False
    payload = json.dumps({
        "from": sender,
        "to": [email],
        "subject": subject.replace("\r", " ").replace("\n", " ").strip(),
        "html": html,
        "text": text,
        "headers": {
            **TRANSACTIONAL_HEADERS,
            "X-Entity-Ref-ID": f"cortaflow-{uuid4().hex}",
        },
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "CortaFlow/1.0",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]
    request = Request(RESEND_ENDPOINT, data=payload, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logger.warning("Falha ao enviar %s para %s: %s", log_label, email, error)
        return False


def send_account_verification(email: str, owner_name: str, verification_token: str) -> bool:
    """Envia a confirmação de propriedade do e-mail do dono da barbearia."""
    verification_url = _public_url(
        f"/api/auth/verificar-email?token={quote(verification_token, safe='')}"
    )
    html = _transactional_html(
        preheader="Confirme seu e-mail para continuar com a contratação do CortaFlow.",
        eyebrow="Confirmação de conta",
        title="Confirme seu e-mail",
        owner_name=owner_name,
        intro=(
            "Recebemos seu cadastro. Confirme que este endereço pertence a você "
            "para continuar com a contratação do seu plano."
        ),
        action_label="Confirmar meu e-mail",
        action_url=verification_url,
        callout_title="Próximo passo",
        callout_text=(
            "Após a confirmação, você seguirá para o checkout seguro da Stripe. "
            "Sua conta só será ativada depois da confirmação do pagamento."
        ),
        expiry_text="Por segurança, este link expira em 24 horas e só pode ser usado uma vez.",
        closing_text="Se você não iniciou este cadastro, ignore esta mensagem.",
        footer_text="Mensagem automática sobre o seu cadastro na CortaFlow.",
    )
    text = (
        "CORTAFLOW\n\n"
        "Confirme seu e-mail\n\n"
        f"Olá, {owner_name.strip() or 'cliente CortaFlow'}.\n\n"
        "Recebemos seu cadastro. Confirme que este endereço pertence a você para "
        "continuar com a contratação do seu plano.\n\n"
        f"Confirmar meu e-mail: {verification_url}\n\n"
        "Após a confirmação, você seguirá para o checkout seguro da Stripe. Sua "
        "conta só será ativada depois da confirmação do pagamento.\n\n"
        "Por segurança, este link expira em 24 horas e só pode ser usado uma vez.\n\n"
        "Se você não iniciou este cadastro, ignore esta mensagem."
    )
    return _send_transactional_email(
        email=email,
        subject="Confirme seu e-mail | CortaFlow",
        html=html,
        text=text,
        log_label="confirmação de conta",
    )


def send_password_reset(email: str, owner_name: str, reset_token: str) -> bool:
    """Envia um link de uso único para redefinir a senha."""
    reset_url = _public_url(
        f"/api/auth/redefinir-senha?token={quote(reset_token, safe='')}"
    )
    html = _transactional_html(
        preheader="Use o link seguro para definir uma nova senha na CortaFlow.",
        eyebrow="Segurança da conta",
        title="Defina uma nova senha",
        owner_name=owner_name,
        intro=(
            "Recebemos uma solicitação para redefinir a senha da sua conta. "
            "Use o botão abaixo para escolher uma nova senha."
        ),
        action_label="Definir nova senha",
        action_url=reset_url,
        callout_title="Link protegido",
        callout_text=(
            "Este link é pessoal, de uso único e não deve ser compartilhado com ninguém."
        ),
        expiry_text="O link expira em 24 horas. Depois disso, solicite uma nova redefinição.",
        closing_text=(
            "Não solicitou essa alteração? Ignore esta mensagem. Sua senha atual "
            "continuará funcionando normalmente."
        ),
        footer_text="Mensagem automática de segurança da sua conta CortaFlow.",
    )
    text = (
        "CORTAFLOW\n\n"
        "Defina uma nova senha\n\n"
        f"Olá, {owner_name.strip() or 'cliente CortaFlow'}.\n\n"
        "Recebemos uma solicitação para redefinir a senha da sua conta.\n\n"
        f"Definir nova senha: {reset_url}\n\n"
        "Este link é pessoal, de uso único e expira em 24 horas. Não compartilhe "
        "este endereço com ninguém.\n\n"
        "Não solicitou essa alteração? Ignore esta mensagem. Sua senha atual "
        "continuará funcionando normalmente."
    )
    return _send_transactional_email(
        email=email,
        subject="Redefinição de senha | CortaFlow",
        html=html,
        text=text,
        log_label="recuperação de senha",
    )


def send_barber_invitation(
    email: str,
    barber_name: str,
    reset_token: str,
    shop_name: str,
    barber_id: int,
) -> bool:
    access_url = _public_url(
        f"/api/auth/redefinir-senha?token={quote(reset_token, safe='')}"
    )
    html = _transactional_html(
        preheader=f"Você recebeu acesso à equipe da {shop_name} no CortaFlow.",
        eyebrow="Convite para a equipe",
        title="Crie sua senha de acesso",
        owner_name=barber_name,
        intro=(
            f"A administração da {shop_name} vinculou você à equipe. "
            "Crie sua senha para atualizar seus próprios dados de contato."
        ),
        action_label="Criar minha senha",
        action_url=access_url,
        callout_title="Acesso individual",
        callout_text=(
            "Sua conta permite acessar somente seu resumo, sua agenda, seus insights e seus dados profissionais. "
            "Financeiro geral e configurações administrativas continuam protegidos."
        ),
        expiry_text="Por segurança, este convite expira em 30 minutos.",
        closing_text="Se você não reconhece este convite, ignore esta mensagem.",
        footer_text="Mensagem automática de acesso à equipe CortaFlow.",
    )
    text = (
        "CORTAFLOW\n\n"
        "Crie sua senha de acesso\n\n"
        f"Olá, {barber_name}.\n\n"
        f"A administração da {shop_name} vinculou você à equipe.\n\n"
        f"Criar minha senha: {access_url}\n\n"
        "O convite expira em 30 minutos e libera somente seu resumo, sua agenda, seus insights e seu perfil."
    )
    return _send_transactional_email(
        email=email,
        subject=f"Convite para a equipe | {shop_name}",
        html=html,
        text=text,
        log_label="convite de profissional",
        idempotency_key=(
            f"barber-invite/{barber_id}/"
            f"{hashlib.sha256(reset_token.encode('utf-8')).hexdigest()[:16]}"
        ),
    )


def send_subscription_confirmation(
    email: str,
    owner_name: str,
    plan_name: str,
    amount_cents: int,
    period_end: datetime | None,
) -> bool:
    """Envia o resumo da assinatura depois que a Stripe confirma o pagamento."""
    amount = f"{amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    renewal = period_end.strftime("%d/%m/%Y") if period_end else "consulte no painel"
    panel_url = _public_url("/painel")
    details_html = f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0 0;background:#f7f7f4;border:1px solid #e1e2dc;">
                <tr>
                  <td style="padding:18px 20px;color:#555950;font-size:14px;line-height:1.8;">
                    <strong style="display:block;color:#171915;font-size:17px;">{escape(plan_name)}</strong>
                    <span>Valor mensal: <strong>R$ {amount}</strong></span><br>
                    <span>Próxima renovação: <strong>{renewal}</strong></span><br>
                    <span>Status: <strong style="color:#317a4b;">Ativa</strong></span>
                  </td>
                </tr>
              </table>"""
    html = _transactional_html(
        preheader=f"Pagamento confirmado. Sua assinatura {plan_name} está ativa.",
        eyebrow="Pagamento confirmado",
        title="Sua assinatura está ativa",
        owner_name=owner_name,
        intro=(
            "Seu pagamento foi confirmado com sucesso e o acesso ao CortaFlow "
            "já está liberado."
        ),
        action_label="Acessar meu painel",
        action_url=panel_url,
        callout_title="Cobrança protegida pela Stripe",
        callout_text=(
            "Os dados do seu cartão são processados com segurança pela Stripe e "
            "não ficam armazenados na CortaFlow."
        ),
        expiry_text=None,
        closing_text=(
            "Você pode consultar os detalhes ou gerenciar sua assinatura na área "
            "Minha assinatura do painel."
        ),
        footer_text="Mensagem automática sobre a sua assinatura CortaFlow.",
        details_html=details_html,
    )
    text = (
        "CORTAFLOW\n\n"
        "Sua assinatura está ativa\n\n"
        f"Olá, {owner_name.strip() or 'cliente CortaFlow'}.\n\n"
        "Seu pagamento foi confirmado com sucesso e o acesso ao CortaFlow já está liberado.\n\n"
        f"Plano: {plan_name}\n"
        f"Valor mensal: R$ {amount}\n"
        f"Próxima renovação: {renewal}\n"
        "Status: Ativa\n\n"
        f"Acessar meu painel: {panel_url}\n\n"
        "Os dados do seu cartão são processados com segurança pela Stripe e não "
        "ficam armazenados na CortaFlow."
    )
    return _send_transactional_email(
        email=email,
        subject=f"Pagamento confirmado | {plan_name}",
        html=html,
        text=text,
        log_label="confirmação da assinatura",
    )


def _brand_header(label: str, title: str, logo_url: str | None = None) -> str:
    candidate = (logo_url or "").strip()
    parsed = urlparse(candidate)
    has_remote_logo = parsed.scheme == "https" and bool(parsed.netloc)
    has_local_logo = candidate.startswith("/assets/")
    image_url = candidate if has_remote_logo else _public_url(candidate) if has_local_logo else BRAND_ICON_URL
    image_alt = f"Logo da {title}" if has_remote_logo or has_local_logo else "CortaFlow"
    return f"""
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#151713;">
        <tr>
          <td class="booking-header" style="padding:28px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="76" style="width:76px;vertical-align:middle;">
                  <table role="presentation" cellpadding="0" cellspacing="0">
                    <tr>
                      <td align="center" valign="middle" style="width:62px;height:62px;border:2px solid #d5a93f;border-radius:50%;background:#ffffff;">
                        <img src="{escape(image_url, quote=True)}" width="54" height="54" alt="{escape(image_alt, quote=True)}" style="display:block;width:54px;max-width:54px;height:54px;margin:2px auto;border-radius:50%;object-fit:contain;">
                      </td>
                    </tr>
                  </table>
                </td>
                <td style="vertical-align:middle;">
                  <p style="margin:0 0 7px;color:#d8ae54;font-size:10px;line-height:1.3;font-weight:700;text-transform:uppercase;">{escape(label)}</p>
                  <h1 class="booking-shop-name" style="margin:0;color:#ffffff;font-size:25px;line-height:1.15;font-weight:700;">{escape(title)}</h1>
                  <p style="margin:7px 0 0;color:#aeb2aa;font-size:12px;line-height:1.4;">Agendamento realizado pelo CortaFlow</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>"""


def _format_date(value: datetime) -> tuple[str, str]:
    weekdays = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
    months = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    return f"{weekdays[value.weekday()]}, {value.day} de {months[value.month - 1]}", value.strftime("%H:%M")


def _email_html(item: dict) -> str:
    day, hour = _format_date(item["data_hora"])
    shop = str(item["barbearia_nome"])
    amount = f"{float(item['preco']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>Reserva confirmada na {escape(shop)}</title>
  <style>
    body,table,td,a {{ -webkit-text-size-adjust:100%;-ms-text-size-adjust:100%; }}
    table,td {{ mso-table-lspace:0pt;mso-table-rspace:0pt; }}
    table {{ border-collapse:collapse!important; }}
    img {{ -ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none; }}
    @media only screen and (max-width:620px) {{
      .booking-wrap {{ padding:0!important; }}
      .booking-card {{ width:100%!important;border-left:0!important;border-right:0!important; }}
      .booking-header {{ padding:24px 20px!important; }}
      .booking-content {{ padding:28px 20px 12px!important; }}
      .booking-footer {{ padding:20px 20px 28px!important; }}
      .booking-shop-name {{ font-size:22px!important; }}
      .detail-label {{ width:105px!important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;width:100%;background:#f2f0ea;color:#171915;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
    Sua reserva na {escape(shop)} está confirmada para {escape(day)}, às {hour}.
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f2f0ea;">
    <tr>
      <td class="booking-wrap" align="center" style="padding:32px 12px;">
        <table role="presentation" class="booking-card" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid #ddd9cf;">
          <tr><td>{_brand_header('Reserva confirmada', shop, item.get('barbearia_logo_url'))}</td></tr>
          <tr>
            <td class="booking-content" style="padding:34px 32px 12px;">
              <p style="margin:0 0 12px;color:#171915;font-size:16px;line-height:1.6;">Olá, <strong>{escape(str(item['cliente_nome']))}</strong>.</p>
              <p style="margin:0;color:#565a52;font-size:15px;line-height:1.7;">Seu horário foi reservado com sucesso. Confira os detalhes:</p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;background:#faf8f3;border:1px solid #e5dfd1;border-left:4px solid #d5a93f;">
                <tr>
                  <td style="padding:20px 18px;">
                    <p style="margin:0 0 16px;color:#171915;font-size:18px;line-height:1.35;font-weight:700;">{escape(str(item['servico']))}</p>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr><td class="detail-label" width="120" style="padding:5px 12px 5px 0;color:#777a72;font-size:13px;">Data</td><td style="padding:5px 0;color:#242720;font-size:13px;font-weight:700;">{escape(day)}</td></tr>
                      <tr><td class="detail-label" width="120" style="padding:5px 12px 5px 0;color:#777a72;font-size:13px;">Horário</td><td style="padding:5px 0;color:#242720;font-size:13px;font-weight:700;">{hour}</td></tr>
                      <tr><td class="detail-label" width="120" style="padding:5px 12px 5px 0;color:#777a72;font-size:13px;">Profissional</td><td style="padding:5px 0;color:#242720;font-size:13px;font-weight:700;">{escape(str(item['barbeiro_nome']))}</td></tr>
                      <tr><td class="detail-label" width="120" style="padding:5px 12px 5px 0;color:#777a72;font-size:13px;">Valor</td><td style="padding:5px 0;color:#242720;font-size:13px;font-weight:700;">R$ {amount}</td></tr>
                      <tr><td class="detail-label" width="120" style="padding:5px 12px 5px 0;color:#777a72;font-size:13px;">Reserva</td><td style="padding:5px 0;color:#8b6418;font-size:13px;font-weight:700;">#{int(item['id']):04d}</td></tr>
                    </table>
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f4;border:1px solid #e3e4de;">
                <tr><td style="padding:15px 17px;color:#60645c;font-size:13px;line-height:1.6;">Precisa alterar o horário? Entre em contato diretamente com a barbearia antes do atendimento.</td></tr>
              </table>
            </td>
          </tr>
          <tr>
            <td class="booking-footer" style="padding:22px 32px 32px;color:#858980;font-size:11px;line-height:1.6;">
              <p style="margin:0 0 6px;">Mensagem automática enviada pela {escape(shop)}.</p>
              <p style="margin:0;">Agendamentos e gestão por <strong style="color:#725316;">CortaFlow</strong>.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


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
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"></head><body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
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


def _barber_notification_html(item: dict, event: str) -> str:
    day, hour = _format_date(item["data_hora"])
    labels = {
        "novo": ("NOVO AGENDAMENTO", "Novo horário na sua agenda"),
        "reagendado": ("AGENDAMENTO ALTERADO", "Um horário foi reagendado"),
        "cancelado": ("AGENDAMENTO CANCELADO", "Um horário foi cancelado"),
    }
    eyebrow, title = labels[event]
    panel_url = _public_url(f"/painel?view=agenda&appointment={item['id']}")
    client_email = escape(item.get("cliente_email") or "Não informado")
    observations = escape(item.get("observacoes") or "Nenhuma observação")
    amount = f"{float(item['preco']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;background:#f3f0e9;font-family:Arial,sans-serif;color:#171713">
    <div style="max-width:640px;margin:28px auto;background:#fff;border:1px solid #ded9ce">
      {_brand_header(eyebrow, item['barbearia_nome'], item.get('barbearia_logo_url'))}
      <div style="padding:30px">
        <p style="font-size:18px;margin:0 0 8px"><strong>{escape(title)}</strong></p>
        <p style="color:#62645e;margin:0 0 22px">Olá, {escape(item['barbeiro_nome'])}. Confira os dados:</p>
        <div style="border-left:4px solid #d5a93f;background:#faf8f3;padding:18px;line-height:1.9">
          <strong style="font-size:18px">{escape(item['cliente_nome'])}</strong><br>
          Telefone: {escape(item.get('cliente_telefone') or 'Não informado')}<br>
          E-mail: <a href="mailto:{client_email}" style="color:#9a6b13">{client_email}</a><br>
          Serviço: {escape(item['servico'])}<br>
          Profissional: {escape(item['barbeiro_nome'])}<br>
          Data: {escape(day)} às {hour}<br>
          Valor: R$ {amount}<br>
          Observações: {observations}<br>
          Reserva: #{int(item['id']):04d}
        </div>
        <p style="margin:24px 0;text-align:center">
          <a href="{escape(panel_url, quote=True)}" style="display:inline-block;background:#171915;color:#fff;text-decoration:none;font-weight:bold;padding:14px 22px">Abrir no painel</a>
        </p>
        <p style="font-size:12px;color:#777">Este aviso foi enviado somente ao profissional responsável. Quando ele não possui e-mail cadastrado, o endereço administrativo é usado como contingência.</p>
      </div>
    </div></body></html>"""


def send_barber_appointment_notification(
    appointment_id: int,
    event: str = "novo",
    event_key: str | None = None,
) -> bool:
    if event not in {"novo", "reagendado", "cancelado"}:
        raise ValueError("Evento de notificação inválido")
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", DEFAULT_SENDER).strip()
    item = one("""SELECT a.id,a.barbearia_id,a.barbeiro_id,a.cliente_nome,
        a.cliente_telefone,a.cliente_email,a.data_hora,a.servico,a.preco,
        a.observacoes,a.atualizado_em,b.nome barbeiro_nome,
        b.notification_email,s.nome barbearia_nome,s.logo_url barbearia_logo_url,
        s.email_notificacoes,s.notificar_novos_agendamentos
        FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
        JOIN barbearias s ON s.id=a.barbearia_id WHERE a.id=%s""", (appointment_id,))
    if not item or not item["notificar_novos_agendamentos"]:
        return False
    recipient = str(item.get("notification_email") or "").strip().lower()
    recipient_source = "barbeiro"
    if not recipient:
        recipient = str(item.get("email_notificacoes") or "").strip().lower()
        recipient_source = "administrativo"
        logger.warning(
            "Profissional %s sem e-mail de notificação; usando contingência administrativa",
            item["barbeiro_id"],
        )
    if not recipient:
        logger.warning(
            "Agendamento %s sem destinatário de notificação configurado",
            appointment_id,
        )
        return False
    if not api_key:
        logger.warning("RESEND_API_KEY não configurada; aviso do agendamento %s não enviado", appointment_id)
        return False
    key = event_key or str(item.get("atualizado_em") or item["id"])
    claimed = one("""INSERT INTO notificacoes_email(
        agendamento_id,barbearia_id,barbeiro_id,evento,event_key,destinatario,
        origem_destinatario,status)
        VALUES(%s,%s,%s,%s,%s,%s,%s,'processando')
        ON CONFLICT(agendamento_id,evento,event_key,destinatario) DO UPDATE
          SET status='processando',erro=NULL,atualizado_em=NOW()
          WHERE notificacoes_email.status='erro'
        RETURNING id""", (
            appointment_id,item["barbearia_id"],item["barbeiro_id"],event,
            key[:80],recipient,recipient_source,
        ))
    if not claimed:
        return False
    notification_id = claimed["id"]
    subjects = {
        "novo": f"Novo agendamento #{appointment_id:04d} - {item['barbearia_nome']}",
        "reagendado": f"Agendamento reagendado #{appointment_id:04d} - {item['barbearia_nome']}",
        "cancelado": f"Agendamento cancelado #{appointment_id:04d} - {item['barbearia_nome']}",
    }
    payload = json.dumps({
        "from": sender,
        "to": [recipient],
        "subject": subjects[event],
        "html": _barber_notification_html(item, event),
        "headers": TRANSACTIONAL_HEADERS,
    }).encode("utf-8")
    request = Request(RESEND_ENDPOINT, data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"appointment/{event}/{notification_id}",
        "User-Agent": "CortaFlow/1.0",
    })
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
        one("""UPDATE notificacoes_email SET status='enviado',resend_message_id=%s,
            enviado_em=NOW(),erro=NULL,atualizado_em=NOW() WHERE id=%s RETURNING id""",
            (result.get("id"),notification_id))
        return True
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        detail = str(error)
        if isinstance(error, HTTPError):
            try:
                detail = error.read().decode("utf-8", errors="replace") or detail
            except OSError:
                pass
        one("""UPDATE notificacoes_email SET status='erro',erro=%s,
            atualizado_em=NOW() WHERE id=%s RETURNING id""",
            (detail[:500],notification_id))
        logger.warning(
            "Falha ao enviar evento %s do agendamento %s", event, appointment_id
        )
        return False


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
    """Compatibilidade: agora direciona o aviso ao profissional responsável."""
    return send_barber_appointment_notification(
        appointment_id,
        event="novo",
        event_key=f"novo-{appointment_id}",
    )


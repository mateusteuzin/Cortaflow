import logging
import threading
from datetime import timedelta
from decimal import Decimal

from ..database import db, one
from .whatsapp import AppointmentMessage, MetaWhatsAppService, WhatsAppError, normalize_phone

logger = logging.getLogger("barber.whatsapp.worker")
RETRY_DELAYS_SECONDS = (0, 60, 300, 900)


class WhatsAppWorker:
    def __init__(self, service=None, poll_seconds: int = 10):
        self.service = service or MetaWhatsAppService()
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="whatsapp-worker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=3)

    def notify(self):
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                while not self._stop.is_set() and self.process_next():
                    pass
            except Exception:
                logger.exception("Erro inesperado no worker do WhatsApp")
            self._wake.wait(self.poll_seconds)
            self._wake.clear()

    def process_next(self) -> bool:
        row = self._claim_next()
        if not row:
            return False
        appointment_id = row["id"]
        try:
            phone = normalize_phone(row["cliente_telefone"])
            message = AppointmentMessage(
                appointment_id=appointment_id,
                client_name=row["cliente_nome"],
                client_phone=phone,
                service_name=row["servico"],
                starts_at=row["data_hora"],
                professional_name=row.get("barbeiro_nome") or "",
                location=row.get("endereco") or "",
                price=Decimal(row["preco"]) if row.get("preco") is not None else None,
            )
            result = self.service.send_appointment_confirmation(message)
            one("""UPDATE agendamentos SET whatsapp_enviado=true,whatsapp_enviado_em=NOW(),
                whatsapp_message_id=%s,whatsapp_status='ENVIADO',whatsapp_erro=NULL,
                whatsapp_proxima_tentativa=NULL,whatsapp_telefone=%s
                WHERE id=%s AND status NOT IN ('concluido','realizado') RETURNING id""",
                (result.message_id, phone, appointment_id))
        except (ValueError, WhatsAppError) as error:
            retryable = isinstance(error, WhatsAppError) and error.retryable
            self._record_failure(appointment_id, row["whatsapp_tentativas"], str(error), retryable)
        except Exception:
            logger.exception("Falha inesperada no envio appointment_id=%s", appointment_id)
            self._record_failure(appointment_id, row["whatsapp_tentativas"], "Falha interna no envio", True)
        return True

    @staticmethod
    def _claim_next():
        with db() as cur:
            cur.execute("""SELECT a.id FROM agendamentos a
                WHERE a.whatsapp_autorizado AND NOT a.whatsapp_enviado
                  AND a.whatsapp_status='PENDENTE'
                  AND a.status NOT IN ('concluido','realizado')
                  AND COALESCE(a.whatsapp_proxima_tentativa,NOW())<=NOW()
                ORDER BY a.whatsapp_proxima_tentativa NULLS FIRST,a.id
                FOR UPDATE SKIP LOCKED LIMIT 1""")
            candidate = cur.fetchone()
            if not candidate:
                return None
            cur.execute("""UPDATE agendamentos SET whatsapp_status='ENVIANDO',
                whatsapp_tentativas=whatsapp_tentativas+1 WHERE id=%s RETURNING whatsapp_tentativas""",
                (candidate["id"],))
            attempts = cur.fetchone()["whatsapp_tentativas"]
            cur.execute("""SELECT a.id,a.cliente_nome,a.cliente_telefone,a.data_hora,a.servico,a.preco,
                b.nome barbeiro_nome,s.endereco,%s::int whatsapp_tentativas
                FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
                JOIN barbearias s ON s.id=a.barbearia_id WHERE a.id=%s""", (attempts,candidate["id"]))
            return cur.fetchone()

    @staticmethod
    def _record_failure(appointment_id: int, attempts: int, error: str, retryable: bool):
        can_retry = retryable and attempts < len(RETRY_DELAYS_SECONDS)
        delay = RETRY_DELAYS_SECONDS[attempts] if can_retry else None
        safe_error = (error or "Falha no envio")[:300]
        if can_retry:
            one("""UPDATE agendamentos SET whatsapp_status='PENDENTE',whatsapp_erro=%s,
                whatsapp_proxima_tentativa=NOW()+(%s * INTERVAL '1 second') WHERE id=%s RETURNING id""",
                (safe_error,delay,appointment_id))
        else:
            one("""UPDATE agendamentos SET whatsapp_status='FALHOU',whatsapp_erro=%s,
                whatsapp_proxima_tentativa=NULL WHERE id=%s RETURNING id""", (safe_error,appointment_id))


whatsapp_worker = WhatsAppWorker()

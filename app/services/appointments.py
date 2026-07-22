from ..database import db


class AppointmentNotFoundError(Exception):
    pass


class InvalidAppointmentStatusError(Exception):
    pass


ACTIVE_STATUSES = ("agendado", "confirmado", "em_andamento")
COMPLETED_STATUSES = ("concluido", "realizado")


def complete_appointment(appointment_id: int, shop_id: int) -> dict:
    """Conclui e anonimiza um agendamento da barbearia em uma transação."""
    with db() as cur:
        cur.execute(
            "SELECT * FROM agendamentos WHERE id=%s AND barbearia_id=%s FOR UPDATE",
            (appointment_id, shop_id),
        )
        appointment = cur.fetchone()
        if not appointment:
            raise AppointmentNotFoundError

        current_status = appointment["status"]
        if current_status == "cancelado":
            raise InvalidAppointmentStatusError

        already_completed = current_status in COMPLETED_STATUSES
        phone = appointment.get("cliente_telefone")

        # A fidelidade é a única ação interna que ainda depende do telefone.
        # Em tentativas idempotentes ela não é executada novamente.
        if not already_completed and phone:
            cur.execute(
                """INSERT INTO fidelidade_cliente(
                    barbearia_id,cliente_telefone,cliente_nome,total_cortes
                ) VALUES(%s,%s,%s,1)
                ON CONFLICT(barbearia_id,cliente_telefone) DO UPDATE SET
                    total_cortes=fidelidade_cliente.total_cortes+1,
                    cliente_nome=EXCLUDED.cliente_nome
                RETURNING id""",
                (shop_id, phone, appointment["cliente_nome"]),
            )
            cur.fetchone()

        cur.execute(
            """SELECT EXISTS(
                SELECT 1 FROM agendamentos
                WHERE barbearia_id=%s AND id<>%s AND cliente_telefone=%s
                  AND status=ANY(%s)
            ) AS has_active""",
            (shop_id, appointment_id, phone, list(ACTIVE_STATUSES)),
        )
        has_active = bool(phone and cur.fetchone()["has_active"])

        cur.execute(
            """UPDATE agendamentos SET
                status='concluido',
                cliente_email=NULL,
                cliente_telefone=NULL,
                whatsapp_telefone=NULL,
                whatsapp_autorizado=FALSE,
                whatsapp_status=CASE
                    WHEN whatsapp_status IN ('ENVIADO','ENTREGUE','LIDO') THEN whatsapp_status
                    ELSE 'ENCERRADO'
                END,
                whatsapp_proxima_tentativa=NULL,
                concluido_em=COALESCE(concluido_em,NOW()),
                atualizado_em=NOW()
            WHERE id=%s AND barbearia_id=%s
            RETURNING *""",
            (appointment_id, shop_id),
        )
        completed = cur.fetchone()

        # fidelidade_cliente é um cadastro compartilhado: preserve o contato
        # enquanto houver outro agendamento ativo do mesmo cliente.
        if phone and not has_active:
            cur.execute(
                """UPDATE fidelidade_cliente SET cliente_telefone=NULL
                WHERE barbearia_id=%s AND cliente_telefone=%s""",
                (shop_id, phone),
            )

        return completed

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_email(value: EmailStr | None):
    if value is None:
        return value
    return str(value).strip().lower()


def validate_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("A senha não pode ultrapassar 72 bytes")
    if value.lower() in {
        "12345678",
        "password",
        "senha123",
        "qwerty123",
        "admin123",
    }:
        raise ValueError("Escolha uma senha menos comum")
    if value.isspace():
        raise ValueError("A senha não pode conter apenas espaços")
    return value


class Register(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=12, max_length=72)
    telefone: str = Field(default="", max_length=30)
    barbearia_nome: str = Field(min_length=2, max_length=160)
    plano: Literal["essencial", "profissional", "premium"] = "profissional"

    @field_validator("email")
    @classmethod
    def normalize_registration_email(cls, value):
        return normalize_email(value)

    @field_validator("senha")
    @classmethod
    def validate_registration_password(cls, value):
        return validate_password(value)


class Login(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value):
        return normalize_email(value)


class ResendVerification(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_resend_email(cls, value):
        return normalize_email(value)


class VerificationSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=20, max_length=200)


class ForgotPassword(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_recovery_email(cls, value):
        return normalize_email(value)


class ResetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)
    senha: str = Field(min_length=12, max_length=72)

    @field_validator("senha")
    @classmethod
    def validate_new_password(cls, value):
        return validate_password(value)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: Literal["essencial", "profissional", "premium"]


class CheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=8, max_length=255, pattern=r"^cs_(test_)?[A-Za-z0-9_]+$")


class Barber(BaseModel):
    nome: str
    telefone: str = ""
    comissao_percentual: Decimal = Field(default=40, ge=0, le=100)
    foto_url: str = ""


class Appointment(BaseModel):
    barbeiro_id: int
    servico_id: int | None = None
    cliente_nome: str
    cliente_telefone: str
    cliente_email: EmailStr | None = None
    data_hora: datetime
    duracao_minutos: int = Field(default=30, ge=15, le=240)
    servico: str = "Corte"
    preco: Decimal = Field(default=45, ge=0)
    whatsapp_autorizado: bool = False


class AppointmentUpdate(BaseModel):
    barbeiro_id: int | None = None
    data_hora: datetime | None = None
    status: str | None = None
    servico: str | None = None
    preco: Decimal | None = None


class PublicAppointment(Appointment):
    model_config = ConfigDict(extra="forbid")
    cliente_email: EmailStr


class Product(BaseModel):
    nome: str
    preco: Decimal = Field(ge=0)
    quantidade_estoque: int = Field(default=0, ge=0)


class Service(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    descricao: str = Field(default="", max_length=240)
    duracao_minutos: int = Field(default=30, ge=10, le=480)
    preco: Decimal = Field(ge=0)
    imagem_url: str = ""


class ProductSale(BaseModel):
    produto_id: int
    quantidade: int = Field(default=1, gt=0)


class Cut(BaseModel):
    cliente_telefone: str
    cliente_nome: str = ""


class ConfirmRequest(BaseModel):
    agendamento_id: int


class ShopUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nome: str
    telefone: str = ""
    endereco: str = ""
    cnpj: str = ""
    logo_url: str = ""
    email_notificacoes: EmailStr | None = None
    notificar_novos_agendamentos: bool = True
    public_booking_enabled: bool = True

    @field_validator("email_notificacoes")
    @classmethod
    def normalize_notification_email(cls, value):
        return normalize_email(value)


class BusinessHour(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    ativo: bool = True
    hora_inicio: time | None = None
    hora_fim: time | None = None

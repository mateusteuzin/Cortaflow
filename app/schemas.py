from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

GOOGLE_EMAIL_DOMAINS = {"gmail.com", "googlemail.com"}

def validate_google_email_address(value: EmailStr | None):
    if value is None:
        return value
    domain = str(value).rsplit("@", 1)[-1].lower()
    if domain not in GOOGLE_EMAIL_DOMAINS:
        raise ValueError("Use um e-mail oficial do Gmail (@gmail.com)")
    return value

class Register(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=6, max_length=72)
    telefone: str = ""
    barbearia_nome: str = Field(min_length=2, max_length=160)
    plano: Literal["essencial", "profissional", "premium"] = "profissional"

    @field_validator("email")
    @classmethod
    def validate_google_email(cls, value):
        return validate_google_email_address(value)

class Login(BaseModel):
    email: EmailStr
    senha: str

class ResendVerification(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_google_email(cls, value):
        return validate_google_email_address(value)

class VerificationSession(BaseModel):
    code: str = Field(min_length=20, max_length=200)

class ForgotPassword(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_google_email(cls, value):
        return validate_google_email_address(value)

class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    senha: str = Field(min_length=6, max_length=72)

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
    def validate_google_email(cls, value):
        return validate_google_email_address(value)

class BusinessHour(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    ativo: bool = True
    hora_inicio: time | None = None
    hora_fim: time | None = None

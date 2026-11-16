"""Modelos de dados (SQLAlchemy) e constantes de domínio do PetMóvel Itajubá."""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# --- Constantes de domínio -------------------------------------------------

PERFIL_CLIENTE = "CLIENTE"
PERFIL_PRESTADOR = "PRESTADOR"

ESPECIES = ("Cão", "Gato")
PORTES = ("Pequeno", "Medio", "Grande")
MULTIPLICADORES = {"Pequeno": 1.0, "Medio": 1.25, "Grande": 1.5}

TIPO_LOJA = "PRESENCIAL_LOJA"
TIPO_MOVEL = "DOMICILIO_MOVEL"
TIPOS = (TIPO_LOJA, TIPO_MOVEL)

FORMAS_PAGAMENTO = ("Dinheiro", "Cartao", "PIX")

PENDENTE = "Pendente"
CONFIRMADO = "Confirmado"
EM_DESLOCAMENTO = "Em Deslocamento"
EM_ATENDIMENTO = "Em Atendimento"
CONCLUIDO = "Concluído"
CANCELADO = "Cancelado"

STATUS_ATIVOS = (PENDENTE, CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO)
STATUS_FINAIS = (CONCLUIDO, CANCELADO)

# Slots de atendimento: horas cheias das 08:00 às 17:00.
HORAS_ATENDIMENTO = range(8, 18)


# --- Tabelas ---------------------------------------------------------------

class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    telefone = db.Column(db.String(30))
    endereco_completo = db.Column(db.String(255))
    bairro = db.Column(db.String(80))
    perfil = db.Column(db.String(20), nullable=False, default=PERFIL_CLIENTE)

    pets = db.relationship("Pet", back_populates="cliente", order_by="Pet.nome")
    notificacoes = db.relationship("Notificacao", back_populates="usuario")

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def eh_prestador(self) -> bool:
        return self.perfil == PERFIL_PRESTADOR


class Pet(db.Model):
    __tablename__ = "pet"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)
    especie = db.Column(db.String(10), nullable=False)
    porte = db.Column(db.String(10), nullable=False)
    restricoes_medicas = db.Column(db.Text)

    cliente = db.relationship("Usuario", back_populates="pets")
    agendamentos = db.relationship("Agendamento", back_populates="pet")


class Servico(db.Model):
    __tablename__ = "servico"

    id = db.Column(db.Integer, primary_key=True)
    nome_servico = db.Column(db.String(80), nullable=False)
    descricao = db.Column(db.String(255))
    preco_base = db.Column(db.Float, nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)


class BairroCobertura(db.Model):
    __tablename__ = "bairro_cobertura"

    id = db.Column(db.Integer, primary_key=True)
    nome_bairro = db.Column(db.String(80), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)


class UnidadeMovel(db.Model):
    __tablename__ = "unidade_movel"

    id = db.Column(db.Integer, primary_key=True)
    modelo = db.Column(db.String(80), nullable=False)
    placa = db.Column(db.String(20), nullable=False)
    profissional_responsavel = db.Column(db.String(120), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)


class PostoFixo(db.Model):
    __tablename__ = "posto_fixo"

    id = db.Column(db.Integer, primary_key=True)
    identificacao_mesa = db.Column(db.String(80), nullable=False)
    responsavel_setor = db.Column(db.String(120), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)


class Agendamento(db.Model):
    __tablename__ = "agendamento"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    pet_id = db.Column(db.Integer, db.ForeignKey("pet.id"), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    tipo_atendimento = db.Column(db.String(20), nullable=False)
    endereco_atendimento = db.Column(db.String(255))
    bairro_atendimento = db.Column(db.String(80))
    status = db.Column(db.String(20), nullable=False, default=PENDENTE)
    forma_pagamento = db.Column(db.String(20), nullable=False)
    valor_total = db.Column(db.Float, nullable=False, default=0.0)
    unidade_movel_id = db.Column(db.Integer, db.ForeignKey("unidade_movel.id"))
    posto_fixo_id = db.Column(db.Integer, db.ForeignKey("posto_fixo.id"))

    cliente = db.relationship("Usuario")
    pet = db.relationship("Pet", back_populates="agendamentos")
    itens = db.relationship(
        "AgendamentoServico", back_populates="agendamento",
        cascade="all, delete-orphan",
    )
    unidade_movel = db.relationship("UnidadeMovel")
    posto_fixo = db.relationship("PostoFixo")

    @property
    def duracao_total(self) -> int:
        return sum(item.servico.duracao_minutos for item in self.itens)

    @property
    def em_domicilio(self) -> bool:
        return self.tipo_atendimento == TIPO_MOVEL


class AgendamentoServico(db.Model):
    __tablename__ = "agendamento_servico"

    id = db.Column(db.Integer, primary_key=True)
    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamento.id"), nullable=False)
    servico_id = db.Column(db.Integer, db.ForeignKey("servico.id"), nullable=False)
    preco_aplicado = db.Column(db.Float, nullable=False)

    agendamento = db.relationship("Agendamento", back_populates="itens")
    servico = db.relationship("Servico")


class Notificacao(db.Model):
    __tablename__ = "notificacao"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    mensagem = db.Column(db.String(255), nullable=False)
    lida = db.Column(db.Boolean, nullable=False, default=False)
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    usuario = db.relationship("Usuario", back_populates="notificacoes")

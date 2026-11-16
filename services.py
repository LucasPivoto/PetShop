"""Regras de negócio do PetMóvel Itajubá.

Nada aqui depende de `request`: as funções recebem objetos e, quando o relógio
importa, um parâmetro `agora`, o que as mantém testáveis isoladamente.
"""
from datetime import date, datetime, time, timedelta

from models import (
    HORAS_ATENDIMENTO, MULTIPLICADORES, STATUS_ATIVOS, TIPO_MOVEL, Agendamento,
    BairroCobertura, PostoFixo, Servico, UnidadeMovel, db,
)

JANELA = timedelta(hours=1)


class RegraNegocioError(Exception):
    """Violação de regra de negócio; a mensagem é exibida ao usuário."""


# --- Preço -----------------------------------------------------------------

def calcular_preco(preco_base: float, porte: str) -> float:
    if porte not in MULTIPLICADORES:
        raise RegraNegocioError("Porte do pet inválido.")
    return round(preco_base * MULTIPLICADORES[porte], 2)


def calcular_total(servicos: list[Servico], porte: str) -> float:
    return round(sum(calcular_preco(s.preco_base, porte) for s in servicos), 2)


# --- Cobertura -------------------------------------------------------------

def buscar_bairro(nome: str | None) -> BairroCobertura | None:
    """Localiza o bairro pelo nome, ignorando maiúsculas e espaços nas pontas."""
    chave = (nome or "").strip().casefold()
    if not chave:
        return None
    for bairro in BairroCobertura.query.all():
        if bairro.nome_bairro.strip().casefold() == chave:
            return bairro
    return None


def bairro_coberto(nome: str | None) -> bool:
    bairro = buscar_bairro(nome)
    return bool(bairro and bairro.ativo)


# --- Disponibilidade -------------------------------------------------------

def _modelo_recurso(tipo: str):
    return UnidadeMovel if tipo == TIPO_MOVEL else PostoFixo


def capacidade(tipo: str) -> int:
    """Quantidade de recursos ativos (vans ou baias) da modalidade."""
    return _modelo_recurso(tipo).query.filter_by(ativo=True).count()


def ocupados(tipo: str, data_hora: datetime, ignorar_id: int | None = None) -> int:
    """Atendimentos ativos da modalidade a menos de 1 hora de `data_hora`."""
    consulta = Agendamento.query.filter(
        Agendamento.tipo_atendimento == tipo,
        Agendamento.status.in_(STATUS_ATIVOS),
        Agendamento.data_hora > data_hora - JANELA,
        Agendamento.data_hora < data_hora + JANELA,
    )
    if ignorar_id is not None:
        consulta = consulta.filter(Agendamento.id != ignorar_id)
    return consulta.count()


def horarios_disponiveis(tipo: str, dia: date, agora: datetime | None = None) -> list[dict]:
    agora = agora or datetime.now()
    vagas = capacidade(tipo)
    horarios = []
    for hora in HORAS_ATENDIMENTO:
        slot = datetime.combine(dia, time(hora, 0))
        livre = slot > agora and ocupados(tipo, slot) < vagas
        horarios.append({"hora": f"{hora:02d}:00", "livre": livre})
    return horarios

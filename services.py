"""Regras de negócio do PetMóvel Itajubá.

Nada aqui depende de `request`: as funções recebem objetos e, quando o relógio
importa, um parâmetro `agora`, o que as mantém testáveis isoladamente.
"""
from datetime import date, datetime, time, timedelta

from models import (
    CANCELADO, CONCLUIDO, CONFIRMADO, EM_ATENDIMENTO, EM_DESLOCAMENTO,
    FORMAS_PAGAMENTO, HORAS_ATENDIMENTO, MULTIPLICADORES, PENDENTE,
    PERFIL_CLIENTE, PERFIL_PRESTADOR, STATUS_ATIVOS, TIPO_LOJA, TIPO_MOVEL, TIPOS,
    Agendamento, AgendamentoServico, BairroCobertura, Notificacao, Pet, PostoFixo,
    Servico, UnidadeMovel, Usuario, db,
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


# --- Notificações ----------------------------------------------------------

def notificar(usuario_id: int, mensagem: str) -> Notificacao:
    """Registra uma notificação na sessão (o commit fica com quem chamou)."""
    notificacao = Notificacao(usuario_id=usuario_id, mensagem=mensagem)
    db.session.add(notificacao)
    return notificacao


def _rotulo_agendamento(ag: Agendamento) -> str:
    return f"Agendamento #{ag.id} ({ag.pet.nome}, {ag.data_hora:%d/%m/%Y %H:%M})"


# --- Criação de agendamento ------------------------------------------------

def _para_int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def criar_agendamento(cliente: Usuario, pet_id, servico_ids: list, tipo: str,
                      data_hora: datetime, forma_pagamento: str, bairro: str = "",
                      endereco: str = "", agora: datetime | None = None) -> Agendamento:
    """Valida e grava um agendamento Pendente. Em falha, nada é gravado."""
    agora = agora or datetime.now()

    pet = db.session.get(Pet, _para_int(pet_id) or 0)
    if pet is None or pet.cliente_id != cliente.id:
        raise RegraNegocioError("Selecione um pet válido.")

    ids = list(dict.fromkeys(_para_int(i) for i in (servico_ids or [])))
    if not ids:
        raise RegraNegocioError("Selecione ao menos um serviço.")
    servicos = [db.session.get(Servico, i or 0) for i in ids]
    if any(s is None for s in servicos):
        raise RegraNegocioError("Serviço selecionado não existe.")

    if tipo not in TIPOS:
        raise RegraNegocioError("Modalidade de atendimento inválida.")
    if forma_pagamento not in FORMAS_PAGAMENTO:
        raise RegraNegocioError("Forma de pagamento inválida.")

    horario_cheio = data_hora.minute == 0 and data_hora.second == 0
    if not horario_cheio or data_hora.hour not in HORAS_ATENDIMENTO:
        raise RegraNegocioError("Escolha um horário cheio entre 08:00 e 17:00.")
    if data_hora <= agora:
        raise RegraNegocioError("Escolha uma data e um horário futuros.")

    bairro_nome = endereco_final = None
    if tipo == TIPO_MOVEL:
        endereco_final = (endereco or "").strip()
        if not endereco_final:
            raise RegraNegocioError(
                "Informe o endereço completo para o atendimento em domicílio.")
        registro = buscar_bairro(bairro)
        if registro is None or not registro.ativo:
            nome = (bairro or "").strip() or "informado"
            raise RegraNegocioError(
                f"O bairro {nome} está fora da área de cobertura da unidade móvel.")
        bairro_nome = registro.nome_bairro

    if ocupados(tipo, data_hora) >= capacidade(tipo):
        recurso = "unidade móvel" if tipo == TIPO_MOVEL else "baia da loja"
        raise RegraNegocioError(
            f"Não há {recurso} disponível nesse horário. Escolha outro horário.")

    ag = Agendamento(
        cliente_id=cliente.id, pet_id=pet.id, data_hora=data_hora,
        tipo_atendimento=tipo, endereco_atendimento=endereco_final,
        bairro_atendimento=bairro_nome, status=PENDENTE,
        forma_pagamento=forma_pagamento,
        valor_total=calcular_total(servicos, pet.porte),
    )
    for servico in servicos:
        ag.itens.append(AgendamentoServico(
            servico_id=servico.id,
            preco_aplicado=calcular_preco(servico.preco_base, pet.porte)))
    db.session.add(ag)
    db.session.flush()
    notificar(cliente.id, f"{_rotulo_agendamento(ag)}: solicitação recebida. "
                          f"Status: {PENDENTE} — aguardando confirmação da equipe.")
    db.session.commit()
    return ag


# --- Máquina de estados ----------------------------------------------------

PAPEL_PRESTADOR = "prestador"
PAPEL_DONO = "dono"

# Única fonte da verdade das transições. Qualquer combinação fora desta tabela
# é recusada: (ação, rótulo, de, para, papéis autorizados, modalidades).
TRANSICOES = (
    ("confirmar", "Confirmar (validar rota e escala)", PENDENTE, CONFIRMADO,
     (PAPEL_PRESTADOR,), TIPOS),
    ("recusar", "Recusar atendimento", PENDENTE, CANCELADO,
     (PAPEL_PRESTADOR,), TIPOS),
    ("iniciar_deslocamento", "Iniciar deslocamento", CONFIRMADO, EM_DESLOCAMENTO,
     (PAPEL_PRESTADOR,), (TIPO_MOVEL,)),
    ("iniciar_atendimento", "Chegada no local", EM_DESLOCAMENTO, EM_ATENDIMENTO,
     (PAPEL_PRESTADOR,), (TIPO_MOVEL,)),
    ("iniciar_atendimento", "Iniciar atendimento", CONFIRMADO, EM_ATENDIMENTO,
     (PAPEL_PRESTADOR,), (TIPO_LOJA,)),
    ("concluir", "Finalizar procedimentos", EM_ATENDIMENTO, CONCLUIDO,
     (PAPEL_PRESTADOR,), TIPOS),
    ("cancelar", "Cancelar", PENDENTE, CANCELADO, (PAPEL_DONO,), TIPOS),
    ("cancelar", "Cancelar", CONFIRMADO, CANCELADO,
     (PAPEL_DONO, PAPEL_PRESTADOR), TIPOS),
)

_DETALHES = {
    "recusar": "A equipe não pôde aceitar a solicitação.",
    "cancelar": "O agendamento foi cancelado.",
    "iniciar_deslocamento": "A unidade móvel está a caminho do seu endereço.",
    "iniciar_atendimento": "O atendimento do seu pet começou.",
    "concluir": "Atendimento finalizado. Obrigado pela preferência!",
}


def _papel(ag: Agendamento, usuario: Usuario) -> str | None:
    if usuario.perfil == PERFIL_PRESTADOR:
        return PAPEL_PRESTADOR
    if usuario.perfil == PERFIL_CLIENTE and usuario.id == ag.cliente_id:
        return PAPEL_DONO
    return None


def _transicoes_validas(ag: Agendamento, usuario: Usuario) -> list[tuple]:
    papel = _papel(ag, usuario)
    return [t for t in TRANSICOES
            if t[2] == ag.status and papel in t[4] and ag.tipo_atendimento in t[5]]


def acoes_disponiveis(ag: Agendamento, usuario: Usuario) -> list[tuple[str, str]]:
    """Pares (ação, rótulo) que `executar_acao` aceitaria para este usuário."""
    return [(t[0], t[1]) for t in _transicoes_validas(ag, usuario)]


def _alocar_recurso(ag: Agendamento):
    """Primeiro recurso ativo da modalidade sem outro atendimento na janela."""
    coluna = (Agendamento.unidade_movel_id if ag.tipo_atendimento == TIPO_MOVEL
              else Agendamento.posto_fixo_id)
    em_uso = {
        linha[0] for linha in db.session.query(coluna).filter(
            Agendamento.id != ag.id,
            Agendamento.tipo_atendimento == ag.tipo_atendimento,
            Agendamento.status.in_((CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO)),
            Agendamento.data_hora > ag.data_hora - JANELA,
            Agendamento.data_hora < ag.data_hora + JANELA,
            coluna.isnot(None),
        )
    }
    modelo = _modelo_recurso(ag.tipo_atendimento)
    for recurso in modelo.query.filter_by(ativo=True).order_by(modelo.id):
        if recurso.id not in em_uso:
            return recurso
    return None


def _confirmar(ag: Agendamento) -> str:
    """validarRotaEEscala(): confere a cobertura e reserva van ou baia."""
    if ag.tipo_atendimento == TIPO_MOVEL and not bairro_coberto(ag.bairro_atendimento):
        raise RegraNegocioError(
            f"O bairro {ag.bairro_atendimento} está fora da área de cobertura "
            "da unidade móvel. Recuse o atendimento ou reative o bairro.")
    recurso = _alocar_recurso(ag)
    if recurso is None:
        nome = "unidade móvel" if ag.tipo_atendimento == TIPO_MOVEL else "baia"
        raise RegraNegocioError(f"Não há {nome} livre nesse horário para confirmar.")
    if ag.tipo_atendimento == TIPO_MOVEL:
        ag.unidade_movel_id = recurso.id
        return f"Solicitação aprovada — {recurso.modelo} reservada para o seu endereço."
    ag.posto_fixo_id = recurso.id
    return f"Solicitação aprovada — {recurso.identificacao_mesa} reservada."


def executar_acao(ag: Agendamento, acao: str, usuario: Usuario) -> Agendamento:
    """Aplica uma transição da tabela, notifica o cliente e faz commit."""
    transicao = next((t for t in _transicoes_validas(ag, usuario) if t[0] == acao), None)
    if transicao is None:
        raise RegraNegocioError(
            f"Ação não permitida para um agendamento com status {ag.status}.")
    novo_status = transicao[3]
    detalhe = _confirmar(ag) if acao == "confirmar" else _DETALHES[acao]
    ag.status = novo_status
    notificar(ag.cliente_id, f"{_rotulo_agendamento(ag)}: {detalhe} Status: {novo_status}.")
    db.session.commit()
    return ag


# --- Visão do prestador ----------------------------------------------------

def agenda_do_dia(dia: date, tipo: str | None = None) -> list[Agendamento]:
    inicio = datetime.combine(dia, time.min)
    consulta = Agendamento.query.filter(
        Agendamento.data_hora >= inicio,
        Agendamento.data_hora < inicio + timedelta(days=1),
    )
    if tipo:
        consulta = consulta.filter(Agendamento.tipo_atendimento == tipo)
    return consulta.order_by(Agendamento.data_hora, Agendamento.id).all()


def resumo_do_dia(dia: date) -> dict:
    validos = [a for a in agenda_do_dia(dia) if a.status != CANCELADO]
    return {
        "total": len(validos),
        "pendentes": sum(a.status == PENDENTE for a in validos),
        "loja": sum(a.tipo_atendimento == TIPO_LOJA for a in validos),
        "movel": sum(a.tipo_atendimento == TIPO_MOVEL for a in validos),
    }

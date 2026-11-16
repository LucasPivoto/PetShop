from datetime import datetime, time, timedelta

import pytest

from conftest import AGORA, DIA
from models import (
    CANCELADO, CONCLUIDO, CONFIRMADO, EM_ATENDIMENTO, EM_DESLOCAMENTO, PENDENTE,
    TIPO_LOJA, TIPO_MOVEL, Agendamento, AgendamentoServico, BairroCobertura,
    Notificacao, UnidadeMovel, Usuario, db,
)
from services import (
    RegraNegocioError, acoes_disponiveis, agenda_do_dia, criar_agendamento,
    executar_acao, resumo_do_dia,
)

TODOS_STATUS = [PENDENTE, CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO, CONCLUIDO, CANCELADO]
TODAS_ACOES = ["confirmar", "recusar", "cancelar", "iniciar_deslocamento",
               "iniciar_atendimento", "concluir", "inexistente"]
PERMITIDAS_PRESTADOR_DOMICILIO = {
    (PENDENTE, "confirmar"): CONFIRMADO,
    (PENDENTE, "recusar"): CANCELADO,
    (CONFIRMADO, "cancelar"): CANCELADO,
    (CONFIRMADO, "iniciar_deslocamento"): EM_DESLOCAMENTO,
    (EM_DESLOCAMENTO, "iniciar_atendimento"): EM_ATENDIMENTO,
    (EM_ATENDIMENTO, "concluir"): CONCLUIDO,
}


def _u(uid):
    return db.session.get(Usuario, uid)


def _novo(dados, tipo=TIPO_MOVEL, hora=10, **kw):
    """Cria via regra de negócio, com valores válidos por padrão."""
    args = dict(
        cliente=_u(dados.cliente), pet_id=dados.thor,
        servico_ids=[dados.banho, dados.unhas], tipo=tipo,
        data_hora=datetime.combine(DIA, time(hora, 0)), forma_pagamento="PIX",
        bairro="BPS", endereco="Rua A, 10", agora=AGORA,
    )
    args.update(kw)
    return criar_agendamento(**args)


def _direto(dados, tipo=TIPO_MOVEL, hora=10, status=PENDENTE, dia=DIA, cliente=None, pet=None):
    """Insere direto no banco, em qualquer status, com recurso se já confirmado."""
    ag = Agendamento(
        cliente_id=cliente or dados.cliente, pet_id=pet or dados.thor,
        data_hora=datetime.combine(dia, time(hora, 0)), tipo_atendimento=tipo,
        status=status, forma_pagamento="PIX", valor_total=75.0,
        bairro_atendimento="BPS" if tipo == TIPO_MOVEL else None,
        endereco_atendimento="Rua A, 10" if tipo == TIPO_MOVEL else None,
    )
    if status in (CONFIRMADO, EM_DESLOCAMENTO, EM_ATENDIMENTO, CONCLUIDO):
        if tipo == TIPO_MOVEL:
            ag.unidade_movel_id = dados.van
        else:
            ag.posto_fixo_id = dados.baia1
    ag.itens.append(AgendamentoServico(servico_id=dados.banho, preco_aplicado=75.0))
    db.session.add(ag)
    db.session.commit()
    return ag


def _ultima_notificacao(usuario_id):
    return (Notificacao.query.filter_by(usuario_id=usuario_id)
            .order_by(Notificacao.id.desc()).first())


# --- Criação ---------------------------------------------------------------

def test_cria_pendente_com_total_e_itens(app, dados):
    ag = _novo(dados)
    assert ag.status == PENDENTE
    assert ag.valor_total == 105.0
    assert sorted(i.preco_aplicado for i in ag.itens) == [30.0, 75.0]
    assert ag.unidade_movel_id is None and ag.posto_fixo_id is None
    assert ag.bairro_atendimento == "BPS"
    assert ag.endereco_atendimento == "Rua A, 10"
    assert Notificacao.query.filter_by(usuario_id=dados.cliente).count() == 1


def test_bairro_gravado_com_nome_canonico(app, dados):
    ag = _novo(dados, bairro="  bps ")
    assert ag.bairro_atendimento == "BPS"


def test_loja_ignora_endereco(app, dados):
    ag = _novo(dados, tipo=TIPO_LOJA)
    assert ag.bairro_atendimento is None
    assert ag.endereco_atendimento is None


@pytest.mark.parametrize("kw", [
    {"pet_id": "luna"},
    {"pet_id": 9999},
    {"pet_id": "abc"},
    {"servico_ids": []},
    {"servico_ids": [9999]},
    {"servico_ids": ["abc"]},
    {"tipo": "OUTRO"},
    {"forma_pagamento": "Cheque"},
    {"data_hora": datetime(2026, 3, 1, 10, 0)},
    {"data_hora": datetime(2026, 3, 3, 10, 30)},
    {"data_hora": datetime(2026, 3, 3, 7, 0)},
    {"data_hora": datetime(2026, 3, 3, 18, 0)},
    {"bairro": "Cruzeiro"},
    {"bairro": "Inexistente"},
    {"endereco": "   "},
])
def test_criacao_invalida_nao_grava(app, dados, kw):
    if kw.get("pet_id") == "luna":
        kw = {"pet_id": dados.luna}
    with pytest.raises(RegraNegocioError):
        _novo(dados, **kw)
    assert Agendamento.query.count() == 0
    assert Notificacao.query.count() == 0


def test_servico_repetido_conta_uma_vez(app, dados):
    ag = _novo(dados, servico_ids=[dados.banho, dados.banho])
    assert ag.valor_total == 75.0
    assert len(ag.itens) == 1


def test_van_cheia_recusa_segundo(app, dados):
    _novo(dados)
    with pytest.raises(RegraNegocioError):
        _novo(dados)
    assert Agendamento.query.count() == 1


def test_loja_recusa_terceiro(app, dados):
    _novo(dados, tipo=TIPO_LOJA)
    _novo(dados, tipo=TIPO_LOJA)
    with pytest.raises(RegraNegocioError):
        _novo(dados, tipo=TIPO_LOJA)
    assert Agendamento.query.count() == 2


def test_cancelado_libera_slot(app, dados):
    primeiro = _novo(dados)
    executar_acao(primeiro, "cancelar", _u(dados.cliente))
    segundo = _novo(dados)
    assert segundo.status == PENDENTE


# --- Fluxos completos ------------------------------------------------------

def test_fluxo_completo_domicilio(app, dados):
    prestador = _u(dados.prestador)
    ag = _novo(dados)
    passos = [("confirmar", CONFIRMADO), ("iniciar_deslocamento", EM_DESLOCAMENTO),
              ("iniciar_atendimento", EM_ATENDIMENTO), ("concluir", CONCLUIDO)]
    for acao, esperado in passos:
        executar_acao(ag, acao, prestador)
        assert ag.status == esperado
        assert esperado in _ultima_notificacao(dados.cliente).mensagem
    assert ag.unidade_movel_id == dados.van
    assert ag.posto_fixo_id is None


def test_fluxo_completo_loja(app, dados):
    prestador = _u(dados.prestador)
    a = _novo(dados, tipo=TIPO_LOJA)
    b = _novo(dados, tipo=TIPO_LOJA)
    executar_acao(a, "confirmar", prestador)
    executar_acao(b, "confirmar", prestador)
    assert a.posto_fixo_id == dados.baia1
    assert b.posto_fixo_id == dados.baia2
    assert a.unidade_movel_id is None
    executar_acao(a, "iniciar_atendimento", prestador)
    assert a.status == EM_ATENDIMENTO
    executar_acao(a, "concluir", prestador)
    assert a.status == CONCLUIDO


def test_loja_nao_desloca(app, dados):
    ag = _direto(dados, tipo=TIPO_LOJA, status=CONFIRMADO)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "iniciar_deslocamento", _u(dados.prestador))
    assert ag.status == CONFIRMADO


def test_domicilio_nao_pula_deslocamento(app, dados):
    ag = _direto(dados, status=CONFIRMADO)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "iniciar_atendimento", _u(dados.prestador))
    assert ag.status == CONFIRMADO


@pytest.mark.parametrize("status", TODOS_STATUS)
@pytest.mark.parametrize("acao", TODAS_ACOES)
def test_matriz_de_transicoes_prestador_domicilio(app, dados, status, acao):
    ag = _direto(dados, status=status)
    antes = Notificacao.query.count()
    esperado = PERMITIDAS_PRESTADOR_DOMICILIO.get((status, acao))
    if esperado:
        executar_acao(ag, acao, _u(dados.prestador))
        assert ag.status == esperado
        assert Notificacao.query.count() == antes + 1
    else:
        with pytest.raises(RegraNegocioError):
            executar_acao(ag, acao, _u(dados.prestador))
        db.session.refresh(ag)
        assert ag.status == status
        assert Notificacao.query.count() == antes


@pytest.mark.parametrize("status", [CONCLUIDO, CANCELADO])
def test_estados_finais_imutaveis(app, dados, status):
    ag = _direto(dados, status=status)
    for usuario in (_u(dados.prestador), _u(dados.cliente)):
        for acao in TODAS_ACOES:
            with pytest.raises(RegraNegocioError):
                executar_acao(ag, acao, usuario)
    assert ag.status == status


# --- Permissões ------------------------------------------------------------

@pytest.mark.parametrize("status", [PENDENTE, CONFIRMADO])
def test_cliente_cancela_pendente_e_confirmado(app, dados, status):
    ag = _direto(dados, status=status)
    executar_acao(ag, "cancelar", _u(dados.cliente))
    assert ag.status == CANCELADO


@pytest.mark.parametrize("status", [EM_DESLOCAMENTO, EM_ATENDIMENTO])
def test_cliente_nao_cancela_em_andamento(app, dados, status):
    ag = _direto(dados, status=status)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "cancelar", _u(dados.cliente))
    assert ag.status == status


def test_outro_cliente_nao_cancela(app, dados):
    ag = _direto(dados)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "cancelar", _u(dados.maria))
    assert ag.status == PENDENTE


def test_cliente_nao_confirma(app, dados):
    ag = _direto(dados)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "confirmar", _u(dados.cliente))
    assert ag.status == PENDENTE


def test_prestador_nao_usa_cancelar_em_pendente(app, dados):
    ag = _direto(dados)
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "cancelar", _u(dados.prestador))
    assert ag.status == PENDENTE


# --- Recurso some entre agendar e confirmar --------------------------------

def test_confirmar_falha_se_bairro_desativado(app, dados):
    ag = _novo(dados)
    db.session.get(BairroCobertura, dados.bps).ativo = False
    db.session.commit()
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "confirmar", _u(dados.prestador))
    db.session.refresh(ag)
    assert ag.status == PENDENTE
    assert ag.unidade_movel_id is None


def test_confirmar_falha_se_van_desativada(app, dados):
    ag = _novo(dados)
    db.session.get(UnidadeMovel, dados.van).ativo = False
    db.session.commit()
    with pytest.raises(RegraNegocioError):
        executar_acao(ag, "confirmar", _u(dados.prestador))
    db.session.refresh(ag)
    assert ag.status == PENDENTE


def test_confirmar_falha_se_recurso_ja_alocado(app, dados):
    _direto(dados, status=CONFIRMADO)
    pendente = _direto(dados, status=PENDENTE)
    with pytest.raises(RegraNegocioError):
        executar_acao(pendente, "confirmar", _u(dados.prestador))
    db.session.refresh(pendente)
    assert pendente.status == PENDENTE
    assert pendente.unidade_movel_id is None


def test_confirmar_usa_van_livre_em_outro_horario(app, dados):
    _direto(dados, hora=10, status=CONFIRMADO)
    outro = _direto(dados, hora=11, status=PENDENTE)
    executar_acao(outro, "confirmar", _u(dados.prestador))
    assert outro.unidade_movel_id == dados.van


# --- Ações disponíveis, resumo e agenda ------------------------------------

def _nomes(ag, uid):
    return [acao for acao, _ in acoes_disponiveis(ag, _u(uid))]


def test_acoes_disponiveis(app, dados):
    pendente = _direto(dados, hora=8)
    assert _nomes(pendente, dados.prestador) == ["confirmar", "recusar"]
    assert _nomes(pendente, dados.cliente) == ["cancelar"]
    assert _nomes(pendente, dados.maria) == []

    conf_movel = _direto(dados, hora=10, status=CONFIRMADO)
    assert _nomes(conf_movel, dados.prestador) == ["iniciar_deslocamento", "cancelar"]
    assert _nomes(conf_movel, dados.cliente) == ["cancelar"]

    conf_loja = _direto(dados, tipo=TIPO_LOJA, hora=10, status=CONFIRMADO)
    assert _nomes(conf_loja, dados.prestador) == ["iniciar_atendimento", "cancelar"]

    em_rota = _direto(dados, hora=12, status=EM_DESLOCAMENTO)
    assert _nomes(em_rota, dados.prestador) == ["iniciar_atendimento"]
    assert _nomes(em_rota, dados.cliente) == []

    concluido = _direto(dados, hora=14, status=CONCLUIDO)
    assert _nomes(concluido, dados.prestador) == []
    assert _nomes(concluido, dados.cliente) == []


def test_rotulos_das_acoes(app, dados):
    em_rota = _direto(dados, hora=12, status=EM_DESLOCAMENTO)
    conf_loja = _direto(dados, tipo=TIPO_LOJA, hora=10, status=CONFIRMADO)
    prestador = _u(dados.prestador)
    assert dict(acoes_disponiveis(em_rota, prestador))["iniciar_atendimento"] == "Chegada no local"
    assert dict(acoes_disponiveis(conf_loja, prestador))["iniciar_atendimento"] == "Iniciar atendimento"


def test_resumo_e_agenda_do_dia(app, dados):
    _direto(dados, tipo=TIPO_LOJA, hora=14, status=CONFIRMADO)
    _direto(dados, tipo=TIPO_MOVEL, hora=9, status=PENDENTE)
    _direto(dados, tipo=TIPO_LOJA, hora=11, status=CANCELADO)
    _direto(dados, tipo=TIPO_MOVEL, hora=9, dia=DIA + timedelta(days=1))

    assert resumo_do_dia(DIA) == {"total": 2, "pendentes": 1, "loja": 1, "movel": 1}
    agenda = agenda_do_dia(DIA)
    assert [a.data_hora.hour for a in agenda] == [9, 11, 14]
    assert len(agenda_do_dia(DIA, TIPO_LOJA)) == 2
    assert len(agenda_do_dia(DIA, TIPO_MOVEL)) == 1

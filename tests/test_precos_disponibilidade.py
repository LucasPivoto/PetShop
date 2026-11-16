from datetime import datetime, time

import pytest

from conftest import AGORA, DIA
from models import (
    CANCELADO, PENDENTE, TIPO_LOJA, TIPO_MOVEL, Agendamento, PostoFixo,
    Servico, UnidadeMovel, db,
)
from services import (
    RegraNegocioError, bairro_coberto, calcular_preco, calcular_total,
    capacidade, horarios_disponiveis,
)


def _ag(dados, tipo, hora, status=PENDENTE):
    ag = Agendamento(
        cliente_id=dados.cliente, pet_id=dados.thor,
        data_hora=datetime.combine(DIA, time(hora, 0)),
        tipo_atendimento=tipo, status=status, forma_pagamento="PIX", valor_total=75.0,
    )
    db.session.add(ag)
    db.session.commit()
    return ag


def _livres(tipo, agora=AGORA):
    return {h["hora"]: h["livre"] for h in horarios_disponiveis(tipo, DIA, agora)}


@pytest.mark.parametrize("base,porte,esperado", [
    (50, "Pequeno", 50.0), (50, "Medio", 62.5), (35, "Medio", 43.75), (50, "Grande", 75.0),
])
def test_calcular_preco(base, porte, esperado):
    assert calcular_preco(base, porte) == esperado


def test_porte_invalido_levanta():
    with pytest.raises(RegraNegocioError):
        calcular_preco(50, "Gigante")


def test_calcular_total(app, dados):
    servicos = [db.session.get(Servico, dados.banho), db.session.get(Servico, dados.unhas)]
    assert calcular_total(servicos, "Grande") == 105.0


@pytest.mark.parametrize("nome,ok", [
    ("Centro", True), ("  centro ", True), ("BPS", True),
    ("Cruzeiro", False), ("Inexistente", False), ("", False), (None, False),
])
def test_bairro_coberto(app, dados, nome, ok):
    assert bairro_coberto(nome) is ok


def test_capacidade(app, dados):
    assert capacidade(TIPO_LOJA) == 2
    assert capacidade(TIPO_MOVEL) == 1
    db.session.get(PostoFixo, dados.baia1).ativo = False
    db.session.commit()
    assert capacidade(TIPO_LOJA) == 1


def test_horarios_lista_dez_slots(app, dados):
    hs = horarios_disponiveis(TIPO_MOVEL, DIA, AGORA)
    assert [h["hora"] for h in hs] == [f"{h:02d}:00" for h in range(8, 18)]
    assert all(h["livre"] for h in hs)


def test_van_ocupada_bloqueia_slot(app, dados):
    _ag(dados, TIPO_MOVEL, 10)
    livres = _livres(TIPO_MOVEL)
    assert livres["10:00"] is False
    assert livres["11:00"] is True


def test_cancelado_nao_ocupa(app, dados):
    _ag(dados, TIPO_MOVEL, 10, status=CANCELADO)
    assert _livres(TIPO_MOVEL)["10:00"] is True


def test_loja_tem_duas_vagas(app, dados):
    _ag(dados, TIPO_LOJA, 10)
    assert _livres(TIPO_LOJA)["10:00"] is True
    _ag(dados, TIPO_LOJA, 10)
    assert _livres(TIPO_LOJA)["10:00"] is False


def test_tipos_nao_competem(app, dados):
    _ag(dados, TIPO_MOVEL, 10)
    assert _livres(TIPO_LOJA)["10:00"] is True


def test_slots_passados_indisponiveis(app, dados):
    agora = datetime.combine(DIA, time(12, 30))
    livres = _livres(TIPO_MOVEL, agora)
    assert [livres[f"{h:02d}:00"] for h in range(8, 13)] == [False] * 5
    assert livres["13:00"] is True


def test_sem_recurso_ativo_nada_livre(app, dados):
    db.session.get(UnidadeMovel, dados.van).ativo = False
    db.session.commit()
    assert not any(_livres(TIPO_MOVEL).values())

import re
from datetime import date, datetime, time, timedelta
from urllib.parse import unquote

import pytest

from conftest import login
from models import (
    CONCLUIDO, CONFIRMADO, PENDENTE, TIPO_LOJA, TIPO_MOVEL, Agendamento,
    AgendamentoServico, Notificacao, db,
)

HOJE = date.today()


def _html(resposta):
    return resposta.get_data(as_text=True)


def _avisos(resposta):
    return " ".join(re.findall(r'data-toast.*?<p class="flex-1">(.*?)</p>',
                               _html(resposta), re.S)).lower()


def _card(html, chave):
    return int(re.search(rf'data-card="{chave}"[^>]*>\s*(\d+)', html).group(1))


def _direto(dados, tipo=TIPO_MOVEL, hora=10, status=PENDENTE, dia=HOJE):
    ag = Agendamento(
        cliente_id=dados.cliente, pet_id=dados.thor,
        data_hora=datetime.combine(dia, time(hora, 0)), tipo_atendimento=tipo,
        status=status, forma_pagamento="PIX", valor_total=105.0,
        bairro_atendimento="BPS" if tipo == TIPO_MOVEL else None,
        endereco_atendimento="Rua A, 10" if tipo == TIPO_MOVEL else None,
    )
    if status == CONFIRMADO:
        if tipo == TIPO_MOVEL:
            ag.unidade_movel_id = dados.van
        else:
            ag.posto_fixo_id = dados.baia1
    ag.itens.append(AgendamentoServico(servico_id=dados.banho, preco_aplicado=75.0))
    ag.itens.append(AgendamentoServico(servico_id=dados.unhas, preco_aplicado=30.0))
    db.session.add(ag)
    db.session.commit()
    return ag


def _acao(client, ag, acao, **extra):
    return client.post(f"/agendamentos/{ag.id}/acao", data={"acao": acao, **extra})


# --- Acesso ----------------------------------------------------------------

def test_painel_exige_prestador(client, dados):
    resposta = client.get("/painel")
    assert unquote(resposta.headers["Location"]).endswith("/login?next=/painel")
    login(client, "cliente@teste.com")
    resposta = client.get("/painel")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")


# --- Dashboard e agenda ----------------------------------------------------

def test_cards_do_dia(client, dados):
    _direto(dados, tipo=TIPO_MOVEL, hora=10, status=PENDENTE)
    _direto(dados, tipo=TIPO_LOJA, hora=15, status=CONFIRMADO)
    _direto(dados, tipo=TIPO_LOJA, hora=9, dia=HOJE + timedelta(days=1))
    login(client, "admin@petmovel.com")
    html = _html(client.get("/painel"))
    assert (_card(html, "total"), _card(html, "pendentes")) == (2, 1)
    assert (_card(html, "loja"), _card(html, "movel")) == (1, 1)


def test_cards_ignoram_filtro_de_modalidade(client, dados):
    _direto(dados, tipo=TIPO_MOVEL, hora=10)
    _direto(dados, tipo=TIPO_LOJA, hora=15)
    login(client, "admin@petmovel.com")
    html = _html(client.get("/painel?tipo=loja"))
    assert (_card(html, "total"), _card(html, "movel")) == (2, 1)


def test_mostra_dados_do_atendimento(client, dados):
    _direto(dados, tipo=TIPO_MOVEL, hora=10)
    login(client, "admin@petmovel.com")
    html = _html(client.get("/painel"))
    for trecho in ("10:00", "Rua A, 10", "BPS", "Carlos Cliente", "(35) 99999-0000",
                   "Thor", "Grande", "Banho Completo", "Corte de Unhas", "PIX", "R$ 105,00"):
        assert trecho in html


def test_mostra_alerta_de_restricao(client, dados):
    _direto(dados)
    login(client, "admin@petmovel.com")
    html = _html(client.get("/painel"))
    assert "Alergia a shampoo perfumado" in html
    assert "data-alerta-restricao" in html


def test_filtro_modalidade(client, dados):
    _direto(dados, tipo=TIPO_MOVEL, hora=10)
    _direto(dados, tipo=TIPO_LOJA, hora=15)
    login(client, "admin@petmovel.com")
    assert "Rua A, 10" in _html(client.get("/painel?tipo=movel"))
    assert "Rua A, 10" not in _html(client.get("/painel?tipo=loja"))
    assert "Rua A, 10" in _html(client.get("/painel?tipo=todos"))
    assert "Rua A, 10" in _html(client.get("/painel?tipo=qualquercoisa"))


def test_filtro_data(client, dados):
    amanha = HOJE + timedelta(days=1)
    _direto(dados, hora=10)
    login(client, "admin@petmovel.com")
    html = _html(client.get(f"/painel?data={amanha.isoformat()}"))
    assert "Rua A, 10" not in html
    assert "Nenhum atendimento" in html
    assert _card(html, "total") == 0


def test_data_invalida_vira_hoje(client, dados):
    _direto(dados, hora=10)
    login(client, "admin@petmovel.com")
    resposta = client.get("/painel?data=xyz")
    assert resposta.status_code == 200
    assert "Rua A, 10" in _html(resposta)


# --- Máquina de estados pelo painel ----------------------------------------

def test_botoes_contextuais(client, dados):
    _direto(dados)
    login(client, "admin@petmovel.com")
    html = _html(client.get("/painel"))
    assert 'value="confirmar"' in html and 'value="recusar"' in html
    assert 'value="concluir"' not in html
    assert 'value="iniciar_deslocamento"' not in html


def test_concluido_nao_tem_botoes(client, dados):
    _direto(dados, status=CONCLUIDO)
    login(client, "admin@petmovel.com")
    assert 'name="acao"' not in _html(client.get("/painel"))


def test_fluxo_completo_por_post(client, dados):
    ag = _direto(dados)
    login(client, "admin@petmovel.com")
    for acao in ("confirmar", "iniciar_deslocamento", "iniciar_atendimento", "concluir"):
        assert _acao(client, ag, acao).status_code == 302
    db.session.refresh(ag)
    assert ag.status == CONCLUIDO
    assert ag.unidade_movel_id == dados.van
    assert Notificacao.query.filter_by(usuario_id=dados.cliente).count() == 4


@pytest.mark.parametrize("acao", ["concluir", "iniciar_atendimento", "cancelar", "xyz"])
def test_transicao_forjada_nao_altera(client, dados, acao):
    ag = _direto(dados)
    login(client, "admin@petmovel.com")
    resposta = client.post(f"/agendamentos/{ag.id}/acao", data={"acao": acao},
                           follow_redirects=True)
    assert "não permitida" in _avisos(resposta)
    db.session.refresh(ag)
    assert ag.status == PENDENTE


def test_confirmacao_sem_recurso_avisa(client, dados):
    _direto(dados, hora=10, status=CONFIRMADO)
    pendente = _direto(dados, hora=10, status=PENDENTE)
    login(client, "admin@petmovel.com")
    resposta = client.post(f"/agendamentos/{pendente.id}/acao", data={"acao": "confirmar"},
                           follow_redirects=True)
    assert "unidade móvel livre" in _avisos(resposta)
    db.session.refresh(pendente)
    assert pendente.status == PENDENTE


def test_acao_volta_para_o_filtro(client, dados):
    ag = _direto(dados)
    login(client, "admin@petmovel.com")
    resposta = _acao(client, ag, "confirmar", next="/painel?tipo=loja")
    assert resposta.headers["Location"].endswith("/painel?tipo=loja")


def test_formulario_de_acao_carrega_o_filtro_atual(client, dados):
    _direto(dados)
    login(client, "admin@petmovel.com")
    html = _html(client.get(f"/painel?data={HOJE.isoformat()}&tipo=movel"))
    assert f'name="next" value="/painel?data={HOJE.isoformat()}&amp;tipo=movel"' in html

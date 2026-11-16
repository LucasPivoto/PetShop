import re
from datetime import date, datetime, time, timedelta
from urllib.parse import unquote

import pytest

from conftest import login
from models import (
    CANCELADO, CONCLUIDO, CONFIRMADO, PENDENTE, TIPO_LOJA, TIPO_MOVEL,
    Agendamento, AgendamentoServico, Notificacao, db,
)

AMANHA = date.today() + timedelta(days=1)


def _html(resposta):
    return resposta.get_data(as_text=True)


def _avisos(resposta):
    """Texto dos toasts (mensagens flash), sem o restante da página."""
    return " ".join(re.findall(r'data-toast.*?<p class="flex-1">(.*?)</p>',
                               _html(resposta), re.S)).lower()


def _form(dados, **kw):
    form = {
        "pet_id": dados.thor, "servicos": [dados.banho, dados.unhas],
        "tipo": TIPO_MOVEL, "data": AMANHA.isoformat(), "hora": "10:00",
        "bairro": "BPS", "endereco": "Rua A, 10", "forma_pagamento": "PIX",
    }
    form.update(kw)
    return form


def _direto(dados, status=PENDENTE, cliente=None, pet=None, hora=9, tipo=TIPO_LOJA):
    ag = Agendamento(
        cliente_id=cliente or dados.cliente, pet_id=pet or dados.thor,
        data_hora=datetime.combine(AMANHA, time(hora, 0)), tipo_atendimento=tipo,
        status=status, forma_pagamento="PIX", valor_total=75.0)
    if status in (CONFIRMADO, CONCLUIDO):
        ag.posto_fixo_id = dados.baia1
    ag.itens.append(AgendamentoServico(servico_id=dados.banho, preco_aplicado=75.0))
    db.session.add(ag)
    db.session.commit()
    return ag


# --- Acesso ----------------------------------------------------------------

@pytest.mark.parametrize("caminho", ["/agendar", "/meus-agendamentos", "/notificacoes"])
def test_exige_login(client, dados, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302
    assert unquote(resposta.headers["Location"]).endswith(f"/login?next={caminho}")


def test_prestador_nao_agenda(client, dados):
    login(client, "admin@petmovel.com")
    assert client.get("/agendar").status_code == 302
    client.post("/agendar", data=_form(dados))
    assert Agendamento.query.count() == 0


def test_agendar_sem_pets_redireciona(client, app):
    client.post("/cadastro", data={"nome": "Sem Pet", "email": "sempet@teste.com",
                                   "senha": "123456"})
    resposta = client.get("/agendar")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/pets/novo")


def test_tela_agendar_lista_dados(client, dados):
    login(client, "cliente@teste.com")
    html = _html(client.get("/agendar"))
    assert "Thor" in html and "Banho Completo" in html
    assert "Cruzeiro" in html and "fora da área de cobertura" in html
    assert "Luna" not in html
    assert "Rua Coronel Rennó, 120" in html


# --- Criação ---------------------------------------------------------------

def test_agendar_sucesso(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post("/agendar", data=_form(dados))
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/meus-agendamentos")
    ag = Agendamento.query.one()
    assert ag.status == PENDENTE
    assert ag.valor_total == 105.0
    assert ag.cliente_id == dados.cliente
    assert ag.data_hora == datetime.combine(AMANHA, time(10, 0))
    assert (ag.bairro_atendimento, ag.endereco_atendimento) == ("BPS", "Rua A, 10")


def test_agendar_loja(client, dados):
    login(client, "cliente@teste.com")
    client.post("/agendar", data=_form(dados, tipo=TIPO_LOJA, bairro="", endereco=""))
    ag = Agendamento.query.one()
    assert ag.tipo_atendimento == TIPO_LOJA
    assert ag.endereco_atendimento is None


def test_valor_enviado_e_ignorado(client, dados):
    login(client, "cliente@teste.com")
    client.post("/agendar", data=_form(dados, valor_total="1", status="Confirmado",
                                       cliente_id=dados.maria))
    ag = Agendamento.query.one()
    assert ag.valor_total == 105.0
    assert ag.status == PENDENTE
    assert ag.cliente_id == dados.cliente


@pytest.mark.parametrize("kw,trecho", [
    ({"bairro": "Cruzeiro"}, "fora da área de cobertura"),
    ({"bairro": "Bairro Que Não Existe"}, "fora da área de cobertura"),
    ({"servicos": []}, "serviço"),
    ({"servicos": ["9999"]}, "serviço"),
    ({"hora": "10:30"}, "horário"),
    ({"hora": "03:00"}, "horário"),
    ({"hora": ""}, "inválido"),
    ({"hora": "25:99"}, "inválido"),
    ({"data": "2020-01-01"}, "futuros"),
    ({"data": "amanhã"}, "inválido"),
    ({"data": ""}, "inválido"),
    ({"pet_id": "luna"}, "pet"),
    ({"pet_id": ""}, "pet"),
    ({"endereco": ""}, "endereço"),
    ({"forma_pagamento": "Cheque"}, "pagamento"),
    ({"tipo": "TELETRANSPORTE"}, "modalidade"),
])
def test_agendar_invalido(client, dados, kw, trecho):
    if kw.get("pet_id") == "luna":
        kw = {"pet_id": dados.luna}
    login(client, "cliente@teste.com")
    resposta = client.post("/agendar", data=_form(dados, **kw))
    assert resposta.status_code == 400
    assert trecho.lower() in _avisos(resposta)
    assert Agendamento.query.count() == 0


def test_erro_preserva_o_que_foi_preenchido(client, dados):
    login(client, "cliente@teste.com")
    html = _html(client.post("/agendar", data=_form(dados, bairro="Cruzeiro",
                                                    endereco="Travessa Única, 77")))
    assert "Travessa Única, 77" in html


def test_slot_cheio(client, dados):
    login(client, "cliente@teste.com")
    client.post("/agendar", data=_form(dados))
    resposta = client.post("/agendar", data=_form(dados))
    assert resposta.status_code == 400
    assert "disponível nesse horário" in _avisos(resposta)
    assert Agendamento.query.count() == 1


# --- API de horários -------------------------------------------------------

def test_api_horarios(client, dados):
    login(client, "cliente@teste.com")
    url = f"/api/horarios?tipo={TIPO_MOVEL}&data={AMANHA.isoformat()}"
    horarios = client.get(url).get_json()["horarios"]
    assert len(horarios) == 10
    assert all(h["livre"] for h in horarios)
    client.post("/agendar", data=_form(dados))
    livres = {h["hora"]: h["livre"] for h in client.get(url).get_json()["horarios"]}
    assert livres["10:00"] is False
    assert livres["11:00"] is True


def test_api_horarios_sem_login(client, dados):
    resposta = client.get(f"/api/horarios?tipo={TIPO_MOVEL}&data={AMANHA.isoformat()}")
    assert resposta.status_code == 401
    assert "erro" in resposta.get_json()


@pytest.mark.parametrize("qs", [
    "tipo=X&data=2026-03-03", "tipo=DOMICILIO_MOVEL&data=ontem", "tipo=DOMICILIO_MOVEL", "",
])
def test_api_horarios_invalido(client, dados, qs):
    login(client, "cliente@teste.com")
    resposta = client.get(f"/api/horarios?{qs}")
    assert resposta.status_code == 400
    assert "erro" in resposta.get_json()


# --- Meus agendamentos -----------------------------------------------------

def test_abas_ativos_e_historico(client, dados):
    _direto(dados, status=PENDENTE, hora=9)
    _direto(dados, status=CONCLUIDO, hora=11)
    login(client, "cliente@teste.com")
    html = _html(client.get("/meus-agendamentos"))
    assert "Agendamentos Ativos" in html and "Histórico de Atendimentos" in html
    assert "Pendente" in html and "Concluído" in html
    assert html.count('value="cancelar"') == 1


def test_nao_ve_agendamento_alheio(client, dados):
    _direto(dados, cliente=dados.maria, pet=dados.luna)
    login(client, "cliente@teste.com")
    html = _html(client.get("/meus-agendamentos"))
    assert "Luna" not in html
    assert "Nenhum agendamento ativo" in html


@pytest.mark.parametrize("status", [PENDENTE, CONFIRMADO])
def test_cliente_cancela(client, dados, status):
    ag = _direto(dados, status=status)
    login(client, "cliente@teste.com")
    resposta = client.post(f"/agendamentos/{ag.id}/acao", data={"acao": "cancelar"})
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/meus-agendamentos")
    db.session.refresh(ag)
    assert ag.status == CANCELADO


def test_cliente_nao_cancela_alheio(client, dados):
    ag = _direto(dados, cliente=dados.maria, pet=dados.luna)
    login(client, "cliente@teste.com")
    resposta = client.post(f"/agendamentos/{ag.id}/acao", data={"acao": "cancelar"})
    assert resposta.status_code == 404
    db.session.refresh(ag)
    assert ag.status == PENDENTE


def test_acao_em_agendamento_inexistente(client, dados):
    login(client, "cliente@teste.com")
    assert client.post("/agendamentos/9999/acao", data={"acao": "cancelar"}).status_code == 404


def test_acao_exige_login(client, dados):
    ag = _direto(dados)
    assert client.post(f"/agendamentos/{ag.id}/acao", data={"acao": "cancelar"}).status_code == 302
    db.session.refresh(ag)
    assert ag.status == PENDENTE


@pytest.mark.parametrize("acao", ["confirmar", "concluir", "iniciar_atendimento", "", "xyz"])
def test_cliente_nao_forja_transicao(client, dados, acao):
    ag = _direto(dados)
    login(client, "cliente@teste.com")
    resposta = client.post(f"/agendamentos/{ag.id}/acao", data={"acao": acao},
                           follow_redirects=True)
    assert "não permitida" in _avisos(resposta)
    db.session.refresh(ag)
    assert ag.status == PENDENTE


@pytest.mark.parametrize("alvo", ["https://evil.example", "//evil.example"])
def test_next_externo_ignorado(client, dados, alvo):
    ag = _direto(dados)
    login(client, "cliente@teste.com")
    resposta = client.post(f"/agendamentos/{ag.id}/acao", data={"acao": "cancelar", "next": alvo})
    assert resposta.headers["Location"].endswith("/meus-agendamentos")


# --- Notificações ----------------------------------------------------------

def test_sino_e_notificacoes(client, dados):
    login(client, "cliente@teste.com")
    assert "data-nao-lidas" not in _html(client.get("/"))
    client.post("/agendar", data=_form(dados))
    assert 'data-nao-lidas="1"' in _html(client.get("/"))
    assert "solicitação recebida" in _html(client.get("/notificacoes"))

    resposta = client.post("/notificacoes/ler")
    assert resposta.status_code == 302
    assert Notificacao.query.filter_by(usuario_id=dados.cliente, lida=False).count() == 0
    assert "data-nao-lidas" not in _html(client.get("/"))


def test_notificacoes_sao_do_usuario(client, dados):
    db.session.add(Notificacao(usuario_id=dados.maria, mensagem="Recado só da Maria"))
    db.session.commit()
    login(client, "cliente@teste.com")
    assert "Recado só da Maria" not in _html(client.get("/notificacoes"))
    client.post("/notificacoes/ler")
    assert Notificacao.query.filter_by(usuario_id=dados.maria, lida=False).count() == 1

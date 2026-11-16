"""Entradas hostis ou absurdas nunca devem causar erro 500 nem redirecionar para fora.

Achados da revisão final do branch; cada teste reproduz um deles.
"""
import re
from datetime import date, datetime, time, timedelta

import pytest

from app import create_app, destino_seguro
from conftest import AGORA, login
from models import TIPO_MOVEL, Agendamento, Servico, Usuario, db
from services import RegraNegocioError, criar_agendamento

ENORME = "99999999999999999999999"
AMANHA = date.today() + timedelta(days=1)


def _html(resposta):
    return resposta.get_data(as_text=True)


def _avisos(resposta):
    return " ".join(re.findall(r'data-toast.*?<p class="flex-1">(.*?)</p>',
                               _html(resposta), re.S)).lower()


def _form(dados, **kw):
    form = {
        "pet_id": dados.thor, "servicos": [dados.banho], "tipo": TIPO_MOVEL,
        "data": AMANHA.isoformat(), "hora": "10:00", "bairro": "BPS",
        "endereco": "Rua A, 10", "forma_pagamento": "PIX",
    }
    form.update(kw)
    return form


# --- `next` nunca leva a outro site ----------------------------------------

@pytest.mark.parametrize("alvo", [
    "/\t/evil.example", "/\n/evil.example", "/\r/evil.example", "/ /evil.example",
    "\t//evil.example", "/\x00/evil.example", "https://evil.example", "//evil.example",
    "/\\evil.example", "evil.example", "",
])
def test_destino_seguro_recusa(alvo):
    assert destino_seguro(alvo) is None


@pytest.mark.parametrize("alvo", ["/pets", "/painel?data=2026-03-03&tipo=loja", "/agendar"])
def test_destino_seguro_aceita_caminho_local(alvo):
    assert destino_seguro(alvo) == alvo


@pytest.mark.parametrize("alvo", ["/\t/evil.example", "/\n/evil.example", "/\r\n/evil.example"])
def test_login_com_next_de_controle_nao_sai_do_site(client, dados, alvo):
    resposta = client.post("/login", query_string={"next": alvo},
                           data={"email": "cliente@teste.com", "senha": "123456"})
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/meus-agendamentos")


# --- Inteiros gigantes -----------------------------------------------------

def test_id_gigante_na_url_e_404(client, dados):
    login(client, "cliente@teste.com")
    assert client.get(f"/pets/{ENORME}/editar").status_code == 404
    assert client.post(f"/pets/{ENORME}/excluir").status_code == 404
    assert client.post(f"/agendamentos/{ENORME}/acao", data={"acao": "cancelar"}).status_code == 404


def test_id_gigante_na_gestao_e_404(client, dados):
    login(client, "admin@petmovel.com")
    for acao in ("editar", "alternar", "excluir"):
        assert client.post(f"/gestao/postos/{ENORME}/{acao}").status_code == 404


@pytest.mark.parametrize("kw,trecho", [
    ({"pet_id": ENORME}, "pet"), ({"servicos": [ENORME]}, "serviço"),
    ({"pet_id": "-1"}, "pet"), ({"servicos": ["-5"]}, "serviço"),
])
def test_agendar_com_id_gigante_e_erro_de_formulario(client, dados, kw, trecho):
    login(client, "cliente@teste.com")
    resposta = client.post("/agendar", data=_form(dados, **kw))
    assert resposta.status_code == 400
    assert trecho in _avisos(resposta)
    assert Agendamento.query.count() == 0


@pytest.mark.parametrize("duracao", [ENORME, "1441"])
def test_gestao_recusa_duracao_absurda(client, dados, duracao):
    login(client, "admin@petmovel.com")
    resposta = client.post("/gestao/servicos/novo", follow_redirects=True, data={
        "nome_servico": "Spa", "descricao": "Dia de spa", "preco_base": "90",
        "duracao_minutos": duracao})
    assert resposta.status_code == 200
    assert "duração" in _avisos(resposta)
    assert Servico.query.count() == 2


@pytest.mark.parametrize("preco", ["0,004", "0.001", "1e400", "1000000"])
def test_gestao_recusa_preco_que_vira_zero_ou_absurdo(client, dados, preco):
    login(client, "admin@petmovel.com")
    resposta = client.post("/gestao/servicos/novo", follow_redirects=True, data={
        "nome_servico": "Spa", "descricao": "Dia de spa", "preco_base": preco,
        "duracao_minutos": "30"})
    assert "preço" in _avisos(resposta)
    assert Servico.query.count() == 2


# --- Datas extremas --------------------------------------------------------

@pytest.mark.parametrize("data", ["9999-12-31", "0001-01-01", "1999-12-31", "2101-01-01"])
def test_painel_com_data_extrema_abre_hoje(client, dados, data):
    login(client, "admin@petmovel.com")
    resposta = client.get(f"/painel?data={data}")
    assert resposta.status_code == 200
    assert date.today().strftime("%d/%m/%Y") in _html(resposta)


@pytest.mark.parametrize("data", ["9999-12-31", "0001-01-01"])
def test_api_horarios_com_data_extrema_nao_quebra(client, dados, data):
    login(client, "cliente@teste.com")
    assert client.get(f"/api/horarios?tipo={TIPO_MOVEL}&data={data}").status_code == 200


def test_nao_agenda_com_mais_de_um_ano_de_antecedencia(app, dados):
    cliente = db.session.get(Usuario, dados.cliente)
    longe = datetime.combine(AGORA.date() + timedelta(days=366), time(10, 0))
    with pytest.raises(RegraNegocioError, match="antecedência"):
        criar_agendamento(cliente, dados.thor, [dados.banho], TIPO_MOVEL, longe, "PIX",
                          bairro="BPS", endereco="Rua A, 10", agora=AGORA)
    assert Agendamento.query.count() == 0


def test_agenda_dentro_de_um_ano(app, dados):
    cliente = db.session.get(Usuario, dados.cliente)
    limite = datetime.combine(AGORA.date() + timedelta(days=365), time(10, 0))
    ag = criar_agendamento(cliente, dados.thor, [dados.banho], TIPO_MOVEL, limite, "PIX",
                           bairro="BPS", endereco="Rua A, 10", agora=AGORA)
    assert ag.id is not None


def test_agendar_no_ano_9999_e_erro_de_formulario(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post("/agendar", data=_form(dados, data="9999-12-31"))
    assert resposta.status_code == 400
    assert "antecedência" in _avisos(resposta)
    assert Agendamento.query.count() == 0


def test_tela_de_agendar_limita_a_data_no_navegador(client, dados):
    login(client, "cliente@teste.com")
    limite = (date.today() + timedelta(days=365)).isoformat()
    assert f'max="{limite}"' in _html(client.get("/agendar"))


# --- CSRF ------------------------------------------------------------------

@pytest.mark.parametrize("token", ["é", "ção" * 10, "☃"])
def test_token_csrf_nao_ascii_e_400(tmp_path, token):
    aplicacao = create_app({
        "TESTING": True, "SEED_ON_START": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/csrf.db",
    })
    cliente_http = aplicacao.test_client()
    cliente_http.get("/login")  # cria o token na sessão
    resposta = cliente_http.post("/login", data={
        "email": "x@x.com", "senha": "123456", "_csrf": token})
    assert resposta.status_code == 400

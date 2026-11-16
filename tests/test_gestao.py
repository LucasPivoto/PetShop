import re
from datetime import date, datetime, time, timedelta

import pytest

from conftest import login
from models import (
    CONFIRMADO, TIPO_LOJA, TIPO_MOVEL, Agendamento, AgendamentoServico,
    BairroCobertura, PostoFixo, Servico, UnidadeMovel, db,
)
from services import bairro_coberto, capacidade, horarios_disponiveis

AMANHA = date.today() + timedelta(days=1)
SERVICO = {"nome_servico": "Escovação Dental", "descricao": "Limpeza dos dentes",
           "preco_base": "30,00", "duracao_minutos": "20"}


def _html(resposta):
    return resposta.get_data(as_text=True)


def _avisos(resposta):
    return " ".join(re.findall(r'data-toast.*?<p class="flex-1">(.*?)</p>',
                               _html(resposta), re.S)).lower()


def _usar_recursos(dados):
    """Um agendamento confirmado que usa o serviço banho e a van."""
    ag = Agendamento(
        cliente_id=dados.cliente, pet_id=dados.thor,
        data_hora=datetime.combine(AMANHA, time(10, 0)), tipo_atendimento=TIPO_MOVEL,
        status=CONFIRMADO, forma_pagamento="PIX", valor_total=75.0,
        unidade_movel_id=dados.van, bairro_atendimento="BPS", endereco_atendimento="Rua A")
    ag.itens.append(AgendamentoServico(servico_id=dados.banho, preco_aplicado=75.0))
    db.session.add(ag)
    db.session.commit()


@pytest.fixture
def admin(client, dados):
    login(client, "admin@petmovel.com")
    return client


# --- Acesso ----------------------------------------------------------------

def test_gestao_exige_prestador(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.get("/gestao")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    client.post("/gestao/servicos/novo", data=SERVICO)
    client.post(f"/gestao/bairros/{dados.cruzeiro}/alternar")
    client.post(f"/gestao/servicos/{dados.unhas}/excluir")
    assert Servico.query.count() == 2
    assert db.session.get(BairroCobertura, dados.cruzeiro).ativo is False


def test_gestao_exige_login(client, dados):
    assert client.get("/gestao").status_code == 302
    client.post("/gestao/servicos/novo", data=SERVICO)
    assert Servico.query.count() == 2


@pytest.mark.parametrize("aba,trecho", [
    ("servicos", "Banho Completo"), ("bairros", "Cruzeiro"),
    ("unidades", "ABC-1D23"), ("postos", "Baia 02 - Loja Física"),
])
def test_abas_renderizam(admin, aba, trecho):
    resposta = admin.get(f"/gestao?aba={aba}")
    assert resposta.status_code == 200
    assert trecho in _html(resposta)


def test_aba_padrao_e_servicos(admin):
    assert "Banho Completo" in _html(admin.get("/gestao"))
    assert "Banho Completo" in _html(admin.get("/gestao?aba=inexistente"))


@pytest.mark.parametrize("caminho", [
    "/gestao/usuarios/novo", "/gestao/usuarios/1/editar", "/gestao/usuarios/1/excluir",
    "/gestao/servicos/9999/editar", "/gestao/bairros/9999/alternar",
    "/gestao/postos/9999/excluir",
])
def test_recurso_ou_id_desconhecido(admin, caminho):
    assert admin.post(caminho, data=SERVICO).status_code == 404


# --- Serviços --------------------------------------------------------------

def test_cria_servico_aparece_na_home(admin):
    resposta = admin.post("/gestao/servicos/novo", data=SERVICO)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/gestao?aba=servicos")
    servico = Servico.query.filter_by(nome_servico="Escovação Dental").one()
    assert (servico.preco_base, servico.duracao_minutos) == (30.0, 20)
    html = _html(admin.get("/"))
    assert "Escovação Dental" in html and "R$ 30,00" in html


@pytest.mark.parametrize("campo,valor", [
    ("preco_base", "0"), ("preco_base", "-5"), ("preco_base", "abc"), ("preco_base", ""),
    ("preco_base", "nan"), ("preco_base", "inf"),
    ("duracao_minutos", "0"), ("duracao_minutos", "x"), ("duracao_minutos", "12.5"),
    ("nome_servico", "   "), ("descricao", ""),
])
def test_servico_invalido(admin, campo, valor):
    resposta = admin.post("/gestao/servicos/novo", data={**SERVICO, campo: valor},
                          follow_redirects=True)
    assert _avisos(resposta)
    assert Servico.query.count() == 2


def test_preco_com_virgula(admin):
    admin.post("/gestao/servicos/novo", data={**SERVICO, "preco_base": "45,50"})
    assert Servico.query.filter_by(nome_servico="Escovação Dental").one().preco_base == 45.5


def test_edita_servico(admin, dados):
    admin.post(f"/gestao/servicos/{dados.banho}/editar", data={
        "nome_servico": "Banho Completo", "descricao": "Banho", "preco_base": "55",
        "duracao_minutos": "50"})
    banho = db.session.get(Servico, dados.banho)
    assert (banho.preco_base, banho.duracao_minutos) == (55.0, 50)


def test_edicao_invalida_nao_altera(admin, dados):
    admin.post(f"/gestao/servicos/{dados.banho}/editar", data={
        "nome_servico": "Outro nome", "descricao": "Banho", "preco_base": "-1",
        "duracao_minutos": "50"})
    db.session.expire_all()
    banho = db.session.get(Servico, dados.banho)
    assert (banho.nome_servico, banho.preco_base) == ("Banho Completo", 50.0)


def test_exclui_servico_sem_uso(admin, dados):
    admin.post(f"/gestao/servicos/{dados.unhas}/excluir")
    assert db.session.get(Servico, dados.unhas) is None


def test_nao_exclui_servico_em_uso(admin, dados):
    _usar_recursos(dados)
    resposta = admin.post(f"/gestao/servicos/{dados.banho}/excluir", follow_redirects=True)
    assert "agendamentos" in _avisos(resposta)
    assert db.session.get(Servico, dados.banho) is not None


def test_alternar_servico_404(admin, dados):
    assert admin.post(f"/gestao/servicos/{dados.banho}/alternar").status_code == 404


def test_excluir_exige_post(admin, dados):
    assert admin.get(f"/gestao/servicos/{dados.unhas}/excluir").status_code == 405
    assert db.session.get(Servico, dados.unhas) is not None


# --- Bairros ---------------------------------------------------------------

def test_ativar_bairro_libera_cobertura(admin, dados):
    assert not bairro_coberto("Cruzeiro")
    resposta = admin.post(f"/gestao/bairros/{dados.cruzeiro}/alternar")
    assert resposta.headers["Location"].endswith("/gestao?aba=bairros")
    assert bairro_coberto("Cruzeiro")
    assert "Cruzeiro" in _html(admin.get("/"))
    admin.post(f"/gestao/bairros/{dados.cruzeiro}/alternar")
    assert not bairro_coberto("Cruzeiro")


def test_cria_bairro_ativo(admin):
    admin.post("/gestao/bairros/novo", data={"nome_bairro": " Medicina "})
    bairro = BairroCobertura.query.filter_by(nome_bairro="Medicina").one()
    assert bairro.ativo is True


@pytest.mark.parametrize("nome", ["centro", "  CENTRO ", "Cruzeiro"])
def test_bairro_duplicado(admin, nome):
    resposta = admin.post("/gestao/bairros/novo", data={"nome_bairro": nome},
                          follow_redirects=True)
    assert "já existe" in _avisos(resposta)
    assert BairroCobertura.query.count() == 3


def test_renomear_bairro_para_o_proprio_nome(admin, dados):
    admin.post(f"/gestao/bairros/{dados.centro}/editar", data={"nome_bairro": "CENTRO"})
    assert db.session.get(BairroCobertura, dados.centro).nome_bairro == "CENTRO"


def test_exclui_bairro(admin, dados):
    admin.post(f"/gestao/bairros/{dados.cruzeiro}/excluir")
    assert db.session.get(BairroCobertura, dados.cruzeiro) is None


# --- Unidades móveis e postos fixos ----------------------------------------

def test_desativar_van_fecha_horarios(admin, dados):
    admin.post(f"/gestao/unidades/{dados.van}/alternar")
    assert db.session.get(UnidadeMovel, dados.van).ativo is False
    assert not any(h["livre"] for h in horarios_disponiveis(TIPO_MOVEL, AMANHA))


def test_cria_unidade(admin):
    admin.post("/gestao/unidades/novo", data={
        "modelo": "Van PetMóvel 02", "placa": "XYZ-9K88", "profissional_responsavel": "Lia"})
    assert capacidade(TIPO_MOVEL) == 2


def test_unidade_incompleta(admin):
    admin.post("/gestao/unidades/novo", data={"modelo": "Van 02", "placa": ""})
    assert UnidadeMovel.query.count() == 1


def test_cria_e_alterna_posto(admin):
    admin.post("/gestao/postos/novo", data={
        "identificacao_mesa": "Baia 03", "responsavel_setor": "Rita"})
    novo = PostoFixo.query.filter_by(identificacao_mesa="Baia 03").one()
    assert novo.ativo is True
    assert capacidade(TIPO_LOJA) == 3
    admin.post(f"/gestao/postos/{novo.id}/alternar")
    assert capacidade(TIPO_LOJA) == 2


def test_nao_exclui_van_em_uso(admin, dados):
    _usar_recursos(dados)
    resposta = admin.post(f"/gestao/unidades/{dados.van}/excluir", follow_redirects=True)
    assert "agendamentos" in _avisos(resposta)
    assert db.session.get(UnidadeMovel, dados.van) is not None


def test_exclui_posto_sem_uso(admin, dados):
    admin.post(f"/gestao/postos/{dados.baia2}/excluir")
    assert db.session.get(PostoFixo, dados.baia2) is None

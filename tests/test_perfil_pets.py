from datetime import datetime
from urllib.parse import unquote

import pytest

from conftest import login
from models import (
    CONCLUIDO, TIPO_LOJA, Agendamento, Pet, Usuario, db,
)

PET = {"nome": "Rex", "especie": "Cão", "porte": "Medio", "restricoes_medicas": "Medo de secador"}


def _html(resposta):
    return resposta.get_data(as_text=True)


def _agendar_direto(dados, pet_id, cliente_id):
    db.session.add(Agendamento(
        cliente_id=cliente_id, pet_id=pet_id, data_hora=datetime(2026, 3, 3, 10, 0),
        tipo_atendimento=TIPO_LOJA, status=CONCLUIDO, forma_pagamento="PIX", valor_total=75.0))
    db.session.commit()


# --- Acesso ----------------------------------------------------------------

@pytest.mark.parametrize("caminho", ["/pets", "/pets/novo", "/perfil"])
def test_area_do_cliente_exige_login(client, dados, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302
    assert unquote(resposta.headers["Location"]).endswith(f"/login?next={caminho}")


def test_prestador_nao_acessa_pets(client, dados):
    login(client, "admin@petmovel.com")
    resposta = client.get("/pets")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/")
    client.post("/pets/novo", data=PET)
    assert Pet.query.count() == 2


# --- Pets ------------------------------------------------------------------

def test_lista_so_os_proprios(client, dados):
    login(client, "cliente@teste.com")
    html = _html(client.get("/pets"))
    assert "Thor" in html
    assert "Alergia a shampoo perfumado" in html
    assert "Luna" not in html


def test_cria_pet(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post("/pets/novo", data=PET)
    assert resposta.status_code == 302
    pet = Pet.query.filter_by(nome="Rex").one()
    assert pet.cliente_id == dados.cliente
    assert (pet.especie, pet.porte, pet.restricoes_medicas) == ("Cão", "Medio", "Medo de secador")


def test_restricao_vazia_vira_nulo(client, dados):
    login(client, "cliente@teste.com")
    client.post("/pets/novo", data={**PET, "restricoes_medicas": "   "})
    assert Pet.query.filter_by(nome="Rex").one().restricoes_medicas is None


@pytest.mark.parametrize("campo,valor", [
    ("nome", ""), ("nome", "   "), ("especie", "Peixe"), ("porte", "Gigante"), ("porte", ""),
])
def test_pet_invalido(client, dados, campo, valor):
    login(client, "cliente@teste.com")
    resposta = client.post("/pets/novo", data={**PET, campo: valor})
    assert resposta.status_code == 400
    assert Pet.query.count() == 2


def test_edita_pet(client, dados):
    login(client, "cliente@teste.com")
    assert "Thor" in _html(client.get(f"/pets/{dados.thor}/editar"))
    resposta = client.post(f"/pets/{dados.thor}/editar", data={
        "nome": "Thor", "especie": "Cão", "porte": "Medio", "restricoes_medicas": ""})
    assert resposta.status_code == 302
    thor = db.session.get(Pet, dados.thor)
    assert thor.porte == "Medio"
    assert thor.restricoes_medicas is None


def test_edicao_invalida_nao_altera(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post(f"/pets/{dados.thor}/editar", data={**PET, "porte": "Gigante"})
    assert resposta.status_code == 400
    db.session.expire_all()
    thor = db.session.get(Pet, dados.thor)
    assert (thor.nome, thor.porte) == ("Thor", "Grande")


def test_nao_edita_pet_alheio(client, dados):
    login(client, "cliente@teste.com")
    assert client.get(f"/pets/{dados.luna}/editar").status_code == 404
    assert client.post(f"/pets/{dados.luna}/editar", data=PET).status_code == 404
    assert db.session.get(Pet, dados.luna).nome == "Luna"


def test_pet_inexistente(client, dados):
    login(client, "cliente@teste.com")
    assert client.get("/pets/9999/editar").status_code == 404
    assert client.post("/pets/9999/excluir").status_code == 404


def test_nao_exclui_pet_alheio(client, dados):
    login(client, "cliente@teste.com")
    assert client.post(f"/pets/{dados.luna}/excluir").status_code == 404
    assert db.session.get(Pet, dados.luna) is not None


def test_exclui_pet_sem_agendamento(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post(f"/pets/{dados.thor}/excluir")
    assert resposta.status_code == 302
    assert db.session.get(Pet, dados.thor) is None


def test_excluir_exige_post(client, dados):
    login(client, "cliente@teste.com")
    assert client.get(f"/pets/{dados.thor}/excluir").status_code == 405
    assert db.session.get(Pet, dados.thor) is not None


def test_nao_exclui_pet_com_agendamento(client, dados):
    _agendar_direto(dados, dados.thor, dados.cliente)
    login(client, "cliente@teste.com")
    resposta = client.post(f"/pets/{dados.thor}/excluir", follow_redirects=True)
    assert "possui agendamentos" in _html(resposta)
    assert db.session.get(Pet, dados.thor) is not None


def test_lista_mostra_atendimentos_concluidos(client, dados):
    _agendar_direto(dados, dados.thor, dados.cliente)
    login(client, "cliente@teste.com")
    assert "1 atendimento concluído" in _html(client.get("/pets"))


# --- Perfil ----------------------------------------------------------------

def test_edita_perfil(client, dados):
    login(client, "cliente@teste.com")
    assert "cliente@teste.com" in _html(client.get("/perfil"))
    resposta = client.post("/perfil", data={
        "nome": "Carlos Silva", "telefone": "(35) 91111-2222",
        "endereco_completo": "Rua Nova, 5", "bairro": "Varginha",
        "email": "hacker@evil.example", "perfil": "PRESTADOR",
    })
    assert resposta.status_code == 302
    usuario = db.session.get(Usuario, dados.cliente)
    assert (usuario.nome, usuario.telefone, usuario.bairro) == (
        "Carlos Silva", "(35) 91111-2222", "Varginha")
    assert usuario.endereco_completo == "Rua Nova, 5"
    assert usuario.email == "cliente@teste.com"
    assert usuario.perfil == "CLIENTE"


def test_perfil_nome_obrigatorio(client, dados):
    login(client, "cliente@teste.com")
    resposta = client.post("/perfil", data={"nome": "  ", "telefone": "", "bairro": ""})
    assert resposta.status_code == 400
    assert db.session.get(Usuario, dados.cliente).nome == "Carlos Cliente"

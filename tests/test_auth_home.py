import re

import pytest

from app import create_app
from conftest import login
from models import PERFIL_CLIENTE, Usuario, db

CADASTRO = {
    "nome": "Nova Tutora", "email": "nova@teste.com", "senha": "segredo1",
    "telefone": "(35) 98888-7777", "endereco_completo": "Rua B, 20", "bairro": "Centro",
}


def _html(resposta):
    return resposta.get_data(as_text=True)


# --- Home ------------------------------------------------------------------

def test_home_publica(client, dados):
    resposta = client.get("/")
    html = _html(resposta)
    assert resposta.status_code == 200
    assert "PetMóvel Itajubá" in html
    assert "Banho Completo" in html and "Corte de Unhas" in html
    assert "Centro" in html and "BPS" in html
    assert "Cruzeiro" not in html


def test_home_mostra_preco_e_duracao(client, dados):
    html = _html(client.get("/"))
    assert "R$ 50,00" in html
    assert "45 min" in html


def test_navbar_por_perfil(client, dados):
    assert "Entrar" in _html(client.get("/"))
    login(client, "cliente@teste.com")
    html = _html(client.get("/"))
    assert "Meus Pets" in html and "Entrar" not in html
    client.post("/logout")
    login(client, "admin@petmovel.com")
    html = _html(client.get("/"))
    assert "Painel" in html and "Meus Pets" not in html


# --- Cadastro --------------------------------------------------------------

def test_cadastro_cria_cliente_e_loga(client, app):
    resposta = client.post("/cadastro", data=CADASTRO)
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/pets")
    usuario = Usuario.query.filter_by(email="nova@teste.com").one()
    assert usuario.perfil == PERFIL_CLIENTE
    assert usuario.check_senha("segredo1")
    assert usuario.bairro == "Centro"
    with client.session_transaction() as sessao:
        assert sessao["usuario_id"] == usuario.id


def test_cadastro_ignora_perfil_prestador(client, app):
    client.post("/cadastro", data={**CADASTRO, "perfil": "PRESTADOR"})
    assert Usuario.query.filter_by(email="nova@teste.com").one().perfil == PERFIL_CLIENTE


def test_cadastro_normaliza_email(client, app):
    client.post("/cadastro", data={**CADASTRO, "email": "  Nova@Teste.COM "})
    assert Usuario.query.one().email == "nova@teste.com"


def test_cadastro_email_duplicado(client, dados):
    resposta = client.post("/cadastro", data={**CADASTRO, "email": "CLIENTE@teste.com"})
    assert resposta.status_code == 400
    assert "já está cadastrado" in _html(resposta)
    assert Usuario.query.count() == 3


def test_cadastro_senha_curta(client, app):
    resposta = client.post("/cadastro", data={**CADASTRO, "senha": "123"})
    assert resposta.status_code == 400
    assert Usuario.query.count() == 0


@pytest.mark.parametrize("campo", ["nome", "email"])
def test_cadastro_campos_obrigatorios(client, app, campo):
    resposta = client.post("/cadastro", data={**CADASTRO, campo: "   "})
    assert resposta.status_code == 400
    assert Usuario.query.count() == 0


def test_cadastro_email_sem_arroba(client, app):
    resposta = client.post("/cadastro", data={**CADASTRO, "email": "invalido"})
    assert resposta.status_code == 400
    assert Usuario.query.count() == 0


# --- Login -----------------------------------------------------------------

def test_login_cliente(client, dados):
    resposta = login(client, "cliente@teste.com")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/meus-agendamentos")


def test_login_prestador(client, dados):
    resposta = login(client, "admin@petmovel.com")
    assert resposta.headers["Location"].endswith("/painel")


def test_login_email_maiusculo(client, dados):
    assert login(client, " Cliente@Teste.com ").status_code == 302


@pytest.mark.parametrize("email,senha", [
    ("cliente@teste.com", "errada"), ("ninguem@teste.com", "123456"), ("", ""),
])
def test_login_invalido(client, dados, email, senha):
    resposta = login(client, email, senha)
    assert resposta.status_code == 200
    assert "E-mail ou senha inválidos" in _html(resposta)
    with client.session_transaction() as sessao:
        assert "usuario_id" not in sessao


def test_login_next_local(client, dados):
    resposta = client.post("/login?next=/pets",
                           data={"email": "cliente@teste.com", "senha": "123456"})
    assert resposta.headers["Location"].endswith("/pets")


@pytest.mark.parametrize("alvo", ["https://evil.example", "//evil.example", "/\\evil.example"])
def test_login_next_externo_ignorado(client, dados, alvo):
    resposta = client.post("/login", query_string={"next": alvo},
                           data={"email": "cliente@teste.com", "senha": "123456"})
    assert resposta.headers["Location"].endswith("/meus-agendamentos")
    assert "evil" not in resposta.headers["Location"]


def test_logout(client, dados):
    login(client, "cliente@teste.com")
    assert client.get("/logout").status_code == 405
    resposta = client.post("/logout")
    assert resposta.status_code == 302
    with client.session_transaction() as sessao:
        assert "usuario_id" not in sessao


def test_usuario_removido_perde_sessao(client, dados):
    login(client, "admin@petmovel.com")
    db.session.delete(db.session.get(Usuario, dados.prestador))
    db.session.commit()
    assert "Entrar" in _html(client.get("/"))


# --- CSRF ------------------------------------------------------------------

def test_csrf_exigido(tmp_path):
    aplicacao = create_app({
        "TESTING": True, "SEED_ON_START": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/csrf.db",
    })
    cliente_http = aplicacao.test_client()
    credenciais = {"email": "x@x.com", "senha": "123456"}

    assert cliente_http.post("/login", data=credenciais).status_code == 400

    pagina = _html(cliente_http.get("/login"))
    token = re.search(r'name="_csrf" value="([^"]+)"', pagina).group(1)
    assert cliente_http.post("/login", data={**credenciais, "_csrf": "errado"}).status_code == 400
    assert cliente_http.post("/login", data={**credenciais, "_csrf": token}).status_code == 200

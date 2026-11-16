from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app import create_app
from models import (
    PERFIL_CLIENTE, PERFIL_PRESTADOR, BairroCobertura, Pet, PostoFixo,
    Servico, UnidadeMovel, Usuario, db,
)

# Relógio fixo para os testes das regras de negócio.
AGORA = datetime(2026, 3, 2, 7, 0)
DIA = date(2026, 3, 3)


@pytest.fixture
def app(tmp_path):
    aplicacao = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db",
        "SEED_ON_START": False,
        "CSRF_ENABLED": False,
    })
    with aplicacao.app_context():
        yield aplicacao
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def _usuario(nome, email, perfil, bairro=None, endereco=None):
    u = Usuario(nome=nome, email=email, perfil=perfil, telefone="(35) 99999-0000",
                bairro=bairro, endereco_completo=endereco)
    u.set_senha("123456")
    db.session.add(u)
    return u


@pytest.fixture
def dados(app):
    cliente = _usuario("Carlos Cliente", "cliente@teste.com", PERFIL_CLIENTE,
                       "BPS", "Rua Coronel Rennó, 120")
    maria = _usuario("Maria Souza", "maria@teste.com", PERFIL_CLIENTE,
                     "Centro", "Praça Theodomiro Santiago, 45")
    prestador = _usuario("Equipe PetMóvel", "admin@petmovel.com", PERFIL_PRESTADOR)
    db.session.flush()

    thor = Pet(cliente_id=cliente.id, nome="Thor", especie="Cão", porte="Grande",
               restricoes_medicas="Alergia a shampoo perfumado")
    luna = Pet(cliente_id=maria.id, nome="Luna", especie="Gato", porte="Pequeno")
    banho = Servico(nome_servico="Banho Completo", descricao="Banho", preco_base=50.0,
                    duracao_minutos=45)
    unhas = Servico(nome_servico="Corte de Unhas", descricao="Unhas", preco_base=20.0,
                    duracao_minutos=15)
    centro = BairroCobertura(nome_bairro="Centro", ativo=True)
    bps = BairroCobertura(nome_bairro="BPS", ativo=True)
    cruzeiro = BairroCobertura(nome_bairro="Cruzeiro", ativo=False)
    van = UnidadeMovel(modelo="Van PetMóvel 01", placa="ABC-1D23",
                       profissional_responsavel="João Ferreira", ativo=True)
    baia1 = PostoFixo(identificacao_mesa="Baia 01 - Loja Física",
                      responsavel_setor="Ana Lima", ativo=True)
    baia2 = PostoFixo(identificacao_mesa="Baia 02 - Loja Física",
                      responsavel_setor="Pedro Santos", ativo=True)
    db.session.add_all([thor, luna, banho, unhas, centro, bps, cruzeiro, van, baia1, baia2])
    db.session.commit()

    return SimpleNamespace(
        cliente=cliente.id, maria=maria.id, prestador=prestador.id,
        thor=thor.id, luna=luna.id, banho=banho.id, unhas=unhas.id,
        centro=centro.id, bps=bps.id, cruzeiro=cruzeiro.id,
        van=van.id, baia1=baia1.id, baia2=baia2.id,
    )


def login(client, email, senha="123456"):
    return client.post("/login", data={"email": email, "senha": senha})

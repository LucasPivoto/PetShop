import os

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from models import PERFIL_CLIENTE, Pet, Usuario, db


def test_tabelas_criadas(app):
    nomes = set(db.inspect(db.engine).get_table_names())
    assert {
        "usuario", "pet", "servico", "bairro_cobertura", "unidade_movel",
        "posto_fixo", "agendamento", "agendamento_servico", "notificacao",
    } <= nomes


def test_senha_e_hash(app):
    u = Usuario(nome="A", email="a@a.com", perfil=PERFIL_CLIENTE)
    u.set_senha("123456")
    assert u.senha_hash != "123456"
    assert u.check_senha("123456")
    assert not u.check_senha("errada")


def test_email_unico(app, dados):
    repetido = Usuario(nome="Outro", email="cliente@teste.com", perfil=PERFIL_CLIENTE)
    repetido.set_senha("123456")
    db.session.add(repetido)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_banco_padrao_na_raiz_do_projeto(monkeypatch):
    import app as modulo_app

    criados = []
    monkeypatch.setattr(db, "create_all", lambda *a, **k: criados.append(True))
    aplicacao = create_app({"SEED_ON_START": False})
    uri = aplicacao.config["SQLALCHEMY_DATABASE_URI"]
    raiz = os.path.dirname(os.path.abspath(modulo_app.__file__))
    assert uri == "sqlite:///" + os.path.join(raiz, "petshop.db")
    assert "instance" not in uri


def test_fixture_dados(app, dados):
    assert db.session.get(Pet, dados.thor).cliente_id == dados.cliente
    assert Usuario.query.count() == 3

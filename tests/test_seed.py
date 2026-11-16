from datetime import date, datetime

import seed
from app import create_app
from models import (
    CONCLUIDO, CONFIRMADO, EM_ATENDIMENTO, PENDENTE, PERFIL_CLIENTE,
    PERFIL_PRESTADOR, Agendamento, BairroCobertura, Notificacao, Pet, PostoFixo,
    Servico, UnidadeMovel, Usuario, db,
)
from services import calcular_total


def test_seed_contagens(app):
    seed.popular()
    assert Usuario.query.count() == 3
    assert Pet.query.count() == 3
    assert Servico.query.count() == 5
    assert BairroCobertura.query.count() == 6
    assert UnidadeMovel.query.count() == 1
    assert PostoFixo.query.count() == 2
    assert Agendamento.query.count() == 4
    assert {a.status for a in Agendamento.query} == {
        PENDENTE, CONFIRMADO, EM_ATENDIMENTO, CONCLUIDO}


def test_seed_credenciais(app):
    seed.popular()
    esperado = {
        "admin@petmovel.com": (PERFIL_PRESTADOR, None),
        "cliente@teste.com": (PERFIL_CLIENTE, "BPS"),
        "maria@teste.com": (PERFIL_CLIENTE, "Centro"),
    }
    for email, (perfil, bairro) in esperado.items():
        u = Usuario.query.filter_by(email=email).one()
        assert u.check_senha("123456")
        assert u.perfil == perfil
        assert u.bairro == bairro
    assert "Itajubá" in Usuario.query.filter_by(email="cliente@teste.com").one().endereco_completo


def test_seed_pets(app):
    seed.popular()
    pets = {(p.nome, p.especie, p.porte, p.restricoes_medicas) for p in Pet.query}
    assert pets == {
        ("Thor", "Cão", "Grande", "Alergia a shampoo perfumado"),
        ("Luna", "Gato", "Pequeno", None),
        ("Bob", "Cão", "Medio", None),
    }


def test_seed_servicos(app):
    seed.popular()
    servicos = {(s.nome_servico, s.preco_base, s.duracao_minutos) for s in Servico.query}
    assert servicos == {
        ("Banho Completo", 50.0, 45), ("Tosa Higiênica", 35.0, 30),
        ("Tosa Completa", 70.0, 60), ("Corte de Unhas", 20.0, 15),
        ("Hidratação de Pelos", 40.0, 30),
    }
    assert all(s.descricao for s in Servico.query)


def test_seed_cruzeiro_inativo(app):
    seed.popular()
    ativos = {b.nome_bairro for b in BairroCobertura.query.filter_by(ativo=True)}
    inativos = {b.nome_bairro for b in BairroCobertura.query.filter_by(ativo=False)}
    assert ativos == {"Centro", "BPS", "Pinheirinho", "Varginha", "Morro Chic"}
    assert inativos == {"Cruzeiro"}


def test_seed_recursos(app):
    seed.popular()
    van = UnidadeMovel.query.one()
    assert (van.modelo, van.placa, van.ativo) == ("Van PetMóvel 01", "ABC-1D23", True)
    assert {p.identificacao_mesa for p in PostoFixo.query} == {
        "Baia 01 - Loja Física", "Baia 02 - Loja Física"}


def test_seed_totais_coerentes(app):
    seed.popular()
    totais = set()
    for ag in Agendamento.query:
        soma = round(sum(i.preco_aplicado for i in ag.itens), 2)
        assert ag.valor_total == soma
        assert ag.valor_total == calcular_total([i.servico for i in ag.itens], ag.pet.porte)
        assert ag.cliente_id == ag.pet.cliente_id
        totais.add((ag.status, ag.valor_total))
    assert totais == {(PENDENTE, 105.0), (CONFIRMADO, 43.75),
                      (EM_ATENDIMENTO, 90.0), (CONCLUIDO, 105.0)}


def test_seed_recursos_alocados(app):
    seed.popular()
    por_status = {a.status: a for a in Agendamento.query}
    assert por_status[PENDENTE].unidade_movel_id is None
    assert por_status[PENDENTE].posto_fixo_id is None
    assert por_status[CONFIRMADO].posto_fixo_id is not None
    assert por_status[EM_ATENDIMENTO].unidade_movel_id is not None
    assert por_status[CONCLUIDO].posto_fixo_id is not None
    assert por_status[PENDENTE].bairro_atendimento == "BPS"
    assert por_status[EM_ATENDIMENTO].bairro_atendimento == "Centro"


def test_seed_datas_relativas(app):
    seed.popular(agora=datetime(2026, 3, 2, 9, 0))
    dias = sorted(a.data_hora.date() for a in Agendamento.query)
    assert dias == [date(2026, 3, 1)] + [date(2026, 3, 2)] * 3


def test_seed_notificacoes(app):
    seed.popular()
    assert Notificacao.query.count() == 4
    assert Notificacao.query.filter_by(lida=False).count() == 4
    for ag in Agendamento.query:
        assert Notificacao.query.filter(
            Notificacao.usuario_id == ag.cliente_id,
            Notificacao.mensagem.contains(ag.status),
        ).count() >= 1


def test_popular_se_vazio_idempotente(app):
    assert seed.popular_se_vazio() is True
    assert seed.popular_se_vazio() is False
    assert Usuario.query.count() == 3
    assert Agendamento.query.count() == 4


def test_create_app_popula(tmp_path):
    aplicacao = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/novo.db",
    })
    with aplicacao.app_context():
        assert Usuario.query.count() == 3
        db.session.remove()
    # Reiniciar com o mesmo banco não duplica nada.
    de_novo = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/novo.db",
    })
    with de_novo.app_context():
        assert Usuario.query.count() == 3
        db.session.remove()

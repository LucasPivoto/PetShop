"""Dados iniciais do PetMóvel Itajubá, criados na primeira execução."""
from datetime import datetime, time, timedelta

from models import (
    CONCLUIDO, CONFIRMADO, EM_ATENDIMENTO, PENDENTE, PERFIL_CLIENTE,
    PERFIL_PRESTADOR, TIPO_LOJA, TIPO_MOVEL, Agendamento, AgendamentoServico,
    BairroCobertura, Notificacao, Pet, PostoFixo, Servico, UnidadeMovel, Usuario, db,
)
from services import calcular_preco, calcular_total

SENHA_PADRAO = "123456"


def _usuario(nome, email, perfil, telefone, endereco=None, bairro=None):
    usuario = Usuario(nome=nome, email=email, perfil=perfil, telefone=telefone,
                      endereco_completo=endereco, bairro=bairro)
    usuario.set_senha(SENHA_PADRAO)
    db.session.add(usuario)
    return usuario


def _agendamento(pet, servicos, tipo, quando, status, pagamento,
                 van=None, baia=None, mensagem=""):
    ag = Agendamento(
        cliente_id=pet.cliente_id, pet_id=pet.id, data_hora=quando,
        tipo_atendimento=tipo, status=status, forma_pagamento=pagamento,
        valor_total=calcular_total(servicos, pet.porte),
        unidade_movel_id=van.id if van else None,
        posto_fixo_id=baia.id if baia else None,
    )
    if tipo == TIPO_MOVEL:
        ag.endereco_atendimento = pet.cliente.endereco_completo
        ag.bairro_atendimento = pet.cliente.bairro
    for servico in servicos:
        ag.itens.append(AgendamentoServico(
            servico_id=servico.id,
            preco_aplicado=calcular_preco(servico.preco_base, pet.porte)))
    db.session.add(ag)
    db.session.flush()
    db.session.add(Notificacao(
        usuario_id=pet.cliente_id,
        mensagem=f"Agendamento #{ag.id} ({pet.nome}, {quando:%d/%m/%Y %H:%M}): "
                 f"{mensagem} Status: {status}.",
    ))
    return ag


def popular(agora: datetime | None = None) -> None:
    """Insere o conjunto completo de dados de demonstração."""
    agora = agora or datetime.now()
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)

    _usuario("Equipe PetMóvel", "admin@petmovel.com", PERFIL_PRESTADOR, "(35) 3622-1000")
    carlos = _usuario(
        "Carlos Cliente", "cliente@teste.com", PERFIL_CLIENTE, "(35) 99876-5432",
        "Rua Coronel Rennó, 120, Itajubá-MG", "BPS")
    maria = _usuario(
        "Maria Souza", "maria@teste.com", PERFIL_CLIENTE, "(35) 99123-4567",
        "Praça Theodomiro Santiago, 45, Itajubá-MG", "Centro")
    db.session.flush()

    thor = Pet(cliente_id=carlos.id, nome="Thor", especie="Cão", porte="Grande",
               restricoes_medicas="Alergia a shampoo perfumado")
    bob = Pet(cliente_id=carlos.id, nome="Bob", especie="Cão", porte="Medio")
    luna = Pet(cliente_id=maria.id, nome="Luna", especie="Gato", porte="Pequeno")

    banho = Servico(
        nome_servico="Banho Completo", preco_base=50.0, duracao_minutos=45,
        descricao="Banho com shampoo neutro, secagem e escovação.")
    tosa_higienica = Servico(
        nome_servico="Tosa Higiênica", preco_base=35.0, duracao_minutos=30,
        descricao="Aparo das regiões íntimas, patas e barriga.")
    tosa_completa = Servico(
        nome_servico="Tosa Completa", preco_base=70.0, duracao_minutos=60,
        descricao="Tosa do corpo inteiro na máquina ou na tesoura.")
    unhas = Servico(
        nome_servico="Corte de Unhas", preco_base=20.0, duracao_minutos=15,
        descricao="Corte e lixamento das unhas com segurança.")
    hidratacao = Servico(
        nome_servico="Hidratação de Pelos", preco_base=40.0, duracao_minutos=30,
        descricao="Máscara hidratante para pelos macios e brilhantes.")

    bairros = [BairroCobertura(nome_bairro=nome, ativo=True)
               for nome in ("Centro", "BPS", "Pinheirinho", "Varginha", "Morro Chic")]
    bairros.append(BairroCobertura(nome_bairro="Cruzeiro", ativo=False))

    van = UnidadeMovel(modelo="Van PetMóvel 01", placa="ABC-1D23",
                       profissional_responsavel="João Ferreira", ativo=True)
    baia1 = PostoFixo(identificacao_mesa="Baia 01 - Loja Física",
                      responsavel_setor="Ana Lima", ativo=True)
    baia2 = PostoFixo(identificacao_mesa="Baia 02 - Loja Física",
                      responsavel_setor="Pedro Santos", ativo=True)

    db.session.add_all([thor, bob, luna, banho, tosa_higienica, tosa_completa, unhas,
                        hidratacao, *bairros, van, baia1, baia2])
    db.session.flush()

    # Um agendamento em cada estado relevante, para o sistema abrir populado.
    _agendamento(
        thor, [tosa_completa], TIPO_LOJA, datetime.combine(ontem, time(14, 0)),
        CONCLUIDO, "Dinheiro", baia=baia2,
        mensagem="Atendimento finalizado. Obrigado pela preferência!")
    _agendamento(
        luna, [banho, hidratacao], TIPO_MOVEL, datetime.combine(hoje, time(10, 0)),
        EM_ATENDIMENTO, "Dinheiro", van=van,
        mensagem="O atendimento do seu pet começou.")
    _agendamento(
        bob, [tosa_higienica], TIPO_LOJA, datetime.combine(hoje, time(15, 0)),
        CONFIRMADO, "Cartao", baia=baia1,
        mensagem="Solicitação aprovada — Baia 01 - Loja Física reservada.")
    _agendamento(
        thor, [banho, unhas], TIPO_MOVEL, datetime.combine(hoje, time(16, 0)),
        PENDENTE, "PIX",
        mensagem="solicitação recebida.")

    db.session.commit()


def popular_se_vazio() -> bool:
    """Popula o banco apenas se ele ainda não tiver usuários."""
    if Usuario.query.count() > 0:
        return False
    popular()
    return True

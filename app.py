"""PetMóvel Itajubá — aplicação Flask (rotas, autenticação e inicialização)."""
import hmac
import math
import os
import secrets
import socket
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request, session,
    url_for,
)
from markupsafe import Markup
from werkzeug.routing import IntegerConverter

import seed
from models import (
    CONCLUIDO, ESPECIES, FORMAS_PAGAMENTO, MULTIPLICADORES, PERFIL_CLIENTE,
    PERFIL_PRESTADOR, PORTES, STATUS_ATIVOS, TIPO_LOJA, TIPO_MOVEL, TIPOS,
    Agendamento, AgendamentoServico, BairroCobertura, Notificacao, Pet, PostoFixo,
    Servico, UnidadeMovel, Usuario, db,
)
from services import (
    ANTECEDENCIA_MAXIMA, RegraNegocioError, acoes_disponiveis, agenda_do_dia, buscar_bairro,
    criar_agendamento, executar_acao, horarios_disponiveis, resumo_do_dia,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Depoimentos ilustrativos exibidos na página inicial (tutores fictícios).
DEPOIMENTOS = (
    {"nome": "Fernanda", "bairro": "Pinheirinho", "pet": "tutora do Paçoca",
     "texto": "A van chegou no horário combinado e o Paçoca nem precisou sair de casa. "
              "Voltou cheiroso e tranquilo!"},
    {"nome": "Rafael", "bairro": "Centro", "pet": "tutor da Mel",
     "texto": "Agendei pelo site em dois minutos e acompanhei cada etapa pelas "
              "notificações. Atendimento muito cuidadoso."},
    {"nome": "Dona Lúcia", "bairro": "Varginha", "pet": "tutora do Tobias",
     "texto": "O Tobias tem pele sensível e a equipe respeitou todas as restrições "
              "que cadastrei. Recomendo de olhos fechados."},
)


# --- Autenticação ----------------------------------------------------------

def destino_seguro(alvo: str | None) -> str | None:
    """Aceita só caminhos locais, para o `next` nunca levar a outro site."""
    if not alvo or not alvo.startswith("/") or alvo.startswith("//") or "\\" in alvo:
        return None
    # Tab, quebra de linha e afins são descartados pelos navegadores ao seguir o
    # redirecionamento ("/\t/site" viraria "//site"), então nenhum é aceito.
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in alvo):
        return None
    return alvo


def login_required(view):
    @wraps(view)
    def protegida(*args, **kwargs):
        if g.usuario is None:
            flash("Entre ou cadastre-se para continuar.", "info")
            # Só páginas (GET) são retomadas após o login; um POST não é repetido.
            destino = request.full_path.rstrip("?") if request.method == "GET" else None
            return redirect(url_for("login", next=destino))
        return view(*args, **kwargs)
    return protegida


def _exige_perfil(perfil):
    def decorador(view):
        @wraps(view)
        @login_required
        def protegida(*args, **kwargs):
            if g.usuario.perfil != perfil:
                flash("Acesso restrito.", "erro")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return protegida
    return decorador


cliente_required = _exige_perfil(PERFIL_CLIENTE)
prestador_required = _exige_perfil(PERFIL_PRESTADOR)


def pagina_inicial_do(usuario: Usuario) -> str:
    return "/painel" if usuario.eh_prestador else "/meus-agendamentos"


# --- Filtros de exibição ---------------------------------------------------

def brl(valor) -> str:
    texto = f"{float(valor or 0):,.2f}"
    return "R$ " + texto.replace(",", "§").replace(".", ",").replace("§", ".")


def datahora(valor) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else ""


class IdConverter(IntegerConverter):
    """`<id:...>` nas rotas: inteiro que cabe numa chave do SQLite; acima disso, 404."""

    def __init__(self, mapa):
        super().__init__(mapa, max=2**63 - 1)


# --- Fábrica ---------------------------------------------------------------

def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "petmovel-dev-secret"),
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(BASE_DIR, "petshop.db"),
        SEED_ON_START=True,
        CSRF_ENABLED=True,
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        if app.config["SEED_ON_START"]:
            seed.popular_se_vazio()

    app.url_map.converters["id"] = IdConverter
    app.add_template_filter(brl)
    app.add_template_filter(datahora)
    _registrar_ganchos(app)
    _registrar_rotas_publicas(app)
    _registrar_rotas_perfil_e_pets(app)
    _registrar_rotas_agendamento(app)
    _registrar_rotas_prestador(app)
    _registrar_rotas_gestao(app)
    return app


def _registrar_ganchos(app: Flask) -> None:
    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    def csrf_field() -> Markup:
        return Markup(f'<input type="hidden" name="_csrf" value="{csrf_token()}">')

    @app.before_request
    def carregar_usuario():
        g.usuario = None
        if "usuario_id" in session:
            g.usuario = db.session.get(Usuario, session["usuario_id"])
            if g.usuario is None:
                session.pop("usuario_id", None)

    @app.before_request
    def proteger_csrf():
        if request.method != "POST" or not app.config["CSRF_ENABLED"]:
            return
        esperado = session.get("_csrf", "")
        enviado = request.form.get("_csrf", "")
        if not esperado or not hmac.compare_digest(
                esperado.encode("utf-8"), enviado.encode("utf-8")):
            abort(400, "Sessão expirada ou formulário inválido. Recarregue a página.")

    @app.context_processor
    def variaveis_globais():
        nao_lidas = 0
        if g.get("usuario"):
            nao_lidas = Notificacao.query.filter_by(
                usuario_id=g.usuario.id, lida=False).count()
        return dict(
            usuario=g.get("usuario"), nao_lidas=nao_lidas,
            csrf_token=csrf_token, csrf_field=csrf_field,
            TIPO_LOJA=TIPO_LOJA, TIPO_MOVEL=TIPO_MOVEL,
        )


def _registrar_rotas_publicas(app: Flask) -> None:
    @app.get("/")
    def index():
        return render_template(
            "index.html",
            servicos=Servico.query.order_by(Servico.id).all(),
            bairros=BairroCobertura.query.filter_by(ativo=True)
            .order_by(BairroCobertura.nome_bairro).all(),
            depoimentos=DEPOIMENTOS,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        proximo = destino_seguro(request.args.get("next"))
        if request.method == "GET":
            if g.usuario:
                return redirect(proximo or pagina_inicial_do(g.usuario))
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        usuario = Usuario.query.filter_by(email=email).first() if email else None
        if usuario is None or not usuario.check_senha(request.form.get("senha", "")):
            flash("E-mail ou senha inválidos.", "erro")
            return render_template("login.html", email=email)

        session["usuario_id"] = usuario.id
        flash(f"Olá, {usuario.nome.split()[0]}! Que bom ver você.", "sucesso")
        return redirect(proximo or pagina_inicial_do(usuario))

    @app.route("/cadastro", methods=["GET", "POST"])
    def cadastro():
        if request.method == "GET":
            if g.usuario:
                return redirect(pagina_inicial_do(g.usuario))
            return render_template("cadastro.html", form={})

        form = {campo: request.form.get(campo, "").strip() for campo in
                ("nome", "email", "telefone", "endereco_completo", "bairro")}
        form["email"] = form["email"].lower()
        senha = request.form.get("senha", "")

        erro = None
        if not form["nome"]:
            erro = "Informe o seu nome."
        elif "@" not in form["email"] or " " in form["email"]:
            erro = "Informe um e-mail válido."
        elif len(senha) < 6:
            erro = "A senha deve ter ao menos 6 caracteres."
        elif Usuario.query.filter_by(email=form["email"]).first():
            erro = "Este e-mail já está cadastrado. Entre com a sua senha."
        if erro:
            flash(erro, "erro")
            return render_template("cadastro.html", form=form), 400

        # O cadastro público sempre cria um tutor; a equipe vem do seed.
        usuario = Usuario(perfil=PERFIL_CLIENTE, **form)
        usuario.set_senha(senha)
        db.session.add(usuario)
        db.session.commit()
        session["usuario_id"] = usuario.id
        flash("Cadastro concluído! Agora cadastre o seu primeiro pet.", "sucesso")
        return redirect("/pets")

    @app.post("/logout")
    def logout():
        session.pop("usuario_id", None)
        flash("Você saiu da sua conta.", "info")
        return redirect(url_for("index"))


def _pet_do_cliente(pet_id: int) -> Pet:
    """Pet do usuário logado; o de outro tutor responde 404, como se não existisse."""
    pet = db.session.get(Pet, pet_id)
    if pet is None or pet.cliente_id != g.usuario.id:
        abort(404)
    return pet


def _ler_pet_do_formulario() -> tuple[dict, str | None]:
    form = {
        "nome": request.form.get("nome", "").strip(),
        "especie": request.form.get("especie", ""),
        "porte": request.form.get("porte", ""),
        "restricoes_medicas": request.form.get("restricoes_medicas", "").strip() or None,
    }
    erro = None
    if not form["nome"]:
        erro = "Informe o nome do pet."
    elif form["especie"] not in ESPECIES:
        erro = "Selecione a espécie: Cão ou Gato."
    elif form["porte"] not in PORTES:
        erro = "Selecione o porte do pet."
    return form, erro


def _registrar_rotas_perfil_e_pets(app: Flask) -> None:
    @app.route("/perfil", methods=["GET", "POST"])
    @cliente_required
    def perfil():
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            if not nome:
                flash("Informe o seu nome.", "erro")
                return render_template("perfil.html"), 400
            g.usuario.nome = nome
            for campo in ("telefone", "endereco_completo", "bairro"):
                setattr(g.usuario, campo, request.form.get(campo, "").strip())
            db.session.commit()
            flash("Perfil atualizado.", "sucesso")
            return redirect(url_for("perfil"))
        return render_template("perfil.html")

    @app.get("/pets")
    @cliente_required
    def pets():
        concluidos = dict(
            db.session.query(Agendamento.pet_id, db.func.count(Agendamento.id))
            .filter(Agendamento.cliente_id == g.usuario.id, Agendamento.status == CONCLUIDO)
            .group_by(Agendamento.pet_id).all())
        return render_template("pets.html", pets=g.usuario.pets, concluidos=concluidos)

    @app.route("/pets/novo", methods=["GET", "POST"])
    @cliente_required
    def pet_novo():
        form = {}
        if request.method == "POST":
            form, erro = _ler_pet_do_formulario()
            if erro is None:
                db.session.add(Pet(cliente_id=g.usuario.id, **form))
                db.session.commit()
                flash(f"{form['nome']} foi cadastrado.", "sucesso")
                return redirect(url_for("pets"))
            flash(erro, "erro")
        return render_template("pet_form.html", pet=None, form=form), (400 if form else 200)

    @app.route("/pets/<id:pet_id>/editar", methods=["GET", "POST"])
    @cliente_required
    def pet_editar(pet_id):
        pet = _pet_do_cliente(pet_id)
        form = {campo: getattr(pet, campo) for campo in
                ("nome", "especie", "porte", "restricoes_medicas")}
        status = 200
        if request.method == "POST":
            form, erro = _ler_pet_do_formulario()
            if erro is None:
                for campo, valor in form.items():
                    setattr(pet, campo, valor)
                db.session.commit()
                flash(f"Dados de {pet.nome} atualizados.", "sucesso")
                return redirect(url_for("pets"))
            flash(erro, "erro")
            status = 400
        return render_template("pet_form.html", pet=pet, form=form), status

    @app.post("/pets/<id:pet_id>/excluir")
    @cliente_required
    def pet_excluir(pet_id):
        pet = _pet_do_cliente(pet_id)
        if pet.agendamentos:
            flash("Este pet possui agendamentos e não pode ser excluído.", "erro")
        else:
            nome = pet.nome
            db.session.delete(pet)
            db.session.commit()
            flash(f"{nome} foi removido.", "info")
        return redirect(url_for("pets"))


def _contexto_agendar(form: dict) -> dict:
    """Dados da tela de agendamento, inclusive o JSON usado pelo JavaScript."""
    servicos = Servico.query.order_by(Servico.id).all()
    bairros = BairroCobertura.query.order_by(BairroCobertura.nome_bairro).all()
    dados = {
        "pets": [{"id": p.id, "nome": p.nome, "especie": p.especie, "porte": p.porte}
                 for p in g.usuario.pets],
        "servicos": [{"id": s.id, "nome": s.nome_servico, "preco_base": s.preco_base,
                      "duracao": s.duracao_minutos} for s in servicos],
        "multiplicadores": MULTIPLICADORES,
        "bairros": [{"nome": b.nome_bairro, "ativo": b.ativo} for b in bairros],
        "tipoMovel": TIPO_MOVEL,
        "tipoLoja": TIPO_LOJA,
    }
    return dict(pets=g.usuario.pets, servicos=servicos, bairros=bairros, dados=dados,
                form=form, formas=FORMAS_PAGAMENTO, hoje=date.today().isoformat(),
                limite=(date.today() + ANTECEDENCIA_MAXIMA).isoformat())


def _registrar_rotas_agendamento(app: Flask) -> None:
    @app.route("/agendar", methods=["GET", "POST"])
    @cliente_required
    def agendar():
        if request.method == "GET":
            if not g.usuario.pets:
                flash("Cadastre um pet antes de agendar.", "info")
                return redirect(url_for("pet_novo"))
            bairro = buscar_bairro(g.usuario.bairro)
            form = {
                "pet_id": str(g.usuario.pets[0].id), "servicos": [], "tipo": TIPO_LOJA,
                "data": (date.today() + timedelta(days=1)).isoformat(), "hora": "",
                "bairro": bairro.nome_bairro if bairro else "",
                "endereco": g.usuario.endereco_completo or "", "forma_pagamento": "",
            }
            return render_template("agendar.html", **_contexto_agendar(form))

        form = {campo: request.form.get(campo, "").strip() for campo in
                ("pet_id", "tipo", "data", "hora", "bairro", "endereco", "forma_pagamento")}
        form["servicos"] = request.form.getlist("servicos")
        try:
            try:
                data_hora = datetime.strptime(f"{form['data']} {form['hora']}",
                                              "%Y-%m-%d %H:%M")
            except ValueError:
                raise RegraNegocioError("Data ou horário inválido.") from None
            # O valor total é sempre recalculado no servidor; o do formulário é ignorado.
            ag = criar_agendamento(
                g.usuario, form["pet_id"], form["servicos"], form["tipo"], data_hora,
                form["forma_pagamento"], bairro=form["bairro"], endereco=form["endereco"])
        except RegraNegocioError as erro:
            db.session.rollback()
            flash(str(erro), "erro")
            return render_template("agendar.html", **_contexto_agendar(form)), 400

        flash(f"Agendamento #{ag.id} solicitado! Aguarde a confirmação da equipe.", "sucesso")
        return redirect(url_for("meus_agendamentos"))

    @app.get("/api/horarios")
    def api_horarios():
        if g.usuario is None:
            return jsonify(erro="Faça login para consultar os horários."), 401
        tipo = request.args.get("tipo", "")
        try:
            dia = date.fromisoformat(request.args.get("data", ""))
        except ValueError:
            return jsonify(erro="Data inválida."), 400
        if tipo not in TIPOS:
            return jsonify(erro="Modalidade inválida."), 400
        return jsonify(horarios=horarios_disponiveis(tipo, dia))

    @app.get("/meus-agendamentos")
    @cliente_required
    def meus_agendamentos():
        todos = Agendamento.query.filter_by(cliente_id=g.usuario.id).all()
        ativos = sorted((a for a in todos if a.status in STATUS_ATIVOS),
                        key=lambda a: a.data_hora)
        historico = sorted((a for a in todos if a.status not in STATUS_ATIVOS),
                           key=lambda a: a.data_hora, reverse=True)
        acoes = {a.id: acoes_disponiveis(a, g.usuario) for a in ativos}
        return render_template("meus_agendamentos.html", ativos=ativos,
                               historico=historico, acoes=acoes)

    @app.post("/agendamentos/<id:ag_id>/acao")
    @login_required
    def agendamento_acao(ag_id):
        ag = db.session.get(Agendamento, ag_id)
        # Para um cliente, o agendamento de outro tutor "não existe".
        if ag is None or not (g.usuario.eh_prestador or ag.cliente_id == g.usuario.id):
            abort(404)
        try:
            executar_acao(ag, request.form.get("acao", ""), g.usuario)
            flash(f"Agendamento #{ag.id} de {ag.pet.nome}: status atualizado para "
                  f"{ag.status}.", "sucesso")
        except RegraNegocioError as erro:
            db.session.rollback()
            flash(str(erro), "erro")
        return redirect(destino_seguro(request.form.get("next"))
                        or pagina_inicial_do(g.usuario))

    @app.get("/notificacoes")
    @login_required
    def notificacoes():
        lista = (Notificacao.query.filter_by(usuario_id=g.usuario.id)
                 .order_by(Notificacao.criada_em.desc(), Notificacao.id.desc()).all())
        return render_template("notificacoes.html", notificacoes=lista)

    @app.post("/notificacoes/ler")
    @login_required
    def notificacoes_ler():
        Notificacao.query.filter_by(usuario_id=g.usuario.id, lida=False).update(
            {"lida": True})
        db.session.commit()
        return redirect(url_for("notificacoes"))


FILTROS_MODALIDADE = {"movel": TIPO_MOVEL, "loja": TIPO_LOJA}


def _registrar_rotas_prestador(app: Flask) -> None:
    @app.get("/painel")
    @prestador_required
    def painel():
        try:
            dia = date.fromisoformat(request.args.get("data", ""))
        except ValueError:
            dia = date.today()
        if not date(2000, 1, 1) <= dia <= date(2100, 12, 31):
            dia = date.today()
        filtro = request.args.get("tipo")
        if filtro not in FILTROS_MODALIDADE:
            filtro = "todos"

        agenda = agenda_do_dia(dia, FILTROS_MODALIDADE.get(filtro))
        return render_template(
            "painel.html", dia=dia, filtro=filtro, agenda=agenda,
            resumo=resumo_do_dia(dia),
            acoes={ag.id: acoes_disponiveis(ag, g.usuario) for ag in agenda},
            hoje=date.today(), anterior=dia - timedelta(days=1),
            seguinte=dia + timedelta(days=1),
            # As ações devolvem o prestador para esta mesma visão filtrada.
            aqui=f"/painel?data={dia.isoformat()}&tipo={filtro}",
        )


# --- Gestão básica (CRUD auxiliar) -----------------------------------------

PRECO_MAXIMO = 99_999.99
DURACAO_MAXIMA = 24 * 60  # minutos


def _texto(valor: str) -> str:
    valor = valor.strip()
    if not valor:
        raise ValueError("preencha todos os campos")
    return valor


def _preco(valor: str) -> float:
    try:
        numero = float(valor.strip().replace(",", "."))
    except ValueError:
        raise ValueError("o preço deve ser um número, como 45,50") from None
    if not math.isfinite(numero):
        raise ValueError("o preço deve ser um número, como 45,50")
    numero = round(numero, 2)
    if numero <= 0:
        raise ValueError("o preço deve ser de ao menos R$ 0,01")
    if numero > PRECO_MAXIMO:
        raise ValueError("o preço deve ser de no máximo R$ 99.999,99")
    return numero


def _minutos(valor: str) -> int:
    try:
        numero = int(valor.strip())
    except ValueError:
        raise ValueError("a duração deve ser um número inteiro de minutos") from None
    if not 0 < numero <= DURACAO_MAXIMA:
        raise ValueError(f"a duração deve ficar entre 1 e {DURACAO_MAXIMA} minutos")
    return numero


# Cada recurso da gestão: modelo, campos (nome, rótulo, validador) e como saber
# se o registro já foi usado em agendamentos (o que impede a exclusão).
GESTAO = {
    "servicos": {
        "titulo": "Serviços", "singular": "serviço", "modelo": Servico,
        "campos": (("nome_servico", "Nome", _texto), ("descricao", "Descrição", _texto),
                   ("preco_base", "Preço base (R$)", _preco),
                   ("duracao_minutos", "Duração (min)", _minutos)),
        "em_uso": lambda r: AgendamentoServico.query.filter_by(servico_id=r.id).count(),
    },
    "bairros": {
        "titulo": "Bairros de Cobertura", "singular": "bairro", "modelo": BairroCobertura,
        "campos": (("nome_bairro", "Bairro de Itajubá", _texto),),
        "em_uso": lambda r: 0,
    },
    "unidades": {
        "titulo": "Unidades Móveis", "singular": "unidade móvel", "modelo": UnidadeMovel,
        "campos": (("modelo", "Modelo", _texto), ("placa", "Placa", _texto),
                   ("profissional_responsavel", "Profissional responsável", _texto)),
        "em_uso": lambda r: Agendamento.query.filter_by(unidade_movel_id=r.id).count(),
    },
    "postos": {
        "titulo": "Postos Fixos", "singular": "posto fixo", "modelo": PostoFixo,
        "campos": (("identificacao_mesa", "Identificação da baia/mesa", _texto),
                   ("responsavel_setor", "Responsável pelo setor", _texto)),
        "em_uso": lambda r: Agendamento.query.filter_by(posto_fixo_id=r.id).count(),
    },
}


def _gestao_config(recurso: str) -> dict:
    if recurso not in GESTAO:
        abort(404)
    return GESTAO[recurso]


def _gestao_registro(config: dict, registro_id: int):
    registro = db.session.get(config["modelo"], registro_id)
    if registro is None:
        abort(404)
    return registro


def _gestao_ler_formulario(recurso: str, config: dict, atual=None) -> dict:
    """Valida os campos do formulário; levanta ValueError com o motivo."""
    valores = {nome: validar(request.form.get(nome, ""))
               for nome, _rotulo, validar in config["campos"]}
    if recurso == "bairros":
        existente = buscar_bairro(valores["nome_bairro"])
        if existente is not None and existente is not atual:
            raise ValueError(f"o bairro {existente.nome_bairro} já existe")
    return valores


def _registrar_rotas_gestao(app: Flask) -> None:
    def voltar(recurso):
        return redirect(url_for("gestao", aba=recurso))

    @app.get("/gestao")
    @prestador_required
    def gestao():
        aba = request.args.get("aba")
        if aba not in GESTAO:
            aba = "servicos"
        config = GESTAO[aba]
        modelo = config["modelo"]
        return render_template(
            "gestao.html", aba=aba, abas=GESTAO, config=config,
            registros=modelo.query.order_by(modelo.id).all(),
            tem_ativo=hasattr(modelo, "ativo"),
        )

    @app.post("/gestao/<recurso>/novo")
    @prestador_required
    def gestao_novo(recurso):
        config = _gestao_config(recurso)
        try:
            valores = _gestao_ler_formulario(recurso, config)
        except ValueError as erro:
            flash(f"Não foi possível cadastrar: {erro}.", "erro")
            return voltar(recurso)
        db.session.add(config["modelo"](**valores))
        db.session.commit()
        flash(f"Novo {config['singular']} cadastrado.", "sucesso")
        return voltar(recurso)

    @app.post("/gestao/<recurso>/<id:registro_id>/editar")
    @prestador_required
    def gestao_editar(recurso, registro_id):
        config = _gestao_config(recurso)
        registro = _gestao_registro(config, registro_id)
        try:
            valores = _gestao_ler_formulario(recurso, config, atual=registro)
        except ValueError as erro:
            flash(f"Não foi possível salvar: {erro}.", "erro")
            return voltar(recurso)
        for campo, valor in valores.items():
            setattr(registro, campo, valor)
        db.session.commit()
        flash("Alterações salvas.", "sucesso")
        return voltar(recurso)

    @app.post("/gestao/<recurso>/<id:registro_id>/alternar")
    @prestador_required
    def gestao_alternar(recurso, registro_id):
        config = _gestao_config(recurso)
        if not hasattr(config["modelo"], "ativo"):
            abort(404)
        registro = _gestao_registro(config, registro_id)
        registro.ativo = not registro.ativo
        db.session.commit()
        estado = "ativado" if registro.ativo else "desativado"
        flash(f"{config['singular'].capitalize()} {estado}.", "sucesso")
        return voltar(recurso)

    @app.post("/gestao/<recurso>/<id:registro_id>/excluir")
    @prestador_required
    def gestao_excluir(recurso, registro_id):
        config = _gestao_config(recurso)
        registro = _gestao_registro(config, registro_id)
        if config["em_uso"](registro):
            dica = " Desative-o em vez de excluir." if hasattr(registro, "ativo") else ""
            flash(f"Este {config['singular']} já foi usado em agendamentos e não pode "
                  f"ser excluído.{dica}", "erro")
            return voltar(recurso)
        db.session.delete(registro)
        db.session.commit()
        flash(f"{config['singular'].capitalize()} excluído.", "info")
        return voltar(recurso)


# --- Execução local (python app.py) ----------------------------------------

HOST = "127.0.0.1"
# A 5000 é a porta habitual do Flask, mas em muitas máquinas (sobretudo no
# Windows) ela é reservada pelo sistema ou usada por outro serviço. Nesse caso
# o servidor passa para a próxima da lista em vez de falhar ao iniciar.
PORTAS_PADRAO = (5000, 8000, 8080, 5050)


def portas_candidatas(ambiente) -> list[int]:
    """Portas a tentar, em ordem; a variável PORT, se válida, vem primeiro."""
    candidatas = list(PORTAS_PADRAO)
    try:
        preferida = int(ambiente.get("PORT", ""))
    except ValueError:
        preferida = 0
    if 0 < preferida < 65536:
        candidatas = [preferida] + [p for p in candidatas if p != preferida]
    return candidatas


def _porta_disponivel(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        if os.name != "nt":
            # Fora do Windows, permite reusar uma porta recém-liberada.
            sonda.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sonda.bind((host, porta))
        except OSError:  # em uso, ou proibida pelo sistema (WinError 10013)
            return False
    return True


def escolher_porta(host: str, candidatas: list[int]) -> int:
    """Primeira porta que o sistema deixa abrir; em último caso, uma livre qualquer."""
    for porta in candidatas:
        if _porta_disponivel(host, porta):
            return porta
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind((host, 0))
        return sonda.getsockname()[1]


def porta_do_servidor(ambiente) -> int:
    """Porta em que o servidor vai subir, registrada em `ambiente`.

    Com FLASK_DEBUG=1 o Flask reexecuta o programa num processo filho enquanto o
    pai já segura a porta; o filho reusa a escolha do pai em vez de sondar de novo
    (e concluir, errado, que a porta está bloqueada).
    """
    if ambiente.get("WERKZEUG_RUN_MAIN") == "true" and ambiente.get("PETMOVEL_PORTA"):
        return int(ambiente["PETMOVEL_PORTA"])
    candidatas = portas_candidatas(ambiente)
    porta = escolher_porta(HOST, candidatas)
    if porta != candidatas[0]:
        print(f" * A porta {candidatas[0]} está bloqueada ou em uso neste computador; "
              f"usando a porta {porta}.")
    print(f" * PetMóvel Itajubá: abra http://{HOST}:{porta} no navegador")
    ambiente["PETMOVEL_PORTA"] = str(porta)
    return porta


def main() -> None:
    app = create_app()
    porta = porta_do_servidor(os.environ)
    app.run(host=HOST, port=porta, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()

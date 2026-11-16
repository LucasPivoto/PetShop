"""PetMóvel Itajubá — aplicação Flask (rotas, autenticação e inicialização)."""
import hmac
import os
import secrets
from functools import wraps

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from markupsafe import Markup

import seed
from models import (
    CONCLUIDO, ESPECIES, PERFIL_CLIENTE, PERFIL_PRESTADOR, PORTES, TIPO_LOJA,
    TIPO_MOVEL, Agendamento, BairroCobertura, Notificacao, Pet, Servico, Usuario, db,
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
    if alvo and alvo.startswith("/") and not alvo.startswith("//") and "\\" not in alvo:
        return alvo
    return None


def login_required(view):
    @wraps(view)
    def protegida(*args, **kwargs):
        if g.usuario is None:
            flash("Entre ou cadastre-se para continuar.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
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

    app.add_template_filter(brl)
    app.add_template_filter(datahora)
    _registrar_ganchos(app)
    _registrar_rotas_publicas(app)
    _registrar_rotas_perfil_e_pets(app)
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
        if not esperado or not hmac.compare_digest(esperado, enviado):
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

    @app.route("/pets/<int:pet_id>/editar", methods=["GET", "POST"])
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

    @app.post("/pets/<int:pet_id>/excluir")
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


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")

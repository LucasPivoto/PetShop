"""PetMóvel Itajubá — aplicação Flask (rotas, autenticação e inicialização)."""
import os

from flask import Flask

from models import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")

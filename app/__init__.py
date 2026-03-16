from flask import Flask, redirect, url_for
from flask_login import current_user

from app.extensions import db, login_manager

from app.auth.routes import auth_bp
from app.academy.routes import academy_bp
from app.mit_sts.routes import mit_sts_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///academy.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    app.register_blueprint(auth_bp)
    app.register_blueprint(academy_bp)
    app.register_blueprint(mit_sts_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role == "mit":
                return redirect(url_for("mit_sts.my_mit"))
            if current_user.role in ["coach", "admin", "training_director"]:
                return redirect(url_for("mit_sts.dashboard"))
            return redirect(url_for("academy.dashboard"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()

    return app
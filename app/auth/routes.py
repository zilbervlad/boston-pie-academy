from flask import Blueprint, request, redirect, url_for, render_template_string, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("academy.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("academy.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template_string("""
    <h2>Boston Pie Academy Login</h2>
    <form method="POST">
        <input name="username" placeholder="Username" required>
        <input name="password" type="password" placeholder="Password" required>
        <button type="submit">Login</button>
    </form>
    """)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/seed-admin")
def seed_admin():
    existing = User.query.filter_by(username="admin").first()
    if existing:
        return "Admin user already exists. Username: admin / Password: admin123"

    user = User(
        name="Admin User",
        username="admin",
        role="admin",
    )
    user.set_password("admin123")

    db.session.add(user)
    db.session.commit()

    return "Admin created. Username: admin / Password: admin123"
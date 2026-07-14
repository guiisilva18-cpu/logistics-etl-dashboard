from flask import Blueprint, redirect, render_template, request, session, url_for

from utils import verificar_credenciais

bp_auth = Blueprint("auth", __name__)


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")
        if verificar_credenciais(usuario, senha):
            session["usuario"] = usuario
            return redirect(url_for("principal.index"))
        erro = "Usuário ou senha inválidos."
    return render_template("login.html", erro=erro)


@bp_auth.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("auth.login"))

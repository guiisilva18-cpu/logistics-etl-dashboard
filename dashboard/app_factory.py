import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, request, session, url_for

import config
from TELAS import bp_auth, bp_colaboradores, bp_operacoes, bp_principal, bp_sem_coleta
from utils import mensagem_erro, usuario_logado

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"dashboard_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="FRONT HTML", static_folder="static")
    app.secret_key = config.SECRET_KEY

    @app.before_request
    def exigir_login():
        if request.endpoint in ("auth.login", "static"):
            return None
        if not usuario_logado(session):
            if request.path.startswith("/api/"):
                return jsonify({"erro": "Não autenticado"}), 401
            return redirect(url_for("auth.login"))

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        log.exception("Erro não tratado")
        return (
            f"<body style='background:#0B0D12;color:#E8E9ED;font-family:monospace;padding:40px'>"
            f"<h2>Erro no servidor</h2><p>{mensagem_erro(e)}</p>"
            f"<p style='color:#8B92A1'>Detalhes completos em logs/{log_file.name}</p></body>",
            500,
        )

    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_principal)
    app.register_blueprint(bp_sem_coleta)
    app.register_blueprint(bp_colaboradores)
    app.register_blueprint(bp_operacoes)

    return app


app = create_app()

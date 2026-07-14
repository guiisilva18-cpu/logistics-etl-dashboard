import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Blueprint, jsonify, request

import config
from dashboard_logic import montar_resumo_sem_bipagem
from utils import mensagem_erro

bp_sem_coleta = Blueprint("sem_coleta", __name__)

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
log = logging.getLogger(__name__)


@bp_sem_coleta.route("/api/sem-coleta")
def api_sem_coleta():
    try:
        data_filtro = request.args.get("data")
        pa_filtro = request.args.get("pa")
        resumo = montar_resumo_sem_bipagem(data_filtro, pa_filtro)
        resumo["pas_disponiveis"] = sorted(set(l["pa"] for l in resumo.get("linhas", [])))
        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        resumo["intervalo_atualizacao_segundos"] = config.INTERVALO_ATUALIZACAO_SEGUNDOS
        return jsonify(resumo)
    except Exception as e:
        log.exception("Erro em /api/sem-coleta")
        return jsonify({"erro": mensagem_erro(e)}), 500

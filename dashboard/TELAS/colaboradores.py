import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Blueprint, jsonify, request, session

import config
from dashboard_logic import (
    listar_colaboradores_disponiveis,
    listar_pas_disponiveis,
    montar_detalhe_colaborador,
    montar_ranking_colaboradores,
)
from processar import sincronizar_diarista
from utils import mensagem_erro, pode_ver_colaboradores

bp_colaboradores = Blueprint("colaboradores", __name__)

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
log = logging.getLogger(__name__)


@bp_colaboradores.route("/api/colaboradores")
def api_colaboradores():
    if not pode_ver_colaboradores(session.get("usuario")):
        return jsonify({"erro": "Acesso não permitido."}), 403
    try:
        sincronizar_diarista(config.PASTA_RELATORIOS)
        colaborador = request.args.get("colaborador")
        pa_filtro = request.args.get("pa")
        data_filtro = request.args.get("data")

        if colaborador:
            resumo = montar_detalhe_colaborador(colaborador, pa_filtro, data_filtro)
            resumo["modo"] = "detalhe"
        else:
            resumo = montar_ranking_colaboradores(data_filtro, pa_filtro)
            resumo["modo"] = "ranking"

        resumo["colaboradores_disponiveis"] = listar_colaboradores_disponiveis()
        resumo["pas_disponiveis"] = listar_pas_disponiveis()
        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        resumo["intervalo_atualizacao_segundos"] = config.INTERVALO_ATUALIZACAO_SEGUNDOS
        return jsonify(resumo)
    except FileNotFoundError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        log.exception("Erro em /api/colaboradores")
        return jsonify({"erro": mensagem_erro(e)}), 500

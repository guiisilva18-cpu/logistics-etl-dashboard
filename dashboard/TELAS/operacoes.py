import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Blueprint, jsonify, request

import config
from dashboard_logic import (
    carregar_diaristas_por_pa,
    carregar_sem_coleta_por_pa,
    listar_pas_disponiveis,
    montar_falta_bipagem_detalhe,
    montar_kpis_pa,
)
from processar import sincronizar_diarista
from utils import mensagem_erro

bp_operacoes = Blueprint("operacoes", __name__)

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
log = logging.getLogger(__name__)


@bp_operacoes.route("/api/falta-bipagem-detalhe")
def api_falta_bipagem_detalhe():
    try:
        data_filtro = request.args.get("data")
        pa_filtro = request.args.get("pa")
        resumo = montar_falta_bipagem_detalhe(data_filtro, pa_filtro)
        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(resumo)
    except Exception as e:
        log.exception("Erro em /api/falta-bipagem-detalhe")
        return jsonify({"erro": mensagem_erro(e)}), 500


@bp_operacoes.route("/api/kpis-pa")
def api_kpis_pa():
    try:
        sincronizar_diarista(config.PASTA_RELATORIOS)
        data_filtro = request.args.get("data")
        pa_filtro = request.args.get("pa")
        resumo = montar_kpis_pa(data_filtro, pa_filtro)
        resumo["pas_disponiveis"] = listar_pas_disponiveis()
        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        resumo["intervalo_atualizacao_segundos"] = config.INTERVALO_ATUALIZACAO_SEGUNDOS
        return jsonify(resumo)
    except FileNotFoundError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        log.exception("Erro em /api/kpis-pa")
        return jsonify({"erro": mensagem_erro(e)}), 500


@bp_operacoes.route("/api/status-dados")
def api_status_dados():
    try:
        sincronizar_diarista(config.PASTA_RELATORIOS)
        diaristas_por_pa = carregar_diaristas_por_pa()
        sem_coleta_total = carregar_sem_coleta_por_pa()
        return jsonify({
            "diaristas": {
                "arquivo_carregado": bool(diaristas_por_pa),
                "total": sum(diaristas_por_pa.values()),
                "por_pa": diaristas_por_pa,
            },
            "sem_coleta": {
                "arquivo_carregado": bool(sem_coleta_total),
                "total": sum(sem_coleta_total.values()),
            },
        })
    except Exception as e:
        log.exception("Erro em /api/status-dados")
        return jsonify({"erro": mensagem_erro(e)}), 500

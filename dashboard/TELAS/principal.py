import logging

import pandas as pd
from flask import Blueprint, jsonify, make_response, render_template, request, session

import config
import processar
from dashboard_logic import (
    TIPO_BIPAGEM_COLETA,
    listar_pas_disponiveis,
    montar_resumo_bipagem_coleta,
    montar_resumo_generico,
    montar_visao_geral,
)
from processar import atualizar_todos, carregar_dataset
from utils import mensagem_erro, pode_ver_colaboradores

bp_principal = Blueprint("principal", __name__)

# O logging (nível, formato, arquivo de saída) é configurado uma única
# vez em app_factory.py — aqui só pegamos o logger.
log = logging.getLogger(__name__)


@bp_principal.route("/")
def index():
    # Sem isso, alguns navegadores guardam esta página em cache (o HTML
    # tem o JS de formatação embutido) mesmo depois de um F5 forçado, e
    # o usuário continua vendo a versão antiga mesmo com dado novo vindo
    # da API — daí a impressão de que a correção "não pegou".
    resposta = make_response(render_template(
        "index.html",
        pode_ver_colaboradores=pode_ver_colaboradores(session.get("usuario")),
    ))
    resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resposta


@bp_principal.route("/api/tipos")
def api_tipos():
    try:
        atualizar_todos(config.PASTA_RELATORIOS)
        return jsonify({
            "tipos": processar.listar_tipos(),
            "pas_disponiveis": listar_pas_disponiveis(),
            "atualizado_em": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "intervalo_atualizacao_segundos": config.INTERVALO_ATUALIZACAO_SEGUNDOS,
        })
    except FileNotFoundError as e:
        return jsonify({"erro": str(e), "tipos": []}), 400
    except Exception as e:
        log.exception("Erro em /api/tipos")
        return jsonify({"erro": mensagem_erro(e), "tipos": []}), 500


@bp_principal.route("/api/visao-geral")
def api_visao_geral():
    try:
        atualizar_todos(config.PASTA_RELATORIOS)
        resumo = montar_visao_geral()
        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        resumo["intervalo_atualizacao_segundos"] = config.INTERVALO_ATUALIZACAO_SEGUNDOS
        return jsonify(resumo)
    except FileNotFoundError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        log.exception("Erro em /api/visao-geral")
        return jsonify({"erro": mensagem_erro(e)}), 500


@bp_principal.route("/api/dados/<tipo>")
def api_dados(tipo):
    try:
        data_filtro = request.args.get("data")

        if tipo == TIPO_BIPAGEM_COLETA:
            resumo = montar_resumo_bipagem_coleta(data_filtro)
        else:
            atualizar_todos(config.PASTA_RELATORIOS)
            df = carregar_dataset(tipo)
            resumo = montar_resumo_generico(df, tipo)

        resumo["atualizado_em"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        resumo["intervalo_atualizacao_segundos"] = config.INTERVALO_ATUALIZACAO_SEGUNDOS
        return jsonify(resumo)
    except FileNotFoundError as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        log.exception(f"Erro em /api/dados/{tipo}")
        return jsonify({"erro": mensagem_erro(e)}), 500

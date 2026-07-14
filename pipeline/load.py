"""Carrega os pedidos de coleta extraídos da API no MySQL."""
import os
from collections import Counter

import pymysql
from dotenv import load_dotenv

from extract import NAO_COLETADO

load_dotenv()

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
    "charset": "utf8mb4",
}

INSERT_SQL = """
    INSERT INTO dados_ponto_coleta
        (numero_pedido, estacao_coleta, nome_cliente, base_remetente, data_referencia, data_hora_coleta, despachado)
    VALUES (%(numero_pedido)s, %(estacao_coleta)s, %(nome_cliente)s, %(base_remetente)s, %(data_referencia)s, %(data_hora_coleta)s, %(despachado)s)
"""

DELETE_RESUMO_SQL = "DELETE FROM resumo_pa WHERE data_referencia = %s"

INSERT_RESUMO_SQL = """
    INSERT INTO resumo_pa
        (data_referencia, base_remetente, total_remessas, coletados, nao_coletados)
    VALUES (%(data_referencia)s, %(base_remetente)s, %(total)s, %(coletados)s, %(nao_coletados)s)
"""


def _montar_resumo(dia: str, registros: list[dict]) -> list[dict]:
    total_por_pa = Counter(r["base_remetente"] for r in registros)
    nao_coletados_por_pa = Counter(
        r["base_remetente"] for r in registros if r["estacao_coleta"] == NAO_COLETADO
    )
    return [
        {
            "data_referencia": dia,
            "base_remetente": pa,
            "total": total,
            "nao_coletados": nao_coletados_por_pa.get(pa, 0),
            "coletados": total - nao_coletados_por_pa.get(pa, 0),
        }
        for pa, total in total_por_pa.items()
    ]


def carregar_pedidos(dia: str, registros: list[dict]) -> int:
    if not registros:
        return 0

    resumo = _montar_resumo(dia, registros)
    registros_com_data = [{**r, "data_referencia": dia} for r in registros]

    conexao = pymysql.connect(**DB_CONFIG)
    try:
        with conexao.cursor() as cursor:
            # Sobrescreve a tabela de detalhe a cada carga (sem acumular histórico),
            # para não gerar armazenamento/custo crescente no banco.
            cursor.execute("TRUNCATE TABLE dados_ponto_coleta")
            cursor.executemany(INSERT_SQL, registros_com_data)
            afetados = cursor.rowcount

            # Resumo por PA acumula histórico (poucas linhas/dia, custo desprezível),
            # mas o dia sendo carregado é sempre substituído por inteiro — evita
            # deixar PA "fantasma" de uma carga anterior do mesmo dia.
            cursor.execute(DELETE_RESUMO_SQL, (dia,))
            cursor.executemany(INSERT_RESUMO_SQL, resumo)
        conexao.commit()
        return afetados
    finally:
        conexao.close()


if __name__ == "__main__":
    from datetime import datetime, timedelta

    from extract import buscar_pedidos_coleta

    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    registros = buscar_pedidos_coleta(ontem)
    total = carregar_pedidos(ontem, registros)
    print(f"{len(registros)} pedidos processados, {total} linhas afetadas no banco")

"""Popula o banco com dados 100% fictícios, no mesmo formato que o
pipeline/ e o dashboard/ produzem/esperam em produção — serve pra rodar o
projeto localmente sem precisar de acesso ao portal real.

O que este script faz:
1. Cria o schema/tabelas (roda os .sql de pipeline/ e dashboard/).
2. Gera pedidos fictícios para "ontem" e carrega em `dados_ponto_coleta` +
   `resumo_pa`, do mesmo jeito que `pipeline/load.py` faria com dados reais.
3. Gera um histórico de ~14 dias de `resumo_pa`, pra dar tendência nos
   gráficos do dashboard.
4. Gera uma planilha `Diarista.CLT.xlsx` fictícia (uma aba por dia, mesmo
   formato que os líderes preenchem em produção) em `dashboard/dados_entrada/`
   e chama a função REAL `mysql_source.sincronizar_diarista_clt()` pra
   sincronizar `lideres_pa` / `efetivo_clt_pa` / `diaristas_pa` — ou seja,
   também serve como teste de ponta a ponta desse caminho de código.

Nenhum nome de cliente, colaborador ou número de pedido aqui é real.
"""
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

random.seed(42)

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
    "charset": "utf8mb4",
}

DIAS_HISTORICO = 14

PAS = [
    "PA NORTEXPRESS-SP", "PA HUBCENTRAL-SP", "PA VAREJOMAX-RJ", "PA FASTGOODS-MG",
    "PA MERCATOSHOP-SP", "PA ECOLOG-PR", "PA URBANBOX-SP", "PA DELTACARGO-RJ",
    "PA PRIMESHOP-SP", "PA METROLOG-BA", "PA SWIFTPACK-SC", "PA OMEGADIST-SP",
    "PA TROPICALHUB-CE", "PA CENTROOESTE-GO", "PA LITORALHUB-ES",
]

LIDERES = [
    "Ana Ribeiro", "Carlos Mendes", "Beatriz Alves", "Diego Santos",
    "Fernanda Lima", "Rodrigo Costa", "Juliana Rocha", "Marcelo Pinto",
]

CLIENTES = [
    "Comercial Alfa Ltda", "Distribuidora Beta EIRELI", "Grupo Gamma S.A.",
    "Varejo Delta ME", "Atacado Ômega Ltda", "Loja Prisma Comércio",
    "Nexus Distribuição", "Cliente Zenith Ltda",
]

ESTACOES = ["Estação Norte", "Estação Sul", "Estação Centro", "Estação Leste", "Estação Oeste"]

NAO_COLETADO = "Não coletado"


def _conectar():
    return pymysql.connect(**DB_CONFIG)


def _rodar_sql_file(cursor, caminho: Path):
    sql = caminho.read_text(encoding="utf-8")
    for comando in sql.split(";"):
        comando = comando.strip()
        if comando:
            cursor.execute(comando)


def criar_schema():
    # Conecta sem selecionar um schema ainda — os próprios .sql fazem
    # CREATE DATABASE IF NOT EXISTS + USE, então o schema pode nem existir
    # na primeira vez que este script roda.
    config_bootstrap = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conexao = pymysql.connect(**config_bootstrap)
    try:
        with conexao.cursor() as cursor:
            _rodar_sql_file(cursor, REPO_ROOT / "pipeline" / "sql" / "create_tables.sql")
            _rodar_sql_file(cursor, REPO_ROOT / "dashboard" / "sql" / "create_tables_dashboard.sql")
        conexao.commit()
    finally:
        conexao.close()


def _numero_pedido_ficticio(i: int) -> str:
    return f"DEMO{date.today().strftime('%y%m%d')}{i:07d}"


def gerar_detalhe_do_dia(dia: date) -> list[dict]:
    registros = []
    contador = 0
    for pa in PAS:
        volume = random.randint(150, 1800)
        taxa_nao_coletado = random.uniform(0.03, 0.22)
        for _ in range(volume):
            contador += 1
            coletado = random.random() > taxa_nao_coletado
            registros.append({
                "numero_pedido": _numero_pedido_ficticio(contador),
                "estacao_coleta": random.choice(ESTACOES) if coletado else NAO_COLETADO,
                "nome_cliente": random.choice(CLIENTES),
                "base_remetente": pa,
                "data_referencia": dia,
                "data_hora_coleta": None,
                "despachado": False,
            })
    return registros


def carregar_dia(cursor, dia: date, registros: list[dict]):
    from collections import Counter

    cursor.execute("TRUNCATE TABLE dados_ponto_coleta")
    cursor.executemany(
        "INSERT INTO dados_ponto_coleta "
        "(numero_pedido, estacao_coleta, nome_cliente, base_remetente, data_referencia, data_hora_coleta, despachado) "
        "VALUES (%(numero_pedido)s, %(estacao_coleta)s, %(nome_cliente)s, %(base_remetente)s, %(data_referencia)s, %(data_hora_coleta)s, %(despachado)s)",
        registros,
    )

    _inserir_resumo(cursor, dia, registros)


def _inserir_resumo(cursor, dia: date, registros: list[dict]):
    from collections import Counter

    total_por_pa = Counter(r["base_remetente"] for r in registros)
    nao_coletados_por_pa = Counter(
        r["base_remetente"] for r in registros if r["estacao_coleta"] == NAO_COLETADO
    )
    resumo = [
        {
            "data_referencia": dia,
            "base_remetente": pa,
            "total": total,
            "nao_coletados": nao_coletados_por_pa.get(pa, 0),
            "coletados": total - nao_coletados_por_pa.get(pa, 0),
        }
        for pa, total in total_por_pa.items()
    ]
    cursor.execute("DELETE FROM resumo_pa WHERE data_referencia = %s", (dia,))
    cursor.executemany(
        "INSERT INTO resumo_pa (data_referencia, base_remetente, total_remessas, coletados, nao_coletados) "
        "VALUES (%(data_referencia)s, %(base_remetente)s, %(total)s, %(coletados)s, %(nao_coletados)s)",
        resumo,
    )


def gerar_resumo_historico(cursor, ultimo_dia: date):
    """Preenche resumo_pa pros dias anteriores ao mais recente (sem gerar o
    detalhe completo — em produção o detalhe também não é histórico)."""
    for offset in range(1, DIAS_HISTORICO):
        dia = ultimo_dia - timedelta(days=offset)
        registros = gerar_detalhe_do_dia(dia)
        _inserir_resumo(cursor, dia, registros)


def gerar_planilha_diarista(ultimo_dia: date) -> Path:
    pasta_destino = REPO_ROOT / "dashboard" / "dados_entrada"
    pasta_destino.mkdir(parents=True, exist_ok=True)
    caminho = pasta_destino / "Diarista.CLT.xlsx"

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for offset in range(DIAS_HISTORICO):
            dia = ultimo_dia - timedelta(days=offset)
            linhas = []
            for pa in PAS:
                linhas.append({
                    "PA": pa,
                    "LIDER": random.choice(LIDERES),
                    "Quantidade CLT": random.randint(5, 35),
                    "Quantidade Diarista": random.randint(0, 12),
                    "TOTAL FUNCIONARIOS": 0,
                })
            df = pd.DataFrame(linhas)
            # Linha 0 fica em branco de propósito — em produção é um título
            # mesclado; o parser (header=1) ignora essa linha de qualquer forma.
            df.to_excel(writer, sheet_name=dia.strftime("%d.%m"), index=False, startrow=1)

    return caminho


def main():
    print("Criando schema/tabelas...")
    criar_schema()

    ontem = date.today() - timedelta(days=1)

    print(f"Gerando pedidos fictícios para {ontem}...")
    registros = gerar_detalhe_do_dia(ontem)

    conexao = _conectar()
    try:
        with conexao.cursor() as cursor:
            carregar_dia(cursor, ontem, registros)
            gerar_resumo_historico(cursor, ontem)
        conexao.commit()
    finally:
        conexao.close()
    print(f"{len(registros)} pedidos carregados em dados_ponto_coleta/resumo_pa "
          f"({DIAS_HISTORICO} dias de histórico em resumo_pa).")

    print("Gerando planilha Diarista.CLT.xlsx fictícia...")
    caminho_planilha = gerar_planilha_diarista(ontem)

    print("Sincronizando líderes/CLT/diaristas com o MySQL (mysql_source.sincronizar_diarista_clt)...")
    import mysql_source  # noqa: E402  (import tardio: precisa do sys.path ajustado acima)
    mysql_source.sincronizar_diarista_clt(caminho_planilha)

    print("Pronto. Rode o dashboard (dashboard/app.py) pra ver os dados fictícios.")


if __name__ == "__main__":
    main()

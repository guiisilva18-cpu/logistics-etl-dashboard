"""Acesso ao MySQL (mesmo banco alimentado pelo pipeline/, ver raiz do repo).

"coleta" e "sem_coleta" não vêm mais de .xlsx baixado manualmente — os
dados de pedido/PA vêm de `dados_ponto_coleta` (detalhe do dia mais
recente carregado; a tabela é sobrescrita a cada carga, sem histórico) e
`resumo_pa` (resumo diário por PA, acumula histórico). `lideres_pa`,
`diaristas_pa` e `efetivo_clt_pa` são tabelas de referência mantidas
manualmente pelo time de operações (ver `sql/create_tables_dashboard.sql`).
"""
import functools
import threading
import time
from datetime import datetime

import pymysql
import pandas as pd

import config

NAO_COLETADO = "Não coletado"

# resumo_pa/lideres_pa/efetivo_clt_pa/diaristas_pa/dados_ponto_coleta só
# mudam quando a carga diária roda (ou alguém faz um backfill manual) —
# não faz sentido bater no RDS de novo a cada refresh de 60s do dashboard,
# multiplicado por cada aba/usuário aberto. Cache compartilhado (1 processo
# Flask, todas as threads/usuários) por TTL; um restart do dashboard (já
# feito depois de toda carga/backfill) limpa na hora.
_CACHE_TTL_SEGUNDOS = 300
_cache_consultas: dict[tuple, tuple[float, object]] = {}
_lock_cache = threading.Lock()


def _copiar(valor):
    if isinstance(valor, pd.DataFrame):
        return valor.copy()
    if isinstance(valor, dict):
        return dict(valor)
    return valor


def _invalidar_cache() -> None:
    """Chamado depois de qualquer escrita (ex: sincronizar_diarista_clt) —
    sem isso, uma edição na planilha só apareceria no dashboard depois de
    _CACHE_TTL_SEGUNDOS, mesmo já sincronizada no banco."""
    with _lock_cache:
        _cache_consultas.clear()


def _com_cache(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        chave = (func.__name__, args, tuple(sorted(kwargs.items())))
        agora = time.time()
        with _lock_cache:
            cacheado = _cache_consultas.get(chave)
            if cacheado is not None and (agora - cacheado[0]) < _CACHE_TTL_SEGUNDOS:
                return _copiar(cacheado[1])

        resultado = func(*args, **kwargs)

        with _lock_cache:
            _cache_consultas[chave] = (agora, resultado)
        return _copiar(resultado)

    return wrapper

# Conectar no banco custa ~1s por causa da distância até a região
# — nada a ver com a query em si. Abrir uma conexão nova pra cada consulta
# deixava cada tela do dashboard visivelmente lenta (várias consultas por
# request). Em vez disso, mantém 1 conexão persistente por thread (o
# waitress roda com várias threads) e reaproveita entre requisições,
# reconectando sozinha (via ping) só se a conexão tiver caído.
_local = threading.local()


def _conectar():
    conexao = getattr(_local, "conexao", None)
    if conexao is not None:
        try:
            conexao.ping(reconnect=True)
            return conexao
        except Exception:
            pass
    conexao = pymysql.connect(**config.DB_CONFIG)
    _local.conexao = conexao
    return conexao


@_com_cache
def carregar_detalhe_referencia() -> pd.DataFrame:
    """Detalhe por pedido do dia de referência mais recente carregado.

    `dados_ponto_coleta` é sobrescrita a cada carga — só existe o dia
    mais recente aqui (histórico fica em `resumo_pa`).
    """
    return pd.read_sql(
        "SELECT numero_pedido, estacao_coleta, nome_cliente, base_remetente, "
        "data_referencia, data_hora_coleta, despachado FROM dados_ponto_coleta",
        _conectar(),
    )


@_com_cache
def carregar_resumo_pa() -> pd.DataFrame:
    """Resumo diário por PA — acumula histórico, uma linha por PA/dia."""
    return pd.read_sql(
        "SELECT data_referencia, base_remetente, total_remessas, coletados, nao_coletados "
        "FROM resumo_pa ORDER BY data_referencia",
        _conectar(),
    )


@_com_cache
def _carregar_mapa(tabela: str, coluna_valor: str, data_referencia) -> dict:
    df = pd.read_sql(
        f"SELECT base_remetente, {coluna_valor} FROM {tabela} WHERE data_referencia = %s",
        _conectar(), params=(data_referencia,),
    )
    return dict(zip(df["base_remetente"], df[coluna_valor]))


def carregar_lideres_pa(data_referencia) -> dict:
    return _carregar_mapa("lideres_pa", "lider", data_referencia)


def carregar_diaristas_pa(data_referencia) -> dict:
    return _carregar_mapa("diaristas_pa", "quantidade", data_referencia)


def carregar_efetivo_clt_pa(data_referencia) -> dict:
    return _carregar_mapa("efetivo_clt_pa", "quantidade", data_referencia)


@_com_cache
def carregar_lideres_pa_historico() -> pd.DataFrame:
    """Todo o histórico de líder por PA/dia — usado pra cruzar com
    resumo_pa (que também acumula histórico) linha a linha."""
    return pd.read_sql("SELECT data_referencia, base_remetente, lider FROM lideres_pa", _conectar())


@_com_cache
def carregar_efetivo_clt_pa_historico() -> pd.DataFrame:
    """Todo o histórico de efetivo CLT por PA/dia — evita precisar de uma
    query por dia quando é preciso o efetivo de vários dias de uma vez
    (ex: detalhe de um colaborador com histórico de N dias)."""
    return pd.read_sql("SELECT data_referencia, base_remetente, quantidade FROM efetivo_clt_pa", _conectar())


@_com_cache
def carregar_diaristas_pa_historico() -> pd.DataFrame:
    """Todo o histórico de diaristas por PA/dia (mesmo motivo do acima)."""
    return pd.read_sql("SELECT data_referencia, base_remetente, quantidade FROM diaristas_pa", _conectar())


def sincronizar_diarista_clt(caminho_arquivo) -> None:
    """Lê TODAS as abas de dia (nome "DD.MM", ex.: "07.07") da planilha
    "Diarista.CLT" (colunas PA, Líder, Quantidade CLT, Quantidade
    Diarista) — uma aba por dia, preenchida pelos próprios líderes — e
    sincroniza lideres_pa/efetivo_clt_pa/diaristas_pa por data_referencia.
    Isso permite que KPIs de um dia específico (ex: coleta de 06/07) usem
    o efetivo daquele mesmo dia, em vez de só o de "hoje". A primeira
    linha de cada aba é um título mesclado ("REGISTRO DIARISTA ..."),
    então o cabeçalho de verdade fica na segunda linha (header=1).
    Chamada por processar.py sempre que o arquivo mudar.
    """
    xls = pd.ExcelFile(caminho_arquivo)
    ano_atual = datetime.now().year

    lideres, clt, diaristas = [], [], []
    for nome_aba in xls.sheet_names:
        try:
            data_aba = datetime.strptime(f"{nome_aba}.{ano_atual}", "%d.%m.%Y").date()
        except ValueError:
            continue  # aba que não segue o padrão "DD.MM" (ex: instruções) é ignorada

        df = xls.parse(sheet_name=nome_aba, header=1)
        df.columns = [str(c).strip() for c in df.columns]

        col_pa = next((c for c in df.columns if c.strip().upper() == "PA"), None)
        if not col_pa:
            continue  # aba sem a coluna PA no formato esperado

        col_lider = next((c for c in df.columns if "lider" in c.lower() or "líder" in c.lower()), None)
        col_clt = next((c for c in df.columns if "clt" in c.lower()), None)
        col_diarista = next((c for c in df.columns if "diarista" in c.lower()), None)

        df[col_pa] = df[col_pa].astype(str).str.strip()
        df = df[df[col_pa] != ""]

        for _, row in df.iterrows():
            pa = row[col_pa]
            if col_lider and pd.notna(row[col_lider]) and str(row[col_lider]).strip():
                lideres.append((data_aba, pa, str(row[col_lider]).strip()))
            if col_clt:
                qtd = pd.to_numeric(row[col_clt], errors="coerce")
                clt.append((data_aba, pa, int(qtd) if pd.notna(qtd) else 0))
            if col_diarista:
                qtd = pd.to_numeric(row[col_diarista], errors="coerce")
                diaristas.append((data_aba, pa, int(qtd) if pd.notna(qtd) else 0))

    if not lideres and not clt and not diaristas:
        raise ValueError(f"Planilha {caminho_arquivo}: nenhuma aba no formato 'DD.MM' com coluna 'PA' foi encontrada.")

    conexao = _conectar()
    with conexao.cursor() as cur:
        if lideres:
            cur.executemany(
                "INSERT INTO lideres_pa (data_referencia, base_remetente, lider) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE lider = VALUES(lider)",
                lideres,
            )
        if clt:
            cur.executemany(
                "INSERT INTO efetivo_clt_pa (data_referencia, base_remetente, quantidade) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)",
                clt,
            )
        if diaristas:
            cur.executemany(
                "INSERT INTO diaristas_pa (data_referencia, base_remetente, quantidade) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)",
                diaristas,
            )
    conexao.commit()
    _invalidar_cache()

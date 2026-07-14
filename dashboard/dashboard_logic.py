"""Lógica de negócio e montagem dos dados para o dashboard.

"coleta" e "sem_coleta" vêm do MySQL (mesmo banco alimentado pelo
pipeline/, ver raiz do repo) — não mais de .xlsx baixado manualmente:
- `dados_ponto_coleta`: detalhe por pedido do dia de referência mais
  recente carregado (a tabela é sobrescrita a cada carga, sem histórico).
- `resumo_pa`: resumo diário por PA (coletados/não coletados), acumula
  histórico — é a fonte das telas com seletor de data antiga.
- `lideres_pa`, `diaristas_pa`, `efetivo_clt_pa`: tabelas de referência
  mantidas manualmente (ver mysql_source.py).

Outros tipos de relatório .xlsx (fora de coleta/sem_coleta) continuam
passando pelo mecanismo genérico de auto-detecção em processar.py.
"""
import logging
from datetime import date

import pandas as pd

import config
import processar
from mysql_source import (
    NAO_COLETADO,
    carregar_detalhe_referencia,
    carregar_diaristas_pa,
    carregar_diaristas_pa_historico,
    carregar_efetivo_clt_pa,
    carregar_efetivo_clt_pa_historico,
    carregar_lideres_pa,
    carregar_lideres_pa_historico,
    carregar_resumo_pa,
)
from processar import detectar_coluna_base

log = logging.getLogger(__name__)

TIPO_BIPAGEM_COLETA = "coleta"


def montar_resumo_bipagem_coleta(data_filtro: str | None) -> dict:
    df = carregar_detalhe_referencia()
    if df.empty:
        return {"total_remessas": 0, "datas_disponiveis": []}

    df = df.copy()
    df["data"] = df["data_referencia"].astype(str)
    df["hora"] = pd.to_datetime(df["data_hora_coleta"], errors="coerce").dt.hour

    # dados_ponto_coleta é sobrescrita a cada carga: só existe o dia de
    # referência mais recente aqui (sem seletor de dias antigos nessa
    # tela — para tendência histórica por PA, ver "KPIs por PA").
    datas_disponiveis = sorted(df["data"].dropna().unique().tolist())
    data_filtro = datas_disponiveis[-1] if datas_disponiveis else None
    df_filtrado = df[df["data"] == data_filtro] if data_filtro else df

    df_filtrado = df_filtrado.copy()
    df_filtrado["coletado"] = df_filtrado["estacao_coleta"] != NAO_COLETADO

    total = len(df_filtrado)
    coletados = int(df_filtrado["coletado"].sum())
    nao_coletados = total - coletados
    despachados = int(df_filtrado["despachado"].sum())

    por_base = (
        df_filtrado.groupby("base_remetente")
        .agg(total=("numero_pedido", "count"), coletados=("coletado", "sum"))
        .reset_index()
        .rename(columns={"base_remetente": "base"})
        .sort_values("total", ascending=False)
    )
    por_base["nao_coletados"] = por_base["total"] - por_base["coletados"]

    por_hora = (
        df_filtrado[df_filtrado["coletado"]]
        .dropna(subset=["hora"])
        .assign(hora=lambda d: d["hora"].astype(int))
        .groupby("hora")
        .agg(total=("numero_pedido", "count"), coletados=("coletado", "sum"))
        .reindex(range(24), fill_value=0)
        .reset_index()
    )

    top_nao_coletados_base = por_base.sort_values("nao_coletados", ascending=False).head(8)

    return {
        "tipo_view": "bipagem_coleta",
        "data_selecionada": data_filtro,
        "datas_disponiveis": datas_disponiveis,
        "total_remessas": total,
        "total_coletados": coletados,
        "total_nao_coletados": nao_coletados,
        "total_despachados": despachados,
        "pct_coletado": round(coletados / total * 100, 1) if total else 0,
        "pct_despachado": round(despachados / total * 100, 1) if total else 0,
        "total_bases": int(df_filtrado["base_remetente"].nunique()),
        "por_base": por_base.to_dict(orient="records"),
        "top_nao_coletados_base": top_nao_coletados_base[["base", "nao_coletados"]].to_dict(orient="records"),
        "por_hora": por_hora.to_dict(orient="records"),
        "total_geral_historico": total,
    }


def montar_resumo_generico(df: pd.DataFrame, tipo: str) -> dict:
    if df.empty:
        return {"tipo_view": "generico", "total_linhas": 0, "colunas": []}

    df = df.copy()
    colunas = [c for c in df.columns if c != "_arquivo_origem"]

    col_base = detectar_coluna_base(df)
    col_colab = processar.detectar_coluna_colaborador(df)

    col_data = None
    for c in colunas:
        if df[c].dtype == object or "data" in c.lower() or "hora" in c.lower():
            convertido = pd.to_datetime(df[c], errors="coerce")
            if convertido.notna().mean() > 0.7:
                col_data = c
                df["_data_detectada"] = convertido
                break

    distribuicoes = {}
    colunas_prioritarias = [c for c in [col_base, col_colab] if c] + [c for c in colunas if c not in (col_base, col_colab)]

    for c in colunas_prioritarias:
        if c in (col_data,):
            continue
        try:
            nunique = df[c].nunique(dropna=True)
        except TypeError:
            continue
        if 1 < nunique <= 30:
            contagem = df[c].value_counts(dropna=True).head(15)
            distribuicoes[c] = [{"valor": str(k), "total": int(v)} for k, v in contagem.items()]
        if len(distribuicoes) >= 6:
            break

    timeline = None
    if col_data:
        df["_dia"] = df["_data_detectada"].dt.strftime("%Y-%m-%d")
        agg = df.groupby("_dia").size().reset_index(name="total").sort_values("_dia")
        timeline = agg.to_dict(orient="records")

    preview = df[colunas].head(50).fillna("").astype(str).to_dict(orient="records")

    return {
        "tipo_view": "generico",
        "total_linhas": len(df),
        "colunas": colunas,
        "coluna_base": col_base,
        "coluna_colaborador": col_colab,
        "coluna_data": col_data,
        "distribuicoes": distribuicoes,
        "timeline": timeline,
        "preview": preview,
    }


def montar_visao_geral() -> dict:
    resumo = carregar_resumo_pa()
    por_base: dict[str, dict[str, int]] = {}

    if not resumo.empty:
        for base, total in resumo.groupby("base_remetente")["total_remessas"].sum().items():
            por_base.setdefault(base, {})[TIPO_BIPAGEM_COLETA] = int(total)

    tipos = [{"tipo": TIPO_BIPAGEM_COLETA, "nome_exibicao": "Monitoramento de Coleta"}]

    # Outros tipos de relatório .xlsx (mecanismo genérico), se existirem.
    for t in processar.listar_tipos():
        if t["tipo"] in (TIPO_BIPAGEM_COLETA, "sem_coleta"):
            continue
        tipos.append({"tipo": t["tipo"], "nome_exibicao": t["nome_exibicao"]})
        df = processar.carregar_dataset(t["tipo"])
        if df.empty:
            continue
        col_base = detectar_coluna_base(df)
        if col_base:
            for valor, total in df[col_base].dropna().astype(str).value_counts().items():
                por_base.setdefault(valor, {})[t["tipo"]] = int(total)

    linhas = []
    for nome, contagens in por_base.items():
        linhas.append({"nome": nome, "total": sum(contagens.values()), "por_tipo": contagens})
    linhas = sorted(linhas, key=lambda x: x["total"], reverse=True)

    return {
        "tipos": tipos,
        "por_base": linhas[:50],
        "total_bases": len(linhas),
        "total_geral": sum(l["total"] for l in linhas),
    }


SEM_LIDER_CADASTRADO = "4 EM 1"


def _contar_lideres(nome_lider: str) -> int:
    """Conta quantos líderes estão num campo "líder" (PAs com dois turnos
    têm dois nomes separados por "/", ex: "MATHEUS/INGRID" -> 2)."""
    return len([n for n in nome_lider.split("/") if n.strip()])


def _efetivo_clt_com_lideres(clt_por_pa: dict, lideres_por_pa: dict) -> dict:
    """CLT vindo da planilha (efetivo_clt_pa) + 1 por líder cadastrado na
    PA (lideres_pa), somado à parte. O(s) líder(es) já estão trabalhando
    ali independente de a planilha do dia estar preenchida, então contam
    de cara — usado tanto em KPIs por PA quanto no custo por colaborador."""
    resultado = dict(clt_por_pa)
    for pa, nome_lider in lideres_por_pa.items():
        resultado[pa] = resultado.get(pa, 0) + _contar_lideres(nome_lider)
    return resultado


def _agrupar_por_data(df: pd.DataFrame, coluna_valor: str) -> dict:
    """Converte um histórico (data_referencia, base_remetente, coluna_valor)
    num dict {data (str): {base_remetente: valor}} — usado pra pegar o
    efetivo de vários dias de uma vez (1 query) em vez de 1 query por dia."""
    if df.empty:
        return {}
    resultado: dict[str, dict] = {}
    for data_ref, grupo in df.groupby(df["data_referencia"].astype(str)):
        resultado[data_ref] = dict(zip(grupo["base_remetente"], grupo[coluna_valor]))
    return resultado


def _preparar_dados_lideres() -> pd.DataFrame:
    """resumo_pa (histórico diário por PA) cruzado com lideres_pa (PA/dia
    -> líder) — o cruzamento é por data E PA, porque o líder de uma PA
    pode mudar de um dia pro outro (troca de turno, por exemplo). Substitui
    o antigo cruzamento por coletador individual — não temos mais esse
    nível de detalhe sem o relatório de bipagem manual. PA sem líder
    cadastrado naquele dia entra no grupo "4 EM 1" (decisão de produto,
    ver README) em vez de sumir do ranking."""
    resumo = carregar_resumo_pa()
    if resumo.empty:
        return pd.DataFrame()

    lideres_hist = carregar_lideres_pa_historico()

    df = resumo.merge(lideres_hist, on=["data_referencia", "base_remetente"], how="left")
    df["lider"] = df["lider"].fillna(SEM_LIDER_CADASTRADO)
    df["data"] = df["data_referencia"].astype(str)
    return df


def _custo_por_pas(pas: list[str], clt_por_pa: dict, diarista_por_pa: dict) -> dict:
    """Custo diário de um conjunto de PAs — mesmo efetivo (CLT/diarista) e
    mesmas taxas usados em 'KPIs por PA', só que somado entre as PAs que
    um líder atende."""
    clt = sum(int(clt_por_pa.get(pa, 0)) for pa in pas)
    diaristas = sum(int(diarista_por_pa.get(pa, 0)) for pa in pas)
    custo_clt = round(clt * config.CUSTO_CLT_DIA, 2)
    custo_diarista = round(diaristas * config.CUSTO_DIARISTA_DIA, 2)
    return {
        "clt": clt,
        "diaristas": diaristas,
        "custo_clt": custo_clt,
        "custo_diarista": custo_diarista,
        "custo_dia": round(custo_clt + custo_diarista, 2),
    }


def montar_ranking_colaboradores(data_filtro: str | None, pa_filtro: str | None = None) -> dict:
    df = _preparar_dados_lideres()
    if df.empty:
        return {"total_colaboradores": 0, "datas_disponiveis": [], "linhas": []}

    datas_disponiveis = sorted(df["data"].dropna().unique().tolist())
    if data_filtro == "todos":
        df_filtrado = df
    elif data_filtro and data_filtro in datas_disponiveis:
        df_filtrado = df[df["data"] == data_filtro]
    else:
        data_filtro = datas_disponiveis[-1] if datas_disponiveis else None
        df_filtrado = df[df["data"] == data_filtro] if data_filtro else df

    if pa_filtro:
        df_filtrado = df_filtrado[df_filtrado["base_remetente"] == pa_filtro]

    agrupado = (
        df_filtrado.groupby("lider")
        .agg(
            pacotes_bipados=("coletados", "sum"),
            nao_bipados=("nao_coletados", "sum"),
            base=("base_remetente", lambda s: ", ".join(sorted(s.unique()))),
        )
        .reset_index()
        .sort_values("pacotes_bipados", ascending=False)
    )

    total_coletados = int(agrupado["pacotes_bipados"].sum())
    total_falta_bipe = int(agrupado["nao_bipados"].sum())
    total_geral = total_coletados + total_falta_bipe
    taxa_sem_bip = round(total_falta_bipe / total_geral * 100, 2) if total_geral else 0

    # Efetivo do MESMO dia sendo exibido (a planilha tem uma aba por
    # data) — em "todos" (soma de vários dias) não há um único dia pra
    # buscar, então o custo fica zerado.
    if data_filtro == "todos":
        clt_por_pa, diarista_por_pa = {}, {}
    else:
        clt_por_pa = _efetivo_clt_com_lideres(carregar_efetivo_clt_pa(data_filtro), carregar_lideres_pa(data_filtro))
        diarista_por_pa = carregar_diaristas_pa(data_filtro)

    linhas = []
    for _, row in agrupado.iterrows():
        pacotes = int(row["pacotes_bipados"])
        nao_bipados = int(row["nao_bipados"])
        total_pa = pacotes + nao_bipados
        pas_do_lider = [p.strip() for p in row["base"].split(",")]
        custo = _custo_por_pas(pas_do_lider, clt_por_pa, diarista_por_pa)
        custo_dia = custo["custo_dia"]
        linhas.append({
            "nome": row["lider"],
            "base": row["base"],
            "pacotes_bipados": pacotes,
            "nao_bipados": nao_bipados,
            "pct_falta_bipagem": round(nao_bipados / total_pa * 100, 2) if total_pa else 0,
            "custo_dia": custo_dia,
            "custo_total": custo_dia,
            "custo_por_pacote": round(custo_dia / pacotes, 4) if pacotes else 0,
        })

    return {
        "data_selecionada": data_filtro,
        "pa_selecionada": pa_filtro,
        "datas_disponiveis": datas_disponiveis,
        "total_colaboradores": len(linhas),
        "total_pacotes": total_coletados,
        "total_nao_coletados": total_falta_bipe,
        "total_nao_bipados": total_falta_bipe,
        "pct_falta_bipagem": taxa_sem_bip,
        "linhas": linhas,
    }


def montar_detalhe_colaborador(nome_normalizado: str, pa_filtro: str | None = None, data_filtro: str | None = None) -> dict:
    df = _preparar_dados_lideres()
    if df.empty:
        return {"encontrado": False}

    df_pessoa = df[df["lider"] == nome_normalizado]
    if df_pessoa.empty:
        return {"encontrado": False}

    if pa_filtro:
        df_pessoa = df_pessoa[df_pessoa["base_remetente"] == pa_filtro]
        if df_pessoa.empty:
            return {"encontrado": False, "sem_dados_na_pa": True}

    datas_disponiveis = sorted(df_pessoa["data"].dropna().unique().tolist())

    if data_filtro and data_filtro in datas_disponiveis:
        df_pessoa = df_pessoa[df_pessoa["data"] == data_filtro]
    else:
        data_filtro = None

    nome_exibicao = df_pessoa["lider"].iloc[0]

    por_base = (
        df_pessoa.groupby("base_remetente")
        .agg(pacotes_bipados=("coletados", "sum"))
        .reset_index()
        .rename(columns={"base_remetente": "base"})
        .sort_values("pacotes_bipados", ascending=False)
    )

    # Efetivo (CLT+diarista) das PAs desse líder é buscado por dia — a
    # planilha tem uma aba por data, então o custo de cada dia do
    # histórico usa o efetivo daquele mesmo dia, não um valor fixo. Carrega
    # o histórico inteiro de uma vez (3 queries) em vez de 1 dia por vez
    # (3 queries × N dias) — evita abrir dezenas de conexões com o banco
    # só pra montar essa tela.
    clt_hist = _agrupar_por_data(carregar_efetivo_clt_pa_historico(), "quantidade")
    diaristas_hist = _agrupar_por_data(carregar_diaristas_pa_historico(), "quantidade")
    lideres_hist = _agrupar_por_data(carregar_lideres_pa_historico(), "lider")

    linhas_por_dia = []
    for dia, grupo_dia in df_pessoa.groupby("data"):
        pacotes_dia = int(grupo_dia["coletados"].sum())
        nao_bipados_dia = int(grupo_dia["nao_coletados"].sum())
        pas_do_dia = sorted(grupo_dia["base_remetente"].unique().tolist())
        clt_por_pa_dia = _efetivo_clt_com_lideres(clt_hist.get(dia, {}), lideres_hist.get(dia, {}))
        diarista_por_pa_dia = diaristas_hist.get(dia, {})
        custo_dia = _custo_por_pas(pas_do_dia, clt_por_pa_dia, diarista_por_pa_dia)["custo_dia"]
        linhas_por_dia.append({
            "data": dia,
            "pacotes_bipados": pacotes_dia,
            "nao_bipados": nao_bipados_dia,
            "custo_dia": custo_dia,
            "custo_total": custo_dia,
            "custo_por_pacote": round(custo_dia / pacotes_dia, 4) if pacotes_dia else 0,
        })

    por_dia = pd.DataFrame(linhas_por_dia).sort_values("data") if linhas_por_dia else pd.DataFrame(
        columns=["data", "pacotes_bipados", "nao_bipados", "custo_dia", "custo_total", "custo_por_pacote"]
    )

    total_pacotes = int(df_pessoa["coletados"].sum())
    nao_bipados = int(df_pessoa["nao_coletados"].sum())
    dias_trabalhados = int(por_dia.shape[0])
    total_com_nao = total_pacotes + nao_bipados
    taxa_sem_bip = round(nao_bipados / total_com_nao * 100, 2) if total_com_nao else 0
    melhor_dia = por_dia.loc[por_dia["pacotes_bipados"].idxmax()] if not por_dia.empty else None
    custo_total_periodo = round(por_dia["custo_dia"].sum(), 2) if not por_dia.empty else 0

    return {
        "encontrado": True,
        "nome": nome_exibicao,
        "pa_selecionada": pa_filtro,
        "data_selecionada": data_filtro,
        "datas_disponiveis": datas_disponiveis,
        "bases": por_base.to_dict(orient="records"),
        "base_principal": por_base.iloc[0]["base"] if not por_base.empty else None,
        "por_dia": por_dia.to_dict(orient="records"),
        "resumo": {
            "total_pacotes_bipados": total_pacotes,
            "nao_coletados": nao_bipados,
            "nao_bipados": nao_bipados,
            "pct_falta_bipagem": taxa_sem_bip,
            "dias_trabalhados": dias_trabalhados,
            "media_pacotes_dia": round(total_pacotes / dias_trabalhados, 1) if dias_trabalhados else 0,
            "custo_total": custo_total_periodo,
            "custo_medio_por_pacote": round(custo_total_periodo / total_pacotes, 4) if total_pacotes else 0,
            "melhor_dia": (
                {"data": melhor_dia["data"], "pacotes": int(melhor_dia["pacotes_bipados"])}
                if melhor_dia is not None else {"data": None, "pacotes": 0}
            ),
        },
    }


def listar_colaboradores_disponiveis() -> list:
    df = _preparar_dados_lideres()
    if df.empty:
        return []
    nomes = sorted(df["lider"].dropna().unique().tolist())
    return [{"nome_normalizado": n, "nome": n} for n in nomes]


def listar_pas_disponiveis() -> list:
    df = carregar_resumo_pa()
    if df.empty:
        return []
    return sorted(df["base_remetente"].dropna().unique().tolist())


def montar_resumo_sem_bipagem(data_filtro: str | None, pa_filtro: str | None = None) -> dict:
    df = carregar_resumo_pa()
    if df.empty:
        return {"tipo_view": "sem_coleta", "sem_dados": True, "datas_disponiveis": []}

    df = df.copy()
    df["data"] = df["data_referencia"].astype(str)
    datas_disponiveis = sorted(df["data"].dropna().unique().tolist())

    if data_filtro == "todos":
        pass
    elif data_filtro and data_filtro in datas_disponiveis:
        df = df[df["data"] == data_filtro]
    else:
        data_filtro = datas_disponiveis[-1] if datas_disponiveis else None
        if data_filtro:
            df = df[df["data"] == data_filtro]

    if pa_filtro:
        df = df[df["base_remetente"] == pa_filtro]

    if df.empty:
        return {"tipo_view": "sem_coleta", "sem_dados": True, "datas_disponiveis": datas_disponiveis}

    agrupado = df.groupby("base_remetente")["nao_coletados"].sum()
    linhas = [{"pa": pa, "nao_coletados": int(v)} for pa, v in agrupado.items()]
    linhas.sort(key=lambda x: x["nao_coletados"], reverse=True)

    total_nao_coletados = sum(l["nao_coletados"] for l in linhas)
    pas_com_ocorrencia = sum(1 for l in linhas if l["nao_coletados"] > 0)

    return {
        "tipo_view": "sem_coleta",
        "sem_dados": False,
        "data_selecionada": data_filtro,
        "pa_selecionada": pa_filtro,
        "datas_disponiveis": datas_disponiveis,
        "totais": {
            "nao_coletados": total_nao_coletados,
            "total_pas": len(linhas),
            "pas_com_ocorrencia": pas_com_ocorrencia,
        },
        "linhas": linhas,
    }


def carregar_diaristas_por_pa() -> dict:
    """Diaristas de HOJE (aba do dia atual na planilha) — usado na tela
    de status/Diaristas, que mostra o efetivo ao vivo, não histórico."""
    return carregar_diaristas_pa(date.today())


def carregar_sem_coleta_por_pa(data_filtro: str | None = None) -> dict:
    df = carregar_resumo_pa()
    if df.empty:
        return {}

    df = df.copy()
    if data_filtro and data_filtro != "todos":
        df["data"] = df["data_referencia"].astype(str)
        df = df[df["data"] == data_filtro]
    else:
        ultimo_dia = df["data_referencia"].max()
        df = df[df["data_referencia"] == ultimo_dia]

    if df.empty:
        return {}
    return {str(k): int(v) for k, v in df.groupby("base_remetente")["nao_coletados"].sum().items()}


def calcular_previsao_coletas(data_selecionada: str | None, pa_filtro: str | None = None) -> int:
    df = carregar_resumo_pa()
    if df.empty:
        return 0

    df = df.copy()
    df["data"] = df["data_referencia"].astype(str)
    if pa_filtro:
        df = df[df["base_remetente"] == pa_filtro]

    datas = sorted(df["data"].dropna().unique().tolist())
    if not datas:
        return 0

    if data_selecionada and data_selecionada in datas:
        idx = datas.index(data_selecionada)
        dia_anterior = datas[idx - 1] if idx > 0 else None
    else:
        dia_anterior = datas[-1] if len(datas) >= 1 else None

    if not dia_anterior:
        return 0
    total = int(df[df["data"] == dia_anterior]["total_remessas"].sum())
    return int(total * 1.10)


def montar_falta_bipagem_detalhe(data_filtro: str | None, pa_filtro: str | None = None) -> dict:
    df = carregar_resumo_pa()
    if df.empty:
        return {"linhas": [], "total_coletados": 0, "total_sem_coleta": 0, "pct_falta_total": 0,
                "data_selecionada": None, "datas_disponiveis": []}

    df = df.copy()
    df["data"] = df["data_referencia"].astype(str)
    datas_disponiveis = sorted(df["data"].dropna().unique().tolist())

    if data_filtro == "todos":
        df_filtrado = df
    elif data_filtro and data_filtro in datas_disponiveis:
        df_filtrado = df[df["data"] == data_filtro]
    else:
        data_filtro = datas_disponiveis[-1] if datas_disponiveis else None
        df_filtrado = df[df["data"] == data_filtro] if data_filtro else df

    if pa_filtro:
        df_filtrado = df_filtrado[df_filtrado["base_remetente"] == pa_filtro]

    agrupado = (
        df_filtrado.groupby("base_remetente")
        .agg(coletados=("coletados", "sum"), sem_coleta=("nao_coletados", "sum"))
        .reset_index()
    )

    linhas = []
    for _, row in agrupado.iterrows():
        col = int(row["coletados"])
        sem = int(row["sem_coleta"])
        total = col + sem
        pct = round(sem / total * 100, 2) if total else 0
        linhas.append({"pa": row["base_remetente"], "coletados": col, "sem_coleta": sem, "total": total, "pct_falta": pct})

    linhas.sort(key=lambda x: x["pct_falta"], reverse=True)
    total_col = int(agrupado["coletados"].sum())
    total_sem = int(agrupado["sem_coleta"].sum())
    total_total = total_col + total_sem

    return {
        "linhas": linhas,
        "total_coletados": total_col,
        "total_sem_coleta": total_sem,
        "pct_falta_total": round(total_sem / total_total * 100, 2) if total_total else 0,
        "data_selecionada": data_filtro,
        "datas_disponiveis": datas_disponiveis,
    }


def _variacao_dia_anterior(df: pd.DataFrame, data_filtro: str | None, pa_filtro: str | None, datas_disponiveis: list[str]) -> dict | None:
    """Totais (pacotes/não coletados/% falta) do dia imediatamente anterior
    ao selecionado, pra render de seta/percentual de variação nos KPIs. None
    quando a visão é "todos" (soma de vários dias não tem um "anterior" único)
    ou quando o dia selecionado é o primeiro do histórico."""
    if data_filtro == "todos" or not datas_disponiveis:
        return None

    dia_atual = data_filtro if data_filtro in datas_disponiveis else datas_disponiveis[-1]
    idx = datas_disponiveis.index(dia_atual)
    if idx == 0:
        return None
    dia_anterior = datas_disponiveis[idx - 1]

    df_ant = df[df["data"] == dia_anterior]
    if pa_filtro:
        df_ant = df_ant[df_ant["base_remetente"] == pa_filtro]
    if df_ant.empty:
        return None

    pacotes_ant = int(df_ant["coletados"].sum())
    nao_coletados_ant = int(df_ant["nao_coletados"].sum())
    total_ant = pacotes_ant + nao_coletados_ant

    return {
        "dia_anterior": dia_anterior,
        "pacotes_coletados": pacotes_ant,
        "nao_coletados": nao_coletados_ant,
        "pct_falta_bipagem": round(nao_coletados_ant / total_ant * 100, 2) if total_ant else 0,
    }


def _delta_pct(atual: float, anterior: float) -> float | None:
    if not anterior:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def _pas_cronicas(df: pd.DataFrame, dia_referencia: str, datas_disponiveis: list[str], limite: float, minimo_dias: int = 3) -> dict[str, int]:
    """Pra cada PA, quantos dias seguidos (terminando em dia_referencia,
    incluso) ela ficou acima do limite de % falta de bipagem. PA só entra
    no dict com pelo menos `minimo_dias` seguidos — é isso que separa um
    dia ruim pontual (ruído, pode ser um pico isolado) de um problema
    estrutural que pede atenção contínua (líder, escala, cobertura da PA)."""
    if dia_referencia not in datas_disponiveis:
        return {}
    idx = datas_disponiveis.index(dia_referencia)
    janela = datas_disponiveis[: idx + 1]

    pct_por_dia_pa: dict[str, dict[str, float]] = {}
    for dia, grupo in df[df["data"].isin(janela)].groupby("data"):
        agregado = grupo.groupby("base_remetente").agg(
            coletados=("coletados", "sum"), nao_coletados=("nao_coletados", "sum")
        )
        for pa, row in agregado.iterrows():
            total = row["coletados"] + row["nao_coletados"]
            pct_por_dia_pa.setdefault(pa, {})[dia] = (row["nao_coletados"] / total * 100) if total else 0

    resultado = {}
    for pa, por_dia in pct_por_dia_pa.items():
        streak = 0
        for dia in reversed(janela):
            if por_dia.get(dia, 0) > limite:
                streak += 1
            else:
                break
        if streak >= minimo_dias:
            resultado[pa] = streak
    return resultado


def _custo_total_dias(dias: list[str], clt_hist: dict, diaristas_hist: dict, lideres_hist: dict, pa_filtro: str | None = None) -> float:
    """Custo total (CLT + diarista) somado por vários dias — usado no
    comparativo semanal. Reaproveita o mesmo critério de efetivo das
    outras telas (1 líder cadastrado conta como +1 CLT de cara, ver
    _efetivo_clt_com_lideres). Recebe o histórico já carregado (não busca
    de novo) — chamada 1x por semana comparada, não uma vez por dia."""
    custo = 0.0
    for dia in dias:
        clt_dia = _efetivo_clt_com_lideres(clt_hist.get(dia, {}), lideres_hist.get(dia, {}))
        diaristas_dia = diaristas_hist.get(dia, {})
        if pa_filtro:
            custo += clt_dia.get(pa_filtro, 0) * config.CUSTO_CLT_DIA
            custo += diaristas_dia.get(pa_filtro, 0) * config.CUSTO_DIARISTA_DIA
        else:
            custo += sum(clt_dia.values()) * config.CUSTO_CLT_DIA
            custo += sum(diaristas_dia.values()) * config.CUSTO_DIARISTA_DIA
    return round(custo, 2)


def _totais_semana(df: pd.DataFrame, ano_semana: tuple[int, int], pa_filtro: str | None, clt_hist: dict, diaristas_hist: dict, lideres_hist: dict) -> dict | None:
    sub = df[df["ano_semana"] == ano_semana]
    if pa_filtro:
        sub = sub[sub["base_remetente"] == pa_filtro]
    if sub.empty:
        return None

    dias = sorted(sub["data"].dropna().unique().tolist())
    coletados = int(sub["coletados"].sum())
    nao_coletados = int(sub["nao_coletados"].sum())
    total = coletados + nao_coletados

    return {
        "rotulo": f"{dias[0][8:10]}/{dias[0][5:7]}–{dias[-1][8:10]}/{dias[-1][5:7]}",
        "dias": dias,
        "coletados": coletados,
        "nao_coletados": nao_coletados,
        "pct_falta": round(nao_coletados / total * 100, 2) if total else 0,
        "custo_total": _custo_total_dias(dias, clt_hist, diaristas_hist, lideres_hist, pa_filtro),
    }


def montar_comparativo_semanal(df: pd.DataFrame, pa_filtro: str | None = None) -> dict:
    """Semana atual (a que contém o dia mais recente carregado) vs semana
    anterior, agregado — suaviza o ruído dia-a-dia (fim de semana tem
    volume menor por natureza, já confirmado) e dá o horizonte que
    diretoria costuma usar pra decidir, em vez de reagir a um dia isolado."""
    if df.empty:
        return {"disponivel": False}

    df = df.copy()
    df["data_dt"] = pd.to_datetime(df["data_referencia"])
    df["ano_semana"] = df["data_dt"].apply(lambda d: (d.isocalendar()[0], d.isocalendar()[1]))

    ultima_data = df["data_dt"].max()
    ano_atual, semana_atual, _ = ultima_data.isocalendar()
    semana_atual_tupla = (ano_atual, semana_atual)
    if semana_atual > 1:
        semana_anterior_tupla = (ano_atual, semana_atual - 1)
    else:
        fim_ano_anterior = ultima_data.replace(month=1, day=1) - pd.Timedelta(days=1)
        semana_anterior_tupla = (fim_ano_anterior.isocalendar()[0], fim_ano_anterior.isocalendar()[1])

    # Carregado 1x só e reaproveitado pelas duas semanas (antes cada
    # semana recarregava as 3 tabelas de novo — 6 buscas redundantes).
    clt_hist = _agrupar_por_data(carregar_efetivo_clt_pa_historico(), "quantidade")
    diaristas_hist = _agrupar_por_data(carregar_diaristas_pa_historico(), "quantidade")
    lideres_hist = _agrupar_por_data(carregar_lideres_pa_historico(), "lider")

    atual = _totais_semana(df, semana_atual_tupla, pa_filtro, clt_hist, diaristas_hist, lideres_hist)
    anterior = _totais_semana(df, semana_anterior_tupla, pa_filtro, clt_hist, diaristas_hist, lideres_hist)
    if not atual:
        return {"disponivel": False}

    return {
        "disponivel": True,
        "semana_atual": atual,
        "semana_anterior": anterior,
        "variacao_coletados_pct": _delta_pct(atual["coletados"], anterior["coletados"]) if anterior else None,
        "variacao_custo_pct": _delta_pct(atual["custo_total"], anterior["custo_total"]) if anterior else None,
        "variacao_pct_falta_pp": round(atual["pct_falta"] - anterior["pct_falta"], 2) if anterior else None,
    }


def montar_kpis_pa(data_filtro: str | None, pa_filtro: str | None = None) -> dict:
    df = carregar_resumo_pa()
    if df.empty:
        return {"datas_disponiveis": [], "linhas": [], "total_geral": None}

    df = df.copy()
    df["data"] = df["data_referencia"].astype(str)
    datas_disponiveis = sorted(df["data"].dropna().unique().tolist())

    if data_filtro == "todos":
        df_filtrado = df
    elif data_filtro and data_filtro in datas_disponiveis:
        df_filtrado = df[df["data"] == data_filtro]
    else:
        data_filtro = datas_disponiveis[-1] if datas_disponiveis else None
        df_filtrado = df[df["data"] == data_filtro] if data_filtro else df

    if pa_filtro:
        df_filtrado = df_filtrado[df_filtrado["base_remetente"] == pa_filtro]

    if df_filtrado.empty:
        return {"data_selecionada": data_filtro, "pa_selecionada": pa_filtro,
                "datas_disponiveis": datas_disponiveis, "linhas": [], "total_geral": None}

    pas_cronicas = _pas_cronicas(df, datas_disponiveis[-1], datas_disponiveis, config.LIMITE_ALERTA_PCT_FALTA)

    agrupado = df_filtrado.groupby("base_remetente").agg(
        pacotes=("coletados", "sum"), nao_coletados=("nao_coletados", "sum")
    )

    # Efetivo (líder/CLT/diarista) é buscado do MESMO dia que está sendo
    # exibido — a planilha tem uma aba por data, então o efetivo de 06/07
    # usa a aba 06.07, não a de hoje. Em "todos" (múltiplos dias somados),
    # soma o efetivo de cada dia do período (pessoa-dia) em vez de um único
    # dia — mesma soma é usada pro custo, já que a taxa diária é constante
    # (custo_clt do período = CLT-pessoa-dia somado × CUSTO_CLT_DIA).
    if data_filtro == "todos":
        dias_periodo = sorted(df_filtrado["data"].dropna().unique().tolist())
        clt_hist = _agrupar_por_data(carregar_efetivo_clt_pa_historico(), "quantidade")
        diaristas_hist = _agrupar_por_data(carregar_diaristas_pa_historico(), "quantidade")
        lideres_hist = _agrupar_por_data(carregar_lideres_pa_historico(), "lider")

        clt_por_pa, diarista_por_pa, lideres_por_pa = {}, {}, {}
        for dia in dias_periodo:
            clt_dia = _efetivo_clt_com_lideres(clt_hist.get(dia, {}), lideres_hist.get(dia, {}))
            for pa, qtd in clt_dia.items():
                clt_por_pa[pa] = clt_por_pa.get(pa, 0) + qtd
            for pa, qtd in diaristas_hist.get(dia, {}).items():
                diarista_por_pa[pa] = diarista_por_pa.get(pa, 0) + qtd
            lideres_por_pa.update(lideres_hist.get(dia, {}))  # dia mais recente prevalece
    else:
        diarista_por_pa = carregar_diaristas_pa(data_filtro)
        lideres_por_pa = carregar_lideres_pa(data_filtro)
        clt_por_pa = _efetivo_clt_com_lideres(carregar_efetivo_clt_pa(data_filtro), lideres_por_pa)

    linhas = []
    total_pacotes = total_clt = total_diaristas = total_custo_clt = total_custo_diarista = total_sem_coleta = 0
    for pa, row in agrupado.sort_values("pacotes", ascending=False).iterrows():
        pacotes = int(row["pacotes"])
        nao_coletados = int(row["nao_coletados"])
        clt = int(clt_por_pa.get(pa, 0))
        diaristas = int(diarista_por_pa.get(pa, 0))
        total_hc = clt + diaristas
        total_pa = pacotes + nao_coletados
        pct_falta = round(nao_coletados / total_pa * 100, 2) if total_pa else 0
        custo_clt = round(clt * config.CUSTO_CLT_DIA, 2)
        custo_diarista = round(diaristas * config.CUSTO_DIARISTA_DIA, 2)
        custo_pacote_total = round(pacotes * config.CUSTO_POR_PACOTE, 2)
        custo_total = round(custo_clt + custo_diarista + custo_pacote_total, 2)
        eficiencia = round(pacotes / total_hc) if total_hc else None
        custo_por_pacote = round(custo_total / pacotes, 4) if pacotes else 0
        linhas.append({
            "pa": pa,
            "lider": lideres_por_pa.get(pa, SEM_LIDER_CADASTRADO),
            "pacotes_coletados": pacotes,
            "nao_coletados": nao_coletados,
            "nao_bipados": nao_coletados,
            "pct_falta_bipagem": pct_falta,
            "clt": clt,
            "diaristas": diaristas,
            "total_hc": total_hc,
            "eficiencia": eficiencia,
            "custo_clt": custo_clt,
            "custo_diarista": custo_diarista,
            "custo_total": custo_total,
            "custo_por_pacote": custo_por_pacote,
            "dias_consecutivos_risco": pas_cronicas.get(pa, 0),
        })
        total_pacotes += pacotes
        total_clt += clt
        total_diaristas += diaristas
        total_custo_clt += custo_clt
        total_custo_diarista += custo_diarista
        total_sem_coleta += nao_coletados

    total_hc_geral = total_clt + total_diaristas
    total_custo_pacotes_geral = round(total_pacotes * config.CUSTO_POR_PACOTE, 2)
    total_custo_geral = round(total_custo_clt + total_custo_diarista + total_custo_pacotes_geral, 2)
    total_todos = total_pacotes + total_sem_coleta
    pct_falta_geral = round(total_sem_coleta / total_todos * 100, 2) if total_todos else 0
    previsao = calcular_previsao_coletas(data_filtro, pa_filtro)

    anterior = _variacao_dia_anterior(df, data_filtro, pa_filtro, datas_disponiveis)

    total_geral = {
        "pacotes_coletados": int(total_pacotes),
        "nao_coletados": total_sem_coleta,
        "nao_bipados": total_sem_coleta,
        "pct_falta_bipagem": pct_falta_geral,
        "previsao_coletas": previsao,
        "clt": int(total_clt),
        "diaristas": int(total_diaristas),
        "total_hc": int(total_hc_geral),
        "eficiencia": round(total_pacotes / total_hc_geral) if total_hc_geral else None,
        "custo_clt": round(total_custo_clt, 2),
        "custo_diarista": round(total_custo_diarista, 2),
        "custo_total": total_custo_geral,
        "custo_por_pacote": round(total_custo_geral / total_pacotes, 4) if total_pacotes else 0,
        "dia_comparacao": anterior["dia_anterior"] if anterior else None,
        "variacao_pacotes_pct": _delta_pct(total_pacotes, anterior["pacotes_coletados"]) if anterior else None,
        "variacao_nao_coletados_pct": _delta_pct(total_sem_coleta, anterior["nao_coletados"]) if anterior else None,
        "variacao_pct_falta_pp": round(pct_falta_geral - anterior["pct_falta_bipagem"], 2) if anterior else None,
    }

    pas_em_risco = [l["pa"] for l in linhas if l["pct_falta_bipagem"] > config.LIMITE_ALERTA_PCT_FALTA]
    pas_cronicas_ordenado = [{"pa": pa, "dias": dias} for pa, dias in sorted(pas_cronicas.items(), key=lambda x: -x[1])]

    return {
        "data_selecionada": data_filtro,
        "pa_selecionada": pa_filtro,
        "datas_disponiveis": datas_disponiveis,
        "linhas": linhas,
        "total_geral": total_geral,
        "limite_alerta_pct_falta": config.LIMITE_ALERTA_PCT_FALTA,
        "pas_em_risco": pas_em_risco,
        "pas_cronicas": pas_cronicas_ordenado,
        "comparativo_semanal": montar_comparativo_semanal(df, pa_filtro),
    }

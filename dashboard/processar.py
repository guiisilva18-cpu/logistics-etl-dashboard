"""
Lógica de ingestão de MÚLTIPLOS tipos de relatório .xlsx num conjunto
de datasets consolidados — um por tipo de relatório.

Como funciona a detecção de tipo:
- O nome do arquivo baixado do site segue o padrão
  "<Nome do Relatório>_<código/timestamp>.xlsx".
- Removemos o sufixo numérico final para obter um identificador
  estável do "tipo" de relatório (ex: "Monitoramento_de_bipagem_de_
  coleta_Lista_27060820260630124906.xlsx" -> tipo
  "monitoramento_de_bipagem_de_coleta_lista").
- Cada tipo tem seu próprio dataset consolidado (data/master_<tipo>.csv)
  e sua própria entrada no manifesto de arquivos já processados.

Deduplicação:
- Se o tipo tiver uma "chave_unica" configurada em config.TIPOS_CONFIG
  (ex: "Remessa"), usamos ela: a versão mais recente de cada chave
  sempre prevalece.
- Se não houver chave configurada, tentamos detectar automaticamente
  uma coluna com alta unicidade (>95% dos valores únicos). Se não
  encontrarmos nenhuma, fazemos deduplicação por linha inteira (evita
  duplicar exatamente a mesma linha, mas não substitui registros que
  mudarão de status sem uma chave identificável).
"""

import json
import logging
import re
import threading
import time
from pathlib import Path

import pandas as pd

import config
import mysql_source

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"

# Padrão de colunas que indicam "base/estação" e "colaborador",
# usado para a aba de Visão Geral que cruza todos os relatórios.
PADRAO_COLUNA_BASE = re.compile(r"base|esta[cç][aã]o|unidade", re.IGNORECASE)
PADRAO_COLUNA_COLABORADOR = re.compile(
    r"colaborador|coletador|funcion[aá]rio|respons[aá]vel|收件员|entregador|motorista",
    re.IGNORECASE,
)

_RE_SUFIXO_NUMERICO = re.compile(r"[_\-]?\d{6,}(?=\.\w+$)")


def eh_arquivo_funcionarios(filename: str) -> bool:
    """Arquivos de funcionários (cadastro externo) não são mais usados
    by dashboard — a base/colaborador vêm direto do relatório de
    coleta. Mantemos essa checagem só para não tratar esse tipo de
    arquivo, se ele ainda aparecer na pasta, como um relatório comum."""
    return "funcionario" in filename.lower()


def normalizar_nome(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    s = re.sub(r"\s+", " ", s)  # colapsa espaços/tabs/quebras em um espaço só
    return s.strip().upper()


# Mapeamento de palavras-chave para tipos padronizados.
# A ordem importa: primeira correspondência vence.
# ATENÇÃO: "sem_coleta" deve vir ANTES de "coleta" pois "coleta"
# aparece em ambos os nomes.
# Convenção: arquivos nomeados "Coleta_DD.MM..." ou "Sem_Coleta_DD.MM..."
_MAPA_TIPOS_PADRONIZADOS = [
    ([
        "sem_coleta", "sem coleta", "semcoleta",
        "nao_coletado", "não_coletado", "naocoletado",
        "nao coletado", "não coletado"
     ], "sem_coleta"),
    (["coleta", "bipagem"], "coleta"),
]


def identificar_tipo(filename: str) -> str:
    """Mapeia o nome do arquivo a um tipo padronizado (via palavras-chave)
    ou gera um slug a partir do nome, como fallback."""
    nome_lower = filename.lower().replace("-", "_").replace(" ", "_")
    for palavras_chave, tipo_padrao in _MAPA_TIPOS_PADRONIZADOS:
        if any(pk in nome_lower for pk in palavras_chave):
            return tipo_padrao
    # fallback: slug gerado do nome do arquivo (remove sufixo numérico)
    sem_extensao_numerica = _RE_SUFIXO_NUMERICO.sub("", filename)
    base = Path(sem_extensao_numerica).stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return slug or "relatorio_desconhecido"


def nome_exibicao(tipo: str) -> str:
    cfg = config.TIPOS_CONFIG.get(tipo, {})
    if cfg.get("nome_exibicao"):
        return cfg["nome_exibicao"]
    return tipo.replace("_", " ").strip().capitalize()


def _master_path(tipo: str) -> Path:
    return DATA_DIR / f"master_{tipo}.csv"


def _carregar_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def _salvar_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _carregar_master(tipo: str) -> pd.DataFrame | None:
    p = _master_path(tipo)
    if p.exists():
        return pd.read_csv(p)
    return None


def _detectar_chave_automatica(df: pd.DataFrame) -> str | None:
    n = len(df)
    if n == 0:
        return None
    for col in df.columns:
        if col == "_arquivo_origem":
            continue
        try:
            ratio = df[col].nunique(dropna=True) / n
        except TypeError:
            continue
        if ratio > 0.95:
            return col
    return None


def _deduplicar(df: pd.DataFrame, chave: str | None) -> pd.DataFrame:
    if chave and chave in df.columns:
        return df.drop_duplicates(subset=[chave], keep="last")
    colunas_comparaveis = [c for c in df.columns if c != "_arquivo_origem"]
    return df.drop_duplicates(subset=colunas_comparaveis, keep="last")


def _ler_arquivo(filepath: Path) -> pd.DataFrame:
    df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]
    df["_arquivo_origem"] = filepath.name
    return df


# Cache TTL: evita varrer a pasta e reprocessar em toda request.
# A varredura completa só acontece no máximo 1x a cada TTL segundos.
_CACHE_TTL_SEGUNDOS = 30
_ultima_varredura = {"ts": 0.0, "resultado": {}}
# O Flask roda com threaded=True/várias threads (waitress), então
# múltiplas requisições podem cair aqui ao mesmo tempo; o lock evita que
# duas varreduras concorrentes leiam/escrevam o mesmo master.csv juntas.
_lock_varredura = threading.Lock()


def sincronizar_diarista(pasta_relatorios: str) -> bool:
    """Procura um arquivo com "diarista" no nome na pasta configurada e
    sincroniza com o MySQL se o arquivo mudou desde a última vez.

    Não levanta exceção se a pasta ou o arquivo não existirem — só loga um
    aviso e segue. Nenhum endpoint do dashboard deve cair por causa disso,
    já que os líderes/CLT/diaristas sincronizados anteriormente continuam
    valendo (ficam no MySQL) até a planilha voltar a ficar acessível.

    A planilha tem uma aba por dia (formato "DD.MM") e `sincronizar_diarista_clt`
    sincroniza TODAS elas de uma vez, guardando por data — por isso a
    assinatura de cache é só tamanho+data de modificação do arquivo:
    qualquer edição em qualquer aba já dispara uma resincronização completa.
    """
    pasta = Path(pasta_relatorios)
    if not pasta.exists():
        log.warning(f"Pasta de relatórios não encontrada para sync de diarista: {pasta}")
        return False

    manifest = _carregar_manifest()
    sincronizou = False
    for f in pasta.glob("*.xlsx"):
        if "diarista" not in f.name.lower():
            continue
        chave_manifest = f"diarista::{f.name}"
        assinatura = f"{f.stat().st_size}-{int(f.stat().st_mtime)}"
        if manifest.get(chave_manifest) == assinatura:
            continue
        try:
            mysql_source.sincronizar_diarista_clt(f)
            manifest[chave_manifest] = assinatura
            sincronizou = True
            log.info(f"Planilha Diarista/CLT sincronizada com o MySQL: {f.name}")
        except Exception:
            log.exception(f"Erro ao sincronizar planilha Diarista/CLT ({f.name})")

    if sincronizou:
        _salvar_manifest(manifest)
    return sincronizou


def atualizar_todos(pasta_relatorios: str, forcar: bool = False) -> dict:
    """Varre a pasta, agrupa arquivos por tipo detectado, ingere os
    novos/alterados em cada dataset correspondente. Se um tipo não tem
    mais arquivos na pasta, remove o dataset interno automaticamente.
    Garante que arquivos deletados ou atualizados sejam expurgados do master.

    Usada só pelo mecanismo genérico de "outros relatórios" (Visão Geral).
    Se a pasta não existir, não falha — só loga e devolve vazio, pra não
    derrubar telas que não dependem desse mecanismo.
    """
    agora = time.time()
    if not forcar and (agora - _ultima_varredura["ts"]) < _CACHE_TTL_SEGUNDOS:
        return _ultima_varredura["resultado"].copy()

    with _lock_varredura:
        return _atualizar_todos_sem_lock(pasta_relatorios, forcar)


def _atualizar_todos_sem_lock(pasta_relatorios: str, forcar: bool) -> dict:
    agora = time.time()
    if not forcar and (agora - _ultima_varredura["ts"]) < _CACHE_TTL_SEGUNDOS:
        return _ultima_varredura["resultado"].copy()

    DATA_DIR.mkdir(exist_ok=True)
    pasta = Path(pasta_relatorios)
    if not pasta.exists():
        log.warning(f"Pasta configurada não existe, pulando 'outros relatórios': {pasta}")
        return {}

    manifest = _carregar_manifest()
    arquivos = sorted(pasta.glob("*.xlsx"), key=lambda f: f.stat().st_mtime)

    por_tipo: dict[str, list[Path]] = {}
    for f in arquivos:
        if eh_arquivo_funcionarios(f.name):
            continue
        if "diarista" in f.name.lower():
            continue
        tipo = identificar_tipo(f.name)
        por_tipo.setdefault(tipo, []).append(f)

    # 1. Remove datasets inteiros se o tipo não tem mais NENHUM arquivo na pasta
    houve_remocao = False
    for master_path in list(DATA_DIR.glob("master_*.csv")):
        tipo_existente = master_path.stem[len("master_"):]
        if tipo_existente not in por_tipo:
            master_path.unlink()
            log.info(f"[{tipo_existente}] removido do dashboard (sem arquivos na pasta)")
            chaves_remover = [k for k in list(manifest.keys()) if k.startswith(f"{tipo_existente}::")]
            for k in chaves_remover:
                del manifest[k]
            houve_remocao = True

    resultado = {}
    
    # 2. Processa cada tipo que ainda possui arquivos na pasta
    for tipo, lista_arquivos in por_tipo.items():
        master = _carregar_master(tipo)
        chave_cfg = config.TIPOS_CONFIG.get(tipo, {}).get("chave_unica")
        houve_mudanca = False
        
        nomes_atuais = {f.name for f in lista_arquivos}

        # --- NOVO: Expurgar dados de arquivos que foram DELETADOS da pasta ---
        if master is not None and not master.empty:
            tamanho_anterior = len(master)
            master = master[master["_arquivo_origem"].isin(nomes_atuais)]
            if len(master) < tamanho_anterior:
                houve_mudanca = True
                log.info(f"[{tipo}] Limpeza: removidas {tamanho_anterior - len(master)} linhas de arquivos deletados.")

        # --- NOVO: Limpar do manifest os registros de arquivos que não existem mais ---
        chaves_manifest_tipo = [k for k in list(manifest.keys()) if k.startswith(f"{tipo}::")]
        for k in chaves_manifest_tipo:
            nome_arquivo_manifest = k.split("::")[1]
            if nome_arquivo_manifest not in nomes_atuais:
                del manifest[k]
                houve_remocao = True  # Força o salvamento do manifest no final

        for f in lista_arquivos:
            chave_manifest = f"{tipo}::{f.name}"
            assinatura = f"{f.stat().st_size}-{int(f.stat().st_mtime)}"
            
            if manifest.get(chave_manifest) == assinatura:
                continue

            # --- NOVO: Se o arquivo mudou/foi substituído, apagar a versão antiga do master ---
            if master is not None and not master.empty:
                tamanho_antes_update = len(master)
                master = master[master["_arquivo_origem"] != f.name]
                if len(master) < tamanho_antes_update:
                    log.info(f"[{tipo}] Preparando atualização: removidas linhas antigas de {f.name}")

            try:
                novo_df = _ler_arquivo(f)
            except Exception:
                log.exception(f"Erro ao ler {f.name}")
                continue

            chave = chave_cfg or _detectar_chave_automatica(novo_df)
            novo_df = _deduplicar(novo_df, chave)

            master = novo_df if master is None or master.empty else pd.concat([master, novo_df], ignore_index=True)
            master = _deduplicar(master, chave)

            manifest[chave_manifest] = assinatura
            houve_mudanca = True

        # Salva o CSV consolidado se houve qualquer mudança (adição, deleção ou atualização)
        if houve_mudanca and master is not None:
            master.to_csv(_master_path(tipo), index=False)
            log.info(f"[{tipo}] dataset atualizado: {len(master)} linhas totais no arquivo mestre")

        if master is not None or _master_path(tipo).exists():
            resultado[tipo] = str(_master_path(tipo))

    if por_tipo or houve_remocao:
        _salvar_manifest(manifest)

    _ultima_varredura["ts"] = time.time()
    _ultima_varredura["resultado"] = resultado.copy()
    
    return resultado


def carregar_dataset(tipo: str) -> pd.DataFrame:
    df = _carregar_master(tipo)
    return df if df is not None else pd.DataFrame()


def listar_tipos() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    tipos = []
    for p in sorted(DATA_DIR.glob("master_*.csv")):
        tipo = p.stem[len("master_"):]
        try:
            n = sum(1 for _ in open(p, encoding="utf-8")) - 1
        except Exception:
            n = 0
        chave = config.TIPOS_CONFIG.get(tipo, {}).get("chave_unica")
        tipos.append({
            "tipo": tipo,
            "nome_exibicao": nome_exibicao(tipo),
            "total_linhas": max(n, 0),
            "chave_unica": chave,
            "chave_configurada": bool(chave),
        })
    return tipos


def detectar_coluna_base(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if PADRAO_COLUNA_BASE.search(c):
            return c
    return None


def detectar_coluna_colaborador(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if PADRAO_COLUNA_COLABORADOR.search(c):
            return c
    return None
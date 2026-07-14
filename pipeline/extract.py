"""Busca os pedidos de coleta do dia via exportação assíncrona do portal
interno da transportadora (RotaWeb).

A consulta interativa da API (endpoint de listagem paginada) só retorna uma
fração pequena e incompleta dos pedidos reais — acima de um certo volume a
API recusa com "volume de consulta grande demais". O volume completo só sai
por um mecanismo de exportação assíncrona, descoberto via DevTools:

1. POST /export — dispara a geração do arquivo (assíncrono, não retorna
   dado nenhum, só confirma o pedido).
2. GET /export/status — lista os jobs de exportação do operador e informa
   quando cada um ficou pronto (statusType == 1) e o "fileUrl" (caminho
   interno do arquivo).
3. GET /export/download?path=<fileUrl> — devolve uma URL assinada
   (storage temporário, expira em minutos).
4. GET nessa URL assinada — baixa o .xlsx de verdade.

O arquivo gerado tem as colunas já mapeadas (Número de pedido, Estação de
coleta, Nome do cliente, Base remetente), com o volume real (centenas de
milhares de linhas/dia, não a fração que o endpoint interativo devolve).

Nota de portfólio: domínio, nomes de campo específicos do fornecedor e
qualquer dado de negócio real foram removidos/genericizados. A lógica de
polling assíncrono abaixo é a mesma usada em produção.
"""
import io
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("PORTAL_BASE_URL", "https://gw.rotaweb-demo.com.br/networkmanagement")
URL_EXPORT = f"{BASE_URL}/omsWaybill/export"
URL_LISTA_EXPORT = f"{BASE_URL}/ft/ftExport/pageBalance"
URL_DOWNLOAD_FILE = f"{BASE_URL}/file/downloadFile"

TOKEN = os.environ["PORTAL_TOKEN"]
PICK_FINANCE_CODE = os.environ.get("PORTAL_PICK_FINANCE_CODE", "350000")
OPERATOR_CODE = os.environ["PORTAL_OPERATOR_CODE"]

HEADERS = {
    "authToken": TOKEN,
    "Content-Type": "application/json;charset=UTF-8",
    "accept": "application/json, text/plain, */*",
    "lang": "PT",
    "langtype": "PT",
    "origin": "https://portal.rotaweb-demo.com.br",
    "referer": "https://portal.rotaweb-demo.com.br/",
    "timezone": "GMT-0300",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

NAO_COLETADO = "Não coletado"

# Geração do arquivo já foi observada levando de ~2 a ~6 minutos.
TEMPO_MAX_ESPERA_SEGUNDOS = 900
INTERVALO_POLL_SEGUNDOS = 30


class TokenExpiradoError(Exception):
    pass


def _montar_payload_export(dia: str) -> dict:
    return {
        "current": 1,
        "size": 20,
        "pickFinanceCode": PICK_FINANCE_CODE,
        "isC2C": 0,
        "mergeWaybill": [0, 1],
        "mergeWaybills": [0, 1],
        "waybillNos": [],
        "customerCodes": [],
        "countryCode": "BR",
        "countryId": "1",
        "inputTimeStart": f"{dia} 00:00:00",
        "inputTimeEnd": f"{dia} 23:59:59",
    }


def _disparar_exportacao(session: requests.Session, dia: str) -> str:
    momento_disparo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resp = session.post(URL_EXPORT, json=_montar_payload_export(dia))
    if resp.status_code == 401:
        raise TokenExpiradoError(
            "Token do portal expirado ou sessão inativa. "
            "Faça login no portal e atualize PORTAL_TOKEN no arquivo .env."
        )
    resp.raise_for_status()
    resultado = resp.json()
    if resultado.get("code") != 1:
        raise RuntimeError(f"Erro ao disparar exportação: {resultado}")
    return momento_disparo


def _aguardar_arquivo(session: requests.Session, momento_disparo: str) -> str:
    hoje = datetime.now().strftime("%Y-%m-%d")
    params = {
        "current": 1,
        "size": 20,
        "total": 0,
        "operatorCode": OPERATOR_CODE,
        "jobName": "",
        "operatingStartTime": f"{hoje} 00:00:00",
        "operatingEndTime": f"{hoje} 23:59:59",
    }

    limite = time.time() + TEMPO_MAX_ESPERA_SEGUNDOS
    while time.time() < limite:
        time.sleep(INTERVALO_POLL_SEGUNDOS)

        resp = session.get(URL_LISTA_EXPORT, params=params)
        if resp.status_code == 401:
            raise TokenExpiradoError(
                "Token do portal expirado ou sessão inativa. "
                "Faça login no portal e atualize PORTAL_TOKEN no arquivo .env."
            )
        resp.raise_for_status()
        resultado = resp.json()
        registros = (resultado.get("data") or {}).get("records", [])

        candidatos = [r for r in registros if r.get("createTime", "") >= momento_disparo]
        if candidatos:
            mais_recente = max(candidatos, key=lambda r: r["createTime"])
            if mais_recente.get("statusType") == 1 and mais_recente.get("fileUrl"):
                return mais_recente["fileUrl"]

    raise TimeoutError(
        f"Exportação não ficou pronta em {TEMPO_MAX_ESPERA_SEGUNDOS // 60} minutos."
    )


def _baixar_planilha(session: requests.Session, file_url: str) -> bytes:
    resp = session.get(URL_DOWNLOAD_FILE, params={"path": file_url})
    resp.raise_for_status()
    resultado = resp.json()
    if resultado.get("code") != 1:
        raise RuntimeError(f"Erro ao obter link de download: {resultado}")

    resp_arquivo = requests.get(resultado["data"])
    resp_arquivo.raise_for_status()
    return resp_arquivo.content


def _processar_planilha(conteudo: bytes) -> list[dict]:
    df = pd.read_excel(io.BytesIO(conteudo))
    df.columns = [str(c).strip() for c in df.columns]

    registros = []
    for _, row in df.iterrows():
        base_remetente = row.get("Base remetente")
        base_remetente = str(base_remetente).strip() if pd.notna(base_remetente) else ""
        if not base_remetente.upper().startswith("PA "):
            continue

        estacao_coleta = row.get("Estação de coleta")
        estacao_coleta = str(estacao_coleta).strip() if pd.notna(estacao_coleta) else NAO_COLETADO

        registros.append(
            {
                "numero_pedido": str(row.get("Número de pedido")),
                "estacao_coleta": estacao_coleta,
                "nome_cliente": row.get("Nome do cliente"),
                "base_remetente": base_remetente,
                # A exportação não traz timestamp de coleta nem status de
                # despacho por pedido — só o endpoint interativo (restrito
                # em volume) trazia isso.
                "data_hora_coleta": None,
                "despachado": False,
            }
        )

    return registros


def buscar_pedidos_coleta(dia: str) -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)

    momento_disparo = _disparar_exportacao(session, dia)
    file_url = _aguardar_arquivo(session, momento_disparo)
    conteudo = _baixar_planilha(session, file_url)
    return _processar_planilha(conteudo)


if __name__ == "__main__":
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    dados = buscar_pedidos_coleta(ontem)
    print(f"{len(dados)} pedidos encontrados para {ontem}")
    for r in dados[:5]:
        print(r)

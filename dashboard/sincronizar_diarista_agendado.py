"""Sincroniza a planilha Diarista/CLT com o MySQL sem depender de alguém
abrir o dashboard.

A sincronização normal só roda sob demanda (quando alguém acessa KPIs por
PA, Colaboradores ou Status-dados). Esse script existe pra garantir que
aconteça também em horários fixos mesmo sem ninguém abrir a tela — chamado
pelo Task Scheduler às 14:00 (além da sincronização sob demanda de quando
a primeira pessoa entra no dia).
"""
import logging
from pathlib import Path

import config
import processar

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "sincronizacao_diarista.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


if __name__ == "__main__":
    sincronizou = processar.sincronizar_diarista(config.PASTA_RELATORIOS)
    log.info("Sincronização agendada da planilha Diarista/CLT concluída (mudou algo: %s)", sincronizou)

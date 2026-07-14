"""Orquestra a rotina diária: busca os pedidos de coleta do dia anterior e carrega no MySQL."""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from extract import TokenExpiradoError, buscar_pedidos_coleta
from load import carregar_pedidos

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "execucao.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    dia = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("Buscando pedidos de coleta de %s", dia)
    try:
        registros = buscar_pedidos_coleta(dia)
    except TokenExpiradoError as e:
        logger.error("%s", e)
        sys.exit(1)

    logger.info("%d pedidos encontrados", len(registros))

    afetados = carregar_pedidos(dia, registros)
    logger.info("Carga concluída: %d linhas afetadas no banco", afetados)


if __name__ == "__main__":
    main()

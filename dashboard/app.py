"""
Servidor local do NovaRota Ops Dashboard — suporta múltiplos tipos de
relatório, detectados automaticamente pelo nome do arquivo.

Iniciar com:  python app.py
ou dando duplo clique em iniciar_dashboard.bat
"""

import webbrowser
from threading import Timer

from waitress import serve

import config
from app_factory import app


def abrir_navegador():
    webbrowser.open(f"http://localhost:{config.PORTA}")


if __name__ == "__main__":
    Timer(1.2, abrir_navegador).start()
    # waitress no lugar do servidor de desenvolvimento do Flask: o servidor
    # embutido do Flask não é indicado para ficar exposto (inclusive via
    # ngrok), mesmo com debug=False.
    serve(app, host="0.0.0.0", port=config.PORTA, threads=8)

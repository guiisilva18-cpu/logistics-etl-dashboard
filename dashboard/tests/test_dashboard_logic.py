import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

import config
import dashboard_logic
import mysql_source


class CarregarDiaristasPorPaTests(unittest.TestCase):
    def setUp(self):
        self._pasta_original = config.PASTA_RELATORIOS
        self._tmp_dir = tempfile.mkdtemp()
        config.PASTA_RELATORIOS = self._tmp_dir

    def tearDown(self):
        config.PASTA_RELATORIOS = self._pasta_original
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        mysql_source._invalidar_cache()

    def test_usa_quantidade_diarista_e_ignora_quantidade_clt(self):
        # carregar_diaristas_por_pa() lê de diaristas_pa (MySQL), não do
        # .xlsx direto -- quem faz a ponte planilha -> banco é
        # sincronizar_diarista_clt(), que espera uma aba por dia nomeada
        # "DD.MM" com o cabeçalho real na 2a linha (a 1a é um título
        # mesclado, "REGISTRO DIARISTA ..."). Reflete as colunas reais da
        # planilha: PA, LIDER, Quantidade CLT, Quantidade Diarista, TOTAL
        # FUNCIONARIOS. O CLT efetivo vem do relatório de coleta, então
        # essa coluna precisa ser ignorada aqui mesmo que também contenha
        # "quant".
        hoje = date.today()
        nome_aba = hoje.strftime("%d.%m")
        linhas = [
            ["REGISTRO DIARISTA", None, None, None, None],
            ["PA", "LIDER", "Quantidade CLT", "Quantidade Diarista", "TOTAL FUNCIONARIOS"],
            ["PA HUBNORTE-SP", "ANA SILVA", 99, 3, 0],
            ["PA HUBSUL-RJ", "CARLOS SOUZA", 99, 5, 0],
        ]
        caminho = Path(self._tmp_dir) / "Diarista.CLT.xlsx"
        with pd.ExcelWriter(caminho) as writer:
            pd.DataFrame(linhas).to_excel(writer, sheet_name=nome_aba, header=False, index=False)

        mysql_source.sincronizar_diarista_clt(caminho)

        resultado = dashboard_logic.carregar_diaristas_por_pa()

        self.assertEqual(resultado, {"PA HUBNORTE-SP": 3, "PA HUBSUL-RJ": 5})


if __name__ == "__main__":
    unittest.main()

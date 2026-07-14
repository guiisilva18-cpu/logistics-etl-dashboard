import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import config
import dashboard_logic


class CarregarDiaristasPorPaTests(unittest.TestCase):
    def setUp(self):
        self._pasta_original = config.PASTA_RELATORIOS
        self._tmp_dir = tempfile.mkdtemp()
        config.PASTA_RELATORIOS = self._tmp_dir

    def tearDown(self):
        config.PASTA_RELATORIOS = self._pasta_original
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_usa_quantidade_diarista_e_ignora_quantidade_clt(self):
        # Reflete as colunas reais da planilha "Registro Diarista":
        # PA, LIDER, Quantidade CLT, Quantidade Diarista, TOTAL FUNCIONARIOS.
        # O CLT efetivo vem do relatório de coleta, então essa coluna
        # precisa ser ignorada aqui mesmo que também contenha "quant".
        df = pd.DataFrame({
            "PA": ["PA HUBNORTE-SP", "PA HUBSUL-RJ"],
            "LIDER": ["ANA SILVA", "CARLOS SOUZA"],
            "Quantidade CLT": [99, 99],
            "Quantidade Diarista": [3, 5],
            "TOTAL FUNCIONARIOS": [0, 0],
        })
        df.to_excel(Path(self._tmp_dir) / "Diarista.CLT.xlsx", index=False)

        resultado = dashboard_logic.carregar_diaristas_por_pa()

        self.assertEqual(resultado, {"PA HUBNORTE-SP": 3, "PA HUBSUL-RJ": 5})


if __name__ == "__main__":
    unittest.main()

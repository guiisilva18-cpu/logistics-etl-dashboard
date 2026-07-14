import unittest

import pandas as pd

import processar


class IdentificarTipoTests(unittest.TestCase):
    def test_sem_coleta_vence_mesmo_contendo_a_palavra_coleta(self):
        # "sem_coleta" precisa ser checado antes de "coleta", já que o
        # nome do arquivo de sem-coleta também contém a palavra "coleta".
        self.assertEqual(processar.identificar_tipo("Sem_Coleta_27060820260630124906.xlsx"), "sem_coleta")
        self.assertEqual(processar.identificar_tipo("Não_Coletado_Lista_123456.xlsx"), "sem_coleta")

    def test_coleta_e_bipagem_mapeiam_para_coleta(self):
        self.assertEqual(processar.identificar_tipo("Coleta_27060820260630124906.xlsx"), "coleta")
        self.assertEqual(
            processar.identificar_tipo("Monitoramento_de_bipagem_de_coleta_Lista_27060820260630124906.xlsx"),
            "coleta",
        )

    def test_fallback_gera_slug_removendo_sufixo_numerico(self):
        tipo = processar.identificar_tipo("Relatorio_Qualquer_123456789.xlsx")
        self.assertEqual(tipo, "relatorio_qualquer")

    def test_fallback_sem_nome_valido_usa_relatorio_desconhecido(self):
        self.assertEqual(processar.identificar_tipo("---.xlsx"), "relatorio_desconhecido")


class NormalizarNomeTests(unittest.TestCase):
    def test_colapsa_espacos_e_deixa_maiusculo(self):
        self.assertEqual(processar.normalizar_nome("  joão   da  silva "), "JOÃO DA SILVA")

    def test_none_e_nan_viram_string_vazia(self):
        self.assertEqual(processar.normalizar_nome(None), "")
        self.assertEqual(processar.normalizar_nome(float("nan")), "")


class DeduplicarTests(unittest.TestCase):
    def test_com_chave_mantem_a_versao_mais_recente(self):
        df = pd.DataFrame({
            "Remessa": ["A", "A", "B"],
            "status": ["antigo", "novo", "unico"],
        })
        resultado = processar._deduplicar(df, "Remessa")
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado.loc[resultado["Remessa"] == "A", "status"].iloc[0], "novo")

    def test_sem_chave_deduplica_por_linha_inteira(self):
        df = pd.DataFrame({
            "col": ["x", "x", "y"],
            "_arquivo_origem": ["arq1.xlsx", "arq2.xlsx", "arq1.xlsx"],
        })
        resultado = processar._deduplicar(df, None)
        # As duas linhas "x" são idênticas fora de _arquivo_origem, então
        # a deduplicação por linha inteira as trata como duplicatas.
        self.assertEqual(len(resultado), 2)


class DetectarChaveAutomaticaTests(unittest.TestCase):
    def test_detecta_coluna_com_alta_unicidade(self):
        df = pd.DataFrame({
            "id_unico": range(100),
            "categoria": ["A", "B"] * 50,
        })
        self.assertEqual(processar._detectar_chave_automatica(df), "id_unico")

    def test_retorna_none_se_nenhuma_coluna_e_unica_o_suficiente(self):
        df = pd.DataFrame({
            "categoria": ["A", "B"] * 50,
        })
        self.assertIsNone(processar._detectar_chave_automatica(df))


if __name__ == "__main__":
    unittest.main()

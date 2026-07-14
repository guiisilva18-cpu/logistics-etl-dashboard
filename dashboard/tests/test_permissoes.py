import unittest

from werkzeug.security import generate_password_hash

import config
from app_factory import app


class PermissaoColaboradoresTests(unittest.TestCase):
    def setUp(self):
        self._usuarios_originais = config.USUARIOS
        self._permissao_original = config.PERMISSAO_COLABORADORES
        senha_hash = generate_password_hash("senha123")
        config.USUARIOS = {
            "gestor": senha_hash,
            "operador1": senha_hash,
            "operador2": senha_hash,
        }
        config.PERMISSAO_COLABORADORES = {"gestor", "operador1"}

    def tearDown(self):
        config.USUARIOS = self._usuarios_originais
        config.PERMISSAO_COLABORADORES = self._permissao_original

    def _login(self, client, usuario):
        client.post("/login", data={"usuario": usuario, "senha": "senha123"})

    def test_usuario_autorizado_acessa_api_colaboradores(self):
        with app.test_client() as client:
            self._login(client, "gestor")
            resp = client.get("/api/colaboradores")
            self.assertEqual(resp.status_code, 200)

    def test_usuario_nao_autorizado_recebe_403(self):
        with app.test_client() as client:
            self._login(client, "operador2")
            resp = client.get("/api/colaboradores")
            self.assertEqual(resp.status_code, 403)

    def test_botao_de_colaboradores_some_pra_quem_nao_tem_permissao(self):
        with app.test_client() as client:
            self._login(client, "operador2")
            html = client.get("/").get_data(as_text=True)
            # Busca o elemento <button> em si — a mesma string também
            # aparece dentro do JS (querySelector), então uma busca simples
            # por "data-tipo=..." daria falso positivo.
            self.assertNotIn('<button data-tipo="__colaboradores__"', html)

    def test_botao_de_colaboradores_aparece_pra_quem_tem_permissao(self):
        with app.test_client() as client:
            self._login(client, "operador1")
            html = client.get("/").get_data(as_text=True)
            self.assertIn('<button data-tipo="__colaboradores__"', html)


if __name__ == "__main__":
    unittest.main()

import unittest

from werkzeug.security import generate_password_hash

import config
from app_factory import app


class LoginComPaginaProprioTests(unittest.TestCase):
    def setUp(self):
        self._usuarios_originais = config.USUARIOS
        config.USUARIOS = {
            "ana": generate_password_hash("senha-ana"),
            "bruno": generate_password_hash("senha-bruno"),
        }

    def tearDown(self):
        config.USUARIOS = self._usuarios_originais

    def test_sem_sessao_redireciona_para_login(self):
        with app.test_client() as client:
            resp = client.get("/")
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])

    def test_sem_sessao_rota_de_api_da_401_json(self):
        with app.test_client() as client:
            resp = client.get("/api/tipos")
            self.assertEqual(resp.status_code, 401)

    def test_pagina_de_login_fica_acessivel_sem_sessao(self):
        with app.test_client() as client:
            resp = client.get("/login")
            self.assertEqual(resp.status_code, 200)

    def test_login_com_senha_errada_nao_entra(self):
        with app.test_client() as client:
            resp = client.post("/login", data={"usuario": "ana", "senha": "errada"})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("inválidos", resp.get_data(as_text=True))
            # continua sem sessão válida
            self.assertEqual(client.get("/").status_code, 302)

    def test_login_correto_da_acesso_e_cada_usuario_com_sua_senha(self):
        with app.test_client() as client_ana:
            resp = client_ana.post("/login", data={"usuario": "ana", "senha": "senha-ana"})
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(client_ana.get("/").status_code, 200)

        with app.test_client() as client_bruno:
            resp = client_bruno.post("/login", data={"usuario": "bruno", "senha": "senha-bruno"})
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(client_bruno.get("/").status_code, 200)

    def test_senha_de_um_nao_funciona_pro_outro(self):
        with app.test_client() as client:
            resp = client.post("/login", data={"usuario": "ana", "senha": "senha-bruno"})
            self.assertIn("inválidos", resp.get_data(as_text=True))

    def test_logout_derruba_a_sessao(self):
        with app.test_client() as client:
            client.post("/login", data={"usuario": "ana", "senha": "senha-ana"})
            self.assertEqual(client.get("/").status_code, 200)

            client.get("/logout")
            resp = client.get("/")
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])


class LoginDesativadoSemUsuariosTests(unittest.TestCase):
    def setUp(self):
        self._usuarios_originais = config.USUARIOS
        config.USUARIOS = {}

    def tearDown(self):
        config.USUARIOS = self._usuarios_originais

    def test_sem_usuarios_configurados_nao_pede_login(self):
        with app.test_client() as client:
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()

import unittest

import config
from app_factory import create_app


class AppStructureTests(unittest.TestCase):
    def setUp(self):
        # Este teste verifica só a estrutura da app, não o login (isso já
        # é coberto por test_auth.py) — desativa login pra não depender
        # da senha real configurada em produção.
        self._usuarios_originais = config.USUARIOS
        config.USUARIOS = {}

    def tearDown(self):
        config.USUARIOS = self._usuarios_originais

    def test_factory_creates_flask_app(self):
        app = create_app()
        self.assertTrue(hasattr(app, "url_map"))

        client = app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()

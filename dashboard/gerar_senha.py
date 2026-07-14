"""Gera o hash de uma senha para colar em config.py (dicionário USUARIOS).

Uso:  python gerar_senha.py
"""

from getpass import getpass

from werkzeug.security import generate_password_hash

if __name__ == "__main__":
    senha = getpass("Digite a senha (não aparece na tela): ")
    if not senha:
        print("Senha vazia, nada gerado.")
    else:
        print("\nCole isto em config.py, na linha da pessoa:\n")
        print(generate_password_hash(senha))

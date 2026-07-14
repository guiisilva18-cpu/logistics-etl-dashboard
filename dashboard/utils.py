"""Utilitários pequenos compartilhados entre app_factory.py e as telas."""

from werkzeug.security import check_password_hash

import config


def login_exigido() -> bool:
    """Se False, ninguém precisa fazer login (config.USUARIOS vazio)."""
    return bool(config.USUARIOS)


def verificar_credenciais(usuario: str, senha: str) -> bool:
    """True se usuário/senha batem com algum cadastro em config.USUARIOS."""
    hash_esperado = config.USUARIOS.get(usuario)
    if not hash_esperado:
        return False
    return check_password_hash(hash_esperado, senha)


def usuario_logado(session) -> bool:
    """True se a sessão atual (cookie de login) é de um usuário válido."""
    if not login_exigido():
        return True
    return session.get("usuario") in config.USUARIOS


def pode_ver_colaboradores(usuario: str | None) -> bool:
    """Só quem está em config.PERMISSAO_COLABORADORES vê custo/desempenho
    por pessoa. Sem login configurado, não há como restringir por
    usuário, então libera pra todo mundo."""
    if not login_exigido():
        return True
    return usuario in config.PERMISSAO_COLABORADORES


def mensagem_erro(e: Exception) -> str:
    """Mensagem de erro a devolver ao cliente HTTP.

    Com config.DEBUG=True mostra a exceção completa (útil rodando
    localmente); com False mostra algo genérico, já que o dashboard pode
    ficar acessível via ngrok e a mensagem da exceção pode conter
    caminhos/detalhes internos. O traceback completo sempre vai pro log
    (chame log.exception antes de usar esta função).
    """
    if config.DEBUG:
        return f"{type(e).__name__}: {e}"
    return "Erro interno no servidor. Veja os logs para detalhes."

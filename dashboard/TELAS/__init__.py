from .auth import bp_auth
from .colaboradores import bp_colaboradores
from .operacoes import bp_operacoes
from .principal import bp_principal
from .sem_coleta import bp_sem_coleta

__all__ = [
    "bp_auth",
    "bp_colaboradores",
    "bp_operacoes",
    "bp_principal",
    "bp_sem_coleta",
]

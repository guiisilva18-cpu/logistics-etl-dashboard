# dashboard/ — NovaRota Ops

Dashboard interno (Flask) com Visão Geral, Monitoramento de Coleta, Sem
Coleta, KPIs por PA e Desempenho por Colaborador (custo/eficiência). Lê os
dados do mesmo MySQL alimentado pelo `pipeline/` (ver raiz do repo).

## Estrutura
- `app.py`: ponto de entrada para iniciar o aplicativo (serve com waitress).
- `app_factory.py`: criação da aplicação Flask e registro das telas.
- `dashboard_logic.py`: lógica de negócio e montagem dos dados para o dashboard.
- `mysql_source.py`: acesso ao MySQL (com cache em memória por TTL).
- `processar.py`: leitura, normalização e consolidação de relatórios .xlsx genéricos.
- `TELAS/`: módulos separados por tela ou funcionalidade (blueprints Flask).
- `config.py`: configuração do projeto, pastas de entrada, custos e nomes de colunas dos relatórios.
- `utils.py`: pequenos helpers compartilhados entre as telas.

Defina `config.DEBUG = True` para ver a mensagem completa de exceções nas
respostas de erro da API (útil rodando localmente); deixe `False` quando o
dashboard estiver acessível pela rede, para não vazar detalhes internos.

## Login (uma senha por pessoa)

O dashboard pede usuário e senha sempre que `config.USUARIOS` tiver alguém
cadastrado. Usuário de demonstração deste repositório: **demo / demo1234**.

Para cadastrar ou trocar uma senha:

```bash
python gerar_senha.py
```

Digite a senha (não aparece na tela), copie o hash impresso e cole em
`config.py`, no dicionário `USUARIOS`:

```python
USUARIOS = {
    "ana": "scrypt:...",
    "bruno": "scrypt:...",
}
```

Se `USUARIOS` ficar vazio, ninguém precisa fazer login.

## Como executar

1. Copie `.env.example` para `.env` e preencha (mesmo banco usado pelo `pipeline/`).
2. `pip install -r requirements.txt`
3. `python app.py` (abre `http://localhost:8765` automaticamente)

## Planilha Diarista/CLT

`lideres_pa`, `diaristas_pa` e `efetivo_clt_pa` (líder, efetivo CLT e
diaristas por PA/dia) vêm de uma planilha colaborativa mantida pelo time de
operações, sincronizada automaticamente pelo `processar.py` sempre que o
arquivo em `config.PASTA_RELATORIOS` mudar (ver `sql/create_tables_dashboard.sql`).

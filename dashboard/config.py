# ============================================================
# CONFIGURAÇÃO DO NOVAROTA OPS DASHBOARD
# ============================================================

import os

from dotenv import load_dotenv

load_dotenv()

# Conexão com o mesmo MySQL alimentado pelo pipeline/ (ver raiz do repo).
# "coleta" e "sem_coleta" vêm de lá (dados_ponto_coleta/resumo_pa).
DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
    "charset": "utf8mb4",
}

# Pasta onde fica a planilha Diarista.CLT.xlsx (e, opcionalmente, outros
# tipos de relatório além de coleta/sem_coleta — mecanismo genérico de
# auto-detecção por nome de arquivo, já que essas duas vêm do MySQL agora).
# Em produção isso aponta pra uma pasta sincronizada por um serviço de nuvem
# (OneDrive/Drive/etc), já que a planilha é colaborativa entre os líderes.
PASTA_RELATORIOS = os.environ.get("PASTA_RELATORIOS", os.path.join(os.path.dirname(__file__), "dados_entrada"))

# Porta local onde o dashboard vai rodar (acesse em http://localhost:PORTA)
PORTA = int(os.environ.get("PORTA", 8765))

# A cada quantos segundos o navegador checa se há dados novos sozinho
INTERVALO_ATUALIZACAO_SEGUNDOS = 60

# Se True, erros inesperados mostram a mensagem completa da exceção na
# tela. Deixe False quando o dashboard estiver acessível pela rede/internet,
# para não vazar detalhes internos; ligue só para depurar localmente.
DEBUG = False

# ============================================================
# LOGIN DO DASHBOARD (usuário e senha por pessoa)
# ============================================================
# Chave usada pra assinar o cookie de sessão de login. Gerada uma vez e
# fixa aqui pra não deslogar todo mundo a cada reinício do servidor.
# Não compartilhe esse valor — quem o tiver pode forjar sessões de login.
# Em produção isso deve vir de uma variável de ambiente, não ficar hardcoded.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-troque-em-producao")

# Um usuário e senha para cada pessoa que acessa o dashboard (pede login
# no navegador na primeira visita). Se USUARIOS estiver vazio, ninguém
# precisa fazer login (não recomendado se o dashboard ficar acessível
# publicamente).
#
# Para adicionar/trocar uma senha:
#   1. Rode:  python gerar_senha.py
#   2. Digite a senha da pessoa quando pedir (ela não aparece na tela)
#   3. Cole o hash gerado aqui, na linha da pessoa
#
# As senhas NUNCA ficam em texto puro aqui — só o hash. Sem o hash não
# dá pra saber qual é a senha original.
#
# Usuário/senha de demonstração deste repositório: demo / demo1234
USUARIOS = {
    "demo": "scrypt:32768:8:1$agayaRphor83m00i$b18d89d500eb11f787ed6be0354eaad020326b843f47beec7898b94a193bacb94d0db348e5a4f03f704f1468a3a6d1fd8477dd67cc19be2dd533d8e96fc3b9c8",
}

# Quem pode ver a tela "Desempenho por Colaborador" (ranking e detalhe
# individual, com custo por pessoa). Quem não estiver aqui só vê Visão
# Geral e KPIs por PA. Nomes de usuário, iguais às chaves de USUARIOS.
PERMISSAO_COLABORADORES = {"demo"}

# ============================================================
# REGISTRO DE TIPOS DE RELATÓRIO
# ============================================================
# O sistema detecta automaticamente o tipo de cada relatório pelo
# nome do arquivo. Aqui você pode opcionalmente configurar, por tipo:
#   - "chave_unica": nome da coluna que identifica um registro de
#     forma única (evita duplicar quando o mesmo registro aparece em
#     vários downloads). Se não souber/não tiver, deixe None — o
#     sistema tenta detectar automaticamente.
#   - "nome_exibicao": nome bonito mostrado no dashboard.
#
# O identificador de "tipo" (a chave deste dicionário) é gerado a
# partir do nome do arquivo baixado, removendo o sufixo numérico/
# timestamp do final. Para descobrir qual chave usar para um
# relatório novo, basta deixar ele ser processado uma vez (vai
# aparecer em /api/tipos) e copiar o "tipo" de lá para cá.
TIPOS_CONFIG = {
    # Arquivos: "Coleta_DD.MM.YYYY.xlsx" ou similar
    "coleta": {
        "chave_unica": "Remessa",
        "nome_exibicao": "Monitoramento de Coleta",
    },
    # Arquivos: "Sem_Coleta_DD.MM.YYYY.xlsx" ou similar
    "sem_coleta": {
        "chave_unica": "Remessa",
        "nome_exibicao": "Sem Coleta",
    },
    # Exemplo de como adicionar outro relatório:
    # "slug_do_arquivo": {
    #     "chave_unica": "NomeDaColunaUnica",
    #     "nome_exibicao": "Nome Bonito do Relatório",
    # },
}

# ============================================================
# NOMES DE COLUNAS DO RELATÓRIO DE COLETA/BIPAGEM
# ============================================================
# Centralizados aqui porque aparecem em vários pontos de
# dashboard_logic.py. Se o fornecedor mudar o nome de alguma coluna no
# relatório baixado, o ajuste é só aqui. Os nomes em chinês vêm do
# relatório de bipagem original do fornecedor da plataforma (comum em
# integrações com sistemas logísticos de origem asiática).
COL_REMESSA = "Remessa"
COL_BASE = "Nome da base"
COL_DATA_HORA_COLETA = "Data e hora da encomenda Coletada"
COL_COLETADO = "收件标识1：已收件"  # marcador: "1: já coletado"
COL_DESPACHADO = "发件标识1：已发件标识"  # marcador: "1: já despachado"
COL_NOME_COLETADOR = "收件员名称"  # nome do coletador, na planilha original

# ============================================================
# CUSTOS DE MÃO DE OBRA (valores de exemplo — não são dados reais)
# ============================================================
# Custo médio por colaborador CLT por dia
CUSTO_CLT_DIA = 180.00

# Custo médio por diarista por dia
CUSTO_DIARISTA_DIA = 240.00


CUSTO_POR_PACOTE = 0.0

# ============================================================
# ALERTA DE % FALTA DE BIPAGEM
# ============================================================
# Acima desse percentual, a PA entra no banner de risco em "KPIs por PA"
# (pensado pra leitura rápida por diretoria/coordenação).
LIMITE_ALERTA_PCT_FALTA = 15.0

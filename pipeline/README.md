# pipeline/ — ETL diário

Busca os pedidos de coleta do dia anterior no portal interno da
transportadora e carrega em duas tabelas MySQL. Ver a raiz do repositório
para o contexto completo (arquitetura, decisões, como isso alimenta o
`dashboard/`).

## Arquivos
- `extract.py` — dispara a exportação assíncrona, faz polling do status e baixa a planilha gerada
- `load.py` — sobrescreve `dados_ponto_coleta` (TRUNCATE + INSERT) e recalcula `resumo_pa` (DELETE + INSERT do dia)
- `main.py` — orquestra os dois passos, loga em `logs/execucao.log`
- `sql/create_tables.sql` — cria o schema e as duas tabelas

## Setup
1. Copie `.env.example` para `.env` e preencha as credenciais.
2. Rode `sql/create_tables.sql` no banco de destino.
3. `pip install -r requirements.txt`
4. `python main.py` (busca e carrega o dia anterior)

## Por que exportação assíncrona em vez de paginar a API diretamente?
A consulta interativa (listagem paginada) tem um teto de volume — acima de
um certo número de registros por consulta, a API recusa. Para volumes
reais (centenas de milhares de pedidos/dia) é preciso usar o mecanismo de
exportação em lote: disparar a geração do arquivo, fazer polling de um
endpoint de status até o job ficar pronto, e então baixar o arquivo via
uma URL assinada temporária. Esse padrão (job assíncrono + polling +
download por URL assinada) é comum em integrações com sistemas legados que
não expõem uma API de exportação em massa direta.

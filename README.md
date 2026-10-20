# Logistics ETL + Ops Dashboard

[![CI](https://github.com/guiisilva18-cpu/logistics-etl-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/guiisilva18-cpu/logistics-etl-dashboard/actions/workflows/ci.yml)

Pipeline diário (ETL) + dashboard operacional para monitoramento de coleta
de encomendas em uma rede de pontos de apoio (PAs/hubs) de uma
transportadora. Adaptado de um projeto que rodo em produção — nomes de
empresa, sistema, clientes e todos os números aqui são **fictícios**;
código e decisões de arquitetura são os mesmos.

```
┌────────────────┐      exportação      ┌──────────────┐      leitura       ┌───────────────┐
│ Portal interno  │ ──assíncrona──────▶ │  pipeline/    │ ──────────────▶  │  dashboard/    │
│ da transporta-  │  (job + polling +   │  (Python)     │   (MySQL)         │  (Flask)       │
│ dora (RotaWeb)  │   URL assinada)     │               │◀── planilha ────  │                │
└────────────────┘                      └──────┬────────┘  Diarista/CLT    └───────┬────────┘
                                                 │                                   │
                                                 ▼                                   ▼
                                          MySQL: dados_ponto_coleta            navegador (4 usuários,
                                          resumo_pa, lideres_pa,               login por pessoa)
                                          efetivo_clt_pa, diaristas_pa
```

## O problema

A rede tem dezenas de PAs recebendo centenas de milhares de pedidos por
dia. A operação precisa saber, por PA e em tempo quase real: quanto já foi
coletado, quanto falta, qual líder responde por qual PA, e qual o
custo/eficiência de cada equipe (CLT + diaristas) frente ao volume
coletado.

## Decisões de arquitetura (e por quê)

**Exportação assíncrona em vez de paginar a API diretamente.**
A consulta interativa do portal tem um teto de volume por requisição — acima
de um certo número de registros ela recusa o pedido. Pra volumes reais
(centenas de milhares/dia) é preciso: disparar um job de exportação em
lote → fazer polling de um endpoint de status até o job terminar → baixar
o arquivo via uma URL assinada temporária. Ver `pipeline/extract.py`.

**Tabela de detalhe sobrescrita, tabela de resumo com histórico.**
`dados_ponto_coleta` (pedido a pedido) é `TRUNCATE + INSERT` a cada carga —
sem histórico, sem custo de armazenamento crescente. `resumo_pa` (uma
linha por PA/dia) acumula histórico porque o custo é desprezível e é o que
alimenta as tendências no dashboard. O dia recém-carregado sempre é
substituído por inteiro (`DELETE` + `INSERT`, não `UPSERT` linha a linha),
porque os dados "de ontem" continuam sendo reclassificados pela operação
ao longo do dia seguinte — um `UPSERT` deixaria PAs "fantasma" de uma carga
anterior que não aparecem mais na mais recente.

**Cache com TTL + invalidação explícita no dashboard.**
As tabelas de referência só mudam quando a carga diária roda ou alguém
edita a planilha — não faz sentido bater no banco a cada refresh de 60s do
navegador, multiplicado por aba/usuário. `mysql_source.py` cacheia por TTL
e invalida na hora quando algo é escrito (ex: sincronização da planilha).

**Conexão MySQL persistente por thread.** O servidor (waitress, múltiplas
threads) reaproveita uma conexão por thread em vez de abrir uma nova a
cada consulta — abrir conexão pra cada request deixava cada tela do
dashboard visivelmente lenta.

## Estrutura

- [`pipeline/`](pipeline/) — busca os pedidos do dia anterior (exportação assíncrona) e carrega no MySQL.
- [`dashboard/`](dashboard/) — Flask + waitress: Visão Geral, Monitoramento de Coleta, Sem Coleta, KPIs por PA, Desempenho por Colaborador (custo/eficiência por líder).
- [`seed/`](seed/) — gera dados 100% fictícios (pedidos, PAs, líderes, CLT/diaristas) pra rodar o projeto sem precisar de acesso ao portal real.

## Como rodar (com dados fictícios)

Requisito: um MySQL acessível (local, Docker, RDS — qualquer um).

```bash
pip install -r pipeline/requirements.txt
pip install -r dashboard/requirements.txt

# .env na raiz do repo (mesmas variáveis DB_* usadas por pipeline/ e dashboard/)
cp pipeline/.env.example .env

python seed/gerar_dados_ficticios.py   # cria as tabelas e popula com dados fictícios
python dashboard/app.py                 # abre http://localhost:8765
```

Login de demonstração: **demo / demo1234**.

Pra rodar contra o portal real, preencha `pipeline/.env` com as
credenciais do seu portal (mesmo formato do `.env` acima) e rode
`python pipeline/main.py`.

## Testes

```bash
pip install -r dashboard/requirements.txt -r pipeline/requirements.txt
pytest dashboard/tests/ -v
```

- `test_app_structure.py` — a fábrica Flask (`create_app`) sobe e a rota raiz responde 200.
- `test_auth.py` — login/logout, hash de senha por usuário, sessão exigida nas rotas protegidas (inclusive resposta 401 em JSON pras rotas de API).
- `test_permissoes.py` — cada perfil de usuário só acessa as telas liberadas pra ele, e o botão de acesso só aparece na UI pra quem tem permissão.
- `test_dashboard_logic.py` — regra de negócio do cálculo de efetivo (usa quantidade de diarista, ignora quantidade de CLT).
- `test_processar.py` — classificação/normalização de nome de arquivo e planilha (coleta vs. sem-coleta, fallback de slug, tratamento de `None`/`NaN`).

O [CI](.github/workflows/ci.yml) roda essa suíte a cada push/PR contra um
MySQL de serviço do GitHub Actions, com o schema criado a partir de
`pipeline/sql/create_tables.sql` + `dashboard/sql/create_tables_dashboard.sql`
— os testes batem em banco de verdade (`dashboard_logic.py`/`TELAS/*`), não
contra um dublê, então sem esse schema eles nem coletam.

## Stack

Python, Flask, waitress, pandas, PyMySQL, MySQL 8. Front-end sem
framework (HTML/CSS/JS + Chart.js), autenticação por sessão com senha
por pessoa (hash scrypt via Werkzeug).

## Sobre os dados deste repositório

PAs, clientes, líderes, valores de custo e volumes são gerados por
[`seed/gerar_dados_ficticios.py`](seed/gerar_dados_ficticios.py) e não
representam nenhuma empresa real.

## Licença

MIT — ver [LICENSE](LICENSE).

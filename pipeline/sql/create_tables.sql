-- Execute este script uma vez no schema alvo (DBeaver, MySQL Workbench, etc).

CREATE DATABASE IF NOT EXISTS rotaweb_relatorios
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE rotaweb_relatorios;

CREATE TABLE IF NOT EXISTS dados_ponto_coleta (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    numero_pedido VARCHAR(50) NOT NULL,
    estacao_coleta VARCHAR(150),
    nome_cliente VARCHAR(200),
    base_remetente VARCHAR(150),
    data_referencia DATE,
    data_hora_coleta DATETIME,
    despachado TINYINT(1) NOT NULL DEFAULT 0,
    data_carga DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_numero_pedido (numero_pedido)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Resumo diário por PA (Ponto de Apoio/base remetente). Poucas linhas por dia
-- (uma por PA) — acumula histórico com custo de armazenamento desprezível,
-- ao contrário da tabela de detalhe acima (que é sobrescrita a cada carga).
CREATE TABLE IF NOT EXISTS resumo_pa (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    data_referencia DATE NOT NULL,
    base_remetente VARCHAR(150) NOT NULL,
    total_remessas INT NOT NULL,
    coletados INT NOT NULL,
    nao_coletados INT NOT NULL,
    UNIQUE KEY uq_data_pa (data_referencia, base_remetente)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

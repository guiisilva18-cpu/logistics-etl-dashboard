-- Tabelas de referência do dashboard, no MESMO schema usado pelo
-- pipeline/ (ver raiz do repo). Sincronizadas automaticamente a partir da planilha
-- "Diarista.CLT" (uma aba por dia) — o dashboard só lê.
-- Execute uma vez no DBeaver, conectado ao schema alvo.

-- PA -> nome do líder responsável, por dia (a planilha tem uma aba por
-- data "DD.MM" e o líder de uma PA pode mudar de um dia pro outro).
CREATE TABLE IF NOT EXISTS lideres_pa (
    data_referencia DATE NOT NULL,
    base_remetente VARCHAR(150) NOT NULL,
    lider VARCHAR(150) NOT NULL,
    PRIMARY KEY (data_referencia, base_remetente)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PA -> quantidade de diaristas atuando (efetivo temporário), por dia.
CREATE TABLE IF NOT EXISTS diaristas_pa (
    data_referencia DATE NOT NULL,
    base_remetente VARCHAR(150) NOT NULL,
    quantidade INT NOT NULL DEFAULT 0,
    PRIMARY KEY (data_referencia, base_remetente)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PA -> quantidade de efetivo CLT (usado no custo/eficiência da tela KPIs
-- por PA e Colaboradores), por dia.
CREATE TABLE IF NOT EXISTS efetivo_clt_pa (
    data_referencia DATE NOT NULL,
    base_remetente VARCHAR(150) NOT NULL,
    quantidade INT NOT NULL DEFAULT 0,
    PRIMARY KEY (data_referencia, base_remetente)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

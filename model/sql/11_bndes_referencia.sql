-- 11_bndes_referencia.sql
-- Referência de drift e prazo padrão — BNDES (Task 6 do plano v3).
--
-- Parte da staging `bndes_agregado` (model/dados/ingest_bndes.py): decis de
-- valor e de prazo (carência + amortização) por porte × seção, operações
-- indiretas automáticas MICRO/PEQUENA contratadas em 2018–2022.
--
-- Tabela final `bndes_referencia` (tidy):
--   tipo='valor'|'prazo'  → (porte, secao, quantil, valor, n); porte inclui
--                           os marginais 'TODOS'; secao inclui 'todas'
--   tipo='setor'          → distribuição de seções (proporção sobre o total
--                           MICRO+PEQUENA), porte='TODOS', quantil=NULL

CREATE OR REPLACE TABLE `${BQ_DATASET}.bndes_referencia` AS
WITH decis AS (
  SELECT 'valor' AS tipo, porte, secao,
         CAST(q AS FLOAT64) AS quantil, v AS valor, n
  FROM `${BQ_DATASET}.bndes_agregado`
  UNPIVOT (
    v FOR q IN (
      valor_q10 AS '0.1', valor_q20 AS '0.2', valor_q30 AS '0.3',
      valor_q40 AS '0.4', valor_q50 AS '0.5', valor_q60 AS '0.6',
      valor_q70 AS '0.7', valor_q80 AS '0.8', valor_q90 AS '0.9'
    )
  )
  UNION ALL
  SELECT 'prazo', porte, secao, CAST(q AS FLOAT64), v, n
  FROM `${BQ_DATASET}.bndes_agregado`
  UNPIVOT (
    v FOR q IN (
      prazo_q10 AS '0.1', prazo_q20 AS '0.2', prazo_q30 AS '0.3',
      prazo_q40 AS '0.4', prazo_q50 AS '0.5', prazo_q60 AS '0.6',
      prazo_q70 AS '0.7', prazo_q80 AS '0.8', prazo_q90 AS '0.9'
    )
  )
),
setores AS (
  SELECT secao, SUM(n) AS n
  FROM `${BQ_DATASET}.bndes_agregado`
  WHERE porte IN ('MICRO', 'PEQUENA') AND secao != 'todas'
  GROUP BY secao
)
SELECT * FROM decis
UNION ALL
SELECT
  'setor' AS tipo,
  'TODOS' AS porte,
  secao,
  NULL AS quantil,
  n / SUM(n) OVER () AS valor,
  n
FROM setores;

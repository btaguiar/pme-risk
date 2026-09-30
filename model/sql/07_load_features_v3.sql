-- 07_load_features_v3.sql
-- Feature set v3 — SBA 7(a) (troca a base: Home Credit → PME americana)
-- Referência: docs/superpowers/plans/2026-09-29-modelo-v3-sba.md,
--             docs/dados/levantamento-bases-pme-2026-09-29.md, model/features.py
-- Tabela nova (features_v3): o v2 continua reprodutível a partir de features_v2.
--
-- Recorte (decisões do plano):
--   D1 — rótulo CHGOFF=1 × PIF=0; EXEMPT (censura), CANCLD e COMMIT fora
--   D2 — safras FY2010–2015 (EXEMPT ≤ 5,1% por safra)
--   D4 — só empréstimo a prazo (RevolverStatus = 'N')
--   D5 — split temporal: treino FY2010–2013, holdout FY2014–2015
--
-- VAZAMENTO (D3): TermInMonths fica DE FORA — prazo "quebrado" tem 33,64% de
-- CHGOFF contra 0,91% do redondo (regra regravada depois do problema). O
-- teste tests/unit/test_features_v3.py guarda isso.
--
-- Mapeamentos (Task 2) vêm das tabelas carregadas por
-- model/dados/carregar_mapeamentos_bq.py a partir de model/mapeamentos.py.

CREATE OR REPLACE TABLE `${BQ_DATASET}.features_v3` AS
WITH recorte AS (
  SELECT
    approval_fy,
    gross_approval,
    IF(loan_status = 'CHGOFF', 1, 0) AS target,
    naics_code,
    business_age
  FROM `${BQ_DATASET}.sba_7a_raw`
  WHERE approval_fy BETWEEN 2010 AND 2015
    AND loan_status IN ('CHGOFF', 'PIF')
    AND revolver_status = 'N'
    AND gross_approval > 0  -- LN exige valor positivo
),
secoes AS (
  -- NAICS → seção CNAE pelo prefixo mais longo que casa (model/mapeamentos.py)
  SELECT
    c.naics_code,
    ARRAY_AGG(m.secao ORDER BY LENGTH(m.prefixo) DESC LIMIT 1)[OFFSET(0)] AS secao_cnae
  FROM (
    SELECT DISTINCT naics_code
    FROM recorte
    WHERE naics_code IS NOT NULL AND naics_code != ''
  ) c
  JOIN `${BQ_DATASET}.naics_para_secao` m
    ON STARTS_WITH(c.naics_code, m.prefixo)
  GROUP BY c.naics_code
)
SELECT
  s.secao_cnae,
  COALESCE(f.faixa, 'desconhecida') AS faixa_idade,
  LN(r.gross_approval) AS log_valor_usd,
  r.target,
  IF(r.approval_fy <= 2013, 'train', 'holdout') AS split,
  r.approval_fy  -- metadado do eval por safra; nunca entra no SQL de treino
FROM recorte r
JOIN secoes s USING (naics_code)
LEFT JOIN `${BQ_DATASET}.business_age_para_faixa` f USING (business_age);

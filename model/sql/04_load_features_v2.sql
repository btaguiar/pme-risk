-- 04_load_features_v2.sql
-- Feature set v2 — corrige dois skews treino/serviço do v1 (docs/eval/avaliacao-2026-09-28.md)
-- Referência: SPEC §3.3.4, model/features.py
-- Tabela nova (features_v2): o v1 continua reprodutível a partir de `features`.
--
-- 1. DAYS_EMPLOYED = 365243 é sentinela do Home Credit (aposentado/sem vínculo,
--    ~18% das linhas). No v1 virava days_employed_abs = 365243 (~1.000 anos),
--    inflando a média e invertendo o sinal da atribuição no serviço.
--    v2: anos_operacao = NULL (imputado pela média no BQML) + flag explícita.
-- 2. days_employed_abs saiu: no serviço é exatamente anos_operacao * 365.25
--    (colinear) — o laudo explicava a mesma informação como dois fatores.
-- 3. occupation_type_encoded saiu: setor PME não tem análogo em OCCUPATION_TYPE
--    e um hash usado como número contínuo dá risco arbitrário por setor.

CREATE OR REPLACE TABLE `${BQ_DATASET}.features_v2` AS
SELECT
  sk_id_curr,
  AMT_INCOME_TOTAL AS amt_income_total,
  AMT_CREDIT AS amt_credit,
  AMT_ANNUITY AS amt_annuity,

  -- Prazo estimado em meses (HC não tem prazo explícito)
  LEAST(SAFE_DIVIDE(AMT_CREDIT, NULLIF(AMT_ANNUITY, 0)), 120) AS prazo_meses_estimado,

  -- Anos de operação (proxy: DAYS_EMPLOYED) — sentinela vira NULL
  IF(DAYS_EMPLOYED = 365243, NULL,
     LEAST(GREATEST(-DAYS_EMPLOYED / 365.25, 0), 60)) AS anos_operacao,

  -- Sem vínculo registrado (sentinela). No serviço é sempre 0: PME em operação.
  IF(DAYS_EMPLOYED = 365243, 1, 0) AS sem_emprego_registrado,

  -- Região (proxy de UF)
  REGION_RATING_CLIENT AS region_rating,

  CAST(TARGET AS INT64) AS target,

  -- Mesmo split do v1 (holdout idêntico → métricas comparáveis)
  CASE
    WHEN MOD(ABS(FARM_FINGERPRINT(CAST(sk_id_curr AS STRING))), 100) < 80 THEN 'train'
    ELSE 'holdout'
  END AS split

FROM `${BQ_DATASET}.home_credit_raw`
WHERE TARGET IS NOT NULL;

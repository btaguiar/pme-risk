-- 01_load_features.sql
-- Materializa as features transformadas + split determinístico
-- Referência: SPEC §3.3.4, model/features.py
-- IMPORTANTE: materializar UMA vez para não consumir cota de query a cada treino

CREATE OR REPLACE TABLE `${BQ_DATASET}.features` AS
SELECT
  sk_id_curr,
  -- Features numéricas
  AMT_INCOME_TOTAL AS amt_income_total,
  AMT_CREDIT AS amt_credit,
  AMT_ANNUITY AS amt_annuity,

  -- Prazo estimado em meses (HC não tem prazo explícito)
  LEAST(SAFE_DIVIDE(AMT_CREDIT, NULLIF(AMT_ANNUITY, 0)), 120) AS prazo_meses_estimado,

  -- Anos de operação (proxy: DAYS_EMPLOYED convertido)
  LEAST(GREATEST(-DAYS_EMPLOYED / 365.25, 0), 60) AS anos_operacao,

  -- Dias de emprego (absoluto)
  ABS(DAYS_EMPLOYED) AS days_employed_abs,

  -- Ocupação (aproximação de setor) — usar FARM_FINGERPRINT para encoding determinístico
  MOD(ABS(FARM_FINGERPRINT(IFNULL(OCCUPATION_TYPE, 'UNKNOWN'))), 100) AS occupation_type_encoded,

  -- Região (proxy de UF)
  REGION_RATING_CLIENT AS region_rating,

  -- Alvo
  CAST(TARGET AS INT64) AS target,

  -- Split determinístico via hash do ID (80/20)
  CASE
    WHEN MOD(ABS(FARM_FINGERPRINT(CAST(sk_id_curr AS STRING))), 100) < 80 THEN 'train'
    ELSE 'holdout'
  END AS split

FROM `${BQ_DATASET}.home_credit_raw`
WHERE TARGET IS NOT NULL;

-- 02_train_baseline_logreg.sql
-- Baseline: regressão logística (PLANO §5 — baseline obrigatório)
-- Referência: SPEC §3.4

CREATE OR REPLACE MODEL `${BQ_DATASET}.logreg_baseline`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['target'],
  max_iterations = 20,
  learn_rate_strategy = 'LINE_SEARCH',
  early_stop = TRUE,
  min_rel_progress = 0.001,
  data_split_method = 'NO_SPLIT'  -- já temos coluna split pré-definida
) AS
SELECT
  amt_income_total,
  amt_credit,
  amt_annuity,
  prazo_meses_estimado,
  anos_operacao,
  days_employed_abs,
  occupation_type_encoded,
  region_rating,
  target
FROM `${BQ_DATASET}.features`
WHERE split = 'train';

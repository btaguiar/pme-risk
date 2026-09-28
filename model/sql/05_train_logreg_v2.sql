-- 05_train_logreg_v2.sql
-- LOGISTIC_REG sobre features_v2 (ver 04_load_features_v2.sql)
-- Mesmos hiperparâmetros do baseline v1 — muda só o feature set.

CREATE OR REPLACE MODEL `${BQ_DATASET}.logreg_v2`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['target'],
  max_iterations = 20,
  learn_rate_strategy = 'LINE_SEARCH',
  early_stop = TRUE,
  min_rel_progress = 0.001,
  data_split_method = 'NO_SPLIT'
) AS
SELECT
  amt_income_total,
  amt_credit,
  amt_annuity,
  prazo_meses_estimado,
  anos_operacao,
  sem_emprego_registrado,
  region_rating,
  target
FROM `${BQ_DATASET}.features_v2`
WHERE split = 'train';

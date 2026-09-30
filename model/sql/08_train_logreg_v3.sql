-- 08_train_logreg_v3.sql
-- LOGISTIC_REG sobre features_v3 (ver 07_load_features_v3.sql)
-- Baseline obrigatório (PLANO §5). Mesmos hiperparâmetros do v2 — muda a base.
-- Categóricas (secao_cnae, faixa_idade) são one-hot encoded pelo BQML.

CREATE OR REPLACE MODEL `${BQ_DATASET}.logreg_v3`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['target'],
  max_iterations = 20,
  learn_rate_strategy = 'LINE_SEARCH',
  early_stop = TRUE,
  min_rel_progress = 0.001,
  data_split_method = 'NO_SPLIT'  -- split temporal pré-definido (D5)
) AS
SELECT
  secao_cnae,
  faixa_idade,
  log_valor_usd,
  target
FROM `${BQ_DATASET}.features_v3`
WHERE split = 'train';

-- 03_train_candidate.sql
-- Candidato: boosted tree classifier (PLANO §5 — comparar vs baseline)
-- Referência: SPEC §3.5
-- Critério: só promover se superar KS/AUC sem piorar Brier/ECE

CREATE OR REPLACE MODEL `${BQ_DATASET}.boosted_tree_v1`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['target'],
  max_iterations = 50,
  learn_rate = 0.1,
  max_tree_depth = 6,
  subsample = 0.8,
  min_tree_child_weight = 1,
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

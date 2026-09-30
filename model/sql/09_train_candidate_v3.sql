-- 09_train_candidate_v3.sql
-- Candidato: boosted tree classifier (PLANO §5 — comparar vs baseline)
-- Critério D6: só substituir o baseline se ganhar em KS/AUC sem piorar
-- Brier/ECE no holdout temporal. Se repetir o erro 80038528 do BQML,
-- registrar e seguir só com o baseline (já aconteceu no v1).

CREATE OR REPLACE MODEL `${BQ_DATASET}.boosted_tree_v3`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['target'],
  max_iterations = 50,
  learn_rate = 0.1,
  max_tree_depth = 6,
  subsample = 0.8,
  min_tree_child_weight = 1,
  data_split_method = 'NO_SPLIT'  -- split temporal pré-definido (D5)
) AS
SELECT
  secao_cnae,
  faixa_idade,
  log_valor_usd,
  target
FROM `${BQ_DATASET}.features_v3`
WHERE split = 'train';

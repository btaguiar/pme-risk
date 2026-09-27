#!/usr/bin/env bash
# Setup BigQuery dataset for pme-risk
# Idempotente — pode rodar múltiplas vezes
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
DATASET="${BQ_DATASET:-pme_risk}"
LOCATION="${BQ_LOCATION:-US}"

echo "Criando dataset ${DATASET} em ${PROJECT_ID} (${LOCATION})..."

bq --project_id="${PROJECT_ID}" mk \
  --dataset \
  --location="${LOCATION}" \
  --description="pme-risk: features, modelos, laudos, auditoria" \
  "${PROJECT_ID}:${DATASET}" || echo "Dataset já existe."

echo "Criando tabela model_registry..."

bq --project_id="${PROJECT_ID}" query \
  --use_legacy_sql=false \
  "CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.model_registry\` (
    model_version STRING NOT NULL,
    algoritmo STRING NOT NULL,
    feature_set_version STRING NOT NULL,
    treinado_em TIMESTAMP NOT NULL,
    ks FLOAT64,
    auc FLOAT64,
    brier FLOAT64,
    ece FLOAT64,
    status STRING NOT NULL,
    nota STRING
  )"

echo "Criando tabela laudos..."

bq --project_id="${PROJECT_ID}" query \
  --use_legacy_sql=false \
  "CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.laudos\` (
    laudo_id STRING NOT NULL,
    pedido_bruto STRING,
    enriquecidos_json STRING,
    resultado_modelo_json STRING,
    texto STRING,
    evidencias_json STRING,
    status STRING NOT NULL,
    decidido_por STRING,
    decidido_em TIMESTAMP,
    decisao STRING,
    observacao_humana STRING,
    criado_em TIMESTAMP NOT NULL
  )"

echo "Criando tabela trilha_auditoria..."

bq --project_id="${PROJECT_ID}" query \
  --use_legacy_sql=false \
  "CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.trilha_auditoria\` (
    laudo_id STRING NOT NULL,
    pedido_bruto STRING,
    model_version STRING,
    prompts_usados STRING,
    decisao_humana STRING,
    etapas_json STRING,
    criado_em TIMESTAMP NOT NULL
  )"

echo "Setup concluído."

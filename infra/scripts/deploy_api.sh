#!/usr/bin/env bash
# Deploy da API pme-risk no Cloud Run (SPEC §5.2)
# Idempotente — pode rodar múltiplas vezes. Requer: gcloud autenticado + ADC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
SERVICE="${RUN_SERVICE:-pme-risk-api}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT (ex: pme-risk-api@<proj>.iam.gserviceaccount.com)}"
# Fail-closed: sem API_KEY_SECRET o deploy falha — POST /laudos custa Gemini + BQ
API_KEY="${API_KEY_SECRET:?Defina API_KEY_SECRET (header X-API-Key da demo pública)}"

# Papel mínimo para a API ler/escrever BigQuery (idempotente: falha silenciosa se já existe)
for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

# Demo pública com segredo compartilhado: POST /laudos exige header X-API-Key
# (GET/healthz continuam abertos). Trocar por auth real antes de uso produtivo.
gcloud run deploy "${SERVICE}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${BQ_DATASET:-pme_risk},API_KEY_SECRET=${API_KEY}" \
  --min-instances=0 \
  --max-instances=1 \
  --allow-unauthenticated

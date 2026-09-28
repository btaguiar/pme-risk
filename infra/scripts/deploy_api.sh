#!/usr/bin/env bash
# Deploy da API pme-risk no Cloud Run (SPEC §5.2)
# Idempotente — pode rodar múltiplas vezes. Requer: gcloud autenticado + ADC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
SERVICE="${RUN_SERVICE:-pme-risk-api}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT (ex: pme-risk-api@<proj>.iam.gserviceaccount.com)}"
# Fail-closed: sem API_KEY_SECRET o deploy falha — POST /laudos custa Gemini + BQ
API_KEY="${API_KEY_SECRET:?Defina API_KEY_SECRET (header X-API-Key)}"

# Papel mínimo para a API funcionar: BigQuery (laudos/auditoria/modelo) e
# Vertex AI (Gemini do Extrator/Redator). Idempotente: falha silenciosa se já existe.
# aiplatform.user faltava na 1ª rodada — pego em review; validado com token da SA.
for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

# APIs exigidas em runtime (idempotente — aiplatform faltava na 1ª rodada de review)
gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com run.googleapis.com \
  --project="${PROJECT_ID}" >/dev/null

# Imagem do docker/Dockerfile (a mesma validada localmente) — exporta IMAGE
source "$(dirname "$0")/build_image.sh"

# Privado por padrão: só identidades com roles/run.invoker chamam o serviço
# (curl -H "Authorization: Bearer $(gcloud auth print-identity-token)").
# ALLOW_UNAUTHENTICATED=1 abre a demo pública — aí o X-API-Key é a única barreira
# do POST /laudos (GET/healthz ficam abertos).
if [ "${ALLOW_UNAUTHENTICATED:-0}" = "1" ]; then
  AUTH_FLAG="--allow-unauthenticated"
else
  AUTH_FLAG="--no-allow-unauthenticated"
fi

# GCP_PROJECT_ID é lido em runtime pelo pipeline (Cloud Run não o injeta)
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET:-pme_risk},API_KEY_SECRET=${API_KEY}" \
  --min-instances=0 \
  --max-instances=1 \
  "${AUTH_FLAG}"

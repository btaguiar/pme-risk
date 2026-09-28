#!/usr/bin/env bash
# Deploy do job de drift: Cloud Run Job + Cloud Scheduler semanal (SPEC §5.3)
# Idempotente — cria ou atualiza. Cron: segundas 12:00 UTC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
JOB="${DRIFT_JOB_NAME:-pme-risk-drift}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT}"
DATASET="${BQ_DATASET:-pme_risk}"
SCHED="${DRIFT_SCHEDULER_NAME:-pme-risk-drift-weekly}"
SCHEDULE="0 12 * * 1"
JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run"

# APIs do job + Scheduler. Sem isso o `scheduler jobs create` para num prompt
# interativo "enable API? (y/N)" escondido pelo 2>/dev/null (visto em 2026-09-28)
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  --project="${PROJECT_ID}" >/dev/null

# Mesma imagem da API (docker/Dockerfile) — exporta IMAGE
source "$(dirname "$0")/build_image.sh"

gcloud run jobs create "${JOB}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="-m,monitoring.drift_job" \
  --max-retries=1 2>/dev/null || \
gcloud run jobs update "${JOB}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="-m,monitoring.drift_job"

# Scheduler precisa invocar o job em nome da service account
# (papéis BQ a nível de projeto; roles/run.invoker a nível do JOB.
# "roles/cloudrun.invoker" não existe — falha com INVALID_ARGUMENT, visto em 2026-09-28)
for ROLE in roles/bigquery.dataViewer roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

# Invoker no recurso do job (idempotente) — sem ele o Scheduler recebe 403
gcloud run jobs add-iam-policy-binding "${JOB}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member="serviceAccount:${SA}" \
  --role="roles/run.invoker" >/dev/null

gcloud scheduler jobs create http "${SCHED}" \
  --location="${REGION}" \
  --schedule="${SCHEDULE}" \
  --uri="${JOB_URI}" \
  --oauth-service-account-email="${SA}" 2>/dev/null || \
gcloud scheduler jobs update http "${SCHED}" \
  --location="${REGION}" \
  --schedule="${SCHEDULE}" \
  --uri="${JOB_URI}" \
  --oauth-service-account-email="${SA}"

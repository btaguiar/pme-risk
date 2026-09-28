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

gcloud run jobs create "${JOB}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="monitoring/drift_job.py" \
  --max-retries=1 2>/dev/null || \
gcloud run jobs update "${JOB}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="monitoring/drift_job.py"

# Scheduler precisa invocar o job em nome da service account
for ROLE in roles/bigquery.dataViewer roles/bigquery.jobUser roles/cloudrun.invoker; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

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

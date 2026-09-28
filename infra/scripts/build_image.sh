#!/usr/bin/env bash
# Build da imagem pme-risk no Cloud Build + push no Artifact Registry.
# Usado por deploy_api.sh e deploy_drift.sh (mesma imagem para API e job).
# Idempotente. Exporta IMAGE com a tag do commit atual.
# IMAGE já definida → reaproveita essa imagem e pula o build.
set -euo pipefail

if [ -n "${IMAGE:-}" ]; then
  echo "Usando imagem existente: ${IMAGE}"
  export IMAGE
  return 0 2>/dev/null || exit 0
fi

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
REPO="${AR_REPO:-pme-risk}"
TAG="$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . ':!docs' || echo -dirty)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/api:${TAG}"
export IMAGE

gcloud services enable artifactregistry.googleapis.com cloudbuild.googleapis.com \
  --project="${PROJECT_ID}" >/dev/null

gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --description="Imagens pme-risk (API + job de drift)"

gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --config=infra/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE}"

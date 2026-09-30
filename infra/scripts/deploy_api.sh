#!/usr/bin/env bash
# Deploy da API pme-risk no Cloud Run (SPEC §5.2)
# Idempotente — pode rodar múltiplas vezes. Requer: gcloud autenticado + ADC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
SERVICE="${RUN_SERVICE:-pme-risk-api}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT (ex: pme-risk-api@<proj>.iam.gserviceaccount.com)}"
# Segredo do header X-API-Key no Secret Manager — nunca em env var em texto puro
# (ficava legível em `gcloud run services describe`). API_KEY_SECRET local é
# opcional: cria o segredo na 1ª vez e, se diferir da versão atual, rotaciona.
SECRET="${API_KEY_SECRET_NAME:-pme-risk-api-key}"

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
  secretmanager.googleapis.com --project="${PROJECT_ID}" >/dev/null

# Fail-closed: sem segredo existente e sem API_KEY_SECRET o deploy falha —
# POST /laudos custa Gemini + BQ. O valor nunca é impresso.
if gcloud secrets describe "${SECRET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  if [ -n "${API_KEY_SECRET:-}" ]; then
    ATUAL="$(gcloud secrets versions access latest --secret="${SECRET}" --project="${PROJECT_ID}")"
    if [ "${API_KEY_SECRET}" != "${ATUAL}" ]; then
      printf %s "${API_KEY_SECRET}" | gcloud secrets versions add "${SECRET}" \
        --project="${PROJECT_ID}" --data-file=- >/dev/null
      echo "Segredo ${SECRET}: nova versão (rotação)"
    fi
    unset ATUAL
  fi
else
  : "${API_KEY_SECRET:?Segredo ${SECRET} não existe — defina API_KEY_SECRET para criá-lo}"
  printf %s "${API_KEY_SECRET}" | gcloud secrets create "${SECRET}" \
    --project="${PROJECT_ID}" --replication-policy=automatic --data-file=- >/dev/null
  echo "Segredo ${SECRET}: criado"
fi

# Leitura só deste segredo pela SA da API (não o papel no projeto inteiro)
gcloud secrets add-iam-policy-binding "${SECRET}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

# Imagem do docker/Dockerfile (a mesma validada localmente) — exporta IMAGE
source "$(dirname "$0")/build_image.sh"

# Privado por padrão: só identidades com roles/run.invoker chamam o serviço
# (curl -H "Authorization: Bearer $(gcloud auth print-identity-token)").
# ALLOW_UNAUTHENTICATED=1 abre a demo pública. Com CRIACAO_PUBLICA=1, visitantes
# criam laudos sem chave dentro de LIMITE_POR_IP_DIA / LIMITE_GLOBAL_DIA
# (api/limites.py); a decisão do portão humano exige X-API-Key sempre.
if [ "${ALLOW_UNAUTHENTICATED:-0}" = "1" ]; then
  AUTH_FLAG="--allow-unauthenticated"
else
  AUTH_FLAG="--no-allow-unauthenticated"
fi

# GCP_PROJECT_ID é lido em runtime pelo pipeline (Cloud Run não o injeta).
# API_KEY_SECRET chega como env var, mas resolvida do Secret Manager no start da
# instância — o código da API não muda. Rotação: rodar este script de novo.
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET:-pme_risk},CRIACAO_PUBLICA=${CRIACAO_PUBLICA:-0},LIMITE_POR_IP_DIA=${LIMITE_POR_IP_DIA:-3},LIMITE_GLOBAL_DIA=${LIMITE_GLOBAL_DIA:-30}" \
  --set-secrets="API_KEY_SECRET=${SECRET}:latest" \
  --min-instances=0 \
  --max-instances=1 \
  "${AUTH_FLAG}"

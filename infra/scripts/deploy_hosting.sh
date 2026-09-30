#!/usr/bin/env bash
# Firebase Hosting na frente do Cloud Run: https://pme-risk-demo.web.app
#
# O Hosting repassa TODAS as rotas para o serviço pme-risk-api (firebase.json):
# frontend, assets e API vêm da mesma imagem, sem risco de o HTML de uma versão
# pedir assets de outra. O public/ só tem robots.txt.
#
# Site com nome próprio (pme-risk-demo): o site padrão do Firebase usa o ID do
# projeto no endereço, que não deve aparecer em material público. Pelo mesmo
# motivo não há .firebaserc versionado — o projeto vem de GCP_PROJECT_ID.
#
# Limite: rewrite do Hosting para o Cloud Run tem timeout de 60 s; um laudo
# leva ~20–30 s, mas retries do Gemini com backoff podem passar disso (504).
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"

npx -y firebase-tools@latest deploy --only hosting --project "${PROJECT_ID}" --non-interactive

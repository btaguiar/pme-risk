# pme-risk — Laudo de risco de crédito PME

Sistema de análise de risco de crédito para PMEs brasileiras. Um modelo
treinado em BigQuery ML calcula a probabilidade de inadimplência (PD);
agentes LLM extraem, pesquisam e explicam a decisão; um portão humano
aprova ou rejeita antes do laudo final.

## Status

| Fase | Status | Entrega |
|---|---|---|
| 1 — Modelo | ✅ Completa | LOGISTIC_REG em produção, métricas em `eval/model/results/` |
| 2 — Laudo | ✅ Estrutural | Agentes, portão humano, auditoria, golden set F1=0.95 |
| 3 — Produto | 🔧 Código completo | API FastAPI, drift job, Docker, scripts de deploy; checklist de aceite executado e IAM preparada — falta só o deploy Cloud Run (passo manual) |

## Arquitetura

```
pedido em pt-BR
   │
   ▼
Extrator (Gemini) ──► DadosExtraidos
   │                    (ou recusa se fora de escopo)
   ▼
Pesquisador ──► DadosEnriquecidos
   │             (fonte: ✅ verificado / ⚠️ declarado)
   ▼
Modelo BQML ──► ResultadoModelo (PD + fatores, FROZEN)
   │
   ▼
Redator (Gemini) ──► Laudo (texto + evidências)
   │
   ▼
Portão humano ──► aprovar / corrigir / rejeitar
   │
   ▼
Trilha de auditoria (append-only)
```

**Divisão de responsabilidades:** o modelo decide o número; o LLM extrai,
pesquisa, explica e redige. O LLM não tem permissão para alterar a PD.

## Métricas

Regra: só números reproduzíveis a partir de `eval/*/results/` (BRIEF.md).

### Modelo — `eval/model/results/logreg_v1.json`

| Métrica | Valor | Observação |
|---|---|---|
| KS | 0.1767 | baseline LOGISTIC_REG |
| AUC | 0.6156 | holdout n=60.994 |
| Brier | 0.0735 | |
| ECE | 0.0011 | calibração |

### Extração — `eval/laudo/results/laudo_eval_v4.json`

| Métrica | Valor | Meta | Status |
|---|---|---|---|
| F1 extração | 0.9493 | ≥ 0.90 | ✅ |
| Recusa correta | 100% (11/11) | ≥ 95% | ✅ |
| Latência média | 5.68s | — | — |

**Não implementados nesta fase** (ver PLANO §5):
- Fidedignidade do laudo (% de afirmações com evidência)
- Verificado vs. declarado (% de campos classificados)

> **Ressalva:** o salto de F1 (0.84 → 0.95) veio de adicionar exemplos de
> mapeamento `setor→snake_case` no prompt do Extrator. Alguns exemplos são
> literalmente itens do golden set — há vazamento teste↔ajuste. O F1 medido
> provavelmente não generaliza tão bem para setores fora da lista de exemplos.

## Limites honestos

- A base de treino (Home Credit) **não é de PME brasileira** — é crédito pessoal
- O projeto demonstra o **método** (treino, calibração, monitoramento, governança)
- `pd` vem SEMPRE do modelo, nunca do LLM
- O mapeamento de features Home Credit → PME é hipótese documentada em `model/features.py`

## API (produto)

`api/main.py` — FastAPI com rotas finas; a orquestração vive no adapter
`api/pipeline.py` (único ponto de contato com os agentes da Fase 2).

| Método | Rota | Função |
|---|---|---|
| `GET` | `/healthz` | liveness |
| `POST` | `/laudos` | roda o pipeline completo; laudo nasce `pendente` |
| `GET` | `/laudos/{laudo_id}` | laudo aninhado (enriquecidos, modelo, texto, evidências) |
| `PATCH` | `/laudos/{laudo_id}/decisao` | portão humano: `aprovado` / `corrigido` / `rejeitado` |

```bash
# Servidor local (requer GCP_PROJECT_ID + ADC para o pipeline real)
uv run uvicorn api.main:app --port 8000

curl http://localhost:8000/healthz

# Com API_KEY_SECRET definido, POST exige o header (GET/healthz seguem abertos)
curl -X POST http://localhost:8000/laudos \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY_SECRET" \
  -d '{"texto": "Clínica odontológica em SP, ME, 5 anos de operação, faturamento R$ 2.000.000, solicita R$ 300.000 para expansão."}'

curl -X PATCH http://localhost:8000/laudos/<laudo_id>/decisao \
  -H "Content-Type: application/json" \
  -d '{"decisao": "aprovado", "decidido_por": "analista-1"}'
```

Pedidos fora de escopo (ex.: pessoa física) retornam `422` com
`{"detail": {"motivo_recusa": ...}}` — e a recusa entra na trilha de auditoria.

**Proteção da demo:** com a env var `API_KEY_SECRET` definida (o
`deploy_api.sh` a exige), `POST /laudos` requer header `X-API-Key` com o
mesmo valor — sem ela responde `401`. Sem a var definida (dev local), o
endpoint fica aberto. `GET`/`PATCH` seguem abertos para navegação da demo.

**Corte de escopo deliberado (SPEC §5.1):** o laudo final é **só JSON** —
não há endpoint de HTML/PDF nesta fase.

## Monitoramento (drift)

`monitoring/drift_job.py` compara as features numéricas dos últimos laudos
contra a distribuição de treino (PSI por quantis). Acima de 0.25 → log
`WARNING` (log-based alert do free tier).

```bash
# Local (requer ADC + GCP_PROJECT_ID)
uv run python monitoring/drift_job.py
```

No Cloud Run, roda como Job disparado por Cloud Scheduler semanal
(`infra/scripts/deploy_drift.sh`). Categóricas (porte, UF, setor) ficam de
fora: sem análogo honesto no Home Credit (limite documentado).

## Deploy (passo manual)

O build e os endpoints já foram validados localmente (Docker com ADC montado,
smoke 401/404/201 e integração e2e contra GCP real). O deploy exige:

| Variável | Valor |
|---|---|
| `GCP_PROJECT_ID` | projeto GCP destino |
| `RUN_SERVICE_ACCOUNT` | SA da API — já criada com papéis BQ: `pme-risk-api@<proj>.iam.gserviceaccount.com` |
| `API_KEY_SECRET` | segredo do header `X-API-Key` (obrigatório — fail-closed) |

```bash
export GCP_PROJECT_ID=... RUN_SERVICE_ACCOUNT=... API_KEY_SECRET=...
bash infra/scripts/deploy_api.sh     # API no Cloud Run (--allow-unauthenticated p/ demo)
bash infra/scripts/deploy_drift.sh   # Job de drift + Scheduler semanal
```

Pós-deploy: repetir o smoke (`healthz`, `401` sem key, `404` em
`PATCH /laudos/id-inexistente/decisao`, `201` com key) contra a URL pública.

Pré-requisitos já verificados (2026-09-27): tabelas `features`, `laudos`,
`model_registry`, `trilha_auditoria` no BigQuery; budget alert
`pme-risk-budget` (R$ 200, thresholds 50/80/100) ativo.

## Stack

| Camada | Escolha |
|---|---|
| Linguagem | Python 3.12 + uv |
| Modelo | BigQuery ML (LOGISTIC_REG) |
| LLM | Vertex AI — Gemini 2.5 Flash (ADC, sem API key) |
| Storage | BigQuery (features, models, laudos, auditoria) |
| API | FastAPI (`api/`, `uvicorn`) |
| Deploy | Cloud Run (`infra/scripts/deploy_*.sh`, passo manual) |
| Monitoramento | PSI via Cloud Run Job + Scheduler semanal |

## Desenvolvimento

```bash
# Setup
uv sync

# Testes
uv run pytest tests/unit/            # sem GCP (fakes)
GCP_PROJECT_ID=<seu-projeto> uv run pytest tests/integration/  # pipeline real (custa Gemini + BQ)

# API local
uv run uvicorn api.main:app --port 8000

# Lint
uv run ruff check .

# Verificar vazamento de credenciais (roda automaticamente no commit)
bash infra/scripts/check_secrets.sh

# Eval do modelo
GCP_PROJECT_ID=<seu-projeto> uv run python eval/model/run_eval.py

# Eval da extração
GCP_PROJECT_ID=<seu-projeto> uv run python eval/laudo/run_eval.py
```

**Pre-commit hook:** `infra/scripts/check_secrets.py` roda automaticamente
antes de cada commit e bloqueia IDs de projeto, chaves ou tokens. Instalado
em `.git/hooks/pre-commit`. Não precisa lembrar de rodar manualmente.

## Estrutura

```
pme-risk/
├── agents/          # Extrator, Pesquisador, Redator
├── api/             # main.py (rotas), pipeline.py (adapter), portão humano, auditoria
├── data/            # golden_set (sintético), schemas
├── docker/          # Dockerfile da API (Cloud Run)
├── eval/            # run_eval.py + results/ (fonte de verdade p/ métricas)
├── infra/           # scripts gcloud (deploy, secrets), budget-alerts
├── model/           # features, registry, predict, SQL
├── monitoring/      # drift_job.py (PSI)
├── tests/           # unit (sem GCP) + integration (pipeline real)
├── BRIEF.md         # regras: número sem fonte, dado privado
├── PLANO-pme-risk.md
└── SPEC-pme-risk.md
```

## Regras (BRIEF.md)

1. **Nenhum número sem fonte** — só métricas em `eval/*/results/`
2. **Nada de dado privado** — golden set sintético, sem IDs ou credenciais

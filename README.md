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
| 3 — Produto | 🔧 Em andamento | Deploy Cloud Run, drift job, demo |

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

## Stack

| Camada | Escolha |
|---|---|
| Linguagem | Python 3.12 + uv |
| Modelo | BigQuery ML (LOGISTIC_REG) |
| LLM | Vertex AI — Gemini 2.5 Flash (ADC, sem API key) |
| Storage | BigQuery (features, models, laudos, auditoria) |
| API | FastAPI (Fase 3) |
| Deploy | Cloud Run (Fase 3) |

## Desenvolvimento

```bash
# Setup
uv sync

# Testes
uv run pytest tests/unit/

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
├── api/             # Portão humano, auditoria
├── data/            # golden_set (sintético), schemas
├── eval/            # run_eval.py + results/ (fonte de verdade p/ métricas)
├── infra/           # scripts gcloud, budget-alerts
├── model/           # features, registry, predict, SQL
├── tests/           # unit tests
├── BRIEF.md         # regras: número sem fonte, dado privado
├── PLANO-pme-risk.md
└── SPEC-pme-risk.md
```

## Regras (BRIEF.md)

1. **Nenhum número sem fonte** — só métricas em `eval/*/results/`
2. **Nada de dado privado** — golden set sintético, sem IDs ou credenciais

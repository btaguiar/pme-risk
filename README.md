# pme-risk — Laudo de risco de crédito PME

Sistema de análise de risco de crédito para PMEs brasileiras, com modelo
treinado em BigQuery ML, agentes LLM para extração e redação, portão humano
de aprovação e trilha de auditoria completa.

## Status

| Fase | Status | Notas |
|---|---|---|
| 1 — Modelo | ✅ Completa | LOGISTIC_REG em produção |
| 2 — Laudo | ✅ Estrutural | Golden set F1=0.96, recusa 100% |
| 3 — Produto | ⬜ Em andamento | Deploy, drift, README final |

## Arquitetura

```
pedido em pt-BR
   │
   ▼
Extrator (Gemini) ──► DadosExtraidos
   │
   ▼
Pesquisador ──► DadosEnriquecidos (fonte: verificado/declarado)
   │
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

## Métricas

### Modelo (eval/model/results/logreg_v1.json)

| Métrica | Valor |
|---|---|
| KS | 0.1767 |
| AUC | 0.6156 |
| Brier | 0.0735 |
| ECE | 0.0011 |
| Amostras holdout | 60.994 |

### Extração (eval/laudo/results/laudo_eval_v3.json)

| Métrica | Valor | Meta |
|---|---|---|
| F1 extração | 0.9539 | ≥ 0.90 ✅ |
| Recusa correta | 90.91% (10/11) | ≥ 95% ⚠️ |
| Latência média | 5.73s | — |

> **Ressalva:** o salto de F1 (0.84 → 0.95) veio de adicionar exemplos de
> mapeamento `setor→snake_case` no prompt do Extrator. Alguns exemplos são
> literalmente itens do golden set — há vazamento teste↔ajuste. O F1 medido
> provavelmente não generaliza tão bem para setores fora da lista de exemplos.

## Stack

- **Python 3.12** + uv
- **BigQuery ML** — LOGISTIC_REG (treino/inferência)
- **Vertex AI** — Gemini 2.5 Flash (extração/redação)
- **FastAPI** — API de laudos
- **Cloud Run** — deploy (Fase 3)

## Limites honestos

- A base de treino (Home Credit) **não é de PME brasileira** — é crédito pessoal
- O projeto demonstra o **método** (treino, calibração, monitoramento, governança)
- `pd` vem SEMPRE do modelo, nunca do LLM

## Desenvolvimento

```bash
# Setup
uv sync
export GCP_PROJECT_ID=<seu-projeto-gcp>

# Testes
uv run pytest tests/unit/

# Lint
uv run ruff check .

# Eval do modelo
uv run python eval/model/run_eval.py

# Eval da extração
uv run python eval/laudo/run_eval.py
```

## Regras (BRIEF.md)

1. **Nenhum número sem fonte** — só métricas em `eval/*/results/`
2. **Nada de dado privado** — golden set sintético, sem credenciais

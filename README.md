# pme-risk — Laudo de risco de crédito PME

Sistema de análise de risco de crédito para PMEs brasileiras. Um modelo
treinado em BigQuery ML calcula a probabilidade de inadimplência (PD);
agentes LLM extraem, pesquisam e explicam a decisão; um portão humano
aprova ou rejeita antes do laudo final.

## Status

| Fase | Status | Entrega |
|---|---|---|
| 1 — Modelo | ✅ Completa | LOGISTIC_REG `logreg_v2` em produção, métricas em `eval/model/results/` |
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

### Modelo — `eval/model/results/logreg_v2.json` (em produção)

| Métrica | v2 | v1 (`logreg_v1.json`, aposentado) | Observação |
|---|---|---|---|
| KS | 0.1762 | 0.1767 | mesmo holdout, n=60.994 |
| AUC | 0.6141 | 0.6156 | |
| Brier | 0.0735 | 0.0735 | preditor constante na prevalência: **0.0744** |
| ECE | 0.0013 | 0.0011 | calibração |

> **Por que v2 com as mesmas métricas:** o v1 tinha skew treino/serviço que o
> holdout não mostra — a sentinela `DAYS_EMPLOYED=365243` (18% do treino) invertia
> o sinal de "tempo de operação" nos laudos, e o setor entrava como hash usado
> como número contínuo (PD arbitrária por setor). O v2 corrige isso
> (`model/sql/04_load_features_v2.sql`) sem perda offline.
>
> **Ressalva:** o Brier mal supera o preditor constante (0.0735 vs 0.0744) — o
> modelo ordena risco (KS/AUC) melhor do que estima probabilidade absoluta.

### Extração — `eval/laudo/results/laudo_eval_v6.json`

| Métrica | Valor | Meta | Status |
|---|---|---|---|
| F1 extração (micro, por campo) | 0.9601 (P 0.9707 / R 0.9498) | ≥ 0.90 | ✅ |
| Alucinação (valor em campo não mencionado) | 0 | — | ✅ |
| Recusa correta | 100% (11/11) | ≥ 95% | ✅ |
| Recusa indevida | 2.56% (1/39) | — | ⚠️ |
| Latência média | 7.23s | — | — |

Duas rodadas completas deram o mesmo agregado
(`laudo_eval_v6.json`, `laudo_eval_v6_rodada2.json`).

| F1 por campo | v5 (setor livre) | v6 (setor CNAE) |
|---|---|---|
| porte, UF, anos, faturamento, valor, prazo | 0.987 – 1.0 | 0.987 – 1.0 |
| `setor` | 0.5974 | **0.9091** |
| `finalidade` | 0.8571 | 0.8571 |
| `cnpj` | — | — (nenhum texto tem CNPJ; nenhum inventado) |

**Método** (`eval/laudo/run_eval.py`, testado em `tests/unit/test_eval_laudo.py`):
os 39 itens em escopo anotam os 9 campos, com `null` = "não mencionado"; valor
errado conta FP+FN; item que falha ou é recusado por engano fica no
denominador. Os evals v1–v4 pulavam campos `null` (não viam alucinação),
excluíam falhas e só avaliavam `faturamento` em 1 item — no v5, o método antigo
deu 0.9592 contra 0.9167 do novo na mesma rodada.

**v6 — `setor` com vocabulário fechado:** passou a ser a seção CNAE 2.0
(`agents/setores.py`, 21 códigos, imposto ao Gemini via `response_schema`); o
detalhe do negócio vai em `atividade` (livre, usado no laudo, não avaliado). No
v5 o F1 de `setor` media sinônimos (`varejo_otica` × `varejo_optica`). Os erros
restantes são de classificação CNAE de fato (padaria → I em vez de C;
fotografia → R em vez de M; vigilância → S em vez de N).

> **Ressalvas:**
> (1) Tirar o vazamento teste↔prompt revelou uma falha que ele mascarava: o
> exemplo do prompt era o item 0 do golden set, e sem ele o Extrator recusava
> pedidos sem porte explícito. A correção foi tornar explícita a regra legal
> (porte pela receita bruta, LC 123/2006) — regra de domínio, não ajuste por item.
> (2) As notas CNAE do prompt ("seção G inclui reparação de veículos",
> "veterinária é M"...) são fatos da classificação, mas cobrem casos do golden
> set; o F1 de `setor` pode não generalizar igual.
> (3) Em 5 itens a própria CNAE admite duas seções (ex.: engenharia civil F/M);
> o golden aceita qualquer uma, decidido pelo texto antes de rodar o eval.
> (4) `finalidade` segue texto livre e é agora o campo mais fraco.
> (5) A recusa indevida é o item 9 ("quero abrir uma empresa", sem UF nem
> porte) — anotação discutível, mantida para não ajustar o rótulo ao resultado.

### Comparação de modelos no Extrator — `eval/laudo/results/laudo_eval_v6_*.json`

Mesmo prompt, mesmo schema (JSON Schema strict), mesmo golden set; 2 rodadas
completas por modelo (média). Os outros modelos via API compatível com OpenAI
(Alibaba Model Studio) — **só no eval**, ver `eval/laudo/extrator_openai_compat.py`.

| Modelo | F1 (r1 / r2) | Média | `setor` | `finalidade` | Alucinação | Recusa correta | Latência |
|---|---|---|---|---|---|---|---|
| **gemini-2.5-flash** (produção) | 0.9601 / 0.9601 | 0.9601 | 0.909 | 0.857 | 0 | 22/22 | **8.4s** |
| qwen3.8-flash | 0.9529 / 0.9638 | 0.9584 | 0.961 | 0.792 | 0 | 22/22 | 15.5s |
| qwen3.8-max | 0.9710 / 0.9578 | 0.9644 | 0.980 | 0.850 | 0 | 21/22 | 25.1s |
| deepseek-v4-pro | 0.9553 / 0.9529 | 0.9541 | 0.994 | 0.723 | 1 | 22/22 | 11.7s |

**Decisão: Gemini segue em produção.** As diferenças de F1 (≤ 1 ponto na média)
estão dentro da variação entre rodadas do mesmo modelo (qwen3.8-max: 1.3 ponto;
a r2 inclui um timeout de 180s, contado como falha). O Gemini é o mais rápido,
o único estável entre rodadas, e fica no GCP — outro provedor em produção exige
análise de LGPD (transferência internacional, retenção, uso para treino).

> **Leituras e ressalvas:**
> (1) Os três modelos alternativos classificam `setor` (CNAE) melhor que o
> Gemini (0.96–0.99 × 0.91) e pior `finalidade` (0.72–0.85 × 0.86) — mas
> `finalidade` é texto livre e o prompt/rótulos foram iterados sobre o Gemini
> (v1–v4), o que favorece o Gemini nesse campo.
> (2) Critério de entrada: o modelo precisa impor o schema. `glm-5.3` aceita
> `json_schema` e o ignora; `deepseek-v4.1-flash` o rejeita — ficaram de fora
> (com JSON livre, o eval mediria formato, não extração).
> (3) Schema frouxo quebra silenciosamente: com `fora_de_escopo` opcional, o
> deepseek-v4-pro recusava devolvendo só `{"pedido": null}` (0/11 recusas
> válidas). O extrator do eval marca todos os campos como `required`
> (semântica strict); números acima já com essa correção.
> (4) Todos raciocinam por padrão (~750–950 tokens de saída por pedido); o custo
> do Gemini não é medido pelo eval (só o `usage` dos outros provedores).

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
| `GET` | `/health` (`/healthz` só local) | liveness |
| `POST` | `/laudos` | roda o pipeline completo; laudo nasce `pendente` |
| `GET` | `/laudos/{laudo_id}` | laudo aninhado (enriquecidos, modelo, texto, evidências) |
| `PATCH` | `/laudos/{laudo_id}/decisao` | portão humano: `aprovado` / `corrigido` / `rejeitado` |

```bash
# Servidor local (requer GCP_PROJECT_ID + ADC para o pipeline real)
uv run uvicorn api.main:app --port 8000

curl http://localhost:8000/health   # /healthz também (só local — Cloud Run reserva paths com "z" final)

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

**Proteção:** o deploy é **privado por padrão** (Cloud Run IAM — exige
`Authorization: Bearer $(gcloud auth print-identity-token)`). Além disso,
`POST /laudos` requer header `X-API-Key` — sem ela responde `401`. No Cloud Run a
chave vem do **Secret Manager** (`pme-risk-api-key`, lido só pela SA da API) e
nunca aparece em `gcloud run services describe`; o código lê a env var
`API_KEY_SECRET` e não sabe a diferença. Sem a var (dev local), fica aberto.

**Portão humano:** decisões são finais — decidir um laudo que já saiu de
`pendente` responde `409`. Cada decisão entra na `trilha_auditoria`
(`decisao_humana` com quem, quando e observação).

**Cota do Gemini:** 429/5xx são repetidos com backoff (`agents/gemini.py`);
se persistir, `POST /laudos` responde `503` com `Retry-After`.

**Corte de escopo deliberado (SPEC §5.1):** o laudo final é **só JSON** —
não há endpoint de HTML/PDF nesta fase.

## Monitoramento (drift)

`monitoring/drift_job.py` compara as features numéricas dos últimos laudos
contra a distribuição de treino (PSI por quantis). Acima de 0.25 → log
`WARNING` (log-based alert do free tier).

```bash
# Local (requer ADC + GCP_PROJECT_ID)
uv run python -m monitoring.drift_job
```

No Cloud Run, roda como Job disparado por Cloud Scheduler semanal
(`infra/scripts/deploy_drift.sh`). Com menos de 100 laudos por feature o
PSI não é calculado (`amostra_insuficiente`): com n pequeno ele mede ruído
(n=30 → 68% de falso alarme em simulação; n=100 → 1%). Categóricas (porte, UF, setor) ficam de
fora: sem análogo honesto no Home Credit (limite documentado).

## Deploy (passo manual)

O build e os endpoints já foram validados localmente (Docker com ADC montado,
smoke 401/404/201 e integração e2e contra GCP real). O deploy exige:

| Variável | Valor |
|---|---|
| `GCP_PROJECT_ID` | projeto GCP destino |
| `RUN_SERVICE_ACCOUNT` | SA da API: `pme-risk-api@<proj>.iam.gserviceaccount.com` — papéis `bigquery.dataEditor/dataViewer/jobUser` + `aiplatform.user` |

> **Validação com a identidade da SA (2026-09-27):** os testes e2e rodaram com
> ADC do usuário (permissões amplas) — então as permissões da SA foram
> validadas separadamente, por impersonation com token dela: BigQuery
> `query` → 200; Vertex AI `generateContent` (gemini-2.5-flash) → 200.
> Antes do deploy real, opcionalmente rode o e2e inteiro como a SA:
> `gcloud auth application-default login --impersonate-service-account=$RUN_SERVICE_ACCOUNT`
> e `GCP_PROJECT_ID=<proj> uv run pytest tests/integration -v` (restaura o ADC depois).
| `API_KEY_SECRET` | chave do header `X-API-Key` — cria o segredo `pme-risk-api-key` na 1ª vez; se diferir da versão atual, **rotaciona** (nova versão). Opcional depois que o segredo existe; sem segredo e sem a var o deploy falha (fail-closed) |

```bash
export GCP_PROJECT_ID=... RUN_SERVICE_ACCOUNT=... API_KEY_SECRET=...
bash infra/scripts/deploy_api.sh     # API no Cloud Run, privada (ALLOW_UNAUTHENTICATED=1 p/ demo pública)
bash infra/scripts/deploy_drift.sh   # Job de drift + Scheduler semanal
```

**Rotação da chave:** troque `API_KEY_SECRET` e rode `deploy_api.sh` — ele adiciona
a versão e publica uma revisão nova. Desative a versão antiga em seguida
(`gcloud secrets versions disable <n> --secret=pme-risk-api-key`). Revisões
anteriores a 2026-09-28 tinham a chave em texto puro; ela foi rotacionada e a
versão antiga desativada.

Pós-deploy: repetir o smoke com `Authorization: Bearer $(gcloud auth print-identity-token)` (`/health`, `401` sem key, `404` em
`PATCH /laudos/id-inexistente/decisao`, `201` com key, `409` ao re-decidir) contra a URL do serviço.

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
GCP_PROJECT_ID=<seu-projeto> uv run python -m eval.model.run_eval

# Eval da extração
GCP_PROJECT_ID=<seu-projeto> uv run python -m eval.laudo.run_eval
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

# Design — Fase 3 (Produto): API, deploy e drift

Data: 2026-09-27
Fontes: [PLANO §6](../../../PLANO-pme-risk.md), [SPEC §5](../../../SPEC-pme-risk.md)
Contexto: Fase 2 em reestruturação pelo desenvolvedor — este design **não toca**
em `agents/`, `api/routes/portao_humano.py`, `api/auditoria.py`, `tests/`
existentes nem `README.md`.

## Decisão-chave

**Adapter de pipeline único** (`api/pipeline.py`): é o único módulo da Fase 3
que importa código da Fase 2 (`agents.*`, `PortaoHumano`, `TrilhaAuditoria`).
Rotas ficam finas e recebem o pipeline por injeção de dependência do FastAPI.
Quando a reestruturação da Fase 2 aterrissar, apenas `pipeline.py` precisa ser
ajustado.

Formato do laudo final: **só JSON** (sem HTML/PDF) — decisão do desenvolvedor.

## 1. API

### `api/main.py`

- Cria o app FastAPI, registra os routers, expõe `GET /healthz` →
  `200 {"status": "ok"}` para o Cloud Run.
- Config via variáveis de ambiente (nomes no `.env.example`):
  `GCP_PROJECT_ID`, `BQ_DATASET` (default `pme_risk`), `BQ_LOCATION`.

### `api/routes/laudos.py`

- `POST /laudos` — body `{"texto": "<pedido pt-BR>"}`:
  - Sucesso → `201 {"laudo_id": "<uuid4>", "status": "pendente"}`;
  - Extrator recusa (`fora_de_escopo=true`) → `422 {"motivo_recusa": "..."}`,
    sem laudo persistido, mas com registro na `trilha_auditoria`.
- `GET /laudos/{id}` — laudo completo em JSON: desserializa
  `enriquecidos_json` e `resultado_modelo_json` da tabela `laudos` e devolve
  o documento aninhado + colunas de decisão. `404` se inexistente.

### `api/routes/decisao.py`

- `PATCH /laudos/{id}/decisao` — body `{"decisao": "aprovado|corrigido|rejeitado",
  "decidido_por": str, "observacao": str?}`. Encaminha para `PortaoHumano`
  via adapter. `404` se inexistente; `422` se decisão inválida.

Sem endpoint de PDF/HTML nesta fase.

## 2. Adapter — `api/pipeline.py`

Classe `Pipeline` (singleton via dependência `get_pipeline()`):

- `gerar(texto) -> LaudoCriado | Recusa`:
  1. Extrator → `DadosExtraidos`;
  2. Se `fora_de_escopo` → `TrilhaAuditoria.registrar` + retorna `Recusa`;
  3. Pesquisador → `DadosEnriquecidos`;
  4. `model.predict.prever` → `ResultadoModelo` (PD vem do modelo, nunca do LLM);
  5. Redator → texto + evidências;
  6. `PortaoHumano.criar` com `laudo_id = uuid4()`, `status='pendente'`;
  7. `TrilhaAuditoria.registrar` (model_version, hashes de prompt, etapas).
- `obter(laudo_id) -> dict | None` — lê a tabela `laudos`, desserializa JSONs.
- `decidir(laudo_id, decisao, decidido_por, observacao) -> dict | None`.

Testes sobrescrevem `app.dependency_overrides[get_pipeline]` com um pipeline
falso em memória — nenhuma chamada a GCP nos testes unitários.

## 3. Drift — `monitoring/drift_job.py`

- Função pura `psi(esperado, atual, n_bins=10) -> float` — bins por quantis da
  distribuição de treino; testável sem GCP.
- Job (modo script):
  1. Lê features de treino da tabela `features` (split `train`);
  2. Lê os últimos N laudos (default 100) e mapeia campos do pedido → features
     de treino: `valor_solicitado`↔`amt_credit`,
     `faturamento_anual_declarado`↔`amt_income_total`, `anos_operacao`,
     `prazo_meses`↔`prazo_meses_estimado`;
  3. PSI por variável; categóricas sem análogo direto (porte, UF, setor) ficam
     de fora — limite documentado no módulo;
  4. PSI > 0,25 → log estruturado `WARNING` por variável (PLANO §5);
  5. Resumo JSON em stdout.
- Roda como Cloud Run Job (não no processo da API).

## 4. Deploy

- `docker/Dockerfile` — `python:3.12-slim`, `uv sync`, uvicorn em
  `api.main:app` escutando `$PORT` (0.0.0.0). Sem segredo na imagem: ADC no
  runtime via service account do Cloud Run.
- `.dockerignore` na raiz (`.venv`, `data/raw`, `.env`, caches).
- `infra/scripts/deploy_api.sh` — `gcloud run deploy pme-risk-api --source .`
  com service account de papel mínimo (BigQuery Data Editor + Job User),
  idempotente, sem IDs de projeto hard-coded (lê `GCP_PROJECT_ID`).
- `infra/scripts/deploy_drift.sh` — build do job de drift como Cloud Run Job +
  `gcloud scheduler jobs create http` semanal (OIDC), idempotente.

## 5. Testes (arquivos novos)

- `tests/unit/test_api.py` — com pipeline falso: healthz 200; POST cria laudo
  201; POST fora de escopo 422; GET retorna documento aninhado; GET 404;
  PATCH decide (200) e valida decisão inválida (422).
- `tests/unit/test_drift.py` — PSI: distribuições idênticas → ~0; deslocadas →
  >0,25; bins com contagem zero não produzem NaN/inf.

## 6. Fora de escopo

- Qualquer arquivo da Fase 2 existente hoje;
- `README.md` (em edição pelo desenvolvedor; números do eval entram depois);
- HTML/PDF do laudo; frontend; autenticação de analista.

## Critério de pronto

- `uvicorn api.main:app` sobe localmente com ADC válido e `POST /laudos`
  devolve `laudo_id` de ponta a ponta (pipeline real);
- `GET /healthz` responde 200;
- `pytest tests/unit` passa com pipeline falso (sem GCP);
- `ruff check` limpo;
- Scripts de deploy idempotentes documentados (comentário no cabeçalho).

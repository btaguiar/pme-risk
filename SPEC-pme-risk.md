# Spec de implementação: pme-risk

Operacionaliza o [PLANO-pme-risk.md](PLANO-pme-risk.md) em decisões técnicas
concretas: estrutura de repo, schemas, contratos e sequência de tarefas.
A Fase 1 está no nível de "dá para abrir o editor e começar"; Fases 2 e 3
estão em nível estrutural (contratos e schemas) e ganham o mesmo detalhe no
início de cada uma — o plano já manda cortar escopo em vez de estender prazo,
então não vale a pena especificar em detalhe algo que pode mudar.

`BRIEF.md`, citado no plano como fonte das regras herdadas (nenhum número sem
fonte, nada de dado privado), não existe neste repositório. Duas opções:
recriar o arquivo aqui ou apontar para onde ele já existe. Até lá, este
documento trata as duas regras como se estivessem inline no PLANO.

---

## 1. Estrutura de repositório

```
pme-risk/
├── PLANO-pme-risk.md
├── SPEC-pme-risk.md
├── README.md                    # escrito na Fase 3, com números do eval
├── pyproject.toml
├── .env.example                 # nomes de variável, nunca valores
├── infra/
│   ├── terraform/                # ou scripts gcloud — decidir na semana 1 (ver §8)
│   └── budget-alerts.md          # passos p/ configurar 50/80/100% (§7 do plano)
├── data/
│   ├── raw/                      # .gitignore — nunca commitar dado baixado
│   ├── golden_set/               # sintético, pt-BR — este SIM versiona
│   │   └── pedidos.jsonl
│   └── schemas/
│       └── pedido_credito.schema.json
├── model/
│   ├── sql/
│   │   ├── 01_load_features.sql
│   │   ├── 02_train_baseline_logreg.sql
│   │   └── 03_train_candidate.sql
│   ├── features.py               # feature engineering (pandas → BQ)
│   ├── registry.py                # grava/lê model_registry (BigQuery)
│   └── predict.py                 # PD + fatores a partir do modelo publicado
├── agents/
│   ├── extractor/
│   │   ├── prompt.md
│   │   └── extractor.py
│   ├── pesquisador/
│   │   └── pesquisador.py         # usa quimera-core
│   ├── redator/
│   │   ├── prompt.md
│   │   └── redator.py
│   └── schemas.py                 # contratos Pydantic entre agentes
├── api/
│   ├── main.py                    # FastAPI
│   ├── routes/
│   │   ├── laudos.py
│   │   └── portao_humano.py
│   └── auditoria.py                # grava trilha de auditoria
├── monitoring/
│   └── drift_job.py                # PSI, roda via Cloud Scheduler
├── eval/
│   ├── model/
│   │   ├── run_eval.py             # KS, AUC, Brier, ECE vs. baseline
│   │   └── results/                # JSON por versão de modelo — versionado
│   ├── laudo/
│   │   ├── run_eval.py             # fidedignidade, verificado/declarado, recusa
│   │   └── results/
│   └── extraction/
│       ├── run_eval.py             # F1 de extração de entidades
│       └── results/
├── docker/
│   └── Dockerfile
└── tests/
    ├── unit/
    └── golden/
```

Regra: `eval/*/results/` é a única fonte de números para README e posts —
nada de métrica citada que não esteja num JSON versionado ali.

## 2. Stack técnica

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.12 | consistente com o resto do portfólio |
| Empacotamento | `uv` + `pyproject.toml` | rápido, lockfile determinístico |
| API | FastAPI + Pydantic v2 | schemas = contrato entre agentes e validação de request |
| Modelo | BigQuery ML (`LOGISTIC_REG`, depois `BOOSTED_TREE_CLASSIFIER`) | já decidido no plano (§3, §5) |
| LLM | Gemini via `google-genai` SDK + **Vertex AI** (ADC, sem API key) | free tier no flash; citado no plano |
| Busca vetorial | `BigQuery VECTOR_SEARCH` | decidido no plano — não Vertex AI Vector Search |
| Storage de estado (laudos, portão humano, auditoria, registry) | Tabelas BigQuery | evita introduzir Firestore/Datastore como segundo sistema de dados; cabe no free tier de storage (10 GB) |
| Deploy | Cloud Run + Docker | decidido no plano |
| Agendamento | Cloud Scheduler → Cloud Run job (drift) | decidido no plano |
| Lint/test | `ruff`, `pytest` | padrão |

**Decisão a validar na semana 1:** Terraform vs. scripts `gcloud` soltos em
`infra/`. Para um projeto de portfólio de 10 semanas, scripts `gcloud`
versionados (idempotentes, com comentário do que fazem) provavelmente bastam
e reduzem a superfície a manter — Terraform só compensa se a infra crescer
além de ~10 recursos. Recomendo scripts; revisar se a Fase 3 mostrar
necessidade real de state management.

## 3. Fase 1 — Modelo (detalhado)

### 3.1 Schema do pedido de crédito

`data/schemas/pedido_credito.schema.json` — também vira o `BaseModel`
Pydantic em `agents/schemas.py`, usado tanto pelo Extrator quanto pela API:

```json
{
  "setor": "enum — seção CNAE 2.0 (agents/setores.py, 21 códigos)",
  "atividade": "string | null — descrição livre do negócio, usada no laudo",
  "porte": "MEI | ME | EPP",
  "uf": "string (2 letras)",
  "anos_operacao": "number",
  "faturamento_anual_declarado": "number (BRL) — sempre ⚠️ declarado",
  "valor_solicitado": "number (BRL)",
  "prazo_meses": "integer | null — opcional, nem sempre mencionado",
  "finalidade": "enum — agents/finalidades.py (9 códigos, giro × investimento)",
  "finalidade_detalhe": "string | null — texto livre, usado no laudo, não avaliado",
  "cnpj": "string | null — se presente, habilita consulta pública (BrasilAPI)"
}
```

**Decisões de implementação (2026-09-27):**
- `prazo_meses` é opcional (`int | None`) — nem sempre mencionado no pedido
- `valor_solicitado` e `faturamento_anual_declarado` são obrigatórios
- `finalidade` é vocabulário fechado (`agents/finalidades.py`), imposto via `response_schema` (2026-09-29)
- **(2026-09-28)** `setor` virou seção CNAE 2.0 (vocabulário fechado, imposto via
  `response_schema`); o detalhe vai em `atividade`. Rótulo livre fazia o F1 do
  campo medir sinônimos (0.60 no eval v5)

### 3.2 Decisão em aberto: mapeamento de features Home Credit → PME

> **Resolvido no v3 (2026-09-29):** a base de treino passou a ser SBA 7(a)
> (empréstimos reais a PME, com desfecho), com features seção CNAE, faixa de
> idade e valor em US$ PPP, e calibração SCR de porte e UF. Mapa atual em
> `model/features.py` e `model/mapeamentos.py`; decisão em
> `docs/superpowers/plans/2026-09-29-modelo-v3-sba.md`. O texto abaixo é o
> histórico do v1/v2.

O Home Credit Default Risk (dados de crédito pessoal: renda do solicitante,
tempo de emprego, tipo de contrato, histórico em bureau) não tem
correspondência direta com os campos acima (dados de **empresa**, não de
pessoa física). Isso não invalida o projeto — o próprio plano já assume que
"a base de treino não é de PME brasileira" (§4) e que o objetivo é demonstrar
o método, não produzir um modelo pronto para concessão real.

Ainda assim, o mapeamento de colunas precisa ser uma decisão explícita e
documentada — não implícita no código — porque ela define o que "PD" quer
dizer no laudo final. Proposta de mapeamento conceitual, a validar/ajustar
na EDA da semana 1:

| Campo do pedido PME | Coluna Home Credit análoga | Nota |
|---|---|---|
| `faturamento_anual_declarado` | `AMT_INCOME_TOTAL` | proxy de capacidade de pagamento |
| `valor_solicitado` | `AMT_CREDIT` | |
| `prazo_meses` | derivado de `AMT_CREDIT` / `AMT_ANNUITY` | Home Credit não tem prazo explícito em meses |
| `anos_operacao` | `DAYS_EMPLOYED` (convertido) | proxy de maturidade/estabilidade, não é o mesmo conceito |
| `setor` | `OCCUPATION_TYPE` | mapeamento aproximado, registrar tabela de de-para |
| `uf` | `REGION_RATING_CLIENT` | Home Credit não tem UF brasileira — usar como proxy de risco regional, não geografia real |

Esta tabela é uma hipótese de trabalho, não um resultado de EDA. Ela deve ser
revisada (e o resultado registrado em `model/features.py` como comentário e
em `eval/model/results/`) antes de qualquer treino ser citado como "final".
Isso é exatamente o tipo de limite que o §4 do plano manda deixar explícito
no README.

### 3.3 Sequência de tarefas — Semana 1

1. Criar projeto GCP dedicado (não o do quimera) + budget alerts 50/80/100%
   (plano §7, item 1 da disciplina) — **fazer isto antes de qualquer chamada
   de API**.
2. Baixar Home Credit (Kaggle) → `data/raw/` (gitignored) → carregar em
   BigQuery (`bq load`).
3. EDA mínima: validar/ajustar a tabela de mapeamento acima; decidir
   tratamento de nulos e outliers; congelar a lista de features em
   `model/features.py`.
4. `model/sql/01_load_features.sql`: view ou tabela materializada com as
   features já transformadas + split treino/holdout (coluna `split`,
   determinístico via hash do ID — reprodutível).

### 3.4 Semana 2

1. `02_train_baseline_logreg.sql` — `CREATE MODEL ... OPTIONS(model_type='LOGISTIC_REG', input_label_cols=['target'])`.
2. `eval/model/run_eval.py`: roda `ML.EVALUATE` e `ML.PREDICT` no holdout,
   calcula KS (scipy `ks_2samp` sobre score por classe), Brier, ECE/curva de
   calibração (bins fixos, ex. 10 bins) — grava
   `eval/model/results/logreg_v1.json`.
3. `model/registry.py`: cria tabela `model_registry` —
   `(model_version, algoritmo, feature_set_version, treinado_em, ks, auc, brier, ece, status)`.
   Baseline entra como `status='baseline'`.

### 3.5 Semana 3

1. `03_train_candidate.sql` — `BOOSTED_TREE_CLASSIFIER`, mesmo feature set.
2. Rodar mesmo `run_eval.py` sobre o candidato → `boosted_v1.json`.
3. Comparar contra o baseline: **critério do plano (§5) é regra, não
   sugestão** — só promover o candidato se ele superar KS/AUC do baseline
   sem piorar Brier/ECE. Empate técnico = ficar com o baseline logístico e
   registrar isso em `model_registry` (`status='candidate_rejected'` +
   nota).
4. `model/predict.py`: função `prever(features) -> (pd, faixa_risco, fatores)`
   contra o modelo `status='production'` do registry. Fatores por variável:
   para `LOGISTIC_REG`, coeficiente × valor da feature padronizada; para
   `BOOSTED_TREE_CLASSIFIER`, `ML.EXPLAIN_PREDICT` (Shapley values nativo do
   BQML) — mais barato que reimplementar SHAP fora do BigQuery.

### 3.6 Definição de pronto da Fase 1

- `eval/model/results/*.json` existe para baseline e (se treinado) candidato;
- `model_registry` tem exatamente um modelo com `status='production'`;
- `model/predict.py` roda isolado (sem API, sem agentes) e devolve PD + fatores
  para um vetor de features de exemplo;
- Limite do mapeamento de features (§3.2) está documentado, não só no código.

## 4. Fase 2 — Laudo (estrutural)

### 4.1 Contratos entre agentes (`agents/schemas.py`)

```python
class PedidoCredito(BaseModel):
    ...  # schema da §3.1

class DadosExtraidos(BaseModel):
    pedido: PedidoCredito
    fora_de_escopo: bool
    motivo_recusa: str | None

class DadosEnriquecidos(BaseModel):
    extraidos: DadosExtraidos
    cnpj_dados: dict | None       # BrasilAPI: seção CNAE, anos, porte, UF, situação + divergencias
    fonte_por_campo: dict[str, Literal["verificado", "declarado"]]

class ResultadoModelo(BaseModel):
    pd: float
    faixa_risco: str
    fatores: list[tuple[str, float]]   # (nome_feature, contribuição)
    model_version: str                  # rastreia model_registry

class Laudo(BaseModel):
    enriquecidos: DadosEnriquecidos
    resultado_modelo: ResultadoModelo
    texto: str                          # redigido pelo Redator
    evidencias: list[str]               # normas/fontes citadas no texto
    status: Literal["pendente", "aprovado", "corrigido", "rejeitado"]
```

`ResultadoModelo` é somente leitura para os agentes de texto — nenhum deles
tem uma rota de código que reescreva `pd` ou `faixa_risco` (regra do plano
§2: "o LLM não tem permissão para alterar a PD"). Vale um teste de unidade
que garanta isso por construção (campo sem setter exposto / dataclass
congelado), não só por convenção.

### 4.2 Prompts (`agents/*/prompt.md`)

- **Extrator:** entrada = texto livre pt-BR → saída = `DadosExtraidos`
  (JSON mode / structured output do Gemini). Deve recusar (`fora_de_escopo=true`)
  quando faltar informação essencial ou o pedido não for de crédito PME.
- **Redator:** entrada = `DadosEnriquecidos` + `ResultadoModelo` → saída =
  texto do laudo. Prompt deve instruir explicitamente: (a) marcar cada dado
  como ✅/⚠️ conforme `fonte_por_campo`; (b) toda afirmação de risco tem que
  citar `resultado_modelo.fatores` ou uma norma da base vetorial — nunca
  opinião livre; (c) nunca mencionar um valor de PD diferente do recebido.

### 4.3 Portão humano

Tabela BigQuery `laudos` (chave `laudo_id`) com o `Laudo` serializado +
colunas de decisão: `decidido_por`, `decidido_em`, `decisao`,
`observacao_humana`. Endpoint `PATCH /laudos/{id}/decisao` em
`api/routes/portao_humano.py`. Nenhum laudo é "final" (exportável como
HTML/PDF) com `status='pendente'`.

### 4.4 Trilha de auditoria

Tabela `trilha_auditoria`, uma linha por laudo, append-only: `laudo_id`,
`pedido_bruto`, `model_version`, `prompts_usados` (hash + referência ao
arquivo de prompt, não o texto completo — evita duplicar dado grande),
`decisao_humana`, timestamps de cada etapa. Serve tanto para debug quanto
para a alegação de "auditável" no README.

### 4.5 Golden set

`data/golden_set/pedidos.jsonl`, ~50 linhas, cada uma com `texto_pt_br` +
`esperado: DadosExtraidos`. Cobrir: os 3 portes, pelo menos 4 setores, pedidos
ambíguos (faltando dado) e pedidos claramente fora de escopo (ex. pessoa
física pedindo empréstimo, ou pedido em outro idioma).

## 5. Fase 3 — Produto (estrutural)

### 5.1 Endpoints (`api/main.py`)

- `POST /laudos` — recebe texto livre, roda o pipeline completo até
  `status='pendente'`, devolve `laudo_id`.
- `GET /laudos/{id}` — estado atual do laudo.
- `PATCH /laudos/{id}/decisao` — portão humano (§4.3).
- `GET /laudos/{id}/pdf` — só serve se `status` for `aprovado` ou `corrigido`.
- `GET /healthz` — para o Cloud Run.

### 5.2 Deploy

`docker/Dockerfile` (uvicorn + FastAPI), build via Cloud Build (`infra/cloudbuild.yaml`)
ou local + push no Artifact Registry, variáveis sensíveis via Secret Manager
(nunca em `.env` commitado — só `.env.example` com nomes).

**Implementado (2026-09-28):** `API_KEY_SECRET` vem do segredo `pme-risk-api-key`
via `--set-secrets` (antes ia em `--set-env-vars`, legível na descrição do
serviço); `secretAccessor` só no segredo, para a SA da API.

### 5.3 Job de drift

`monitoring/drift_job.py`: lê distribuição das features dos últimos N laudos
em `trilha_auditoria`, compara via PSI contra a distribuição de treino
(salva como artefato em `model/sql/01_load_features.sql` output). Roda como
Cloud Run Job disparado por Cloud Scheduler (cron semanal). Alerta = log
estruturado com severidade WARNING se PSI > 0,25 (limite já definido no
plano §5) — sem serviço de alerta pago adicional; Cloud Logging + a política
de log-based alert do Cloud Monitoring free tier cobre isso.

## 6. Convenções

- Todo módulo Python com type hints; `ruff` no CI (mesmo que CI seja só um
  script local rodado antes de commit, dado que ainda não é repo git).
- Nenhum SQL solto em string Python para o treino do modelo — sempre em
  `model/sql/*.sql`, versionado, para o `model_registry` poder referenciar
  o arquivo exato usado.
- Testes em `tests/golden/` rodam o golden set contra o Extrator e calculam
  F1 diretamente — é o mesmo código usado por `eval/extraction/run_eval.py`,
  não uma reimplementação paralela.

## 7. Checklist de dia 1

1. `git init` (o diretório ainda não é repositório git — confirmar antes de
   qualquer outro passo, inclusive antes de criar `.gitignore`).
2. Projeto GCP dedicado + billing budget alerts 50/80/100%.
3. `.gitignore` cobrindo `data/raw/`, `.env`, credenciais.
4. `pyproject.toml` com as deps da §2.
5. Scaffold de pastas da §1 (mesmo vazias, com `.gitkeep` onde fizer sentido).

## 8. Riscos técnicos e mitigação

| Risco | Mitigação |
|---|---|
| Mapeamento Home Credit → PME (§3.2) ficar arbitrário demais e comprometer a credibilidade do "PD" | Documentar a hipótese explicitamente no README como limite, não escondê-la; considerar reportar métricas também segmentadas por porte simulado |
| `ML.EXPLAIN_PREDICT` não cobrir `LOGISTIC_REG` do jeito esperado | Testar cedo (semana 2, não semana 3); fallback é coeficiente × feature padronizada, que já cobre o caso linear |
| Custo de treino repetido do BQML consumir a cota de 1 TB de query grátis | Materializar a tabela de features uma vez (§3.3.4) em vez de recomputar a cada `CREATE MODEL` |
| quimera-core não estar publicável a tempo da Fase 2 | Materializou-se: o stub serviu até 2026-09-29, quando a consulta passou a usar a BrasilAPI (`agents/pesquisador/cnpj.py`) atrás de uma função injetável — o quimera-core pode substituí-la |

## 9. Pendências que exigem decisão do desenvolvedor

- ~~Confirmar ou recriar `BRIEF.md`~~ — ✅ recriado em 2026-09-27
- ~~Validar a tabela de mapeamento de features (§3.2)~~ — ⚠️ mapeamento
  documentado como hipótese em `model/features.py`; validação completa
  requer EDA adicional
- ~~Terraform vs. scripts `gcloud` (§2)~~ — ✅ scripts `gcloud` (decidido)
- ~~EDA do mapeamento Home Credit → PME (§3.2)~~ — ✅ superado no v3: a
  base passou a ser SBA 7(a), e o levantamento das bases está em
  `docs/dados/levantamento-bases-pme-2026-09-29.md`.
- **Boosted tree candidato** — erro BQML 80038528 não investigado. Decisão
  de ficar no baseline é válida (regra: empate = baseline). Para comparação
  de modelos no currículo, investigar erro e tentar com hiperparâmetros
  diferentes. Não bloqueia.

## 10. Decisões de implementação (2026-09-27)

| Decisão | Escolha | Motivo |
|---|---|---|
| `prazo_meses` opcional | `int \| None` | Nem sempre mencionado no pedido |
| LLM auth | Vertex AI via ADC | Sem API key, integração GCP nativa |
| LLM do Extrator | `gemini-2.5-flash` mantido (2026-09-28) | Comparado a qwen3.8-flash/max e deepseek-v4-pro: F1 empatado (≤ 1 ponto), Gemini mais rápido e sem transferência de dados para fora do GCP |
| Extração `setor` | Seção CNAE 2.0 (enum) | Padrão externo; rótulo livre gerava sinônimos |
| Extração `finalidade` | Vocabulário fechado (enum, 2026-09-29) | Rótulo livre gerava sinônimos (`modernizacao` × `equipamentos`); detalhe em `finalidade_detalhe` |
| `valor_solicitado` obrigatório | Sim | Essencial para análise de crédito |
| `verificado` no Pesquisador | Só se o dado público **confere** com o declarado (setor, porte, UF; anos com tolerância de 1) | Divergência fica declarada e vai para `cnpj_dados.divergencias`; consulta falhou → tudo declarado |
| Boosted tree | `candidate_rejected` | Erro BQML 80038528, baseline promovido |
| Check de credenciais | `infra/scripts/check_secrets.sh` | Previne vazamento de IDs (3ª reincidência) |
| Eval harness | Conta recusa mesmo em erro | Item que falha validação não pode pular contagem |

## 11. Ferramentas de qualidade

| Ferramenta | Comando | Propósito |
|---|---|---|
| Lint | `uv run ruff check .` | Padrões de código |
| Testes | `uv run pytest tests/unit/` | Contratos, frozen, validação |
| Credenciais | `bash infra/scripts/check_secrets.sh` | Previne vazamento de IDs/keys |
| Eval modelo | `uv run python eval/model/run_eval.py` | KS/AUC/Brier/ECE |
| Eval extração | `uv run python eval/laudo/run_eval.py` | F1, recusa, latência |

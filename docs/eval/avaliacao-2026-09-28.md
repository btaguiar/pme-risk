# Avaliação de implementação — pme-risk

**Data:** 2026-09-28
**Foco:** portfólio/vaga (o projeto prova competência para vagas de risco/ML/LLM, conforme PLANO §1 e §9)
**Escala:** 0–10
**Referência de escopo:** `PLANO-pme-risk.md`, `SPEC-pme-risk.md`, `BRIEF.md`
**Método:** varredura read-only de todo o código, verificação cruzada docs ↔ JSONs de eval, execução de testes/lint/check de segredos.

---

## Nota final: **7,0 / 10**

**Parecer.** Projeto acima da média de portfólio: pipeline completo de ponta a ponta (dados brutos → modelo BQML → agentes → API → drift), arquitetura com contratos imutáveis e injeção de dependência, testes sem GCP com fakes, e — o mais raro — documentação honesta que declara limites e ressalvas (Home Credit ≠ PME, vazamento teste↔prompt). O que impede nota alta são três defeitos que um avaliador técnico sênior encontraria rápido: (1) **skew treino/serviço** na feature `occupation_type_encoded` (três encodings distintos para a mesma variável) e tratamento ausente da anomalia `DAYS_EMPLOYED=365243`; (2) **deploy não executável como está** — os scripts não injetam `GCP_PROJECT_ID` no runtime; (3) **F1=0.95 com defeitos metodológicos** que o avaliador descobriria ao perguntar "como você calculou o F1?". A honestidade dos docs mitiga parte do risco reputacional, mas não o risco técnico.

---

## Rubrica

| # | Dimensão | Peso | Nota | Justificativa |
|---|---|---|---|---|
| 1 | Completude vs PLANO/SPEC | 2,0 | **1,5** | 3 fases com código entregue; mas 3 das 8 linhas da matriz de evals (§5) não implementadas, baseline de chamada única do laudo ausente (critério de pronto da Fase 2 não cumprido formalmente) e busca vetorial de normas cortada sem registro |
| 2 | Qualidade de código/arquitetura | 2,0 | **1,5** | `ResultadoModelo` frozen + testes de imutabilidade, DI com fakes, structured output + validação dupla, API key em tempo constante; porém zero tratamento de erro nos agentes e sem máquina de estados na decisão |
| 3 | Testes e evals | 1,5 | **1,0** | 48 testes passando, fakes exemplares, PSI testado por propriedades, métricas conferem com JSONs; mas agentes/model/eval sem teste, um teste no-op, e F1 com defeitos de denominador/cobertura |
| 4 | ML/MLOps | 1,5 | **0,9** | BQML + split determinístico + `ML.EXPLAIN_PREDICT` + registry + PSI semanal; porém skew treino/serviço em feature do modelo e anomalia do Home Credit não tratada em 18% do treino |
| 5 | Segurança/privacidade (BRIEF) | 1,0 | **0,7** | Golden set sintético, `.env` gitignored, pre-commit instalado, IAM mínimo; porém IDs de projeto reais commitados no próprio scanner de segredos (violação do BRIEF §2) e API key em env var em vez de Secret Manager |
| 6 | Documentação/honestidade | 1,0 | **0,8** | Maior força moral do projeto: limites declarados, ressalva de vazamento verdadeira, números reproduzíveis; mas PLANO desatualizado (v3 vs v4), SPEC obsoleta em 3 pontos e um docstring factualmente falso |
| 7 | Prontidão de produto/demo | 1,0 | **0,6** | API + Docker + scripts fail-closed e checklist local executado; porém o deploy quebraria em runtime e a imagem roda como root |
| | **Total** | **10,0** | **7,0** | |

---

## Verificações objetivas (2026-09-28)

| Verificação | Resultado |
|---|---|
| `uv run pytest tests/unit tests/golden` | ✅ 48 passed (1,36s) |
| `uv run ruff check .` | ✅ All checks passed |
| `bash infra/scripts/check_secrets.sh` | ✅ "OK: nenhum vazamento" — porém o próprio arquivo contém IDs reais (ver C1) |
| Métricas README/PLANO ↔ `eval/*/results/` | ✅ Todos os números conferem com os JSONs citados |

---

## Achados por severidade

### Críticos (corrigir antes de qualquer divulgação)

**C1 — Skew treino/serviço em `occupation_type_encoded` (três encodings para a mesma feature)**
- Treino: `FARM_FINGERPRINT` real — `model/sql/01_load_features.sql:24`
- Avaliação offline (`preparar_features`): aproximação **MD5** — `model/features.py:60-70`
- Serviço (API): **FNV-1a** — `api/pipeline.py:41-65`
- O docstring mente: `model/features.py:85` afirma "usa FARM_FINGERPRINT % 100 para ser compatível com 01_load_features.sql" enquanto a função usa MD5 (`features.py:61` admite "APROXIMAÇÃO... usa MD5, não FarmHash").
- Consequência: o coeficiente logístico aprendido para `occupation_type_encoded` é aplicado em produção a um espaço de hash diferente do treino. É o defeito técnico mais grave do projeto.
- Correção: usar o mesmo hash nos três caminhos (ex.: portar `FARM_FINGERPRINT` para Python ou treinar com um encoding reproduzível em Python/SQL).

**C2 — Deploy não injeta `GCP_PROJECT_ID` no runtime**
- `infra/scripts/deploy_api.sh:32` injeta só `BQ_DATASET` e `API_KEY_SECRET`.
- `infra/scripts/deploy_drift.sh:19,27` injeta só `BQ_DATASET`.
- O código exige a var em runtime: `api/pipeline.py:195`, `monitoring/drift_job.py:123` → `KeyError` → 500 no primeiro POST / job de drift.
- O checklist local funcionou porque a env era exportada manualmente. **O deploy conforme os scripts não é executável.**
- Correção: `--set-env-vars="...,GCP_PROJECT_ID=${PROJECT_ID}"` nos dois scripts.

**C3 — IDs de projeto GCP reais commitados no próprio guardião de segredos**
- `infra/scripts/check_secrets.py:15-17` e `infra/scripts/check_secrets.sh:9-11` contêm três IDs de projeto GCP reais (omitidos aqui pelo mesmo motivo).
- Esses arquivos estão na lista de skip do scanner (`SKIP_FILES`), ou seja, ele nunca flagra a si mesmo.
- Viola o `BRIEF.md` §2 ("Não expor IDs de projeto GCP... em qualquer material público") — irônico: a violação está exatamente no mecanismo de proteção.
- Correção: remover os IDs concretos (usar padrões genéricos ou ofuscação) e/ou deixar o scanner verificar os próprios arquivos.

**C4 — Anomalia `DAYS_EMPLOYED = 365243` não tratada (sentinela de "desempregado" no Home Credit)**
- `model/features.py:112` faz `.abs()` sem tratar; `model/sql/01_load_features.sql:21` idem.
- A sentinela existe em ~18% das linhas de `application_train.csv` e vira outlier de ~1.000 anos em `days_employed_abs`, enquanto no serviço o valor máximo é ~21.915 (`api/pipeline.py:64`).
- Outro skew treino/serviço + dano à qualidade do modelo (a feature entra crua na logreg).
- Correção: tratar 365243 como nulo/sentinel nos dois caminhos antes de gerar a feature.

### Médios (impactam métricas, entrevistas ou o "auditável")

**M1 — Decisão humana fora da trilha de auditoria**
- `api/auditoria.py:33` tem o parâmetro `decisao_humana`, mas ele é sempre `None` (`api/pipeline.py:128,164`).
- `Pipeline.decidir` (`api/pipeline.py:176`) só faz UPDATE na tabela `laudos` — **não** appenda na `trilha_auditoria`.
- Contraria a SPEC §4.4 e o PLANO §2 ("registro de quem decidiu e quando"). O evento mais importante do fluxo "auditável" não fica no registro imutável.

**M2 — F1 da extração inflado por defeitos metodológicos**
- `eval/laudo/run_eval.py:131-133`: `f1s.append` só acontece quando `obtido_dict is not None` — item em escopo que falha/recusa por engano **desaparece do denominador**, puxando a média para cima.
- `faturamento_anual_declarado` está no `esperado` de apenas **1 dos 40** itens em escopo do golden set (`data/golden_set/pedidos.jsonl`) — o campo obrigatório mais valioso do schema quase nunca é avaliado. `cnpj` nunca é avaliado; `prazo_meses` só em 8 itens.
- Valor errado conta só como FP (`run_eval.py:72`), não FP+FN — recall otimista em campos trocados.
- Vazamento teste↔prompt **confirmado** (o exemplo do prompt do Extrator é o item 1 do golden set; a tabela de normalização cobre ~10 setores do golden set). A ressalva está declarada no README:68-71 e PLANO:174 ✅ — mas o F1 medido não generaliza.

**M3 — `__main__` do eval do laudo roda com `max_itens=5`**
- `eval/laudo/run_eval.py:196`. O comando do README (`uv run python eval/laudo/run_eval.py`) sobrescreveria `laudo_eval.json` com avaliação de 5 itens, não reproduzindo os números citados. Reprodutibilidade frágil.

**M4 — Brier mal supera o baseline ingênuo, e isso não é dito**
- Brier 0.0735 (`eval/model/results/logreg_v1.json`) vs. preditor constante na prevalência (~8% de inadimplência → Brier ingênuo ≈ 0.0742). Estatisticamente indistinguível em calibração.
- O PLANO §5 exige "melhor que baseline ingênuo" — o baseline ingênuo não está calculado em nenhum JSON, e a diferença não é citada em documentação nenhuma.

**M5 — Sem tratamento de erro nos agentes**
- `agents/extractor/extractor.py:67` e `agents/redator/redator.py:89`: `json.loads(response.text)` sem try/except/retry; chamadas de API sem fallback.
- `os.environ["GCP_PROJECT_ID"]` → `KeyError` seco (`extractor.py:41`, `redator.py:52`).
- Falha do Gemini vira 500 cru na API.

**M6 — Matriz de evals incompleta (3 de 8 linhas)**
- Não implementados (declarados no PLANO:140 ✅): **Fidedignidade** (% de afirmações com evidência), **Verificado vs. declarado** (% de campos classificados).
- **Baseline de chamada única do laudo** (PLANO §5) nunca foi implementado — o critério de pronto da Fase 2 ("Multi-agente supera o baseline ou decisão registrada") não foi cumprido formalmente.
- Na prática `verificado/declarado` nunca acontece: o stub de CNPJ retorna `None` sempre (`agents/pesquisador/pesquisador.py:35`) → 100% dos campos sai `declarado` e `CAMPOS_VERIFICAVEIS` é código morto.

### Baixos (higiene e acabamento)

**B1 —** `assert isinstance(resultado, LaudoCriado)` (`api/routes/laudos.py:44`) some com `python -O`; deveria ser `if/raise`.
**B2 —** Teste no-op: `tests/golden/test_golden_set.py:35-40` (`test_valor_solicitado_null_implica_fora_de_escopo`) tem corpo `pass` — não asserta nada.
**B3 —** SPEC §6 prometia que `tests/golden` rodaria o golden set contra o Extrator e calcularia F1 com o mesmo código do eval — não é verdade; o teste só valida estrutura JSONL.
**B4 —** `promover()` marca o modelo antigo como `candidate_rejected` (`model/registry.py:101`) — semanticamente errado; falta status `retired`.
**B5 —** Dockerfile sem `USER` (roda como root); `pandas` e `scipy` são deps principais mas não usados em runtime pela API/drift — peso extra na imagem.
**B6 —** `API_KEY_SECRET` vai em `--set-env-vars` (`deploy_api.sh:32`) em vez de Secret Manager (`--set-secrets`) — contraria a SPEC §5.2; legível em `gcloud run services describe`.
**B7 —** PLANO (linhas 167-172) apresenta a **v3** do eval (recusa 90,91%) enquanto o README (57-62) apresenta a **v4** (recusa 100%) — ambos citam seus JSONs (BRIEF respeitado), mas o PLANO está desatualizado.
**B8 —** `PATCH /laudos/{id}/decisao` aberto sem autenticação (documentado como tradeoff); sem máquina de estados — laudo aprovado pode ser re-decidido.
**B9 —** `VERTEX_LOCATION` é lida pelo código (`extractor.py:22`, `redator.py:22`) mas não documentada no `.env.example`.
**B10 —** Cobertura do drift: só 4 das 8 features (`monitoring/drift_job.py:24-29`); `prazo_meses_estimado` tem semântica diferente do treino (default 36 não aplicado).
**B11 —** Custo por laudo no eval é constante chutada (`run_eval.py:165`: `$0.0001/request`) — o PLANO §5 prometia custo medido por rodada.

---

## Pontos fortes (defensáveis em entrevista)

1. **Imutabilidade da PD por construção** — `ResultadoModelo` frozen (`agents/schemas.py:63`), o Redator só devolve `{texto, evidencias}`, e há teste de mutação (`tests/unit/test_schemas.py:20-33`). Responde direto "como você impede o LLM de alterar o score?".
2. **Pipeline com injeção de dependência** — `api/pipeline.py` aceita callables injetáveis; 48 testes rodam **sem GCP** com fakes (`dependency_overrides`). Padrão profissional de testabilidade.
3. **API key em tempo constante** (`hmac.compare_digest`, `api/routes/laudos.py:29`) + deploy fail-closed sem o segredo (`deploy_api.sh:10-11`).
4. **PSI correto e testado por propriedades** (`monitoring/drift_job.py:43`, `tests/unit/test_drift.py`) — idênticas→0, deslocamento→alerta, sem NaN.
5. **Documentação honesta** — limites do Home Credit→PME em código (`model/features.py:13-34`) e README:73-78; ressalva de vazamento teste↔prompt declarada espontaneamente; corte de PDF documentado.
6. **Evals versionados** com números 100% reproduzíveis a partir de `eval/*/results/` (regra do BRIEF cumprida — verificado item a item).
7. **Trilha append-only de verdade** — só INSERT em `trilha_auditoria` (`api/auditoria.py:62`), hash de prompt SHA-256, degradação deliberada documentada (`api/pipeline.py:166-170`).
8. **Scripts de deploy com histórico de review** — correção de IAM (`aiplatform.user`) documentada no comentário (`deploy_api.sh:15`); binding `cloudrun.invoker` no recurso do job com comentário do erro testado (`deploy_drift.sh:43`).

---

## Gaps vs PLANO (matriz §5)

| Eval (PLANO §5) | Status | Onde |
|---|---|---|
| KS, AUC (holdout) | ✅ | `eval/model/results/logreg_v1.json` |
| Brier, ECE | ✅ | idem |
| F1 extração | ✅ (com ressalvas M2) | `eval/laudo/results/laudo_eval_v4.json` |
| Recusa correta | ✅ 100% (11/11) | idem |
| Drift PSI | ✅ (parcial — 4/8 features) | `monitoring/drift_job.py` |
| Custo e latência | ⚠️ latência ✅, custo chutado | `eval/laudo/run_eval.py:165` |
| Fidedignidade do laudo | ❌ não implementado | declarado PLANO:140 |
| Verificado vs. declarado | ❌ não implementado (stub sempre `None`) | declarado PLANO:140 |
| Baseline laudo (chamada única) | ❌ não implementado | — |

---

## Recomendações priorizadas

| # | Ação | Impacto na nota | Esforço |
|---|---|---|---|
| 1 | Unificar o encoding de `occupation_type_encoded` (C1) + tratar sentinela 365243 (C4) | +0,5 (dim. 4) | médio |
| 2 | Injetar `GCP_PROJECT_ID` nos deploys (C2) e fazer um smoke real | +0,3 (dim. 7) | baixo |
| 3 | Remover IDs reais do `check_secrets` (C3) | +0,2 (dim. 5) | baixo |
| 4 | Registrar `decisao_humana` na trilha em `Pipeline.decidir` (M1) | +0,2 (dim. 1/2) | baixo |
| 5 | Corrigir o denominador do F1 e avaliar `faturamento` nos 40 itens (M2) | +0,2 (dim. 3) | médio |
| 6 | Calcular e publicar o baseline ingênuo do modelo (M4) | +0,1 (dim. 6) | baixo |
| 7 | try/except + retry nos agentes (M5), `USER` no Docker (B5) | +0,1 | médio |
| 8 | Alinhar PLANO com a v4 do eval (B7) e documentar `VERTEX_LOCATION` (B9) | +0,1 (dim. 6) | baixo |

Com as correções 1–6 o projeto chegaria a **~8,5**, faixa de destaque em processo seletivo.

---

## Anexo — verificação de métricas (docs ↔ `eval/*/results/`)

| Métrica | README | JSON | Confere | PLANO | JSON | Confere |
|---|---|---|---|---|---|---|
| KS | 0.1767 | `logreg_v1.json` = 0.1767 | ✅ | 0.1767 | idem | ✅ |
| AUC | 0.6156 (n=60.994) | 0.6156 (60994) | ✅ | 0.6156 | idem | ✅ |
| Brier | 0.0735 | 0.0735 | ✅ | 0.0735 | idem | ✅ |
| ECE | 0.0011 | 0.0011 | ✅ | 0.0011 | idem | ✅ |
| F1 extração | 0.9493 | `laudo_eval_v4.json` | ✅ | 0.9539 | `laudo_eval_v3.json` | ✅ |
| Recusa | 100% (11/11) | v4 = 1.0 | ✅ | 90,91% (10/11) ⚠ | v3 | ✅ |
| Latência | 5.68s | v4 = 5.68 | ✅ | 5.73s | v3 | ✅ |

Nenhum número órfão no README — regra 1 do BRIEF cumprida. A única divergência é PLANO (v3) vs README (v4), ambos com fonte citada.

# Modelo v3 — SBA 7(a) + calibração SCR + referência BNDES — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o modelo de risco treinado em crédito pessoal (Home Credit,
`logreg_v2`) por um treinado em **empréstimos reais a PME** (SBA 7(a)), com a
PD **ajustada ao risco relativo brasileiro** por porte e UF (SCR.data) e com o
drift medido contra **pedidos PME brasileiros** (BNDES). O resto da arquitetura
não muda: a PD vem só do modelo, o LLM explica, o portão humano decide.

**Base da decisão:** [`docs/dados/levantamento-bases-pme-2026-09-29.md`](../../dados/levantamento-bases-pme-2026-09-29.md)

**Tech Stack:** Python 3.14, BigQuery / BigQuery ML, pandas (só na ingestão),
pytest, ruff. Nada de serviço novo no GCP.

**Timebox:** 2 semanas (PLANO §6: estourou → corta escopo, não estende prazo).
Precisa terminar antes do fim do trial (~2026-12-25), porque os evals do laudo
rodam no Gemini.

---

## Decisões já tomadas (levantamento de 2026-09-29)

| # | Decisão | Por quê |
|---|---|---|
| D1 | Rótulo: `CHGOFF` = 1, `PIF` = 0; fora: `EXEMPT`, `CANCLD`, `COMMIT` | Só desfechos observados. EXEMPT é censura (ativo, status oculto) |
| D2 | Safras FY2010–2015 | EXEMPT ≤ 5,1% por safra; de 2017 em diante a censura infla a perda |
| D3 | **`TermInMonths` fora das features** | Vazamento: perda de 0,91% (prazo redondo) × 33,64% (prazo quebrado) |
| D4 | Só empréstimo a prazo (`RevolverStatus = N`) | O pedido do pme-risk é empréstimo a prazo, não linha rotativa |
| D5 | Validação temporal: treino FY2010–2013, holdout FY2014–2015 | Split aleatório esconderia a mudança de safra; banco valida no tempo |
| D6 | Baseline logístico obrigatório; candidato só entra se ganhar em KS/AUC sem piorar Brier/ECE | PLANO §5 |
| D7 | SCR ajusta **porte e UF** (o que a SBA não vê); **setor fica no modelo** | Ajustar setor pelos dois lados contaria o efeito em dobro. O ranking de setor SBA × SCR vira checagem de sanidade, não ajuste |
| D8 | BNDES só como agregado (sem linha com nome de cliente) | Nome aberto é dado pessoal em PF/MEI |
| D9 | `logreg_v2` fica no registry como `retired` quando o v3 entrar | Reprodutibilidade; o histórico do README continua citável |

## Decisões do dono do projeto (2026-09-29)

- **P1 — Conversão BRL → USD: fator PPP** do Banco Mundial (compara poder de
  compra; câmbio de mercado faria um pedido brasileiro parecer ~2× menor). O
  fator e o ano ficam registrados com a fonte no código.
- **P2 — Faturamento sai do modelo** (a SBA não tem) e fica só no laudo, como
  ⚠️ declarado. Uma razão valor/faturamento sem análogo no treino repetiria o
  erro do hash de setor do v1.

---

## Features do v3

| Feature | Treino (SBA) | Serviço (pedido) | Tipo |
|---|---|---|---|
| `secao_cnae` | `NaicsCode` → seção CNAE (Task 2) | `pedido.setor` | STRING (categórica) |
| `faixa_idade` | `BusinessAge` → faixa (Task 2) | `pedido.anos_operacao` → mesma faixa | STRING (categórica) |
| `log_valor_usd` | `ln(GrossApproval)` | `ln(valor_solicitado / fator_PPP)` | FLOAT64 |

Três features é pouco, e é de propósito: é o que existe dos dois lados sem
vazamento nem proxy inventado. Espera-se AUC modesta. O ganho do v3 está na
**validade** da base, não na discriminação. Isso vai escrito no README.

Faixas de idade: `startup` (abertura; < 1 ano) · `2_5` (≥ 2 e < 5) ·
`5_mais` · `desconhecida` (Unanswered, vazio, códigos antigos ambíguos, troca de
controle). **A SBA não tem faixa de 1–2 anos**: no serviço, `anos_operacao` < 2
→ `startup` (hipótese: faixa mais próxima em risco), < 5 → `2_5`, senão
`5_mais`. Perda no recorte de treino: 9,48% (abertura), 8,35% (< 1 ano),
7,2–8,5% (2–5), 6,04% (5+). Detalhes em `model/mapeamentos.py`.

## Calibração brasileira (SCR.data)

Ajuste em escala logit, aplicado depois do `ML.PREDICT`:

```
logit(PD_final) = logit(PD_SBA) + ln(RR_porte) + ln(RR_uf)
RR_porte = inad_SCR(porte) / inad_SCR(Micro+Pequeno)
RR_uf    = inad_SCR(Micro+Pequeno, uf) / inad_SCR(Micro+Pequeno)
```

- Média dos últimos 12 meses de SCR, para suavizar sazonalidade.
- Porte: MEI e ME → `Micro`; EPP → `Pequeno`.
- UF com carteira PME abaixo de um piso → RR = 1 (sem ajuste; registrado).
- Os dois ajustes entram em `fatores` como `ajuste_porte_br` e `ajuste_uf_br`,
  para o Redator explicá-los e o juiz de fidedignidade aceitar os nomes.
- **O nível absoluto não é calibrado pelo SCR:** a inadimplência dele é
  estoque vencido acima de 90 dias, e a perda da SBA é acumulada ao longo da
  vida do empréstimo (levantamento §2).

---

### Task 1: Ingestão SBA → BigQuery

**Files:**
- Create: `model/dados/ingest_sba.py`, `model/sql/06_load_sba_raw.sql` (se necessário)
- Test: `tests/unit/test_ingest_sba.py`

- [x] Baixar `FOIA_7a_FY2010_FY2019_asof_260630.csv` (URL fixa no código, versão no nome da tabela).
- [x] **Descartar PII na leitura**: nome, endereço, CEP do tomador e dados do banco. Só entram as colunas usadas + `ApprovalFY`, `LoanStatus`, `RevolverStatus`.
- [x] Normalizar `LoanStatus` (`"P I F"` → `PIF`).
- [x] Carregar em `${BQ_DATASET}.sba_7a_raw` (particionada por `ApprovalFY`).
- [x] Teste: fixture de 10 linhas com PII → a saída não tem colunas de PII e `P I F` vira `PIF`.
- [x] Commit.

### Task 2: Mapeamentos NAICS → CNAE e BusinessAge → faixa

**Files:**
- Create: `model/mapeamentos.py`
- Test: `tests/unit/test_mapeamentos.py`

- [x] `NAICS_PARA_SECAO`: por prefixo, do mais específico para o mais geral (ex.: `2211` → `eletricidade_gas`, `2213` → `agua_esgoto_residuos`, `532` → `administrativas_servicos_complementares`, `44`/`45`/`42` → `comercio`, `31`–`33` → `industria_transformacao`). Tabela com a fonte (concordância NAICS × ISIC do US Census) no docstring.
- [x] `faixa_idade_sba(business_age)` e `faixa_idade_pedido(anos)` com as faixas acima.
- [x] Testes: todo NAICS de 2 dígitos mapeia para uma chave de `SETORES_CNAE`; as duas funções de faixa produzem o mesmo conjunto de valores. Cobertura real: 1.268 códigos distintos, 2 linhas sem seção (NAICS vazio).
- [x] Commit.

### Task 3: Feature set v3 e treino (baseline + candidato)

**Files:**
- Create: `model/sql/07_load_features_v3.sql`, `model/sql/08_train_logreg_v3.sql`, `model/sql/09_train_candidate_v3.sql`
- Modify: `model/features.py` (docstring do mapa, `FEATURE_SET_VERSION = "v3_sba"`, `FEATURES_TABLE = "features_v3"`, `FEATURE_COLUMNS`)

- [x] `features_v3`: aplica D1, D2, D4, os mapeamentos da Task 2 (via tabela de mapeamento carregada no BQ ou `CASE` gerado) e `split` por safra (D5).
- [x] **Teste de vazamento** (`tests/unit/test_features_v3.py`): nenhum `TermInMonths`, `ChargeOffDate`, `PaidInFullDate`, `GrossChargeOffAmount` ou `LoanStatus` em `FEATURE_COLUMNS` ou no SQL de treino.
- [x] Treinar `logreg_v3` (mesmos hiperparâmetros do v2) e um candidato (`BOOSTED_TREE_CLASSIFIER`; se repetir o erro 80038528, registrar e seguir só com o baseline). **Candidato falhou com internalError 80038528 (3 tentativas, igual ao v1) — baseline segue sozinho.** Tabela: treino 112.335 (7,67% CHGOFF), holdout 63.502 (6,87%).
- [x] Medir bytes do treino (cota de 1 TB). **36,2 MB no total** (features + treino + checagens, INFORMATION_SCHEMA.JOBS).
- [x] Commit.

### Task 4: Eval do modelo v3

**Files:**
- Modify: `eval/model/run_eval.py` (versão e feature set por parâmetro)
- Create: `eval/model/results/logreg_v3.json` (gerado)

- [x] KS, AUC, Brier, **Brier ingênuo**, ECE no holdout temporal FY2014–2015. **KS 0,1354 · AUC 0,5845 · Brier 0,0638 < ingênuo 0,0640 ✅ · ECE 0,0071** (n=63.502).
- [x] Métricas também **por safra** (2014 × 2015), para ver a estabilidade. Brier bate o ingênuo nas duas (0,0610/0,0612 e 0,0662/0,0664); AUC 0,5903 × 0,5799.
- [x] **Sanidade de setor:** correlação de Spearman entre a perda por seção na SBA e a inadimplência por seção no SCR. Vai no JSON, sem limite de aceite (é checagem, não meta). *(ρ = 0,1429 em 20 seções — positiva fraca; registrada no logreg_v3.json após a Task 5)*
- [x] Critério: `logreg_v3` bate o Brier ingênuo. Candidato só substitui se cumprir D6. *(candidato falhou no treino — Task 3)*
- [x] Commit do JSON.

### Task 5: Calibração SCR

**Files:**
- Create: `model/dados/ingest_scr.py`, `model/sql/10_scr_fatores.sql`, `model/calibracao.py`
- Test: `tests/unit/test_calibracao.py`

- [x] Ingerir 12 meses de SCR.data v2 (só PJ; colunas do levantamento §2) em `scr_pj_raw`. *(1.535.774 linhas, data-bases 2025-08..2026-07; CSV do BCB mistura latin-1 e UTF-8 por campo — decodificação tolerante por valor)*
- [x] `scr_fatores`: `RR_porte` e `RR_uf` com o piso de carteira. *(RR_porte: Micro 0,78, Pequeno 1,08; RR_uf: 0,79 SP a 1,97 AC; piso R$ 1 bi/mês de carteira PME — só RR fica sem ajusto)*
- [x] `calibracao.aplicar(pd, porte, uf, fatores) -> (pd_final, [("ajuste_porte_br", Δlogit), ("ajuste_uf_br", Δlogit)])`.
- [x] Testes: RR = 1 não muda a PD; RR > 1 aumenta; resultado sempre em (0, 1); UF abaixo do piso → sem ajuste.
- [x] Commit.

### Task 6: Referência BNDES (drift e prazo padrão)

**Files:**
- Create: `model/dados/ingest_bndes.py`, `model/sql/11_bndes_referencia.sql`
- Modify: `monitoring/drift_job.py`

- [ ] Ler o CSV de operações indiretas automáticas em streaming e **gravar só o agregado**: MICRO/PEQUENA, contratações 2018–2022, quantis de valor e prazo (`carencia + amortizacao`) por porte e seção.
- [ ] Verificar se há contratações posteriores a 2022 em outro recurso do conjunto; se não houver, registrar como limite.
- [ ] Drift: `valor_solicitado` e `prazo_meses` contra o BNDES, e setor (PSI categórico) contra a distribuição do BNDES. Atualizar o docstring: a referência deixa de ser o treino.
- [ ] Prazo padrão, quando o pedido não informa: mediana do BNDES por porte (substitui `_PRAZO_DEFAULT_MESES`). Hoje o prazo é obrigatório na API, então isso só afeta o eval e o texto.
- [ ] Testes do drift com referência injetada.
- [ ] Commit.

### Task 7: Serviço — pipeline, predict, registry

**Files:**
- Modify: `api/pipeline.py` (`pedido_para_features`, `FEATURES_CONSTANTES_NO_SERVICO`), `model/predict.py` (`_FEATURE_TYPES` por versão com STRING, `_BQ_MODEL_NAMES`, chamada da calibração), `model/registry.py` (registro do v3, v2 → `retired`)
- Test: `tests/unit/test_pipeline_features.py`, `tests/unit/test_predict.py` (novo, com BQ mockado)

- [ ] `pedido_para_features` v3: `secao_cnae`, `faixa_idade`, `log_valor_usd` (fator PPP, P1).
- [ ] `prever` aplica a calibração e devolve os fatores do modelo + os dois ajustes.
- [ ] Frontend: rótulos legíveis para os novos nomes de fator (`frontend/src/lib/format.ts`).
- [ ] Teste de contrato: o conjunto de features do serviço é exatamente `FEATURE_COLUMNS` do v3 (pega skew treino/serviço, como no v1).
- [ ] Commit.

### Task 8: Evals do laudo e documentação

- [ ] Rodar de novo `eval/laudo/run_eval_laudo.py` (Redator com os novos fatores): fidedignidade e verificado × declarado, 2 rodadas.
- [ ] README: seção do modelo com `logreg_v3.json`; nova ressalva ("PME americana, ajustada ao risco relativo brasileiro"); **o vazamento do prazo como achado**; v2 no histórico.
- [ ] PLANO §4/§5/§6 e SPEC §3.2 atualizados; `model/features.py` com o mapa novo.
- [ ] Commit.

### Task 9: Deploy

- [ ] Build local, smoke do container (POST real), push, `deploy_api.sh` e `deploy_drift.sh` com a mesma `IMAGE`, smoke no Cloud Run, execução manual do job de drift.
- [ ] Atualizar o `model_registry` em produção (v3 `production`, v2 `retired`).

---

## Critérios de aceite

1. Nenhum campo com vazamento no treino (teste da Task 3).
2. `logreg_v3` bate o Brier ingênuo no holdout temporal; métricas por safra no JSON.
3. Features do serviço = features do treino (teste da Task 7).
4. Laudo: fidedignidade 100% e marcação verificado × declarado ≥ o resultado anterior.
5. Todo número novo no README sai de `eval/*/results/`.
6. Custo: treino + ingestão dentro da cota gratuita do BigQuery (bytes medidos e registrados).

## Riscos

| Risco | Mitigação |
|---|---|
| AUC do v3 abaixo da do v2 (0,61) | Esperado e aceitável: o v2 discriminava crédito pessoal, não PME. O README compara a validade das bases, não só a AUC |
| Mapeamento NAICS → CNAE impreciso em setores de fronteira | Teste de cobertura + sanidade de Spearman com o SCR; imprecisão registrada |
| Censura residual (3,2% EXEMPT em FY2010–2015) | Registrar; sensibilidade: treinar tratando EXEMPT como 0 e comparar |
| Boosted tree repete o erro do BQML | Seguir só com o baseline (já aconteceu no v1; D6 permite) |
| Trial acaba antes da Task 8 | Tasks 1–7 não dependem do Gemini; a 8 é a única que precisa de crédito |

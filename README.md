# pme-risk — Laudo de risco de crédito PME

**Demo:** https://pme-risk-demo.web.app

Sistema de análise de risco de crédito para PMEs brasileiras. Um modelo
treinado em BigQuery ML calcula a probabilidade de inadimplência (PD);
agentes LLM extraem, pesquisam e explicam a decisão; um portão humano
aprova ou rejeita antes do laudo final.

## Status

| Fase | Status | Entrega |
|---|---|---|
| 1 — Modelo | ✅ Completa (v3) | LOGISTIC_REG `logreg_v3` treinado em empréstimos reais a PME (SBA 7(a)), calibrado ao risco relativo brasileiro (SCR.data); métricas em `eval/model/results/` |
| 2 — Laudo | ✅ Completa | Agentes, portão humano, auditoria; extração F1 0.99, fidedignidade do laudo 99.9% (v2), baseline de chamada única medido |
| 3 — Produto | ✅ Demo pública | API + frontend no Cloud Run; visitante gera laudo dentro de limite diário, só analista (X-API-Key no Secret Manager) decide; job de drift semanal; smoke pós-deploy executado |

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

### Modelo — `eval/model/results/logreg_v3.json` (v3)

**Base:** empréstimos reais a pequenas empresas dos EUA (SBA 7(a) FOIA),
desfecho observado (`CHGOFF` = perda × `PIF` = quitado), safras FY2010–2015,
só empréstimo a prazo. **Validação temporal:** treino FY2010–2013 (112.335),
holdout FY2014–2015 (63.502). Escolha das bases e alternativas descartadas:
[`docs/dados/levantamento-bases-pme-2026-09-29.md`](docs/dados/levantamento-bases-pme-2026-09-29.md).

| Métrica (holdout temporal) | v3 | FY2014 | FY2015 |
|---|---|---|---|
| KS | 0.1354 | 0.1400 | 0.1342 |
| AUC | 0.5845 | 0.5903 | 0.5799 |
| Brier | 0.0638 | 0.0610 | 0.0662 |
| Brier do preditor constante | 0.0640 | 0.0612 | 0.0664 |
| ECE | 0.0071 | 0.0105 | 0.0042 |

**Features (3):** seção CNAE (NAICS → CNAE, `model/mapeamentos.py`), faixa de
idade do negócio e ln do valor em US$ PPP (fator do Banco Mundial). **Depois
do modelo**, a PD recebe o risco relativo brasileiro de porte e UF em escala
logit (SCR.data, 12 meses; `model/calibracao.py`). Os dois ajustes aparecem
no laudo como `ajuste_porte_br` e `ajuste_uf_br`.

> **Achado — vazamento no prazo da SBA.** Prazo "redondo" (12, 24, 36…) tem
> 0,91% de perda; prazo "quebrado" (13, 25, 35…), 33,64% — 91% das perdas.
> O prazo é regravado depois do problema e carrega o desfecho: um modelo com
> ele teria AUC alta e falsa. **O prazo ficou fora**, e um teste
> (`tests/unit/test_features_v3.py`) impede que volte.
>
> **Ressalvas:**
> (1) AUC abaixo da do v2 (0.6141) — esperado: o v2 discriminava crédito
> pessoal; três features sem vazamento discriminam pouco. O ganho do v3 é a
> **validade da base** (PME, desfecho real), não a discriminação.
> (2) O Brier mal supera o preditor constante (0.0638 × 0.0640) — como no v2,
> o modelo ordena risco melhor do que estima probabilidade.
> (3) PME americana com garantia federal (viés de seleção), outro ciclo
> macroeconômico. O SCR calibra o **risco relativo** de porte e UF, não o
> nível absoluto (definições diferentes de inadimplência).
> (4) O ranking de setor SBA × SCR quase não concorda (Spearman ρ = 0.14, 20
> seções): o efeito de setor aprendido nos EUA pode não valer no Brasil.
> (5) A SBA não codifica 1–2 anos de idade; esses pedidos caem na faixa
> `startup` (hipótese em `model/mapeamentos.py`).
> (6) Faturamento não entra no modelo (a SBA não tem); fica no laudo como
> ⚠️ declarado.
> (7) Candidato boosted tree falhou no BQML (erro 80038528, como no v1); o
> baseline logístico segue sozinho, como o PLANO §5 permite.

<details>
<summary>Histórico — v1/v2 (Home Credit, crédito pessoal, aposentados)</summary>

| Métrica | v2 (`logreg_v2.json`) | v1 (`logreg_v1.json`) | Observação |
|---|---|---|---|
| KS | 0.1762 | 0.1767 | holdout aleatório, n=60.994 |
| AUC | 0.6141 | 0.6156 | |
| Brier | 0.0735 | 0.0735 | preditor constante: 0.0744 |
| ECE | 0.0013 | 0.0011 | |

O v2 corrigiu dois skews treino/serviço do v1 (sentinela `DAYS_EMPLOYED` e
setor como hash contínuo). Os dois foram aposentados porque a base era de
crédito pessoal, não de PME.

</details>

### Extração — `eval/laudo/results/laudo_eval_v7.json`

| Métrica | Valor | Meta | Status |
|---|---|---|---|
| F1 extração (micro, por campo) | 0.9868 (P 0.9933 / R 0.9803) | ≥ 0.90 | ✅ |
| Alucinação (valor em campo não mencionado) | 0 | — | ✅ |
| Recusa correta | 100% (17/17) | ≥ 95% | ✅ |
| Recusa indevida | 1.59% (1/63) | — | ⚠️ |
| Latência média | 5.78s | — | — |

Golden set: 80 itens (63 em escopo, 17 fora). Duas rodadas completas deram o
mesmo agregado (`laudo_eval_v7.json`, `laudo_eval_v7_rodada2.json`); por lote
variam — o Gemini deixou de ser determinístico em 2 itens de `setor`:

| Lote | Itens | F1 r1 / r2 | Recusa correta |
|---|---|---|---|
| original (v1–v6) | 50 (39 em escopo) | 0.9783 / 0.9819 | 11/11 |
| `v7_novos` | 30 (24 em escopo) | 1.0 / 0.9944 | 6/6 |

| F1 por campo | v5 (setor livre) | v6 (setor CNAE) | v7 (finalidade fechada, 80 itens) |
|---|---|---|---|
| porte, UF, anos, faturamento, valor, prazo | 0.987 – 1.0 | 0.987 – 1.0 | 0.992 – 1.0 |
| `setor` | 0.5974 | 0.9091 | **0.944** |
| `finalidade` | 0.8571 | 0.8571 | **0.992** |
| `cnpj` | — | — | 1.0 (1 item) |

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
> (4) (v6) `finalidade` era texto livre e o campo mais fraco — resolvido no v7.
> (5) A recusa indevida é o item 9 ("quero abrir uma empresa", sem UF nem
> porte) — anotação discutível, mantida para não ajustar o rótulo ao resultado.

**v7 — `finalidade` com vocabulário fechado e golden set ampliado:**
`finalidade` passou a ser um de 9 códigos (`agents/finalidades.py`: capital de
giro, estoque, refinanciamento, máquinas e equipamentos, veículos, obras e
reforma, tecnologia, expansão, abertura de empresa), imposto via
`response_schema`; o detalhe vai em `finalidade_detalhe` (livre, não avaliado).
Os 39 itens originais foram reanotados pela regra de desempate do prompt
("item comprado nomeado → categoria do item"), e 30 itens novos
(`"lote": "v7_novos"`) entraram com setores, finalidades e formas de escrever
fora dos exemplos do prompt (faturamento mensal, prazo em anos ou parcelas,
porte ausente, CNPJ no texto, recusa em inglês e por ilicitude).

> **Ressalvas (v7):**
> (1) O salto de `finalidade` (0.86 → 0.99) é quase todo **de método**, como o
> de `setor` no v6: sinônimos (`modernizacao`, `automacao`, `equipamentos`)
> viraram um código. O único erro restante é o item 9, recusado inteiro.
> (2) **O lote novo não é um holdout independente.** Os itens e as regras de
> desempate do prompt foram escritos pela mesma pessoa, no mesmo dia; F1 de
> 0.99–1.0 ali mede consistência com o vocabulário, não generalização a textos
> de terceiros. Em 6 dos 24 itens novos em escopo o golden aceita duas
> categorias (ex.: trator = máquina ou veículo; "construir chalés" = obra ou
> expansão), decididas pelo texto antes de rodar.
> (3) Os erros de `setor` restantes são CNAE de fato e variam entre rodadas:
> padaria → I, fotografia → R, joalheria → C (r1), farmácia → Q (r2).
> (4) O v7 não é comparável ao v6 no agregado: mudaram rótulos e itens. A
> comparação de modelos abaixo é do v6 e não foi refeita.

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

### Laudo (texto) — `eval/laudo/results/laudo_texto_v2.json`

Multi-agente (Extrator → Pesquisador → Redator) contra o **baseline de chamada
única** exigido pelo PLANO §5 (texto bruto + PD → laudo, mesmo modelo, regras e
schema de saída), com o **modelo v3** e a calibração SCR. 62 itens em escopo × 2
rodadas por braço; a PD é a mesma nos dois.

| Métrica (PLANO §5) | Meta | Multi-agente r1 / r2 | Baseline r1 / r2 |
|---|---|---|---|
| **Fidedignidade** — afirmações verificáveis com evidência | 100% | 99.89% / 99.89% (1.847 · 1.850) | 99.95% / 99.95% (1.994 · 1.979) |
| Laudos 100% fiéis | — | 61/62 · 61/62 | 61/62 · 61/62 |
| PD citada exatamente | — | 62/62 · 62/62 | 62/62 · 62/62 |
| **Verificado × declarado** — marcação correta por campo no texto | 100% | **98.15% / 98.46%** | 96.38% / 97.13% |
| Classificação estruturada por campo (`fonte_por_campo`) | — | **100%** | 0% (texto livre) |
| Latência da redação | — | 15.4s / 14.4s | 13.1s / 14.4s |

> **Meta de 100% de fidedignidade não atingida no v2.** As afirmações sem
> evidência são erros reais do Redator, mantidos na conta: números em formato
> ambíguo ("R$ 2.500.000.00", misturando milhar pt-BR e decimal en — 2 por
> rodada no multi-agente), um "5" sem fonte e uma norma citada fora de
> `evidencias` (baseline). Três lacunas do juiz apareceram com o v3 e foram
> corrigidas com teste, sem mudar nenhuma métrica do v1 (rejulgado idêntico):
> o nome "SBA 7(a)" não é número; CNPJ formatado vale se os dígitos batem com
> o pedido; o valor de setor entre crases vale se é o do pedido.

**Juiz determinístico** (`eval/laudo/fidedignidade.py`, sem LLM): todo número do
laudo precisa bater com o pedido, a PD ou os fatores (aceita arredondamento,
truncamento, % e razões entre valores do pedido); todo nome entre crases precisa
ser fator, campo ou a faixa derivada da PD; toda norma precisa estar no corpus
e em `evidencias`. Os textos ficam salvos no JSON: `--rejulgar` refaz o
julgamento sem LLM, e cada correção do juiz foi feita contra esses textos.

**Decisão do PLANO ("multi-agente só se justifica se superar o baseline"):
multi-agente mantido.** Praticamente empatam em fidedignidade (1–2
afirmações por rodada de diferença); o multi-agente vence em
verificado × declarado — a métrica do PLANO — por ter classificação estruturada
por campo (base para o ✅ quando houver consulta de CNPJ) e marcar melhor no
texto. Custo igual: calcular a PD exige extração estruturada em qualquer
arquitetura, então os dois fazem 2 chamadas ao LLM por laudo.

> **Ressalvas:**
> (1) **Achado do v1:** em 5 dos 152 laudos o Gemini escreveu o símbolo errado no
> lugar de ⚠️ — ☢, ‱, ‼ e **☑** (este parece "verificado" num dado declarado);
> 1 no multi-agente, 4 no baseline. Um laudo do baseline marcou em bloco ("todos
> ⚠️ declarados") e não campo a campo, o que conta como erro pela regra do prompt.
> (2) O juiz só checa afirmações verificáveis mecanicamente; frases
> qualitativas ("setor resiliente") não são avaliadas.
> (3) O único CNPJ do golden set é fictício (a consulta pública responde 400):
> nenhum campo sai verificado, então ✅ nunca é esperado neste eval.
> (4) O item 9 do golden set é recusado pelo Extrator e não chega ao Redator
> (62 de 63); o baseline não tem caminho de recusa e não foi testado fora de escopo.
> (5) Histórico: o v1 (`laudo_texto_v1.json`, modelo v2, 38 itens) teve 100% de
> fidedignidade nos dois braços e marcação 97.4%/100% × 94.9%/94.9%.

> **Ressalva:** o salto de F1 (0.84 → 0.95) veio de adicionar exemplos de
> mapeamento `setor→snake_case` no prompt do Extrator. Alguns exemplos são
> literalmente itens do golden set — há vazamento teste↔ajuste. O F1 medido
> provavelmente não generaliza tão bem para setores fora da lista de exemplos.

### Consulta de CNPJ — verificado × declarado

O Pesquisador (`agents/pesquisador/`) consulta o CNPJ na **BrasilAPI** (dados
abertos da Receita Federal; gratuita, sem chave). Um campo só vira ✅
**verificado** quando o dado público confere com o declarado: seção CNAE
(`cnae_fiscal` → seção, `agents/setores.py`), porte (MEI pela opção no Simei;
ME/EPP pelo porte cadastral; "DEMAIS" diverge de qualquer porte PME), UF e anos desde a abertura (tolerância de 1 ano).
Se diverge, o campo segue ⚠️ declarado e a divergência vai para
`cnpj_dados.divergencias` — o Redator é instruído a mostrá-la com os dois valores.
Faturamento, valor, prazo e finalidade são sempre declarados.

- **Só o CNPJ sai do GCP**; a resposta é reduzida aos campos de verificação —
  razão social (no MEI, costuma ser o nome da pessoa), sócios e contatos são
  descartados (LGPD art. 6º, III).
- Falha de rede, timeout (5s) ou CNPJ inexistente → tudo declarado; a consulta
  nunca derruba o laudo. `CNPJ_API_URL=""` desliga a consulta.
- Desvio do PLANO §3 (previa o `quimera-core`), registrado lá; a função é
  injetável e pode ser trocada.

> **Ressalva:** a consulta tem testes unitários com a forma real da resposta e
> smoke contra a API, mas **não tem eval**: o golden set é sintético e o único
> CNPJ dele é fictício (dígito verificador inválido — a API responde 400), então
> nenhum item exercita o caminho ✅. Medir isso exige pedidos com CNPJs reais de
> empresas públicas.

## Limites honestos

- A base de treino é de **PME americana** (SBA 7(a)), ajustada ao risco relativo
  brasileiro de porte e UF (SCR.data) — não é crédito PME brasileiro por operação,
  que não existe em base pública (sigilo bancário, LC 105/2001)
- O projeto demonstra o **método** (treino, calibração, monitoramento, governança),
  não um modelo pronto para concessão real
- `pd` vem SEMPRE do modelo (e da calibração determinística), nunca do LLM
- Mapeamentos NAICS → CNAE e faixas de idade documentados em `model/mapeamentos.py`

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

**Proteção.** A chave de analista (`X-API-Key`) vem do **Secret Manager**
(`pme-risk-api-key`, lido só pela SA da API) e nunca aparece em
`gcloud run services describe`; o código lê a env var `API_KEY_SECRET`. Sem a
var (dev local), tudo fica aberto.

- **Demo pública** (`ALLOW_UNAUTHENTICATED=1 CRIACAO_PUBLICA=1`): visitantes
  criam laudos **sem chave**, dentro de dois limites diários (UTC) — por IP
  (`LIMITE_POR_IP_DIA`, padrão 3; em memória, o IP não é gravado) e global
  (`LIMITE_GLOBAL_DIA`, padrão 30; contado na trilha de auditoria, sobrevive a
  reinícios). Acima deles, `429` com `Retry-After`. Com a chave, sem limite
  (`api/limites.py`).
- **Decidir no portão humano exige a chave sempre** (`PATCH /laudos/{id}/decisao`
  sem ela → `401`): visitante gera laudo, não aprova.
- **Privado** (padrão do `deploy_api.sh`): Cloud Run IAM (`Authorization:
  Bearer $(gcloud auth print-identity-token)`) e `POST /laudos` com a chave.

**Portão humano:** decisões são finais — decidir um laudo que já saiu de
`pendente` responde `409`. Cada decisão entra na `trilha_auditoria`
(`decisao_humana` com quem, quando e observação).

**Cota do Gemini:** 429/5xx são repetidos com backoff (`agents/gemini.py`);
se persistir, `POST /laudos` responde `503` com `Retry-After`.

**Corte de escopo deliberado (SPEC §5.1):** o laudo final é **só JSON** —
não há endpoint de HTML/PDF nesta fase.

## Monitoramento (drift)

`monitoring/drift_job.py` compara os últimos laudos com **pedidos PME
brasileiros** — operações do BNDES (indiretas automáticas, MICRO/PEQUENA,
2018–2022, sem cooperativas de crédito; só o agregado é gravado). Valor e prazo
por decis do porte, setor por PSI categórico. Comparar com o treino (SBA,
americano) dispararia sempre. Acima de 0.25 → log `WARNING` (log-based alert
do free tier).

```bash
# Local (requer ADC + GCP_PROJECT_ID)
uv run python -m monitoring.drift_job
```

No Cloud Run, roda como Job disparado por Cloud Scheduler semanal
(`infra/scripts/deploy_drift.sh`). Com menos de 100 laudos por feature o
PSI não é calculado (`amostra_insuficiente`): com n pequeno ele mede ruído
(n=30 → 68% de falso alarme em simulação; n=100 → 1%). Limites: valores do
BNDES são nominais de 2018–2022, e o crédito BNDES é direcionado/subsidiado;
porte e UF não entram no drift (o risco relativo deles vem do SCR).

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
bash infra/scripts/deploy_hosting.sh # Firebase Hosting na frente do Cloud Run
```

**Endereço público:** https://pme-risk-demo.web.app — Firebase Hosting repassa
todas as rotas para o Cloud Run (`firebase.json`), então frontend, assets e API
vêm da mesma imagem. O site tem nome próprio porque o site padrão do Firebase
usa o ID do projeto no endereço; pelo mesmo motivo não há `.firebaserc`
versionado (o projeto vem de `GCP_PROJECT_ID`). Limite: o rewrite do Hosting
para o Cloud Run corta em 60 s — um laudo leva ~20–30 s, mas retries do Gemini
com backoff podem passar disso.

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

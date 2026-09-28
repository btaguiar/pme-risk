# Plano: pme-risk — laudo de risco de crédito PME, auditável, em GCP

Documento de escopo do projeto de portfólio `pme-risk`. Público: o próprio
desenvolvedor (execução) e avaliadores de currículo (prova de competência).
Regras herdadas do [BRIEF.md](BRIEF.md): nenhum número sem fonte, nada de dados
privados (sem IDs de projeto, caminhos de servidor ou variáveis de ambiente).

---

## 1. Por que este projeto

Análise de 14 vagas de bancos/fintechs coletadas pelo SCOUT (ledger de vagas,
varredura de 2026-09-27): banco BV, PagBank, Getnet, Coru, CloudWalk, Ria Money
Transfer, BTG Pactual, entre consultorias que atendem o setor.

Skills mais pedidas (frequência nas 14 vagas): Python (10), LLM (8), RAG (8),
Machine Learning (7), AI Agents (7), IA Generativa (7), AWS (6), SQL (6).

O portfólio atual cobre Python, LLM, RAG e AI Agents (Cortex, quimera, pauta,
grifo). O que falta mostrar:

| Gap | Quem pede nas vagas |
|---|---|
| ML em produção + MLOps | PagBank ("monitorar e manter modelos em produção"), Ria, ATRA |
| Guardrails, evals, approval gates | Getnet ("evals, guardrails, harnesses"), Coru ("human approval gates", "instrument evals") |
| Cloud gerenciada | 6 de 14 vagas citam AWS/GCP/Azure |
| Domínio de risco e crédito | BV (auditoria interna com agentes e modelos preditivos), PagBank (soluções preditivas para decisão) |

O pme-risk fecha os quatro gaps num único sistema: **um modelo de risco
treinado e monitorado**, com **agentes que explicam e documentam** a decisão e
um **portão humano** antes do laudo final.

## 2. Problema

Transformar um pedido de crédito para PME em português (ex.: "clínica odontológica,
5 anos de operação, faturamento de R$ 2M, quer R$ 300k para expansão") em um
**laudo de risco** com:

1. **Probabilidade de inadimplência (PD)** e faixa de risco vindas de um modelo
   treinado — nunca de opinião de LLM;
2. **Fatores que mais pesaram** no score (contribuição por variável);
3. Cada dado marcado como **✅ verificado** (fonte pública) ou **⚠️ declarado**
   pelo solicitante — faturamento, por exemplo, não existe em base pública;
4. Toda afirmação do laudo acompanhada da **evidência ou norma que a sustenta**;
5. Um **portão de aprovação humana** (aprovar / corrigir / rejeitar) antes de o
   laudo ser finalizado, com registro de quem decidiu e quando.

**Regra de ouro:** só afirmar métricas reproduzíveis em `eval/`. Se não está no
eval, não entra no README nem no post.

**Divisão de responsabilidades:** o modelo decide o número; o LLM extrai,
pesquisa, explica e redige. O LLM não tem permissão para alterar a PD.

## 3. Arquitetura (Google Cloud)

```
pedido em pt-BR
   │
   ▼
Cloud Run — API FastAPI (orquestração)
   │
   ├─► 1. Extrator (Gemini) ─────► campos estruturados (setor, porte, UF, valor, prazo)
   │                               fora de escopo → recusa
   │
   ├─► 2. Pesquisador ───────────► núcleo do quimera → dados públicos do CNPJ (BigQuery)
   │
   ├─► 3. Modelo de risco ───────► BigQuery ML → PD + fatores (versão do modelo registrada)
   │
   ├─► 4. Redator (Gemini) ──────► explica o score, cita evidências e normas,
   │                               separa verificado de declarado
   │
   ├─► 5. Portão humano ─────────► analista aprova / corrige / rejeita
   │
   └─► 6. Trilha de auditoria ───► entradas, versão do modelo, prompts, decisão humana
                                    laudo final (HTML/PDF)

Cloud Scheduler ──► job de monitoramento: PSI (drift) da entrada vs. treino
```

Busca vetorial (normas e política de crédito): `BigQuery VECTOR_SEARCH` — não
Vertex AI Vector Search, que cobra por hora de instância.

### Relação com o quimera

O pme-risk é um **repositório separado**. O Pesquisador reusa o núcleo de busca
e enriquecimento de CNPJ do quimera como pacote Python (`quimera-core`,
instalável via git). Os dois READMEs apontam um para o outro: o quimera
responde "quais empresas?"; o pme-risk responde "qual o risco desta empresa?".

Pré-requisito: publicar o quimera (hoje sem remote) ou, no mínimo, o núcleo.
A Fase 1 não depende disso — pode começar antes.

### Tradução GCP ↔ vocabulário das vagas

As vagas pedem AWS com mais frequência que GCP. As competências são equivalentes
para fins de currículo — declarar a experiência real em GCP com a equivalência
que o recrutador busca:

| GCP (usado aqui) | Equivalente AWS citado nas vagas |
|---|---|
| Cloud Run | ECS / App Runner / Lambda |
| BigQuery | Athena / Redshift |
| BigQuery ML | SageMaker (treino/inferência tabular) |
| Pub/Sub | SNS / SQS |
| Secret Manager | Secrets Manager |
| Cloud Scheduler | EventBridge |

## 4. Dados

| Uso | Fonte | Observação |
|---|---|---|
| Treinar o modelo de risco | Base pública rotulada (Home Credit; alternativas: German Credit, Taiwan Default) | Rótulos reais de inadimplência — não sintéticos |
| Contexto Brasil | BCB — SCR.data (inadimplência por porte, setor, UF) | Prior / sanity check do modelo para PME brasileira |
| Dados da empresa | CNPJ público (Receita), via núcleo do quimera | Idade, CNAE, porte, situação cadastral |
| Normas citáveis | LGPD art. 20; Res. CMN 4.966; política de crédito fictícia escrita para o projeto | Conferir texto vigente antes de citar |
| Extração e recusa | Golden set sintético de ~50 pedidos pt-BR | Setores, portes, regiões, pedidos ambíguos e fora de escopo |

**Limite honesto (vai no README):** a base de treino não é de PME brasileira.
O projeto demonstra o método (treino, calibração, monitoramento, governança),
não um modelo pronto para concessão real.

## 5. Matriz de evals (versionada em `eval/`)

| Eval | Métrica | Limite de aceite |
|---|---|---|
| Discriminação do modelo | **KS, AUC/Gini** (holdout) | registrado por versão; melhor que baseline ingênuo |
| Calibração do modelo | **Brier, curva de calibração / ECE** | melhor que baseline ingênuo |
| Extração de entidades (setor, porte, UF, valor, prazo) | F1 | ≥ 0,90 |
| Fidedignidade do laudo | % de afirmações com evidência citada | 100% (zero afirmação solta) |
| Verificado vs. declarado | % de campos classificados corretamente | 100% |
| Recusa correta | % de pedidos fora de escopo recusados | ≥ 0,95 |
| Drift | **PSI** por variável, entrada vs. treino | alerta se PSI > 0,25 |
| Custo e latência | R$ e segundos por laudo | documentado por rodada de eval |

> **Status de implementação (2026-09-27):**
> - ✅ Extração (F1), Recusa → implementados em `eval/laudo/run_eval.py`
> - ✅ KS/AUC/Brier/ECE → implementados em `eval/model/run_eval.py`
> - ✅ Drift (PSI por variável) → implementado em `monitoring/drift_job.py`
>   (job de Cloud Run + Scheduler semanal via `infra/scripts/deploy_drift.sh`)
> - ❌ **Fidedignidade** e **Verificado vs. declarado** → **não implementados**
>   nesta fase. O schema do Redator (texto livre + lista plana de evidências)
>   não permite calcular essas métricas automaticamente. Para implementar:
>   (a) Redator estruturaria afirmações individuais com evidência associada,
>   ou (b) juiz separado que parseia o texto do laudo.

**Baselines obrigatórios:**
- **Modelo:** regressão logística simples. Modelo mais complexo só entra se
  superar em KS/AUC sem piorar calibração. → ✅ baseline logístico treinado;
  boosted tree candidato rejeitado (erro BQML 80038528)
- **Laudo:** uma chamada única ao Gemini (recebe PD + dados, redige o laudo),
  sem agentes. A arquitetura multi-agente só se justifica se superar o baseline
  na matriz acima. Empate técnico = ficar com o baseline e registrar o resultado.

### Resultados (2026-09-27)

**Modelo — `eval/model/results/logreg_v1.json`:**

| Métrica | Valor | Meta | Status |
|---|---|---|---|
| KS | 0.1767 | — | baseline |
| AUC | 0.6156 | — | baseline |
| Brier | 0.0735 | — | baseline |
| ECE | 0.0011 | — | baseline |
| Holdout | 60.994 amostras | — | — |

**Extração — `eval/laudo/results/laudo_eval_v3.json`:**

| Métrica | Valor | Meta | Status |
|---|---|---|---|
| F1 extração | 0.9539 | ≥ 0.90 | ✅ |
| Recusa correta | 90.91% (10/11) | ≥ 0.95 | ⚠️ |
| Latência média | 5.73s | — | — |

> Ressalva: F1 pode estar inflado por vazamento teste↔ajuste (exemplos no
> prompt são itens do golden set). Ver README.

## 6. Fases (~10 semanas, timebox)

| Fase | Prazo | Entrega | Critério de pronto | Status |
|---|---|---|---|---|
| **1 — Modelo** | 3 semanas | Treino no BigQuery ML, baseline logístico, KS/AUC/Brier, versionamento | Métricas do modelo em `eval/`; funciona sozinho | ✅ Completa |
| **2 — Laudo** | 4 semanas | Extrator + Pesquisador + Redator + portão humano + trilha de auditoria; golden set; baseline de chamada única | Multi-agente supera o baseline (ou decisão registrada) | ✅ Estrutural |
| **3 — Produto** | 3 semanas | Deploy em Cloud Run, job de drift, laudo navegável, README | Demo pública; post LinkedIn com números do eval | 🔧 Código completo; checklist de aceite executado (Docker local, smoke 401/404/201, e2e real, drift, budget); IAM preparada (SA + papéis BQ); falta o deploy |

Se uma fase estourar o prazo, corta-se escopo — não se estende o prazo.
Fase 2 aceitável sem três agentes separados, se o baseline empatar.

## 7. Custos e créditos

| Item | Fonte |
|---|---|
| Créditos disponíveis | R$ 1.753,25 (trial, conferido em 2026-09-27) |
| Validade | ~89 dias (até ~2026-12-25) |
| Gasto alvo do projeto | **< R$ 200** (envelope, não meta) |

Os serviços centrais têm camada gratuita permanente (limites conferir em
cloud.google.com/free antes de cada rodada de eval):

- Gemini API (modelo flash) — free tier por minuto de request;
- BigQuery — 1 TB de consulta e 10 GB de storage por mês (BigQuery ML consome
  essa cota no treino — medir antes de retreinar);
- Cloud Run — 2 milhões de requests por mês;
- Cloud Scheduler — poucos jobs gratuitos por conta.

**Regra de sobrevivência do demo:** o que continuar rodando depois de
2026-12-25 deve caber no free tier. O demo do portfólio não pode morrer junto
com o trial — ou seja, nada de dependência de serviço cobrado por hora.

**Disciplina:**

1. Projeto GCP próprio (separado do quimera), com budget alerts em
   50% / 80% / 100% desde o primeiro dia;
2. Rodadas de eval com modelo flash; modelos maiores só para comparação pontual,
   registrada;
3. Vertex AI Pipelines fora do escopo — BigQuery ML cobre treino e inferência.

## 8. Não fazer

- **Dados reais de pessoas ou empresas sensíveis.** O golden set é sintético.
  CNPJ de exemplo deve ser fictício ou de empresas públicas sem vínculo com
  decisões reais de crédito.
- **Deixar o LLM definir ou ajustar a PD.** O número vem do modelo; o LLM explica.
- **Apresentar o modelo como pronto para concessão real.** A base de treino não
  é de PME brasileira — o limite vai explícito no README.
- **Afirmar performance sem eval que a reproduza.** Sem número órfão no README.
- **Depender de serviço pago pós-trial.** Ver regra de sobrevivência (§7).
- **Expôr detalhes de infra privada.** Sem IDs de projeto, contas de serviço,
  chaves ou nomes de variáveis de ambiente em qualquer material público.

## 9. O que este projeto prova para a vaga

- **ML em produção + MLOps:** modelo versionado, métricas por versão, drift
  monitorado (padrão PagBank/ATRA);
- **AI Agents com approval gates** e trilha de auditoria (padrão Coru/BV),
  ancorados em exigência legal (LGPD art. 20 — revisão de decisão automatizada);
- **Citação de evidência, separação verificado/declarado e recusa correta**
  (padrão grifo/GOV-1);
- **Evals versionados** como critério de aceite, com baseline obrigatório
  (padrão Getnet);
- **Cloud gerenciada** com disciplina de custo (padrão PagBank/CloudWalk);
- **Vocabulário de risco de crédito** — PD, KS, calibração, PSI, regulação —
  a língua de quem entrevista em banco;
- **Composição de sistemas:** reusa o quimera como componente em vez de copiar.

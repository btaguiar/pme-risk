# Reavaliação de implementação — pme-risk

**Data:** 2026-09-28 (mesmo dia da avaliação original, após as correções)
**Base de comparação:** [`avaliacao-2026-09-28.md`](avaliacao-2026-09-28.md) — nota 7,0
**Foco:** portfólio/vaga (mesma rubrica e pesos da avaliação original)
**Método:** execução real — testes, e2e contra GCP, API local e em container,
deploy no Cloud Run com smoke, job de drift disparado pelo Scheduler, eval de
extração em 2 rodadas por modelo — mais conferência de cada achado no código.

> **Viés declarado.** Esta reavaliação foi escrita pelo mesmo agente que
> implementou as correções. Os números vêm de `eval/*/results/` e dos testes,
> mas as notas da rubrica são julgamento. Vale uma revisão independente antes de
> citar a nota em material público.

---

## Nota: **8,5 / 10** (antes 7,0)

**Parecer.** Os quatro achados críticos foram corrigidos e validados em execução,
não só no código: o skew treino/serviço saiu (modelo `logreg_v2`), o deploy roda
de verdade (Cloud Run privado, smoke 403/401/422/201/200/409), os IDs de projeto
saíram dos arquivos versionados e a chave da API foi para o Secret Manager,
rotacionada. O F1 da extração deixou de ser inflado pelo método e agora vem com
teste de alucinação, recusa indevida e comparação entre quatro modelos. O que
segura a nota abaixo de 9: três evals da matriz do PLANO seguem sem implementar
(fidedignidade do laudo, verificado × declarado, baseline de chamada única), o
Redator não tem nenhuma métrica, e os IDs de projeto continuam no **histórico**
do git — o que bloqueia publicar o repositório como está.

---

## Rubrica

| # | Dimensão | Peso | Antes | Agora | O que mudou |
|---|---|---|---|---|---|
| 1 | Completude vs PLANO/SPEC | 2,0 | 1,5 | **1,6** | Comparação de modelos registrada (PLANO §7); 3 linhas da matriz de evals e o baseline de chamada única seguem pendentes |
| 2 | Código/arquitetura | 2,0 | 1,5 | **1,7** | Portão com transição atômica e 409; retry/503 no Gemini; `setor` como enum imposto ao LLM. Restam `json.loads` sem tratamento nos agentes e um `assert` em rota |
| 3 | Testes e evals | 1,5 | 1,0 | **1,3** | 48 → 79 testes; eval de extração com testes próprios, método honesto, 2 rodadas; o Redator segue sem métrica |
| 4 | ML/MLOps | 1,5 | 0,9 | **1,2** | Skew e sentinela corrigidos com métricas equivalentes; Brier ingênuo publicado; drift com amostra mínima. O modelo segue fraco (AUC 0,61) |
| 5 | Segurança/privacidade | 1,0 | 0,7 | **0,85** | Secret Manager + rotação, deploy privado, container sem root, scanner bloqueia valores do `.env`. IDs de projeto ainda no histórico |
| 6 | Documentação/honestidade | 1,0 | 0,8 | **0,95** | README, PLANO e SPEC sincronizados com os JSONs; cada ganho de métrica vem com a ressalva que o limita |
| 7 | Prontidão de produto/demo | 1,0 | 0,6 | **0,9** | Deploy executado e verificado ponta a ponta, incluindo job agendado; demo privada (IAM + X-API-Key) |
| | **Total** | **10,0** | **7,0** | **8,5** | |

---

## Status dos achados originais

| Achado | Status | Evidência |
|---|---|---|
| **C1** skew em `occupation_type_encoded` | ✅ Resolvido | Feature removida no v2: setor PME não tem análogo no treino; hash usado como número dava PD arbitrária por setor (`model/sql/04_load_features_v2.sql`) |
| **C2** deploy sem `GCP_PROJECT_ID` | ✅ Resolvido | Reproduzido antes (500 em tudo exceto healthz); corrigido e validado no Cloud Run |
| **C3** IDs reais no scanner de segredos | ⚠️ Parcial | Fora de todos os arquivos atuais (padrões vêm de `.env` e de arquivo local ignorado). **Ainda em 3–4 commits antigos** |
| **C4** sentinela `DAYS_EMPLOYED=365243` | ✅ Resolvido | Vira NULL + flag no v2. Antes, invertia o sinal de "tempo de operação" no laudo |
| **M1** decisão humana fora da auditoria | ✅ Resolvido | Decisão entra na `trilha_auditoria`; re-decidir → 409 (antes sobrescrevia) |
| **M2** F1 inflado pelo método | ✅ Resolvido | Método v5: na mesma rodada, o método antigo dava 0,9592 e o novo 0,9167 |
| **M3** eval sobrescrevia o JSON com 5 itens | ✅ Resolvido | Rodada parcial grava `*_parcial` |
| **M4** Brier ≈ baseline ingênuo, não dito | ✅ Documentado | 0,0735 × 0,0744 no JSON e no README. Não é correção do modelo, é transparência |
| **M5** agentes sem tratamento de erro | ⚠️ Parcial | Retry com backoff e 503 para 429/5xx. `json.loads` e `os.environ[...]` sem tratamento nos agentes |
| **M6** matriz de evals incompleta | ❌ Aberto | Fidedignidade, verificado × declarado e baseline de chamada única não implementados; stub de CNPJ ainda devolve `None` |
| **B1** `assert` em rota | ❌ Aberto | `api/routes/laudos.py` |
| **B2** teste que não verificava nada | ✅ Resolvido | Virou checagem real de campos essenciais |
| **B3** golden set sem teste da métrica | ✅ Resolvido | `tests/unit/test_eval_laudo.py` |
| **B4** modelo aposentado como `candidate_rejected` | ✅ Resolvido | Status `retired` |
| **B5** container como root / deps pesadas | ⚠️ Parcial | Roda como `app`; `pandas`/`scipy` ainda são dependências de runtime |
| **B6** chave da API em env var | ✅ Resolvido | Secret Manager, acesso só da SA da API, rotacionada; versão antiga desativada |
| **B7** PLANO desatualizado | ✅ Resolvido | PLANO cita v2 do modelo e v6 do eval |
| **B8** PATCH sem máquina de estados | ✅ Resolvido (estados) | Transição atômica e 409. Não há identidade por analista além do IAM do serviço |
| **B9** `VERTEX_LOCATION` não documentada | ❌ Aberto | Ausente do `.env.example` |
| **B10** drift parcial | ⚠️ Parcial | Amostra mínima de 100 (n=30 → 68% de falso alarme em simulação); segue com 4 features |
| **B11** custo chutado | ⚠️ Parcial | Tokens medidos para os modelos alternativos; custo do Gemini segue como estimativa |

---

## Achados novos — só apareceram executando

Nenhum destes estava na avaliação original, que foi estática. Todos corrigidos,
exceto onde indicado.

| Achado | Como apareceu |
|---|---|
| 429 do Gemini virava 500 cru | 3 vezes durante a validação |
| `/healthz` dá 404 no Cloud Run | Plataforma reserva paths terminados em "z"; criado `/health` |
| Redator narrava fator constante como fato ("ausência de registro de empregados") | Laudo real, após o v2. Fatores constantes no serviço saíram da explicação |
| Deploy nunca tinha rodado: buildpacks no lugar do Dockerfile, papel IAM inexistente (`cloudrun.invoker`), prompt interativo escondido no Scheduler | Primeiro deploy real |
| Drift alertava sempre (PSI ≈ 11 com 5 laudos) | Execução do job |
| `UPDATE` do registry falharia com streaming buffer | Promoção do v2 |
| **Vazamento teste↔prompt escondia uma falha**: sem o item 0 do golden set como exemplo, o Extrator recusava pedidos sem porte explícito | Eval v6. Corrigido com a regra legal de porte (LC 123/2006) |
| Schema frouxo quebra outros provedores: `deepseek-v4-pro` recusava devolvendo só `{"pedido": null}` | Comparação de modelos |
| Travamentos de `gcloud`/`bq`/e2e | **Ambiente, não projeto:** IPv6 quebrado na rede local. Contornado forçando IPv4 no Python do gcloud |

---

## Métricas atuais (fonte: `eval/*/results/`)

**Modelo — `logreg_v2.json`** (mesmo holdout do v1, n = 60.994)

| KS | AUC | Brier | Brier ingênuo | ECE |
|---|---|---|---|---|
| 0,1762 | 0,6141 | 0,0735 | 0,0744 | 0,0013 |

**Extração — `laudo_eval_v6.json`** (2 rodadas, mesmo agregado)

| F1 (micro) | Precisão | Recall | Alucinação | Recusa correta | Recusa indevida |
|---|---|---|---|---|---|
| 0,9601 | 0,9707 | 0,9498 | 0 | 11/11 | 1/39 |

Evolução do F1 de extração, com o que mudou em cada passo:

| Versão | F1 | O que mudou |
|---|---|---|
| v4 (método antigo) | 0,9493 | — |
| v5 | 0,9167 | Só o método: falhas no denominador, alucinação medida, 9 campos anotados |
| v6 | 0,9601 | `setor` como seção CNAE (0,60 → 0,91); regra de porte explícita |

---

## Comparação de modelos no Extrator

**Pergunta:** outro modelo extrai melhor, mais rápido ou mais barato que o
`gemini-2.5-flash`? Os alternativos rodaram via API compatível com OpenAI
(Alibaba Model Studio), **só no eval**: mesmo prompt, mesmo schema em JSON Schema
strict, mesmo golden set, 2 rodadas completas cada
(`eval/laudo/results/laudo_eval_v6_*.json`).

**Seleção.** Dos 15 modelos do endpoint, ficaram de fora: áudio e imagem;
`auto`, um roteador que escolhe o modelo e não permite resultado reproduzível;
versões superadas da mesma linha. Dos 5 candidatos de texto, dois foram
excluídos por não imporem o schema. `glm-5.3` aceita `json_schema` e o ignora:
devolveu setor fora do enum CNAE. `deepseek-v4.1-flash` rejeita o parâmetro. Com
JSON livre, o eval mediria erro de formato, não extração.

| Modelo | F1 r1 / r2 | Média | `setor` | `finalidade` | Alucinação | Recusa correta | Latência | Tokens de saída |
|---|---|---|---|---|---|---|---|---|
| **gemini-2.5-flash** (produção) | 0,9601 / 0,9601 | 0,9601 | 0,909 | 0,857 | 0 | 22/22 | **8,4s** | não medido |
| qwen3.8-flash | 0,9529 / 0,9638 | 0,9584 | 0,961 | 0,792 | 0 | 22/22 | 15,5s | ~950 |
| qwen3.8-max | 0,9710 / 0,9578 | 0,9644 | 0,980 | 0,850 | 0 | 21/22 | 25,1s | ~890 |
| deepseek-v4-pro | 0,9553 / 0,9529 | 0,9541 | 0,994 | 0,723 | 1 | 22/22 | 11,7s | ~740 |

**Leitura.**
1. **O F1 empata.** As médias ficam a até 1 ponto umas das outras, menos que a
   variação entre rodadas do próprio qwen3.8-max (1,3 ponto; a rodada 2 inclui
   um timeout de 180s, contado como falha). Com 39 itens em escopo, o eval não
   separa diferenças desse tamanho.
2. **Os alternativos classificam CNAE melhor e `finalidade` pior.** A primeira
   parte parece real (0,96–0,99 × 0,91, estável nas duas rodadas). A segunda é
   enviesada a favor do Gemini: `finalidade` é texto livre, e prompt e rótulos
   foram iterados sobre o Gemini desde o v1.
3. **O Gemini é o mais rápido e o único determinístico entre rodadas.** Todos os
   modelos raciocinam por padrão; os alternativos gastaram ~740–950 tokens de
   saída por pedido.
4. **Um achado de robustez, não de qualidade.** Com `fora_de_escopo` opcional no
   schema, o deepseek-v4-pro acertou 0/11 recusas na primeira execução: recusava,
   mas omitia os campos da recusa. O extrator alternativo passou a marcar todos
   os campos como obrigatórios (semântica strict) e os 3 modelos rodaram de novo
   nas mesmas condições; a tabela é dessa segunda execução.

**Decisão: `gemini-2.5-flash` segue em produção** — empate em qualidade, melhor
latência e estabilidade, e nenhum dado sai do GCP. Levar outro provedor para
produção exigiria análise de LGPD antes de qualquer métrica: transferência
internacional (art. 33), retenção e uso dos dados para treino. No eval isso não
se aplica porque o golden set é sintético.

**O que a comparação não mede:** o Redator (não há eval de laudo), custo em
dinheiro (o endpoint usado é um plano por tokens) e generalização para textos
fora do golden set.

---

## Pendências priorizadas

| # | Ação | Por quê | Esforço |
|---|---|---|---|
| 1 | Limpar os IDs de projeto do **histórico** do git (reescrever ou publicar histórico novo) | Pré-requisito para publicar o repositório | baixo, mas destrutivo — decisão do dono |
| 2 | Eval do Redator: fidedignidade (% de afirmações com evidência) e baseline de chamada única | Maior lacuna da matriz do PLANO; hoje o texto do laudo não tem métrica | médio |
| 3 | `finalidade` com vocabulário fechado, como foi feito com `setor` | Campo mais fraco (0,86) e o que enviesa a comparação de modelos | baixo |
| 4 | Ampliar o golden set além de 39 itens em escopo, com casos novos fora do prompt | Separar diferenças de ~1 ponto; medir generalização das notas CNAE | médio |
| 5 | Tratamento de erro restante nos agentes, `assert` em rota, `VERTEX_LOCATION` no `.env.example` | Higiene (M5, B1, B9) | baixo |
| 6 | Consulta real de CNPJ no Pesquisador | Hoje nenhum campo sai "verificado" | médio |

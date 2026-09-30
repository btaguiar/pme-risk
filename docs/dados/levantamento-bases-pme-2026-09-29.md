# Levantamento de bases para o modelo de risco PME

**Data:** 2026-09-29
**Pergunta:** existe base pública de crédito PME melhor que a Home Credit
(crédito pessoal) para treinar e calibrar o modelo?
**Método:** download dos arquivos oficiais e perfil com pandas (SBA, SCR.data)
ou leitura em streaming (BNDES, 1,2 GB). Os números abaixo são desses arquivos,
nas versões indicadas. São **exploração de dados, não métrica de modelo**: nada
aqui entra no README como desempenho (BRIEF §1).

> **Resumo.** Não há base pública brasileira de PME com dado por operação e
> rótulo de inadimplência: dado por operação é coberto por sigilo bancário
> (LC 105/2001). A proposta combina três fontes. A **SBA 7(a)** (EUA) traz o
> rótulo e serve para treinar. O **SCR.data** (BCB) calibra a PD à
> inadimplência brasileira. O **BNDES** dá as distribuições de valor e prazo de
> um pedido PME brasileiro. Achado crítico: na SBA, o **prazo vaza o
> desfecho** e não pode ser feature.

---

## 1. SBA 7(a) — treino

**Fonte:** [SBA Open Data — 7(a) & 504 FOIA](https://data.sba.gov/dataset/7a-504-foia),
arquivos `FOIA_7a_*_asof_260630.csv` (atualização trimestral) e
`7a_504_foia_data_dictionary.xlsx`. O perfil abaixo usa `FOIA_7a_FY2010_FY2019`
(255 MB, 545.751 empréstimos, 42 colunas).

**Rótulo** (`LoanStatus`): `CHGOFF` = baixado como perda; `PIF` = quitado
(escrito `P I F` no arquivo); `EXEMPT` = ativo, com o status ocultado pela FOIA
Exemption 4; `CANCLD` = cancelado; `COMMIT` = não desembolsado.

| Status | Empréstimos |
|---|---|
| PIF | 394.721 |
| CANCLD | 66.744 |
| EXEMPT | 50.089 |
| CHGOFF | 34.153 |
| COMMIT | 44 |

**Censura por safra.** Quanto mais recente a safra, mais empréstimos seguem
ativos (`EXEMPT`). Calcular a taxa só sobre os resolvidos infla as safras
recentes, porque a perda aparece antes da quitação.

| Safra (FY) | % EXEMPT | % CHGOFF entre resolvidos |
|---|---|---|
| 2010 | 1,4 | 9,35 |
| 2012 | 2,6 | 6,46 |
| 2014 | 4,0 | 6,70 |
| 2015 | 5,1 | 7,28 |
| 2017 | 14,4 | 9,18 |
| 2019 | 27,1 | 9,67 |

→ **Janela de treino proposta: FY2010–2015.** São 256.464 empréstimos
resolvidos, com 3,2% ainda EXEMPT e 7,18% de CHGOFF.

**Sinal por segmento** (resolvidos, FY2010–2019):
- **Idade do negócio (`BusinessAge`):** "Existing, 5 or more years" ≈ 6%;
  demais faixas (startups, menos de 5 anos, troca de controle) ≈ 7–10%.
- **Setor (NAICS, 2 dígitos):** 62 saúde 5,22%; 33 indústria 6,61%;
  72 alimentação/alojamento 8,89%; 45 varejo 10,28%; 71 artes/recreação 10,53%.
- **Empregos (`JobsSupported`):** sinal fraco (5,7%–8,6%). O campo soma
  empregos criados e mantidos, e a SBA não o audita, então é um proxy ruim de
  porte.

### ⚠️ Vazamento no prazo (`TermInMonths`)

| Prazo | % CHGOFF | Empréstimos |
|---|---|---|
| "Redondo" (12, 24, 36, 48, 60, 72, 84, 96, 120, 180, 240, 300) | 0,91 | 336.465 |
| "Quebrado" (13, 25, 30, 35…) | **33,64** | 92.409 |

91% das perdas (31.088 de 34.153) têm prazo "quebrado". A leitura mais provável
é que o prazo seja regravado depois do problema (renegociação ou compra da
garantia), carregando informação do desfecho. Um modelo com esse campo teria
AUC alta e falsa. **Decisão: o prazo fica fora das features da SBA.** O PSI e o
laudo continuam usando o prazo do pedido, mas ele não entra no treino.

**Mapeamento para o pedido do pme-risk:**

| Pedido | SBA | Situação |
|---|---|---|
| `setor` | `NaicsCode` → seção CNAE (aproximado) | ✅ |
| `anos_operacao` | `BusinessAge` (faixas) | ✅ categórica |
| `valor_solicitado` | `GrossApproval` (USD) | ✅ |
| `porte` | `JobsSupported` | ⚠️ proxy fraco; calibrado pelo SCR |
| `prazo_meses` | `TermInMonths` | ❌ vazamento |
| `faturamento_anual_declarado` | — | ❌ inexistente; fica só no laudo (⚠️ declarado) |
| `uf` | — | calibrado pelo SCR |

**Limites:** empresas americanas, outro ciclo macroeconômico, e todos os
empréstimos têm garantia federal (viés de seleção). O arquivo traz nome e
endereço do tomador: descartar na ingestão.

---

## 2. SCR.data (BCB) — calibração

**Fonte:** [Portal de Dados Abertos do BCB — SCR.data](https://dadosabertos.bcb.gov.br/dataset/scr_data),
Versão 2 (`https://www.bcb.gov.br/pda/desig/scrdata_{ANO}.zip`, um CSV mensal de
~100 MB); [metodologia](https://www.bcb.gov.br/pda/desig/metodologia_versao2.pdf).
Perfil de `scrdata_202607.csv` (data-base jul/2026, 310.459 linhas agregadas).

- Colunas usadas: `cliente` (PF/PJ), `porte`, `cnae_ocupacao` (título da seção
  CNAE), `uf`, `modalidade`, `carteira_ativa`, `carteira_inadimplencia`.
- **Os títulos de seção batem com `agents/setores.py`** em 19 de 22 casos. As
  exceções são "Água, esgoto…", com título mais longo no SCR, "Organismos
  internacionais…" e "Não informados".
- O dado é **agregado**, não serve para treinar por operação.

**Inadimplência PJ, jul/2026** (`carteira_inadimplencia / carteira_ativa`):

| Porte | % | Carteira (R$ bi) |
|---|---|---|
| Micro | 7,58 | 127,8 |
| Pequeno | 7,43 | 445,6 |
| Médio | 4,70 | 718,1 |
| Grande | 0,52 | 1.514,7 |

Micro + Pequeno por seção (maiores carteiras): comércio 9,49%; indústria de
transformação 7,09%; transporte 8,47%; construção 7,16%; alojamento e
alimentação 10,58%; saúde 5,64%. Por UF: de 5,96% (SP) a 13,08% (AC).

**Coerência com a SBA:** alimentação entre os setores mais altos e saúde entre
os mais baixos nas duas bases.

**Cuidado de definição:** no SCR, a inadimplência é estoque (vencido acima de
90 dias sobre a carteira ativa). Na SBA, é perda acumulada ao longo da vida do
empréstimo. As métricas não são iguais, então **a calibração usa o risco
relativo entre segmentos**, não o nível absoluto do SCR como PD.

---

## 3. BNDES — distribuições brasileiras (sem rótulo)

**Fonte:** [Dados abertos BNDES — operações de financiamento](https://dadosabertos.bndes.gov.br/dataset/operacoes-financiamento),
arquivo de operações indiretas automáticas (1,2 GB, 2.148.456 operações, 30
colunas; no arquivo lido, contratações de 2002 a 2022).

- Colunas úteis: UF, data, valor contratado e desembolsado, juros, custo
  financeiro, **carência e amortização (meses)**, produto, **subsetor CNAE com
  código**, porte do cliente, banco repassador.
- Porte: MICRO 968.897; PEQUENA 445.737; MÉDIA 360.323; GRANDE 373.499.
- **Sem rótulo de inadimplência.** `situacao_da_operacao` só tem `LIQUIDADA`
  (2.089.441) e `ATIVA` (59.015). Na operação indireta, o risco do cliente
  final é do banco repassador. Para o BNDES, a operação liquida quando o banco
  paga, e o desfecho da empresa não é dado do BNDES.
- CNPJ mascarado; nome do cliente aberto (dado pessoal em PF/MEI). **Usar só
  agregados.**
- Viés: crédito direcionado e subsidiado (TJLP, Finame), não o crédito PME em
  geral.

**Usos propostos:** distribuição de referência brasileira para o PSI (o
treino será americano, e sem isso o drift dispararia sempre); prazo padrão
realista por porte e setor quando o pedido não informa; golden set com valores
e prazos da distribuição real.

---

## 4. Descartadas

| Base | Motivo |
|---|---|
| Lending Club (`purpose = small_business`) | Tomador pessoa física: mesmo problema da Home Credit |
| Falências de empresas polonesas (UCI) | Exige índices de balanço que o pedido não tem |
| `basedosdados.br_me_cnpj` (BigQuery) | Cadastro, não crédito. Consulta direta custa ≥ 51,8 GB por CNPJ, e os snapshots recentes estão restritos por row-level security (medido em 2026-09-29) |

---

## 5. Desenho proposto

```
SBA 7(a) FY2010–2015 ──► treino (rótulo CHGOFF × PIF)
                          features: setor (NAICS→CNAE), idade, valor — sem prazo
                          validação temporal: treino 2010–2013, teste 2014–2015
                          baseline logístico obrigatório (PLANO §5)
SCR.data ──────────────► calibração relativa por setor × porte × UF
BNDES ─────────────────► referência de drift, prazo padrão, golden set
```

Ressalva que substitui a atual no README: "modelo treinado em PME americana
(SBA 7(a)), calibrado à inadimplência relativa brasileira (SCR.data)", no lugar
de "base de crédito pessoal".

**Custo estimado no BigQuery:** SBA 2010–2019 (~0,26 GB em CSV) + 2 anos de SCR
(~2,5 GB descompactado) cabem no free tier de armazenamento (10 GB) e de
consulta (1 TB/mês).

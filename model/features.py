"""Feature engineering para o modelo de risco pme-risk.

MAPA DE FEATURES — SBA 7(a) → pedido PME (SPEC §3.2, plano do v3)

O v3 troca a base de treino: crédito pessoal (Home Credit, `logreg_v2`) →
empréstimos reais a PME (SBA 7(a) FOIA, `logreg_v3`). A decisão e os limites
estão em docs/dados/levantamento-bases-pme-2026-09-29.md e
docs/superpowers/plans/2026-09-29-modelo-v3-sba.md.

| Feature       | Treino (SBA 7(a))                    | Serviço (pedido)                   |
|---------------|--------------------------------------|------------------------------------|
| secao_cnae    | NaicsCode → seção CNAE (mapeamentos) | pedido.setor                       |
| faixa_idade   | BusinessAge → faixa (mapeamentos)    | pedido.anos_operacao → mesma faixa |
| log_valor_usd | ln(GrossApproval), USD               | ln(valor_solicitado / fator PPP)   |

Três features é pouco, e é de propósito: é o que existe dos dois lados sem
vazamento nem proxy inventado. Espera-se AUC modesta — o ganho do v3 está na
validade da base, não na discriminação (README).

FORA DO MODELO (v3):
- prazo (TermInMonths): VAZAMENTO — prazo "quebrado" tem 33,64% de CHGOFF
  contra 0,91% do redondo (a regra é regravada depois do problema;
  levantamento §1). Guardado por tests/unit/test_features_v3.py.
- faturamento: a SBA não tem; fica só no laudo (⚠️ declarado). Uma razão
  valor/faturamento sem análogo no treino repetiria o erro do hash de setor
  do v1.
- porte e UF: a SBA não vê; entram como calibração pós-modelo em escala
  logit (SCR.data, model/calibracao.py), não como feature.

CONVERSÃO DE VALOR (decisão P1): o pedido é em BRL e o treino em USD. Usa o
fator PPP do Banco Mundial — compara poder de compra; o câmbio de mercado
faria um pedido brasileiro parecer ~2× menor. Indicador PA.NUS.PPP, Brasil,
ano 2025 (último disponível em 2026-09-29):
https://api.worldbank.org/v2/country/BRA/indicator/PA.NUS.PPP

LIMITES HONESTOS:
- A base de treino é de PME americana com garantia federal (viés de seleção)
  e outro ciclo macroeconômico.
- O risco relativo brasileiro (porte, UF) entra pela calibração SCR; o nível
  absoluto da PD NÃO é calibrado pelo SCR (definições diferentes).
- pd (probabilidade de inadimplência) vem SEMPRE do modelo, nunca do LLM.

REFERÊNCIA: PLANO §4, SPEC §3.2, BRIEF.md
"""

from __future__ import annotations

# Versão do feature set — mudar quando o mapeamento for revisado
FEATURE_SET_VERSION = "v3_sba"

# Tabela BigQuery do feature set atual (treino, eval e drift leem daqui)
FEATURES_TABLE = "features_v3"

# Fator PPP (BRL por US$ de paridade de poder de compra) — fonte no docstring
FATOR_PPP_BRL_POR_USD = 2.55440835439356  # Banco Mundial, PA.NUS.PPP, Brasil, 2025

# Features congeladas para o treino
FEATURE_COLUMNS = [
    "secao_cnae",  # STRING — seção CNAE 2.0 (21 códigos, agents/setores.py)
    "faixa_idade",  # STRING — startup | 2_5 | 5_mais | desconhecida
    "log_valor_usd",  # FLOAT64 — ln do valor em US$ PPP
]

# Coluna alvo: CHGOFF = 1, PIF = 0 (D1 do plano)
TARGET_COLUMN = "target"

# Split temporal (D5): treino FY2010–2013, holdout FY2014–2015
SPLIT_COLUMN = "split"
SAFRA_COLUMN = "approval_fy"  # metadado do eval por safra; nunca entra no treino

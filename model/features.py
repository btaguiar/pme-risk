"""Feature engineering para o modelo de risco pme-risk.

MAPA DE FEATURES — Home Credit → PME (SPEC §3.2)

Esta é uma HIPÓTESE DE TRABALHO, não um resultado de EDA. A tabela abaixo
deve ser revisada após a análise exploratória (semana 1) e o resultado
registrado em eval/model/results/ antes de qualquer treino ser citado
como "final".

| Campo do pedido PME          | Coluna Home Credit análoga | Nota |
|------------------------------|----------------------------|------|
| faturamento_anual_declarado  | AMT_INCOME_TOTAL           | proxy de capacidade de pagamento |
| valor_solicitado             | AMT_CREDIT                 | |
| prazo_meses                  | AMT_CREDIT / AMT_ANNUITY   | HC não tem prazo explícito em meses |
| anos_operacao                | DAYS_EMPLOYED (convertido)  | proxy de maturidade/estabilidade |
| (sempre 0 no serviço)        | DAYS_EMPLOYED = 365243     | sem_emprego_registrado — sentinela do HC |
| setor                        | —                          | FORA do modelo desde v2 (ver abaixo) |
| uf                           | REGION_RATING_CLIENT       | proxy de risco regional, não geografia |

FEATURE SET v2 (04_load_features_v2.sql) — correções do v1:
- Sentinela DAYS_EMPLOYED = 365243 (~18% das linhas) vira anos_operacao NULL
  + flag. No v1 ela inflava days_employed_abs e invertia o sinal da atribuição.
- days_employed_abs saiu: no serviço era anos_operacao * 365.25 (colinear).
- occupation_type_encoded saiu: o hash de OCCUPATION_TYPE era usado como número
  contínuo, e os setores PME caíam em códigos nunca vistos no treino — o setor
  mudava a PD de forma arbitrária. Setor segue no laudo, não na PD.

LIMITES HONESTOS:
- A base de treino NÃO é de PME brasileira — é crédito pessoal.
- O projeto demonstra o MÉTODO, não um modelo pronto para concessão real.
- pd (probabilidade de inadimplência) vem SEMPRE do modelo, nunca do LLM.

REFERÊNCIA: PLANO §4, SPEC §3.2, BRIEF.md
"""

from __future__ import annotations

import pandas as pd

# Versão do feature set — mudar quando o mapeamento for revisado
FEATURE_SET_VERSION = "v2_sem_sentinela"

# Tabela BigQuery do feature set atual (treino, eval e drift leem daqui)
FEATURES_TABLE = "features_v2"

# Sentinela do Home Credit para "sem vínculo empregatício" em DAYS_EMPLOYED
DAYS_EMPLOYED_SENTINELA = 365243

# Features congeladas para o treino (específicas do Home Credit)
FEATURE_COLUMNS = [
    "amt_income_total",
    "amt_credit",
    "amt_annuity",
    "prazo_meses_estimado",
    "anos_operacao",
    "sem_emprego_registrado",
    "region_rating",
]

# Coluna alvo
TARGET_COLUMN = "target"

# Colunas de split
SPLIT_COLUMN = "split"
ID_COLUMN = "sk_id_curr"


def _hash_deterministico(value: str) -> int:
    """Hash determinístico para split local (MD5 — não bate com o split do SQL)."""
    import hashlib

    h = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def preparar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma o DataFrame bruto do Home Credit no feature set v2 (EDA local).

    Espelha 04_load_features_v2.sql, exceto o split: aqui é MD5 do ID, lá é
    FARM_FINGERPRINT — para métricas citáveis, usar a tabela do BigQuery.

    Args:
        df: DataFrame com colunas do application_train.csv

    Returns:
        DataFrame com as features transformadas + coluna target + split
    """
    out = pd.DataFrame()
    out[ID_COLUMN] = df[ID_COLUMN]

    out["amt_income_total"] = df["AMT_INCOME_TOTAL"]
    out["amt_credit"] = df["AMT_CREDIT"]
    out["amt_annuity"] = df["AMT_ANNUITY"]

    # Prazo estimado em meses (HC não tem prazo explícito)
    out["prazo_meses_estimado"] = (df["AMT_CREDIT"] / df["AMT_ANNUITY"]).clip(upper=120)

    # Anos de operação (proxy: DAYS_EMPLOYED) — sentinela vira NaN + flag
    sentinela = df["DAYS_EMPLOYED"] == DAYS_EMPLOYED_SENTINELA
    anos = (-df["DAYS_EMPLOYED"] / 365.25).clip(lower=0, upper=60)
    out["anos_operacao"] = anos.mask(sentinela)
    out["sem_emprego_registrado"] = sentinela.astype(int)

    # Região (proxy de UF)
    out["region_rating"] = df["REGION_RATING_CLIENT"]

    out[TARGET_COLUMN] = df["TARGET"]
    out[SPLIT_COLUMN] = out[ID_COLUMN].map(
        lambda x: "train" if _hash_deterministico(str(x)) % 100 < 80 else "holdout"
    )
    return out

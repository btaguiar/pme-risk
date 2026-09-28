"""Feature engineering para o modelo de risco pme-risk.

⚠️ AVISO FASE 3 — ACOPLEMENTO CRÍTICO ⚠️
O encoding de `occupation_type_encoded` DEVE usar FARM_FINGERPRINT % 100
(compatível com BigQuery). NÃO usar `pd.get_dummies()` — produz valores
completamente diferentes e o modelo foi treinado com FARM_FINGERPRINT.
Ver `_farm_fingerprint()` abaixo e `01_load_features.sql`.

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
| setor                        | OCCUPATION_TYPE            | mapeamento aproximado |
| uf                           | REGION_RATING_CLIENT       | proxy de risco regional, não geografia |

LIMITES HONESTOS:
- A base de treino NÃO é de PME brasileira — é crédito pessoal.
- O projeto demonstra o MÉTODO, não um modelo pronto para concessão real.
- pd (probabilidade de inadimplência) vem SEMPRE do modelo, nunca do LLM.

REFERÊNCIA: PLANO §4, SPEC §3.2, BRIEF.md
"""

from __future__ import annotations

import pandas as pd

# Versão do feature set — mudar quando o mapeamento for revisado
FEATURE_SET_VERSION = "v1_hipotese"

# Features congeladas para o treino (específicas do Home Credit)
FEATURE_COLUMNS = [
    "amt_income_total",
    "amt_credit",
    "amt_annuity",
    "prazo_meses_estimado",
    "anos_operacao",
    "occupation_type_encoded",
    "region_rating",
    "days_employed_abs",
]

# Coluna alvo
TARGET_COLUMN = "target"

# Colunas de split
SPLIT_COLUMN = "split"
ID_COLUMN = "sk_id_curr"


def _farm_fingerprint(value: str) -> int:
    """FARM_FINGERPRINT compatível com BigQuery (para encoding determinístico).

    Reproduce a lógica de 01_load_features.sql:
      MOD(ABS(FARM_FINGERPRINT(IFNULL(OCCUPATION_TYPE, 'UNKNOWN'))), 100)
    """
    import hashlib

    h = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


def preparar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma o DataFrame bruto do Home Credit no feature set congelado.

    IMPORTANTE: o encoding de occupation_type_encoded usa FARM_FINGERPRINT % 100
    para ser compatível com 01_load_features.sql (o modelo foi treinado com
    esse encoding). NÃO usar get_dummies — produz valores diferentes.

    Args:
        df: DataFrame com colunas do application_train.csv

    Returns:
        DataFrame com as features transformadas + coluna target + split
    """
    out = pd.DataFrame()

    # ID para split determinístico
    out[ID_COLUMN] = df[ID_COLUMN]

    # Features numéricas diretas
    out["amt_income_total"] = df["AMT_INCOME_TOTAL"]
    out["amt_credit"] = df["AMT_CREDIT"]
    out["amt_annuity"] = df["AMT_ANNUITY"]

    # Prazo estimado em meses (HC não tem prazo explícito)
    out["prazo_meses_estimado"] = (df["AMT_CREDIT"] / df["AMT_ANNUITY"]).clip(upper=120)

    # Anos de operação (proxy: DAYS_EMPLOYED convertido)
    out["anos_operacao"] = (-df["DAYS_EMPLOYED"] / 365.25).clip(lower=0, upper=60)

    # Dias de emprego (valor absoluto — HC usa negativo)
    out["days_employed_abs"] = df["DAYS_EMPLOYED"].abs()

    # Ocupação — FARM_FINGERPRINT % 100 (compatível com 01_load_features.sql)
    occupation = df["OCCUPATION_TYPE"].fillna("UNKNOWN")
    out["occupation_type_encoded"] = occupation.map(_farm_fingerprint).astype(int)

    # Região (proxy de UF)
    out["region_rating"] = df["REGION_RATING_CLIENT"]

    # Alvo
    out[TARGET_COLUMN] = df["TARGET"]

    # Split determinístico via hash do ID (80/20)
    out[SPLIT_COLUMN] = (out[ID_COLUMN].apply(hash) % 100 < 80).map(
        {True: "train", False: "holdout"}
    )

    return out

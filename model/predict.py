"""Predição de risco — PD + fatores a partir do modelo publicado.

Referência: SPEC §3.5
Regra: pd vem SEMPRE do modelo, nunca do LLM (PLANO §2, BRIEF.md)
"""

from __future__ import annotations

from dataclasses import dataclass

from google.cloud import bigquery

from model.registry import ModelRegistry

# Tipos esperados das features no BQML (para query parameters)
_FEATURE_TYPES: dict[str, str] = {
    "amt_income_total": "FLOAT64",
    "amt_credit": "FLOAT64",
    "amt_annuity": "FLOAT64",
    "prazo_meses_estimado": "FLOAT64",
    "anos_operacao": "FLOAT64",
    "days_employed_abs": "INT64",
    "occupation_type_encoded": "INT64",
    "region_rating": "INT64",
}

# Nomes físicos dos modelos BQML por algoritmo
_BQ_MODEL_NAMES: dict[str, str] = {
    "LOGISTIC_REG": "logreg_baseline",
    "BOOSTED_TREE_CLASSIFIER": "boosted_tree_v1",
}


@dataclass(frozen=True)
class ResultadoPredicao:
    """Resultado da predição — imutável."""

    pd: float
    faixa_risco: str
    fatores: list[tuple[str, float]]
    model_version: str


def classificar_faixa_risco(pd: float) -> str:
    """Classifica a PD em faixa de risco."""
    if pd < 0.05:
        return "baixo"
    elif pd < 0.15:
        return "medio"
    elif pd < 0.30:
        return "alto"
    else:
        return "muito_alto"


def _resolver_bq_model_name(algoritmo: str, model_version: str) -> str:
    """Resolve o nome físico do modelo BQML a partir do algoritmo.

    Levanta ValueError se o algoritmo não tiver nome mapeado.
    """
    name = _BQ_MODEL_NAMES.get(algoritmo)
    if name is None:
        raise ValueError(
            f"Algoritmo '{algoritmo}' sem nome BQML mapeado. "
            f"Adicione em _BQ_MODEL_NAMES. model_version={model_version}"
        )
    return name


def _montar_feature_params(features: dict[str, float]) -> dict[str, bigquery.ScalarQueryParameter]:
    """Monta query parameters tipados para as features."""
    params: dict[str, bigquery.ScalarQueryParameter] = {}
    for name, type_ in _FEATURE_TYPES.items():
        if name not in features:
            raise KeyError(f"Feature obrigatória ausente: {name}")
        value = features[name]
        if type_ == "INT64":
            params[name] = bigquery.ScalarQueryParameter(name, "INT64", int(value))
        else:
            params[name] = bigquery.ScalarQueryParameter(name, "FLOAT64", float(value))
    return params


def _montar_feature_select() -> str:
    """Monta o SELECT das features usando query parameters."""
    return ", ".join(f"@{name} AS {name}" for name in _FEATURE_TYPES)


def prever(
    features: dict[str, float],
    project_id: str,
    dataset: str,
) -> ResultadoPredicao:
    """Prediz PD + fatores para um vetor de features.

    Args:
        features: dict com as features do modelo (ver model/features.py)
        project_id: GCP project ID
        dataset: BigQuery dataset

    Returns:
        ResultadoPredicao com pd, faixa_risco, fatores e model_version
    """
    registry = ModelRegistry(project_id, dataset)
    model = registry.obter_producao()

    if model is None:
        raise RuntimeError("Nenhum modelo com status='production' no registry")

    model_version = model["model_version"]
    algoritmo = model["algoritmo"]
    bq_model_name = _resolver_bq_model_name(algoritmo, model_version)

    client = bigquery.Client(project=project_id)
    feature_params = _montar_feature_params(features)
    feature_select = _montar_feature_select()
    query_params = list(feature_params.values())

    # PD via UNNEST por label=1 — não OFFSET(0), que é ordenado por prob desc
    predict_sql = f"""
        SELECT
          (SELECT CAST(prob AS FLOAT64) FROM UNNEST(predicted_target_probs) WHERE label = 1) AS pd
        FROM ML.PREDICT(
          MODEL `{project_id}.{dataset}.{bq_model_name}`,
          (SELECT {feature_select})
        )
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    results = list(client.query(predict_sql, job_config=job_config).result())
    if not results:
        raise RuntimeError("Predição retornou vazio")

    pd = float(dict(results[0])["pd"])
    faixa = classificar_faixa_risco(pd)

    # Fatores via ML.EXPLAIN_PREDICT
    explain_sql = f"""
        SELECT top_feature_attributions
        FROM ML.EXPLAIN_PREDICT(
          MODEL `{project_id}.{dataset}.{bq_model_name}`,
          (SELECT {feature_select})
        )
    """
    explain_results = list(client.query(explain_sql, job_config=job_config).result())
    fatores: list[tuple[str, float]] = []
    if explain_results:
        attributions = dict(explain_results[0])["top_feature_attributions"]
        if attributions:
            for item in attributions:
                fatores.append((item["feature"], float(item["attribution"])))

    return ResultadoPredicao(
        pd=pd,
        faixa_risco=faixa,
        fatores=fatores,
        model_version=model_version,
    )


if __name__ == "__main__":
    import os

    example_features = {
        "amt_income_total": 200000.0,
        "amt_credit": 300000.0,
        "amt_annuity": 15000.0,
        "prazo_meses_estimado": 20.0,
        "anos_operacao": 5.0,
        "days_employed_abs": 1825.0,
        "occupation_type_encoded": 42.0,
        "region_rating": 2.0,
    }

    result = prever(
        features=example_features,
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
    )
    print(f"PD: {result.pd:.4f}")
    print(f"Faixa: {result.faixa_risco}")
    print(f"Modelo: {result.model_version}")
    for name, contrib in sorted(result.fatores, key=lambda x: abs(x[1]), reverse=True):
        print(f"  {name:30s} {contrib:+.4f}")

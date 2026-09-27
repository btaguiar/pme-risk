"""Avaliação do modelo de risco — KS, AUC, Brier, ECE.

Lê predições reais do BQML sobre o holdout e grava em eval/model/results/.
Referência: SPEC §3.4, PLANO §5
Regra: só citar métricas que estejam em eval/model/results/*.json (BRIEF.md)
"""

from __future__ import annotations

import json
from pathlib import Path

from google.cloud import bigquery
from scipy import stats

RESULTS_DIR = Path(__file__).parent / "results"

# Deve corresponder a FEATURE_SET_VERSION em model/features.py
FEATURE_SET_VERSION = "v1_hipotese"


def calcular_ks(y_true: list[int], y_score: list[float]) -> float:
    """KS statistic via scipy ks_2samp sobre score por classe."""
    scores_pos = [s for t, s in zip(y_true, y_score, strict=True) if t == 1]
    scores_neg = [s for t, s in zip(y_true, y_score, strict=True) if t == 0]
    if not scores_pos or not scores_neg:
        return 0.0
    ks_stat, _ = stats.ks_2samp(scores_pos, scores_neg)
    return float(ks_stat)


def calcular_auc(y_true: list[int], y_score: list[float]) -> float:
    """AUC via Mann-Whitney U (sem sklearn)."""
    scores_pos = [s for t, s in zip(y_true, y_score, strict=True) if t == 1]
    scores_neg = [s for t, s in zip(y_true, y_score, strict=True) if t == 0]
    if not scores_pos or not scores_neg:
        return 0.5
    u_stat, _ = stats.mannwhitneyu(scores_pos, scores_neg, alternative="greater")
    n_pos = len(scores_pos)
    n_neg = len(scores_neg)
    return float(u_stat / (n_pos * n_neg))


def calcular_brier(y_true: list[int], y_score: list[float]) -> float:
    """Brier score — média do erro quadrático."""
    n = len(y_true)
    if n == 0:
        return 0.0
    return sum((s - t) ** 2 for t, s in zip(y_true, y_score, strict=True)) / n


def calcular_ece(y_true: list[int], y_score: list[float], n_bins: int = 10) -> float:
    """Expected Calibration Error com bins fixos."""
    n = len(y_true)
    if n == 0:
        return 0.0
    bins: list[list[tuple[int, float]]] = [[] for _ in range(n_bins)]
    for t, s in zip(y_true, y_score, strict=True):
        bin_idx = min(int(s * n_bins), n_bins - 1)
        bins[bin_idx].append((t, s))
    ece = 0.0
    for bin_data in bins:
        if not bin_data:
            continue
        bin_size = len(bin_data)
        avg_pred = sum(s for _, s in bin_data) / bin_size
        avg_true = sum(t for t, _ in bin_data) / bin_size
        ece += (bin_size / n) * abs(avg_pred - avg_true)
    return ece


def obter_predicoes(
    project_id: str,
    dataset: str,
    bq_model_name: str,
) -> tuple[list[int], list[float]]:
    """Executa ML.PREDICT sobre o holdout e retorna (y_true, y_score)."""
    client = bigquery.Client(project=project_id)

    query = f"""
        SELECT
          target,
          (SELECT CAST(prob AS FLOAT64) FROM UNNEST(predicted_target_probs) WHERE label = 1) AS pd
        FROM ML.PREDICT(
          MODEL `{project_id}.{dataset}.{bq_model_name}`,
          (
            SELECT amt_income_total, amt_credit, amt_annuity,
                   prazo_meses_estimado, anos_operacao, days_employed_abs,
                   occupation_type_encoded, region_rating, target
            FROM `{project_id}.{dataset}.features`
            WHERE split = 'holdout'
          )
        )
    """
    rows = list(client.query(query).result())
    y_true = [int(r["target"]) for r in rows]
    y_score = [float(r["pd"]) for r in rows]
    return y_true, y_score


def avaliar_modelo(
    project_id: str,
    dataset: str,
    bq_model_name: str,
    model_version: str,
    algoritmo: str,
) -> dict:
    """Calcula métricas sobre holdout real e grava em eval/model/results/."""
    y_true, y_score = obter_predicoes(project_id, dataset, bq_model_name)

    metrics = {
        "model_version": model_version,
        "algoritmo": algoritmo,
        "feature_set_version": FEATURE_SET_VERSION,
        "n_amostras": len(y_true),
        "ks": round(calcular_ks(y_true, y_score), 4),
        "auc": round(calcular_auc(y_true, y_score), 4),
        "brier": round(calcular_brier(y_true, y_score), 4),
        "ece": round(calcular_ece(y_true, y_score), 4),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{model_version}.json"
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


if __name__ == "__main__":
    import os

    result = avaliar_modelo(
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
        bq_model_name="logreg_baseline",
        model_version="logreg_v1",
        algoritmo="LOGISTIC_REG",
    )
    print(json.dumps(result, indent=2))

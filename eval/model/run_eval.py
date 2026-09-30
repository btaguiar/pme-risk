"""Avaliação do modelo de risco — KS, AUC, Brier, ECE.

Lê predições reais do BQML sobre o holdout e grava em eval/model/results/.
Referência: SPEC §3.4, PLANO §5
Regra: só citar métricas que estejam em eval/model/results/*.json (BRIEF.md)

v3 (SBA 7(a)): holdout TEMPORAL FY2014–2015 (D5), métricas também por safra
(2014 × 2015) e sanidade de setor — Spearman entre a perda por seção CNAE na
SBA e a inadimplência Micro+Pequeno por seção no SCR (checagem, sem limite
de aceite; precisa de `scr_pj_raw`, Task 5).
"""

from __future__ import annotations

import json
from pathlib import Path

from google.cloud import bigquery
from scipy import stats

from model.features import FEATURE_COLUMNS, FEATURE_SET_VERSION, FEATURES_TABLE

RESULTS_DIR = Path(__file__).parent / "results"


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


def calcular_brier_ingenuo(y_true: list[int]) -> float:
    """Brier do preditor constante na prevalência — piso que o modelo precisa bater."""
    n = len(y_true)
    if n == 0:
        return 0.0
    p = sum(y_true) / n
    return p * (1 - p)


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


def _metricas(y_true: list[int], y_score: list[float]) -> dict:
    """Métricas padrão arredondadas."""
    return {
        "n_amostras": len(y_true),
        "prevalencia": round(sum(y_true) / len(y_true), 4) if y_true else None,
        "ks": round(calcular_ks(y_true, y_score), 4),
        "auc": round(calcular_auc(y_true, y_score), 4),
        "brier": round(calcular_brier(y_true, y_score), 4),
        "brier_ingenuo": round(calcular_brier_ingenuo(y_true), 4),
        "ece": round(calcular_ece(y_true, y_score), 4),
    }


def obter_predicoes(
    project_id: str,
    dataset: str,
    bq_model_name: str,
    *,
    features_table: str = FEATURES_TABLE,
    feature_columns: list[str] | None = None,
    com_safra: bool = True,
) -> list[dict]:
    """Executa ML.PREDICT sobre o holdout e retorna linhas com target, pd e safra.

    `com_safra=False` para tabelas sem approval_fy (features/features_v2).
    """
    colunas = feature_columns or FEATURE_COLUMNS
    col_safra = "approval_fy AS safra," if com_safra else "NULL AS safra,"
    client = bigquery.Client(project=project_id)

    query = f"""
        SELECT
          target,
          {col_safra}
          (SELECT CAST(prob AS FLOAT64) FROM UNNEST(predicted_target_probs) WHERE label = 1) AS pd
        FROM ML.PREDICT(
          MODEL `{project_id}.{dataset}.{bq_model_name}`,
          (
            SELECT {", ".join(colunas)}, target{" , approval_fy" if com_safra else ""}
            FROM `{project_id}.{dataset}.{features_table}`
            WHERE split = 'holdout'
          )
        )
    """
    rows = list(client.query(query).result())
    return [
        {
            "target": int(r["target"]),
            "safra": int(r["safra"]) if r["safra"] is not None else None,
            "pd": float(r["pd"]),
        }
        for r in rows
    ]


def sanidade_setor(project_id: str, dataset: str) -> dict | None:
    """Spearman entre a perda por seção CNAE na SBA e a inadimplência Micro+Pequeno
    por seção no SCR (se `scr_pj_raw` ainda não existir, devolve None).

    Checagem de sanidade do mapeamento NAICS→CNAE (plano D7), não meta.
    """
    client = bigquery.Client(project=project_id)
    try:
        sba = {
            r["secao_cnae"]: float(r["tx_perda"])
            for r in client.query(
                f"SELECT secao_cnae, AVG(target) AS tx_perda "
                f"FROM `{project_id}.{dataset}.features_v3` GROUP BY secao_cnae"
            ).result()
        }
        scr = {
            r["secao"]: float(r["tx_inad"])
            for r in client.query(
                f"""SELECT secao, SUM(carteira_inadimplencia) / SUM(carteira_ativa) AS tx_inad
                    FROM `{project_id}.{dataset}.scr_pj_raw`
                    WHERE porte IN ('Micro', 'Pequeno')
                      AND cliente = 'PJ'
                    GROUP BY secao"""
            ).result()
        }
    except Exception:
        return None

    comuns = sorted(set(sba) & set(scr))
    if len(comuns) < 3:
        return None
    rho, _ = stats.spearmanr([sba[s] for s in comuns], [scr[s] for s in comuns])
    return {"rho": round(float(rho), 4), "n_secoes": len(comuns)}


def avaliar_modelo(
    project_id: str,
    dataset: str,
    bq_model_name: str,
    model_version: str,
    algoritmo: str,
    *,
    feature_set_version: str = FEATURE_SET_VERSION,
    features_table: str = FEATURES_TABLE,
    feature_columns: list[str] | None = None,
    por_safra: bool = False,
    nota: str | None = None,
) -> dict:
    """Calcula métricas sobre holdout real e grava em eval/model/results/."""
    linhas = obter_predicoes(
        project_id,
        dataset,
        bq_model_name,
        features_table=features_table,
        feature_columns=feature_columns,
    )
    y_true = [row["target"] for row in linhas]
    y_score = [row["pd"] for row in linhas]

    metrics = {
        "model_version": model_version,
        "algoritmo": algoritmo,
        "feature_set_version": feature_set_version,
        **_metricas(y_true, y_score),
    }

    if por_safra:
        safras = sorted({row["safra"] for row in linhas})
        metrics["por_safra"] = {
            str(safra): _metricas(
                [row["target"] for row in linhas if row["safra"] == safra],
                [row["pd"] for row in linhas if row["safra"] == safra],
            )
            for safra in safras
        }

    sanidade = sanidade_setor(project_id, dataset)
    if sanidade is not None:
        metrics["sanidade_setor_sba_x_scr"] = sanidade

    if nota:
        metrics["nota"] = nota

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{model_version}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    return metrics


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Avalia um modelo no holdout e grava o JSON")
    parser.add_argument(
        "--model", default="logreg_v3", help="versão (nome do JSON e do modelo BQML)"
    )
    parser.add_argument("--table", default=FEATURES_TABLE, help="tabela de features do holdout")
    parser.add_argument(
        "--colunas",
        default=",".join(FEATURE_COLUMNS),
        help="features do modelo separadas por vírgula",
    )
    parser.add_argument("--algoritmo", default="LOGISTIC_REG")
    parser.add_argument("--feature-set-version", default=FEATURE_SET_VERSION)
    parser.add_argument("--por-safra", action="store_true", help="métricas por safra (v3)")
    parser.add_argument("--nota", default=None)
    args = parser.parse_args()

    result = avaliar_modelo(
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
        bq_model_name=args.model,
        model_version=args.model,
        algoritmo=args.algoritmo,
        feature_set_version=args.feature_set_version,
        features_table=args.table,
        feature_columns=args.colunas.split(","),
        por_safra=args.por_safra,
        nota=args.nota,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

"""Job de drift — PSI da entrada (laudos) vs. treino (PLANO §5, SPEC §5.3).

Compara as features NUMÉRICAS com análogo direto entre pedido e treino.
Categóricas (porte, UF, setor) ficam de fora: sem análogo honesto no Home
Credit (SPEC §3.2) — limite documentado, não omissão.

PSI > 0.25 → log estruturado WARNING (log-based alert do free tier).
Roda como Cloud Run Job (deploy_drift.sh), não no processo da API.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import os
import sys
from collections.abc import Sequence

from google.cloud import bigquery

LIMIAR_PSI = 0.25
N_BINS = 10
_EPS = 1e-6

MAPEAMENTO_FEATURE_CAMPO = {
    "amt_credit": "valor_solicitado",
    "amt_income_total": "faturamento_anual_declarado",
    "anos_operacao": "anos_operacao",
    "prazo_meses_estimado": "prazo_meses",
}


def _quantile(valores: Sequence[float], q: float) -> float:
    ordenado = sorted(valores)
    idx = min(int(q * (len(ordenado) - 1)), len(ordenado) - 1)
    return ordenado[idx]


def _proporcoes(valores: Sequence[float], limites: list[float]) -> list[float]:
    contagens = [0] * (len(limites) + 1)
    for v in valores:
        contagens[bisect.bisect_right(limites, v)] += 1
    return [c / len(valores) for c in contagens]


def psi(esperado: Sequence[float], atual: Sequence[float], n_bins: int = N_BINS) -> float:
    """Population Stability Index com bins por quantis da distribuição de treino."""
    if len(esperado) == 0 or len(atual) == 0:
        return 0.0
    limites = sorted({_quantile(esperado, i / n_bins) for i in range(1, n_bins)})
    p_esp = _proporcoes(esperado, limites)
    p_atu = _proporcoes(atual, limites)
    total = 0.0
    for e, a in zip(p_esp, p_atu, strict=True):
        e = max(e, _EPS)
        a = max(a, _EPS)
        total += (a - e) * math.log(a / e)
    return total


def calcular_drift(
    treino: dict[str, list[float]], atual: dict[str, list[float]]
) -> dict[str, float]:
    """PSI por feature; feature sem dados atuais → 0.0 (sem drift mensurável)."""
    return {feat: psi(vals, atual.get(feat, [])) for feat, vals in treino.items()}


def _carregar_treino(client: bigquery.Client, dataset: str) -> dict[str, list[float]]:
    colunas = ", ".join(MAPEAMENTO_FEATURE_CAMPO)
    query = f"""
        SELECT {colunas}
        FROM `{client.project}.{dataset}.features`
        WHERE split = 'train'
    """
    rows = list(client.query(query).result())
    return {
        feat: [float(row[feat]) for row in rows if row[feat] is not None]
        for feat in MAPEAMENTO_FEATURE_CAMPO
    }


def _carregar_laudos(
    client: bigquery.Client, dataset: str, n_laudos: int
) -> dict[str, list[float]]:
    query = f"""
        SELECT enriquecidos_json
        FROM `{client.project}.{dataset}.laudos`
        ORDER BY criado_em DESC
        LIMIT {int(n_laudos)}
    """
    atual: dict[str, list[float]] = {feat: [] for feat in MAPEAMENTO_FEATURE_CAMPO}
    for row in client.query(query).result():
        pedido = json.loads(row["enriquecidos_json"])["extraidos"]["pedido"]
        for feat, campo in MAPEAMENTO_FEATURE_CAMPO.items():
            valor = pedido.get(campo)
            if valor is not None:
                atual[feat].append(float(valor))
    return atual


def rodar(project_id: str, dataset: str, n_laudos: int = 100) -> dict:
    """Calcula drift, loga WARNING acima do limiar e devolve o resumo."""
    client = bigquery.Client(project=project_id)
    treino = _carregar_treino(client, dataset)
    atual = _carregar_laudos(client, dataset, n_laudos)
    psis = calcular_drift(treino, atual)
    alertas = {feat: valor for feat, valor in psis.items() if valor > LIMIAR_PSI}
    for feat, valor in alertas.items():
        logging.warning("drift detectado: %s PSI=%.4f > %.2f", feat, valor, LIMIAR_PSI)
    return {
        "psis": psis,
        "limiar": LIMIAR_PSI,
        "n_laudos": n_laudos,
        "alertas": alertas,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    resumo = rodar(
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
        n_laudos=int(os.environ.get("DRIFT_N_LAUDOS", "100")),
    )
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())

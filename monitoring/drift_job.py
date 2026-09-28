"""Job de drift — PSI da entrada (laudos) vs. treino (PLANO §5, SPEC §5.3).

Compara as features NUMÉRICAS com análogo direto entre pedido e treino.
Categóricas (porte, UF, setor) ficam de fora: sem análogo honesto no Home
Credit (SPEC §3.2) — limite documentado, não omissão.

PSI > 0.25 → log estruturado WARNING (log-based alert do free tier).
Roda como Cloud Run Job (deploy_drift.sh), não no processo da API.
"""

from __future__ import annotations

import bisect
import logging
import math
from collections.abc import Sequence

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

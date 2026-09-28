"""Adapter de pipeline — único ponto de contato entre a Fase 3 (API) e a Fase 2 (agentes).

Referência: docs/superpowers/specs/2026-09-27-fase3-produto-design.md
Se a Fase 2 for reestruturada, este é o único arquivo a ajustar.

O mapeamento pedido → features segue a HIPÓTESE documentada em
model/features.py (SPEC §3.2) — proxy, não paridade com Home Credit.
"""

from __future__ import annotations

from agents.schemas import PedidoCredito

# Proxy neutro de UF → region_rating. 2 é a moda de REGION_RATING_CLIENT.
# Sem inventar risco por UF (SPEC §3.2: "não geografia real").
_REGION_RATING_DEFAULT = 2

# Prazo default quando o pedido não menciona (mesma base do clip em 01_load_features.sql)
_PRAZO_DEFAULT_MESES = 36


def _fnv1a_64_signed(texto: str) -> int:
    """FNV-1a 64-bit com interpretação assinada — determinístico para `setor`.

    Não exige paridade exata com FARM_FINGERPRINT do BigQuery: o mapeamento
    setor → occupation_type já é aproximação documentada (SPEC §3.2).
    """
    h = 0xCBF29CE484222325
    for byte in texto.encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h - (1 << 64) if h >= (1 << 63) else h


def pedido_para_features(pedido: PedidoCredito) -> dict[str, float]:
    """Mapeia PedidoCredito (PME) → vetor de features do modelo (Home Credit)."""
    prazo = min(pedido.prazo_meses or _PRAZO_DEFAULT_MESES, 120)
    anos = min(max(pedido.anos_operacao, 0), 60)
    return {
        "amt_income_total": float(pedido.faturamento_anual_declarado),
        "amt_credit": float(pedido.valor_solicitado),
        "amt_annuity": float(pedido.valor_solicitado) / prazo,
        "prazo_meses_estimado": float(prazo),
        "anos_operacao": float(anos),
        "days_employed_abs": round(anos * 365.25, 2),
        "occupation_type_encoded": float(abs(_fnv1a_64_signed(pedido.setor)) % 100),
        "region_rating": float(_REGION_RATING_DEFAULT),
    }

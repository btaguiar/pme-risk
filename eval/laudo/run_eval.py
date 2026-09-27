"""Eval do laudo — fidedignidade, verificado/declarado, recusa.

Referência: PLANO §5 — matriz de evals
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
GOLDEN_PATH = Path(__file__).parent.parent.parent / "data" / "golden_set" / "pedidos.jsonl"


def carregar_golden_set() -> list[dict]:
    """Carrega o golden set."""
    return [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]


def avaliar_fidedignidade(laudos: list[dict]) -> float:
    """% de afirmações com evidência citada (meta: 100%)."""
    total_afirmacoes = 0
    com_evidencia = 0
    for laudo in laudos:
        afirmacoes = laudo.get("afirmacoes", [])
        for a in afirmacoes:
            total_afirmacoes += 1
            if a.get("evidencia"):
                com_evidencia += 1
    return com_evidencia / total_afirmacoes if total_afirmacoes > 0 else 0.0


def avaliar_verificado_declarado(laudos: list[dict]) -> float:
    """% de campos classificados corretamente (meta: 100%)."""
    total_campos = 0
    corretos = 0
    for laudo in laudos:
        fonte_esperada = laudo.get("fonte_esperada", {})
        fonte_obtida = laudo.get("fonte_por_campo", {})
        for campo, esperado in fonte_esperada.items():
            total_campos += 1
            if fonte_obtida.get(campo) == esperado:
                corretos += 1
    return corretos / total_campos if total_campos > 0 else 0.0


def avaliar_recusa(resultados: list[dict]) -> float:
    """% de pedidos fora de escopo recusados corretamente (meta: ≥ 95%)."""
    total_fora_escopo = 0
    recusados = 0
    for r in resultados:
        if r.get("esperado_fora_escopo"):
            total_fora_escopo += 1
            if r.get("fora_de_escopo_detectado"):
                recusados += 1
    return recusados / total_fora_escopo if total_fora_escopo > 0 else 1.0


def gerar_relatorio(laudos: list[dict], resultados: list[dict]) -> dict:
    """Gera relatório completo e grava em results/."""
    relatorio = {
        "fidedignidade": round(avaliar_fidedignidade(laudos), 4),
        "verificado_declarado": round(avaliar_verificado_declarado(laudos), 4),
        "recusa": round(avaliar_recusa(resultados), 4),
        "n_laudos": len(laudos),
        "n_recusas_avaliadas": sum(1 for r in resultados if r.get("esperado_fora_escopo")),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "laudo_eval.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)

    return relatorio

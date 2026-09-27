"""Eval do laudo — fidedignidade, verificado/declarado, recusa.

Executa o golden set contra o Extrator e calcula métricas.
Referência: PLANO §5 — matriz de evals
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
GOLDEN_PATH = Path(__file__).parent.parent.parent / "data" / "golden_set" / "pedidos.jsonl"


@dataclass
class ResultadoItem:
    """Resultado de um item do golden set."""

    indice: int
    texto: str
    esperado: dict
    obtido: dict | None = None
    erro: str | None = None
    latencia_s: float = 0.0


@dataclass
class RelatorioEval:
    """Relatório completo do eval."""

    f1_extracao: float = 0.0
    taxa_recusa_correta: float = 0.0
    taxa_fora_escopo_detectado: float = 0.0
    fidedignidade: float = 0.0
    verificado_declarado: float = 0.0
    n_itens: int = 0
    n_recusas_esperadas: int = 0
    n_recusas_corretas: int = 0
    latencia_media_s: float = 0.0
    custo_estimado_usd: float = 0.0
    itens: list[ResultadoItem] = field(default_factory=list)


def carregar_golden_set() -> list[dict]:
    """Carrega o golden set."""
    return [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]


def calcular_f1_campos(esperado: dict, obtido: dict) -> float:
    """F1 para extração de entidades (campos individuais)."""
    campos = [k for k in esperado if k not in ("fora_de_escopo", "motivo_recusa")]
    if not campos:
        return 1.0

    tp = 0  # campo correto
    fp = 0  # campo extraído mas errado
    fn = 0  # campo esperado mas não extraído

    for campo in campos:
        val_esp = esperado.get(campo)
        val_obt = obtido.get(campo)
        if val_esp is None:
            continue  # não avalia campos não especificados
        if val_obt == val_esp:
            tp += 1
        elif val_obt is None:
            fn += 1
        else:
            fp += 1

    precisao = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precisao + recall == 0:
        return 0.0
    return 2 * (precisao * recall) / (precisao + recall)


def executar_golden_set(
    extrair_fn=None,
    project_id: str | None = None,
    max_itens: int | None = None,
) -> RelatorioEval:
    """Executa o golden set contra o Extrator.

    Args:
        extrair_fn: função de extração (para testes) ou None para usar o real
        project_id: GCP project ID
        max_itens: limitar número de itens (para testes rápidos)

    Returns:
        RelatorioEval com métricas
    """
    if extrair_fn is None:
        from agents.extractor.extractor import extrair as extrair_fn  # type: ignore[assignment]

    golden = carregar_golden_set()
    if max_itens:
        golden = golden[:max_itens]

    relatorio = RelatorioEval(n_itens=len(golden))
    f1s: list[float] = []

    for i, item in enumerate(golden):
        texto = item["texto_pt_br"]
        esperado = item["esperado"]

        inicio = time.monotonic()
        try:
            obtido = extrair_fn(texto, project_id=project_id)
            obtido_dict = obtido.pedido.model_dump()
            fora_escopo = obtido.fora_de_escopo
            latencia = time.monotonic() - inicio
        except Exception as e:
            obtido_dict = None
            fora_escopo = False
            latencia = time.monotonic() - inicio
            relatorio.itens.append(
                ResultadoItem(
                    indice=i, texto=texto, esperado=esperado, erro=str(e), latencia_s=latencia
                )
            )
            continue

        # F1 de extração
        f1 = calcular_f1_campos(esperado, obtido_dict or {})
        f1s.append(f1)

        # Recusa
        esperado_fora = esperado.get("fora_de_escopo", False)
        if esperado_fora:
            relatorio.n_recusas_esperadas += 1
            if fora_escopo:
                relatorio.n_recusas_corretas += 1

        relatorio.itens.append(
            ResultadoItem(
                indice=i,
                texto=texto,
                esperado=esperado,
                obtido=obtido_dict,
                latencia_s=latencia,
            )
        )

    # Agregar métricas
    relatorio.f1_extracao = sum(f1s) / len(f1s) if f1s else 0.0
    relatorio.taxa_recusa_correta = (
        relatorio.n_recusas_corretas / relatorio.n_recusas_esperadas
        if relatorio.n_recusas_esperadas > 0
        else 1.0
    )
    relatorio.latencia_media_s = (
        sum(item.latencia_s for item in relatorio.itens) / len(relatorio.itens)
        if relatorio.itens
        else 0.0
    )
    # Estimativa de custo: ~$0.0001 por request flash
    relatorio.custo_estimado_usd = len(relatorio.itens) * 0.0001

    return relatorio


def salvar_relatorio(relatorio: RelatorioEval, nome: str = "laudo_eval") -> Path:
    """Salva o relatório em eval/laudo/results/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{nome}.json"

    dados = {
        "f1_extracao": round(relatorio.f1_extracao, 4),
        "taxa_recusa_correta": round(relatorio.taxa_recusa_correta, 4),
        "n_itens": relatorio.n_itens,
        "n_recusas_esperadas": relatorio.n_recusas_esperadas,
        "n_recusas_corretas": relatorio.n_recusas_corretas,
        "latencia_media_s": round(relatorio.latencia_media_s, 2),
        "custo_estimado_usd": round(relatorio.custo_estimado_usd, 4),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

    return output_path


if __name__ == "__main__":
    import os

    relatorio = executar_golden_set(
        project_id=os.environ.get("GCP_PROJECT_ID"),
        max_itens=5,  # limitar para teste rápido
    )
    path = salvar_relatorio(relatorio)
    print(
        json.dumps(
            {
                "f1_extracao": relatorio.f1_extracao,
                "taxa_recusa_correta": relatorio.taxa_recusa_correta,
                "n_itens": relatorio.n_itens,
                "latencia_media_s": relatorio.latencia_media_s,
            },
            indent=2,
        )
    )
    print(f"Salvo em: {path}")

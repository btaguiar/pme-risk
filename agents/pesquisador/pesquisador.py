"""Pesquisador — enriquecimento com dados públicos do CNPJ.

Referência: SPEC §4.2
Fonte: BrasilAPI (agents/pesquisador/cnpj.py) — o quimera-core previsto no
PLANO §3 não está publicável.

Um campo só vira "verificado" quando o dado público **confere** com o
declarado. Se diverge, segue "declarado" e a divergência vai para
`cnpj_dados["divergencias"]` — o laudo não pode chamar de verificado um valor
que a fonte pública contradiz.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from agents.pesquisador.cnpj import consultar_cnpj
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito

# Campos que sempre são declarados pelo solicitante (não verificáveis em base pública)
CAMPOS_DECLARADOS = {
    "faturamento_anual_declarado",
    "finalidade",
    "finalidade_detalhe",
    "valor_solicitado",
    "prazo_meses",
}

# Campos verificáveis via CNPJ (quando disponível)
CAMPOS_VERIFICAVEIS = {
    "setor",
    "anos_operacao",
    "porte",
    "uf",
}

# "5 anos" declarado × 5,7 anos desde a abertura confere; 2 × 7 não.
TOLERANCIA_ANOS = 1.0


def _confere(campo: str, declarado: object, publico: object) -> bool:
    if declarado is None or publico is None:
        return False
    if campo == "anos_operacao":
        return abs(float(declarado) - float(publico)) < TOLERANCIA_ANOS  # type: ignore[arg-type]
    return declarado == publico


def _comparar(pedido: PedidoCredito, cnpj_dados: dict) -> tuple[set[str], list[dict]]:
    """Campos que conferem com a fonte pública e divergências encontradas."""
    conferem: set[str] = set()
    divergencias: list[dict] = []
    for campo in sorted(CAMPOS_VERIFICAVEIS):
        declarado, publico = getattr(pedido, campo), cnpj_dados.get(campo)
        if _confere(campo, declarado, publico):
            conferem.add(campo)
        elif publico is not None:
            divergencias.append({"campo": campo, "declarado": declarado, "publico": publico})
    return conferem, divergencias


def enriquecer(
    extraidos: DadosExtraidos,
    consultar: Callable[[str], dict | None] = consultar_cnpj,
) -> DadosEnriquecidos:
    """Enriquece dados extraídos com fonte por campo.

    Args:
        extraidos: saída do Extrator
        consultar: consulta de CNPJ (injetável nos testes)

    Returns:
        DadosEnriquecidos com fonte_por_campo preenchido
    """
    # Se pedido é None (fora_de_escopo), retorna vazio
    if extraidos.pedido is None:
        return DadosEnriquecidos(extraidos=extraidos)

    fonte_por_campo: dict[str, Literal["verificado", "declarado"]] = {}
    cnpj_dados = None
    conferem: set[str] = set()

    if extraidos.pedido.cnpj:
        cnpj_dados = consultar(extraidos.pedido.cnpj)
    if cnpj_dados:
        conferem, divergencias = _comparar(extraidos.pedido, cnpj_dados)
        cnpj_dados = {**cnpj_dados, "divergencias": divergencias}

    for campo in extraidos.pedido.model_dump():
        if campo == "cnpj":
            continue
        fonte_por_campo[campo] = "verificado" if campo in conferem else "declarado"

    return DadosEnriquecidos(
        extraidos=extraidos,
        cnpj_dados=cnpj_dados,
        fonte_por_campo=fonte_por_campo,
    )

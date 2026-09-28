"""Pesquisador — enriquecimento de dados públicos (CNPJ).

Referência: SPEC §4.2
NOTA: Usa stub local enquanto quimera-core não está publicável (PLANO §3).
"""

from __future__ import annotations

from typing import Literal

from agents.schemas import DadosEnriquecidos, DadosExtraidos

# Campos que sempre são declarados pelo solicitante (não verificáveis em base pública)
CAMPOS_DECLARADOS = {
    "faturamento_anual_declarado",
    "finalidade",
    "valor_solicitado",
    "prazo_meses",
}

# Campos verificáveis via CNPJ (quando disponível)
CAMPOS_VERIFICAVEIS = {
    "setor",
    "anos_operacao",
    "porte",
}


def _enriquecer_cnpj(cnpj: str) -> dict | None:
    """Stub de enriquecimento CNPJ — retorna dados fictícios.

    TODO: Substituir por quimera-core quando publicável (PLANO §3).
    """
    # Stub: retorna None para indicar "não verificado"
    return None


def enriquecer(extraidos: DadosExtraidos) -> DadosEnriquecidos:
    """Enriquece dados extraídos com fonte por campo.

    Args:
        extraidos: saída do Extrator

    Returns:
        DadosEnriquecidos com fonte_por_campo preenchido
    """
    # Se pedido é None (fora_de_escopo), retorna vazio
    if extraidos.pedido is None:
        return DadosEnriquecidos(extraidos=extraidos)

    # Determina fonte por campo
    fonte_por_campo: dict[str, Literal["verificado", "declarado"]] = {}
    cnpj_dados = None

    # Enriquecimento CNPJ (stub) — só marca "verificado" se retornar dados
    if extraidos.pedido.cnpj:
        cnpj_dados = _enriquecer_cnpj(extraidos.pedido.cnpj)

    for campo in extraidos.pedido.model_dump():
        if campo == "cnpj":
            continue
        if campo in CAMPOS_DECLARADOS:
            fonte_por_campo[campo] = "declarado"
        elif cnpj_dados and campo in CAMPOS_VERIFICAVEIS:
            fonte_por_campo[campo] = "verificado"
        else:
            fonte_por_campo[campo] = "declarado"

    return DadosEnriquecidos(
        extraidos=extraidos,
        cnpj_dados=cnpj_dados,
        fonte_por_campo=fonte_por_campo,
    )

"""Contratos Pydantic entre agentes do pme-risk.

ResultadoModelo é somente leitura para os agentes de texto — nenhum deles
tem uma rota de código que reescreva pd ou faixa_risco (PLANO §2:
"o LLM não tem permissão para alterar a PD").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PedidoCredito(BaseModel):
    """Pedido de crédito PME — schema da SPEC §3.1."""

    setor: str = Field(description="CNAE ou descrição livre — o Extrator normaliza")
    porte: Literal["MEI", "ME", "EPP"]
    uf: str = Field(pattern=r"^[A-Z]{2}$", description="UF com 2 letras maiúsculas")
    anos_operacao: float = Field(ge=0, description="Anos de operação")
    faturamento_anual_declarado: float = Field(ge=0, description="BRL — sempre declarado")
    valor_solicitado: float = Field(ge=0, description="Valor do crédito em BRL")
    prazo_meses: int | None = Field(default=None, ge=1, description="Prazo em meses (opcional)")
    finalidade: str = Field(description="Finalidade do crédito (texto livre)")
    cnpj: str | None = Field(default=None, pattern=r"^\d{14}$", description="CNPJ")


class DadosExtraidos(BaseModel):
    """Saída do Extrator."""

    pedido: PedidoCredito
    fora_de_escopo: bool = False
    motivo_recusa: str | None = None

    @model_validator(mode="after")
    def _validar_recusa(self) -> DadosExtraidos:
        if self.fora_de_escopo and not self.motivo_recusa:
            raise ValueError("motivo_recusa obrigatório quando fora_de_escopo=True")
        return self


class DadosEnriquecidos(BaseModel):
    """Saída do Pesquisador (enriquecimento CNPJ + fonte por campo)."""

    extraidos: DadosExtraidos
    cnpj_dados: dict | None = None
    fonte_por_campo: dict[str, Literal["verificado", "declarado"]] = Field(default_factory=dict)


class ResultadoModelo(BaseModel):
    """Resultado do modelo de risco — SOMENTE LEITURA para agentes de texto.

    Modelo frozen: pd e faixa_risco não podem ser alterados após criação.
    """

    model_config = {"frozen": True}

    pd: float = Field(ge=0, le=1, description="Probabilidade de inadimplência")
    faixa_risco: str = Field(description="Faixa de risco calculada pelo modelo")
    fatores: list[tuple[str, float]] = Field(
        description="Contribuição por variável: (nome_feature, contribuição)"
    )
    model_version: str = Field(description="Versão do modelo no model_registry")


class Laudo(BaseModel):
    """Laudo de risco completo."""

    enriquecidos: DadosEnriquecidos
    resultado_modelo: ResultadoModelo
    texto: str = Field(description="Redigido pelo Redator")
    evidencias: list[str] = Field(
        default_factory=list, description="Normas/fontes citadas no texto"
    )
    status: Literal["pendente", "aprovado", "corrigido", "rejeitado"] = "pendente"

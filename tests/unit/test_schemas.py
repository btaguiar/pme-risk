"""Testes unitários — contratos entre agentes.

Referência: SPEC §4.1 — garantir por construção que ResultadoModelo é imutável.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.schemas import (
    DadosEnriquecidos,
    DadosExtraidos,
    Laudo,
    PedidoCredito,
    ResultadoModelo,
)


class TestResultadoModelo:
    def test_frozen_nao_permite_alterar_pd(self):
        r = ResultadoModelo(
            pd=0.15,
            faixa_risco="medio",
            fatores=[("feat1", 0.1)],
            model_version="v1",
        )
        with pytest.raises(ValidationError):
            r.pd = 0.99  # type: ignore[misc]

    def test_frozen_nao_permite_alterar_faixa(self):
        r = ResultadoModelo(
            pd=0.15,
            faixa_risco="medio",
            fatores=[("feat1", 0.1)],
            model_version="v1",
        )
        with pytest.raises(ValidationError):
            r.faixa_risco = "baixo"  # type: ignore[misc]

    def test_pd_validacao(self):
        with pytest.raises(ValidationError):
            ResultadoModelo(
                pd=1.5,
                faixa_risco="medio",
                fatores=[],
                model_version="v1",
            )


class TestDadosExtraidos:
    def test_recusa_sem_motivo_falha(self):
        with pytest.raises(ValidationError):
            DadosExtraidos(
                pedido=PedidoCredito(
                    setor="saude",
                    porte="ME",
                    uf="SP",
                    anos_operacao=5,
                    faturamento_anual_declarado=1000000,
                    valor_solicitado=300000,
                    prazo_meses=36,
                    finalidade="expansao",
                ),
                fora_de_escopo=True,
                motivo_recusa=None,
            )

    def test_recusa_com_motivo_ok(self):
        d = DadosExtraidos(
            pedido=PedidoCredito(
                setor="saude",
                porte="ME",
                uf="SP",
                anos_operacao=5,
                faturamento_anual_declarado=1000000,
                valor_solicitado=300000,
                prazo_meses=36,
                finalidade="expansao",
            ),
            fora_de_escopo=True,
            motivo_recusa="Pessoa física",
        )
        assert d.fora_de_escopo is True
        assert d.motivo_recusa == "Pessoa física"


class TestLaudo:
    def test_status_padrao_pendente(self):
        resultado = ResultadoModelo(pd=0.1, faixa_risco="baixo", fatores=[], model_version="v1")
        enriquecidos = DadosEnriquecidos(
            extraidos=DadosExtraidos(
                pedido=PedidoCredito(
                    setor="saude",
                    porte="ME",
                    uf="SP",
                    anos_operacao=5,
                    faturamento_anual_declarado=1000000,
                    valor_solicitado=300000,
                    prazo_meses=36,
                    finalidade="expansao",
                )
            )
        )
        laudo = Laudo(
            enriquecidos=enriquecidos,
            resultado_modelo=resultado,
            texto="Teste",
        )
        assert laudo.status == "pendente"

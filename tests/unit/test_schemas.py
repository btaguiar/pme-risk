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
                    setor="saude_servicos_sociais",
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
                setor="saude_servicos_sociais",
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
                    setor="saude_servicos_sociais",
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


class TestSetorCNAE:
    def test_rotulo_livre_rejeitado(self):
        import pytest
        from pydantic import ValidationError

        from agents.schemas import PedidoCredito

        with pytest.raises(ValidationError):
            PedidoCredito(
                setor="saude_odontologia",  # rótulo livre do eval v5
                porte="ME",
                uf="SP",
                anos_operacao=1,
                faturamento_anual_declarado=1,
                valor_solicitado=1,
                finalidade="expansao",
            )

    def test_prompt_do_extrator_lista_todas_as_secoes(self):
        from agents.extractor.extractor import PROMPT_PATH
        from agents.setores import SETORES_CNAE

        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        faltando = [cod for cod in SETORES_CNAE if f"`{cod}`" not in prompt]
        assert not faltando, f"Seções CNAE ausentes do prompt: {faltando}"

    def test_prompt_do_extrator_lista_todas_as_finalidades(self):
        from agents.extractor.extractor import PROMPT_PATH
        from agents.finalidades import FINALIDADES

        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        faltando = [cod for cod in FINALIDADES if f"`{cod}`" not in prompt]
        assert not faltando, f"Finalidades ausentes do prompt: {faltando}"

    def test_finalidade_fora_do_vocabulario_rejeitada(self):
        from pydantic import ValidationError

        from agents.schemas import PedidoCredito

        with pytest.raises(ValidationError):
            PedidoCredito(
                setor="comercio",
                porte="ME",
                uf="SP",
                anos_operacao=1,
                faturamento_anual_declarado=1,
                valor_solicitado=1,
                finalidade="modernizacao",
            )

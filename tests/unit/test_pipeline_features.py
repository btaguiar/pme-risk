"""Testes do mapeamento PedidoCredito → features do modelo v3 (SPEC §3.2)."""

from __future__ import annotations

import math

from agents.schemas import PedidoCredito
from api.pipeline import pedido_para_features
from model.features import FATOR_PPP_BRL_POR_USD, FEATURE_COLUMNS


def _pedido(**overrides: object) -> PedidoCredito:
    base = {
        "setor": "saude_servicos_sociais",
        "porte": "ME",
        "uf": "SP",
        "anos_operacao": 5,
        "faturamento_anual_declarado": 2_000_000,
        "valor_solicitado": 300_000,
        "prazo_meses": 36,
        "finalidade": "expansao",
    }
    return PedidoCredito(**{**base, **overrides})  # type: ignore[arg-type]


class TestPedidoParaFeatures:
    def test_mapeamento_direto(self):
        feats = pedido_para_features(_pedido())
        assert feats["secao_cnae"] == "saude_servicos_sociais"
        assert feats["faixa_idade"] == "5_mais"
        assert feats["log_valor_usd"] == math.log(300_000 / FATOR_PPP_BRL_POR_USD)

    def test_vetor_tem_exatamente_as_features_do_modelo(self):
        assert sorted(pedido_para_features(_pedido())) == sorted(FEATURE_COLUMNS)

    def test_faixa_de_idade_segue_as_fronteiras_do_treino(self):
        assert pedido_para_features(_pedido(anos_operacao=1))["faixa_idade"] == "startup"
        assert pedido_para_features(_pedido(anos_operacao=1.9))["faixa_idade"] == "startup"
        assert pedido_para_features(_pedido(anos_operacao=2))["faixa_idade"] == "2_5"
        assert pedido_para_features(_pedido(anos_operacao=4.9))["faixa_idade"] == "2_5"
        assert pedido_para_features(_pedido(anos_operacao=5))["faixa_idade"] == "5_mais"

    def test_faturamento_e_prazo_nao_entram_no_modelo(self):
        # Faturamento não existe na SBA; prazo da SBA vaza o desfecho (D3/P2)
        f1 = pedido_para_features(_pedido(faturamento_anual_declarado=10_000_000, prazo_meses=120))
        f2 = pedido_para_features(_pedido(faturamento_anual_declarado=10_000, prazo_meses=12))
        assert f1 == f2

    def test_setor_altera_a_feature_de_setor(self):
        # No v3 o setor é feature de verdade (não era no v2)
        assert pedido_para_features(_pedido(setor="comercio"))["secao_cnae"] == "comercio"

    def test_valor_zero_nao_quebra_o_log(self):
        feats = pedido_para_features(_pedido(valor_solicitado=0))
        assert feats["log_valor_usd"] == math.log(1.0 / FATOR_PPP_BRL_POR_USD)

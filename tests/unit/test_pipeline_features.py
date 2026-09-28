"""Testes do mapeamento PedidoCredito → features do modelo (SPEC §3.2)."""

from __future__ import annotations

from agents.schemas import PedidoCredito
from api.pipeline import pedido_para_features
from model.features import FEATURE_COLUMNS


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
        assert feats["amt_income_total"] == 2_000_000.0
        assert feats["amt_credit"] == 300_000.0
        assert feats["prazo_meses_estimado"] == 36.0
        assert feats["amt_annuity"] == 300_000.0 / 36
        assert feats["anos_operacao"] == 5.0
        assert feats["sem_emprego_registrado"] == 0.0
        assert feats["region_rating"] == 2.0

    def test_vetor_tem_exatamente_as_features_do_modelo(self):
        assert sorted(pedido_para_features(_pedido())) == sorted(FEATURE_COLUMNS)

    def test_prazo_ausente_usa_default_36(self):
        feats = pedido_para_features(_pedido(prazo_meses=None))
        assert feats["prazo_meses_estimado"] == 36.0
        assert feats["amt_annuity"] == 300_000.0 / 36

    def test_anos_operacao_limitado_a_60(self):
        feats = pedido_para_features(_pedido(anos_operacao=80))
        assert feats["anos_operacao"] == 60.0

    def test_setor_nao_altera_features(self):
        # Setor PME não tem análogo no treino — não pode mexer na PD (feature set v2)
        f1 = pedido_para_features(_pedido(setor="saude_servicos_sociais"))
        f2 = pedido_para_features(_pedido(setor="comercio"))
        assert f1 == f2

"""Testes do mapeamento PedidoCredito → features do modelo (SPEC §3.2)."""

from __future__ import annotations

from agents.schemas import PedidoCredito
from api.pipeline import _fnv1a_64_signed, pedido_para_features


def _pedido(**overrides: object) -> PedidoCredito:
    base = {
        "setor": "saude_odontologica",
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
        assert feats["days_employed_abs"] == round(5 * 365.25, 2)
        assert feats["region_rating"] == 2.0

    def test_prazo_ausente_usa_default_36(self):
        feats = pedido_para_features(_pedido(prazo_meses=None))
        assert feats["prazo_meses_estimado"] == 36.0
        assert feats["amt_annuity"] == 300_000.0 / 36

    def test_anos_operacao_limitado_a_60(self):
        feats = pedido_para_features(_pedido(anos_operacao=80))
        assert feats["anos_operacao"] == 60.0
        assert feats["days_employed_abs"] == round(60 * 365.25, 2)

    def test_occupation_encoded_deterministico_e_faixa(self):
        f1 = pedido_para_features(_pedido())
        f2 = pedido_para_features(_pedido())
        assert f1["occupation_type_encoded"] == f2["occupation_type_encoded"]
        assert 0.0 <= f1["occupation_type_encoded"] <= 99.0


class TestFnv1a:
    def test_deterministico(self):
        assert _fnv1a_64_signed("saude") == _fnv1a_64_signed("saude")

    def test_diferente_por_entrada(self):
        assert _fnv1a_64_signed("saude") != _fnv1a_64_signed("comercio")

    def test_valor_assinado_64_bits(self):
        h = _fnv1a_64_signed("x")
        assert -(1 << 63) <= h < (1 << 63)

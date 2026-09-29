"""Testes da métrica de extração (eval/laudo/run_eval.py) — sem LLM."""

from __future__ import annotations

import pytest

from agents.schemas import DadosExtraidos, PedidoCredito
from eval.laudo import run_eval
from eval.laudo.run_eval import (
    ACERTO,
    ALUCINACAO,
    ERRO_VALOR,
    NEGATIVO,
    OMISSAO,
    classificar_campo,
    executar_golden_set,
    montar_resultado,
)

_ESPERADO = {
    "setor": "saude_servicos_sociais",
    "porte": "EPP",
    "uf": "SP",
    "anos_operacao": 5,
    "faturamento_anual_declarado": 2_000_000,
    "valor_solicitado": 300_000,
    "prazo_meses": None,
    "finalidade": "expansao",
    "cnpj": None,
    "fora_de_escopo": False,
}
_N_ANOTADOS = 7  # campos não-null em _ESPERADO


def _pedido(**overrides: object) -> DadosExtraidos:
    base = {k: v for k, v in _ESPERADO.items() if k != "fora_de_escopo"}
    return DadosExtraidos(pedido=PedidoCredito(**{**base, **overrides}))  # type: ignore[arg-type]


def _recusa() -> DadosExtraidos:
    return DadosExtraidos(fora_de_escopo=True, motivo_recusa="pessoa física")


def _rodar(monkeypatch, golden: list[dict], respostas: list) -> dict:
    monkeypatch.setattr(run_eval, "carregar_golden_set", lambda: golden)
    fila = iter(respostas)

    def extrair_fn(texto: str, project_id: str | None = None) -> DadosExtraidos:
        resposta = next(fila)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    return montar_resultado(executar_golden_set(extrair_fn=extrair_fn), parcial=False)


def _item(esperado: dict) -> dict:
    return {"texto_pt_br": "texto", "esperado": esperado}


class TestClassificarCampo:
    @pytest.mark.parametrize(
        ("esperado", "obtido", "classe"),
        [
            ("SP", "SP", ACERTO),
            ("SP", None, OMISSAO),
            ("SP", "RJ", ERRO_VALOR),
            (None, "RJ", ALUCINACAO),
            (None, None, NEGATIVO),
            (5, 5.0, ACERTO),
            (["construcao", "profissionais_cientificas_tecnicas"], "construcao", ACERTO),
            (["construcao", "profissionais_cientificas_tecnicas"], "comercio", ERRO_VALOR),
        ],
    )
    def test_classes(self, esperado, obtido, classe):
        assert classificar_campo(esperado, obtido) == classe


class TestExecutarGoldenSet:
    def test_extracao_perfeita_f1_um(self, monkeypatch):
        r = _rodar(monkeypatch, [_item(_ESPERADO)], [_pedido()])
        assert r["f1_extracao"] == 1.0
        assert r["tp"] == _N_ANOTADOS and r["fp"] == 0 and r["fn"] == 0
        # nada anotado nem extraído → sem F1, não 0.0
        assert r["f1_por_campo"]["cnpj"] is None

    def test_alucinacao_em_campo_nao_mencionado_conta_fp(self, monkeypatch):
        r = _rodar(monkeypatch, [_item(_ESPERADO)], [_pedido(prazo_meses=36)])
        assert r["fp"] == 1 and r["fn"] == 0
        assert r["classes"][ALUCINACAO] == 1
        assert r["f1_extracao"] < 1.0

    def test_valor_errado_conta_fp_e_fn(self, monkeypatch):
        r = _rodar(monkeypatch, [_item(_ESPERADO)], [_pedido(uf="RJ")])
        assert r["tp"] == _N_ANOTADOS - 1 and r["fp"] == 1 and r["fn"] == 1
        assert r["divergencias"] == [
            {"indice": 0, "campo": "uf", "tipo": ERRO_VALOR, "esperado": "SP", "obtido": "RJ"}
        ]

    def test_falha_de_execucao_fica_no_denominador(self, monkeypatch):
        r = _rodar(
            monkeypatch,
            [_item(_ESPERADO), _item(_ESPERADO)],
            [_pedido(), RuntimeError("429")],
        )
        assert r["n_falhas_execucao"] == 1
        assert r["tp"] == _N_ANOTADOS and r["fn"] == _N_ANOTADOS
        assert r["f1_macro_por_item"] == 0.5
        # o método antigo excluía a falha e reportaria 1.0
        assert r["f1_metodo_v4"] == 1.0

    def test_recusa_indevida_conta_omissao_e_taxa(self, monkeypatch):
        r = _rodar(monkeypatch, [_item(_ESPERADO)], [_recusa()])
        assert r["n_recusas_indevidas"] == 1
        assert r["taxa_recusa_indevida"] == 1.0
        assert r["fn"] == _N_ANOTADOS and r["f1_extracao"] == 0.0

    def test_recusa_correta_nao_entra_no_f1(self, monkeypatch):
        fora = {"fora_de_escopo": True, "motivo_recusa": "pessoa física"}
        r = _rodar(monkeypatch, [_item(fora)], [_recusa()])
        assert r["taxa_recusa_correta"] == 1.0
        assert r["n_em_escopo"] == 0 and r["tp"] == r["fp"] == r["fn"] == 0

    def test_falha_em_item_fora_de_escopo_nao_e_recusa_correta(self, monkeypatch):
        fora = {"fora_de_escopo": True, "motivo_recusa": "pessoa física"}
        r = _rodar(monkeypatch, [_item(fora)], [RuntimeError("timeout")])
        assert r["n_recusas_esperadas"] == 1 and r["n_recusas_corretas"] == 0

    def test_f1_e_recusas_separados_por_lote(self, monkeypatch):
        fora = {"fora_de_escopo": True, "motivo_recusa": "pessoa física"}
        golden = [
            _item(_ESPERADO),
            {**_item(_ESPERADO), "lote": "v7_novos"},
            {**_item(fora), "lote": "v7_novos"},
        ]
        r = _rodar(monkeypatch, golden, [_pedido(), _pedido(uf="RJ"), _recusa()])
        assert r["por_lote"]["original"]["f1_extracao"] == 1.0
        assert r["por_lote"]["v7_novos"]["f1_extracao"] < 1.0
        assert r["por_lote"]["v7_novos"]["n_recusas_corretas"] == 1
        assert r["por_lote"]["original"]["n_recusas_esperadas"] == 0

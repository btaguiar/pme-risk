"""model/predict.py no v3 — BigQuery e registry simulados."""

from __future__ import annotations

import math

import pytest

from agents.schemas import PedidoCredito
from api.pipeline import pedido_para_features
from model import calibracao, predict
from model.features import FEATURE_COLUMNS

_FEATURES = {"secao_cnae": "comercio", "faixa_idade": "5_mais", "log_valor_usd": 10.0}


class _Job:
    def __init__(self, linhas):
        self._linhas = linhas

    def result(self):
        return self._linhas


class _Client:
    """ML.PREDICT devolve pd=0.10; ML.EXPLAIN_PREDICT, uma atribuição."""

    consultas: list[tuple[str, list]] = []

    def __init__(self, project=None):
        pass

    def query(self, sql, job_config=None):
        _Client.consultas.append((sql, list(job_config.query_parameters)))
        if "EXPLAIN_PREDICT" in sql:
            return _Job(
                [{"top_feature_attributions": [{"feature": "log_valor_usd", "attribution": 0.2}]}]
            )
        return _Job([{"pd": 0.10}])


class _Registry:
    def __init__(self, project_id, dataset):
        pass

    def obter_producao(self):
        return {"model_version": "logreg_v3"}


@pytest.fixture(autouse=True)
def _bq(monkeypatch):
    _Client.consultas = []
    monkeypatch.setattr(predict.bigquery, "Client", _Client)
    monkeypatch.setattr(predict, "ModelRegistry", _Registry)
    fatores = calibracao.FatoresSCR(rr_porte={"Micro": 0.78}, rr_uf={"AC": 1.97})
    monkeypatch.setattr(calibracao, "carregar_fatores", lambda *_: fatores)


def test_sem_porte_e_uf_devolve_a_pd_do_modelo():
    r = predict.prever(_FEATURES, "proj", "ds")
    assert r.pd == pytest.approx(0.10)
    assert r.fatores == [("log_valor_usd", 0.2)]
    assert r.model_version == "logreg_v3"


def test_com_porte_e_uf_aplica_a_calibracao_e_nomeia_os_ajustes():
    r = predict.prever(_FEATURES, "proj", "ds", porte="ME", uf="AC")
    logit = math.log(0.10 / 0.90) + math.log(0.78) + math.log(1.97)
    assert r.pd == pytest.approx(1 / (1 + math.exp(-logit)))
    nomes = [n for n, _ in r.fatores]
    assert nomes == ["log_valor_usd", "ajuste_porte_br", "ajuste_uf_br"]
    assert dict(r.fatores)["ajuste_uf_br"] == pytest.approx(math.log(1.97))


def test_faixa_e_classificada_sobre_a_pd_final():
    r = predict.prever(_FEATURES, "proj", "ds", porte="ME", uf="AC")
    assert r.faixa_risco == predict.classificar_faixa_risco(r.pd)


def test_parametros_tipados_string_para_categoricas():
    predict.prever(_FEATURES, "proj", "ds")
    _sql, params = _Client.consultas[0]
    tipos = {p.name: p.type_ for p in params}
    assert tipos == {"secao_cnae": "STRING", "faixa_idade": "STRING", "log_valor_usd": "FLOAT64"}


def test_versao_sem_modelo_compativel_falha_claro(monkeypatch):
    monkeypatch.setattr(_Registry, "obter_producao", lambda self: {"model_version": "logreg_v2"})
    with pytest.raises(ValueError, match="logreg_v2"):
        predict.prever(_FEATURES, "proj", "ds")


def test_contrato_servico_igual_ao_treino():
    """O skew do v1 veio de o serviço montar features diferentes das do treino."""
    pedido = PedidoCredito(
        setor="comercio",
        porte="ME",
        uf="SP",
        anos_operacao=6,
        faturamento_anual_declarado=300_000,
        valor_solicitado=40_000,
        finalidade="estoque",
    )
    features = pedido_para_features(pedido)
    assert list(features) == FEATURE_COLUMNS
    assert list(predict._FEATURE_TYPES) == FEATURE_COLUMNS

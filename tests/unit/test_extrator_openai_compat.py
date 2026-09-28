"""Testes do extrator alternativo do eval — transporte HTTP falso, sem rede."""

from __future__ import annotations

import json

import httpx
import pytest

from eval.laudo import extrator_openai_compat as mod
from eval.laudo.extrator_openai_compat import ExtratorOpenAICompat

_PEDIDO = {
    "pedido": {
        "setor": "comercio",
        "atividade": "mercearia",
        "porte": "ME",
        "uf": "PE",
        "anos_operacao": 6,
        "faturamento_anual_declarado": 300000,
        "valor_solicitado": 40000,
        "prazo_meses": 12,
        "finalidade": "estoque",
        "cnpj": None,
    },
    "fora_de_escopo": False,
    "motivo_recusa": None,
}


def _resposta(conteudo: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": conteudo}}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 300},
        },
    )


def _extrator(respostas: list[httpx.Response], capturadas: list[dict]) -> ExtratorOpenAICompat:
    fila = iter(respostas)

    def handler(request: httpx.Request) -> httpx.Response:
        capturadas.append(json.loads(request.content))
        return next(fila)

    return ExtratorOpenAICompat(
        modelo="modelo-x",
        base_url="https://exemplo.invalid/v1",
        cliente=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "chave-de-teste")
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)


def test_extrai_e_registra_uso():
    capturadas: list[dict] = []
    ext = _extrator([_resposta(json.dumps(_PEDIDO))], capturadas)
    dados = ext("Mercearia em Recife...")
    assert dados.pedido is not None and dados.pedido.setor == "comercio"
    assert ext.uso == [{"entrada": 1500, "saida": 300}]


def test_envia_mesmo_schema_e_prompt_do_extrator_de_producao():
    from agents.extractor.extractor import montar_prompt
    from agents.schemas import DadosExtraidos

    capturadas: list[dict] = []
    _extrator([_resposta(json.dumps(_PEDIDO))], capturadas)("texto do pedido")
    corpo = capturadas[0]
    assert corpo["messages"][0]["content"] == montar_prompt("texto do pedido")
    rf = corpo["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    enviado = rf["json_schema"]["schema"]
    assert enviado["required"] == list(DadosExtraidos.model_json_schema()["properties"])
    pedido = enviado["$defs"]["PedidoCredito"]
    assert set(pedido["required"]) == set(pedido["properties"])
    assert corpo["temperature"] == 0


def test_repete_em_429():
    capturadas: list[dict] = []
    ext = _extrator([httpx.Response(429), _resposta(json.dumps(_PEDIDO))], capturadas)
    assert ext("texto").pedido is not None
    assert len(capturadas) == 2


def test_setor_fora_da_cnae_falha_validacao():
    invalido = {**_PEDIDO, "pedido": {**_PEDIDO["pedido"], "setor": "varejo_otica"}}
    ext = _extrator([_resposta(json.dumps(invalido))], [])
    with pytest.raises(ValueError):
        ext("texto")


def test_sem_chave_falha(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    ext = _extrator([], [])
    with pytest.raises(RuntimeError):
        ext("texto")


def test_recusa_incompleta_falha_validacao():
    # {"pedido": null} sem fora_de_escopo: o que o schema frouxo permitia
    ext = _extrator([_resposta(json.dumps({"pedido": None}))], [])
    with pytest.raises(ValueError):
        ext("texto")

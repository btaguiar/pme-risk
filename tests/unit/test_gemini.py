"""Helpers compartilhados dos agentes Gemini — agents/gemini.py."""

from __future__ import annotations

import pytest
from google.genai import types

from agents.gemini import RespostaInvalidaError, resolver_project_id, validar_resposta
from agents.schemas import DadosExtraidos


def _resposta(texto: str | None, finish_reason: str = "STOP") -> types.GenerateContentResponse:
    parts = [types.Part(text=texto)] if texto is not None else []
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=finish_reason,
            )
        ]
    )


class TestResolverProjectId:
    def test_explicito_prevalece(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "do-env")
        assert resolver_project_id("explicito") == "explicito"

    def test_cai_no_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "do-env")
        assert resolver_project_id(None) == "do-env"

    def test_sem_nada_erro_claro(self, monkeypatch):
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        with pytest.raises(RuntimeError, match="GCP_PROJECT_ID"):
            resolver_project_id(None)


class TestValidarResposta:
    def test_json_valido(self):
        r = _resposta('{"fora_de_escopo": true, "motivo_recusa": "pessoa física"}')
        dados = validar_resposta(r, DadosExtraidos)
        assert dados.fora_de_escopo is True

    def test_vazia_informa_finish_reason(self):
        with pytest.raises(RespostaInvalidaError, match="SAFETY"):
            validar_resposta(_resposta(None, "SAFETY"), DadosExtraidos)

    def test_json_truncado(self):
        with pytest.raises(RespostaInvalidaError):
            validar_resposta(_resposta('{"fora_de_escopo": tr'), DadosExtraidos)

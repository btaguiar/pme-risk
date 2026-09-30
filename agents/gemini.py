"""Opções HTTP compartilhadas pelos agentes que chamam o Gemini (Vertex AI).

O cliente google-genai não repete requisições por padrão: um 429
(RESOURCE_EXHAUSTED, cota por minuto) virava 500 direto na API — visto duas
vezes na validação de 2026-09-28. Backoff exponencial: ~2+4+8+16s no pior caso.

Timeout por requisição: sem ele, uma conexão lenta segurava a chamada sem
limite (visto no eval de 2026-09-30: redação com pico de 130 s). A demo
pública passa pelo Firebase Hosting, que corta em 60 s — melhor falhar antes,
com 503 claro (api/routes/laudos.py), do que o visitante ver um 504 do proxy.
"""

from __future__ import annotations

import os

from google.genai import types
from pydantic import BaseModel, ValidationError

TIMEOUT_MS = 45_000

HTTP_OPTIONS = types.HttpOptions(
    timeout=TIMEOUT_MS,
    retry_options=types.HttpRetryOptions(
        attempts=5,
        initial_delay=2.0,
        max_delay=30.0,
        http_status_codes=[429, 500, 503, 504],
    ),
)


def config_thinking() -> types.ThinkingConfig:
    """Orçamento de "thinking" do Gemini 2.5 Flash (GEMINI_THINKING_BUDGET).

    Padrão 0 (desligado): medido em 2026-09-30, o Extrator caiu de 7,9 s para
    1,4 s e o Redator de 15,6 s para 4,3 s — com thinking, o pipeline passava
    dos 60 s do Firebase Hosting. -1 volta ao comportamento dinâmico do modelo
    (o dos evals v7 de extração e v3 do laudo). Qualidade sem thinking medida
    nos evals antes de ir para produção (README).
    """
    return types.ThinkingConfig(thinking_budget=int(os.environ.get("GEMINI_THINKING_BUDGET", "0")))


class RespostaInvalidaError(RuntimeError):
    """O Gemini respondeu, mas sem JSON válido para o schema pedido.

    Acontece com resposta vazia (bloqueio de segurança, MAX_TOKENS) ou JSON
    truncado. Não é transitório como um 429: a API devolve 502, não 503.
    """


def resolver_project_id(project_id: str | None) -> str:
    """project_id explícito ou GCP_PROJECT_ID — erro claro em vez de KeyError."""
    project_id = project_id or os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID não configurado")
    return project_id


def validar_resposta[M: BaseModel](response: types.GenerateContentResponse, schema: type[M]) -> M:
    """Converte o texto da resposta no schema, sem deixar vazar JSONDecodeError."""
    texto = response.text
    if not texto:
        motivo = response.candidates[0].finish_reason if response.candidates else None
        raise RespostaInvalidaError(f"Resposta vazia do Gemini (finish_reason={motivo})")
    try:
        return schema.model_validate_json(texto)
    except ValidationError as e:
        raise RespostaInvalidaError(f"Resposta do Gemini fora do schema {schema.__name__}") from e

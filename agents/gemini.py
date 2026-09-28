"""Opções HTTP compartilhadas pelos agentes que chamam o Gemini (Vertex AI).

O cliente google-genai não repete requisições por padrão: um 429
(RESOURCE_EXHAUSTED, cota por minuto) virava 500 direto na API — visto duas
vezes na validação de 2026-09-28. Backoff exponencial: ~2+4+8+16s no pior caso.
"""

from __future__ import annotations

from google.genai import types

HTTP_OPTIONS = types.HttpOptions(
    retry_options=types.HttpRetryOptions(
        attempts=5,
        initial_delay=2.0,
        max_delay=30.0,
        http_status_codes=[429, 500, 503, 504],
    )
)

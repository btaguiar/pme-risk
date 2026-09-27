"""Extrator — transforma texto livre em DadosExtraidos.

Referência: SPEC §4.2
"""

from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types

from agents.schemas import DadosExtraidos

PROMPT_PATH = Path(__file__).parent / "prompt.md"

# Modelo Gemini para extração (free tier flash)
EXTRACT_MODEL = "gemini-2.5-flash"


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def extrair(
    texto: str,
    api_key: str | None = None,
) -> DadosExtraidos:
    """Extrai dados estruturados de um pedido de crédito em texto livre.

    Args:
        texto: pedido de crédito em pt-BR
        api_key: chave da API Gemini (opcional se GOOGLE_API_KEY setado)

    Returns:
        DadosExtraidos com pedido estruturado ou recusa
    """
    client = genai.Client(api_key=api_key)

    prompt = f"""{_carregar_prompt()}

---

Extraia os dados do seguinte pedido:

{texto}
"""

    response = client.models.generate_content(
        model=EXTRACT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DadosExtraidos,
            temperature=0.0,
        ),
    )

    # O Gemini retorna JSON validado contra o schema
    resultado = json.loads(response.text)
    return DadosExtraidos.model_validate(resultado)

"""Extrator — transforma texto livre em DadosExtraidos.

Referência: SPEC §4.2
Usa Vertex AI via ADC (sem API key).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

from agents.gemini import HTTP_OPTIONS
from agents.schemas import DadosExtraidos

PROMPT_PATH = Path(__file__).parent / "prompt.md"

EXTRACT_MODEL = "gemini-2.5-flash"
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def extrair(
    texto: str,
    project_id: str | None = None,
) -> DadosExtraidos:
    """Extrai dados estruturados de um pedido de crédito em texto livre.

    Args:
        texto: pedido de crédito em pt-BR
        project_id: GCP project ID (usa GCP_PROJECT_ID se None)

    Returns:
        DadosExtraidos com pedido estruturado ou recusa
    """
    project_id = project_id or os.environ["GCP_PROJECT_ID"]
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=VERTEX_LOCATION,
        http_options=HTTP_OPTIONS,
    )

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

    resultado = json.loads(response.text)
    return DadosExtraidos.model_validate(resultado)

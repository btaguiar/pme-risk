"""Redator — gera texto do laudo a partir de dados enriquecidos + resultado do modelo.

Referência: SPEC §4.2
Regra: NUNCA alterar a PD (PLANO §2, BRIEF.md)
Usa Vertex AI via ADC (sem API key).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from agents.schemas import DadosEnriquecidos, ResultadoModelo

PROMPT_PATH = Path(__file__).parent / "prompt.md"

REDACTOR_MODEL = "gemini-2.5-flash"
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


class ResultadoRedacao(BaseModel):
    """Saída do Redator."""

    texto: str
    evidencias: list[str]


def redigir(
    enriquecidos: DadosEnriquecidos,
    resultado_modelo: ResultadoModelo,
    project_id: str | None = None,
) -> ResultadoRedacao:
    """Redige o laudo de risco.

    Args:
        enriquecidos: dados com fonte_por_campo
        resultado_modelo: PD + fatores (FROZEN — não será alterado)
        project_id: GCP project ID (usa GCP_PROJECT_ID se None)

    Returns:
        ResultadoRedacao com texto e evidências
    """
    project_id = project_id or os.environ["GCP_PROJECT_ID"]
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=VERTEX_LOCATION,
    )

    dados_json = json.dumps(
        {
            "enriquecidos": enriquecidos.model_dump(),
            "resultado_modelo": resultado_modelo.model_dump(),
        },
        indent=2,
        ensure_ascii=False,
    )

    prompt = f"""{_carregar_prompt()}

---

Redija o laudo com base nos seguintes dados:

{dados_json}

IMPORTANTE: A PD é {resultado_modelo.pd:.4f}. Use exatamente este valor.
"""

    response = client.models.generate_content(
        model=REDACTOR_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ResultadoRedacao,
            temperature=0.3,
        ),
    )

    resultado = json.loads(response.text)
    return ResultadoRedacao.model_validate(resultado)

"""Redator — gera texto do laudo a partir de dados enriquecidos + resultado do modelo.

Referência: SPEC §4.2
Regra: NUNCA alterar a PD (PLANO §2, BRIEF.md)
"""

from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from agents.schemas import DadosEnriquecidos, ResultadoModelo

PROMPT_PATH = Path(__file__).parent / "prompt.md"

REDACTOR_MODEL = "gemini-2.5-flash"


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


class ResultadoRedacao(BaseModel):
    """Saída do Redator."""

    texto: str
    evidencias: list[str]


def redigir(
    enriquecidos: DadosEnriquecidos,
    resultado_modelo: ResultadoModelo,
    api_key: str | None = None,
) -> ResultadoRedacao:
    """Redige o laudo de risco.

    Args:
        enriquecidos: dados com fonte_por_campo
        resultado_modelo: PD + fatores (FROZEN — não será alterado)
        api_key: chave da API Gemini

    Returns:
        ResultadoRedacao com texto e evidências
    """
    client = genai.Client(api_key=api_key)

    # Serializa dados para o prompt
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

"""Teste de integração — pipeline real, exige ADC + GCP_PROJECT_ID.

Run: GCP_PROJECT_ID=<projeto> uv run pytest tests/integration -v
Custa chamadas Gemini + BigQuery — rodar com parcimônia (PLANO §7).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"), reason="GCP_PROJECT_ID não definido"
)

TEXTO_PEDIDO = (
    "Clínica odontológica em São Paulo, ME, com 5 anos de operação, "
    "faturamento anual de R$ 2.000.000, solicita R$ 300.000 para expansão."
)


def test_gerar_laudo_ponta_a_ponta() -> None:
    from api.pipeline import LaudoCriado, Pipeline

    pipeline = Pipeline(
        os.environ["GCP_PROJECT_ID"],
        os.environ.get("BQ_DATASET", "pme_risk"),
    )
    resultado = pipeline.gerar(TEXTO_PEDIDO)
    assert isinstance(resultado, LaudoCriado)
    row = pipeline.obter(resultado.laudo_id)
    assert row is not None and row["status"] == "pendente"

"""Rotas de laudos — SPEC §5.1.

Rotas finas: parse → pipeline (adapter) → resposta.
"""

from __future__ import annotations

import hmac
import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import LaudoCriado, Pipeline, Recusa, get_pipeline

router = APIRouter(tags=["laudos"])

PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]


def verificar_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Protege endpoints custosos (Gemini + BigQuery) da demo pública.

    API_KEY_SECRET definido → exige header X-API-Key igual (compare_digest).
    Sem a env var → aberto (desenvolvimento local e testes).
    """
    esperado = os.environ.get("API_KEY_SECRET")
    if not esperado:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, esperado):
        raise HTTPException(status_code=401, detail="X-API-Key ausente ou inválida")


class PedidoTexto(BaseModel):
    texto: str = Field(min_length=10, description="Pedido de crédito PME em pt-BR")


@router.post("/laudos", status_code=201, dependencies=[Depends(verificar_api_key)])
def criar_laudo(pedido: PedidoTexto, pipeline: PipelineDep) -> dict[str, str]:
    resultado = pipeline.gerar(pedido.texto)
    if isinstance(resultado, Recusa):
        raise HTTPException(status_code=422, detail={"motivo_recusa": resultado.motivo})
    assert isinstance(resultado, LaudoCriado)
    return {"laudo_id": resultado.laudo_id, "status": resultado.status}


@router.get("/laudos/{laudo_id}")
def obter_laudo(laudo_id: str, pipeline: PipelineDep) -> dict:
    row = pipeline.obter(laudo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return _serializar(row)


def _serializar(row: dict) -> dict:
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "enriquecidos": json.loads(row["enriquecidos_json"]),
        "resultado_modelo": json.loads(row["resultado_modelo_json"]),
        "texto": row["texto"],
        "evidencias": json.loads(row["evidencias_json"]),
        "decidido_por": row.get("decidido_por"),
        "decidido_em": row.get("decidido_em"),
        "observacao_humana": row.get("observacao_humana"),
        "criado_em": row.get("criado_em"),
    }

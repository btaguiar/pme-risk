"""Rotas de laudos — SPEC §5.1.

Rotas finas: parse → pipeline (adapter) → resposta.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import LaudoCriado, Pipeline, Recusa, get_pipeline

router = APIRouter(tags=["laudos"])


class PedidoTexto(BaseModel):
    texto: str = Field(min_length=10, description="Pedido de crédito PME em pt-BR")


@router.post("/laudos", status_code=201)
def criar_laudo(pedido: PedidoTexto, pipeline: Pipeline = Depends(get_pipeline)) -> dict[str, str]:
    resultado = pipeline.gerar(pedido.texto)
    if isinstance(resultado, Recusa):
        raise HTTPException(status_code=422, detail={"motivo_recusa": resultado.motivo})
    assert isinstance(resultado, LaudoCriado)
    return {"laudo_id": resultado.laudo_id, "status": resultado.status}


@router.get("/laudos/{laudo_id}")
def obter_laudo(laudo_id: str, pipeline: Pipeline = Depends(get_pipeline)) -> dict:
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

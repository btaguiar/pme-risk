"""Portão humano — endpoint de decisão (SPEC §5.1, §4.3)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import Pipeline, get_pipeline

router = APIRouter(tags=["laudos"])


class DecisaoRequest(BaseModel):
    decisao: Literal["aprovado", "corrigido", "rejeitado"]
    decidido_por: str = Field(min_length=1, description="Identificador do analista")
    observacao: str | None = None


@router.patch("/laudos/{laudo_id}/decisao")
def decidir_laudo(
    laudo_id: str, body: DecisaoRequest, pipeline: Pipeline = Depends(get_pipeline)
) -> dict:
    row = pipeline.decidir(laudo_id, body.decisao, body.decidido_por, body.observacao)
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "decidido_por": row["decidido_por"],
        "decidido_em": row["decidido_em"],
    }

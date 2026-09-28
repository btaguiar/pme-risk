"""Portão humano — endpoint de decisão (SPEC §5.1, §4.3)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import Pipeline, get_pipeline
from api.routes.portao_humano import LaudoJaDecididoError

router = APIRouter(tags=["laudos"])

PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]


class DecisaoRequest(BaseModel):
    decisao: Literal["aprovado", "corrigido", "rejeitado"]
    decidido_por: str = Field(min_length=1, description="Identificador do analista")
    observacao: str | None = None


@router.patch("/laudos/{laudo_id}/decisao")
def decidir_laudo(laudo_id: str, body: DecisaoRequest, pipeline: PipelineDep) -> dict:
    try:
        row = pipeline.decidir(laudo_id, body.decisao, body.decidido_por, body.observacao)
    except LaudoJaDecididoError as e:
        raise HTTPException(status_code=409, detail=f"Laudo já decidido (status={e.status})") from e
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "decidido_por": row["decidido_por"],
        "decidido_em": row["decidido_em"],
    }

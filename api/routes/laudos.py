"""Rotas de laudos — SPEC §5.1.

Rotas finas: parse → pipeline (adapter) → resposta.
"""

from __future__ import annotations

import hmac
import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from api import frontend
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
    # Obrigatório: entra no cálculo da parcela e da feature prazo_meses_estimado —
    # sem ele o modelo usaria um prazo default. Teto de 120 = clip do pipeline.
    prazo_meses: int = Field(ge=1, le=120, description="Prazo do crédito em meses")


@router.post("/laudos", status_code=201, dependencies=[Depends(verificar_api_key)])
def criar_laudo(pedido: PedidoTexto, pipeline: PipelineDep) -> dict[str, str]:
    try:
        resultado = pipeline.gerar(pedido.texto, prazo_meses=pedido.prazo_meses)
    except genai_errors.APIError as e:
        # Cota/indisponibilidade do Gemini que sobreviveu ao retry (agents/gemini.py):
        # erro transitório do lado de lá — 503 diz ao cliente para tentar depois.
        if e.code in (429, 503):
            raise HTTPException(
                status_code=503,
                detail="Serviço de LLM temporariamente indisponível; tente novamente.",
                headers={"Retry-After": "30"},
            ) from e
        raise
    if isinstance(resultado, Recusa):
        raise HTTPException(status_code=422, detail={"motivo_recusa": resultado.motivo})
    assert isinstance(resultado, LaudoCriado)
    return {"laudo_id": resultado.laudo_id, "status": resultado.status}


@router.get("/laudos/{laudo_id}")
def obter_laudo(request: Request, laudo_id: str, pipeline: PipelineDep):
    if frontend.quer_html(request):
        return frontend.casca_spa()
    row = pipeline.obter(laudo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return _serializar(row)


def _resumo(row: dict) -> dict:
    resultado = json.loads(row["resultado_modelo_json"]) if row.get("resultado_modelo_json") else {}
    extraidos = json.loads(row["enriquecidos_json"]) if row.get("enriquecidos_json") else {}
    pedido = extraidos.get("extraidos", {}).get("pedido") or {}
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "criado_em": row.get("criado_em"),
        "decidido_em": row.get("decidido_em"),
        "decidido_por": row.get("decidido_por"),
        "pd": resultado.get("pd"),
        "faixa_risco": resultado.get("faixa_risco"),
        "pedido": {
            "setor": pedido.get("setor"),
            "porte": pedido.get("porte"),
            "uf": pedido.get("uf"),
            "valor_solicitado": pedido.get("valor_solicitado"),
        },
    }


@router.get("/laudos")
def listar_laudos(request: Request, pipeline: PipelineDep, limite: int = 20):
    """Resumo dos laudos recentes (JSON) ou casca do SPA (navegador)."""
    if frontend.quer_html(request):
        return frontend.casca_spa()
    return [_resumo(row) for row in pipeline.listar(limite)]


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

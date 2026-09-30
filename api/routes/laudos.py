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

from agents.gemini import RespostaInvalidaError
from api import frontend, limites
from api.pipeline import LaudoCriado, Pipeline, Recusa, get_pipeline

router = APIRouter(tags=["laudos"])

PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]


def verificar_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Rotas só de analista (decisão do portão humano).

    API_KEY_SECRET definido → exige header X-API-Key igual (compare_digest).
    Sem a env var → aberto (desenvolvimento local e testes).
    """
    if _chave_valida(x_api_key) is False:
        raise HTTPException(status_code=401, detail="X-API-Key ausente ou inválida")


def _chave_valida(x_api_key: str | None) -> bool | None:
    """True/False se há chave configurada; None se não há (dev local)."""
    esperado = os.environ.get("API_KEY_SECRET")
    if not esperado:
        return None
    return x_api_key is not None and hmac.compare_digest(x_api_key, esperado)


def autorizar_criacao(
    request: Request,
    pipeline: PipelineDep,
    x_api_key: Annotated[str | None, Header()] = None,
    x_forwarded_for: Annotated[str | None, Header()] = None,
) -> None:
    """Chave de analista → sem limite. Demo aberta → limites diários (api/limites.py).

    Chave enviada e errada é 401 mesmo na demo aberta: não cai no limite
    silenciosamente. Sem CRIACAO_PUBLICA, vale a regra antiga (chave exigida).
    """
    valida = _chave_valida(x_api_key)
    if valida:
        return
    if x_api_key is not None and valida is False:
        raise HTTPException(status_code=401, detail="X-API-Key inválida")
    if not limites.criacao_publica():
        if valida is False:
            raise HTTPException(status_code=401, detail="X-API-Key ausente ou inválida")
        return  # dev local sem chave configurada
    retry = {"Retry-After": str(limites.segundos_ate_meia_noite_utc())}
    if pipeline.contar_pedidos_hoje() >= limites.limite_global():
        raise HTTPException(
            status_code=429,
            detail="A demo atingiu o limite diário de laudos. Tente novamente amanhã.",
            headers=retry,
        )
    ip = limites.ip_do_cliente(x_forwarded_for, request.client.host if request.client else None)
    if not limites.POR_IP.tentar(ip, limites.limite_por_ip()):
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {limites.limite_por_ip()} laudos por dia atingido. "
            "Tente novamente amanhã.",
            headers=retry,
        )


class PedidoTexto(BaseModel):
    texto: str = Field(min_length=10, description="Pedido de crédito PME em pt-BR")
    # Obrigatório: entra no cálculo da parcela e da feature prazo_meses_estimado —
    # sem ele o modelo usaria um prazo default. Teto de 120 = clip do pipeline.
    prazo_meses: int = Field(ge=1, le=120, description="Prazo do crédito em meses")


@router.post("/laudos", status_code=201, dependencies=[Depends(autorizar_criacao)])
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
    except RespostaInvalidaError as e:
        # O LLM respondeu fora do schema (vazio, truncado): falha do upstream.
        raise HTTPException(status_code=502, detail="Resposta inválida do serviço de LLM.") from e
    if isinstance(resultado, Recusa):
        raise HTTPException(status_code=422, detail={"motivo_recusa": resultado.motivo})
    if not isinstance(resultado, LaudoCriado):
        # assert some com python -O; tipo inesperado do pipeline vira 500 explícito.
        raise TypeError(f"Pipeline devolveu {type(resultado).__name__}")
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

"""Adapter de pipeline — único ponto de contato entre a Fase 3 (API) e a Fase 2 (agentes).

Referência: docs/superpowers/specs/2026-09-27-fase3-produto-design.md
Se a Fase 2 for reestruturada, este é o único arquivo a ajustar.

O mapeamento pedido → features segue a HIPÓTESE documentada em
model/features.py (SPEC §3.2) — proxy, não paridade com Home Credit.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from agents.extractor.extractor import PROMPT_PATH as _EXTRACTOR_PROMPT_PATH
from agents.extractor.extractor import extrair
from agents.pesquisador.pesquisador import enriquecer
from agents.redator.redator import PROMPT_PATH as _REDACTOR_PROMPT_PATH
from agents.redator.redator import ResultadoRedacao, redigir
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito, ResultadoModelo
from api.auditoria import TrilhaAuditoria
from api.routes.portao_humano import PortaoHumano
from model.predict import ResultadoPredicao, prever

_log = logging.getLogger(__name__)

# Proxy neutro de UF → region_rating. 2 é a moda de REGION_RATING_CLIENT.
# Sem inventar risco por UF (SPEC §3.2: "não geografia real").
_REGION_RATING_DEFAULT = 2

# Prazo default quando o pedido não menciona (mesma base do clip em 01_load_features.sql)
_PRAZO_DEFAULT_MESES = 36


def _fnv1a_64_signed(texto: str) -> int:
    """FNV-1a 64-bit com interpretação assinada — determinístico para `setor`.

    Não exige paridade exata com FARM_FINGERPRINT do BigQuery: o mapeamento
    setor → occupation_type já é aproximação documentada (SPEC §3.2).
    """
    h = 0xCBF29CE484222325
    for byte in texto.encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h - (1 << 64) if h >= (1 << 63) else h


def pedido_para_features(pedido: PedidoCredito) -> dict[str, float]:
    """Mapeia PedidoCredito (PME) → vetor de features do modelo (Home Credit)."""
    prazo = min(pedido.prazo_meses or _PRAZO_DEFAULT_MESES, 120)
    anos = min(max(pedido.anos_operacao, 0), 60)
    return {
        "amt_income_total": float(pedido.faturamento_anual_declarado),
        "amt_credit": float(pedido.valor_solicitado),
        "amt_annuity": float(pedido.valor_solicitado) / prazo,
        "prazo_meses_estimado": float(prazo),
        "anos_operacao": float(anos),
        "days_employed_abs": round(anos * 365.25, 2),
        "occupation_type_encoded": float(abs(_fnv1a_64_signed(pedido.setor)) % 100),
        "region_rating": float(_REGION_RATING_DEFAULT),
    }


@dataclass(frozen=True)
class Recusa:
    motivo: str


@dataclass(frozen=True)
class LaudoCriado:
    laudo_id: str
    status: str = "pendente"


@lru_cache
def _hashes_prompt() -> dict[str, str]:
    return {
        "extrator": TrilhaAuditoria.hash_prompt(_EXTRACTOR_PROMPT_PATH.read_text(encoding="utf-8")),
        "redator": TrilhaAuditoria.hash_prompt(_REDACTOR_PROMPT_PATH.read_text(encoding="utf-8")),
    }


class Pipeline:
    """Orquestra extrator → pesquisador → modelo → redator + persistência.

    Callables e clientes são injetáveis para testes sem GCP.
    """

    def __init__(
        self,
        project_id: str,
        dataset: str,
        *,
        extrair_fn: Callable[..., DadosExtraidos] = extrair,
        enriquecer_fn: Callable[[DadosExtraidos], DadosEnriquecidos] = enriquecer,
        prever_fn: Callable[..., ResultadoPredicao] = prever,
        redigir_fn: Callable[..., ResultadoRedacao] = redigir,
        portao: PortaoHumano | None = None,
        auditoria: TrilhaAuditoria | None = None,
    ) -> None:
        self.project_id = project_id
        self.dataset = dataset
        self._extrair_fn = extrair_fn
        self._enriquecer_fn = enriquecer_fn
        self._prever_fn = prever_fn
        self._redigir_fn = redigir_fn
        self._portao = portao or PortaoHumano(project_id, dataset)
        self._auditoria = auditoria or TrilhaAuditoria(project_id, dataset)

    def gerar(self, texto: str) -> LaudoCriado | Recusa:
        """Roda o pipeline completo até `status='pendente'` (SPEC §5.1)."""
        etapas: list[dict[str, str]] = []
        extraidos = self._extrair_fn(texto, project_id=self.project_id)
        etapas.append({"etapa": "extrator", "timestamp": _agora()})

        if extraidos.fora_de_escopo:
            self._auditoria.registrar(
                laudo_id="-",
                pedido_bruto=texto,
                model_version=None,
                prompts_usados=_hashes_prompt(),
                decisao_humana=None,
                etapas=etapas,
            )
            return Recusa(motivo=extraidos.motivo_recusa or "fora de escopo")

        enriquecidos = self._enriquecer_fn(extraidos)
        etapas.append({"etapa": "pesquisador", "timestamp": _agora()})

        features = pedido_para_features(enriquecidos.extraidos.pedido)
        predicao = self._prever_fn(features, project_id=self.project_id, dataset=self.dataset)
        etapas.append({"etapa": "modelo", "timestamp": _agora()})

        resultado = ResultadoModelo(
            pd=predicao.pd,
            faixa_risco=predicao.faixa_risco,
            fatores=[(nome, contrib) for nome, contrib in predicao.fatores],
            model_version=predicao.model_version,
        )
        redacao = self._redigir_fn(enriquecidos, resultado, project_id=self.project_id)
        etapas.append({"etapa": "redator", "timestamp": _agora()})

        laudo_id = str(uuid.uuid4())
        self._portao.criar(
            laudo_id=laudo_id,
            pedido_bruto=texto,
            enriquecidos_json=enriquecidos.model_dump_json(),
            resultado_modelo_json=resultado.model_dump_json(),
            texto=redacao.texto,
            evidencias_json=json.dumps(redacao.evidencias, ensure_ascii=False),
        )
        try:
            self._auditoria.registrar(
                laudo_id=laudo_id,
                pedido_bruto=texto,
                model_version=predicao.model_version,
                prompts_usados=_hashes_prompt(),
                decisao_humana=None,
                etapas=etapas,
            )
        except Exception:
            # Laudo já persistido — falha de auditoria não deve falhar a requisição
            # (retry do cliente duplicaria o laudo). Degradação visível nos logs.
            _log.exception("Falha ao registrar auditoria do laudo %s", laudo_id)
        return LaudoCriado(laudo_id=laudo_id)

    def obter(self, laudo_id: str) -> dict | None:
        return self._portao.obter(laudo_id)

    def decidir(
        self,
        laudo_id: str,
        decisao: str,
        decidido_por: str,
        observacao: str | None = None,
    ) -> dict | None:
        row = self._portao.decidir(laudo_id, decisao, decidido_por, observacao)
        return row or None


def _agora() -> str:
    return datetime.now(UTC).isoformat()


@lru_cache
def get_pipeline() -> Pipeline:
    """Dependência FastAPI — instância real (GCP) para produção."""
    return Pipeline(
        os.environ["GCP_PROJECT_ID"],
        os.environ.get("BQ_DATASET", "pme_risk"),
    )

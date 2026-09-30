"""Adapter de pipeline — único ponto de contato entre a Fase 3 (API) e a Fase 2 (agentes).

Referência: docs/superpowers/specs/2026-09-27-fase3-produto-design.md
Se a Fase 2 for reestruturada, este é o único arquivo a ajustar.

O mapeamento pedido → features segue a HIPÓTESE documentada em
model/features.py (SPEC §3.2) — proxy, não paridade com Home Credit.
"""

from __future__ import annotations

import json
import logging
import math
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
from model.features import FATOR_PPP_BRL_POR_USD
from model.mapeamentos import faixa_idade_pedido
from model.predict import ResultadoPredicao, prever

_log = logging.getLogger(__name__)

# No v3 nenhuma feature é constante no serviço: setor, idade e valor vêm do
# pedido. O filtro permanece porque os ajustes de calibração SCR não são
# features do modelo e o laudo só cita fatores + ajustes nomeados.
FEATURES_CONSTANTES_NO_SERVICO = frozenset()


def pedido_para_features(pedido: PedidoCredito) -> dict[str, float | str]:
    """Mapeia PedidoCredito (PME) → vetor de features do modelo v3 (SBA).

    Valor em US$ PPP (fator do Banco Mundial — decisão P1 do plano; o câmbio
    de mercado faria o pedido parecer ~2× menor). Faturamento e prazo ficam
    fora do modelo: a SBA não tem faturamento e o prazo dela vaza o desfecho
    (model/features.py).
    """
    # Valor 0 (schema aceita) daria ln(0); ancora em 1 BRL — cauda extrema
    # esquerda, sem derrubar a requisição.
    valor_usd = max(float(pedido.valor_solicitado), 1.0) / FATOR_PPP_BRL_POR_USD
    return {
        "secao_cnae": pedido.setor,
        "faixa_idade": faixa_idade_pedido(pedido.anos_operacao),
        "log_valor_usd": math.log(valor_usd),
    }


def montar_resultado_modelo(predicao: ResultadoPredicao) -> ResultadoModelo:
    """ResultadoModelo do laudo — sem os fatores constantes no serviço."""
    return ResultadoModelo(
        pd=predicao.pd,
        faixa_risco=predicao.faixa_risco,
        fatores=[
            (nome, contrib)
            for nome, contrib in predicao.fatores
            if nome not in FEATURES_CONSTANTES_NO_SERVICO
        ],
        model_version=predicao.model_version,
    )


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
        self._portao = portao
        self._auditoria = auditoria

    @property
    def portao(self) -> PortaoHumano:
        """Portão humano — criado só no primeiro uso (casca do SPA não precisa de GCP)."""
        if self._portao is None:
            if not self.project_id:
                raise RuntimeError("GCP_PROJECT_ID não configurado")
            self._portao = PortaoHumano(self.project_id, self.dataset)
        return self._portao

    @property
    def auditoria(self) -> TrilhaAuditoria:
        """Trilha de auditoria — criada só no primeiro uso."""
        if self._auditoria is None:
            if not self.project_id:
                raise RuntimeError("GCP_PROJECT_ID não configurado")
            self._auditoria = TrilhaAuditoria(self.project_id, self.dataset)
        return self._auditoria

    def gerar(self, texto: str, prazo_meses: int | None = None) -> LaudoCriado | Recusa:
        """Roda o pipeline completo até `status='pendente'` (SPEC §5.1).

        `prazo_meses` vem de campo estruturado do formulário e prevalece sobre o
        prazo que o Extrator ler no texto; fica registrado no pedido bruto.
        """
        etapas: list[dict[str, str]] = []
        pedido_bruto = (
            texto if prazo_meses is None else f"{texto}\n\n[Prazo solicitado: {prazo_meses} meses]"
        )
        extraidos = self._extrair_fn(texto, project_id=self.project_id)
        etapas.append({"etapa": "extrator", "timestamp": _agora()})

        if prazo_meses is not None and extraidos.pedido is not None:
            pedido = extraidos.pedido.model_copy(update={"prazo_meses": prazo_meses})
            extraidos = extraidos.model_copy(update={"pedido": pedido})

        if extraidos.fora_de_escopo:
            self.auditoria.registrar(
                laudo_id="-",
                pedido_bruto=pedido_bruto,
                model_version=None,
                prompts_usados=_hashes_prompt(),
                decisao_humana=None,
                etapas=etapas,
            )
            return Recusa(motivo=extraidos.motivo_recusa or "fora de escopo")

        enriquecidos = self._enriquecer_fn(extraidos)
        etapas.append({"etapa": "pesquisador", "timestamp": _agora()})

        features = pedido_para_features(enriquecidos.extraidos.pedido)
        predicao = self._prever_fn(
            features,
            project_id=self.project_id,
            dataset=self.dataset,
            porte=extraidos.pedido.porte,
            uf=extraidos.pedido.uf,
        )
        etapas.append({"etapa": "modelo", "timestamp": _agora()})

        resultado = montar_resultado_modelo(predicao)
        redacao = self._redigir_fn(enriquecidos, resultado, project_id=self.project_id)
        etapas.append({"etapa": "redator", "timestamp": _agora()})

        laudo_id = str(uuid.uuid4())
        self.portao.criar(
            laudo_id=laudo_id,
            pedido_bruto=pedido_bruto,
            enriquecidos_json=enriquecidos.model_dump_json(),
            resultado_modelo_json=resultado.model_dump_json(),
            texto=redacao.texto,
            evidencias_json=json.dumps(redacao.evidencias, ensure_ascii=False),
        )
        try:
            self.auditoria.registrar(
                laudo_id=laudo_id,
                pedido_bruto=pedido_bruto,
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
        return self.portao.obter(laudo_id)

    def listar(self, limite: int = 20) -> list[dict]:
        return self.portao.listar(limite)

    def contar_pedidos_hoje(self) -> int:
        """Pedidos do dia UTC corrente — teto global da demo aberta (api/limites.py)."""
        hoje = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.auditoria.contar_pedidos_desde(hoje)

    def decidir(
        self,
        laudo_id: str,
        decisao: str,
        decidido_por: str,
        observacao: str | None = None,
    ) -> dict | None:
        """Portão humano + registro da decisão na trilha append-only (SPEC §4.4).

        Propaga LaudoJaDecididoError — decisões são finais.
        """
        row = self.portao.decidir(laudo_id, decisao, decidido_por, observacao)
        if not row:
            return None
        decisao_humana = {
            "decisao": decisao,
            "decidido_por": decidido_por,
            "decidido_em": str(row.get("decidido_em")),
            "observacao": observacao,
        }
        try:
            self.auditoria.registrar(
                laudo_id=laudo_id,
                pedido_bruto=row.get("pedido_bruto") or "",
                model_version=json.loads(row["resultado_modelo_json"]).get("model_version"),
                prompts_usados={},
                decisao_humana=json.dumps(decisao_humana, ensure_ascii=False),
                etapas=[{"etapa": "decisao_humana", "timestamp": _agora()}],
            )
        except Exception:
            # Mesma política do gerar(): a decisão já está persistida em `laudos`.
            _log.exception("Falha ao registrar decisão do laudo %s na auditoria", laudo_id)
        return row


def _agora() -> str:
    return datetime.now(UTC).isoformat()


@lru_cache
def get_pipeline() -> Pipeline:
    """Dependência FastAPI — instância real (GCP) para produção."""
    return Pipeline(
        os.environ.get("GCP_PROJECT_ID", ""),
        os.environ.get("BQ_DATASET", "pme_risk"),
    )

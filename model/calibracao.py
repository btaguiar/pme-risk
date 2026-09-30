"""Calibração brasileira da PD — riscos relativos do SCR em escala logit.

    logit(PD_final) = logit(PD_SBA) + ln(RR_porte) + ln(RR_uf)

- RR_porte: MEI e ME → `Micro`; EPP → `Pequeno` (SCR.data).
- RR_uf: UF do pedido; UF abaixo do piso de carteira fica com RR = 1 na
  origem (10_scr_fatores.sql) — aqui, UF ausente também é 0 de ajuste.
- O nível absoluto NÃO é calibrado pelo SCR: a inadimplência dele é estoque
  vencido > 90 dias e a perda da SBA é acumulada na vida do empréstimo
  (levantamento §2). Só o risco relativo entre segmentos.
- Os dois ajustes entram como `ajuste_porte_br` e `ajuste_uf_br` na lista de
  fatores do laudo — nomes que o Redator explica e o juiz de fidedignidade
  aceita (plano v3, Task 5).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from google.cloud import bigquery

# Porte do pedido (LC 123/2006) → porte do SCR
_PORTE_PARA_SCR = {"MEI": "Micro", "ME": "Micro", "EPP": "Pequeno"}

# BQML devolve (0, 1), mas o float pode raspar as bordas; logit exige aberto
_EPS_PD = 1e-12


@dataclass(frozen=True)
class FatoresSCR:
    """Riscos relativos por porte e UF (tabela `scr_fatores`)."""

    rr_porte: Mapping[str, float] = field(default_factory=dict)
    rr_uf: Mapping[str, float] = field(default_factory=dict)

    def ajuste_porte(self, porte: str) -> float:
        """Δlogit do porte; 0 quando não há fator (ex.: porte fora do SCR)."""
        chave = _PORTE_PARA_SCR.get(porte, porte)
        return math.log(self.rr_porte.get(chave, 1.0))

    def ajuste_uf(self, uf: str) -> float:
        """Δlogit da UF; 0 quando a UF não tem fator (piso de carteira)."""
        return math.log(self.rr_uf.get(uf, 1.0))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def aplicar(
    pd_sba: float, porte: str, uf: str, fatores: FatoresSCR
) -> tuple[float, list[tuple[str, float]]]:
    """Aplica os dois ajustes e devolve (pd_final, [(nome, Δlogit), ...])."""
    ajustes = [
        ("ajuste_porte_br", fatores.ajuste_porte(porte)),
        ("ajuste_uf_br", fatores.ajuste_uf(uf)),
    ]
    p = min(max(pd_sba, _EPS_PD), 1.0 - _EPS_PD)
    pd_final = _sigmoid(_logit(p) + sum(delta for _, delta in ajustes))
    return pd_final, ajustes


@lru_cache(maxsize=1)
def _fatores(project_id: str, dataset: str) -> FatoresSCR:
    client = bigquery.Client(project=project_id)
    rows = client.query(
        f"SELECT tipo, chave, rr FROM `{project_id}.{dataset}.scr_fatores`"
    ).result()
    rr_porte: dict[str, float] = {}
    rr_uf: dict[str, float] = {}
    for row in rows:
        destino = rr_porte if row["tipo"] == "porte" else rr_uf
        destino[row["chave"]] = float(row["rr"])
    return FatoresSCR(rr_porte=rr_porte, rr_uf=rr_uf)


def carregar_fatores(project_id: str, dataset: str) -> FatoresSCR:
    """Lê `scr_fatores` (cacheada — a tabela muda só quando o SCR é reingerido)."""
    return _fatores(project_id, dataset)

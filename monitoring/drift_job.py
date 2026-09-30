"""Job de drift — PSI da entrada (laudos) vs. referência BNDES (PLANO §5, SPEC §5.3).

v3: o treino é SBA 7(a) — PME americana. Comparar pedidos brasileiros contra
a distribuição de treino dispararia o PSI sempre. A referência de drift
passou a ser o **BNDES**: operações indiretas automáticas MICRO/PEQUENA,
contratações 2018–2022 (`bndes_referencia`, Task 6 do plano v3).

- `valor_solicitado` e `prazo_meses`: PSI numérico. Cada laudo cai nos decis
  da referência do seu porte (MEI/ME → MICRO, EPP → PEQUENA); pedidos de
  portes diferentes formam uma mistura — esperado uniforme por construção.
- `setor`: PSI categórico contra a distribuição de seções do BNDES.

Limites documentados: os valores do BNDES são nominais de 2018–2022
(inflação posterior pode deslocar o PSI de valor); o prazo do BNDES é
carência + amortização; porte e UF não entram aqui — o risco relativo deles
vem do SCR (model/calibracao.py).

PSI > 0.25 → log estruturado WARNING (log-based alert do free tier).
Roda como Cloud Run Job (deploy_drift.sh), não no processo da API.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from google.cloud import bigquery

LIMIAR_PSI = 0.25
N_BINS = 10
_EPS = 1e-6
# Abaixo disso o PSI mede ruído, não drift: sob H0, E[PSI] ≈ (N_BINS-1)/n —
# com n=30 já passa de 0.25, e com n < N_BINS há faixas vazias forçadas (PSI ~10).
# Com n=100 o piso de ruído fica em ~0.09.
N_MIN_AMOSTRAS = 100

# Porte do pedido (LC 123/2006) → porte BNDES
_PORTE_PARA_BNDES = {"MEI": "MICRO", "ME": "MICRO", "EPP": "PEQUENA"}


@dataclass(frozen=True)
class ReferenciaBNDES:
    """Agregado de referência lido de `bndes_referencia` (ou injetado em teste)."""

    valor_decis: dict[str, list[float]] = field(default_factory=dict)  # porte → 9 cortes
    prazo_decis: dict[str, list[float]] = field(default_factory=dict)
    setor_proporcoes: dict[str, float] = field(default_factory=dict)  # seção → share


def _quantile(valores: Sequence[float], q: float) -> float:
    ordenado = sorted(valores)
    idx = min(int(q * (len(ordenado) - 1)), len(ordenado) - 1)
    return ordenado[idx]


def _proporcoes(valores: Sequence[float], limites: list[float]) -> list[float]:
    contagens = [0] * (len(limites) + 1)
    for v in valores:
        contagens[bisect.bisect_right(limites, v)] += 1
    return [c / len(valores) for c in contagens]


def _psi_proporcoes(p_esp: Sequence[float], p_atu: Sequence[float]) -> float:
    total = 0.0
    for e, a in zip(p_esp, p_atu, strict=True):
        e = max(e, _EPS)
        a = max(a, _EPS)
        total += (a - e) * math.log(a / e)
    return total


def psi(esperado: Sequence[float], atual: Sequence[float], n_bins: int = N_BINS) -> float:
    """Population Stability Index com bins por quantis da distribuição de referência."""
    if len(esperado) == 0 or len(atual) == 0:
        return 0.0
    limites = sorted({_quantile(esperado, i / n_bins) for i in range(1, n_bins)})
    return _psi_proporcoes(_proporcoes(esperado, limites), _proporcoes(atual, limites))


def psi_decis(grupos: Sequence[tuple[Sequence[float], Sequence[float]]]) -> float:
    """PSI contra decis de referência — mistura de grupos (portes).

    Cada valor cai no decil da referência do seu grupo; o esperado é uniforme
    (0,1 por bin) por construção dos decis.
    """
    contagens = [0] * N_BINS
    n = 0
    for decis, valores in grupos:
        if not decis:
            continue
        for v in valores:
            contagens[bisect.bisect_right(list(decis), v)] += 1
            n += 1
    if n == 0:
        return 0.0
    return _psi_proporcoes([1.0 / N_BINS] * N_BINS, [c / n for c in contagens])


def psi_categorico(esperado: Mapping[str, float], atual: Mapping[str, int]) -> float:
    """PSI categórico entre proporções esperadas e contagens atuais."""
    n = sum(atual.values())
    if n == 0 or not esperado:
        return 0.0
    chaves = sorted(set(esperado) | set(atual))
    p_esp = [esperado.get(c, 0.0) for c in chaves]
    p_atu = [atual.get(c, 0) / n for c in chaves]
    return _psi_proporcoes(p_esp, p_atu)


def calcular_drift(
    referencia: ReferenciaBNDES,
    pedidos: list[dict],
    min_amostras: int = N_MIN_AMOSTRAS,
) -> dict[str, float | None]:
    """PSI por feature contra a referência BNDES; None com menos de `min_amostras`."""
    valor_por_porte: dict[str, list[float]] = defaultdict(list)
    prazo_por_porte: dict[str, list[float]] = defaultdict(list)
    setores: Counter[str] = Counter()

    for p in pedidos:
        porte = _PORTE_PARA_BNDES.get(p.get("porte", ""), "MICRO")
        if p.get("valor_solicitado") is not None:
            valor_por_porte[porte].append(float(p["valor_solicitado"]))
        if p.get("prazo_meses") is not None:
            prazo_por_porte[porte].append(float(p["prazo_meses"]))
        if p.get("setor"):
            setores[p["setor"]] += 1

    n_valor = sum(len(v) for v in valor_por_porte.values())
    n_prazo = sum(len(v) for v in prazo_por_porte.values())

    def _decis(decis_ref: dict[str, list[float]], por_porte: dict[str, list[float]]):
        return [(decis_ref.get(porte, []), valores) for porte, valores in por_porte.items()]

    return {
        "valor_solicitado": (
            psi_decis(_decis(referencia.valor_decis, valor_por_porte))
            if n_valor >= min_amostras
            else None
        ),
        "prazo_meses": (
            psi_decis(_decis(referencia.prazo_decis, prazo_por_porte))
            if n_prazo >= min_amostras
            else None
        ),
        "setor": (
            psi_categorico(referencia.setor_proporcoes, setores)
            if sum(setores.values()) >= min_amostras
            else None
        ),
    }


def referencia_de_linhas(linhas: Iterable[dict]) -> ReferenciaBNDES:
    """Monta a ReferenciaBNDES a partir das linhas de `bndes_referencia`.

    Para o PSI numérico interessam os decis marginais por porte (secao='todas').
    """
    ref = ReferenciaBNDES()
    for row in linhas:
        tipo, porte = row.get("tipo"), row.get("porte")
        secao, quantil, valor = row.get("secao"), row.get("quantil"), row.get("valor")
        if tipo == "setor":
            ref.setor_proporcoes[secao] = float(valor)
        elif tipo in ("valor", "prazo") and porte != "TODOS" and secao == "todas":
            alvo = ref.valor_decis if tipo == "valor" else ref.prazo_decis
            alvo.setdefault(porte, [None] * 9)[int(round(float(quantil) * 10)) - 1] = float(valor)
    return ref


def _carregar_referencia(client: bigquery.Client, dataset: str) -> ReferenciaBNDES:
    query = f"""
        SELECT tipo, porte, secao, quantil, valor
        FROM `{client.project}.{dataset}.bndes_referencia`
    """
    linhas = [dict(r) for r in client.query(query).result()]
    ref = referencia_de_linhas(linhas)
    # dropa grupos com decis incompletos (ex.: porte sem referência)
    for alvo in (ref.valor_decis, ref.prazo_decis):
        for porte in list(alvo):
            if any(v is None for v in alvo[porte]):
                del alvo[porte]
    return ref


def _carregar_laudos(client: bigquery.Client, dataset: str, n_laudos: int) -> list[dict]:
    query = f"""
        SELECT enriquecidos_json
        FROM `{client.project}.{dataset}.laudos`
        ORDER BY criado_em DESC
        LIMIT {int(n_laudos)}
    """
    pedidos = []
    for row in client.query(query).result():
        pedido = json.loads(row["enriquecidos_json"])["extraidos"]["pedido"]
        pedidos.append(
            {
                "porte": pedido.get("porte"),
                "setor": pedido.get("setor"),
                "valor_solicitado": pedido.get("valor_solicitado"),
                "prazo_meses": pedido.get("prazo_meses"),
            }
        )
    return pedidos


def rodar(project_id: str, dataset: str, n_laudos: int = 100) -> dict:
    """Calcula drift contra o BNDES, loga WARNING acima do limiar e devolve o resumo."""
    client = bigquery.Client(project=project_id)
    referencia = _carregar_referencia(client, dataset)
    pedidos = _carregar_laudos(client, dataset, n_laudos)
    psis = calcular_drift(referencia, pedidos)
    alertas = {
        feat: valor for feat, valor in psis.items() if valor is not None and valor > LIMIAR_PSI
    }
    insuficientes = {feat: None for feat, valor in psis.items() if valor is None}
    for feat in insuficientes:
        logging.info("drift não medido: %s com menos de %d amostras", feat, N_MIN_AMOSTRAS)
    for feat, valor in alertas.items():
        logging.warning("drift detectado: %s PSI=%.4f > %.2f", feat, valor, LIMIAR_PSI)
    return {
        "referencia": "BNDES 2018-2022 (bndes_referencia)",
        "psis": psis,
        "limiar": LIMIAR_PSI,
        "n_laudos_max": n_laudos,
        "n_min_amostras": N_MIN_AMOSTRAS,
        "alertas": alertas,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    resumo = rodar(
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
        n_laudos=int(os.environ.get("DRIFT_N_LAUDOS", "100")),
    )
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())

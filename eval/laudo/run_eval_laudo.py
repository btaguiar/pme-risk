"""Eval do texto do laudo — multi-agente × baseline de chamada única (PLANO §5).

Métricas por braço (juiz determinístico em eval/laudo/fidedignidade.py):
- fidedignidade: % de afirmações verificáveis (números, fatores, normas) com evidência;
- verificado × declarado: % de dados do pedido marcados corretamente no texto
  (⚠️ declarado / ✅ verificado) + classificação estruturada por campo;
- PD citada exatamente; latência da redação.

Os itens em escopo do golden set passam uma vez por Extrator → Pesquisador →
modelo (a PD é a mesma nos dois braços); cada rodada redige de novo nos dois.

Duas etapas: (1) gerar os laudos, salvando textos e insumos no JSON; (2) julgar.
`--rejulgar <json>` refaz só a etapa 2 sobre os mesmos textos, sem LLM — correções
no juiz ficam auditáveis contra os laudos originais.

Run: GCP_PROJECT_ID=<projeto> uv run python -m eval.laudo.run_eval_laudo
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from agents.schemas import DadosEnriquecidos, ResultadoModelo
from eval.laudo.fidedignidade import Julgamento, julgar

RESULTS_DIR = Path(__file__).parent / "results"
GOLDEN_PATH = Path(__file__).parent.parent.parent / "data" / "golden_set" / "pedidos.jsonl"

# Campos de referência com valor literal no texto (rótulos normalizados ficam de fora)
CAMPOS_REFERENCIA = (
    "setor",  # citável entre crases (fator secao_cnae); lista = qualquer seção aceita
    "cnpj",  # citável formatado (12.345.678/0001-00)
    "porte",
    "uf",
    "anos_operacao",
    "faturamento_anual_declarado",
    "valor_solicitado",
    "prazo_meses",
)

MULTI = "multi_agente"
BASELINE = "baseline_chamada_unica"


@dataclass
class Preparado:
    """Item em escopo já extraído, enriquecido e com PD."""

    indice: int
    texto: str
    campos: dict[str, object]
    enriquecidos: DadosEnriquecidos
    resultado: ResultadoModelo

    def insumos(self) -> dict:
        """O que o juiz precisa — serializável, para rejulgar sem GCP."""
        pedido = self.enriquecidos.extraidos.pedido
        return {
            "texto_pedido": self.texto,
            "campos": self.campos,
            "pd": self.resultado.pd,
            "fatores": [list(f) for f in self.resultado.fatores],
            "fonte_por_campo": self.enriquecidos.fonte_por_campo,
            "cnpj_dados": self.enriquecidos.cnpj_dados,
            "n_campos_pedido": len([c for c in pedido.model_dump() if c != "cnpj"])
            if pedido
            else 0,
        }


def carregar_em_escopo() -> list[tuple[int, dict]]:
    itens = [json.loads(ln) for ln in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]
    return [(i, x) for i, x in enumerate(itens) if not x["esperado"].get("fora_de_escopo")]


def preparar(
    indice: int,
    item: dict,
    project_id: str,
    dataset: str,
    extrair_fn: Callable,
    enriquecer_fn: Callable,
    prever_fn: Callable,
) -> Preparado | dict:
    """Extrai → enriquece → PD. Devolve dict de falha se o item não chega ao Redator."""
    from api.pipeline import montar_resultado_modelo, pedido_para_features

    try:
        extraidos = extrair_fn(item["texto_pt_br"], project_id=project_id)
        if extraidos.fora_de_escopo or extraidos.pedido is None:
            return {"indice": indice, "motivo": f"recusado: {extraidos.motivo_recusa}"}
        enriquecidos = enriquecer_fn(extraidos)
        predicao = prever_fn(
            pedido_para_features(extraidos.pedido),
            project_id=project_id,
            dataset=dataset,
            porte=extraidos.pedido.porte,
            uf=extraidos.pedido.uf,
        )
    except Exception as e:
        return {"indice": indice, "motivo": f"{type(e).__name__}: {e}"[:300]}
    return Preparado(
        indice,
        item["texto_pt_br"],
        campos_referencia(item["esperado"]),
        enriquecidos,
        montar_resultado_modelo(predicao),
    )


def campos_referencia(esperado: dict) -> dict[str, object]:
    """Valores de referência do golden set para o juiz.

    Lista só para `setor` (a própria CNAE admite duas seções); nos demais
    campos, lista não é valor único e fica de fora.
    """
    return {
        c: esperado[c]
        for c in CAMPOS_REFERENCIA
        if esperado.get(c) is not None and (c == "setor" or not isinstance(esperado[c], list))
    }


def redigir(braco: str, p: Preparado, redigir_fn: Callable, project_id: str) -> dict:
    """Gera um laudo — devolve texto e evidências (ou o erro), sem julgar."""
    inicio = time.monotonic()
    try:
        if braco == MULTI:
            redacao = redigir_fn(p.enriquecidos, p.resultado, project_id=project_id)
        else:
            redacao = redigir_fn(p.texto, p.resultado, project_id=project_id)
    except Exception as e:
        return {"indice": p.indice, "erro": f"{type(e).__name__}: {e}"[:300]}
    return {
        "indice": p.indice,
        "texto": redacao.texto,
        "evidencias": redacao.evidencias,
        "latencia_s": round(time.monotonic() - inicio, 2),
    }


def julgar_laudo(braco: str, laudo: dict, insumos: dict) -> Julgamento:
    return julgar(
        laudo["texto"],
        laudo["evidencias"],
        insumos["pd"],
        [tuple(f) for f in insumos["fatores"]],
        insumos["campos"],
        insumos["texto_pedido"],
        insumos["fonte_por_campo"] if braco == MULTI else None,
        # .get: JSONs de rodadas anteriores à consulta de CNPJ não têm a chave
        insumos.get("cnpj_dados") if braco == MULTI else None,
    )


def agregar(braco: str, laudos: list[dict], itens: dict[str, dict]) -> dict:
    """Métricas do braço a partir dos laudos salvos e dos insumos por item."""
    gerados = [lo for lo in laudos if "texto" in lo]
    js = [(lo, julgar_laudo(braco, lo, itens[str(lo["indice"])])) for lo in gerados]
    afirm = sum(j.afirmacoes for _, j in js)
    com_ev = sum(j.com_evidencia for _, j in js)
    mencionados = sum(j.campos_mencionados for _, j in js)
    marcados_ok = sum(j.campos_marcados_ok for _, j in js)
    if braco == MULTI:  # classificação estruturada: campos com fonte_por_campo
        total = sum(i["n_campos_pedido"] for i in itens.values())
        classificados = sum(len(i["fonte_por_campo"]) for i in itens.values())
        estruturada = round(classificados / total, 4) if total else None
    else:
        estruturada = 0.0  # texto livre, sem classificação por campo
    problemas = []
    for lo, j in js:
        lista = (
            [f"número: {n}" for n in j.numeros_sem_evidencia]
            + [f"fator: {f}" for f in j.fatores_desconhecidos]
            + [f"norma sem citação: {n}" for n in j.normas_sem_citacao]
            + ["norma fora do corpus"] * j.normas_fora_do_corpus
            + [f"marcação: {c}" for c in j.campos_marcados_errado]
        )
        if lista:
            problemas.append({"indice": lo["indice"], "problemas": lista})
    return {
        "n_laudos": len(gerados),
        "n_falhas": len(laudos) - len(gerados),
        "fidedignidade": round(com_ev / afirm, 4) if afirm else None,
        "afirmacoes": afirm,
        "afirmacoes_com_evidencia": com_ev,
        "laudos_100pct_fieis": sum(j.fidedignidade == 1.0 for _, j in js),
        "pd_citada": sum(j.pd_citada for _, j in js),
        "marcacao_correta": round(marcados_ok / mencionados, 4) if mencionados else None,
        "campos_mencionados": mencionados,
        "marcas_verificado_indevidas": sum(j.marcas_verificado for _, j in js),
        "classificacao_estruturada": estruturada,
        "latencia_redacao_media_s": round(sum(lo["latencia_s"] for lo in gerados) / len(gerados), 2)
        if gerados
        else None,
        "problemas": problemas,
    }


def julgar_saida(saida: dict) -> dict:
    """(Re)calcula as métricas de todas as rodadas a partir dos laudos salvos.

    A referência (`campos`) é recalculada do golden set pelo índice — é
    determinística, e assim JSONs antigos usam os mesmos CAMPOS_REFERENCIA.
    """
    golden = dict(carregar_em_escopo())
    for indice, insumos in saida["itens"].items():
        insumos["campos"] = campos_referencia(golden[int(indice)]["esperado"])
    saida["metricas"] = {
        rodada: {braco: agregar(braco, laudos, saida["itens"]) for braco, laudos in bracos.items()}
        for rodada, bracos in saida["laudos"].items()
    }
    return saida


def gerar(
    project_id: str,
    dataset: str,
    rodadas: int,
    max_itens: int | None,
    workers: int,
    model_version: str | None = None,
) -> dict:
    from agents.extractor.extractor import extrair
    from agents.pesquisador.pesquisador import enriquecer
    from agents.redator.redator import redigir as redigir_multi
    from eval.laudo.baseline_chamada_unica import redigir_baseline
    from model.predict import prever

    if model_version:  # candidato ainda não promovido no registry
        prever = partial(prever, model_version=model_version)

    itens = carregar_em_escopo()[:max_itens] if max_itens else carregar_em_escopo()
    with ThreadPoolExecutor(workers) as pool:
        prep = list(
            pool.map(
                lambda ix: preparar(ix[0], ix[1], project_id, dataset, extrair, enriquecer, prever),
                itens,
            )
        )
    preparados = [p for p in prep if isinstance(p, Preparado)]
    bracos = {MULTI: redigir_multi, BASELINE: redigir_baseline}
    laudos: dict[str, dict[str, list[dict]]] = {}
    for rodada in range(1, rodadas + 1):
        laudos[str(rodada)] = {}
        for braco, fn in bracos.items():
            with ThreadPoolExecutor(workers) as pool:
                laudos[str(rodada)][braco] = list(
                    pool.map(lambda p, b=braco, f=fn: redigir(b, p, f, project_id), preparados)
                )
    return {
        "juiz": "determinístico (eval/laudo/fidedignidade.py)",
        "model_version": model_version or "produção (registry)",
        "n_itens_em_escopo": len(itens),
        "n_preparados": len(preparados),
        "nao_preparados": [p for p in prep if not isinstance(p, Preparado)],
        "itens": {str(p.indice): p.insumos() for p in preparados},
        "laudos": laudos,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nome", default="laudo_texto_v1")
    parser.add_argument("--rodadas", type=int, default=2)
    parser.add_argument("--max-itens", type=int, default=None, help="rodada parcial")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rejulgar", type=Path, default=None, help="JSON salvo; só o juiz")
    parser.add_argument(
        "--model-version", default=None, help="avalia um candidato antes de promover"
    )
    args = parser.parse_args()

    if args.rejulgar:
        path = args.rejulgar
        saida = json.loads(path.read_text(encoding="utf-8"))
    else:
        saida = gerar(
            project_id=os.environ["GCP_PROJECT_ID"],
            dataset=os.environ.get("BQ_DATASET", "pme_risk"),
            rodadas=args.rodadas,
            max_itens=args.max_itens,
            workers=args.workers,
            model_version=args.model_version,
        )
        saida["parcial"] = args.max_itens is not None
        nome = f"{args.nome}_parcial" if args.max_itens else args.nome
        path = RESULTS_DIR / f"{nome}.json"
    julgar_saida(saida)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saida, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for rodada, bracos in saida["metricas"].items():
        for braco, m in bracos.items():
            resumo = {k: v for k, v in m.items() if k != "problemas"}
            print(f"rodada {rodada} {braco}: {json.dumps(resumo, ensure_ascii=False)}")
    print(f"Salvo em: {path}")


if __name__ == "__main__":
    main()

"""Eval da extração — F1 por campo, recusa correta e recusa indevida.

Executa o golden set contra o Extrator e grava em eval/laudo/results/.
Referência: PLANO §5 — matriz de evals

Método v5 (substitui v1–v4, ver `f1_metodo_v4` no JSON para a ponte):
- micro-F1 sobre todos os campos de todos os itens em escopo;
- `null` no esperado = "não mencionado": valor extraído ali é alucinação (FP);
- valor errado conta FP + FN (extraiu algo, e não o certo);
- item em escopo que falha ou é recusado por engano conta como omissão de
  todos os campos — não sai do denominador.

Run: GCP_PROJECT_ID=<projeto> uv run python -m eval.laudo.run_eval
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
GOLDEN_PATH = Path(__file__).parent.parent.parent / "data" / "golden_set" / "pedidos.jsonl"

# Todos os campos de PedidoCredito (agents/schemas.py) — o golden set anota os 9
# em todo item em escopo, com null explícito para "não mencionado".
CAMPOS = [
    "setor",
    "porte",
    "uf",
    "anos_operacao",
    "faturamento_anual_declarado",
    "valor_solicitado",
    "prazo_meses",
    "finalidade",
    "cnpj",
]

# Custo por chamada do Extrator — estimativa fixa, não medida (ver README)
_CUSTO_ESTIMADO_POR_CHAMADA_USD = 0.0001

ACERTO = "acerto"
OMISSAO = "omissao"
ERRO_VALOR = "erro_valor"
ALUCINACAO = "alucinacao"
NEGATIVO = "negativo"  # não mencionado e não extraído — não conta


def classificar_campo(esperado: object, obtido: object) -> str:
    """Classifica um campo extraído contra o esperado."""
    if esperado is None:
        return NEGATIVO if obtido is None else ALUCINACAO
    if obtido is None:
        return OMISSAO
    return ACERTO if obtido == esperado else ERRO_VALOR


def classificar_item(esperado: dict, obtido: dict | None) -> dict[str, str]:
    """Classifica os CAMPOS de um item em escopo; obtido=None é falha/recusa indevida."""
    obtido = obtido or {}
    return {campo: classificar_campo(esperado.get(campo), obtido.get(campo)) for campo in CAMPOS}


@dataclass
class Contagem:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def somar(self, classe: str) -> None:
        if classe == ACERTO:
            self.tp += 1
        elif classe == OMISSAO:
            self.fn += 1
        elif classe == ERRO_VALOR:
            self.fp += 1
            self.fn += 1
        elif classe == ALUCINACAO:
            self.fp += 1

    @property
    def precisao(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precisao, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def f1_metodo_v4(esperado: dict, obtido: dict) -> float:
    """F1 por item como nos evals v1–v4 — mantido só para comparação.

    Defeitos (corrigidos no v5): pula campos com esperado null (não vê
    alucinação), valor errado conta só FP, e o chamador excluía itens com falha.
    """
    tp = fp = fn = 0
    for campo, val_esp in esperado.items():
        if campo in ("fora_de_escopo", "motivo_recusa") or val_esp is None:
            continue
        val_obt = obtido.get(campo)
        if val_obt == val_esp:
            tp += 1
        elif val_obt is None:
            fn += 1
        else:
            fp += 1
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class RelatorioEval:
    """Relatório completo do eval."""

    contagem: Contagem = field(default_factory=Contagem)
    por_campo: dict[str, Contagem] = field(
        default_factory=lambda: {campo: Contagem() for campo in CAMPOS}
    )
    classes: dict[str, int] = field(default_factory=dict)
    f1s_item: list[float] = field(default_factory=list)
    f1s_v4: list[float] = field(default_factory=list)
    n_itens: int = 0
    n_em_escopo: int = 0
    n_falhas_execucao: int = 0
    n_recusas_indevidas: int = 0
    n_recusas_esperadas: int = 0
    n_recusas_corretas: int = 0
    latencias: list[float] = field(default_factory=list)
    divergencias: list[dict] = field(default_factory=list)
    falhas: list[dict] = field(default_factory=list)

    @property
    def taxa_recusa_correta(self) -> float:
        if not self.n_recusas_esperadas:
            return 1.0
        return self.n_recusas_corretas / self.n_recusas_esperadas

    @property
    def taxa_recusa_indevida(self) -> float:
        return self.n_recusas_indevidas / self.n_em_escopo if self.n_em_escopo else 0.0

    @property
    def f1_macro_por_item(self) -> float:
        return sum(self.f1s_item) / len(self.f1s_item) if self.f1s_item else 0.0

    @property
    def f1_v4(self) -> float:
        return sum(self.f1s_v4) / len(self.f1s_v4) if self.f1s_v4 else 0.0


def carregar_golden_set() -> list[dict]:
    """Carrega o golden set."""
    return [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]


def _registrar_item(
    relatorio: RelatorioEval, indice: int, esperado: dict, obtido: dict | None
) -> None:
    """Contabiliza um item em escopo (obtido=None → falha ou recusa indevida)."""
    relatorio.n_em_escopo += 1
    contagem_item = Contagem()
    for campo, classe in classificar_item(esperado, obtido).items():
        relatorio.classes[classe] = relatorio.classes.get(classe, 0) + 1
        relatorio.contagem.somar(classe)
        relatorio.por_campo[campo].somar(classe)
        contagem_item.somar(classe)
        if classe not in (ACERTO, NEGATIVO):
            relatorio.divergencias.append(
                {
                    "indice": indice,
                    "campo": campo,
                    "tipo": classe,
                    "esperado": esperado.get(campo),
                    "obtido": (obtido or {}).get(campo),
                }
            )
    relatorio.f1s_item.append(contagem_item.f1)
    # Método v4 só via itens extraídos com sucesso — replicado aqui para a ponte
    if obtido is not None:
        relatorio.f1s_v4.append(f1_metodo_v4(esperado, obtido))


def executar_golden_set(
    extrair_fn: Callable | None = None,
    project_id: str | None = None,
    max_itens: int | None = None,
) -> RelatorioEval:
    """Executa o golden set contra o Extrator.

    Args:
        extrair_fn: função de extração (para testes) ou None para usar a real
        project_id: GCP project ID
        max_itens: limitar número de itens (rodada parcial, não citável)
    """
    if extrair_fn is None:
        from agents.extractor.extractor import extrair as extrair_fn  # type: ignore[assignment]

    golden = carregar_golden_set()
    if max_itens:
        golden = golden[:max_itens]

    relatorio = RelatorioEval(n_itens=len(golden))

    for i, item in enumerate(golden):
        texto = item["texto_pt_br"]
        esperado = item["esperado"]
        esperado_fora = bool(esperado.get("fora_de_escopo", False))

        inicio = time.monotonic()
        try:
            obtido = extrair_fn(texto, project_id=project_id)
            fora_escopo = obtido.fora_de_escopo
            obtido_dict = obtido.pedido.model_dump() if obtido.pedido else None
        except Exception as e:
            relatorio.latencias.append(time.monotonic() - inicio)
            relatorio.n_falhas_execucao += 1
            relatorio.falhas.append({"indice": i, "erro": f"{type(e).__name__}: {e}"[:300]})
            if esperado_fora:
                relatorio.n_recusas_esperadas += 1  # falha não é recusa correta
            else:
                _registrar_item(relatorio, i, esperado, None)
            continue
        relatorio.latencias.append(time.monotonic() - inicio)

        if esperado_fora:
            relatorio.n_recusas_esperadas += 1
            if fora_escopo:
                relatorio.n_recusas_corretas += 1
            continue

        if fora_escopo:
            relatorio.n_recusas_indevidas += 1
            obtido_dict = None
        _registrar_item(relatorio, i, esperado, obtido_dict)

    return relatorio


def montar_resultado(relatorio: RelatorioEval, parcial: bool) -> dict:
    """Resultado serializável — o JSON citável em README/PLANO."""
    c = relatorio.contagem
    return {
        "metodo": "v5",
        "parcial": parcial,
        "f1_extracao": round(c.f1, 4),
        "precisao": round(c.precisao, 4),
        "recall": round(c.recall, 4),
        "f1_macro_por_item": round(relatorio.f1_macro_por_item, 4),
        "f1_metodo_v4": round(relatorio.f1_v4, 4),
        "tp": c.tp,
        "fp": c.fp,
        "fn": c.fn,
        "classes": dict(sorted(relatorio.classes.items())),
        # null = campo sem nenhum caso avaliável (nem anotado, nem extraído)
        "f1_por_campo": {
            campo: round(ct.f1, 4) if ct.tp + ct.fp + ct.fn else None
            for campo, ct in relatorio.por_campo.items()
        },
        "taxa_recusa_correta": round(relatorio.taxa_recusa_correta, 4),
        "n_recusas_esperadas": relatorio.n_recusas_esperadas,
        "n_recusas_corretas": relatorio.n_recusas_corretas,
        "taxa_recusa_indevida": round(relatorio.taxa_recusa_indevida, 4),
        "n_recusas_indevidas": relatorio.n_recusas_indevidas,
        "n_itens": relatorio.n_itens,
        "n_em_escopo": relatorio.n_em_escopo,
        "n_falhas_execucao": relatorio.n_falhas_execucao,
        "latencia_media_s": round(
            sum(relatorio.latencias) / len(relatorio.latencias) if relatorio.latencias else 0.0,
            2,
        ),
        "custo_estimado_usd": round(len(relatorio.latencias) * _CUSTO_ESTIMADO_POR_CHAMADA_USD, 4),
        "divergencias": relatorio.divergencias,
        "falhas": relatorio.falhas,
    }


def salvar_resultado(resultado: dict, nome: str) -> Path:
    """Salva o resultado em eval/laudo/results/<nome>.json."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{nome}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return output_path


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nome", default="laudo_eval_v5", help="arquivo em results/")
    parser.add_argument("--max-itens", type=int, default=None, help="rodada parcial")
    args = parser.parse_args()

    relatorio = executar_golden_set(
        project_id=os.environ.get("GCP_PROJECT_ID"), max_itens=args.max_itens
    )
    parcial = args.max_itens is not None
    # Rodada parcial nunca sobrescreve o resultado citável
    nome = f"{args.nome}_parcial" if parcial else args.nome
    resultado = montar_resultado(relatorio, parcial)
    path = salvar_resultado(resultado, nome)
    resumo = {k: v for k, v in resultado.items() if k not in ("divergencias", "falhas")}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"Salvo em: {path}")


if __name__ == "__main__":
    main()

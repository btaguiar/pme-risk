"""Testes do runner do eval do laudo com fakes — sem Gemini nem BigQuery."""

from __future__ import annotations

from agents.redator.redator import ResultadoRedacao
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito
from eval.laudo.run_eval_laudo import (
    BASELINE,
    MULTI,
    Preparado,
    agregar,
    julgar_saida,
    preparar,
    redigir,
)
from model.predict import ResultadoPredicao

_ITEM = {
    "texto_pt_br": "Padaria em BH, EPP, 12 anos, fatura R$ 1,8 mi, pede R$ 150 mil.",
    "esperado": {
        "porte": "EPP",
        "uf": "MG",
        "anos_operacao": 12,
        "faturamento_anual_declarado": 1_800_000,
        "valor_solicitado": 150_000,
        "prazo_meses": None,
        "setor": ["industria_transformacao", "comercio"],
    },
}


def _extrair(texto, project_id=None):
    return DadosExtraidos(
        pedido=PedidoCredito(
            setor="industria_transformacao",
            porte="EPP",
            uf="MG",
            anos_operacao=12,
            faturamento_anual_declarado=1_800_000,
            valor_solicitado=150_000,
            finalidade="capital_de_giro",
        )
    )


def _enriquecer(extraidos):
    campos = [c for c in extraidos.pedido.model_dump() if c != "cnpj"]
    return DadosEnriquecidos(
        extraidos=extraidos, fonte_por_campo=dict.fromkeys(campos, "declarado")
    )


def _prever(features, project_id, dataset, **_calib):
    return ResultadoPredicao(
        pd=0.0664,
        faixa_risco="medio",
        fatores=[("log_valor_usd", -0.264), ("faixa_idade", 0.08)],
        model_version="logreg_v3",
    )


def _preparado() -> Preparado:
    p = preparar(1, _ITEM, "proj", "ds", _extrair, _enriquecer, _prever)
    assert isinstance(p, Preparado)
    return p


def test_preparar_usa_golden_e_mantem_os_fatores_do_modelo():
    p = _preparado()
    assert p.campos == {
        "porte": "EPP",
        "uf": "MG",
        "anos_operacao": 12,
        "faturamento_anual_declarado": 1_800_000,
        "valor_solicitado": 150_000,
    }
    # No v3 nenhuma feature é constante no serviço — todas vão ao laudo
    assert [n for n, _ in p.resultado.fatores] == ["log_valor_usd", "faixa_idade"]


def test_preparar_recusa_vira_nao_preparado():
    def recusar(texto, project_id=None):
        return DadosExtraidos(fora_de_escopo=True, motivo_recusa="sem porte")

    r = preparar(9, _ITEM, "proj", "ds", recusar, _enriquecer, _prever)
    assert r == {"indice": 9, "motivo": "recusado: sem porte"}


def test_bracos_julgados_e_agregados():
    p = _preparado()
    itens = {"1": p.insumos()}
    fiel = "PD de 0.0664. EPP ⚠️, 12 anos ⚠️. `log_valor_usd`: -0.264. LGPD art. 20."
    inventado = "PD de 0.0664. EPP ✅, fatura R$ 3.000.000,00."

    def multi(enriquecidos, resultado, project_id=None):
        return ResultadoRedacao(texto=fiel, evidencias=["LGPD art. 20"])

    def baseline(texto, resultado, project_id=None):
        return ResultadoRedacao(texto=inventado, evidencias=[])

    m = agregar(MULTI, [redigir(MULTI, p, multi, "proj")], itens)
    b = agregar(BASELINE, [redigir(BASELINE, p, baseline, "proj")], itens)
    assert m["fidedignidade"] == 1.0 and m["marcacao_correta"] == 1.0
    assert m["classificacao_estruturada"] == 1.0
    assert b["fidedignidade"] == 0.5 and b["marcas_verificado_indevidas"] == 1
    assert b["classificacao_estruturada"] == 0.0
    assert {"indice": 1, "problemas": ["número: 3.000.000,00", "marcação: porte"]} in b["problemas"]


def test_rejulgar_a_partir_do_json_salvo_sem_llm():
    import json

    p = _preparado()
    saida = {
        "itens": {"1": p.insumos()},
        "laudos": {
            "1": {
                MULTI: [
                    {"indice": 1, "texto": "PD de 0.0664.", "evidencias": [], "latencia_s": 1.0}
                ]
            }
        },
    }
    saida = json.loads(json.dumps(saida))  # ida e volta pelo JSON, como no disco
    julgar_saida(saida)
    assert saida["metricas"]["1"][MULTI]["fidedignidade"] == 1.0


def test_falha_na_redacao_e_contada():
    def quebra(*_a, **_k):
        raise RuntimeError("429")

    p = _preparado()
    r = agregar(MULTI, [redigir(MULTI, p, quebra, "proj")], {"1": p.insumos()})
    assert r["n_falhas"] == 1 and r["n_laudos"] == 0

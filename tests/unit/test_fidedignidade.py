"""Testes do juiz determinístico do laudo (eval/laudo/fidedignidade.py)."""

from __future__ import annotations

import pytest

from eval.laudo.fidedignidade import (
    extrair_numeros,
    interpretar_numero,
    julgar,
    normas_citadas,
    tem_evidencia,
)

_FATORES = [("anos_operacao", -0.264278), ("amt_credit", 0.057417)]
_CAMPOS = {"porte": "EPP", "uf": "MG", "anos_operacao": 12, "valor_solicitado": 150000}
_PEDIDO = "Padaria em BH, EPP, 12 anos, pede R$ 150 mil."
_PD = 0.066437


def _julgar(texto: str, evidencias: list[str] | None = None):
    return julgar(
        texto,
        evidencias if evidencias is not None else ["LGPD art. 20"],
        _PD,
        _FATORES,
        _CAMPOS,
        _PEDIDO,
    )


class TestNumeros:
    @pytest.mark.parametrize(
        ("bruto", "esperado"),
        [
            ("1.800.000,00", {1800000.0}),
            ("150.000", {150.0, 150000.0}),
            ("0.057", {0.057}),
            ("5,59", {5.59}),
            ("-0.264", {-0.264}),
        ],
    )
    def test_leituras(self, bruto, esperado):
        assert {v for v, _ in interpretar_numero(bruto)} == esperado

    def test_arredondamento_do_texto_tem_evidencia(self):
        (n,) = extrair_numeros("fator de 0.057")
        assert tem_evidencia(n, {0.057417})

    def test_truncamento_tem_evidencia(self):
        # caso real do golden set, item 1: fatores 0.07468 e -0.03452
        a, b = extrair_numeros("+0.074 e -0.034")
        assert tem_evidencia(a, {0.07468}) and tem_evidencia(b, {-0.03452})

    def test_valor_proximo_mas_diferente_nao_tem_evidencia(self):
        (n,) = extrair_numeros("fator de 0.081")
        assert not tem_evidencia(n, {0.07468})

    def test_percentual_casa_com_pd(self):
        (n,) = extrair_numeros("PD de 6,64%")
        assert tem_evidencia(n, {_PD})

    def test_escala_mil(self):
        (n,) = extrair_numeros("R$ 150 mil")
        assert tem_evidencia(n, {150000})

    def test_titulo_numerado_nao_conta(self):
        # caso real: "## 2. Dados do Solicitante" era contado como afirmação
        assert extrair_numeros("## 2. Dados do Solicitante\n**3. Análise**") == []

    def test_numero_de_norma_e_enumerador_nao_contam(self):
        assert extrair_numeros("1. Conforme Res. CMN 4.966 e LGPD art. 20") == []


class TestNormas:
    def test_permitidas_e_fora_do_corpus(self):
        assert normas_citadas("LGPD art. 20; Res. CMN 4.966; Lei 13.709/2018") == [
            "lgpd_art20",
            "cmn_4966",
            None,
        ]


class TestJulgar:
    def test_laudo_fiel(self):
        j = _julgar(
            "PD de 0.0664 (6,64%). Porte EPP ⚠️, 12 anos ⚠️, R$ 150.000,00 ⚠️.\n"
            "- `anos_operacao`: -0.264\n"
            "Revisão garantida pela LGPD art. 20."
        )
        assert j.fidedignidade == 1.0
        assert j.pd_citada
        assert j.marcacao == 1.0 and j.campos_mencionados == 3

    def test_razao_derivada_do_pedido_tem_evidencia(self):
        # R$ 150 mil / R$ 750 mil = 20% do faturamento
        j = julgar(
            "Pede 20% do faturamento.",
            [],
            _PD,
            _FATORES,
            {**_CAMPOS, "faturamento_anual_declarado": 750000},
            _PEDIDO,
        )
        assert j.fidedignidade == 1.0

    def test_simbolo_errado_no_lugar_de_declarado(self):
        # caso real: Gemini escreveu ☢️ e ‱ no lugar de ⚠️
        j = _julgar("Porte: EPP ☢️\n12 anos ‱")
        assert sorted(j.campos_marcados_errado) == ["anos_operacao", "porte"]

    def test_numero_inventado_derruba_fidedignidade(self):
        j = _julgar("PD de 0.0664. Faturamento de R$ 900.000,00 ⚠️.")
        assert j.numeros_sem_evidencia == ["900.000,00"]
        assert j.fidedignidade == 0.5

    def test_pd_alterada_nao_conta_como_citada(self):
        j = _julgar("PD de 0.0800.")
        assert not j.pd_citada and j.fidedignidade == 0.0

    def test_fator_inexistente(self):
        j = _julgar("- `ebitda`: +0.1")
        assert j.fatores_desconhecidos == ["ebitda"]

    def test_norma_fora_do_corpus_e_norma_sem_citacao(self):
        j = _julgar("Conforme Lei 13.709/2018 e Res. CMN 4.966.", evidencias=[])
        assert j.normas_fora_do_corpus == 1
        assert j.normas_sem_citacao == ["Res. CMN 4.966"]
        assert j.com_evidencia == 0

    def test_dado_declarado_sem_marca_ou_com_verificado(self):
        j = _julgar("Porte: EPP ✅\nUF: MG\n12 anos ⚠️")
        assert j.campos_mencionados == 3
        assert sorted(j.campos_marcados_errado) == ["porte", "uf"]
        assert j.marcas_verificado == 1


def test_faixa_de_risco_entre_crases_e_valida_mas_so_a_correta():
    # caso real: o baseline escreveu `medio`; PD 0.066 → faixa "medio"
    assert _julgar("Faixa `medio`.").fatores_desconhecidos == []
    assert _julgar("Faixa `alto`.").fatores_desconhecidos == ["alto"]


def test_numero_dos_dados_publicos_do_cnpj_tem_evidencia():
    texto = "Segundo a Receita, a empresa opera há 7,2 anos (⚠️ declarado: 5)."
    sem = julgar(texto, [], 0.1, [], {"anos_operacao": 5}, "5 anos")
    com = julgar(
        texto, [], 0.1, [], {"anos_operacao": 5}, "5 anos", cnpj_dados={"anos_operacao": 7.2}
    )
    assert "7,2" in sem.numeros_sem_evidencia
    assert com.numeros_sem_evidencia == []


def test_nome_do_programa_sba_7a_nao_e_numero():
    texto = "O modelo foi treinado em empréstimos do programa SBA 7(a), dos EUA."
    assert extrair_numeros(texto) == []
    # um 7 solto continua sendo afirmação numérica
    assert [n.trecho for n in extrair_numeros("São 7 fatores.")] == ["7"]


def test_cnpj_formatado_vale_se_bate_com_o_pedido():
    texto = "CNPJ 12.345.678/0001-00 informado."
    ok = julgar(texto, [], 0.1, [], {"cnpj": "12345678000100"}, "")
    assert ok.numeros_sem_evidencia == [] and ok.afirmacoes == 1
    errado = julgar(texto, [], 0.1, [], {"cnpj": "99999999000199"}, "")
    assert errado.numeros_sem_evidencia == ["12.345.678/0001-00"]


def test_valor_categorico_do_pedido_entre_crases():
    texto = "O setor `saude_servicos_sociais` reduz o risco."
    ok = julgar(texto, [], 0.1, [], {"setor": "saude_servicos_sociais"}, "")
    assert ok.fatores_desconhecidos == []
    errado = julgar(texto, [], 0.1, [], {"setor": "comercio"}, "")
    assert errado.fatores_desconhecidos == ["saude_servicos_sociais"]


def test_lgpd_por_extenso_e_norma_nao_numero():
    texto = "Direito à revisão conforme o Art. 20 da Lei Geral de Proteção de Dados (LGPD)."
    assert extrair_numeros(texto) == []
    j = julgar(texto, ["LGPD art. 20"], 0.1, [], {}, "")
    assert j.numeros_sem_evidencia == [] and j.normas_sem_citacao == []

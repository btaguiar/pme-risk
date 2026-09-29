"""Pesquisador e consulta pública de CNPJ — sem rede (a consulta é injetada)."""

from __future__ import annotations

import json
import urllib.error
from datetime import date

import pytest

from agents.pesquisador import cnpj
from agents.pesquisador.pesquisador import enriquecer
from agents.schemas import DadosExtraidos, PedidoCredito
from agents.setores import secao_da_cnae

# Forma real da resposta da BrasilAPI (campos que o pme-risk lê + os que descarta)
_BRUTO = {
    "cnpj": "12345678000100",
    "razao_social": "FULANO DE TAL 12345678900",
    "qsa": [{"nome_socio": "FULANO DE TAL"}],
    "email": "fulano@example.com",
    "uf": "SP",
    "cnae_fiscal": 4711302,
    "cnae_fiscal_descricao": "Comércio varejista de mercadorias em geral",
    "data_inicio_atividade": "2020-09-29",
    "porte": "MICRO EMPRESA",
    "opcao_pelo_mei": False,
    "descricao_situacao_cadastral": "ATIVA",
}
_HOJE = date(2026, 9, 29)


def _pedido(**overrides: object) -> DadosExtraidos:
    base = {
        "setor": "comercio",
        "porte": "ME",
        "uf": "SP",
        "anos_operacao": 6,
        "faturamento_anual_declarado": 300_000,
        "valor_solicitado": 40_000,
        "finalidade": "estoque",
        "cnpj": "12345678000100",
    }
    return DadosExtraidos(pedido=PedidoCredito(**{**base, **overrides}))  # type: ignore[arg-type]


def _consulta(dados: dict | None):
    return lambda _cnpj: dados


class TestSecaoDaCnae:
    @pytest.mark.parametrize(
        ("cnae", "secao"),
        [
            (4711302, "comercio"),
            (600001, "industria_extrativa"),  # 0600-0/01: Receita perde o zero
            ("8630-5/04", "saude_servicos_sociais"),
            (5611201, "alojamento_alimentacao"),
            (7500100, "profissionais_cientificas_tecnicas"),  # veterinária é M
            (3600601, "agua_esgoto_residuos"),
        ],
    )
    def test_divisao_para_secao(self, cnae, secao):
        assert secao_da_cnae(cnae) == secao

    def test_divisao_inexistente(self):
        assert secao_da_cnae(4000000) is None  # divisão 40 não existe na CNAE 2.0


class TestNormalizar:
    def test_so_campos_usados_sem_dado_pessoal(self):
        dados = cnpj.normalizar(_BRUTO, _HOJE)
        assert dados["setor"] == "comercio"
        assert dados["porte"] == "ME"
        assert dados["anos_operacao"] == 6.0
        texto = json.dumps(dados, ensure_ascii=False)
        assert "FULANO" not in texto and "email" not in dados and "qsa" not in dados

    def test_mei_prevalece_sobre_porte_cadastral(self):
        dados = cnpj.normalizar({**_BRUTO, "opcao_pelo_mei": True}, _HOJE)
        assert dados["porte"] == "MEI"

    def test_porte_demais_nao_e_pme(self):
        assert cnpj.normalizar({**_BRUTO, "porte": "DEMAIS"}, _HOJE)["porte"] == "DEMAIS"

    def test_porte_nao_informado_fica_none(self):
        assert cnpj.normalizar({**_BRUTO, "porte": None}, _HOJE)["porte"] is None


class TestBuscar:
    def test_url_vazia_desliga(self, monkeypatch):
        monkeypatch.setenv("CNPJ_API_URL", "")
        assert cnpj.consultar_cnpj("12345678000100") is None

    def test_falha_de_rede_vira_none(self, monkeypatch):
        def falhar(*_a, **_k):
            raise urllib.error.URLError("sem rede")

        monkeypatch.setattr(cnpj.urllib.request, "urlopen", falhar)
        assert cnpj.consultar_cnpj("12345678000100") is None


class TestEnriquecer:
    def test_sem_cnpj_tudo_declarado_e_nao_consulta(self):
        def nao_chamar(_cnpj):
            raise AssertionError("não deveria consultar")

        r = enriquecer(_pedido(cnpj=None), consultar=nao_chamar)
        assert r.cnpj_dados is None
        assert set(r.fonte_por_campo.values()) == {"declarado"}

    def test_consulta_sem_resultado_tudo_declarado(self):
        r = enriquecer(_pedido(), consultar=_consulta(None))
        assert set(r.fonte_por_campo.values()) == {"declarado"}

    def test_campos_que_conferem_viram_verificados(self):
        r = enriquecer(_pedido(), consultar=_consulta(cnpj.normalizar(_BRUTO, _HOJE)))
        for campo in ("setor", "porte", "uf", "anos_operacao"):
            assert r.fonte_por_campo[campo] == "verificado", campo
        for campo in ("faturamento_anual_declarado", "valor_solicitado", "finalidade"):
            assert r.fonte_por_campo[campo] == "declarado", campo
        assert r.cnpj_dados["divergencias"] == []

    def test_divergencia_fica_declarada_e_registrada(self):
        publico = cnpj.normalizar({**_BRUTO, "data_inicio_atividade": "2024-09-29"}, _HOJE)
        r = enriquecer(_pedido(anos_operacao=6), consultar=_consulta(publico))
        assert r.fonte_por_campo["anos_operacao"] == "declarado"
        assert r.cnpj_dados["divergencias"] == [
            {"campo": "anos_operacao", "declarado": 6.0, "publico": 2.0}
        ]

    def test_empresa_grande_declarada_me_diverge(self):
        publico = cnpj.normalizar({**_BRUTO, "porte": "DEMAIS"}, _HOJE)
        r = enriquecer(_pedido(porte="ME"), consultar=_consulta(publico))
        assert r.fonte_por_campo["porte"] == "declarado"
        assert {"campo": "porte", "declarado": "ME", "publico": "DEMAIS"} in r.cnpj_dados[
            "divergencias"
        ]

    def test_anos_dentro_da_tolerancia_conferem(self):
        # 6 declarados × 6,5 desde a abertura: arredondamento de quem declara
        publico = cnpj.normalizar({**_BRUTO, "data_inicio_atividade": "2020-03-29"}, _HOJE)
        r = enriquecer(_pedido(anos_operacao=6), consultar=_consulta(publico))
        assert r.fonte_por_campo["anos_operacao"] == "verificado"

    def test_recusa_nao_consulta(self):
        extraidos = DadosExtraidos(fora_de_escopo=True, motivo_recusa="pessoa física")
        r = enriquecer(extraidos, consultar=_consulta(None))
        assert r.fonte_por_campo == {}

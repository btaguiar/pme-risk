"""Mapeamentos SBA ↔ pedido do feature set v3."""

from __future__ import annotations

import pytest

from agents.setores import SETORES_CNAE
from model.mapeamentos import (
    FAIXAS_IDADE,
    NAICS_PARA_SECAO,
    faixa_idade_pedido,
    faixa_idade_sba,
    secao_do_naics,
)

# Setores NAICS 2017 de 2 dígitos (todos os que a SBA pode trazer)
_SETORES_NAICS = [
    "11", "21", "22", "23", "31", "32", "33", "42", "44", "45", "48", "49",
    "51", "52", "53", "54", "55", "56", "61", "62", "71", "72", "81", "92",
]  # fmt: skip


@pytest.mark.parametrize("s2", _SETORES_NAICS)
def test_todo_setor_naics_mapeia_para_secao_valida(s2):
    assert secao_do_naics(s2 + "0000") in SETORES_CNAE


@pytest.mark.parametrize(
    ("naics", "secao"),
    [
        ("722511", "alojamento_alimentacao"),  # restaurante
        ("221122", "eletricidade_gas"),
        ("221310", "agua_esgoto_residuos"),
        ("541511", "informacao_comunicacao"),  # programação sob encomenda
        ("541940", "profissionais_cientificas_tecnicas"),  # veterinária é M
        ("811111", "comercio"),  # oficina mecânica: CNAE G
        ("811210", "outros_servicos"),
        ("532111", "administrativas_servicos_complementares"),  # aluguel de carros
        ("562111", "agua_esgoto_residuos"),
        ("621210", "saude_servicos_sociais"),  # dentista
    ],
)
def test_prefixo_mais_longo_decide(naics, secao):
    assert secao_do_naics(naics) == secao


def test_naics_vazio_ou_desconhecido():
    assert secao_do_naics(None) is None
    assert secao_do_naics("") is None
    assert secao_do_naics("990000") is None


def test_todos_os_valores_do_mapa_sao_setores_validos():
    assert set(NAICS_PARA_SECAO.values()) <= set(SETORES_CNAE)


@pytest.mark.parametrize(
    ("business_age", "faixa"),
    [
        ("Startup, Loan Funds will Open Business", "startup"),
        ("New, Less than 1 Year old", "startup"),
        ("Less than 3 years old but at least 2", "2_5"),
        ("Less than 5 years old but at least 4", "2_5"),
        ("Existing, 5 or more years", "5_mais"),
        ("Unanswered", "desconhecida"),
        ("Existing or more than 2 years old", "desconhecida"),
        ("Change of Ownership", "desconhecida"),
        (None, "desconhecida"),
    ],
)
def test_faixa_sba(business_age, faixa):
    assert faixa_idade_sba(business_age) == faixa


@pytest.mark.parametrize(
    ("anos", "faixa"),
    [(0, "startup"), (1.5, "startup"), (2, "2_5"), (4.9, "2_5"), (5, "5_mais"), (30, "5_mais")],
)
def test_faixa_pedido(anos, faixa):
    assert faixa_idade_pedido(anos) == faixa


def test_servico_so_produz_faixas_que_o_treino_conhece():
    treino = {faixa_idade_sba(b) for b in ("Startup, Loan Funds will Open Business",
              "Less than 3 years old but at least 2", "Existing, 5 or more years")}  # fmt: skip
    servico = {faixa_idade_pedido(a) for a in (0, 1, 3, 10)}
    assert servico <= treino <= set(FAIXAS_IDADE)

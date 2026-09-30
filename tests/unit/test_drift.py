"""Testes do cálculo de PSI — funções puras, sem GCP."""

from __future__ import annotations

import random

from monitoring.drift_job import (
    LIMIAR_PSI,
    ReferenciaBNDES,
    calcular_drift,
    psi,
    psi_categorico,
    psi_decis,
    referencia_de_linhas,
)


def _amostra(n: int, mu: float, sigma: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


def _uniforme(n: int, lo: float, hi: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(lo, hi) for _ in range(n)]


class TestPsi:
    def test_distribuicoes_identicas_psi_zero(self):
        esp = _amostra(5000, 0, 1, seed=42)
        assert psi(esp, esp) == 0.0

    def test_mesma_distribuicao_sementes_diferentes_psi_baixo(self):
        esp = _amostra(5000, 0, 1, seed=1)
        atu = _amostra(5000, 0, 1, seed=2)
        assert psi(esp, atu) < 0.05

    def test_deslocamento_2_sigma_estoura_limiar(self):
        esp = _amostra(5000, 0, 1, seed=1)
        atu = _amostra(5000, 2, 1, seed=2)
        assert psi(esp, atu) > LIMIAR_PSI

    def test_atual_constante_nao_gera_inf_nem_nan(self):
        esp = _amostra(1000, 0, 1, seed=1)
        v = psi(esp, [0.0] * 100)
        assert v == v and v not in (float("inf"), float("-inf"))

    def test_lista_vazia_retorna_zero(self):
        assert psi([], []) == 0.0


class TestPsiDecis:
    def test_distribuicao_nos_proprios_decis_psi_zero(self):
        decis = [10.0 * (i + 1) for i in range(9)]  # cortes 10..90
        valores = [i / 10 for i in range(1000)]  # uniforme 0..100 → ~100 por decil
        assert psi_decis([(decis, valores)]) < 0.01

    def test_deslocamento_estoura_limiar(self):
        decis = [10.0 * (i + 1) for i in range(9)]
        valores = [i / 10 + 50 for i in range(1000)]  # tudo à direita
        assert psi_decis([(decis, valores)]) > LIMIAR_PSI

    def test_mistura_de_grupos_usa_os_decis_do_seu_porte(self):
        decis = [10.0 * (i + 1) for i in range(9)]
        esp = _uniforme(500, 0, 100, seed=1)
        v = psi_decis([(decis, esp[:250]), (decis, esp[250:])])
        assert v < 0.05

    def test_grupo_sem_referencia_ignora_os_valores(self):
        assert psi_decis([([], [1.0, 2.0])]) == 0.0


class TestPsiCategorico:
    def test_distribuicoes_iguais_psi_zero(self):
        esp = {"comercio": 0.5, "saude_servicos_sociais": 0.3, "construcao": 0.2}
        atual = {"comercio": 50, "saude_servicos_sociais": 30, "construcao": 20}
        assert psi_categorico(esp, atual) == 0.0

    def test_distribuicao_diferente_estoura_limiar(self):
        esp = {"comercio": 0.5, "saude_servicos_sociais": 0.3, "construcao": 0.2}
        atual = {"comercio": 0, "saude_servicos_sociais": 0, "construcao": 100}
        assert psi_categorico(esp, atual) > LIMIAR_PSI

    def test_categoria_nova_no_atual_conta(self):
        esp = {"comercio": 1.0}
        atual = {"comercio": 50, "artes_cultura_esporte": 50}
        assert psi_categorico(esp, atual) > LIMIAR_PSI


def _referencia() -> ReferenciaBNDES:
    decis = [10.0 * (i + 1) for i in range(9)]
    return ReferenciaBNDES(
        valor_decis={"MICRO": decis, "PEQUENA": decis},
        prazo_decis={"MICRO": decis, "PEQUENA": decis},
        setor_proporcoes={"comercio": 0.4, "saude_servicos_sociais": 0.35, "construcao": 0.25},
    )


def _pedidos(n: int, fator: float = 1.0, seed: int = 1) -> list[dict]:
    rng = random.Random(seed)
    setores = list(_referencia().setor_proporcoes)
    return [
        {
            "porte": rng.choice(["ME", "EPP", "MEI"]),
            "setor": setores[i % len(setores)],
            "valor_solicitado": rng.uniform(0, 100) * fator,
            "prazo_meses": rng.uniform(0, 100) * fator,
        }
        for i in range(n)
    ]


class TestCalcularDrift:
    def test_sem_drift_fica_abaixo_do_limiar(self):
        drift = calcular_drift(_referencia(), _pedidos(300))
        assert all(v is not None and v < LIMIAR_PSI for v in drift.values())

    def test_deslocamento_de_valor_dispara(self):
        drift = calcular_drift(_referencia(), _pedidos(300, fator=5))
        assert drift["valor_solicitado"] > LIMIAR_PSI

    def test_amostra_pequena_nao_mede(self):
        drift = calcular_drift(_referencia(), _pedidos(5))
        assert all(v is None for v in drift.values())

    def test_prazo_nao_informado_nao_entra_no_psi(self):
        pedidos = _pedidos(300)
        for p in pedidos[:250]:  # só 50 informam prazo (< N_MIN_AMOSTRAS)
            p["prazo_meses"] = None
        drift = calcular_drift(_referencia(), pedidos)
        assert drift["prazo_meses"] is None
        assert drift["valor_solicitado"] is not None


class TestReferenciaDeLinhas:
    def test_monta_decis_mediana_e_setores(self):
        linhas = (
            [
                {
                    "tipo": "valor",
                    "porte": "MICRO",
                    "secao": "todas",
                    "quantil": q,
                    "valor": q * 100,
                }
                for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
            ]
            + [
                {
                    "tipo": "prazo",
                    "porte": "MICRO",
                    "secao": "todas",
                    "quantil": q,
                    "valor": q * 100,
                }
                for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
            ]
            + [
                {
                    "tipo": "setor",
                    "porte": "TODOS",
                    "secao": "comercio",
                    "quantil": None,
                    "valor": 0.7,
                }
            ]
        )
        ref = referencia_de_linhas(linhas)
        assert ref.valor_decis["MICRO"] == [10.0 * (i + 1) for i in range(9)]
        assert ref.setor_proporcoes == {"comercio": 0.7}

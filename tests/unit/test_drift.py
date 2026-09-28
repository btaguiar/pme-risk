"""Testes do cálculo de PSI — função pura, sem GCP."""

from __future__ import annotations

import random

from monitoring.drift_job import LIMIAR_PSI, calcular_drift, psi


def _amostra(n: int, mu: float, sigma: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


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


class TestCalcularDrift:
    def test_retorna_psi_por_feature(self):
        esp = _amostra(2000, 0, 1, seed=1)
        desloc = _amostra(2000, 3, 1, seed=2)
        drift = calcular_drift(
            treino={"amt_credit": esp, "anos_operacao": esp},
            atual={"amt_credit": desloc, "anos_operacao": esp},
        )
        assert drift["amt_credit"] > LIMIAR_PSI
        assert drift["anos_operacao"] < 0.05

    def test_feature_sem_dados_atuais_nao_quebra(self):
        esp = _amostra(100, 0, 1, seed=1)
        drift = calcular_drift(treino={"amt_credit": esp}, atual={})
        assert drift["amt_credit"] == 0.0

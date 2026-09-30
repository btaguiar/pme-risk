"""Calibração SCR — função pura, sem GCP."""

from __future__ import annotations

import math

import pytest

from model.calibracao import FatoresSCR, aplicar


def _fatores(rr_porte: dict[str, float], rr_uf: dict[str, float]) -> FatoresSCR:
    return FatoresSCR(rr_porte=rr_porte, rr_uf=rr_uf)


class TestAplicar:
    def test_rr_1_nao_muda_a_pd(self):
        f = _fatores({"Micro": 1.0, "Pequeno": 1.0}, {"SP": 1.0})
        pd_final, ajustes = aplicar(0.07, "ME", "SP", f)
        assert pd_final == pytest.approx(0.07)
        assert ajustes == [("ajuste_porte_br", 0.0), ("ajuste_uf_br", 0.0)]

    def test_rr_maior_que_1_aumenta_a_pd(self):
        f = _fatores({"Micro": 1.5}, {"AC": 1.5})
        pd_final, ajustes = aplicar(0.07, "ME", "AC", f)
        esperado = 1.0 / (1.0 + math.exp(-(math.log(0.07 / 0.93) + 2 * math.log(1.5))))
        assert pd_final == esperado
        assert ajustes[0] == ("ajuste_porte_br", math.log(1.5))
        assert ajustes[1] == ("ajuste_uf_br", math.log(1.5))

    def test_rr_menor_que_1_diminui_a_pd(self):
        f = _fatores({"Micro": 0.8}, {})
        pd_final, _ = aplicar(0.07, "ME", "SP", f)
        assert pd_final < 0.07

    def test_resultado_sempre_dentro_do_intervalo_aberto(self):
        f = _fatores({"Micro": 50.0}, {"SP": 50.0})
        alto, _ = aplicar(0.999999, "ME", "SP", f)
        assert 0 < alto < 1
        g = _fatores({"Micro": 0.01}, {"SP": 0.01})
        baixo, _ = aplicar(1e-9, "ME", "SP", g)
        assert 0 < baixo < 1

    def test_pd_nas_bordas_nao_estoura(self):
        f = _fatores({"Micro": 1.2}, {"SP": 1.2})
        for pd_borda in (0.0, 1.0):
            pd_final, _ = aplicar(pd_borda, "ME", "SP", f)
            assert 0 < pd_final < 1

    def test_uf_abaixo_do_piso_nao_ajusta(self):
        # UFs abaixo do piso ficam com RR = 1 na origem — aqui, ausentes
        f = _fatores({"Micro": 1.1}, {"SP": 1.1})  # RR não tem 'AC'
        _, ajustes = aplicar(0.07, "ME", "AC", f)
        assert ajustes[1] == ("ajuste_uf_br", 0.0)

    def test_mapeamento_de_porte_mei_me_epp(self):
        f = _fatores({"Micro": 1.3, "Pequeno": 0.9}, {})
        assert f.ajuste_porte("MEI") == math.log(1.3)
        assert f.ajuste_porte("ME") == math.log(1.3)
        assert f.ajuste_porte("EPP") == math.log(0.9)

    def test_porte_desconhecido_sem_ajuste(self):
        f = _fatores({}, {})
        assert f.ajuste_porte("DEMAIS") == 0.0

    def test_ajustes_tem_os_nomes_do_plano(self):
        f = _fatores({"Micro": 1.1}, {"SP": 1.1})
        _, ajustes = aplicar(0.07, "ME", "SP", f)
        assert [nome for nome, _ in ajustes] == ["ajuste_porte_br", "ajuste_uf_br"]

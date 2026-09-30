"""Contador por IP e relógio da demo aberta (api/limites.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from api.limites import ContadorPorIP, ip_do_cliente, segundos_ate_meia_noite_utc


def test_contador_por_ip_zera_na_virada_do_dia():
    c = ContadorPorIP()
    d1, d2 = date(2026, 9, 30), date(2026, 10, 1)
    assert c.tentar("1.1.1.1", 1, hoje=d1)
    assert not c.tentar("1.1.1.1", 1, hoje=d1)
    assert c.tentar("1.1.1.1", 1, hoje=d2)


def test_ip_do_primeiro_salto_do_forwarded_for():
    assert ip_do_cliente("203.0.113.7, 10.0.0.1", "10.0.0.2") == "203.0.113.7"
    assert ip_do_cliente(None, "10.0.0.2") == "10.0.0.2"


def test_segundos_ate_meia_noite():
    agora = datetime(2026, 9, 30, 23, 0, tzinfo=UTC)
    assert segundos_ate_meia_noite_utc(agora) == 3600

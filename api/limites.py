"""Limite de uso da criação pública de laudos (demo aberta).

Cada `POST /laudos` custa Gemini (extração + redação) e BigQuery. Com a demo
aberta (`CRIACAO_PUBLICA=1`), quem não tem a chave de analista cria laudos
dentro de dois limites diários (UTC):

- **por IP** (`LIMITE_POR_IP_DIA`, padrão 3) — em memória: o IP não é gravado
  em lugar nenhum (dado pessoal, LGPD). Zera quando a instância reinicia;
  a barreira de custo de verdade é o teto global.
- **global** (`LIMITE_GLOBAL_DIA`, padrão 30) — contado na trilha de auditoria,
  que registra todo pedido (laudo ou recusa): sobrevive a reinícios e ao
  scale-to-zero do Cloud Run.

Com a chave de analista (`X-API-Key`) não há limite. Sem `CRIACAO_PUBLICA`,
a criação continua exigindo a chave (comportamento anterior).
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, date, datetime, timedelta

LIMITE_POR_IP_PADRAO = 3
LIMITE_GLOBAL_PADRAO = 30


def criacao_publica() -> bool:
    return os.environ.get("CRIACAO_PUBLICA") == "1"


def limite_por_ip() -> int:
    return int(os.environ.get("LIMITE_POR_IP_DIA", LIMITE_POR_IP_PADRAO))


def limite_global() -> int:
    return int(os.environ.get("LIMITE_GLOBAL_DIA", LIMITE_GLOBAL_PADRAO))


def segundos_ate_meia_noite_utc(agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    amanha = datetime.combine(agora.date() + timedelta(days=1), datetime.min.time(), UTC)
    return max(1, int((amanha - agora).total_seconds()))


class ContadorPorIP:
    """Pedidos por IP no dia UTC corrente, só em memória."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dia: date | None = None
        self._contagem: dict[str, int] = {}

    def _virar_dia(self, hoje: date) -> None:
        if self._dia != hoje:
            self._dia = hoje
            self._contagem = {}

    def tentar(self, ip: str, limite: int, hoje: date | None = None) -> bool:
        """Conta o pedido e devolve True se ainda cabia no limite do dia."""
        hoje = hoje or datetime.now(UTC).date()
        with self._lock:
            self._virar_dia(hoje)
            if self._contagem.get(ip, 0) >= limite:
                return False
            self._contagem[ip] = self._contagem.get(ip, 0) + 1
            return True

    def zerar(self) -> None:
        with self._lock:
            self._dia = None
            self._contagem = {}


POR_IP = ContadorPorIP()


def ip_do_cliente(x_forwarded_for: str | None, host: str | None) -> str:
    """Primeiro IP do X-Forwarded-For (o Cloud Run o preenche) ou o do socket."""
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return host or "desconhecido"

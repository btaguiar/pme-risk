"""Consulta pública de CNPJ — dados abertos da Receita Federal via BrasilAPI.

Fonte escolhida em 2026-09-29 no lugar do quimera-core previsto no PLANO §3: o
quimera não tem remote e sua tabela vive em outro projeto GCP. A BrasilAPI é
gratuita e sem chave (cabe na regra de sobrevivência pós-trial) e só recebe o
CNPJ — nenhum outro dado do pedido sai do GCP.

Minimização (LGPD art. 6º, III): só ficam os campos usados na verificação e no
laudo. Razão social, sócios (QSA), e-mail e telefone são descartados — no MEI a
razão social costuma ser o nome da pessoa física.

Falha de rede, timeout ou CNPJ inexistente → None: o pedido segue com tudo
declarado, como antes. A consulta nunca derruba o laudo.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date

from agents.setores import secao_da_cnae

_log = logging.getLogger(__name__)

URL_PADRAO = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
FONTE = "BrasilAPI — dados abertos do CNPJ (Receita Federal)"
TIMEOUT_S = 5.0

# Porte cadastral da Receita → porte do pedido. "DEMAIS" não é PME: fica None.
_PORTE_RECEITA = {"MICRO EMPRESA": "ME", "EMPRESA DE PEQUENO PORTE": "EPP"}


def _buscar(cnpj: str) -> dict | None:
    """GET na API pública. CNPJ_API_URL vazia desliga a consulta (testes, eval offline)."""
    modelo_url = os.environ.get("CNPJ_API_URL", URL_PADRAO)
    if not modelo_url:
        return None
    req = urllib.request.Request(
        modelo_url.format(cnpj=cnpj), headers={"User-Agent": "pme-risk/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        # HTTPError (400/404: CNPJ inválido ou inexistente) é subclasse de URLError
        _log.warning("Consulta de CNPJ falhou: %s", type(e).__name__)
        return None


def _anos_desde(inicio: str, hoje: date) -> float | None:
    try:
        d = date.fromisoformat(inicio)
    except (TypeError, ValueError):
        return None
    return round((hoje - d).days / 365.25, 1)


def normalizar(bruto: dict, hoje: date) -> dict:
    """Resposta da API → só os campos que o pme-risk usa, já no vocabulário do pedido."""
    porte = "MEI" if bruto.get("opcao_pelo_mei") else _PORTE_RECEITA.get(bruto.get("porte") or "")
    cnae = bruto.get("cnae_fiscal")
    return {
        "fonte": FONTE,
        "consultado_em": hoje.isoformat(),
        "cnpj": bruto.get("cnpj"),
        "situacao_cadastral": bruto.get("descricao_situacao_cadastral"),
        "uf": bruto.get("uf"),
        "cnae_fiscal": cnae,
        "cnae_fiscal_descricao": bruto.get("cnae_fiscal_descricao"),
        "setor": secao_da_cnae(cnae) if cnae is not None else None,
        "data_inicio_atividade": bruto.get("data_inicio_atividade"),
        "anos_operacao": _anos_desde(bruto.get("data_inicio_atividade"), hoje),
        "porte": porte,
    }


def consultar_cnpj(cnpj: str, hoje: date | None = None) -> dict | None:
    """Dados públicos normalizados do CNPJ, ou None se a consulta não trouxe nada."""
    bruto = _buscar(cnpj)
    if not bruto:
        return None
    return normalizar(bruto, hoje or date.today())

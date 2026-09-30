"""Mapeamentos SBA ↔ pedido PME para o feature set v3.

NAICS → seção CNAE 2.0
----------------------
NAICS (EUA) e CNAE (Brasil) derivam ambos da ISIC; o mapeamento segue a
concordância NAICS × ISIC Rev. 4 do US Census Bureau no nível de seção. Onde um
setor NAICS de 2 dígitos se divide entre seções CNAE, um prefixo mais longo
decide (casamento pelo prefixo mais longo):

- 2211/2212 energia e gás → D; 2213 água e esgoto → E
- 5151x/517/518/519 e 5415 (sistemas de computação) → J (ISIC 62/63)
- 532/533 aluguel de bens → N (ISIC 77); 531 imobiliário → L
- 55 gestão de empresas → M (ISIC 70)
- 562 resíduos → E (ISIC 38); resto de 56 → N
- 8111 reparação de veículos → G (a CNAE põe reparação de veículos no comércio)
- 814 serviços domésticos → T; resto de 81 → S

Aproximação de seção, não de subclasse: basta para a feature `secao_cnae`.

BusinessAge → faixa de idade
----------------------------
A SBA codifica idade em faixas e **não tem 1–2 anos** (há "New, Less than 1
Year", depois "Less than 3 years old but at least 2"). Faixas do v3:

| Faixa | SBA | Pedido (`anos_operacao`) |
|---|---|---|
| `startup` | Startup (abre o negócio); New, < 1 ano | < 2 (1–2 anos: hipótese, faixa mais próxima em risco) |
| `2_5` | ≥ 2 e < 3; ≥ 3 e < 4; ≥ 4 e < 5 | 2 ≤ anos < 5 |
| `5_mais` | Existing, 5 or more years | ≥ 5 |
| `desconhecida` | Unanswered, vazio, códigos ambíguos antigos, troca de controle | nunca (o pedido sempre informa) |
"""

from __future__ import annotations

from agents.setores import SETORES_CNAE

# Prefixo NAICS → código de setor (agents/setores.py). Casamento pelo mais longo.
NAICS_PARA_SECAO: dict[str, str] = {
    "11": "agropecuaria",
    "21": "industria_extrativa",
    "22": "eletricidade_gas",  # padrão do setor; 2213 decide água/esgoto
    "2211": "eletricidade_gas",
    "2212": "eletricidade_gas",
    "2213": "agua_esgoto_residuos",
    "23": "construcao",
    "31": "industria_transformacao",
    "32": "industria_transformacao",
    "33": "industria_transformacao",
    "42": "comercio",
    "44": "comercio",
    "45": "comercio",
    "48": "transporte_armazenagem",
    "49": "transporte_armazenagem",
    "51": "informacao_comunicacao",
    "52": "financeiro_seguros",
    "53": "atividades_imobiliarias",  # padrão; 532/533 decidem aluguel de bens
    "531": "atividades_imobiliarias",
    "532": "administrativas_servicos_complementares",
    "533": "administrativas_servicos_complementares",
    "54": "profissionais_cientificas_tecnicas",
    "5415": "informacao_comunicacao",
    "55": "profissionais_cientificas_tecnicas",
    "56": "administrativas_servicos_complementares",
    "562": "agua_esgoto_residuos",
    "61": "educacao",
    "62": "saude_servicos_sociais",
    "71": "artes_cultura_esporte",
    "72": "alojamento_alimentacao",
    "81": "outros_servicos",
    "8111": "comercio",
    "814": "servicos_domesticos",
    "92": "administracao_publica",
}

_PREFIXOS = sorted(NAICS_PARA_SECAO, key=len, reverse=True)


def secao_do_naics(naics: str | None) -> str | None:
    """Seção CNAE (código de agents/setores.py) do código NAICS, ou None."""
    if not naics:
        return None
    naics = naics.strip()
    for prefixo in _PREFIXOS:
        if naics.startswith(prefixo):
            return NAICS_PARA_SECAO[prefixo]
    return None


FAIXAS_IDADE = ("startup", "2_5", "5_mais", "desconhecida")

_BUSINESS_AGE_PARA_FAIXA: dict[str, str] = {
    "Startup, Loan Funds will Open Business": "startup",
    "New, Less than 1 Year old": "startup",
    "Less than 3 years old but at least 2": "2_5",
    "Less than 4 years old but at least 3": "2_5",
    "Less than 5 years old but at least 4": "2_5",
    "Existing, 5 or more years": "5_mais",
}


def faixa_idade_sba(business_age: str | None) -> str:
    """Faixa de idade do treino; tudo fora da tabela vira `desconhecida`."""
    return _BUSINESS_AGE_PARA_FAIXA.get((business_age or "").strip(), "desconhecida")


def faixa_idade_pedido(anos_operacao: float) -> str:
    """Faixa de idade no serviço — as mesmas fronteiras do treino."""
    if anos_operacao < 2:
        return "startup"
    if anos_operacao < 5:
        return "2_5"
    return "5_mais"


def _validar() -> None:
    desconhecidos = set(NAICS_PARA_SECAO.values()) - set(SETORES_CNAE)
    if desconhecidos:
        raise ValueError(f"Setores fora de agents/setores.py: {desconhecidos}")


_validar()

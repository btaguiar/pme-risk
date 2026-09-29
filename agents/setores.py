"""Vocabulário fechado de setor — seções da CNAE 2.0 (IBGE/CONCLA).

Até o eval v5 `setor` era rótulo livre em snake_case: o Extrator e o anotador
escreviam sinônimos (`varejo_otica` × `varejo_optica`) e o F1 do campo media
concordância de vocabulário (0.60). A seção CNAE é um padrão externo, é o que
uma consulta de CNPJ devolve e restringe a saída do Gemini via response_schema.

O detalhe do negócio ("padaria", "clínica odontológica") vai em
`PedidoCredito.atividade`, texto livre usado no laudo e não avaliado.
"""

from __future__ import annotations

from typing import Literal

# código → (letra da seção CNAE 2.0, título oficial resumido)
SETORES_CNAE: dict[str, tuple[str, str]] = {
    "agropecuaria": ("A", "Agricultura, pecuária, produção florestal, pesca e aquicultura"),
    "industria_extrativa": ("B", "Indústrias extrativas"),
    "industria_transformacao": ("C", "Indústrias de transformação"),
    "eletricidade_gas": ("D", "Eletricidade e gás"),
    "agua_esgoto_residuos": ("E", "Água, esgoto, gestão de resíduos e descontaminação"),
    "construcao": ("F", "Construção"),
    "comercio": ("G", "Comércio; reparação de veículos automotores e motocicletas"),
    "transporte_armazenagem": ("H", "Transporte, armazenagem e correio"),
    "alojamento_alimentacao": ("I", "Alojamento e alimentação"),
    "informacao_comunicacao": ("J", "Informação e comunicação"),
    "financeiro_seguros": ("K", "Atividades financeiras, de seguros e serviços relacionados"),
    "atividades_imobiliarias": ("L", "Atividades imobiliárias"),
    "profissionais_cientificas_tecnicas": ("M", "Atividades profissionais, científicas e técnicas"),
    "administrativas_servicos_complementares": (
        "N",
        "Atividades administrativas e serviços complementares",
    ),
    "administracao_publica": ("O", "Administração pública, defesa e seguridade social"),
    "educacao": ("P", "Educação"),
    "saude_servicos_sociais": ("Q", "Saúde humana e serviços sociais"),
    "artes_cultura_esporte": ("R", "Artes, cultura, esporte e recreação"),
    "outros_servicos": ("S", "Outras atividades de serviços"),
    "servicos_domesticos": ("T", "Serviços domésticos"),
    "organismos_internacionais": ("U", "Organismos internacionais e outras instituições"),
}

SetorCNAE = Literal[tuple(SETORES_CNAE)]  # type: ignore[valid-type]

# Divisões CNAE 2.0 (2 primeiros dígitos da subclasse) → seção. Faixas oficiais
# do IBGE/CONCLA; é o que liga o `cnae_fiscal` de uma consulta de CNPJ ao setor.
_DIVISOES_POR_SECAO: dict[str, tuple[range, ...]] = {
    "agropecuaria": (range(1, 4),),
    "industria_extrativa": (range(5, 10),),
    "industria_transformacao": (range(10, 34),),
    "eletricidade_gas": (range(35, 36),),
    "agua_esgoto_residuos": (range(36, 40),),
    "construcao": (range(41, 44),),
    "comercio": (range(45, 48),),
    "transporte_armazenagem": (range(49, 54),),
    "alojamento_alimentacao": (range(55, 57),),
    "informacao_comunicacao": (range(58, 64),),
    "financeiro_seguros": (range(64, 67),),
    "atividades_imobiliarias": (range(68, 69),),
    "profissionais_cientificas_tecnicas": (range(69, 76),),
    "administrativas_servicos_complementares": (range(77, 83),),
    "administracao_publica": (range(84, 85),),
    "educacao": (range(85, 86),),
    "saude_servicos_sociais": (range(86, 89),),
    "artes_cultura_esporte": (range(90, 94),),
    "outros_servicos": (range(94, 97),),
    "servicos_domesticos": (range(97, 98),),
    "organismos_internacionais": (range(99, 100),),
}


def secao_da_cnae(cnae: int | str) -> str | None:
    """Código de setor da subclasse CNAE (ex: 4711302 → "comercio").

    Aceita o inteiro da Receita, que perde o zero à esquerda (0600001 → 600001).
    """
    digitos = "".join(c for c in str(cnae) if c.isdigit()).zfill(7)
    if len(digitos) != 7:
        return None
    divisao = int(digitos[:2])
    for secao, faixas in _DIVISOES_POR_SECAO.items():
        if any(divisao in faixa for faixa in faixas):
            return secao
    return None
